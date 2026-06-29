# dev/ — documentazione interna di sviluppo

**Cartella interna. NON destinata all'utente finale e NON inclusa nel package
PyPI** (esclusa in `pyproject.toml` → `[tool.hatch.build.targets.sdist] exclude`).
Al flip a repo pubblico questa cartella va rimossa o curata (eventualmente
estraendone un `ARCHITECTURE.md` pubblico, in inglese e ripulito).

Contenuto:

- [`DEVELOPMENT.md`](DEVELOPMENT.md) — processo di sviluppo interno: interprete
  per i test `requires_pb`, reload/restart del server MCP, strategia restart,
  pre-commit hygiene, release loop, coordinamento coi progetti sibling, stato
  dogfooding/publish.
- [`PLAN.md`](PLAN.md) — design document storico (fasi 1-7 chiuse) + decisioni
  residue per il publish PyPI.
- [`pbl-file-format.txt`](pbl-file-format.txt) — reverse-engineering del formato
  binario PBL/PBD (reference per chi estende il discovery; non usato a runtime).

I doc per l'utente finale stanno in `README.md` (root) e in `docs/`.
