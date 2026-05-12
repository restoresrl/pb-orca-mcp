# tiny_app fixture

Minimal PowerBuilder workspace used by phase 2+ tests:

- `tiny_app.pbt` — target (PowerBuilder 2022 R3)
- `tiny_app.pbl` — application library (contains `tiny_app` Application object + one window + one function)
- `helper.pbl` — secondary library with one non-visual user object

## Status

**Not committed yet.** This fixture must be authored inside PowerBuilder IDE
(the binary `.pbl` format is not human-writable). Phase 2 of the roadmap
includes a "record the steps to recreate this fixture" subtask so that the
fixture is reproducible.

Until then, tests that depend on this fixture are gated by the `requires_pb`
pytest marker (see `tests/conftest.py`) and skipped unless
`PB_ORCA_MCP_HAS_PB=1` is set in the environment.

## How to recreate

1. Open PB 2022 R3 IDE.
2. New Workspace → `tiny_app.pbw` in this directory.
3. New Target → Application → `tiny_app`.
4. Add a Window object `w_main`, a global Function `f_double(long) returns long`.
5. New PBL `helper.pbl`, add it to the target's LibList.
6. In `helper.pbl`, add a NonVisualObject `n_helper` that inherits from `nonvisualobject`.
7. Save, close PB.
8. Commit the resulting `.pbw` / `.pbt` / `*.pbl` files into this directory.
