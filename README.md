# pb-orca-mcp

MCP server that bridges Claude Code (and other MCP clients) to PowerBuilder
via the ORCA API (`pborc.dll`, shipped with every PB IDE install). It works
with **any PB version that exposes ORCA** — actively tested against PB
2019 R3, 2022 R3, and 2025; the ORCA ABI has been stable since PB 2019,
so other releases should work but are untested. It lets an AI coding agent
inspect PBLs, compile entries, rebuild targets, and produce EXE/PBD
artifacts — closing the "edit → compile → read errors → fix" loop that
PowerBuilder's GUI-only IDE otherwise keeps closed.

> **Status: phase 1 of 7 — scaffolding only.**
> The CLI commands exit with a "not implemented" message. The MCP tools are
> not wired up yet. See [`PLAN.md`](PLAN.md) for the full design and roadmap.

## Why

PowerBuilder is a closed-world IDE: an agent can read/write the extracted
sources (`ws_objects/src/*.pbl.src/*.sr*`) but cannot compile or validate
them without a human opening the IDE or running a batch tool like PowerGen.
ORCA exposes the same primitives the IDE uses internally — sessions,
library directories, compile/import, application rebuild, EXE/PBD creation,
hierarchy and reference queries — over a flat C API. This project wraps
that API as MCP tools so Claude Code can drive PowerBuilder directly.

## Requirements

- Windows
- PowerBuilder, **IDE edition** (runtime-only installs lack `pborc.dll`).
  Tested with PB 2019 R3, 2022 R3, 2025; older releases that ship `pborc.dll`
  should also work but aren't covered by CI.
- Python 3.10+, matching the architecture of the PB install you want to drive

## Install (planned)

```pwsh
uv tool install pb-orca-mcp
# or
pipx install pb-orca-mcp
```

Then in `.claude/mcp.json`:

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

See [`docs/claude-code-setup.md`](docs/claude-code-setup.md) for full setup.

## Architecture

- **Multi-version from day 1**: discovery enumerates every PB IDE installed
  on the machine (each ships its own `pborc.dll` under `<install>\IDE\`);
  the loader picks the right one per target. Coexisting installs (e.g. PB
  2019 R3 + 2022 R3 + 2025) are first-class.
- **IDE / runtime distinction**: discovery filters out runtime-only installs
  (no `pborc.dll`) and reports them separately instead of crashing.
- **`.pbt`-driven version inference**: `pb_target_info` extracts the PB version
  required by a target so other tools auto-pick the right install.
- **Single ORCA session per process**: enforced by the server; one
  `(version, arch)` at a time.

Full design in [`PLAN.md`](PLAN.md).

## Roadmap

| Phase | Scope |
|---|---|
| 1 | Foundation (this scaffolding) |
| 2 | Discovery & loader multi-version, `pb_target_info` |
| 3 | Session & application setup |
| 4 | Library operations |
| 5 | Compile loop (callbacks, error buffer) — the core value |
| 6 | Build artifacts & object query |
| 7 | Packaging + docs |

## License

TBD. License selection is a deliberate decision deferred to the v0.1 release.

## Author

Carlo Torrese — `carlo.torrese@re-store.it`
