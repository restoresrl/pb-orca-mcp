# pb-orca-mcp

MCP server that bridges Claude Code (and other MCP clients) to PowerBuilder
via the ORCA API (`pborc.dll`, shipped with every PB IDE install). It works
with **any PB version that exposes ORCA** — actively tested against PB
2019 R3, 2022 R3, and 2025; the ORCA ABI has been stable since PB 2019,
so other releases should work but are untested. It lets an AI coding agent
inspect PBLs, compile entries, rebuild targets, and produce EXE/PBD
artifacts — closing the "edit → compile → read errors → fix" loop that
PowerBuilder's GUI-only IDE otherwise keeps closed.

## Why

PowerBuilder is a closed-world IDE: an agent can read/write the extracted
sources (`ws_objects/src/*.pbl.src/*.sr*`) but cannot compile or validate
them without a human opening the IDE or running a batch tool like PowerGen.
ORCA exposes the same primitives the IDE uses internally — sessions,
library directories, compile/import, application rebuild, EXE/PBD creation,
hierarchy and reference queries — over a flat C API. This project wraps
that API as MCP tools so an agent can drive PowerBuilder directly.

## Quickstart

```pwsh
# 1. Install (when published to PyPI)
uv tool install pb-orca-mcp
# or:
pipx install pb-orca-mcp

# 2. Verify the local PowerBuilder install(s) are detected
pb-orca-mcp doctor

# 3. Wire it into Claude Code
```

In `.claude/mcp.json` (per-project) or `~/.claude/mcp.json` (user-wide):

```json
{
  "mcpServers": {
    "pb-orca": {
      "command": "uvx",
      "args": ["pb-orca-mcp"]
    }
  }
}
```

After restarting Claude Code, `/mcp` should list the `pb_*` tools.
Full setup walkthrough: [`docs/claude-code-setup.md`](docs/claude-code-setup.md).

## Requirements

- **Windows**. ORCA is a Win32 DLL.
- **PowerBuilder IDE edition** (not runtime-only — those lack `pborc.dll`).
  Tested with PB 2019 R3, 2022 R3, 2025; the ABI has been stable since PB
  2019, so other releases should also work but aren't in the CI matrix.
- **Python 3.10+** with the **same architecture** as the PB IDE you want
  to drive. PB IDE is historically x86 across all releases through 2025,
  so an **x86 Python interpreter** is the common case. The server refuses
  to load a mismatched DLL with an explicit error.

`pb-orca-mcp doctor` checks all three and tells you which installs are
usable from the current Python interpreter.

## What it exposes

Every function in ORCA's public API is mapped to one MCP tool. 23 tools
total, grouped:

| Group | Tools |
|---|---|
| Discovery | `pb_discover_pb_install`, `pb_target_info` |
| Session | `pb_session_open`, `pb_session_close`, `pb_set_current_application`, `pb_set_library_list` |
| Library | `pb_library_create`, `pb_library_delete`, `pb_library_directory`, `pb_library_entry_information`, `pb_library_entry_export`, `pb_library_entry_delete`, `pb_library_entry_move`, `pb_library_comment_modify` |
| Compile | `pb_compile_entry_import`, `pb_compile_entry_import_list`, `pb_application_rebuild`, `pb_get_last_compile_errors` |
| Build | `pb_executable_create`, `pb_dynamic_library_create` |
| Query | `pb_object_query_hierarchy`, `pb_object_query_reference`, `pb_object_regenerate` |

Full reference with input/output schema: [`docs/tools.md`](docs/tools.md).
Workflow recipes (compile-test loop, EXE build, hierarchy walk): [`docs/recipes.md`](docs/recipes.md).

## Architecture highlights

- **Multi-version from day 1**: discovery enumerates every PB IDE on the
  machine. Each install ships its own `pborc.dll` under `<install>\IDE\`;
  the loader picks the right one per session. PB 2019 R3 + 2022 R3 + 2025
  coexisting is a supported configuration.
- **IDE / runtime distinction**: discovery filters out runtime-only installs
  (no `pborc.dll`) and surfaces them in a separate list — no crash, no
  confused error.
- **Explicit version selection**: callers pick the install with `pb_version`
  or `install_path` on `pb_session_open`. `.pbt`/`.pbw` files don't embed a
  PB version (they carry the 1999 file-format magic constant, not a release
  marker), so there's no useful auto-pick. See PLAN §"Decisioni di scope".
- **Single ORCA session per process**: enforced by the server. Switching
  installs means close + reopen — ORCA is single-session-per-process and
  not thread-safe.
- **Callback lifetime handling**: ORCA fires Python WINFUNCTYPE callbacks
  for diagnostics and listings. We keep them alive in `Session._callback_refs`
  during each call — otherwise GC mid-call crashes the process.

Full design and rationale in [`PLAN.md`](PLAN.md).

## Status

**Phase 7 of 7 — packaging + docs.** All ORCA primitives are wired through
to MCP tools; ABI tested against PB 19 / 22 / 25 headers. Awaiting first
PyPI release.

| Phase | Scope | Status |
|---|---|---|
| 1 | Foundation (scaffolding, CI, smoke tests) | done |
| 2 | Discovery + loader multi-version, `.pbt`/`.pbw` parser | done |
| 3 | Session lifecycle + application configuration | done |
| 4 | Library operations | done |
| 5 | Compile loop (callbacks, error buffer) — the core value | done |
| 6 | Build artifacts (EXE/PBD) + object hierarchy/reference | done |
| 7 | Packaging + docs | done |

## Documentation

- [`docs/installation.md`](docs/installation.md) — PB prerequisites, x86 vs x64 Python, troubleshooting
- [`docs/claude-code-setup.md`](docs/claude-code-setup.md) — `.claude/mcp.json` snippets and validation
- [`docs/tools.md`](docs/tools.md) — every MCP tool, input/output schema, examples
- [`docs/recipes.md`](docs/recipes.md) — end-to-end workflows
- [`PLAN.md`](PLAN.md) — full design document

## License

MIT — see [`LICENSE`](LICENSE).

## Author

Carlo Torrese — Restore srl — `carlo.torrese@re-store.it`
