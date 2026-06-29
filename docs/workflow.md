# Object editing workflow

How to modify PowerBuilder objects (`.sru`, `.srf`, `.srw`, `.sra`, …) using
`pb-orca-mcp` without breaking the consistency between the binary `.pbl` and
the textual `ws_objects/` projection. Read this before your first write
operation in any PB project; the failure mode is silent and easy to commit.

## The mental model: who is the source of truth?

A PowerBuilder object lives in two forms:

- **`.pbl` library** (binary, e.g. `src/myapp.pbl`) — contains both the source
  and the compiled p-code. It is the runtime deliverable that PB IDE,
  PowerGen, and the executable read from.
- **`ws_objects/<lib>.pbl.src/<entry>.<ext>`** — a textual projection of the
  same source. Plain `.sru` / `.srf` / `.srw` / `.sra` files, suitable for
  diff, grep, code review, and git merge.

**Who is canonical depends on whether the project is under git:**

| Project type | Source of truth | Derived form | How to sync |
| --- | --- | --- | --- |
| Standalone, no git | `.pbl` | (none — no `ws_objects/`) | n/a |
| Managed with git | **`ws_objects/`** | `.pbl` | "Refresh PBL" in PB IDE, or `scc refresh target` via ORCA |

The rationale: `.pbl` files are binary, so git cannot merge them in a useful
way — any non-trivial merge produces a conflict. Appeon introduced
`ws_objects/` precisely to give git text files it can merge. As a result,
**on git projects the textual files are canonical**, and the binary library
is regenerated from them.

The "Refresh PBL" command in PB IDE reads `ws_objects/<lib>.pbl.src/` and
re-populates the `.pbl`, adding new objects, updating modified ones, and
**deleting** orphaned ones. On a typical merge: git merges the text files
under `ws_objects/`, any conflicts on the `.pbl` files are discarded, and
`.pbl` files are regenerated via Refresh PBL.

## What goes wrong if you skip the sync

A common failure mode (you will hit this sooner or later):

1. You modify `ws_objects/.../some_entry.sru` with a text editor (VS Code,
   Claude Code, `sed`, anything not PB IDE).
2. You commit. Git happily includes the new `.sru` content; the `.pbl` is
   unchanged in the commit because nothing wrote to it.
3. Anyone building from this commit gets stale code: PB compiles from the
   `.pbl`, which still contains the pre-change source.

The text file shows the fix; the binary doesn't. The commit looks healthy
on review but the build is broken.

**Rule**: modifying the SOT is correct; you must also **propagate the change
to the `.pbl` in the same commit**, because the `.pbl` is what gets built
and distributed downstream.

## Recommended workflow — pb-orca first

Two variants, depending on whether `ws_objects/` exists.

### Variant A — Git project (`ws_objects/` exists, is SOT)

You edit the file under `ws_objects/`, then propagate to the `.pbl`. The
file under `ws_objects/` is your working copy; never overwrite it with the
content of the `.pbl` (that would propagate the derived form back onto the
source of truth — wrong direction).

#### Today's procedure — manual via `pb_compile_entry_import`

