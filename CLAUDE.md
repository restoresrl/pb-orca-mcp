# CLAUDE.md — pb-orca-mcp

Istruzioni locali al progetto. **Lingua di lavoro: italiano.** Se esiste un
`CLAUDE.md` parent (workspace-level), questo lo estende con le specificità
del progetto Python/MCP.

## Contesto

`pb-orca-mcp` è un **server MCP Python** che espone l'API ORCA di
PowerBuilder come tool MCP, abilitando Claude Code (e altri client MCP) a
guidare PB in autonomia: ispezionare PBL, compilare entry, rebuild target,
costruire EXE / PBD / dynamic library. Progetto **general-purpose** (non
Restore-specifico): audience = chiunque sviluppi PB e voglia un workflow
agentico.

## Stato

**v0.1.0 rilasciata** (tag `v0.1.0`, 2026-05-13). 29 tool MCP che coprono
il full ORCA loop. 107 pytest verdi incluso l'happy-path `requires_pb` su
PB 22.0. Compile-test loop end-to-end validato sia da pytest sia da MCP
con Claude Code in driver.

Repo: https://github.com/restoresrl/pb-orca-mcp — **privato Restore
org, in fase di dogfooding interno**. Flip a pubblico + PyPI publish
rimandati a quando l'uso reale su workspace Magware reali avrà
confermato stabilità. Nessuna scadenza fissa.

**Stato pre-publish** (vedi anche `PLAN.md`): pre-flight cleanups
docs/hygiene già fatti (commit `876c34d` 2026-05-14). Nome `pb-orca-mcp`
su PyPI verificato libero. Count tool allineato a 29 in README/PLAN/docs
(include il gruppo SCC). Licenza MIT. Fix asimmetria export/import in
`docs/recipes.md` Recipe 1 committato (`67d97f3`). Wheel + sdist
buildati localmente in `dist/`, pronti per twine upload futuro. Restano
da fare al momento del flip: aggiornare la nota in fondo a questa
sezione + `gh repo edit ... --visibility public` + `twine upload`.

## Stack & convenzioni

- Python 3.10+, type hints ovunque, `from __future__ import annotations`.
- Build: `hatchling`. Layout: `src/pb_orca_mcp/...` (src layout).
- Test: `pytest`, fixture in `tests/fixtures/`, marker `requires_pb` per
  test che richiedono PB installato (skip default; abilitati con
  `PB_ORCA_MCP_HAS_PB=1`).
- Lint: `ruff` (line-length 100). Type check: `mypy --strict`.
- Stringhe in errori e log in inglese (audience è internazionale). Commit
  message e doc utente in inglese. Conversazioni con Carlo qui dentro in
  italiano.

## Workflow di sviluppo

- **Interprete per test reali**: sull'host con PB IDE installato serve
  Python che matchi l'architettura della DLL. PB IDE 19/22/25 è x86,
  quindi sull'host di Carlo c'è `.venv-x86/Scripts/python.exe` come
  interprete dedicato per i `requires_pb`.
- **Test loop**:
  - `pytest tests` per la suite (i `requires_pb` skip senza
    `PB_ORCA_MCP_HAS_PB=1`).
  - Con env var settata, run completi sull'host con PB. Il fixture
    `tests/fixtures/tiny_app/genapp.pbl` + `genapp.sra` copre l'happy
    path del compile loop.
- **MCP server reload**: il server `pb-orca` viene spawned da Claude Code
  all'avvio (config in `.claude/mcp.json`, NON committed perché contiene
  il path locale al `.venv-x86`). Il server **non ricarica i moduli a
  runtime**, quindi una modifica al codice in `src/` richiede **riavvio
  di Claude Code** per essere testabile via tool MCP. I pytest invece
  vedono le modifiche immediatamente (editable install).
- **Restart strategy — resume prima, handoff come fallback**: il restart
  MCP fa perdere il contesto conversazionale se la nuova sessione parte
  fresca. Soluzione **preferita**: Carlo lancia `claude --resume` (o
  `claude -c` per continue last) dopo il restart → il transcript JSONL
  viene ricaricato → tutto il ragionamento è preservato, niente da
  salvare. Quando suggerisco un restart, suggerisco anche `--resume`.
  Soluzione **fallback** (handoff memory): vale solo quando il resume
  non è praticabile — conversazione molto lunga e context vicino al
  limite, sessione "sporca" che si vuole scartare, sessioni separate
  da giorni. In quei casi salvo `memory/handoff_<topic>.md` con:
  (1) modifiche uncommitted (file + 1 riga), (2) stato test, (3) passi
  di validazione con comandi e outcome attesi, (4) decisioni aperte,
  (5) anti-redo notes. Linko l'handoff in `MEMORY.md` con marker
  **HANDOFF** e lo cancello a validazione confermata. Vedi
  [[save-operational-plans-before-restart]] per il razionale.
- **Pre-commit hygiene** (manuale): ruff + mypy + pytest verdi prima del
  commit. Per i commit destinati al repo pubblico, vale anche la grep
  della memory `public-repo-hygiene` (no riferimenti Restore-internal,
  no path utente-specifici).
- **Release loop**: feature/fix → pytest verde → smoke test via MCP con
  Claude Code in driver → commit + push → tag annotato `vX.Y.Z` →
  `git push origin vX.Y.Z` → (futuro PyPI) `python -m build` + `twine
  upload`. Per release "significative" includere note di release nel
  messaggio del tag (vedi `git show v0.1.0` come modello).

## Cosa NON fare

- **Niente sintassi PowerBuilder qui dentro.** Questo è un repo Python
  che parla A PowerBuilder via DLL, non un repo PB.
