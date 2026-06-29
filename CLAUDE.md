# CLAUDE.md — pb-orca-mcp

Istruzioni locali al progetto. **Lingua di lavoro: italiano.**
Processo di sviluppo interno (release, restart, sibling, stato): vedi
[`DEVELOPMENT.md`](DEVELOPMENT.md).

## Contesto

`pb-orca-mcp` è un **server MCP Python** che espone l'API ORCA di PowerBuilder come
tool MCP, abilitando Claude Code a guidare PB in autonomia: ispezionare PBL,
compilare entry, rebuild target, costruire EXE / PBD / dynamic library. Progetto
**general-purpose** (non Restore-specifico): audience = chiunque sviluppi PB e voglia
un workflow agentico.

## Stack & convenzioni

- Python 3.10+, type hints ovunque, `from __future__ import annotations`.
- Build: `hatchling`, src layout (`src/pb_orca_mcp/...`).
- Test: `pytest`, fixture in `tests/fixtures/`, marker `requires_pb` (skip di
  default; abilitati con `PB_ORCA_MCP_HAS_PB=1` + interprete della stessa arch della
  DLL).
- Comandi: `pytest tests` · `ruff check src tests` · `ruff format --check src tests` ·
  `mypy src` (line-length 100, `mypy --strict`).
- Stringhe in errori/log e doc utente in **inglese** (audience internazionale);
  conversazioni qui in italiano.

## Cosa NON fare

- **Niente sintassi PowerBuilder qui dentro.** È un repo Python che parla A
  PowerBuilder via DLL, non un repo PB.
- **Niente path utente-specifici hardcoded.** Il server deve girare su qualsiasi
  macchina Windows con PB IDE installato.
- **Niente mock di ORCA nei test "core".** I test contro `pborc.dll` reale sono
  `requires_pb`. Mock ammesso solo per unit test di parsing/discovery.
- **Niente PowerGen / OrcaScript / .gen file.** Workflow batch legacy, fuori scope.
- **Niente scrittura di file `.sr*` su disco.** Il server è puro ORCA (in-memory →
  `.pbl`). La scrittura del SOT file (header `$PBExportHeader$` + encoding/BOM +
  CRLF) è fuori scope: la fa il chiamante con i propri strumenti (vedi
  `docs/usage.md` Recipe 1.5). Questo repo è **indipendente** da qualsiasi tool
  esterno per quel passo.

## Cose da tenere a mente (gotcha)

### Discovery / arch / OS

- **Multi-version**: il loader gestisce qualsiasi install con `<install>\IDE\pborc.dll`.
  `KNOWN_VERSIONS = ("19.0","22.0","25.0")` sono solo le testate; le altre vengono
  trovate e marcate `tested: false`. ABI ORCA stabile da PB 2019.
- **IDE vs runtime**: il discovery filtra le install runtime-only (senza `pborc.dll`).
- **x86 vs x64**: Python deve girare nella stessa arch della DLL caricata (vedi
  `docs/installation.md`).
- **Path Windows**: accettiamo `/` in input e normalizziamo internamente con `Path`.

### ORCA / ctypes

- **Single-session per process e non thread-safe**: `asyncio.Lock` globale attorno a
  ogni chiamata ORCA.
- **Callback lifetime**: `WINFUNCTYPE` tenute in `Session._callback_refs` per evitare
  GC durante le chiamate C (altrimenti crash silenzioso).

### Source format / compile

- **`PBORCA_CompileEntryImport` lSrcSize è in BYTES, non chars** → per UTF-16 LE
  `len(syntax) * 2` (NON `+1` né `len`). Valore sbagliato = ORCA scansiona metà bytes
  e aborta con `C0114 "Error scanning object source entry"`. Regression sentinel:
  `test_compile_entry_import_happy_path_application` in `tests/test_session_real.py`.
  Vale anche per `compile_entry_import_list`.
- **Export PB (`.sra`/`.srf`/`.srw`/…)** = UTF-16 LE + BOM + CRLF + prima riga
  `$PBExportHeader$<name>.<ext>`. Marcati binary in `.gitattributes`.
- **Asimmetria export/import**: `library_entry_export` ritorna **solo il body**;
  `compile_entry_import` **richiede** l'header. Niente roundtrip diretto senza
  riattaccarlo. Vedi `docs/usage.md` Recipe 1.
- **Bootstrap catch-22 PBL vuote**: `SessionSetCurrentAppl` rifiuta un app_name non
  esistente (`PBORCA_OBJNOTFOUND -3`), ma `CompileEntryImport` richiede current_app
  set anche per importare la PRIMA application. Nessuna in-API per creare l'app
  iniziale → fixture PBL pre-built (`tests/fixtures/tiny_app/genapp.pbl`).
- **`compile_entry_import` non è atomico**: su error ORCA scrive comunque il source
  (eventualmente truncated) nel `.pbl` → un import fallito può corrompere l'entry. Se
  serve atomicità, snapshot dei bytes pre-call e restore on failure.

## Riferimenti

- Processo dev interno + stato + design rationale: [`DEVELOPMENT.md`](DEVELOPMENT.md).
- ORCA Programmers Guide R3: https://docs.appeon.com/pb2022r3/orca_guide
- ORCA C header (ABI canonico): `<install>\SDK\ORCA\pborca.h`.
