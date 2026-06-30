---
name: pb-orca
description: Use this when driving PowerBuilder through the pb-orca MCP server — opening an ORCA session and inspecting PBLs, compiling/importing entries, rebuilding targets, building EXE/PBD, or querying object hierarchy and references. Covers the session lifecycle, the edit→compile→fix loop, and the ORCA gotchas (single session per process, IDE locks, the export-header requirement, x86/x64). For the .pbl↔ws_objects source-of-truth editing model specifically, see the pb-workflow skill.
metadata:
  version: "0.1.0"
---

# Driving PowerBuilder with pb-orca

`pb-orca` exposes PowerBuilder's ORCA API as MCP tools. With it you can do
headless what the PB IDE does interactively: inspect libraries, compile,
rebuild, build EXE/PBD, and walk inheritance/reference graphs — closing
the **edit → compile → read errors → fix** loop on PB.

You are, in effect, the IDE without a window. ORCA is **single-session
per process**: open one session, do the work, close it.

## Session lifecycle — the fixed order

Most tools need a configured session. The order matters:

1. `pb_session_open` — pick the install with `pb_version` (e.g. `"22.0"`)
   or `install_path`. There is no auto-pick.
2. `pb_set_library_list` — the `.pbl` search list (absolute paths). The
   `.pbt` carries it; read it with `pb_target_info` if you have a target.
3. `pb_set_current_application` — required before any **compile**,
   **rebuild**, or **object-query** call. **May rewrite the `.pbw`** as a
   side effect — revert it afterwards unless you changed the target list.
4. ... do the work ...
5. `pb_session_close`.

Switching PB version = close + reopen (a process holds one PB runtime).

## The four phases

**1. Understand** — map a codebase you don't know:
- `pb_library_directory` — entries in a `.pbl` (name, type, comment).
- `pb_library_entry_export` — an object's source. **Returns the body
  only**, without the `$PBExportHeader$` line.
- `pb_object_query_hierarchy` — ancestor chain.
- `pb_object_query_reference` — what an object calls/uses (outgoing refs).

**2. Change and validate — the core loop:**
- `pb_compile_entry_import` — import + compile one entry's source into the
  `.pbl`. Returns `{"success", "errors": [...]}` with structured
  diagnostics (`object`, `line`, `column`, `message`). Read them, fix the
  source, re-import. **The `syntax` you pass MUST start with
  `$PBExportHeader$<entry_name>.<ext>` on line 1** — export strips it but
  import requires it, so re-prepend it (this is the export/import
  asymmetry).
- `pb_compile_entry_import_list` — batch variant.
- `pb_get_last_compile_errors` — replay the last diagnostics.

**3. Validate broadly:**
- `pb_application_rebuild` — `full` / `incremental` / `migrate` / `3pass`
  rebuild of the current application. Needs steps 1–3 of the lifecycle done.

**4. Build / sync:**
- `pb_executable_create` / `pb_dynamic_library_create` — EXE / PBD.
- `pb_scc_refresh_target` — on git projects, sync `ws_objects/` → `.pbl`
  (the native "Refresh PBL"). Note: `pb_scc_set_target` already sets the
  library list and current application, so **don't** call
  `pb_set_library_list` / `pb_set_current_application` again in the SCC
  flow — they return `PBORCA_DUPOPERATION (-2)`.

## Gotchas that bite

- **Close the PB IDE first.** If the IDE holds the `.pbl` open, write
  calls fail with a lock error. Work on a closed library.
- **`compile_entry_import` writes only the `.pbl`**, not the on-disk
  `.sr*`. On git projects you keep the `ws_objects/` source file in sync
  yourself (see the `pb-workflow` skill).
- **x86 vs x64.** The Python running the server must match the
  `pborc.dll` arch. PB IDE is x86 through 2025, so it usually needs x86
  Python. `pb-orca-mcp doctor` confirms this.
- **Errors are data, not exceptions.** A failed compile returns
  `success: false` with populated `errors`; only genuine ORCA faults
  come back as an `error` envelope.
- **Style is not this server's job.** It imports `syntax` byte for byte and
  won't normalize indent / keyword case / operator spacing. If that matters,
  run a separate formatter over the `.sr*` before importing. pb-orca reads
  and writes through ORCA, nothing more.

## When to reach for pb-workflow

The moment you **edit an object on a git-managed project** (where
`ws_objects/<lib>.pbl.src/<entry>.<ext>` is the source of truth and must
stay consistent with the `.pbl`), switch to the **`pb-workflow`** skill —
it covers which form is canonical, how to propagate edits in both
directions, and the integrity check for add/delete operations. This skill
is the engine overview; `pb-workflow` is the editing discipline.

## Reference

Full tool schemas: `docs/tools.md`. End-to-end recipes + the editing
model: `docs/usage.md`. The human-facing overview is the "How it works"
section of the README.
