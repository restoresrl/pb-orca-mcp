# Recipes

Concrete tool-call sequences for driving PowerBuilder with `pb-orca-mcp` —
the patterns an assistant follows when given a task like "fix the compile error
in `n_cst_main`". Useful to read if you want to know what your assistant is
doing, and to copy from if you are scripting against the tools yourself.

Read [`how-it-works.md`](how-it-works.md) first if you have not: it explains
the `.pbl` / `ws_objects/` model these recipes assume, and the one silent
failure mode worth understanding before your first write. For the full schema
of every tool see [`tools.md`](tools.md); to install and connect a client, see
[`getting-started.md`](getting-started.md).

---

## Session bootstrap

Every session starts the same way; the recipes below assume it is done.

```jsonc
// 1. Pick the PB install. There is no auto-pick: .pbt/.pbw files do not
//    record which PowerBuilder release built them.
{"tool": "pb_session_open", "args": {"pb_version": "22.0"}}

// 2. Set the library list. pb_target_info reads it out of a .pbt for you.
{"tool": "pb_set_library_list", "args": {
  "libraries": ["C:\\proj\\myapp.pbl", "C:\\proj\\dep\\corelib.pbl"]
}}

// 3. Pick the application object. Required before any compile, rebuild or
//    object-query call.
{"tool": "pb_set_current_application", "args": {
  "app_lib": "C:\\proj\\myapp.pbl", "app_name": "myapp"
}}

// At the end
{"tool": "pb_session_close"}
```

On an unfamiliar project, call `pb_workspace_info` first. It needs no session
and tells you which shape of project you are in:

```jsonc
{"tool": "pb_workspace_info", "args": {"lib_path": "C:\\proj\\myapp.pbl"}}
// → {"mode": "ws_objects", "sources": {"source_dir": "...", "exists": true},
//    "orca_encoding": "utf8", "git_root": "C:\\proj", "work_dir": "C:\\proj\\.pb-orca", ...}
```

---

## Recipe 1: the edit loop

The inner loop of agentic PB development. Identical on a project with a
`ws_objects/` text projection and on a binary-only one — only the destination
of step 1 differs, and it is detected for you.

```jsonc
// Step 1: write the object's source to a file.
{"tool": "pb_object_export_file", "args": {
  "lib_path": "C:\\proj\\myapp.pbl",
  "entry_name": "f_compute_total",
  "entry_type": "function"
}}
// → {"file_path": "C:\\proj\\ws_objects\\myapp.pbl.src\\f_compute_total.srf",
//    "encoding": "utf8", "mode": "ws_objects", "is_source_of_truth": true}
//
// On a project with no projection the path would be
// "C:\\proj\\.pb-orca\\f_compute_total.srf" and is_source_of_truth false.
// ORCA writes the file: export header, comment line, BOM, CRLF — byte-identical
// to what the PB IDE writes on Save. Running this on an unchanged object
// reproduces the same bytes, so git stays quiet.
```

Step 2: edit `file_path` with your ordinary file tools. Do not let the editor
normalize line endings — PowerBuilder stores CRLF.

```jsonc
// Step 3: import it back.
{"tool": "pb_object_import_file", "args": {
  "file_path": "C:\\proj\\ws_objects\\myapp.pbl.src\\f_compute_total.srf",
  "lib_path": "C:\\proj\\myapp.pbl"
}}

// → happy path
// {"success": true, "entry_name": "f_compute_total", "entry_type": "function",
//  "errors": [], "synced_files": ["...f_compute_total.srf"], "sync": "ok"}

// → diagnostics path
// {"success": false, "errors": [
//    {"level": 0, "level_name": "error", "message_number": "C0042",
//     "message_text": "Undefined function: getfoo", "column": 8, "line": 142}
//  ], "synced_files": []}
```