- **Niente assunzioni sul workspace dello sviluppatore.** Il server
  deve girare su qualsiasi macchina Windows con PB IDE installato.
  Niente hardcoded path utente-specifici (tipo `C:\<vendor>\workspace\...`).
- **Niente mock di ORCA nei test "core".** I test contro `pborc.dll`
  reale sono `requires_pb` e skippati in CI. Mock ammesso solo per unit
  test di parsing/discovery, non per il loop compile.
- **Niente PowerGen / OrcaScript / .gen file.** Sono workflow batch
  legacy che esistono in altri workspace; non sono target di questo repo.

## Cose da tenere a mente

### Discovery, arch, OS

- **Multi-version core**: il loader gestisce qualsiasi installazione PB
  con `pborc.dll` (la DLL è sempre `<install>\IDE\pborc.dll`, no suffisso
  versione). `KNOWN_VERSIONS = ("19.0", "22.0", "25.0")` sono solo le
  testate; release non elencate vengono trovate dal discovery e marcate
  `tested: false`. ABI ORCA stabile da PB 2019.
- **IDE vs runtime**: il discovery filtra runtime-only (senza `pborc.dll`).
  Non confonderli.
- **x86 vs x64**: Python deve girare nella stessa arch della DLL caricata.
  Documentato in `docs/installation.md`.
- **Path Windows con `\`**: ORCA è Win32-only. Accettiamo `/` in input e
  normalizziamo internamente con `Path` / `os.path`.

### ORCA / ctypes internals

- **ORCA single-session per process e non thread-safe**: `asyncio.Lock`
  globale attorno a ogni chiamata ORCA quando il server MCP esegue tool
  in parallelo.
- **Callback lifetime ctypes**: `WINFUNCTYPE` Python tenute in
  `Session._callback_refs` per evitare GC durante chiamate C — errore
  classico che crasha silenziosamente.

### Source format / compile gotchas

- **`PBORCA_CompileEntryImport` lSrcSize è in BYTES, non chars**. Per
  Unicode (UTF-16 LE) significa `len(syntax) * 2` (NON `+1` né
  `len(syntax)`). Con il valore sbagliato ORCA scansiona solo metà bytes
  e aborta con `C0114 "Error scanning object source entry"` prima del
  compiler. Coperto da `test_compile_entry_import_happy_path_application`
  in `tests/test_session_real.py` (regression sentinel: inverti il fix e
  quel test fallisce con la firma C0114 esatta). Vale anche per
  `compile_entry_import_list`.
- **PB source export (`.sra`/`.srf`/`.srw`/...)** è **UTF-16 LE con BOM**
  + **CRLF** + prima riga obbligatoria `$PBExportHeader$<name>.<ext>`
  (eventuale seconda riga `$PBExportComments$<comment>`). Da leggere con
  `path.read_bytes()` poi `raw[2:].decode("utf-16-le")` se inizia con
  `FF FE`. Marcati come binary in `.gitattributes`.
- **Asimmetria export/import**: `library_entry_export` ritorna **solo il
  body** (senza `$PBExportHeader$...`), mentre `compile_entry_import` lo
  **richiede**. Roundtrip diretto export→import senza riattaccare
  l'header non funziona. Documentato in `docs/recipes.md` Recipe 1
  (commit `67d97f3`) e in `docs/workflow.md`.
- **Bootstrap catch-22 per PBL vuote**: `SessionSetCurrentAppl` rifiuta
  con `PBORCA_OBJNOTFOUND (-3)` un app_name che non esiste già nella pbl,
  ma `CompileEntryImport` richiede current_app set anche per importare
  la PRIMA application. Non c'è in-API per creare l'app object iniziale
  di una PBL vuota — PB IDE usa un path di alto livello che ORCA non
  espone. Workaround per i test: ship una PBL pre-built come fixture
  (vedi `tests/fixtures/tiny_app/genapp.pbl`).
- **`compile_entry_import` non è atomico**: anche su error ORCA scrive il
  source (eventualmente truncated) nel `.pbl`. Quindi un import fallito
  può corrompere il source originale dell'entry. Se servono semantiche
  atomiche, snapshot dei bytes della pbl prima della call e restore on
  failure.

## Sibling project — `pb-ai-code`

Esiste un repo gemello, `../pb-ai-code/` (creato 2026-05-14, ancora in
design phase): è il **dev kit agentico per PowerBuilder** che ha
`pb-orca-mcp` come dipendenza required e ci costruisce sopra skill, docs
Appeon ingestite, orchestrazione di test, pattern di debug post-mortem e
slash command. La visione 4-pilastri (progettazione + coding + testing +
debugging agentico su PB) vive lì, non qui.

`pb-orca-mcp` resta scope-limited all'API ORCA (engine + primitive); la
parte di workflow + knowledge + orchestrazione sta in `pb-ai-code`
(experience). Lavoro attivo su `pb-ai-code` parte **dopo** il PyPI
publish di questo repo.

Vedi [`../pb-ai-code/PLAN.md`](../pb-ai-code/PLAN.md) per il design
completo e [[sibling-pb-ai-code]] in memory per il quick reference.

## Riferimenti

- Piano originale (storico, fasi 1-7 chiuse): [`PLAN.md`](PLAN.md). Lista
  delle decisioni residue per PyPI ancora rilevanti.
- ORCA Programmers Guide R3:
  https://docs.appeon.com/pb2022r3/orca_guide
- ORCA C header (canonical ABI source):
  `<install>\SDK\ORCA\pborca.h` su ogni installazione PB IDE.
- Layout binario PBL (reverse engineering): `docs/pbl-file-format.txt`.
