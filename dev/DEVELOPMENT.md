# DEVELOPMENT.md — processo interno

Note di sviluppo interne a `pb-orca-mcp`, estratte da `CLAUDE.md` per non
gonfiarne il contesto auto-caricato. **Cartella `dev/` interna, non pubblica.**
**Lingua: italiano.**

## Stato

**v0.1.0 rilasciata** (tag `v0.1.0`, 2026-05-13). 29 tool MCP che coprono il full
ORCA loop. Suite pytest verde incluso l'happy-path `requires_pb` su PB 22.0.
Compile-test loop end-to-end validato sia da pytest sia da MCP con Claude Code in
driver.

Repo: `restoresrl/pb-orca-mcp` — **privato, in fase di dogfooding interno**. Flip a
pubblico + PyPI publish rimandati a quando l'uso reale su workspace PB reali avrà
confermato stabilità. Nessuna scadenza fissa.

**Stato pre-publish** (vedi anche `dev/PLAN.md`): pre-flight cleanups docs/hygiene
fatti. Nome `pb-orca-mcp` su PyPI verificato libero. Licenza MIT. Wheel + sdist
buildabili localmente in `dist/`. Restano da fare al momento del flip: rimuovere/
curare `dev/`, `gh repo edit ... --visibility public`, `twine upload`.

## Workflow di sviluppo

- **Interprete per test reali**: sull'host con PB IDE installato serve un Python che
  matchi l'architettura della DLL. PB IDE 19/22/25 è x86, quindi sull'host di
  sviluppo esiste un `.venv-x86/Scripts/python.exe` dedicato ai `requires_pb`.
- **Test loop**:
  - `pytest tests` per la suite (i `requires_pb` skip senza `PB_ORCA_MCP_HAS_PB=1`).
  - Con l'env var settata, run completi sull'host con PB. La fixture
    `tests/fixtures/tiny_app/genapp.pbl` + `genapp.sra` copre l'happy path del
    compile loop.
- **MCP server reload**: il server `pb-orca` viene spawned da Claude Code all'avvio
  (config in `.claude/mcp.json`, NON committed perché contiene il path locale al
  venv x86). Il server **non ricarica i moduli a runtime**, quindi una modifica al
  codice in `src/` richiede **riavvio di Claude Code** per essere testabile via tool
  MCP. I pytest invece vedono le modifiche immediatamente (editable install).
- **Restart strategy — resume prima, handoff come fallback**: il restart MCP fa
  perdere il contesto conversazionale se la nuova sessione parte fresca. Soluzione
  **preferita**: lanciare `claude --resume` (o `claude -c` per continue last) dopo il
  restart → il transcript JSONL viene ricaricato → ragionamento preservato. Quando si
  suggerisce un restart, suggerire anche `--resume`. Soluzione **fallback** (handoff
  memory): vale solo quando il resume non è praticabile — conversazione molto lunga e
  context vicino al limite, sessione "sporca" da scartare, sessioni separate da
  giorni. In quei casi salvare `memory/handoff_<topic>.md` con: (1) modifiche
  uncommitted (file + 1 riga), (2) stato test, (3) passi di validazione con comandi e
  outcome attesi, (4) decisioni aperte, (5) anti-redo notes. Linkare l'handoff in
  `MEMORY.md` con marker **HANDOFF** e cancellarlo a validazione confermata.
- **Pre-commit hygiene** (manuale): ruff + mypy + pytest verdi prima del commit. Per
  i commit destinati al repo pubblico, vale anche la grep della memory
  `public-repo-hygiene` (no riferimenti Restore-internal, no path utente-specifici).
- **Release loop**: feature/fix → pytest verde → smoke test via MCP con Claude Code
  in driver → commit + push → tag annotato `vX.Y.Z` → `git push origin vX.Y.Z` →
  (futuro PyPI) `python -m build` + `twine upload`. Per release "significative"
  includere note di release nel messaggio del tag (vedi `git show v0.1.0` come
  modello).

## Sibling projects — `pb-format`, `pb-ai-code`

**`../pb-format/`** (estratto da qui il 2026-06-29): il formatter di stile
PowerScript (engine token-based + CLI `pb-format`) vive ora in un progetto separato,
**indipendente da ORCA**. Era nato dentro `pb-orca-mcp` ma violava lo scope "puro
ORCA" (conosce la sintassi del linguaggio e scrive file su disco), quindi è stato
spostato. `pb-orca-mcp` **non** lo importa: sono due pacchetti componibili da chi li
usa. La logica per scrivere un `.sr*` ben formato (header `$PBExport*` + encoding/BOM
PB) vive in `pb-format` (`write_source_file` / `pb-format write`); `pb-orca` importa
il source via ORCA con `pb_compile_entry_import`, senza toccare il filesystem.

**`../pb-ai-code/`** (creato 2026-05-14, ancora in design phase): è il **dev kit
agentico per PowerBuilder** che ha `pb-orca-mcp` come dipendenza required e ci
costruisce sopra skill, docs Appeon ingestite, orchestrazione di test, pattern di
debug post-mortem e slash command. La visione 4-pilastri (progettazione + coding +
testing + debugging agentico su PB) vive lì, non qui.

`pb-orca-mcp` resta scope-limited all'API ORCA (engine + primitive); la parte di
workflow + knowledge + orchestrazione sta in `pb-ai-code` (experience). Lavoro attivo
su `pb-ai-code` parte **dopo** il PyPI publish di questo repo.