`entry_name`, `entry_type` and the object comment come from the file, so no
extra arguments are needed. On `success: false` correlate `message_text` and
`line` with the source you submitted, fix the file, and import again — ORCA may
have written partial source into the `.pbl`, so re-import the whole corrected
file.

On success, when the project keeps a text projection, `synced_files` lists what
ORCA rewrote so the text on disk matches the `.pbl` exactly. That is the half
of the change git can review.

### The in-memory variant

For a small change you already hold as a string, skip the file:

```jsonc
{"tool": "pb_library_entry_export", "args": {
  "lib_path": "C:\\proj\\myapp.pbl", "entry_name": "f_compute_total",
  "entry_type": "function"}}
// → {"source": "global type f_compute_total ...\r\n..."}   (the body; no header line)

{"tool": "pb_compile_entry_import", "args": {
  "lib_path": "C:\\proj\\myapp.pbl", "entry_name": "f_compute_total",
  "entry_type": "function", "syntax": "<edited source>",
  "comments": "fixed null dereference"}}
// → {"success": true, "synced_files": [...], "sync": "ok"}
```

ORCA ignores any `$PBExportHeader$` / `$PBExportComments$` lines in `syntax`,
so an exported body and a whole file are both valid input. The object's comment
comes from `comments`. The projection is synced here too.

---

## Recipe 2: create a new object

Write a complete source file under a name that does not exist yet and import
it. The entry is created.

```jsonc
// Fastest correct skeleton: export a similar object, save it under the new
// name, adapt it. Then:
{"tool": "pb_object_import_file", "args": {
  "file_path": "C:\\proj\\ws_objects\\myapp.pbl.src\\n_order.sru",
  "lib_path": "C:\\proj\\myapp.pbl",
  "comments": "Order aggregate"
}}
```

No `$PBExportHeader$` line is needed in the file — import ignores it. The
`comments` value becomes the `$PBExportComments$` line ORCA writes back out, so
give it something meaningful. On a project with a projection the new `.sr*` is
untracked afterwards, so `git add` it.

---

## Recipe 3: delete or move an object

```jsonc
{"tool": "pb_library_entry_delete", "args": {
  "lib_path": "C:\\proj\\myapp.pbl", "entry_name": "w_obsolete",
  "entry_type": "window"}}
// → {"ok": true, "removed_files": ["...\\ws_objects\\myapp.pbl.src\\w_obsolete.srw"]}

{"tool": "pb_library_entry_move", "args": {
  "source_lib": "C:\\proj\\myapp.pbl", "dest_lib": "C:\\proj\\dep\\corelib.pbl",
  "entry_name": "f_split", "entry_type": "function"}}
// → {"ok": true, "removed_files": [...], "synced_files": [...]}
```

The text file follows the object in both cases. Leaving a `.sr*` behind after a
delete is not cosmetic: the next Refresh would read it back and resurrect the
object.

---

## Recipe 4: batch import a set of entries

Faster than looping: ORCA compiles the whole list as one batch, reusing parser
state.

```jsonc
{"tool": "pb_compile_entry_import_list", "args": {
  "items": [
    {"lib_path": "C:\\proj\\dep\\corelib.pbl", "entry_name": "f_split",
     "entry_type": "function", "syntax": "<edited source>"},
    {"lib_path": "C:\\proj\\dep\\corelib.pbl", "entry_name": "f_join",
     "entry_type": "function", "syntax": "<edited source>"}
  ]
}}
```

All diagnostics land in the single `errors` array; to pin which error belongs to
which entry, read `message_text` — ORCA prefixes it with the object name as
`"<entry>:<text>"`. The batch either compiles or does not, so the projection is
synced for every item only when the whole batch succeeds.

---

## Recipe 5: rebuild after a wide refactor

When edits cross many entries, rebuild the whole application in one call
instead of trusting entry-by-entry imports:

```jsonc
{"tool": "pb_application_rebuild", "args": {"rebuild_type": "full"}}
```

