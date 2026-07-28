# Installation & setup

Install `pb-orca-mcp`, register it with your MCP client, and verify it can
see your PowerBuilder install. It is a standard MCP server: any MCP client
(Claude Code, Cursor, Codex CLI, Gemini CLI, Copilot, …) driving any model
can use it.

## Requirements

- **Windows**. ORCA is a Win32 DLL, with no macOS / Linux build.
- **PowerBuilder, IDE edition**. Runtime-only installs don't ship `pborc.dll`.
  Tested with **PB 2019 R3**, **2022 R3**, **2025**; the ABI has been stable
  since PB 2019, so other releases should work too (not in the CI matrix).
- **Python 3.10+**, with the **same architecture** as the PB install (see
  [x86 vs x64](#x86-vs-x64-the-most-common-gotcha)). `uv` provides it for you.

## Install

`uv` ([Astral installer](https://docs.astral.sh/uv/)) runs the server
straight from the GitHub repo.

```pwsh
# Use it without a clone. Pin a release by appending @<tag> to the URL.
uvx --from git+https://github.com/restoresrl/pb-orca-mcp pb-orca-mcp doctor

# Or install it as a persistent tool, so `pb-orca-mcp` is on PATH:
uv tool install git+https://github.com/restoresrl/pb-orca-mcp
```

To **develop on the server itself**, clone it and point `--from` at the
local checkout (always runs your working tree, no reinstall after an edit):

```pwsh
git clone https://github.com/restoresrl/pb-orca-mcp
uvx --from .\pb-orca-mcp pb-orca-mcp doctor
```

## Verify with `doctor`

`pb-orca-mcp doctor` lists every PB IDE install found, with version, arch,
the `pborc.dll` that would load, and whether it's usable from the current
Python:

```text
pb-orca-mcp 0.1.0
Python: 3.12.0 (x86)

[OK] PB 22.0  [x86]  C:\Program Files (x86)\Appeon\PowerBuilder 22.0
    file_version : 22.2.0.3397
    product      : 2022 R3 Build 3397
    source       : registry
    load         : OK (session entry points bound)

Doctor OK: 1 usable install(s) for x86 Python.
```

`[OK]` marks a tested major (`19.0`, `22.0`, `25.0`); `[??]` an untested one,
still attempted (ABI stable since PB 2019).

## x86 vs x64: the most common gotcha

PB IDE is historically **x86** through 2025 (`C:\Program Files (x86)\Appeon\
PowerBuilder N.0\`). `ctypes` can't load an x86 DLL from x64 Python, or vice
versa. If `doctor` reports `No PB install is usable from this Python (x64)`,
pin an x86 Python:

```pwsh
uv python install 3.12 --arch x86
# add --python 3.12-x86 to any install form:
uvx --from git+https://github.com/restoresrl/pb-orca-mcp --python 3.12-x86 pb-orca-mcp doctor
```

## Register the server with your MCP client

Registration uses the standard MCP `mcpServers` block, **the same JSON
everywhere**; only the file it goes in differs per client:

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

| Client | Where the block goes |
| --- | --- |
| Claude Code | `.claude/mcp.json` (project) or `~/.claude/mcp.json` (user) |
| Cursor | `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (user) |
| Codex CLI / Gemini CLI / Copilot / others | the client's MCP config (see its docs for the exact path) |

The block contents are identical; only confirm the file location for your
client. After saving, reload the client and confirm the `pb_*` tools appear
(Claude Code: run `/mcp`; other clients: their MCP/tool inspector or server
log). If the server doesn't show, check that
`uvx --from git+https://github.com/restoresrl/pb-orca-mcp pb-orca-mcp --help`
runs in your shell and `… pb-orca-mcp doctor` exits 0, then read your
client's MCP log for the server's stderr.

### Pinning the PB version (multi-version machines)

The server discovers every install, but each session targets one. Two ways
to pin:

- **Per session**: pass `pb_version` on `pb_session_open`
  (`{"pb_version": "22.0"}`); this is what an agent does when you say "use
  PB 2022 R3".
- **Per server**: restrict discovery via an env var in the config:

```json
{
  "mcpServers": {
    "pb-orca": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/restoresrl/pb-orca-mcp", "pb-orca-mcp"],
      "env": { "PB_INSTALL_PATH": "C:\\Program Files (x86)\\Appeon\\PowerBuilder 22.0" }
    }
  }
}
```

`PB_INSTALL_PATH` accepts a single path or a `;`-separated list. To force an
x86 interpreter from the config, add `"--python", "3.12-x86"` to `args`
before `"pb-orca-mcp"`.

## Agent skills (optional)

Two optional skills give an agent the *know-how* to use the tools well:

- **`pb-orca`**: the session lifecycle, the export → edit → import loop, and
  the ORCA gotchas.
- **`pb-workflow`**: the two project shapes, what the server syncs for you,
  and what to commit.

They live in [`skills/`](../skills/) and are written to the
[Agent Skills](https://agentskills.io) `SKILL.md` standard, so any skill-aware
agent can use them. Install by copying the skill folder into your agent's
skills directory:

| Agent | Skills directory |
| --- | --- |
| Claude Code | `~/.claude/skills/` (user) or `<workspace>/.claude/skills/` (project) |
| Codex CLI | `~/.codex/skills/` |
| Others | the agent's skills location (see its docs) |

```pwsh
# from a clone of this repo, e.g. for Claude Code:
Copy-Item -Recurse skills/pb-orca     ~/.claude/skills/
Copy-Item -Recurse skills/pb-workflow ~/.claude/skills/
```

The skills aren't required: the docs here cover the same ground for clients
without skills. With them, the agent knows the session order and the
source-of-truth model up front, and takes fewer wrong turns.

Claude Code users can alternatively install the whole thing — server plus both
skills — as a plugin; `.claude-plugin/plugin.json` is that packaging. It is one
optional channel, not the canonical home of anything.

## Discovery sources

The server merges three sources (later ones only fill gaps):

1. **`PB_INSTALL_PATH`** env var, the explicit override (single root or
   `;`-separated list).
2. **Windows registry** `HKLM\SOFTWARE\WOW6432Node\Sybase\PowerBuilder\<X.0>`:
   `Location` + `IPS Name` (path), `Build` (version), `BuildFlag`
   (product name). Appeon kept the legacy Sybase key.
3. **Filesystem scan** of `C:\Program Files{,(x86)}\Appeon\PowerBuilder *.0\`,
   with siblings lacking `IDE\pborc.dll` filtered out.

Version metadata comes from the registry when present, else the DLL's PE
`VS_VERSION_INFO` resource.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `doctor`: "No PowerBuilder IDE installation found" | PB Runtime installed, not IDE | Install PB IDE; runtime packages don't ship `pborc.dll`. |
| `doctor`: "No PB install is usable from this Python (x64)" | arch mismatch | Install an x86 Python (above). |
| `doctor` lists install but `load failed: …` | DLL blocked (AV / Defender / SmartScreen) | Whitelist `<install>\IDE\pborc.dll` or reinstall the same PB version. |
| `pb_library_*` → `PBORCA_LIBIOERROR` | PB IDE has the PBL open | Close the IDE or work on a copy. ORCA respects PB IDE file locks. |
| `pb_set_current_application` → `PBORCA_LIBLISTNOTSET` | called before `pb_set_library_list` | Set the library list first. |
| `pb_compile_*` → `PB_ORCA_MCP_STATEERROR` | no session open | Call `pb_session_open` first. |
| Untested major loads but a tool returns `PBORCA_UNKNOWN(...)` | ABI drift from a pre-2019 release | Use PB 2019 R3 or later. |
| `doctor` shows an install but `IPS Name` is missing | very old (pre-Appeon) layout | Set `PB_INSTALL_PATH` explicitly. |
| `pb_library_entry_export` → "the session configuration would corrupt the transfer" | `pb_session_configure` left a non-Unicode encoding in effect | Call `pb_session_configure` with no arguments to reset, then retry. |
| `pb_object_export_file` lands in `.pb-orca/` on a project that has `ws_objects/` | the projection directory for *that* library was not found | Check `pb_workspace_info`: `sources.source_dir` is where it looked. |
| Every line of a `.sr*` shows as changed after an import | the source was imported with LF endings | Re-export the object and re-import the file without letting an editor normalize line endings. |

## Uninstall

```pwsh
# Only if you used `uv tool install`:
uv tool uninstall pb-orca-mcp        # or: pipx uninstall pb-orca-mcp
```

`uvx --from` installs nothing persistent, so there is nothing to uninstall (optionally
`uv cache clean`). The MCP client launches the server on connect and stops
it on disconnect; to force-stop, kill the `pb-orca-mcp` (or `uvx`) process.
The package owns no on-disk state.
