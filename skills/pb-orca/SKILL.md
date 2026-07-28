---
name: pb-orca
description: Use this when driving PowerBuilder through the pb-orca MCP server: opening an ORCA session and inspecting PBLs, exporting an object to a file and importing it back, rebuilding targets, building EXE/PBD, or querying object hierarchy and references. Covers the session lifecycle, the export→edit→import loop, and the ORCA gotchas (single session per process, IDE locks, x86/x64). For what to commit on a project that keeps ws_objects/ text sources, see the pb-workflow skill.
metadata:
  version: "0.2.0"
---

# Driving PowerBuilder with pb-orca

`pb-orca` exposes PowerBuilder's ORCA API as MCP tools. With it you do
headless what the PB IDE does interactively: inspect libraries, compile,
rebuild, build EXE/PBD, and walk inheritance and reference graphs. That closes
the **edit → compile → read errors → fix** loop on a language whose only
editor is a GUI.

You are, in effect, the IDE without a window. ORCA is **single-session per
process**: open one session, do the work, close it.

You do not need to know PowerScript syntax to use this. The server hands you a
source file, you edit it as text, you hand it back, and the compiler tells you
what it thinks.

## Session lifecycle: the fixed order

1. `pb_session_open` — pick the install with `pb_version` (e.g. `"22.0"`) or
   `install_path`. There is no auto-pick: `.pbt`/`.pbw` files do not record
   which PowerBuilder release built them.
2. `pb_set_library_list` — the `.pbl` search list, absolute paths. The `.pbt`
   carries it; read it with `pb_target_info`.
3. `pb_set_current_application` — required before any **compile**, **rebuild**
   or **object-query** call. May rewrite the `.pbw` as a side effect, so check
   `git status` afterwards and revert it unless you changed the target list.
4. …do the work…
5. `pb_session_close`.

Switching PB version means close + reopen: a process can only hold one PB
runtime.

## The edit loop

Three calls, and they work the same whether or not the project keeps text
sources — the destination changes, your steps do not.

```text
pb_object_export_file(lib, entry, type)   -> writes <entry>.<ext>, returns its path
   (you edit that file with ordinary file tools)
pb_object_import_file(path, lib)          -> compiles it into the .pbl
```

- The file ORCA writes is byte-identical to what the PB IDE writes: export
  header, comment line, BOM, CRLF. You never construct those bytes yourself.
- `entry_name`, `entry_type` and the object comment are inferred from the file,
  so a round trip needs no extra arguments.
- On a compile error you get `success: false` and structured diagnostics
  (`message_number`, `message_text`, `line`, `column`). Fix the file and call
  `pb_object_import_file` again. Note that ORCA still writes the partial source
  into the `.pbl` on a failed import, so re-import the whole corrected file
  rather than assuming the entry was left untouched.
- **Do not normalize line endings.** PowerBuilder stores CRLF. An editor that
  writes LF turns the next import into a whole-file rewrite.
- To create an object, write a complete source file and import it under a name
  that does not exist yet. The quickest correct skeleton is an export of a
  similar object, renamed and adapted.

`pb_compile_entry_import` takes the source as a string instead of a file. Use
it for a small, surgical change; the file pair is better for anything you would
not want to re-emit in full through a tool argument.

## Understanding a codebase you have not seen

- `pb_workspace_info` — first call on an unfamiliar project: does it keep text
  sources, where, in which encoding, is git watching.
- `pb_library_directory` — the entries in a `.pbl`.
- `pb_library_export_sources` — the whole library as text files in one call.
  Also the way to bootstrap a `ws_objects/` tree on a binary-only project.
- `pb_object_query_hierarchy` — the ancestor chain.
- `pb_object_query_reference` — what an object calls or uses. Outgoing only;
  ORCA has no "who calls this" primitive.
- `pb_library_entry_export` — the source as a string, in memory. Returns the
  **body**: no `$PBExportHeader$` line, since that belongs to the file format.

## Validate and build

- `pb_application_rebuild` — `incremental` (default), `full`, `migrate`,
  `3pass`. Run it after a change that crosses objects to catch cascading
  breakage.
- `pb_executable_create` / `pb_dynamic_library_create` — EXE and PBD.
- `pb_scc_refresh_target` — the native "Refresh PBL": reconciles a whole
  `ws_objects/` tree into the `.pbl` after a merge or a branch switch. Two
  things to know: `pb_scc_set_target` already sets the library list and current
  application, so calling `pb_set_library_list` /
  `pb_set_current_application` again returns `PBORCA_DUPOPERATION (-2)`; and
  the refresh also drops a flat export plus a `.pbg` into the project root, so
  check `git status` afterwards. For a single object, the import loop is both
  quieter and better at reporting errors.

## Gotchas that bite

- **Close the PB IDE first.** It holds an exclusive lock on the `.pbl` and ORCA
  writes fail with `PBORCA_LIBIOERROR`. Work on a closed library or a copy.
- **x86 vs x64.** The Python running the server must match the `pborc.dll`
  arch. PB IDE is x86 through 2025, so it usually needs an x86 interpreter.
  `pb-orca-mcp doctor` confirms this.
- **Errors are data, not exceptions.** A failed compile returns
  `success: false` with populated `errors`; only genuine ORCA faults come back
  as an `error` envelope.
- **Style is not this server's job.** It imports what you give it, byte for
  byte, and does not normalize indentation or keyword case. Run a formatter
  before importing if that matters to you.
- **`pb_session_configure` is a loaded gun.** The file tools manage the session
  configuration themselves. Setting a non-Unicode export encoding by hand
  makes in-memory exports come back mangled; the server refuses those calls
  rather than returning plausible garbage.

## When to reach for pb-workflow

The moment you are on a project that keeps `ws_objects/` text sources and you
need to know **what to commit**, switch to the `pb-workflow` skill. This skill
is the engine; that one is the source-of-truth discipline.

## Reference

Full tool schemas: `docs/tools.md`. The model everything derives from:
`docs/how-it-works.md`. Recipes: `docs/recipes.md`.