`rebuild_type`: `"incremental"` (default, only what changed), `"full"`
(re-compile every entry), `"migrate"` (migrate-from-older-PB pass), `"3pass"`
(slowest, most thorough). Response: `{"success", "errors": [...]}`.

---

## Recipe 6: build a `.exe`

After the rebuild is clean:

```jsonc
{"tool": "pb_executable_create", "args": {
  "exe_name": "C:\\proj\\dist\\myapp.exe",
  "icon_name": "C:\\proj\\res\\myapp.ico",
  "pbr_name": "C:\\proj\\res\\myapp.pbr",
  "flags": ["machine_code", "optimize_speed", "error_context"],
  "pbd_flags": [
    ["machine_code", "optimize_speed"],   // first non-app PBL → .pbd
    ["machine_code"]                       // second non-app PBL → .pbd
  ],
  "exe_info": {
    "company_name": "Acme Corp", "product_name": "MyApp",
    "file_version": "1.4.2", "file_version_num": "1.4.2.0",
    "product_version": "1.4.2", "product_version_num": "1.4.2.0",
    "copyright": "(c) 2026 Acme Corp"
  }
}}
```

Returns `{"success", "exe_name", "errors": [...]}`. Link errors (unresolved
externals, duplicate definitions) land in `errors` with just `message_text`:
`PBORCA_LNKPROC` is intentionally less rich than `PBORCA_ERRPROC`, with no line
or column for the linker.

For a quick "does it link" run, drop the dressing:

```jsonc
{"tool": "pb_executable_create", "args": {
  "exe_name": "C:\\proj\\dist\\myapp.exe", "flags": ["machine_code"]}}
```

P-code is the default and is the right choice for the inner loop, where build
time matters more than runtime speed.

---

## Recipe 7: build a single `.pbd` for vendoring

When a downstream consumer pulls a compiled snapshot of a library:

```jsonc
{"tool": "pb_dynamic_library_create", "args": {
  "lib_path": "C:\\proj\\dep\\corelib.pbl",
  "flags": ["machine_code", "optimize_speed"]}}
// → produces corelib.pbd next to corelib.pbl
```

---

## Recipe 8: read a whole library as text

One call, and the library is grep-able:

```jsonc
{"tool": "pb_library_export_sources", "args": {
  "lib_path": "C:\\proj\\myapp.pbl",
  "dest_dir": "C:\\scratch\\myapp-sources"}}
// → {"count": 214, "written": [{"entry_name": "...", "file_path": "..."}, ...]}
```

Omit `dest_dir` and it writes into the library's projection directory instead —
which is how you **bootstrap** `ws_objects/` on a project that only ever had
the binary. Commit the result and opaque binary commits become reviewable
diffs; from then on follow the Case B rules in
[`how-it-works.md`](how-it-works.md).

---

## Recipe 9: hierarchy walk

List every ancestor of a user object up to the root PB class:

```jsonc
{"tool": "pb_object_query_hierarchy", "args": {
  "lib_path": "C:\\proj\\myapp.pbl",
  "entry_name": "n_cst_payment_processor",
  "entry_type": "userobject"}}
// → {"ancestors": ["n_cst_payment_base", "n_cst_service_base", "nonvisualobject"]}
```

Closest ancestor first. Useful before editing: export the ancestors too, to
understand the inherited surface.

---

## Recipe 10: "what does this call?"

Before refactoring an entry, list everything it depends on:

```jsonc
{"tool": "pb_object_query_reference", "args": {
  "lib_path": "C:\\proj\\myapp.pbl", "entry_name": "w_main", "entry_type": "window"}}
// → {"count": 7, "references": [
//      {"library": "...corelib.pbl", "entry_name": "f_legacy_thing",
//       "entry_type": "function", "ref_type": "simple"}, ...]}
```

