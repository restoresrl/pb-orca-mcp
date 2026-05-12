# CLAUDE.md — pb-orca-mcp

Istruzioni locali al progetto. **Lingua di lavoro: italiano.** Se esiste un
`CLAUDE.md` parent (workspace-level), questo lo estende con le specificità
del progetto Python/MCP.

## Stato attuale

**Tutte le fasi 1-7 chiuse** (2026-05-12). `pyproject.toml` a `0.1.0`, 107 test pytest
verdi (incl. `requires_pb` su PB 22.0). Il commit-test loop end-to-end è stato
validato via MCP da Claude Code: discovery → session_open → set_liblist →
set_current_application → compile_entry_import (happy path) → application_rebuild
→ get_last_compile_errors → session_close.

**v0.1.0 RC** è il commit `dcdb74a` ("Phase 7: packaging + docs"). Successivi:
`1b0b45c` fix DLL load (PB runtime dir + MSVC redist dir nel search path) e
`a8f9756` fix `compile_entry_import` ABI (lSrcSize è bytes non chars — vedi sotto).

**Tag `v0.1.0` non ancora creato** — in attesa di un round finale di validazione
post-fix prima di pubblicare. Decisioni residue per PyPI: licenza, disponibilità
nome `pb-orca-mcp` (vedi tabella in `PLAN.md` §"Decisioni residue").

**Prossimo step (da fare dopo riavvio Claude Code)**: il fix `a8f9756`
(`compile_entry_import` size-arg) è già nel codice e coperto da pytest, ma il
server MCP della sessione corrente è ancora quello pre-fix (spawn all'avvio
di Claude Code, non ricarica moduli a runtime). **Riavviare Claude Code
con cwd in `pb-orca-mcp/`** per far ripartire il server `pb-orca` con il
codice nuovo, poi eseguire end-to-end via MCP il **compile-test loop su una
PBL reale**: `pb_session_open` → `pb_set_library_list` → `pb_set_current_application`
→ `pb_library_entry_export` (legge il source) → edit lato agent → `pb_compile_entry_import`
(rimette il source con header `$PBExportHeader$<name>.<ext>` riattaccato) →
`pb_get_last_compile_errors` → `pb_application_rebuild`. Questo è l'ultimo
tassello mancante per validare `v0.1.0` dal lato MCP — i pytest equivalenti
sono già verdi, mancava solo la conferma via tool MCP che il loop funziona
end-to-end con Claude in driver.

## Contesto

`pb-orca-mcp` è un **server MCP Python** che espone l'API ORCA di
PowerBuilder come tool MCP, abilitando Claude Code (e altri client MCP) a
guidare PB in autonomia: ispezionare PBL, compilare entry, rebuild target,
costruire EXE/PBD. Progetto **general-purpose** (non specifico Restore),
target audience = chiunque sviluppi PB e voglia un workflow agentico.

Piano completo: [`PLAN.md`](PLAN.md) nella root del repo (copia versionata
del file originario in `~/.claude/plans/giggly-squishing-hamster.md`).

## Stack & convenzioni

- Python 3.10+, type hints ovunque, `from __future__ import annotations`.
- Build: `hatchling`. Layout: `src/pb_orca_mcp/...` (src layout).
- Test: `pytest`, fixture in `tests/fixtures/`, marker `requires_pb` per test che richiedono PB installato.
- Lint: `ruff` (line-length 100). Type check: `mypy --strict`.
- Stringhe in errori e log in inglese (audience è internazionale). Commit message e doc utente in inglese. Conversazioni con Carlo qui dentro in italiano.

## Cosa NON fare