Until `pb-orca-mcp` exposes the ORCA SCC commands (see "Future
improvements"), the sync has to be orchestrated step by step:

1. **Identify** the entry to modify: `ws_objects/<lib>.pbl.src/<entry>.<ext>`.
   If `git status` shows pending changes on this file, use those as the
   baseline. If the file is clean, it is the canonical SOT.

2. **Edit** the file with your normal text-edit primitives.

3. **Open an ORCA session and set up the target**:

   ```jsonc
   {"tool": "pb_session_open", "args": {"pb_version": "22.0"}}
   {"tool": "pb_set_library_list", "args": {
     "libraries": [
       "C:\\proj\\src\\app.pbl",
       "C:\\proj\\src\\<lib>.pbl"
     ]
   }}
   {"tool": "pb_set_current_application", "args": {
     "app_lib": "C:\\proj\\src\\app.pbl",
     "app_name": "app"
   }}
   ```

4. **Propagate the edit to the `.pbl`** by reading the file you just
   modified:

   ```jsonc
   // Read the file content first (host tool), then:
   {"tool": "pb_compile_entry_import", "args": {
     "lib_path": "C:\\proj\\src\\<lib>.pbl",
     "entry_name": "<entry>",
     "entry_type": "<userobject|function|window|application|...>",
     "syntax": "<full file content>"
   }}
   ```

   Expect `{"success": true, "errors": []}`. On failure, fix the SOT file
   and retry — never patch the `.pbl` separately.

5. **Integrity check** (only needed when the change adds or removes entries,
   not when a single existing entry is modified):

   - List entries in the `.pbl`: `pb_library_directory` on the lib path.
   - List files in `ws_objects/<lib>.pbl.src/`: filesystem enumeration.
   - **Entries in `.pbl` but missing from `ws_objects/`** → delete from the
     `.pbl` with `pb_library_entry_delete`.
   - **Files in `ws_objects/` but missing from `.pbl`** → import them with
     additional `pb_compile_entry_import` calls.

6. **Close** the session: `pb_session_close`.

7. **Verify with git**: both files should be modified.

   ```
   modified:   src/<lib>.pbl
   modified:   ws_objects/src/<lib>.pbl.src/<entry>.<ext>
   ```

   If the workspace file (`<project>.pbw`) is also modified, revert it
   (see "Workspace file" below) unless you actually added or removed a
   target.

8. **Commit both files in the same commit**:

   ```
   git add src/<lib>.pbl ws_objects/src/<lib>.pbl.src/<entry>.<ext>
   git commit
   ```

#### Short-cut via native ORCA SCC

PowerBuilder's ORCA API includes `scc *` commands that work with git in
offline mode. They provide the native equivalent of PB IDE's "Refresh
PBL", including add / modify / delete reconciliation. Steps 4–5 of the
manual workflow above collapse into one call sequence via the MCP tools
`pb_scc_connect_offline` → `pb_scc_set_target` → `pb_scc_refresh_target`
→ `pb_scc_close`. See the "Native ORCA SCC sync" section below for the
detail.

### Variant B — Standalone project (no `ws_objects/`, the `.pbl` is SOT)

With no `ws_objects/` directory, the `.pbl` is the only canonical form.
There is no text file to edit on disk; everything happens in memory.

1. Open the session and set up the target (steps 1, 3 of Variant A).
2. Export the entry's source into memory:

   ```jsonc
   {"tool": "pb_library_entry_export", "args": {
     "lib_path": "C:\\proj\\src\\<lib>.pbl",
     "entry_name": "<entry>",
     "entry_type": "<...>"
   }}
   // → response.source is a string with \r\n separators
   ```

3. Modify the string (regex, replace, AST manipulation — your call).
4. Re-import it: `pb_compile_entry_import` with the modified `syntax`.
5. Close the session. Only the `.pbl` has changed; commit it alone.

### Editing `.sr*` source files — encoding caveat

PB IDE picks the encoding of `.sr*` files on disk from the workspace
`.pbw` `DefaultExportEncode` directive, which takes one of three values:

| Value | First bytes | Notes |
|---|---|---|
| `"UTF-8"` | `EF BB BF` | PB 2022 default. Observed across the whole Restore stack surveyed. |
| `"UTF-16BOM"` | `FF FE` | PB legacy default (pre-2019). |
| `"ANSI"` | (no BOM) | Older Windows workspaces, system codepage. |

All three use **CRLF** line endings. On read (Refresh, Import) PB
detects via BOM and accepts any of the three; on write (Export, IDE
Refresh + Regenerate, SCC-driven regen) PB emits in the configured
encoding. An agent that writes the wrong one creates a phantom-diff
cascade — PB re-exports the file on the next Refresh.

Most host editors and CLI write tools default to UTF-8 no-BOM with LF
when they save text files — so a naïve "edit the `.srw` and refresh"
round-trip can silently strip the BOM or flip line endings, at which
point `pb_scc_refresh_target` and `pb_compile_entry_import` fail.
After any host edit on a `.sr*` file, reconvert before the refresh,
matching the workspace setting:

```powershell
$path = "...\<file>.srw"
$content = Get-Content -Raw -Path $path -Encoding UTF8
$content = $content -replace "`r`n","`n" -replace "`n","`r`n"   # normalize to CRLF

# Pick ONE based on the .pbw DefaultExportEncode:
# UTF-8 BOM (PB 2022 default):
[System.IO.File]::WriteAllText($path, $content, [System.Text.UTF8Encoding]::new($true))
# UTF-16 LE BOM:
[System.IO.File]::WriteAllText($path, $content, [System.Text.Encoding]::Unicode)
# ANSI (no BOM, system codepage):
[System.IO.File]::WriteAllText($path, $content, [System.Text.Encoding]::Default)
```

After conversion, verify the first bytes match the target BOM (or the
absence of one for ANSI). Validated 2026-05-22 against PB 22.0 on a
clean `test-mcp` workspace.

**Recommended alternative**: avoid the manual re-encode step entirely
by calling `pb_edit_and_import` with the matching `source_encoding`
parameter — the tool writes the file with the right BOM + codec,
rebuilds the canonical `$PBExportHeader$` / `$PBExportComments$`
header block (PowerScript-escape with CRLF normalization), and
imports atomically. Single tool call instead of edit + re-encode +
import.

### Optional: PowerScript style normalization

`pb_edit_and_import` can also normalize the body it writes — indent,
line endings, keyword case, operator spacing — so an agent's output
matches what PB IDE would have written. This is **opt-in per workspace**:
the formatter only runs once you commit a `.pb-format.toml` at (or above)
the source directory.

- `pb_edit_and_import` takes a `format` parameter, default `"auto"`:
  `"auto"` formats only when a `.pb-format.toml` is discovered walking up
  from `source_path` (so workspaces without that file behave exactly as
  before — zero breaking change); `True` always formats (discovered
  config or engine defaults); `False` never does. The response carries
  `formatted: bool`.
- The same engine is available offline as the `pb-format` CLI:
  `pb-format detect` writes a starter config by sampling the workspace,
  `pb-format format <paths>` normalizes `.sr*` files in place (preserving
  header and encoding), and `pb-format check <paths>` reports drift
  without writing (exit non-zero — handy in pre-commit / CI).

The formatter is deliberately scope-limited (four invariants, no
re-indent, no DataWindow `.srd`). Full contract, config reference, and
rationale: [`formatter.md`](formatter.md).

### Passing large `syntax` strings

`pb_compile_entry_import` accepts `syntax` inline in the tool call. The
MCP JSON parser handles tens of kilobytes fine and Unicode escapes
(`<`, `'`, …) are equivalent to literal `<`, `'`. In Variant A
you read directly from the file with the host tool, which avoids any
manual serialization. In Variant B you keep the string in memory.

If you ever need to JSON-encode a file from the shell on Windows:

```powershell
Add-Type -AssemblyName System.Web.Extensions
$json = (New-Object System.Web.Script.Serialization.JavaScriptSerializer).Serialize(
    (Get-Content -Raw 'file.sru'))
# $json includes the surrounding quotes
```

(`jq` is not always present outside Git Bash; PowerShell 5.1's
`ConvertTo-Json` wraps a bare string in `{"value":"…"}`, which has to be
unwrapped before use.)

## The minimal IDE-equivalent workflow

A simpler variant of Variant A for cases where you know the change is
limited to one existing entry and there are no additions or deletions:

1. Edit `ws_objects/<lib>.pbl.src/<entry>.<ext>` with your editor.
2. Open the ORCA session, set the library list, set the current
   application.
3. Read the file content, call `pb_compile_entry_import`.
4. Close the session and commit both files.

It is essentially the same as Variant A without the integrity check
(step 5). Equivalent to what PB IDE does when you save a single object.

## "Refresh PBL" from PB IDE

PB IDE has a Refresh command on each `.pbl` that reads
`ws_objects/<lib>.pbl.src/` and re-populates the library — adding,
modifying, and **deleting** objects to match the directory. It is the
canonical direction of the flow on PB-on-git projects: SOT → derived
form.

Run Refresh PBL after:

- a git merge that touched `ws_objects/`;
- a branch switch (`git checkout <other-branch>`) that put `ws_objects/`
  in a state different from the `.pbl` in the working copy;
- any external edit of `ws_objects/` (this includes Claude Code with
  external edits, or `git revert`).

From a CLI / non-IDE context the native equivalent is the `pb_scc_*`
tool sequence; see "Native ORCA SCC sync" below.

## Workspace file (`.pbw`)

The `<project>.pbw` file contains the workspace target list and the
current target preference (`DefaultTarget`, `DefaultRemoteTarget`). The
current target is a per-user preference, not a shared truth.

**Operational rule:**

- **Revert by default** when only the current-target lines change.
  `pb_set_current_application` may rewrite the `.pbw` as a side effect.
- **Commit** only when a target was added or removed from the workspace
  (rare but real).

```bash
# .pbw modified by an ORCA session, no target added/removed:
git checkout -- <project>.pbw
```

Note: rewriting the `.pbw` by `pb_set_current_application` has been
observed to be **non-deterministic** — the file is not always touched on
every call. Always check `git status` after an ORCA session and revert
the `.pbw` if needed.

## Native ORCA SCC sync (offline mode, git/svn)

PowerBuilder's ORCA API exposes a `scc *` family of commands that work
with git/svn in offline mode (no remote SCC server connection). It is
the native equivalent of "Refresh PBL" in PB IDE: syncs
`ws_objects/` → `.pbl` including add / modify / delete in a single
call, collapsing Variant A from 8 manual steps to ~4. Exposed via 6
MCP tools: `pb_scc_connect_offline`, `pb_scc_set_target`,
`pb_scc_refresh_target`, `pb_scc_exclude_library_list`,
`pb_scc_get_connect_properties`, `pb_scc_close`.

Typical call sequence (`local_proj_path` must point to the **parent of
`ws_objects/`**):

```jsonc
{"tool": "pb_session_open",        "args": {"pb_version": "22.0"}}
{"tool": "pb_scc_connect_offline", "args": {
    "workspace_file":   "C:\\proj\\<project>.pbw",
    "local_proj_path":  "C:\\proj"
}}
{"tool": "pb_scc_set_target", "args": {
    "target_file": "C:\\proj\\<lib>.pbt",
    "flags":       ["refresh_all", "importonly"]
}}
{"tool": "pb_scc_refresh_target", "args": {"rebuild_type": "incremental"}}
{"tool": "pb_scc_close",   "args": {}}
{"tool": "pb_session_close","args": {}}
```

References: <https://docs.appeon.com/pb2025/pbug/usage_notes_2.html>
and <https://docs.appeon.com/pb2025/pbug/ug36631.html>.

Known limitations:

- `scc get latest version` and direct connections to a remote SCC
  server do not work with git/svn — by design. Use git/svn CLI for
  those (clone, pull, push).
- `pb_scc_get_connect_properties` always returns `PBORCA_REGREADERROR
  (-23)` on a git/svn workspace (the `.pbw` has no SCC block);
  `pb_scc_connect_offline` tolerates it and proceeds. Both are
  doc-officially expected per Appeon.
- `pb_scc_set_target` **also configures the session's library list and
  current application** as a side effect — so subsequent calls to
  `pb_set_library_list` or `pb_set_current_application` return
  `PBORCA_DUPOPERATION (-2)`. Skip them in the SCC flow. A direct
  `pb_application_rebuild` call after `scc_set_target` works without
  any additional setup.
- On the first upload of a workspace to git, objects are generated under
  `ws_objects/` in a flat layout; entries with the same name from
  different `.pbl`s overwrite each other. Workaround: organize the
  project so each `.pbl` has its own `ws_objects/<lib>.pbl.src/`
  subdirectory. PB IDE does this automatically for newly-created
  workspaces.
- In offline mode only `local_proj_path`, `log_file`, `append_log` take
  effect; the other config fields are silently ignored by the SCC layer
  (per `ug36631.html`).

## Future improvements

### Diagnostic comparison: pbl ↔ ws_objects

Independent of the refresh capability above, a purely diagnostic tool
would also be useful: compare a `.pbl` to its `ws_objects/<lib>.pbl.src/`
directory and report differences (missing entries on either side, source
divergences for entries present in both) **without modifying anything**.
Suitable for CI / pre-merge consistency checks.

Today it can be built from `pb_library_directory` + filesystem
enumeration + `pb_library_entry_export`.

### Replace PowerGen with a Claude-Code-orchestrated build

PowerGen is itself a wrapper over ORCA. The build pipeline currently
expressed in `.bat` scripts (PowerGen + `VECli.exe` for VersionEdit + file
copies + `git commit/tag/push`) can be moved into Claude Code workflows
that call `pb-orca-mcp` primitives directly.

| Today (PowerGen / `.bat`) | Future (Claude Code) |
| --- | --- |
| `.gen` orchestrating `/R /P /O /E` | A workflow that calls `pb_application_rebuild` and `pb_compile_entry_import_list` (or `scc refresh target`) |
| File copies (EXE / PBD to build output dir) | Standard file operations |
| `VECli.exe` for WIN32 metadata | Direct `VECli.exe` call from a shell tool |
| `git add` / `commit` / `push` | Native git tool calls |

Out of scope for `pb-orca-mcp` itself — each project has its own build
recipe — but `pb-orca-mcp` provides all the primitives needed.

## `pb-orca-mcp` cheat sheet (object-editing surface)

Session bootstrap:

- `pb_discover_pb_install` — list installed PB versions
- `pb_session_open` — pick a PB install
- `pb_session_close` — idempotent

Target setup:

- `pb_target_info` — read `lib_list`, `app_name`, `app_lib` from a `.pbt`
- `pb_set_library_list` — required before `set_current_application`
- `pb_set_current_application` — required before any write call. **May
  rewrite the workspace file**, revert by default

Read:

- `pb_library_directory` — list entries in a `.pbl` (used for the
  integrity check in Variant A step 5)
- `pb_library_entry_information` — metadata of a single entry
- `pb_library_entry_export` — return an entry's source as a string
- `pb_object_query_hierarchy` — walk the ancestor chain
- `pb_object_query_reference` — list a named object's outgoing references (what it calls/uses)

Write:

- `pb_compile_entry_import` — compile + import a single entry. **Does
  not update `ws_objects/`** (verified experimentally) — consistent with
  the SOT model: ORCA writes to the `.pbl`, you write to the SOT file
  manually
- `pb_compile_entry_import_list` — batch variant
- `pb_library_entry_delete` — delete an entry from the `.pbl` (used in
  the integrity check for orphan entries)
- `pb_object_regenerate` — re-emit p-code only, no source-text change
- `pb_application_rebuild` — full / incremental / migrate / 3pass
  rebuild

SCC (offline mode for git/svn workspaces):

- `pb_scc_get_connect_properties` — read SCC block from `.pbw` (returns
  `-23` on git/svn, expected)
- `pb_scc_connect_offline` — open offline connection (no remote server)
- `pb_scc_set_target` — bind a `.pbt` and list affected PBLs
- `pb_scc_refresh_target` — sync `ws_objects/` → `.pbl` (add/modify/delete)
- `pb_scc_exclude_library_list` — exclude `.pbd` references from refresh
- `pb_scc_close` — close the SCC connection (also done by Session.close)

Diagnostics:

- `pb_get_last_compile_errors` — replay diagnostics from the last
  compile or rebuild call

## Pitfalls

- **Never commit only the `ws_objects/` files**: the `.pbl` must be in
  the same commit. The build pipeline reads from the `.pbl`.
- **Never commit only the `.pbl`**: on git projects the `.pbl` is the
  derived form. Committing only the binary leaves the SOT out of sync;
  any subsequent merge or Refresh PBL will undo the binary-only change.
- **Never overwrite `ws_objects/<entry>.<ext>` with the content of the
  `.pbl`** (e.g. via `pb_library_entry_export` + `Write`) on git projects.
  That propagates the derived form back onto the SOT, which is the
  wrong direction. The only exception is recovery scenarios where the
  `.pbl` is known to be authoritative (e.g. after a fix made in PB IDE
  on a machine without `ws_objects/` checked out).
- **Don't open the `.pbl` in PB IDE during an ORCA write session**: the
  IDE holds an exclusive lock and the import call will fail. Close PB
  IDE first.
- **The `.pbd` deployable stays stale until the next build**: `pb-orca`
  doesn't produce `.pbd` files — only PowerGen / build scripts do. This
  is expected; consumers depending on the `.pbd` won't see your change
  until you run the build.
- **`pb_object_regenerate` is not "regenerate the `.src`"**: it
  re-emits the internal p-code of the entry inside the `.pbl`, without
  touching the textual file.
- **`pb_compile_entry_import` doesn't update `ws_objects/`** (verified
  experimentally). On git projects you handle the SOT file directly with
  your host tools; ORCA's job is to propagate to the `.pbl`. On
  standalone projects there is no SOT file to keep in sync.
