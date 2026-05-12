# CLAUDE.md — pb-orca-mcp

Istruzioni locali al progetto. **Lingua di lavoro: italiano.** Se esiste un
`CLAUDE.md` parent (workspace-level), questo lo estende con le specificità
del progetto Python/MCP.

## Stato attuale

**Fase 1 (Foundation) — COMPLETATA** il 2026-05-12. Scaffolding messo in piedi:
struttura `src/pb_orca_mcp/{orca,tools}/*`, `pyproject.toml` (hatchling, deps
mcp/pydantic/click, dev pytest/ruff/mypy), stub CLI `pb-orca-mcp serve|doctor`
(entrambi escono con exit 2 + "not implemented"), 4 smoke test che girano
senza PB, CI Windows matrix, docs scheletro, repo `git init -b main` (untracked).

**Prossima fase: Fase 2 — Discovery & loader multi-version** (vedi [`PLAN.md`](PLAN.md) §Roadmap).
Implementa: `discovery.py` (registry + filesystem, IDE vs runtime), `pb_target_info`
(parser `.pbt`), `orca/dll.py` factory `load_orca(install)`, tool MCP
`pb_discover_pb_install`. Test reali contro PB 2019 R3, 2022 R3, 2025
(installate sulla macchina del maintainer).

**Decisioni residue da risolvere** prima del primo push / PyPI release:
git remote, licenza, disponibilità nome `pb-orca-mcp` su PyPI
(vedi tabella in `PLAN.md` §"Decisioni residue").

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

## Riferimenti

- Plan file (versionato nel repo): [`PLAN.md`](PLAN.md)
- ORCA Programmers Guide R3: https://docs.appeon.com/pb2022r3/orca_guide
