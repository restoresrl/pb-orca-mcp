# Recipes

End-to-end agentic workflows that combine multiple `pb_*` tools. Each
recipe shows the JSON tool-call sequence with notes on why each step is
required. These are the patterns Claude Code will follow when given a
high-level task like "fix the compile error in `n_cst_main`".

The bootstrap of every session is the same:

```jsonc
// 1. Pick the PB install
{"tool": "pb_session_open", "args": {"pb_version": "22.0"}}

// 2. Set the library list — required before set_current_application
{"tool": "pb_set_library_list", "args": {
  "libraries": [
    "C:\\proj\\myapp.pbl",
    "C:\\proj\\dep\\corelib.pbl"
  ]
}}

// 3. Pick the application object
{"tool": "pb_set_current_application", "args": {
  "app_lib": "C:\\proj\\myapp.pbl",
  "app_name": "myapp"
}}

// At the end of the session
{"tool": "pb_session_close"}
```

Each subsequent recipe assumes that bootstrap is already done.

---

## Recipe 1 — Compile-test loop

The inner loop of agentic PB development: an entry is broken, the agent
edits the source, re-imports it, reads the compile errors, and iterates.

**Note — keeping the on-disk `.sr*` in sync.** This recipe imports from
memory into the `.pbl`; it does not write the `ws_objects/<...>.sr*`
file. When the workspace is the SOT and you need both updated, write the
SOT file first with the standalone `pb-format` tool (it gets the export
header + encoding/BOM right), then import — see Recipe 1.5.

```jsonc
// Step 1: read the current source
{"tool": "pb_library_entry_export", "args": {
  "lib_path": "C:\\proj\\myapp.pbl",
  "entry_name": "f_compute_total",
  "entry_type": "function"
}}
// → {"source": "global type f_compute_total ...\n..."}
//   NOTE — asymmetry vs Step 3 below: `source` is the **body only**.
//   The first line is NOT a `$PBExportHeader$` line. The on-disk export
//   produced by PB IDE *does* start with `$PBExportHeader$<name>.<ext>`,
//   but `library_entry_export` strips it. See memory pb-source-export-format.

// Step 2: the agent edits `source` (outside MCP) to fix a bug

// Step 3: re-import the edited source
//   IMPORTANT: `compile_entry_import` REQUIRES the `$PBExportHeader$` line
//   as the first line of `syntax`. For a direct export→import round-trip
//   you must re-prepend it manually:
//     syntax = "$PBExportHeader$f_compute_total.srf\r\n" + edited_source
//   Without this the import returns an error before reaching the compiler.
{"tool": "pb_compile_entry_import", "args": {
  "lib_path": "C:\\proj\\myapp.pbl",
  "entry_name": "f_compute_total",
  "entry_type": "function",
  "syntax": "$PBExportHeader$f_compute_total.srf\r\n<edited source text>",
  "comments": "fixed null-dereference in line 142"
}}

// → {"success": true, "errors": []}                  // happy path
// → {"success": false, "errors": [                   // diagnostics path
//      {"level": 0, "level_name": "error",
//       "message_number": "C0042",
//       "message_text": "Undefined function: getfoo",
//       "column": 8, "line": 142}
//    ]}
```

When `success: false`, the `errors` array carries the same diagnostics the
PB IDE would show — line/column included. The agent can correlate
`message_text` and `line` with the source it just submitted and iterate.

---

## Recipe 1.5 — Write the source-of-truth file, then import

