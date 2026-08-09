# MCP tool reference

Every tool returns a JSON-friendly Python dict. Errors come back as
`{"error": {"code", "name", "message"}}`; success payloads are tool-specific.
ORCA error codes are mapped to their symbolic name (e.g. `PBORCA_OBJNOTFOUND`)
via `ORCA_ERROR_NAMES`. Errors originating from the server wrapper itself
(state guards, argument validation) use names prefixed with `PB_ORCA_MCP_*`.

Tools are grouped by functional area.

---

## Discovery

### `pb_discover_pb_install()`

Enumerate PowerBuilder IDE installations on the local machine.

**Input**: none.

**Output**:
```json
{
  "ide_installations": [
    {
      "version": "22.0",
      "file_version": "22.2.0.3397",
      "product_version": "2022 R3 Build 3397",
      "arch": "x86",
      "install_path": "C:\\Program Files (x86)\\Appeon\\PowerBuilder 22.0",
      "ide_path": "C:\\Program Files (x86)\\Appeon\\PowerBuilder 22.0\\IDE",
      "orca_dll": "C:\\Program Files (x86)\\Appeon\\PowerBuilder 22.0\\IDE\\pborc.dll",
      "tested": true,
      "source": "registry"
    }
  ],
  "runtime_only_installations": [
    {"path": "C:\\...\\Runtime 22.0", "reason": "pborc.dll missing under IDE/", "version": "22.0"}
  ]
}
```

`tested: true` means the major version is in the project's `KNOWN_VERSIONS`
tuple (`19.0`, `22.0`, `25.0`), the actively tested set. Untested majors
are still returned with `tested: false`; load is attempted optimistically.

### `pb_target_info(path)`

Parse a PowerBuilder `.pbt` (target) or `.pbw` (workspace) file. Does **not**
return the PB version: `.pbt`/`.pbw` carry only the file-format magic
constant (`Save Format v3.0(19990112)` since 1999), not a release marker.
Version selection must be explicit on `pb_session_open`.

**Input**: `{"path": "C:\\projects\\foo\\foo.pbt"}`.

**Output** (`.pbt`):
```json
{
  "kind": "pbt",
  "target_name": "foo",
  "app_name": "foo",
  "app_lib": "foo.pbl",
  "lib_list": ["foo.pbl", "..\\dep\\bar.pbl"],
  "type": "pb"
}
```

**Output** (`.pbw`):
```json
{
  "kind": "pbw",
  "workspace_name": "myws",
  "targets": ["src\\main.pbt", "src\\tools.pbt"],
  "default_target": "src\\main.pbt",
  "default_export_encode": "UTF-8"
}
```

`default_export_encode` is the encoding the IDE writes `ws_objects/` files in
(`UTF-8`, `UTF-16BOM`, `ANSI`). Empty when the directive is absent, in which
case UTF-8 is assumed.

### `pb_workspace_info(lib_path)`

Describe the workspace around a `.pbl`: whether it keeps a `ws_objects/` text
projection, where that projection is, which encoding it uses, whether git is
watching, and where working files go when there is no projection. Needs no
ORCA session and no PowerBuilder install, so it is safe as a first call on an
unfamiliar project.

**Input**: `{"lib_path": "C:\\proj\\src\\app.pbl"}`.

**Output**:
```json
{
  "root": "C:\\proj",
  "workspace_file": "C:\\proj\\proj.pbw",
  "mode": "ws_objects",
  "ws_objects_dir": "C:\\proj\\ws_objects",
  "sources": {
    "lib_path": "C:\\proj\\src\\app.pbl",
    "source_dir": "C:\\proj\\ws_objects\\src\\app.pbl.src",
    "exists": true,
    "file_count": 214
  },
  "export_encode": "UTF-8",
  "orca_encoding": "utf8",
  "encoding_source": "pbw",
  "observed_encoding": "utf8",
  "git_root": "C:\\proj",
  "source_protection": "protected",
  "work_dir": "C:\\proj\\.pb-orca",
  "outside_source_tree": false,
  "advice": "Text projection present: ..."
}
```

- `mode`: `ws_objects` (the text files are the source of truth) or `pbl_only`
  (the `.pbl` is).
- `encoding_source`: `pbw` (declared), `observed` (sniffed from an existing
  `.sr*` because the `.pbw` is silent), or `default`.
- `observed_encoding` differing from `export_encode` means the workspace is
  already inconsistent: the IDE will rewrite those files on its next export.
