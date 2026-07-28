# pb-orca-mcp

[![CI](https://github.com/restoresrl/pb-orca-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/restoresrl/pb-orca-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

**Drive PowerBuilder from an AI assistant.** pb-orca-mcp exposes PowerBuilder's
ORCA API as MCP tools, so an assistant can read your libraries, change objects,
compile them, and build EXE and PBD artifacts — with no IDE window open and no
batch script.

It works with any MCP client (Claude Code, Cursor, Codex CLI, Gemini CLI,
Copilot, …) driving any model, and with any PowerBuilder release that ships
ORCA.

## Why

PowerBuilder is a closed world. Its code lives in a binary `.pbl`, and nothing
outside the IDE can compile or validate it without a human opening a window.
So an assistant can *read* PowerBuilder source, and then it is stuck: it cannot
tell whether what it wrote is even syntactically valid.

ORCA is the API the IDE itself uses — sessions, library directories, source
export and import, compile, rebuild, EXE and PBD creation, inheritance and
reference queries. This project wraps it as MCP tools and closes the loop:

```text
export the object to a file  →  edit it  →  compile it  →  read the errors  →  fix
```

Two things make that practical.

**No PowerScript knowledge is needed on either side.** ORCA writes the source
file and reads it back. The file it produces is byte-identical to what the IDE
writes on Save — export header, encoding, line endings — so neither your
assistant nor this server ever has to construct a byte of PowerBuilder's file
format.

**Your changes stay visible to git.** PowerBuilder projects under source
control keep a text file per object beside the binary library. Every tool that
writes to a `.pbl` also rewrites that text file in the same call, so a change is
never half-applied — the silent failure mode where a commit reviews clean and
the build is stale.

## Quickstart

```pwsh
# 1. Is PowerBuilder reachable?
uvx --from git+https://github.com/restoresrl/pb-orca-mcp --python 3.12-x86 pb-orca-mcp doctor

# 2. Does it work on your project?
uvx --from git+https://github.com/restoresrl/pb-orca-mcp --python 3.12-x86 \
    pb-orca-mcp check C:\path\to\your\workspace.pbw
```

Step 2 opens a real ORCA session against your workspace and reports what it
found, without writing anything. When it prints `Check OK`, the machinery works
on your project — before any of it is wired to an assistant.

Then add this to your MCP client's config (`.claude/mcp.json`,
`.cursor/mcp.json`, …):

```json
{
  "mcpServers": {
    "pb-orca": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/restoresrl/pb-orca-mcp",
        "--python", "3.12-x86",
        "pb-orca-mcp"
      ]
    }
  }
}
```

**The full walkthrough, from install to your first compiled change, is
[`docs/getting-started.md`](docs/getting-started.md).**

## Requirements

Windows, a PowerBuilder **IDE** install (runtime-only packages do not ship
`pborc.dll`), and a Python 3.10+ interpreter matching the PB architecture —
x86 through PB 2025, which is what `--python 3.12-x86` above is for. Tested on
PB 2019 R3, 2022 R3 and 2025.

> **Classic workspace format only.** pb-orca drives the classic architecture
> (binary `.pbl` with `.pbw` / `.pbt`). It does **not** work with the *solution*
> format introduced in PowerBuilder 2025 (`.pbproj` + PBL folders): ORCA does
> not operate on it. PB 2025 still supports classic workspaces, where pb-orca
> works.

## Documentation

Read in this order; each one has a job and does not repeat the others.

| | |
| --- | --- |
| [getting-started.md](docs/getting-started.md) | Install, verify against your own project, connect your assistant, make your first change. **Start here.** |
| [how-it-works.md](docs/how-it-works.md) | How PowerBuilder stores source in two places at once, and the one silent way to get it wrong. Read before your first write on work that matters. |
| [recipes.md](docs/recipes.md) | The exact call sequence for a task: the edit loop, builds, queries, reconciling after a merge. |
| [tools.md](docs/tools.md) | Every MCP tool, with input and output schemas. Checked against the live registry by a test, so it cannot drift. |
| [troubleshooting.md](docs/troubleshooting.md) | Symptom, cause, fix — everything that commonly goes wrong. |
| [integrating.md](docs/integrating.md) | For building your own tooling on top of this server: the contract, the guarantees, and the limits. |

Two optional agent skills live in [`skills/`](skills/), written to the
[Agent Skills](https://agentskills.io) `SKILL.md` standard so any skill-aware
assistant can load them. They are not required — the docs cover the same ground.

## What it exposes

Every function in ORCA's public API maps to one MCP tool: discovery, session
lifecycle, source files, library operations, the compile loop, builds, object
queries, and the offline SCC "Refresh PBL" flow. Plus two CLI commands,
`doctor` and `check`, that need no MCP client at all.

pb-orca is an inspect / edit / compile / build bridge. It is **not** a release
build runner (keep your batch scripts), it does not parse or reformat
PowerScript, and it does not run git.

## Status

Alpha, in active development. The full ORCA public API is wired through. The
ABI is verified against PB 2022 R3 and covers every release since PB 2019;
PB 2019 R3 and 2025 are exercised too. The test suite includes round trips
against real PB 22.0 workspaces in both project shapes, pinning the
byte-identity and sync guarantees; PB-dependent tests skip cleanly where no
PowerBuilder is installed.

MIT-licensed, for PowerBuilder developers on Windows. The repository is
**private during internal dogfooding** and will be made public once real use
confirms stability. No fixed date.

## Related projects

Both optional; neither is needed to use this server.

- [`pb-format`](https://github.com/restoresrl/pb-format) — a standalone
  PowerScript formatter (CLI and library), ORCA-independent. Pair it with
  pb-orca if you want sources normalized to a house style before importing.
- [`pb-ai-code`](https://github.com/restoresrl/pb-ai-code) — an agentic dev kit
  for PowerBuilder built on this server: skills, ingested Appeon docs, test
  orchestration, debugging patterns. In design. The contract it relies on is
  written down in [integrating.md](docs/integrating.md).

## Contributing

Bug reports, fixes and PowerBuilder-version reports are all welcome, and
contributing needs no AI: the dev loop is `pytest` + `ruff` + `mypy`. See
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [`LICENSE`](LICENSE).

## Author

Carlo Torrese, Restore srl, `carlo.torrese@re-store.it`