When `ws_objects/<lib>.pbl.src/<entry_name>.<ext>` is the source of
truth, you want **two** effects: the on-disk `.sr*` updated *and* the
`.pbl` re-imported. `pb-orca-mcp` only does the second — it is a pure
ORCA bridge and never writes a `.sr*` file. Use the standalone
[`pb-format`](https://github.com/restoresrl/pb-format) tool for the
first: it writes the canonical export header and the right encoding/BOM
+ CRLF — the byte layout PB IDE expects, which a plain editor gets wrong
(stripped BOM, flipped line endings).

```sh
# Step 1 — write the SOT file correctly (header + encoding). Body on stdin.
pb-format write "C:\proj\ws_objects\myapp.pbl.src\f_compute_total.srf" \
    --entry-name f_compute_total --ext srf --encoding UTF-8 \
    --comments "fixed null-dereference in line 142" <<'BODY'
global type f_compute_total ...
...
BODY
```

```jsonc
// Step 2 — import that source into the .pbl via ORCA.
{"tool": "pb_compile_entry_import", "args": {
  "lib_path":   "C:\\proj\\myapp.pbl",
  "entry_name": "f_compute_total",
  "entry_type": "function",
  "syntax":     "$PBExportHeader$f_compute_total.srf\r\n<body>",
  "comments":   "fixed null-dereference in line 142"
}}
// → {"success": true, "errors": []}
```

Notes:

- Match `--encoding` to the workspace `.pbw` `DefaultExportEncode`
  (`UTF-8` / `UTF-16BOM` / `ANSI`). The wrong one triggers a phantom-diff
  cascade on the next PB IDE Refresh.
- `pb-format` is also a Python library (`write_source_file`,
  `build_source_text`) if you orchestrate this from code rather than the
  CLI.
- A failed compile in Step 2 returns `success: false` with `errors`; the
  SOT file from Step 1 stays written (SOT and the not-yet-fixed `.pbl`
  may diverge while you iterate).

---

## Recipe 2 — Batch import a set of entries

Faster than calling `pb_compile_entry_import` in a loop: ORCA compiles the
whole list as one batch, reusing parser state where possible.

```jsonc
{"tool": "pb_compile_entry_import_list", "args": {
  "items": [
    {
      "lib_path": "C:\\proj\\dep\\corelib.pbl",
      "entry_name": "f_split",
      "entry_type": "function",
      "syntax": "<edited source>"
    },
    {
      "lib_path": "C:\\proj\\dep\\corelib.pbl",
      "entry_name": "f_join",
      "entry_type": "function",
      "syntax": "<edited source>"
    }
  ]
}}
```

All diagnostics from the batch land in the single `errors` array. To pin
which error belongs to which entry, read the `message_text` — ORCA prefixes
it with the object name in the form `"<entry>:<text>"`.

---

## Recipe 3 — Full application rebuild after a wide refactor

When edits cross many entries, rebuild the whole application in one
ORCA call instead of importing entry-by-entry:

```jsonc
{"tool": "pb_application_rebuild", "args": {"rebuild_type": "full"}}
```

`rebuild_type`:

- `"incremental"` (default): rebuild only what changed since last compile;
- `"full"`: re-compile every entry in the library list;
- `"migrate"`: ORCA's "migrate from older PB version" pass;
- `"3pass"`: ATL-style 3-pass rebuild (slowest, most thorough).

The response shape matches the compile tools: `{"success", "errors": [...]}`.

---

## Recipe 4 — Build a `.exe` for the current application

After the rebuild is clean, produce a runnable executable:

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
    "company_name": "Acme Corp",
    "product_name": "MyApp",
    "file_version": "1.4.2",
    "file_version_num": "1.4.2.0",
    "product_version": "1.4.2",
    "product_version_num": "1.4.2.0",
    "copyright": "(c) 2026 Acme Corp"
  }
}}
```

Returns `{"success", "exe_name", "errors": [...]}`. Link errors (unresolved
externals, duplicate definitions) land in `errors` with just `message_text`
— `PBORCA_LNKPROC` is intentionally less rich than `PBORCA_ERRPROC` (no
line/column for the linker).

For a quick "validate the build" run without all the dressing:

```jsonc
{"tool": "pb_executable_create", "args": {
  "exe_name": "C:\\proj\\dist\\myapp.exe",
  "flags": ["machine_code"]
}}
```

P-code is the default — useful for the inner agentic loop where build time
matters more than runtime speed.

---

## Recipe 5 — Build a single `.pbd` for vendoring

When a downstream consumer pulls a compiled snapshot of a library (the
"vendor the `.pbd` into `dep/`" pattern common in PB projects that
distribute reusable libraries):

```jsonc
{"tool": "pb_dynamic_library_create", "args": {
  "lib_path": "C:\\proj\\dep\\corelib.pbl",
  "flags": ["machine_code", "optimize_speed"]
}}
// → produces corelib.pbd next to corelib.pbl
```

---

## Recipe 6 — Hierarchy walk

Given a user object, list every ancestor up to the root PB class
(`nonvisualobject`, `window`, `userobject`, etc.):

```jsonc
{"tool": "pb_object_query_hierarchy", "args": {
  "lib_path": "C:\\proj\\myapp.pbl",
  "entry_name": "n_cst_payment_processor",
  "entry_type": "userobject"
}}
// → {"ancestors": ["n_cst_payment_base", "n_cst_service_base", "nonvisualobject"]}
```

Closest ancestor first. Useful before editing: the agent can read the
ancestors' sources too via `pb_library_entry_export` and understand the
inherited surface area.

---

## Recipe 7 — "What does this call?" outgoing-reference audit

Before refactoring an entry, list everything it depends on (callees,
ancestors used, types declared, windows opened, etc.):

```jsonc
{"tool": "pb_object_query_reference", "args": {
  "lib_path": "C:\\proj\\myapp.pbl",
  "entry_name": "w_main",
  "entry_type": "window"
}}
// → {
//      "count": 7,
//      "references": [
//        {"library": "C:\\proj\\dep\\corelib.pbl",
//         "entry_name": "f_legacy_thing",
//         "entry_type": "function",
//         "ref_type": "simple"},
//        ...
//      ]
//    }
```

`ref_type` is `"simple"` (declarative reference: function call, type
declaration) or `"open"` (runtime `OpenWithParm` / `Open` of a window).

**Note on direction**. ORCA's `PBORCA_ObjectQueryReference` returns
the *outgoing* references of the queried object — what it uses, not
what uses it. There is no native ORCA primitive for the incoming
direction ("who calls this"); reconstructing it requires iterating
every candidate caller in the library list and inverting the result.

---

## Recipe 8 — Regenerate a single object after touching its ancestor

When you've edited an ancestor and want to re-emit its descendant's
machine code without changing the source:

```jsonc
{"tool": "pb_object_regenerate", "args": {
  "lib_path": "C:\\proj\\myapp.pbl",
  "entry_name": "n_cst_payment_processor",
  "entry_type": "userobject"
}}
```

Cheaper than a full `pb_application_rebuild` when you know exactly which
descendant needs re-emitting.

---

## Anti-recipe — do NOT replace your batch build pipeline

If you already have a working batch build (PowerGen, OrcaScript, custom
`build.bat`), keep it. `pb-orca-mcp` is an interactive development tool
for an agent's inner loop, not a tagged-release build runner. Reasons:

- The MCP server runs in the same process as Claude Code; an unhandled
  crash takes the whole agent down. CI servers want process isolation,
  retry logic, and structured logs that this server doesn't ship.
- The library list is configured per-session in memory; a release build
  needs reproducible config files, not in-memory state.
- ORCA is single-session-per-process; CI jobs that need parallel builds
  hit that wall immediately.

Use this for editing. Keep PowerGen/OrcaScript for releases.

---

## Anti-recipe — do NOT touch PBLs that PB IDE has open

If the PowerBuilder IDE is open on the same PBL, ORCA writes fail with
`PBORCA_LIBIOERROR`. ORCA respects the PB IDE's file locks but doesn't
queue around them. Close the IDE (or work on a copy) before any
`pb_library_*` or `pb_compile_*` call that would write to a PBL the IDE
is editing.
