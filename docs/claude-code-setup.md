# Claude Code setup

> **Status**: phase 1 scaffolding — final form lands with phase 7.

## Register the server

Add this to either:

- **Project-level**: `.claude/mcp.json` in your PowerBuilder workspace
- **User-level**: `~/.claude/mcp.json`

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

`PB_INSTALL_PATH` is optional — the server auto-discovers PB installations
via registry and filesystem scan. Set it explicitly when you have multiple
PB versions installed and want to pin one.

## Verify

In Claude Code, run `/mcp` and look for `pb-orca` in the list of connected
servers. Tools should appear with the `pb_*` prefix.

## First prompt to try

> "Find every PowerBuilder install on this machine and tell me which versions you can drive."

Claude should call `pb_discover_pb_install` and report back the IDE
installations it found, with version and arch.