`ref_type` is `"simple"` (declarative: call, type declaration) or `"open"`
(runtime `Open`/`OpenWithParm` of a window). **Direction**: ORCA returns
*outgoing* references — what the object uses, not what uses it. There is no
native primitive for the incoming direction; reconstructing it means iterating
every candidate caller and inverting.

---

## Recipe 11: regenerate one descendant after touching its ancestor

Re-emit an object's machine code without changing its source:

```jsonc
{"tool": "pb_object_regenerate", "args": {
  "lib_path": "C:\\proj\\myapp.pbl",
  "entry_name": "n_cst_payment_processor", "entry_type": "userobject"}}
```

Cheaper than a full `pb_application_rebuild` when you know exactly which
descendant needs re-emitting. It does not touch the text file: there is no
source change to project.

---

## Recipe 12: reconcile a whole tree after a merge

After a git merge that touched `ws_objects/`, or a branch switch, the `.pbl` is
behind the text tree. `pb_scc_refresh_target` is the native "Refresh PBL" and
reconciles everything — add, modify, delete — in one sequence. `local_proj_path`
must be the **parent of `ws_objects/`**.

```jsonc
{"tool": "pb_session_open",        "args": {"pb_version": "22.0"}}
{"tool": "pb_scc_connect_offline", "args": {
    "workspace_file": "C:\\proj\\myproj.pbw", "local_proj_path": "C:\\proj"}}
{"tool": "pb_scc_set_target", "args": {
    "target_file": "C:\\proj\\myapp.pbt", "flags": ["refresh_all", "importonly"]}}
{"tool": "pb_scc_refresh_target", "args": {"rebuild_type": "incremental"}}
{"tool": "pb_scc_close",    "args": {}}
{"tool": "pb_session_close","args": {}}
```

Caveats, all expected:

- `importonly` is **required** in offline mode, and it goes in
  `pb_scc_set_target`'s `flags`, not in the refresh call. Without it the
  connect fails with `PBORCA_IMPORTONLY_REQ`.
- `pb_scc_set_target` **also sets the library list and current application**, so
  a later `pb_set_library_list` / `pb_set_current_application` returns
  `PBORCA_DUPOPERATION (-2)`. Skip them; go straight to the refresh.
- The refresh writes a flat `.sr*` export plus a `.pbg` file into
  `local_proj_path`. Check `git status` afterwards and clean up what you did
  not want.
- It reports no per-object diagnostics: one malformed file fails the batch.
  For a single object, Recipe 1 is better.
- `pb_scc_get_connect_properties` always returns `PBORCA_REGREADERROR (-23)` on
  a git/svn workspace (no SCC block in the `.pbw`);
  `pb_scc_connect_offline` tolerates it and proceeds.
- `scc get latest version` and remote SCC server connections do not work with
  git/svn by design. Use the git CLI.

---

## Anti-recipe: do not replace your batch build pipeline

If you already have a working batch build (OrcaScript or a custom
`build.bat`), keep it. `pb-orca-mcp` is an interactive development tool for an
agent's inner loop, not a tagged-release build runner:

- The MCP server runs in the same process tree as the client that launched it;
  an unhandled crash takes the agent session down. CI wants process isolation
  and retry.
- The library list is per-session in memory; a release build wants reproducible
  config files.
- ORCA is single-session-per-process; parallel CI builds hit that wall.

Use this for editing; keep OrcaScript and batch scripts for releases.

## Anti-recipe: do not touch PBLs the PB IDE has open

If the IDE is open on the same PBL, ORCA writes fail with
`PBORCA_LIBIOERROR`. ORCA respects the IDE's file locks but does not queue
around them. Close the IDE, or work on a copy, before any call that writes.

## Anti-recipe: do not hand-write a `.sr*` file

Let `pb_object_export_file` produce it. Getting the BOM, the CRLF and the
encoding right by hand is possible and pointless, and getting it wrong produces
a file that imports fine and then breaks the IDE's Refresh in a way that is
hard to trace. See [`how-it-works.md`](how-it-works.md) §5.