- **Niente sintassi PowerBuilder qui dentro.** Questo è un repo Python che parla A PowerBuilder via DLL, non un repo PB.
- **Niente assunzioni sul workspace dello sviluppatore.** Il server deve girare su qualsiasi macchina Windows con PB IDE installato. Niente hardcoded path utente-specifici (tipo `C:\<vendor>\workspace\...`).
- **Niente mock di ORCA nei test "core".** I test contro `pborc.dll` reale sono `requires_pb` e skippati in CI. Mock ammesso solo per unit test di parsing/discovery, non per il loop compile.
- **Niente PowerGen / OrcaScript / .gen file.** Sono workflow batch legacy che esistono in altri workspace; non sono target di questo repo.

## Cose da tenere a mente

- **Multi-version core**: il loader gestisce qualsiasi installazione PB con `pborc.dll` (la DLL è sempre `<install>\IDE\pborc.dll`, no suffisso versione). `KNOWN_VERSIONS = ("19.0", "22.0", "25.0")` sono solo le testate; release non elencate vengono trovate dal discovery e marcate `tested: false`. ABI ORCA stabile da PB 2019.
- **IDE vs runtime**: il discovery filtra runtime-only (senza `pborc.dll`). Non confonderli.
- **Callback lifetime ctypes**: `CFUNCTYPE` Python tenute in `Session._callback_refs` per evitare GC durante chiamate C — errore classico che crashera silenziosamente.
- **ORCA single-session per process** e non thread-safe. `asyncio.Lock` globale attorno a ogni chiamata ORCA quando il server MCP esegue tool in parallelo.
- **x86 vs x64**: Python deve girare nella stessa arch della DLL caricata. Documentato in `docs/installation.md`.
- **Path Windows con `\`**: ORCA è Win32-only. Accettiamo `/` in input e normalizziamo internamente con `Path` / `os.path`.
- **`PBORCA_CompileEntryImport` lSrcSize è in BYTES, non chars**. Per Unicode (UTF-16 LE) significa `len(syntax) * 2` (NON `+1` né `len(syntax)`). Con il valore sbagliato ORCA scansiona solo metà bytes e aborta con `C0114 "Error scanning object source entry"` prima del compiler. Coperto da `test_compile_entry_import_happy_path_application` in `tests/test_session_real.py` (regression sentinel: inverti il fix e quel test fallisce con la firma C0114 esatta). Vale anche per `compile_entry_import_list`.
- **PB source export (`.sra`/`.srf`/`.srw`/...)** è **UTF-16 LE con BOM** + **CRLF** + prima riga obbligatoria `$PBExportHeader$<name>.<ext>` (eventuale seconda riga `$PBExportComments$<comment>`). Da leggere con `path.read_bytes()` poi `raw[2:].decode("utf-16-le")` se inizia con `FF FE`. Marcati come binary in `.gitattributes` perché git deve preservarli byte-identical.
- **Asimmetria export/import**: `library_entry_export` ritorna **solo il body** (senza `$PBExportHeader$...`), mentre `compile_entry_import` lo **richiede**. Roundtrip diretto export→import senza riattacccare l'header non funziona. La recipe in `docs/recipes.md` è imprecisa su questo punto (TODO chiarire).
- **Bootstrap catch-22 per PBL vuote**: `SessionSetCurrentAppl` rifiuta con `PBORCA_OBJNOTFOUND (-3)` un app_name che non esiste già nella pbl, ma `CompileEntryImport` richiede current_app set anche per importare la PRIMA application. Non c'è in-API per creare l'app object iniziale di una PBL vuota — PB IDE usa un path di alto livello che ORCA non espone. Workaround per i test: ship una PBL pre-built come fixture (vedi `tests/fixtures/tiny_app/genapp.pbl`).
- **`compile_entry_import` non è atomico**: anche su error ORCA scrive il source (eventualmente truncated) nel `.pbl`. Quindi un import fallito può corrompere il source originale dell'entry. Se servono semantiche atomiche, snapshot dei bytes della pbl prima della call e restore on failure.

## Riferimenti

- Plan file (versionato nel repo): [`PLAN.md`](PLAN.md)
- ORCA Programmers Guide R3: https://docs.appeon.com/pb2022r3/orca_guide