- **`pb_set_current_application` may rewrite `.pbw`**: observed to be
  non-deterministic. Always check `git status` after a session and
  revert the workspace file unless you actually changed the target list.
- **PB IDE silently regenerates `ws_objects/<entry>.<ext>` when you save
  an object**: this is by design and is how PB IDE keeps SOT and derived
  form in sync. It bites you if you edited `ws_objects/` externally and
  then opened the object in PB IDE **without** running Refresh PBL
  first: the IDE regenerates the `.src` from the (potentially stale)
  `.pbl`, overwriting your external edit. Run Refresh PBL first.

## TL;DR

> **Git project (with `ws_objects/`)**: the SOT is `ws_objects/`. Edit
> files under `ws_objects/<lib>.pbl.src/<entry>.<ext>`, then propagate
> to the `.pbl` with `pb_compile_entry_import` (and run an integrity
> check on add / delete). When `pb-orca-mcp` exposes
> `scc refresh target incremental` this is a single call. Commit both
> the `.pbl` and the `.src` in the same commit. Revert the `.pbw`
> unless you actually changed the target list.
>
> **Standalone project (no `ws_objects/`)**: the `.pbl` is the SOT.
> Work in memory: export → modify → import. Commit just the `.pbl`.
>
> **Never** commit only the `ws_objects/` files leaving the `.pbl`
> stale, and **never** overwrite `ws_objects/` files from the `.pbl` on
> a git project — that is the SOT, not a sink.
