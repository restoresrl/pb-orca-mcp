# pb-orca-mcp

[![CI](https://github.com/restoresrl/pb-orca-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/restoresrl/pb-orca-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

MCP server that bridges Claude Code (and other MCP clients) to PowerBuilder
via the ORCA API (`pborc.dll`, shipped with every PB IDE install). It works
with **any PB version that exposes ORCA**. It lets an AI coding agent
inspect PBLs, compile entries, rebuild targets, and produce EXE/PBD
artifacts — closing the "edit → compile → read errors → fix" loop that
PowerBuilder's GUI-only IDE otherwise keeps closed.

## Why

PowerBuilder is a closed-world IDE: an agent can read and write the
`.sr*` source files PB exports, but it cannot compile, validate or build
them without a human opening the IDE or running a batch tool like
PowerGen. ORCA exposes the same primitives the IDE uses internally —
sessions, library directories, compile/import, application rebuild,
EXE/PBD creation, hierarchy and reference queries — over a flat C API.
This project wraps that API as MCP tools so an agent can drive
PowerBuilder directly.

## How it works — the agentic loop

PowerBuilder is a closed-world IDE: an agent can read and write the
`.sr*` text PB exports, but it can't compile, validate, inspect libraries
or build artifacts without a human opening the IDE. That breaks the
edit → compile → read errors → fix loop at the heart of agentic coding.

pb-orca hands the agent the same primitives the IDE uses internally, over
MCP. The agent opens **one session** against a chosen PB install — in
effect, it *becomes the IDE, headless* — and works through four phases:

1. **Understand** — `pb_library_directory` lists what's in a `.pbl`,
   `pb_library_entry_export` returns an object's source, and
   `pb_object_query_hierarchy` / `pb_object_query_reference` walk
   inheritance and outgoing references. The agent maps a PB codebase it
   has never seen.
2. **Change and validate** — the core loop. The agent imports new source
   with `pb_compile_entry_import`; ORCA compiles it and returns
   **structured errors** (object, line, column, message). The agent reads
   the error, fixes it, and re-imports. This is the loop that was
   impossible before — the source crosses the C ABI and lands in the
   `.pbl` with no IDE window in the way.
3. **Validate broadly** — `pb_application_rebuild` recompiles the whole
   target (full / incremental) to surface cascading breakage.
4. **Build and sync** — `pb_executable_create` /
   `pb_dynamic_library_create` produce EXE/PBD; on git-managed projects
   `pb_scc_refresh_target` propagates `ws_objects/` into the `.pbl`.

**A concrete session** — *"add a method to `n_cst_order` and confirm it
compiles"*:

```text
pb_session_open(22.0)
  → pb_set_library_list + pb_set_current_application
  → pb_library_entry_export(n_cst_order)      # read the current source
  → (agent edits the source)
  → pb_compile_entry_import(...)              # import + compile
  → on errors: read line/column/message, fix, re-import
  → pb_application_rebuild(incremental)       # nothing else broke
```

No IDE window is ever opened.

**Boundaries.** pb-orca is an inspect / compile / build bridge through
ORCA — not a release build runner (PowerGen and batch scripts stay), and
it does not enforce source style (that's
[`pb-format`](https://github.com/restoresrl/pb-format)). It reads and
writes PowerBuilder libraries; higher-level orchestration, skills and
knowledge live in [`pb-ai-code`](https://github.com/restoresrl/pb-ai-code).

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
- **PowerBuilder Development Environment** (not runtime-only — those lack `pborc.dll`).
- **Python 3.10+** with the **same architecture** as the PB IDE you want
  to drive. PB IDE is historically x86 across all releases through 2025,
  so an **x86 Python interpreter** is the common case. The server refuses
  to load a mismatched DLL with an explicit error.

`pb-orca-mcp doctor` checks all three and tells you which installs are
usable from the current Python interpreter.

## What it exposes

Every function in ORCA's public API is mapped to one MCP tool. 29 tools
total, grouped:

| Group | Tools |
|---|---|
| Discovery | `pb_discover_pb_install`, `pb_target_info` |
| Session | `pb_session_open`, `pb_session_close`, `pb_set_current_application`, `pb_set_library_list` |
| Library | `pb_library_create`, `pb_library_delete`, `pb_library_directory`, `pb_library_entry_information`, `pb_library_entry_export`, `pb_library_entry_delete`, `pb_library_entry_move`, `pb_library_comment_modify` |
| Compile | `pb_compile_entry_import`, `pb_compile_entry_import_list`, `pb_application_rebuild`, `pb_get_last_compile_errors` |
| Build | `pb_executable_create`, `pb_dynamic_library_create` |
| Query | `pb_object_query_hierarchy`, `pb_object_query_reference`, `pb_object_regenerate` |
| SCC | `pb_scc_connect_offline`, `pb_scc_set_target`, `pb_scc_refresh_target`, `pb_scc_exclude_library_list`, `pb_scc_get_connect_properties`, `pb_scc_close` |

Full reference with input/output schema: [`docs/tools.md`](docs/tools.md).
Recipes and the `.pbl` ↔ `ws_objects/` editing model: [`docs/usage.md`](docs/usage.md).

## Architecture highlights

- **Multi-version from day 1**: discovery enumerates every PB IDE on the
  machine. Each install ships its own `pborc.dll` under `<install>\IDE\`;
  the loader picks the right one per session. PB 2019 R3 and later versions
  coexisting is a supported configuration.
- **IDE / runtime distinction**: discovery filters out runtime-only installs
  (no `pborc.dll`) and surfaces them in a separate list — no crash, no
  confused error.
- **Explicit version selection**: callers pick the install with `pb_version`
  or `install_path` on `pb_session_open`. `.pbt`/`.pbw` files don't embed a
  PB version (they carry the 1999 file-format magic constant, not a release
  marker), so there's no useful auto-pick.
- **Single ORCA session per process**: enforced by the server. Switching
  installs means close + reopen — ORCA is single-session-per-process and
  not thread-safe.
- **Callback lifetime handling**: ORCA fires Python WINFUNCTYPE callbacks
  for diagnostics and listings. We keep them alive in `Session._callback_refs`
  during each call — otherwise GC mid-call crashes the process.

## Status

**v0.1.0 released** (2026-05-13); active development on `main` since.
All ORCA primitives are wired through to MCP tools (29 total); ABI tested
against PB 2022 R3 — the same set of prototypes covers any release since
PB 2019 (ABI stable). 126 pytest tests green, plus 8 PB-dependent tests
that skip without a local PB install, including the end-to-end
compile-test loop validated with Claude Code driving the MCP server
against a real PB 22.0 workspace. Since the tag, the codebase was
refactored to keep this server purely ORCA: both the PowerScript style
formatter and the well-formed `.sr*` writer moved to the standalone
[`pb-format`](https://github.com/restoresrl/pb-format) package.

Currently in internal dogfooding. The package is being readied for a
first PyPI publish (name reserved, MIT-licensed, CI green), but the
public release is deliberately deferred until real-world use confirms
stability — no fixed date.

## Documentation

- [`docs/installation.md`](docs/installation.md) — PB prerequisites, x86 vs x64 Python, troubleshooting
- [`docs/claude-code-setup.md`](docs/claude-code-setup.md) — register the MCP server, install the agent skills, validate the setup
- [`docs/tools.md`](docs/tools.md) — every MCP tool, input/output schema, examples
- [`docs/usage.md`](docs/usage.md) — recipes (compile loop, build, queries) + the `.pbl` ↔ `ws_objects/` editing model

The two agent skills — `pb-orca` (the engine/loop overview) and
`pb-workflow` (the object-editing discipline) — live under
[`.claude/skills/`](.claude/skills/). The setup guide explains how to
install them into Claude Code so the agent loads them automatically.

## Related projects

- [`pb-format`](https://github.com/restoresrl/pb-format) — standalone
  PowerScript style formatter (CLI + library), extracted from this repo.
  ORCA-independent; pair it with `pb-orca-mcp` to normalize `.sr*`
  sources before importing them.
- [`pb-ai-code`](https://github.com/restoresrl/pb-ai-code) — agentic dev
  kit for PowerBuilder built on top of `pb-orca-mcp`: skills, ingested
  Appeon docs, test orchestration, debugging patterns and slash
  commands for full agentic PB development (design, code, test, debug).
  Currently in design phase; planned to build on this server.

## License

MIT — see [`LICENSE`](LICENSE).

## Author

Carlo Torrese — Restore srl — `carlo.torrese@re-store.it`
