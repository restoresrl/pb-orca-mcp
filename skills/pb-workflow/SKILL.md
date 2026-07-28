---
name: pb-workflow
description: Use this when modifying PowerBuilder objects on a project that keeps ws_objects/ text sources, or when deciding what to commit after a pb-orca session. Covers the two project shapes (ws_objects/ text projection vs binary-only .pbl), which form is the source of truth, what the server syncs for you and what it does not, and the integrity check for add/delete operations.
metadata:
  version: "0.2.0"
---

# What to commit after changing a PowerBuilder object

A PowerBuilder object lives in up to two forms, and the whole discipline here
is about keeping them from drifting apart.

- The **`.pbl`** (binary) holds the source *and* the compiled p-code. It is
  what the IDE and the running `.exe` read. Every project has one.
- **`ws_objects/<lib>.pbl.src/<entry>.<ext>`** (text) is a diff-friendly
  projection of the same source, one file per object. It exists only when the
  workspace was put under source control inside the PB IDE, because git cannot
  usefully merge a binary library.

## Which shape is this project?

Ask `pb_workspace_info(lib_path)`. It answers in one call.

| | `mode: "pbl_only"` | `mode: "ws_objects"` |
| --- | --- | --- |
| Source of truth | the `.pbl` | the text files |
| The `.pbl` is | everything | the derived, built form |
| You edit | a working file under `.pb-orca/` | the `.sr*` file itself |
| You commit | the `.pbl`, if it is tracked | the `.sr*` files, and the `.pbl` if the project tracks it |
| ORCA calls | identical | identical |

That last row is the point: **ORCA behaves the same either way.** It always
reads and writes the `.pbl`. The projection only changes what else has to
happen, and the server does that part for you.

## What the server guarantees

Every tool that writes to a `.pbl` — `pb_object_import_file`,
`pb_compile_entry_import` and its list form, `pb_library_entry_delete`,
`pb_library_entry_move` — also updates the matching text file when the project
has a projection. The response tells you exactly what it touched:

```json
{"success": true, "synced_files": ["...\\ws_objects\\app.pbl.src\\w_main.srw"], "sync": "ok"}
```

`sync` values: `ok` (written), `not_applicable` (no projection to update),
`never` (you passed `sync_sources="never"`), `failed` (with `sync_error`).

Because ORCA writes that file, re-exporting an object you did not change
produces the same bytes and leaves `git status` clean. A phantom-diff cascade
is not something you have to steer around.

## What it does not do

- **It does not commit.** Look at `git status` and stage deliberately.
- **It does not decide whether the `.pbl` is tracked.** Some projects commit
  the binary next to the text; others treat it as a build artifact and let the
  build regenerate it from `ws_objects/`. Both are valid. Follow whatever the
  repository already does — `git status` shows you which.
- **It does not sync a failed compile.** If the import returns
  `success: false`, the text file is left exactly as you wrote it so you can
  fix and retry, and nothing was mirrored.
- **It does not touch the `.pbg`.** Some workspaces keep one listing which
  object belongs to which library. ORCA does not manage it; if your project has
  one and you add or remove objects, check whether it needs updating.

## The rules that still matter

- **Never edit a `ws_objects/` file and stop there.** The build reads the
  `.pbl`. Text-only changes produce a commit that reviews clean and builds
  stale. Always import.
- **Never hand-write a `.sr*` file.** Let `pb_object_export_file` produce it.
  A file whose encoding does not match the workspace's `DefaultExportEncode`,
  or whose CRLF became LF, breaks the IDE's Refresh in confusing ways.
- **Never let an editor normalize line endings** on these files.
- **Close the PB IDE** before writing: it locks the `.pbl`.
- **Check the `.pbw`** after a session. `pb_set_current_application` may
  rewrite it non-deterministically; revert it unless you actually added or
  removed a target.
- **The IDE overwrites `ws_objects/` on Save.** If you edited a file externally
  and then open that object in the IDE without running Refresh PBL first, the
  IDE regenerates the text from the (stale) `.pbl` and your edit is gone.

## Adding and deleting objects

Deletes and moves are synced for you, so the usual case needs no extra work.
Run an integrity check when something outside the server touched the tree — a
merge, a branch switch, a hand-edited directory:

1. `pb_library_directory` → what the `.pbl` holds.
2. List the files in `ws_objects/<lib>.pbl.src/`.
3. In the `.pbl` but not in the text tree → `pb_library_entry_delete`.
4. In the text tree but not in the `.pbl` → `pb_object_import_file`.

For a whole tree at once — after a merge, say — `pb_scc_refresh_target` is the
native "Refresh PBL" and reconciles everything in one call. It reports no
per-object diagnostics, and it drops a flat export plus a `.pbg` into the
project root, so check `git status` afterwards.

## Turning a binary-only project into a reviewable one

`pb_library_export_sources(lib_path)` writes every object in the library out as
text, into the projection directory. Commit the result and the project is a
`ws_objects` project from then on: opaque binary commits become readable diffs.

## Reference

The full model, with the verified ORCA behaviour behind it:
`docs/how-it-works.md`. Tool schemas: `docs/tools.md`.
