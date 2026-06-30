# pb-orca-mcp

[![CI](https://github.com/restoresrl/pb-orca-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/restoresrl/pb-orca-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

MCP server that exposes PowerBuilder's ORCA API (`pborc.dll`, shipped with
every PB IDE install) as MCP tools. Any MCP client (Claude Code, Cursor,
Codex, Gemini CLI, Copilot, …) driving any model can use it to bridge to
PowerBuilder. It works with **any PB version that exposes ORCA**, and lets the
agent inspect PBLs, compile entries, rebuild targets, and produce EXE/PBD
artifacts. That closes the "edit → compile → read errors → fix" loop that
PowerBuilder's GUI-only IDE otherwise keeps shut.

## Why

PowerBuilder is a closed-world IDE: an agent can read and write the
`.sr*` source files PB exports, but it cannot compile, validate, or build
them without a human opening the IDE or running a batch tool like
PowerGen. ORCA exposes the same primitives the IDE uses internally
(sessions, library directories, compile/import, application rebuild,
EXE/PBD creation, hierarchy and reference queries) over a flat C API.
This project wraps that API as MCP tools so an agent can drive
PowerBuilder directly.

## How it works: the agentic loop

pb-orca hands the agent the same primitives the IDE uses internally, over
MCP. The agent opens **one session** against a chosen PB install (in
effect, it becomes the IDE without a window) and works through four phases:

1. **Understand.** `pb_library_directory` lists what's in a `.pbl`,
   `pb_library_entry_export` returns an object's source, and
   `pb_object_query_hierarchy` / `pb_object_query_reference` walk
   inheritance and outgoing references. The agent maps a PB codebase it
   has never seen.
2. **Change and validate** is the core loop. The agent imports new source
   with `pb_compile_entry_import`; ORCA compiles it and returns
   **structured errors** (object, line, column, message). The agent reads
   the error, fixes it, and re-imports. This loop was impossible before:
   the source crosses the C ABI and lands in the `.pbl` with no IDE window
   in the way.
3. **Validate broadly.** `pb_application_rebuild` recompiles the whole
   target (full or incremental) to surface cascading breakage.
4. **Build and sync.** `pb_executable_create` /
   `pb_dynamic_library_create` produce EXE/PBD; on git-managed projects
   `pb_scc_refresh_target` propagates `ws_objects/` into the `.pbl`.

A concrete session, *"add a method to `n_cst_order` and confirm it
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
ORCA, not a release build runner (PowerGen and batch scripts stay), and
it does not enforce source style or higher-level agentic orchestration.
Those are the job of separate, optional tools (not included); pb-orca just
reads and writes PowerBuilder libraries.

## Quickstart

`uv` installs the server straight from the GitHub repo, with no clone
needed. (`uv` is the [Astral installer](https://docs.astral.sh/uv/).)

```pwsh
# Verify the local PowerBuilder install(s) are detected
uvx --from git+https://github.com/restoresrl/pb-orca-mcp pb-orca-mcp doctor

#   Pin a release:  ...pb-orca-mcp@v0.1.0   (append @<tag> to the URL)
#   x86 PB IDE (the common case): add  --python 3.12-x86
# doctor should end with "Doctor OK: N usable install(s)".
```

Register the server with your MCP client. The block below is the standard
MCP `mcpServers` shape, identical across clients; only the file it goes in
differs (Claude Code: `.claude/mcp.json`; Cursor: `.cursor/mcp.json`; etc.,
see [`docs/setup.md`](docs/setup.md)):

```json
{
  "mcpServers": {
    "pb-orca": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/restoresrl/pb-orca-mcp", "pb-orca-mcp"]
    }
  }
}
```

`uvx --from git+<url>` builds and runs the server straight from the repo,
no clone needed. (Working *on* pb-orca itself? Clone it and point `--from`
at the local path instead; see [`docs/setup.md`](docs/setup.md).) Reload
your MCP client (in Claude Code, run `/mcp`); the `pb_*` tools should
appear. The full setup walkthrough covers registration per client, x86
pinning, multi-version, and troubleshooting: [`docs/setup.md`](docs/setup.md).

## Requirements

Windows, a PowerBuilder **IDE** install (runtime-only installs lack
`pborc.dll`), and a Python 3.10+ interpreter whose architecture matches the
PB IDE (historically x86). `pb-orca-mcp doctor` checks all three and reports
which installs are usable. Full prerequisites and the x86/x64 gotcha:
[`docs/setup.md`](docs/setup.md).

> **Classic workspace format only.** pb-orca drives the classic workspace
> architecture (binary `.pbl` with `.pbw` / `.pbt`). It does **not** work with
> the *solution* format introduced in PowerBuilder 2025 (`.pbproj` + PBL
> folders): Appeon's ORCA API doesn't operate on it. PB 2025 and later still
> support the classic workspace format, where pb-orca works; a project migrated
> to a solution is out of scope.

## What it exposes

Every function in ORCA's public API maps to one MCP tool, grouped into
discovery, session, library, compile, build, object-query, and SCC
operations. The [tool reference](docs/tools.md) lists each one with its
input/output schema and examples.

Recipes and the `.pbl` ↔ `ws_objects/` editing model: [`docs/usage.md`](docs/usage.md).

## Architecture highlights

- **Multi-version**: discovery enumerates every PB IDE on the
  machine. Each install ships its own `pborc.dll` under `<install>\IDE\`;
  the loader picks the right one per session. PB 2019 R3 and later versions
  coexisting is a supported configuration.
- **IDE / runtime distinction**: discovery filters out runtime-only installs
  (no `pborc.dll`) and surfaces them in a separate list, so there is no crash
  and no confusing error.
- **Explicit version selection**: callers pick the install with `pb_version`
  or `install_path` on `pb_session_open`. `.pbt`/`.pbw` files don't embed a
  PB version (they carry the 1999 file-format magic constant, not a release
  marker), so there's no useful auto-pick.
- **Single ORCA session per process**: enforced by the server. Switching
  installs means close + reopen, because ORCA is single-session-per-process
  and not thread-safe.

## Status

Alpha, in active development on `main`. `v0.1.0` is **tagged** (GitHub
release, 2026-05-13); install it from the repo with `uv` (see
[Quickstart](#quickstart)).

All of ORCA's public API is wired through to MCP tools. The ABI
is verified against PB 2022 R3, and the same prototypes cover every release
since PB 2019 (the ABI is stable); PB 2019 R3 and 2025 are exercised too.
The test suite is green, including an end-to-end compile-test loop driven by
an MCP agent (Claude Code, in our case) against a real PB 22.0 workspace;
the PB-dependent tests skip cleanly when no local PB install is present.

A GitHub-hosted, MIT-licensed project for PowerBuilder developers on Windows
to use and contribute to. The repository is **currently private during
internal dogfooding** and will be made public once real-world use confirms
stability. There is no fixed date.

## Documentation

- [`docs/setup.md`](docs/setup.md): install, register the server with your MCP client (per-client examples), x86 vs x64 Python, troubleshooting
- [`docs/tools.md`](docs/tools.md): every MCP tool, input/output schema, examples
- [`docs/usage.md`](docs/usage.md): recipes (compile loop, build, queries) plus the `.pbl` ↔ `ws_objects/` editing model

Two optional agent skills, `pb-orca` (the engine/loop overview) and
`pb-workflow` (the object-editing discipline), are written to the
[Agent Skills](https://agentskills.io) `SKILL.md` standard, so any
skill-aware agent can use them (Claude Code, Codex CLI, Gemini CLI, Copilot,
Cursor, …). They are not required to use the server; the docs cover the same
ground for clients without skills. Install instructions per agent are in
[`docs/setup.md`](docs/setup.md).

## Related projects

- [`pb-format`](https://github.com/restoresrl/pb-format): a standalone
  PowerScript style formatter (CLI + library), extracted from this repo.
  ORCA-independent; pair it with `pb-orca-mcp` to normalize `.sr*`
  sources before importing them.
- [`pb-ai-code`](https://github.com/restoresrl/pb-ai-code): an agentic dev
  kit for PowerBuilder built on top of `pb-orca-mcp`: skills, ingested
  Appeon docs, test orchestration, debugging patterns, and slash
  commands for full agentic PB development (design, code, test, debug).
  Currently in design phase; planned to build on this server.

## License

MIT. See [`LICENSE`](LICENSE).

## Author

Carlo Torrese, Restore srl, `carlo.torrese@re-store.it`
