# Troubleshooting

Symptoms, causes, and what to do — everything that commonly goes wrong, in one
place.

Two commands answer most questions before you read any further:

```pwsh
pb-orca-mcp doctor                       # is PowerBuilder reachable at all?
pb-orca-mcp check C:\proj\myproj.pbw     # does the whole stack work on my project?
```

`check` runs the same path the MCP tools do, without an MCP client in the way,
so it tells you whether a problem is in PowerBuilder, in this server, or in the
wiring to your assistant.

- [Installation and startup](#installation-and-startup)
- [The client does not see the tools](#the-client-does-not-see-the-tools)
- [Session errors](#session-errors)
- [Reading and writing objects](#reading-and-writing-objects)
- [Surprises in git](#surprises-in-git)
- [ORCA error codes](#orca-error-codes)

---

## Installation and startup

| Symptom | Cause | Fix |
| --- | --- | --- |
| The first `uvx` command fails on git: *authentication failed*, *repository not found*, *could not read Username* | This repository is private during internal dogfooding, and `uv` fetches it through `git`. Nothing is wrong with PowerBuilder. | Authenticate `git` to GitHub once — `git clone https://github.com/restoresrl/pb-orca-mcp` and let the credential helper store the result — then retry. If the clone itself is refused, you have not been granted access to the repository. |
| `doctor`: *No PowerBuilder IDE installation found* | What is installed is the PB **runtime**, not the IDE. Runtime packages do not ship `pborc.dll`. | Install PowerBuilder IDE 2019 R3 or later. `doctor` lists runtime-only installs separately so you can see what it found. |
| `doctor`: *No PB install is usable from this Python (x64)* | Architecture mismatch. `ctypes` cannot load an x86 DLL from x64 Python, and PB IDE is x86 through 2025. | Use an x86 interpreter: add `--python 3.12-x86` to the `uvx` / `uv tool install` command, and to the `args` in your MCP config. |
| `doctor` lists the install but says `load failed: …` | The DLL is blocked — antivirus, Defender, or SmartScreen quarantining a file from an unfamiliar publisher. | Whitelist `<install>\IDE\pborc.dll`, or repair the PowerBuilder installation. |
| `doctor` finds an install but `IPS Name` is missing | A very old, pre-Appeon registry layout. | Set `PB_INSTALL_PATH` to the install directory explicitly. |
| An untested major loads, then a tool returns `PBORCA_UNKNOWN(...)` | ABI drift from a release older than PB 2019. | Use PB 2019 R3 or later. The ABI has been stable since. |
| Nothing works on a PB 2025 *solution* (`.pbproj` + PBL folders) | ORCA does not operate on the solution format. | Use the classic workspace format (`.pbw` + `.pbt` + binary `.pbl`), which PB 2025 still supports. A project migrated to a solution is out of scope. |
| `WinError 182` loading a second PowerBuilder version in one process | Windows caches DLLs by base name, so `pbvm.dll` from the first PB install poisons the name for any other. | One PowerBuilder version per process. Close the session and start a new server process to switch. |

## The client does not see the tools

Work through it in this order; each step rules out a layer.

1. **Does the server run at all?**
   `uvx --from git+https://github.com/restoresrl/pb-orca-mcp pb-orca-mcp --help`
   should print usage. If not, the problem is `uv` or network access to GitHub,
   not this project.
2. **Does PowerBuilder work?** `pb-orca-mcp doctor` must exit 0.
3. **Does your project work?** `pb-orca-mcp check <your .pbw>` must exit 0. If
   steps 1 to 3 pass, everything below the MCP layer is fine.
4. **Is the config file the right one?** Clients differ: `.mcp.json` at the
   project root for Claude Code, `.cursor/mcp.json` for Cursor, and so on — see
   [getting-started.md](getting-started.md#4-connect-it-to-your-mcp-client).
   The JSON block itself is identical everywhere.
5. **Did the client reload?** Most only read the config at startup.
6. **Read the client's MCP log.** The server writes its errors to stderr and
   the client captures them. A missing `--python 3.12-x86` in `args` typically
   shows up here as an arch error, not as a missing server.

## Session errors

| Error | Meaning | Fix |
| --- | --- | --- |
| `PB_ORCA_MCP_STATEERROR: no ORCA session open` | A tool that needs a session was called before `pb_session_open`. | Open the session first. |
| `PB_ORCA_MCP_STATEERROR: A session is already open` | ORCA allows one session per process. | `pb_session_close` first. Switching PowerBuilder version also needs a new process. |
| `PBORCA_LIBLISTNOTSET (-5)` | `pb_set_current_application` was called before `pb_set_library_list`. | The order is fixed: open → library list → current application. |
| `PBORCA_CURRAPPLNOTSET (-13)` | A compile, rebuild or object query ran without a current application. | Call `pb_set_current_application`. |
| `PBORCA_DUPOPERATION (-2)` right after `pb_scc_set_target` | Expected. `pb_scc_set_target` already sets the library list and the current application. | Skip those two calls in the SCC flow. |
| `PBORCA_VERSIONAMBIGUOUS` / *several installs are usable* | More than one PowerBuilder matches. | Pass `pb_version`, or `install_path` when two installs share a major. |
| `PBORCA_REGREADERROR (-23)` from `pb_scc_get_connect_properties` | Expected on a git or svn workspace: the `.pbw` has no SCC block. | Ignore it. `pb_scc_connect_offline` tolerates it and proceeds. |
| `PBORCA_IMPORTONLY_REQ (-30)` | Offline SCC requires the `importonly` flag. | Pass it in `pb_scc_set_target`'s `flags`, not to the refresh call. |

## Reading and writing objects

| Symptom | Cause | Fix |
| --- | --- | --- |
| `PBORCA_LIBIOERROR (-7)` on any write | The PowerBuilder IDE has that `.pbl` open and holds an exclusive lock. ORCA respects the lock but does not queue behind it. | Close the IDE, or work on a copy. |
| `C0114: Error scanning object source entry` | The source did not arrive as ORCA expected. If you are calling ORCA directly, `lSrcSize` is a **byte** count, not a character count. Through this server, it usually means the session was left configured with a non-Unicode import encoding. | Reset with `pb_session_configure` (no arguments), then retry. |
| *the session configuration would corrupt the transfer* | `pb_session_configure` left a non-Unicode export or import encoding in effect. The in-memory tools refuse rather than returning mangled text. | `pb_session_configure` with no arguments resets to defaults. |
| `PBORCA_OBJEXISTS (-8)` on an export | The target directory does not exist — ORCA does not create it. | The file tools create it for you; if you are driving `pb_session_configure` by hand, create the directory first. |
| `PBORCA_OBJNOTFOUND (-3)` | The entry name or type is wrong, or the library is not in the library list. | Check with `pb_library_directory`. Names are case-insensitive but types are not guessed. |
| A compile fails but the response has no `error` envelope | Not a failure of the call. Compile diagnostics come back as `success: false` with a populated `errors` array. | Read `errors`: message number, text, line, column. |
| An import "succeeded" but the object is now garbage | Almost always an encoding problem upstream of ORCA — source read with the wrong codec. ORCA returns 0 in this case, so it is silent. | Let `pb_object_export_file` produce the file and hand the same file back to `pb_object_import_file`. Never hand-build a `.sr*`. |
| `pb_object_export_file` writes into `.pb-orca/` on a project that has `ws_objects/` | No projection directory was found for *that* library. | Check `pb_workspace_info`: `sources.source_dir` is where it looked. If `outside_source_tree` is true, the library is a vendored or third-party one and is not tracked as source. |

## Surprises in git

| Symptom | Cause | Fix |
| --- | --- | --- |
| Every line of a `.sr*` shows as changed after an import | The source was imported with LF line endings. PowerBuilder stores CRLF, so the whole file gets rewritten. | Re-export the object and import the file without letting an editor normalize line endings. |
| `<project>.pbw` is modified and you did not touch the target list | `pb_set_current_application` can rewrite it as a side effect, non-deterministically. | Revert it, unless you actually added or removed a target. |
| Untracked `.sr*` files and a `.pbg` appear in the project root | `pb_scc_refresh_target` writes a flat export plus a `.pbg` registry into `local_proj_path`. | Expected; delete what you did not want. For a single object, `pb_object_import_file` is quieter. |
| The `.pbl` changed but no `.sr*` did | The project has no text projection for that library, or the call ran with `sync_sources="never"`. | Check `pb_workspace_info`. `sync` in the tool response says which case you are in. |
| A `.sr*` changed but the `.pbl` did not | Someone edited the text file without importing it. The build reads the `.pbl`, so that commit reviews clean and builds stale. | Import the file. This is the failure mode [how-it-works.md](how-it-works.md) §6 is about. |
| Only the binary block of a `.sr*` differs, and nobody changed the source | The object hosts an OLE or ActiveX control. The binary payload is stable within one PowerBuilder build but differs across builds. | Nothing to fix. See [how-it-works.md](how-it-works.md) §9. |

## ORCA error codes

Server-generated names, all prefixed `PB_ORCA_MCP_`:

| Name | Meaning |
| --- | --- |
| `PB_ORCA_MCP_INVALIDARGS` | An argument failed validation |
| `PB_ORCA_MCP_STATEERROR` | Wrong session state, or a configuration that would corrupt the transfer |
| `PB_ORCA_MCP_IOERROR` | A source file could not be read, or a directory could not be created |
| `PB_ORCA_MCP_WORKSPACEERROR` | The workspace layout around a `.pbl` could not be resolved |
| `PB_ORCA_MCP_VERSIONNOTFOUND` | No install with the requested `pb_version` |
| `PB_ORCA_MCP_VERSIONAMBIGUOUS` | Several installs share that major; pass `install_path` |
| `PB_ORCA_MCP_INSTALLNOTFOUND` | `install_path` matched no discovered install |
| `PB_ORCA_MCP_LOADFAILED` | `pborc.dll` would not load |

Everything else comes straight from ORCA and keeps its `PBORCA_*` name. The
full list of 33 codes is in `PBORCA.H` in your PowerBuilder SDK, and in
`src/pb_orca_mcp/orca/constants.py`.

## Still stuck

Open an issue with the output of `pb-orca-mcp doctor` and, if you can share it,
`pb-orca-mcp check` on the project involved. Those two together identify the
PowerBuilder version, the architecture, the workspace shape and the encoding,
which is most of what anyone needs to reproduce a problem.
