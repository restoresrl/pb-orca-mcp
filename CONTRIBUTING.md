# Contributing to pb-orca-mcp

Thanks for your interest. This project bridges Claude Code (and other MCP
clients) to PowerBuilder through the ORCA API. Because ORCA is a Win32
DLL shipped only with the PB IDE, some of the development loop is
inherently Windows- and PB-specific — but most of the code (parsing,
discovery, the formatter, the MCP plumbing) is plain Python you can work
on anywhere.

## Ground rules

- **Issues before large PRs.** Open an issue describing the change first
  for anything beyond a small fix, so we can agree on scope.
- **Scope discipline.** This package wraps the ORCA API and nothing more.
  Higher-level agentic workflows, skills and knowledge live in the
  sibling `pb-ai-code` project. New features here should map to an ORCA
  primitive or directly support the compile/build loop.
- **No vendor- or workspace-specific assumptions.** No hardcoded user
  paths, no convention baked in from a single shop. The server must run
  on any Windows machine with a PB IDE installed.

## Development setup

```pwsh
# 1. Clone and create a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Editable install with dev extras
pip install -e ".[dev]"

# 3. Run the checks
pytest                      # unit + integration (PB-dependent tests auto-skip)
ruff check src tests
ruff format --check src tests
mypy src
```

### Architecture and Python interpreter

`pborc.dll` is loaded with `ctypes`, so **the Python interpreter must
match the DLL's architecture**. The PB IDE is x86 across releases through
2025, so running the PB-dependent tests usually needs an **x86 Python**.
The pure-Python tests (parsing, discovery logic, the formatter, the
`pb-format` CLI) run on any interpreter.

### PB-dependent tests

Tests that touch a real `pborc.dll` are marked `@pytest.mark.requires_pb`
and **skip by default**. To run them you need a PB IDE install and an
arch-matched interpreter:

```pwsh
$env:PB_ORCA_MCP_HAS_PB = "1"
pytest -m requires_pb
```

CI does not run these — GitHub runners have no PowerBuilder. Keep the
non-PB suite green and self-contained; mock ORCA only for unit tests of
parsing/discovery, never for the compile loop (see `tests/test_session_real.py`).

## Code style

- Python 3.10+, type hints everywhere, `from __future__ import annotations`.
- `ruff` for lint and formatting (line length 100), `mypy --strict` for types.
- Strings in errors and logs are **English** (the audience is international).
- Run `ruff format src tests` before committing; CI enforces `--check`.

## Commits and pull requests

- Commit messages follow a lightweight Conventional Commits style:
  `feat(...)`, `fix(...)`, `docs(...)`, `test(...)`, `refactor(...)`,
  `chore(...)`. Keep the subject imperative and under ~72 chars.
- One logical change per PR. Update `CHANGELOG.md` under `[Unreleased]`.
- Make sure `pytest`, `ruff check`, `ruff format --check` and `mypy src`
  all pass locally before opening the PR.
- New behaviour needs tests. New tools or flags need a `docs/` update.

## Reporting bugs

Open an issue with: PB version (`pb-orca-mcp doctor` output helps),
Python version and architecture, the MCP client, and a minimal
reproduction. For compile/import issues, include the exact ORCA error
code and message if you have it.
