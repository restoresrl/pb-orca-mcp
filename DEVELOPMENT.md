# DEVELOPMENT.md — processo interno + design rationale

Note di sviluppo interne a `pb-orca-mcp`. **File interno, NON incluso nel
package** (l'`include` di sdist in `pyproject.toml` è una allowlist e questo file
non è elencato). Al flip a repo pubblico va rimosso o curato (es. estraendone un
`ARCHITECTURE.md` pubblico, in inglese e ripulito). **Lingua: italiano.**

## Stato & flip pubblico

Stato corrente e maturità: vedi README §Status (single source of truth). In
breve: repo privato `restoresrl/pb-orca-mcp`, **dogfooding interno**; il flip a
**GitHub pubblico** è rimandato finché l'uso reale su workspace PB non conferma
stabilità — nessuna scadenza.

Checklist al momento del flip (cose ancora da fare):

- scrub `public-repo-hygiene` (no riferimenti Restore-internal, no path
  utente-specifici);
- rimuovere o curare questo `DEVELOPMENT.md`;
- `gh repo edit ... --visibility public`;
- (opzionale) GitHub Release sul tag `vX.Y.Z` per install pinnati via
  `uvx --from git+...@vX.Y.Z`.

## Workflow di sviluppo

- **Interprete per i test reali**: i `requires_pb` caricano `pborc.dll`, quindi
  serve un Python della stessa arch della DLL (PB IDE 19/22/25 è x86) → sull'host
  di sviluppo c'è un `.venv-x86/Scripts/python.exe` dedicato.
- **Test loop**: `pytest tests` per la suite (i `requires_pb` skip senza
  `PB_ORCA_MCP_HAS_PB=1`); con l'env var + venv x86, run completi sull'host con
  PB. Fixture `tests/fixtures/tiny_app/genapp.pbl` (+ `genapp.sra`) per l'happy
  path del compile loop.
- **Il server MCP NON fa hot-reload**: è spawnato da Claude Code all'avvio
  (config in `.claude/mcp.json`, non committed — contiene il path locale al venv
  x86). Una modifica a `src/` richiede **riavvio di Claude Code** per essere
  testabile via tool MCP; i pytest la vedono subito (editable install).
- **Restart → preferisci `claude --resume`** (o `-c`) per non perdere il
  contesto conversazionale; handoff memory solo come fallback (conversazione
  troppo lunga, context vicino al limite, sessione da scartare). Dettaglio:
  memorie `suggest-resume-on-restart`, `save-operational-plans-before-restart`.
- **Pre-commit hygiene** (manuale): `ruff check` + `ruff format --check` +
  `mypy src` + `pytest` verdi prima del commit.
- **Release loop**: feature/fix → pytest verde → smoke test via MCP con Claude
  Code in driver → commit + push → tag annotato `vX.Y.Z` → `git push origin
  vX.Y.Z` → (eventuale) GitHub Release sul tag, per install pinnati via
  `uvx --from git+...@vX.Y.Z`. Per release significative, note nel messaggio del
  tag (`git show v0.1.0` come modello).

## Progetti correlati

`pb-orca-mcp` è **indipendente** da `pb-format` e `pb-ai-code`: sono citati
**solo** nel README §Related projects, e questo repo non li importa né li
richiede. Relazione e storia: memorie `sibling-pb-format`, `sibling-pb-ai-code`.

## Design rationale (perché queste scelte)

Il design document completo (fasi 1-7, ormai tutte realizzate: scaffolding,
roadmap, schema I/O, checklist di verifica) viveva in `PLAN.md`, rimosso dal
working tree — git history lo conserva. Qui restano solo le decisioni con valore
duraturo e non ovvie dal codice.

**Scope.** Selezione versione PB **esplicita** (`pb_version` / `install_path` su
`pb_session_open`): i file `.pbt`/`.pbw` **non** contengono la versione PB (solo
il magic costante `Save Format v3.0(19990112)`, congelato dal 1999-01-12) →
niente auto-pick né inferenza. Multi-version e distinzione IDE vs runtime sono
requisiti core, non rinviati. ABI ORCA stabile da PB 2019 → un solo set di
prototypes copre 19/22/25.

**Formato `.pbt` / `.pbw`** (verificato su file reali PB 19/22/25): righe
`key "value";`, keyword case-insensitive (`LibList` ↔ `liblist`), path con
escape C-string (`..\\dep\\x.pbl`), `LibList` separa con `;`. Il `.pbw` elenca i
target in `@begin Targets … @end;` + `DefaultTarget` / `DefaultExportEncode`.
Nessuna versione PB presente in nessuno dei due.

**Tool ORCA deliberatamente NON esposti:**

- `PBORCA_BuildProject*` — deprecati in R3, usiamo `ApplicationRebuild`.
- `PBORCA_LibraryEntryCopy` — ridondante con `Move` + `Export` + `CompileEntryImport`.
- `Scc*` online (MSSCCI provider) — esposto solo l'offline git/svn (= "Refresh PBL").

**Funzioni che NON esistono in ORCA** (verificato su `PBORCA.H` 19/22/25):

- `PBORCA_LibraryEntryCommentModify` — non esiste; il commento di un'entry si
  cambia re-importandola con `CompileEntryImport` + nuovo `lpszComments`.
  (`PBORCA_LibraryCommentModify` esiste, ma modifica il commento della PBL stessa.)

**Decisioni risolte:** licenza MIT; git remote `restoresrl/pb-orca-mcp`
(push 2026-05-12).
