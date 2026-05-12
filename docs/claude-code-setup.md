# Claude Code setup

How to register `pb-orca-mcp` with Claude Code (or any other MCP client),
including the arch-matching caveat that trips up most first-time installs.

## 1. Verify your environment

Before wiring anything into Claude Code, confirm `pb-orca-mcp` can see at
least one PowerBuilder install from your terminal:

```pwsh
pb-orca-mcp doctor
```

A working setup ends with `Doctor OK: N usable install(s) for x86 Python.`
(or `x64`, if your PB install is x64). If `doctor` exits 1 with
`No PB install is usable from this Python (x64)`, see
[`installation.md`](installation.md#x86-vs-x64--the-most-common-gotcha)
for how to install an x86 Python and re-create the tool environment.

## 2. Register the server

Add a `pb-orca` entry to one of:

- **Project-level**: `.claude/mcp.json` at the root of your PowerBuilder workspace
- **User-wide**: `~/.claude/mcp.json`

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

The default install handles the common case of one PB IDE on the machine.

### When you have multiple PB versions installed

The server auto-discovers every install but each session targets exactly
one. Two ways to pin the version:

**A. Per-tool-call** — let the agent pick by passing `pb_version` on
`pb_session_open`:

```json
{"tool": "pb_session_open", "args": {"pb_version": "22.0"}}
```

This is what Claude Code will do naturally when you tell it "use PB 2022 R3".

**B. Per-server** — restrict discovery to one install via the env var:

```json
{
  "mcpServers": {
    "pb-orca": {
      "command": "uvx",
      "args": ["pb-orca-mcp"],
      "env": {
        "PB_INSTALL_PATH": "C:\\Program Files (x86)\\Appeon\\PowerBuilder 22.0"
      }
    }
  }
}
```

`PB_INSTALL_PATH` accepts a single path or a `;`-separated list. The
registry/filesystem fallbacks still run, but explicit paths come first.

### Forcing an x86 Python

If `uvx` defaults to your x64 Python and PB is x86, run the server through
a specific x86 interpreter:

```json
{
  "mcpServers": {
    "pb-orca": {
      "command": "uvx",
      "args": ["--python", "3.12-x86", "pb-orca-mcp"]
    }
  }
}
```

The `3.12-x86` syntax requires `uv` 0.4+; pin to whatever x86 Python you
installed (see [`installation.md`](installation.md)).

## 3. Restart Claude Code, verify in `/mcp`

After saving the config:

1. Quit Claude Code.
2. Relaunch it (`claude` from the terminal).
3. Run `/mcp` in the conversation.

You should see `pb-orca` listed under "Connected servers" with `23 tools`
exposed. If `0 tools` or the server isn't listed, check:

- The `command`/`args` resolve in your shell: `uvx pb-orca-mcp --help`
  should print the click help.
- `pb-orca-mcp doctor` (in your shell) exits 0.
- Claude Code's MCP log: a failed server prints its stderr there.

## 4. First prompt to try

> "Find every PowerBuilder install on this machine and tell me which
> versions you can drive."

Claude calls `pb_discover_pb_install` and reports the IDE installations,
with version and arch. Then try:

> "Open an ORCA session against PB 2022 R3."

Claude calls `pb_session_open` with `pb_version: "22.0"`. The response
includes the exact `pborc.dll` path that was loaded. From there any of
the [recipes](recipes.md) is fair game — the compile-test loop (Recipe 1)
is the canonical first real workflow to try.

## 5. Combine with sources extracted from PB

`pb-orca-mcp` doesn't replace Claude's normal file-edit capabilities. The
common pattern is:

1. PowerBuilder IDE has extracted sources into `ws_objects/src/<pbl>.pbl.src/`
   (the standard PB export layout).
2. Claude edits a `.srf` / `.sru` / `.srw` file using its normal `Edit`/`Write` tools.
3. Claude calls `pb_compile_entry_import` with the edited file's contents
   as `syntax` to import it back into the binary `.pbl`.
4. Loop on `errors` until `success: true`.

The `.pbl` is the source of truth for the PB IDE; `ws_objects/src/*` is
the source of truth for git and for Claude. `pb-orca-mcp` is the bridge.

## Stopping the server

The server has no shutdown command of its own — Claude Code starts and
stops it. To force-stop, kill the `pb-orca-mcp` (or `uvx`) process.
There's no on-disk state to clean up.
