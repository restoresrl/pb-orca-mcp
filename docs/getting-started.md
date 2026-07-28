# Getting started

From nothing to a PowerBuilder object you changed, compiled, and saw compile —
without opening the IDE. About fifteen minutes, most of it install.

You do not need to know anything about MCP or about AI agents to follow the
first half. Steps 1 to 3 use a plain command line and prove the machinery works
on **your** project before any of it is wired to an assistant.

- [1. Check the prerequisites](#1-check-the-prerequisites)
- [2. Install and verify PowerBuilder is reachable](#2-install-and-verify-powerbuilder-is-reachable)
- [3. Point it at your own project](#3-point-it-at-your-own-project)
- [4. Connect it to your MCP client](#4-connect-it-to-your-mcp-client)
- [5. Your first change](#5-your-first-change)
- [Where to go next](#where-to-go-next)

---

## 1. Check the prerequisites

**Windows.** ORCA is a Win32 DLL. There is no macOS or Linux build, and there
cannot be one.

**PowerBuilder, IDE edition.** The bridge is `pborc.dll`, which ships under
`<install>\IDE\` with every PB IDE. Runtime-only packages do not include it.
Tested on PB 2019 R3, 2022 R3 and 2025; the ORCA ABI has been stable since
PB 2019, so other releases should work.

**A Python interpreter, same architecture as PowerBuilder.** `ctypes` cannot
load an x86 DLL from an x64 process. PB IDE is x86 through 2025, so in practice
you want an x86 Python. Step 2 sets that up for you and step 2's output tells
you if you got it wrong.

**`uv`.** The [Astral installer](https://docs.astral.sh/uv/) — it fetches
Python and runs the server without you managing an environment.

**Close the PowerBuilder IDE** before step 3. It holds exclusive locks on open
`.pbl` files and ORCA respects them.

## 2. Install and verify PowerBuilder is reachable

No clone needed. `uvx` builds and runs straight from the repository:

```pwsh
uvx --from git+https://github.com/restoresrl/pb-orca-mcp --python 3.12-x86 pb-orca-mcp doctor
```

The first run takes a minute while `uv` fetches an x86 Python and builds the
package. Then:

```text
pb-orca-mcp 0.1.0
Python: 3.12.0 (x86)

[OK] PB 22.0  [x86]  C:\Program Files (x86)\Appeon\PowerBuilder 22.0
    file_version : 22.2.0.3397
    product      : 2022 R3 Build 3397
    source       : registry
    runtime      : C:\Program Files (x86)\Appeon\Common\PowerBuilder\Runtime 22.2.0.3397
    load         : OK (session entry points bound)

Doctor OK: 1 usable install(s) for x86 Python.
```

`[OK]` marks a version in the tested set, `[??]` one outside it (still
attempted). If you get *"No PB install is usable from this Python (x64)"* you
dropped the `--python 3.12-x86`; add it back. If you get *"No PowerBuilder IDE
installation found"*, what you have is a runtime, not an IDE. Anything else:
[troubleshooting.md](troubleshooting.md).

To keep `pb-orca-mcp` permanently on your PATH instead of running it through
`uvx` each time:

```pwsh
uv tool install --python 3.12-x86 git+https://github.com/restoresrl/pb-orca-mcp
```

## 3. Point it at your own project

`doctor` proves PowerBuilder is installed and ORCA loads. It says nothing about
*your* project. This does:

```pwsh
pb-orca-mcp check C:\path\to\your\workspace.pbw
```

Give it a `.pbw`, a `.pbt` or a bare `.pbl` — whichever you have. It parses the
target, works out how your workspace stores source, opens a real ORCA session,
reads the library and exports one object, checking the bytes come out the way
PowerBuilder expects:

```text
Target
  file            : C:\proj\src\myapp.pbt
  resolved        : target myapp.pbt of 3, from myproj.pbw
  application     : myapp in myapp.pbl
  libraries       : 12
    [ok] C:\proj\src\myapp.pbl
    ...

Workspace
  root            : C:\proj
  workspace file  : C:\proj\myproj.pbw
  source of truth : ws_objects  (C:\proj\ws_objects\src\myapp.pbl.src, 214 files)
  encoding        : UTF-8 (from: pbw) -> utf8
  git             : C:\proj

PowerBuilder
  install         : PB 22.0 [x86]  C:\Program Files (x86)\Appeon\PowerBuilder 22.0
  orca            : loaded

Session
  library list    : accepted (12 libraries)
  directory       : 214 entries in myapp.pbl  ("Main application")
  export          : u_app.sru  (482 bytes as utf8)
    [ok] byte-order mark matches utf8
    [ok] export header present
    [ok] CRLF line endings

Check OK: pb-orca can read and export from myproj.pbw.
```

Nothing in your project is written: the exported file goes to a temporary
directory and is deleted before the command returns.

Two lines are worth reading closely.

**`source of truth`** tells you which of the two project shapes you are in. If
it says `ws_objects`, your workspace keeps a text file per object and *that* is
canonical — the `.pbl` is rebuilt from it. If it says `the .pbl`, the binary is
the whole truth. This determines what you commit later, and
[how-it-works.md](how-it-works.md) explains why.

**`encoding`** is the encoding PowerBuilder writes source files in for this
workspace, read from the `.pbw`. You never have to apply it yourself — ORCA
does — but a warning here about the declared encoding disagreeing with the
files on disk means the workspace is already inconsistent, and is worth fixing
before you start.

If you have several PowerBuilder versions installed, `check` asks you to pick:
add `--pb-version 22.0`.

## 4. Connect it to your MCP client

Now wire it to whatever assistant you use. This is a standard MCP server, so
the configuration is the same JSON everywhere; only the file it goes in
differs:

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

| Client | Where the block goes |
| --- | --- |
| Claude Code | `.claude/mcp.json` (project) or `~/.claude/mcp.json` (user) |
| Cursor | `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (user) |
| Codex CLI, Gemini CLI, Copilot, others | that client's MCP config file |

Reload the client and confirm the `pb_*` tools appear — in Claude Code, `/mcp`;
elsewhere, the client's tool inspector or its server log. If they do not,
[troubleshooting.md](troubleshooting.md) has the usual causes.

On a machine with one PowerBuilder version you are done. With several, you can
pin one per server entry instead of naming it in every request:

```json
"env": { "PB_INSTALL_PATH": "C:\\Program Files (x86)\\Appeon\\PowerBuilder 22.0" }
```

### Optional: give the assistant the know-how too

Registering the server gives the assistant the *tools*. Two optional skills in
[`skills/`](../skills/) give it the *judgement*: the session order, the edit
loop, and what to commit on a project with text sources. They are written to
the [Agent Skills](https://agentskills.io) `SKILL.md` standard, so any
skill-aware assistant can load them — copy the folders into its skills
directory (`~/.claude/skills/`, `~/.codex/skills/`, …). Not required; the
assistant will simply take a few more wrong turns without them.

## 5. Your first change

Ask your assistant, in your own words:

> Open a PowerBuilder session on `C:\proj\myproj.pbw` with PB 22.0, show me
> what is in `myapp.pbl`, then export `w_main` so I can look at it.

What it does behind that request:

```text
pb_session_open(pb_version="22.0")
pb_set_library_list([...])            # from the .pbt
pb_set_current_application(...)       # needed before anything compiles
pb_library_directory("myapp.pbl")     # what is in there
pb_object_export_file("myapp.pbl", "w_main", "window")
```

The last call writes `w_main.srw` and returns its path. On a workspace with
text sources that is the real file under `ws_objects/`; otherwise it is a
working copy under `.pb-orca/`. Either way it is a plain text file, and ORCA
wrote it, so the header, the encoding and the line endings are exactly what
PowerBuilder produces itself.

Now change something small — a window title, a comment — and ask:

> Import it back and tell me if it compiles.

```text
pb_object_import_file("...w_main.srw", "myapp.pbl")
→ {"success": true, "errors": [], "synced_files": [...], "sync": "ok"}
```

If the edit does not compile you get the compiler's own diagnostics, with
message number, line and column, and you iterate on the file. That loop —
change, compile, read the error, fix — is the thing this project exists to
make possible.

Then run `git status`. On a project with text sources you will see **both** the
`.sr*` file and the `.pbl` as modified, because the import updated the binary
and rewrote the text projection in the same call. That pairing is the guarantee
the server is built around, and [how-it-works.md](how-it-works.md) explains
what goes wrong without it.

> **Before you do this on work that matters**, read
> [how-it-works.md](how-it-works.md). It is the one document worth reading
> end to end: it describes how PowerBuilder stores source in two places at
> once, and the silent way a commit can end up looking healthy while the build
> is stale.

## Where to go next

| You want to | Read |
| --- | --- |
| Understand the model before touching real work | [how-it-works.md](how-it-works.md) |
| See the exact call sequence for a task | [recipes.md](recipes.md) |
| Look up a tool's arguments and output | [tools.md](tools.md) |
| Fix something that is not working | [troubleshooting.md](troubleshooting.md) |
| Build your own tooling on top of this | [integrating.md](integrating.md) |
