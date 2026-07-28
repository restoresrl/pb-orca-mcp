# pb-orca-mcp

[![CI](https://github.com/restoresrl/pb-orca-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/restoresrl/pb-orca-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

MCP server that exposes PowerBuilder's ORCA API (`pborc.dll`, shipped with
every PB IDE install) as MCP tools. Any MCP client (Claude Code, Cursor,
Codex, Gemini CLI, Copilot, …) driving any model can use it to bridge to
PowerBuilder. It works with **any PB version that exposes ORCA**, and lets the
agent inspect PBLs, edit objects through plain source files, compile, rebuild
targets, and produce EXE/PBD artifacts. That closes the "edit → compile → read
errors → fix" loop that PowerBuilder's GUI-only IDE otherwise keeps shut.

## Why

PowerBuilder is a closed-world IDE. Its code lives in a binary `.pbl`, and
nothing outside the IDE can compile, validate or build it without a human
opening a window or running a batch script. ORCA exposes the same primitives
the IDE uses internally — sessions, library directories, source export and
import, application rebuild, EXE/PBD creation, hierarchy and reference queries
— over a flat C API. This project wraps that API as MCP tools so an agent can
drive PowerBuilder directly.

## How it works: the agentic loop

The agent opens **one session** against a chosen PB install and, in effect,
becomes the IDE without a window.

The edit loop is three calls, and **no PowerScript knowledge is needed on
either side of it**. ORCA writes the object out as a source file, the agent
edits that file with ordinary file tools, ORCA compiles it back:

```text
pb_session_open(22.0)
  → pb_set_library_list + pb_set_current_application
  → pb_object_export_file(n_cst_order)     # ORCA writes n_cst_order.sru
  → (the agent edits that file)
  → pb_object_import_file(...)             # compile + import
  → on errors: read line/column/message, fix the file, import again
  → pb_application_rebuild(incremental)    # confirm nothing else broke
```

The file ORCA produces is byte-identical to what the PB IDE writes on Save —
export header, comment line, BOM, CRLF — so pb-orca never has to construct a
byte of PowerBuilder's file format, and re-exporting an unchanged object leaves
`git status` clean.

**Two shapes of project, one loop.** Where that file lands is detected, not
configured. On a project under source control, PowerBuilder keeps a text
projection of every object under `ws_objects/`; there, the file *is* the source
of truth and pb-orca edits it in place. On a binary-only project, the file is a
working copy under `.pb-orca/` and the `.pbl` is the whole truth. The ORCA
calls are identical either way.

**Git always sees the change.** On a project with a text projection, every tool
that writes to the `.pbl` also rewrites the matching `.sr*` file in the same
call, and says which files it touched. Half-applied changes — a binary that
moved while the reviewable text did not, or the reverse — are the one silent
failure mode in this domain, and closing it is a property of the server rather
than a rule you have to remember. [`docs/how-it-works.md`](docs/how-it-works.md)
is the full account.

**Boundaries.** pb-orca is an inspect / edit / compile / build bridge through
ORCA. It is not a release build runner (batch build scripts keep their job), it
does not parse or reformat PowerScript, and it does not run git or orchestrate
anything. Those belong to separate, optional tools; pb-orca reads and writes
PowerBuilder libraries.

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
discovery, session, source files, library, compile, build, object-query and SCC
operations. The [tool reference](docs/tools.md) lists each one with its
input/output schema and examples, and is checked against the live registry by a
test so it cannot drift.

Recipes: [`docs/usage.md`](docs/usage.md). The model underneath:
[`docs/how-it-works.md`](docs/how-it-works.md).

## Architecture highlights

- **ORCA writes the source files, not us.** `PBORCA_ConfigureSession` puts the
  export in write-to-file mode, so the `.sr*` bytes come from the same engine
  the IDE uses. No PowerScript, no file-format handling, and no encoding
  guesswork lives in this codebase.
- **Workspace detection, not configuration**: the projection directory, the
  export encoding (`DefaultExportEncode`, with the existing files as a
  fallback), and whether git is watching are all read off the project.
  `pb_workspace_info` reports it in one call, with no ORCA session required.
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

Alpha, in active development on `main`.

All of ORCA's public API is wired through to MCP tools. The ABI is verified
against PB 2022 R3, and the same prototypes cover every release since PB 2019
(the ABI is stable); PB 2019 R3 and 2025 are exercised too. The test suite is
green, including a round-trip suite against real PB 22.0 workspaces in both
shapes — one with a `ws_objects/` text projection, one binary-only — that pins
the byte-identity and sync guarantees. PB-dependent tests skip cleanly when no
local PB install is present.

A GitHub-hosted, MIT-licensed project for PowerBuilder developers on Windows
to use and contribute to. The repository is **currently private during
internal dogfooding** and will be made public once real-world use confirms
stability. There is no fixed date.

## Documentation

- [`docs/setup.md`](docs/setup.md): install, register the server with your MCP client (per-client examples), x86 vs x64 Python, troubleshooting
- [`docs/how-it-works.md`](docs/how-it-works.md): the `.pbl` / `ws_objects` model, verified ORCA behaviour, and the failure mode to avoid — start here
- [`docs/usage.md`](docs/usage.md): recipes (edit loop, build, queries, reconciling after a merge)
- [`docs/tools.md`](docs/tools.md): every MCP tool, input/output schema, examples
- [`docs/integrating.md`](docs/integrating.md): the contract for tools built on top of this server

Two optional agent skills, `pb-orca` (the engine and the loop) and
`pb-workflow` (what to commit), live in [`skills/`](skills/) and are written to
the [Agent Skills](https://agentskills.io) `SKILL.md` standard, so any
skill-aware agent can use them (Claude Code, Codex CLI, Gemini CLI, Copilot,
Cursor, …). They are not required; the docs cover the same ground for clients
without skills. Install instructions per agent are in
[`docs/setup.md`](docs/setup.md).

## Related projects

Both are optional and neither is needed to use this server.

- [`pb-format`](https://github.com/restoresrl/pb-format): a standalone
  PowerScript style formatter (CLI + library), extracted from this repo.
  ORCA-independent; pair it with `pb-orca-mcp` if you want `.sr*` sources
  normalized to a house style before importing them.
- [`pb-ai-code`](https://github.com/restoresrl/pb-ai-code): an agentic dev
  kit for PowerBuilder built on top of `pb-orca-mcp`: skills, ingested
  Appeon docs, test orchestration, debugging patterns, and slash
  commands for full agentic PB development (design, code, test, debug).
  Currently in design phase. If you are building something similar, the
  contract it relies on is written down in
  [`docs/integrating.md`](docs/integrating.md).

## License

MIT. See [`LICENSE`](LICENSE).

## Author

Carlo Torrese, Restore srl, `carlo.torrese@re-store.it`