- `sources.source_dir` is populated even when `exists` is false, so a bootstrap
  knows where to write.
- `source_protection`: `protected` when a `.gitattributes` rule exempts the
  `.sr*` files from git's line-ending translation (`binary`, `-text`,
  `text=false`, or `eol=crlf`), `unprotected` when nothing does, `no_git`
  outside a working tree. **Check this before any edit loop.** Unprotected is
  the quiet failure: git stores the sources with LF and checks them out with
  CRLF, so the index and the working tree differ by exactly the bytes ORCA
  writes -- a change can land in the `.pbl` and its projection while
  `git status` stays clean, and nobody sees the drift until a fresh checkout.
  The fix is a `*.sr* binary` rule (plus `*.pbl`, `*.pbd`) followed by
  `git add --renormalize`, in its own commit, because it rewrites every source
  in the index. Note that `eol=lf` counts as unprotected: it is a deliberate
  policy pointed the wrong way, since ORCA writes CRLF. This answers whether
  the protection *exists*; to measure what the index already holds, run
  `git ls-files --eol`.
- `outside_source_tree`: the workspace keeps a projection, but this library has
  no directory under it. That combination is what a **vendored dependency
  snapshot or a third-party component** looks like — a library that lives
  inside the project but is not tracked as source. Such a library is normally
  replaced wholesale by whatever produced it rather than edited in place, and
  should not have a projection generated for it. Branch on this before writing;
  `advice` says the same thing in prose.

---

## Session

### `pb_session_open(*, pb_version=None, install_path=None)`

Open the singleton ORCA session against a specific PB install. **Exactly one**
of `pb_version` or `install_path` is required. `install_path` wins if both
are passed. ORCA is single-session-per-process; calling `open` a second
time raises `PB_ORCA_MCP_STATEERROR`.

**Output** (success):
```json
{
  "ok": true,
  "pb_version": "22.0",
  "file_version": "22.2.0.3397",
  "product_version": "2022 R3 Build 3397",
  "arch": "x86",
  "install_path": "C:\\Program Files (x86)\\Appeon\\PowerBuilder 22.0",
  "orca_dll": "...",
  "tested": true
}
```

**Output** (errors): `PB_ORCA_MCP_INVALIDARGS` (neither arg supplied),
`PB_ORCA_MCP_VERSIONNOTFOUND`, `PB_ORCA_MCP_VERSIONAMBIGUOUS` (multiple installs
of the same major: disambiguate with `install_path`),
`PB_ORCA_MCP_INSTALLNOTFOUND` (path didn't match any discovered install),
`PB_ORCA_MCP_LOADFAILED` (DLL refused to load), `PB_ORCA_MCP_STATEERROR`
(session already open).

### `pb_session_close()`

Close the ORCA session if open. Idempotent.

**Output**: `{"ok": true, "was_open": <bool>}`.

### `pb_set_current_application(app_lib, app_name)`

Configure the current target's application object. `PBORCA_LIBLISTNOTSET (-5)`
is the most common error here: call `pb_set_library_list` first.

**Output** (success): `{"ok": true, "app_lib": "...", "app_name": "..."}`.

### `pb_session_configure(export_encoding="unicode", export_headers=False, export_include_binary=False, export_to_file=False, export_directory=None, import_encoding="unicode", debug=False)`

`PBORCA_ConfigureSession` — the session-wide ORCA options: export encoding,
export headers, write-to-file mode and its target directory, import encoding,
and the debug compiler directive. Calling it with no arguments resets the
session to ORCA's defaults.

The source-file tools set and restore this themselves, so you rarely need it
directly; it is exposed because it is part of ORCA's public API and because
`debug` has no other entry point.

**Careful**: `export_encoding` applies to in-memory exports too, where anything
other than `unicode` packs those bytes into a wide buffer and the decoded
string comes back mangled. `pb_library_entry_export` and
`pb_compile_entry_import` refuse to run while such a configuration is in
effect rather than returning plausible garbage.

**Output**: `{"ok": true, "config": {...}}` — the configuration applied.

### `pb_set_library_list(libraries)`

Set the library list (`.pbl`/`.pbd` paths) for the current session. The
list cannot be empty. Path separators are passed through as-is to ORCA.

**Output** (success): `{"ok": true, "libraries": [...]}`.

---

## Source files: the export → edit → import loop

The three tools an agent uses to change PowerBuilder code. ORCA writes and
reads the `.sr*` file; the caller edits it with ordinary file tools; nothing in
this server parses PowerScript.

Every tool here keeps the text projection and the `.pbl` in step. See
[`how-it-works.md`](how-it-works.md) for why that matters and what breaks
without it.

### `pb_object_export_file(lib_path, entry_name, entry_type, dest_dir=None)`

Write an object's source to a `.sr*` file and return its path. ORCA produces
the bytes — export header, `$PBExportComments$`, BOM, CRLF — so the file is
byte-identical to what the PB IDE writes on Save.

The destination is detected unless `dest_dir` says otherwise:

| Project | Destination | `is_source_of_truth` |
| --- | --- | --- |
| keeps `ws_objects/` | the library's `ws_objects/<lib>.pbl.src/` | `true` |
| binary-only | `<workspace>/.pb-orca/` | `false` |

Exporting an unchanged object into a projection rewrites the same bytes, so it
leaves `git status` clean. A working directory created inside a git repo gets a
self-ignoring `.gitignore`; the repository's own `.gitignore` is never touched.

**Output**:
```json
{
  "ok": true,
  "file_path": "C:\\proj\\ws_objects\\app.pbl.src\\w_main.srw",
  "lib_path": "C:\\proj\\app.pbl",
  "entry_name": "w_main",
  "entry_type": "window",
  "encoding": "utf8",
  "export_encode": "UTF-8",
  "bytes": 713,
  "mode": "ws_objects",
  "is_source_of_truth": true
}
```

### `pb_object_import_file(file_path, lib_path, entry_name=None, entry_type=None, comments=None, sync_sources="auto")`

Compile a `.sr*` file into the `.pbl`, then refresh the text projection.

`entry_name`, `entry_type` and `comments` default to the file's stem, its
extension, and its `$PBExportComments$` line, so a file produced by
`pb_object_export_file` round-trips with no extra arguments. An entry that does
not exist yet is created.

The file is read without translating line endings. PowerBuilder stores CRLF,
and importing LF-normalized text rewrites every line inside the `.pbl`, which
surfaces later as a whole-file phantom diff.

On success, with `sync_sources="auto"` and a project that keeps a projection,
ORCA rewrites the projection file so the text on disk is exactly what the
`.pbl` now holds. That is what keeps git honest. `sync_sources="never"` skips
it.

**Output**:
```json
{
  "success": true,
  "lib_path": "C:\\proj\\app.pbl",
  "entry_name": "w_main",
  "entry_type": "window",
  "file_path": "C:\\proj\\ws_objects\\app.pbl.src\\w_main.srw",
  "file_encoding": "utf8",
  "errors": [],
  "synced_files": ["C:\\proj\\ws_objects\\app.pbl.src\\w_main.srw"],
  "sync": "ok"
}
```

`sync` is `ok`, `not_applicable` (no projection), `never`, or `failed` (with
`sync_error`). On a compile error nothing is synced, `errors` carries the
diagnostics, and the file is left exactly as you wrote it. ORCA does still
write the partial source into the `.pbl` on a failed import, so fix the file
and re-import rather than assuming the entry was untouched.

### `pb_library_export_sources(lib_path, dest_dir=None, entry_type="any")`

Export every object in a library to `.sr*` files, through ORCA. Two uses: read
a whole library as grep-able text in one call, or bootstrap the
`ws_objects/<lib>.pbl.src/` tree on a project that only ever had the binary,
turning opaque binary commits into reviewable diffs.

`dest_dir` defaults to the library's projection directory, created if missing.
Entry kinds with no source form (`project`, `proxyobject`, `binary`) are always
skipped.

**Output**:
```json
{
  "ok": true,
  "lib_path": "C:\\proj\\app.pbl",
  "dest_dir": "C:\\proj\\ws_objects\\app.pbl.src",
  "encoding": "utf8",
  "count": 4,
  "written": [
    {"entry_name": "w_main", "entry_type": "window",
     "file_path": "C:\\proj\\ws_objects\\app.pbl.src\\w_main.srw", "bytes": 713}
  ],
  "skipped": [],
  "failed": []
}
```

`ok` is false when any entry failed; the rest still got written, and `failed`
carries one error envelope per entry.

---

## Library

### `pb_library_create(lib_path, comments="")`

Create an empty `.pbl` at `lib_path`. `comments` is the PBL-level comment.

### `pb_library_delete(lib_path)`

Deletes the PBL. Deliberately leaves the library's
`ws_objects/<lib>.pbl.src/` directory in place: dropping a tree of
version-controlled source as a side effect of one call is worse than leaving
an orphan, which `git status` shows you anyway.

Delete a `.pbl` from disk.

### `pb_library_directory(lib_path, entry_type="any")`

List entries in a PBL. ORCA returns every entry via callback; the
`entry_type` filter is applied client-side after collection. Valid filters
correspond to `PBORCA_TYPE` names: `application`, `datawindow`, `function`,
`menu`, `query`, `structure`, `userobject`, `window`, `pipeline`, `project`,
`proxyobject`, `binary`, plus `any`.

**Output**:
```json
{
  "lib_path": "foo.pbl",
  "lib_comment": "PBL-level comment",
  "entry_type": "userobject",
  "count": 12,
  "entries": [
    {
      "name": "n_cst_main",
      "type": "userobject",
      "size": 12450,
      "create_time": 1717245734,
      "comment": "main application service"
    }
  ]
}
```

### `pb_library_entry_information(lib_path, entry_name, entry_type)`

Metadata for a single entry.

**Output**:
```json
{
  "name": "n_cst_main",
  "type": "userobject",
  "object_size": 8920,
  "source_size": 12450,
  "create_time": 1717245734,
  "comment": "..."
}
```

### `pb_library_entry_export(lib_path, entry_name, entry_type)`

Export the source of an entry as a string, in memory. The wrapper auto-resizes
the buffer (64 KiB initial, retries on `PBORCA_BUFFERTOOSMALL`).

Returns the object **body**: no `$PBExportHeader$` line, no
`$PBExportComments$` line, because those belong to the on-disk file format
rather than to the object. Use `pb_object_export_file` when you want the file.

**Output**: `{"lib_path", "entry_name", "entry_type", "source": "<text>"}`.

### `pb_library_entry_delete(lib_path, entry_name, entry_type, sync_sources="auto")`

Remove a single entry from a PBL, and its text projection file with it. A
surviving `.sr*` would resurrect the object on the next Refresh, so the
default is to remove both; `sync_sources="never"` keeps the file.

**Output**: adds `{"removed_files": [...], "sync": "ok"}`.

### `pb_library_entry_move(source_lib, dest_lib, entry_name, entry_type, sync_sources="auto")`

Move an entry between PBLs. The projection follows: the `.sr*` is removed from
the source library's directory and written fresh into the destination's.

**Output**: adds `{"removed_files": [...], "synced_files": [...], "sync": "ok"}`.

### `pb_library_comment_modify(lib_path, comments)`

Update the PBL-level comment. **There is no per-entry comment-modify in
ORCA**: to change an entry's comment, re-import it via
`pb_compile_entry_import` with the new `comments` argument.

---

## Compile loop: the core agentic value

All compile/rebuild tools return `{"success": bool, "errors": [...]}`. The
`errors` array carries per-diagnostic dicts:

```json
{
  "level": 0,
  "level_name": "error",
  "message_number": "C0042",
  "message_text": "Undefined function: getfoo",
  "column": 8,
  "line": 142
}
```

`level_name` follows the convention `0=error / 1=warning / 2=information`
(the C header doesn't formalize this; raw `level` is always available).
`PBORCA_COMPERROR (-11)` and `PBORCA_LINKERROR (-12)` are **not** raised
as exceptions: they're normal "compile produced diagnostics" outcomes
and surface as `success: false` with populated `errors`.

### `pb_compile_entry_import(lib_path, entry_name, entry_type, syntax, comments="", sync_sources="auto")`

Compile + import a single entry's source into a PBL, from a string in memory.
`pb_object_import_file` is the better tool when the source is a file; use this
one for a small, surgical change you already hold.

`syntax` is the object's complete source. Any `$PBExportHeader$` /
`$PBExportComments$` lines it carries are **ignored** by ORCA, so a body
straight out of `pb_library_entry_export` and the full contents of a `.sr*`
file are both valid input. The object's comment comes from `comments`, never
from the source text.

On success the matching `ws_objects/` file is rewritten through ORCA when the
project keeps one, so the change is visible to git in both forms.

**Output**: adds `{"synced_files": [...], "sync": "ok"}`.

### `pb_compile_entry_import_list(items, sync_sources="auto")`

Batch version — ORCA compiles the whole list together and reuses parser state.
`items` is a list of dicts:

```json
[
  {
    "lib_path": "foo.pbl",
    "entry_name": "f_demo",
    "entry_type": "function",
    "syntax": "<text>",
    "comments": "optional"
  }
]
```

All diagnostics land in the single `errors` array; ORCA prefixes each
`message_text` with the object name as `"<entry>:<text>"`. The batch either
compiles or does not, so the projection is synced for every item only when the
whole batch succeeds.

### `pb_application_rebuild(rebuild_type="incremental")`

Full / incremental / migrate / 3-pass rebuild of the current application.
Valid `rebuild_type`: `"full"`, `"incremental"`, `"migrate"`, `"3pass"`.

Requires `pb_session_open` + `pb_set_library_list` + `pb_set_current_application`.

### `pb_get_last_compile_errors()`

Replay diagnostics from the most recent compile/rebuild call. Useful when
a caller discarded the originating response.

**Output**: `{"errors": [...]}` (empty list if no compile has run).

---

## Build artifacts

### `pb_executable_create(exe_name, *, icon_name=None, pbr_name=None, flags=None, pbd_flags=None, exe_info=None)`

Build a standalone `.exe` for the current application. Returns
`{"success", "exe_name", "errors": [...]}` with link errors when present.

`flags`: list of flag names OR-folded into `lFlags`:

| Flag name | `PBORCA_*` constant | Meaning |
|---|---|---|
| `machine_code` | `PBORCA_MACHINE_CODE` | Compile to machine code (default: p-code) |
| `optimize_speed` | `PBORCA_MACHINE_CODE_OPT_SPEED` | Optimize for speed (default: none) |
| `optimize_space` | `PBORCA_MACHINE_CODE_OPT_SPACE` | Optimize for size |
| `trace_info` | `PBORCA_TRACE_INFO` | Embed trace info |
| `error_context` | `PBORCA_ERROR_CONTEXT` | Embed runtime error context (line numbers) |
| `new_visual_style` | `PBORCA_NEW_VISUAL_STYLE_CONTROLS` | Use XP-and-later visual style controls |
| `x64` | `PBORCA_X64` | x64 deployment |

`pbd_flags`: list-of-lists of flag names, one inner list per non-application
PBL in the library list. When present, ORCA generates a `.pbd` per element.
`None` (default) skips PBD generation.

`exe_info`: optional dict for the EXE's Windows `VS_VERSION_INFO` resource:
`company_name`, `product_name`, `description`, `copyright`, `file_version`,
`file_version_num`, `product_version`, `product_version_num`, `manifest_info`.
Each populated value lands in the produced EXE; omitted keys are left
unset.

### `pb_dynamic_library_create(lib_path, *, pbr_name=None, flags=None)`

Build a single `.pbd` from a `.pbl`. No link callback (the C API doesn't
expose one for this entry point): failures surface as the raw ORCA return
code in an `error` envelope.

---

## Object queries

### `pb_object_query_hierarchy(lib_path, entry_name, entry_type)`

Walk the inheritance chain of an entry. Returns the ancestor list closest-
first, not including the entry itself.

**Output**: `{"lib_path", "entry_name", "entry_type", "ancestors": ["base", "nonvisualobject"]}`.

### `pb_object_query_reference(lib_path, entry_name, entry_type)`

List the entries that the named object references, its **outgoing**
dependencies (callees, ancestors used, types declared, windows opened,
etc.). This is the outgoing direction of the cross-reference graph;
ORCA does not expose an incoming-direction primitive, so finding
"who calls this entry" requires inverting the index by querying every
candidate caller in the library list.

**Output**:
```json
{
  "lib_path": "foo.pbl",
  "entry_name": "n_cst_lib",
  "entry_type": "userobject",
  "count": 5,
  "references": [
    {
      "library": "main.pbl",
      "entry_name": "w_main",
      "entry_type": "window",
      "ref_type": "open"
    }
  ]
}
```

`ref_type` is `"simple"` (declarative reference) or `"open"` (runtime open).

### `pb_object_regenerate(lib_path, entry_name, entry_type)`

Re-emit object code for a single entry, without touching its source. Same
response shape as the compile tools: `{"success", "errors", ...}`.

## SCC (offline "Refresh PBL")

The native equivalent of PB IDE's "Refresh PBL", for git/svn-managed
projects where `ws_objects/` is the source of truth and the `.pbl` is
derived. Offline mode reconciles add/modify/delete from `ws_objects/` into
the binary library without contacting a remote SCC provider. The usual call
order is `pb_scc_connect_offline` → `pb_scc_set_target` →
`pb_scc_refresh_target` → `pb_scc_close`; see [`recipes.md`](recipes.md) for the
full sequence and the git/svn caveats. Online connect, get-latest-version,
and revision operations are not exposed (they need a live MSSCCI provider).

### `pb_scc_connect_offline(workspace_file=None, *, local_proj_path=None, log_file=None, append_log=False, ...)`

Open an offline SCC connection. In offline mode only `local_proj_path`,
`log_file`, and `append_log` take effect; the other connection kwargs
(`provider_name`, `user_id`, `project`, `aux_path`, `comment_max_len`,
`delete_temp_files`, `delete_pbl_on_refresh`) are accepted for symmetry but
ignored by the SCC layer. `local_proj_path` must be the **parent of
`ws_objects/`**. If `workspace_file` is given and has an SCC block, its
values seed the config; a missing block (`PBORCA_REGREADERROR`, the normal
case on git/svn) is tolerated and the connection is built from the kwargs.
Returns `{"ok": true, ...}`.

### `pb_scc_set_target(target_file, flags=None)`

Bind the connection to a target (`.pbt`) and return the PBLs it manages.
`flags` is an optional list from `refresh_all`, `outofdate`, `importonly`,
`exclude_checkout` (default: none). **Side effect**: this also sets the
session's library list and current application, so a later
`pb_set_library_list` / `pb_set_current_application` returns
`PBORCA_DUPOPERATION (-2)`; skip them in the SCC flow. Returns
`{"ok", "target_file", "flags", "count", "libraries"}`.

### `pb_scc_refresh_target(rebuild_type="incremental")`

Refresh the target's PBLs from `ws_objects/` (the "Refresh PBL" itself):
add, modify, and delete entries to match the directory. `rebuild_type` is
one of `"incremental"` (default), `"full"`, `"migrate"`, `"3pass"`. Returns
`{"ok", "rebuild_type"}`; compile diagnostics surface through
`pb_get_last_compile_errors`.

Two things to expect. It operates on the whole tree at once, so a single
malformed file fails the batch with no per-object diagnostic — for one object,
`pb_object_import_file` is both quieter and better at reporting errors. And it
writes a flat `.sr*` export plus a `.pbg` registry file into `local_proj_path`
as a side effect, which shows up as untracked noise in a git repo. Check
`git status` after running it.

### `pb_scc_exclude_library_list(lib_names)`

Exclude specific PBLs (by name) from SCC management for the current target,
e.g. vendored `.pbd` snapshots you don't want refreshed. Returns
`{"ok", "count", "libraries"}`.

### `pb_scc_get_connect_properties(workspace_file)`

Read the SCC connection block from a `.pbw` (read-only; opens no
connection). Returns the block's fields (`provider_name`, `user_id`,
`project`, `local_proj_path`, `aux_path`, `log_file`, `capabilities`, …). On
a git/svn workspace with no SCC block this returns `PBORCA_REGREADERROR
(-23)`, which is expected; `pb_scc_connect_offline` tolerates it.

### `pb_scc_close()`

Close the SCC connection. No-op when not connected. Returns `{"ok": true}`.

---

## Error name reference

`PB_ORCA_MCP_*` codes (from the server wrapper):

| Name | Meaning |
| --- | --- |
| `PB_ORCA_MCP_INVALIDARGS` | Caller-supplied argument failed validation |
| `PB_ORCA_MCP_STATEERROR` | Operation requires (or forbids) an open session, or the session configuration would corrupt the transfer |
| `PB_ORCA_MCP_IOERROR` | A source file could not be read or a directory could not be created |
| `PB_ORCA_MCP_WORKSPACEERROR` | The workspace layout around a `.pbl` could not be resolved |
| `PB_ORCA_MCP_VERSIONNOTFOUND` | No PB install with the requested `pb_version` |
| `PB_ORCA_MCP_VERSIONAMBIGUOUS` | Multiple installs share a major: pass `install_path` |
| `PB_ORCA_MCP_INSTALLNOTFOUND` | `install_path` didn't match a discovered install |
| `PB_ORCA_MCP_LOADFAILED` | `WinDLL` refused to load `pborc.dll` |

`PBORCA_*` codes (passed through from the ORCA C API): see
`PBORCA.H` in your PB SDK or `src/pb_orca_mcp/orca/constants.py` for the
full list (`PBORCA_OK = 0` and 33 negative codes).
