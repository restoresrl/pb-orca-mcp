# Usage guide

End-to-end workflows for driving PowerBuilder with `pb-orca-mcp`, plus the
source-of-truth model you must understand before your first write on a
git-managed PB project.

- **Part 1 — Recipes**: the JSON tool-call sequences for common tasks
  (compile loop, build, queries).
- **Part 2 — The editing model**: how the binary `.pbl` and the textual
  `ws_objects/` projection relate, and how to keep them consistent.

For the full schema of every tool see [`tools.md`](tools.md); for install
and the x86/x64 gotcha see [`installation.md`](installation.md); for the
MCP config and skills see [`claude-code-setup.md`](claude-code-setup.md).

---

# Part 1 — Recipes

Each recipe shows the JSON tool-call sequence with notes on why each step
is required. These are the patterns Claude Code follows when given a
high-level task like "fix the compile error in `n_cst_main`".

## Session bootstrap

The bootstrap of every session is the same; subsequent recipes assume it
is already done.

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

## Recipe 1 — Compile-test loop

The inner loop of agentic PB development: an entry is broken, the agent
edits the source, re-imports it, reads the compile errors, and iterates.

**Note — keeping the on-disk `.sr*` in sync.** This recipe imports from
memory into the `.pbl`; it does not write the `ws_objects/<...>.sr*`
file. When the workspace is the source of truth and you need both
updated, write the SOT file first (Recipe 1.5), then import.

```jsonc
// Step 1: read the current source
{"tool": "pb_library_entry_export", "args": {
  "lib_path": "C:\\proj\\myapp.pbl",
  "entry_name": "f_compute_total",
  "entry_type": "function"
}}
// → {"source": "global type f_compute_total ...\n..."}
//   ASYMMETRY (canonical note): `source` is the **body only**. The first
//   line is NOT a `$PBExportHeader$` line. PB IDE's on-disk export *does*
//   start with `$PBExportHeader$<name>.<ext>`, but library_entry_export
//   strips it.

// Step 2: the agent edits `source` (outside MCP) to fix a bug

// Step 3: re-import the edited source
//   IMPORTANT: compile_entry_import REQUIRES the `$PBExportHeader$` line
//   as the first line of `syntax`. For a direct export→import round-trip
//   you must re-prepend it manually:
//     syntax = "$PBExportHeader$f_compute_total.srf\r\n" + edited_source
//   Without this the import errors out before reaching the compiler.
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

When `success: false`, the `errors` array carries the same diagnostics PB
IDE would show — line/column included. The agent correlates `message_text`
and `line` with the source it just submitted and iterates.

## Recipe 1.5 — Write the source-of-truth file, then import

When `ws_objects/<lib>.pbl.src/<entry>.<ext>` is the source of truth, you
want **two** effects: the on-disk `.sr*` updated *and* the `.pbl`
re-imported. `pb-orca-mcp` only does the second — it is a pure ORCA bridge
and never writes a `.sr*` file. You write the SOT file yourself, with the
exact byte layout PB IDE expects. A plain editor save gets this wrong
(strips the BOM, flips CRLF→LF), which triggers a phantom-diff cascade on
the next PB IDE Refresh — so write it deliberately, with the codec pinned.

The byte layout of a PB source file:

- **Line 1** — `$PBExportHeader$<entry_name>.<ext>`
  (e.g. `$PBExportHeader$f_compute_total.srf`).
- **Body** — the object source, as `pb_library_entry_export` returns it.
- **Line endings** — CRLF (`\r\n`) throughout.
- **Encoding** — match the workspace `.pbw` `DefaultExportEncode`: UTF-16
  LE + BOM (`FF FE`), UTF-8 + BOM (`EF BB BF`), or ANSI (no BOM).

```pwsh
# Step 1 — write the SOT file with the header + the right codec. Pin the
# encoding explicitly; do not let the host editor choose it. UTF-16 LE+BOM
# shown — for UTF-8 BOM use [System.Text.UTF8Encoding]::new($true),
# for ANSI use [System.Text.Encoding]::Default.
$header = '$PBExportHeader$f_compute_total.srf'
$body   = ($body -split "`r?`n") -join "`r`n"            # normalize body to CRLF
[System.IO.File]::WriteAllText(
    'C:\proj\ws_objects\myapp.pbl.src\f_compute_total.srf',
    ($header + "`r`n" + $body),
    [System.Text.Encoding]::Unicode)
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

- The codec must match the `.pbw` `DefaultExportEncode` (`UTF-8` /
  `UTF-16BOM` / `ANSI`). The wrong one triggers a phantom-diff cascade on
  the next PB IDE Refresh (see Part 2 → Encoding caveat).
- The header line is required in **both** places: it's line 1 of the
  on-disk `.sr*`, and it's the first line of the `syntax` you pass to
  `compile_entry_import` (export strips it — import requires it).
- A failed compile in Step 2 returns `success: false`; the SOT file from
  Step 1 stays written (SOT and the not-yet-fixed `.pbl` may diverge while
  you iterate).

## Recipe 2 — Batch import a set of entries

Faster than calling `pb_compile_entry_import` in a loop: ORCA compiles the
whole list as one batch, reusing parser state where possible.

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

All diagnostics from the batch land in the single `errors` array. To pin
which error belongs to which entry, read `message_text` — ORCA prefixes it
with the object name as `"<entry>:<text>"`.

## Recipe 3 — Full application rebuild after a wide refactor

When edits cross many entries, rebuild the whole application in one ORCA
call instead of importing entry-by-entry:

```jsonc
{"tool": "pb_application_rebuild", "args": {"rebuild_type": "full"}}
```

`rebuild_type`: `"incremental"` (default, only what changed), `"full"`
(re-compile every entry), `"migrate"` (migrate-from-older-PB pass),
`"3pass"` (slowest, most thorough). Response: `{"success", "errors": [...]}`.

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
    "company_name": "Acme Corp", "product_name": "MyApp",
    "file_version": "1.4.2", "file_version_num": "1.4.2.0",
    "product_version": "1.4.2", "product_version_num": "1.4.2.0",
    "copyright": "(c) 2026 Acme Corp"
  }
}}
```

Returns `{"success", "exe_name", "errors": [...]}`. Link errors (unresolved
externals, duplicate definitions) land in `errors` with just
`message_text` — `PBORCA_LNKPROC` is intentionally less rich than
`PBORCA_ERRPROC` (no line/column for the linker).

For a quick "validate the build" run without the dressing:

```jsonc
{"tool": "pb_executable_create", "args": {
  "exe_name": "C:\\proj\\dist\\myapp.exe", "flags": ["machine_code"]
}}
```

P-code is the default — useful for the inner loop where build time matters
more than runtime speed.

## Recipe 5 — Build a single `.pbd` for vendoring

When a downstream consumer pulls a compiled snapshot of a library (the
"vendor the `.pbd` into `dep/`" pattern):

```jsonc
{"tool": "pb_dynamic_library_create", "args": {
  "lib_path": "C:\\proj\\dep\\corelib.pbl",
  "flags": ["machine_code", "optimize_speed"]
}}
// → produces corelib.pbd next to corelib.pbl
```

## Recipe 6 — Hierarchy walk

List every ancestor of a user object up to the root PB class:

```jsonc
{"tool": "pb_object_query_hierarchy", "args": {
  "lib_path": "C:\\proj\\myapp.pbl",
  "entry_name": "n_cst_payment_processor",
  "entry_type": "userobject"
}}
// → {"ancestors": ["n_cst_payment_base", "n_cst_service_base", "nonvisualobject"]}
```

Closest ancestor first. Useful before editing: read the ancestors' sources
too via `pb_library_entry_export` to understand the inherited surface.

## Recipe 7 — "What does this call?" outgoing-reference audit

Before refactoring an entry, list everything it depends on:

```jsonc
{"tool": "pb_object_query_reference", "args": {
  "lib_path": "C:\\proj\\myapp.pbl",
  "entry_name": "w_main",
  "entry_type": "window"
}}
// → {"count": 7, "references": [
//      {"library": "...corelib.pbl", "entry_name": "f_legacy_thing",
//       "entry_type": "function", "ref_type": "simple"}, ...]}
```

`ref_type` is `"simple"` (declarative: call, type declaration) or `"open"`
(runtime `Open`/`OpenWithParm` of a window). **Direction**: ORCA returns
the *outgoing* references — what the object uses, not what uses it. There
is no native primitive for the incoming direction; reconstructing it means
iterating every candidate caller and inverting.

## Recipe 8 — Regenerate a single object after touching its ancestor

Re-emit a descendant's machine code without changing its source:

```jsonc
{"tool": "pb_object_regenerate", "args": {
  "lib_path": "C:\\proj\\myapp.pbl",
  "entry_name": "n_cst_payment_processor",
  "entry_type": "userobject"
}}
```

Cheaper than a full `pb_application_rebuild` when you know exactly which
descendant needs re-emitting.

## Anti-recipe — do NOT replace your batch build pipeline

If you already have a working batch build (PowerGen, OrcaScript, a custom
`build.bat`), keep it. `pb-orca-mcp` is an interactive development tool for
an agent's inner loop, not a tagged-release build runner:

- The MCP server runs in the same process as Claude Code; an unhandled
  crash takes the whole agent down. CI wants process isolation and retry.
- The library list is per-session in memory; a release build needs
  reproducible config files.
- ORCA is single-session-per-process; parallel CI builds hit that wall.

Use this for editing; keep PowerGen/OrcaScript for releases.

## Anti-recipe — do NOT touch PBLs that PB IDE has open

If the PB IDE is open on the same PBL, ORCA writes fail with
`PBORCA_LIBIOERROR`. ORCA respects the IDE's file locks but doesn't queue
around them. Close the IDE (or work on a copy) before any `pb_library_*` or
`pb_compile_*` call that writes to a PBL the IDE is editing.

---

# Part 2 — The editing model (source of truth)

How to modify PB objects without breaking the consistency between the
binary `.pbl` and the textual `ws_objects/` projection. Read this before
your first write on a git project — the failure mode is silent and easy
to commit.

## Who is the source of truth?

A PowerBuilder object lives in two forms:

- **`.pbl` library** (binary) — holds both the source and the compiled
  p-code. It is the runtime deliverable PB IDE, PowerGen, and the EXE read.
- **`ws_objects/<lib>.pbl.src/<entry>.<ext>`** — a textual projection of
  the same source (`.sru` / `.srf` / `.srw` / `.sra`), suitable for diff,
  grep, review, and git merge.

| Project type | Source of truth | Derived form | How to sync |
| --- | --- | --- | --- |
| Standalone, no git | `.pbl` | (none) | n/a |
| Managed with git | **`ws_objects/`** | `.pbl` | "Refresh PBL" in PB IDE, or `pb_scc_refresh_target` via ORCA |

The rationale: git can't usefully merge binary `.pbl` files, so Appeon
added `ws_objects/` to give git text files. **On git projects the textual
files are canonical** and the binary library is regenerated from them.

## What goes wrong if you skip the sync

1. You edit `ws_objects/.../some_entry.sru` with a text editor (VS Code,
   Claude Code, `sed` — anything not PB IDE).
2. You commit. Git includes the new `.sru`; the `.pbl` is unchanged
   because nothing wrote to it.
3. Anyone building from this commit gets stale code: PB compiles from the
   `.pbl`, which still has the pre-change source.

The text file shows the fix; the binary doesn't. The commit looks healthy
on review but the build is broken. **Rule**: editing the SOT is correct,
but you must also **propagate the change to the `.pbl` in the same
commit** — the `.pbl` is what gets built and distributed.

## Variant A — git project (`ws_objects/` is the SOT)

Edit the file under `ws_objects/`, then propagate to the `.pbl`. Never
overwrite the `ws_objects/` file with the content of the `.pbl` (that
pushes the derived form back onto the SOT — wrong direction).

1. **Identify** the entry: `ws_objects/<lib>.pbl.src/<entry>.<ext>`. If
   `git status` shows pending changes on it, those are the baseline; if
   clean, the file is the canonical SOT.
2. **Edit** the file.
3. **Bootstrap** the session (see Part 1 → Session bootstrap).
4. **Propagate to the `.pbl`** — read the edited file and import it with
   `pb_compile_entry_import` (Recipe 1). When you write the SOT file from
   scratch, emit the header + the right encoding/CRLF yourself first
   (Recipe 1.5). On failure, fix the SOT file and retry — never patch the
   `.pbl` separately.
5. **Integrity check** (only when the change adds or removes entries):
   - `pb_library_directory` → entries in the `.pbl`; enumerate the files
     in `ws_objects/<lib>.pbl.src/`.
   - In `.pbl` but missing from `ws_objects/` → `pb_library_entry_delete`.
   - In `ws_objects/` but missing from `.pbl` → import them.
6. **Close** the session.
7. **Verify** with `git status`: both `src/<lib>.pbl` and
   `ws_objects/.../<entry>.<ext>` should be modified. If `<project>.pbw`
   is also modified, revert it (see "Workspace file") unless you added or
   removed a target.
8. **Commit both files in the same commit.**

The native ORCA SCC flow collapses steps 4–5 into one call sequence — see
"Refresh PBL & native SCC sync" below.

## Variant B — standalone project (no `ws_objects/`, the `.pbl` is the SOT)

No text file on disk; everything happens in memory.

1. Bootstrap the session.
2. `pb_library_entry_export` → `source` (a string with `\r\n` separators).
3. Modify the string (regex, replace, AST manipulation).
4. `pb_compile_entry_import` with the modified `syntax`.
5. Close the session. Only the `.pbl` changed; commit it alone.

## Encoding caveat for `.sr*` files

PB IDE picks the encoding of `.sr*` files from the workspace `.pbw`
`DefaultExportEncode` directive:

| Value | First bytes | Notes |
|---|---|---|
| `"UTF-8"` | `EF BB BF` | PB 2022 default. |
| `"UTF-16BOM"` | `FF FE` | PB legacy default (pre-2019). |
| `"ANSI"` | (no BOM) | Older Windows workspaces, system codepage. |

All three use **CRLF**. Most host editors save UTF-8 no-BOM with LF, so a
naïve "edit the `.srw` and refresh" can silently strip the BOM or flip
line endings — at which point `pb_scc_refresh_target` and
`pb_compile_entry_import` fail, or PB re-exports the file on the next
Refresh (phantom-diff cascade).

**Recommended**: don't let the editor choose the encoding — write the file
with the codec pinned, as in Recipe 1.5. Normalize the body to CRLF and
write with the matching codec (`[System.Text.UTF8Encoding]::new($true)` for
UTF-8 BOM, `[System.Text.Encoding]::Unicode` for UTF-16 LE BOM,
`[System.Text.Encoding]::Default` for ANSI), then verify the first bytes.

## Style normalization is out of scope

`pb-orca-mcp` does not touch source style. It imports whatever `syntax` you
hand it, byte for byte — it won't reformat indentation, keyword case, or
operator spacing to match PB IDE's conventions. If you care about matching
that style, normalize the `.sr*` source with a separate formatter **before**
importing; this server stays purely an ORCA bridge.

## Refresh PBL & native SCC sync (offline mode, git/svn)

"Refresh PBL" in PB IDE reads `ws_objects/<lib>.pbl.src/` and re-populates
the `.pbl` — adding, modifying, and **deleting** to match the directory.
Run it (or the ORCA equivalent) after: a git merge that touched
`ws_objects/`, a branch switch, or any external edit of `ws_objects/`.

ORCA exposes the same thing offline (no remote SCC server) via 6 tools:
`pb_scc_connect_offline`, `pb_scc_set_target`, `pb_scc_refresh_target`,
`pb_scc_exclude_library_list`, `pb_scc_get_connect_properties`,
`pb_scc_close`. It syncs `ws_objects/` → `.pbl` (add/modify/delete) in one
call, collapsing Variant A to ~4 steps. `local_proj_path` must be the
**parent of `ws_objects/`**:

```jsonc
{"tool": "pb_session_open",        "args": {"pb_version": "22.0"}}
{"tool": "pb_scc_connect_offline", "args": {
    "workspace_file": "C:\\proj\\<project>.pbw", "local_proj_path": "C:\\proj"}}
{"tool": "pb_scc_set_target", "args": {
    "target_file": "C:\\proj\\<lib>.pbt", "flags": ["refresh_all", "importonly"]}}
{"tool": "pb_scc_refresh_target", "args": {"rebuild_type": "incremental"}}
{"tool": "pb_scc_close",    "args": {}}
{"tool": "pb_session_close","args": {}}
```

References:
<https://docs.appeon.com/pb2025/pbug/usage_notes_2.html> and
<https://docs.appeon.com/pb2025/pbug/ug36631.html>.

Known limitations:

- `scc get latest version` and remote SCC server connections do not work
  with git/svn — by design. Use the git/svn CLI for those.
- `pb_scc_get_connect_properties` always returns `PBORCA_REGREADERROR
  (-23)` on a git/svn workspace (the `.pbw` has no SCC block);
  `pb_scc_connect_offline` tolerates it and proceeds. Both are expected.
- `pb_scc_set_target` **also configures the library list and current
  application** — so a later `pb_set_library_list` /
  `pb_set_current_application` returns `PBORCA_DUPOPERATION (-2)`. Skip
  them in the SCC flow; go straight to `pb_application_rebuild`.
- On the first upload to git, objects are generated under `ws_objects/` in
  a flat layout; same-named entries from different `.pbl`s overwrite each
  other. Workaround: give each `.pbl` its own `ws_objects/<lib>.pbl.src/`
  subdirectory (PB IDE does this for newly-created workspaces).
- In offline mode only `local_proj_path`, `log_file`, `append_log` take
  effect; the other config fields are ignored by the SCC layer.

## Workspace file (`.pbw`)

The `<project>.pbw` carries the workspace target list and the current
target preference (`DefaultTarget`, `DefaultRemoteTarget`) — a per-user
preference, not a shared truth.

- **Revert by default** when only the current-target lines change.
  `pb_set_current_application` may rewrite the `.pbw` as a side effect
  (`git checkout -- <project>.pbw`).
- **Commit** only when a target was actually added or removed.

The rewrite is **non-deterministic** — not every call touches it. Always
check `git status` after a session and revert the `.pbw` if needed.

## Pitfalls

- **Never commit only the `ws_objects/` files**: the `.pbl` must be in the
  same commit. The build pipeline reads from the `.pbl`.
- **Never commit only the `.pbl`** on a git project: it's the derived
  form. The next merge or Refresh PBL will undo a binary-only change.
- **Never overwrite `ws_objects/<entry>.<ext>` from the `.pbl`** on a git
  project (e.g. `pb_library_entry_export` + write). That pushes the
  derived form onto the SOT. Exception: recovery where the `.pbl` is known
  authoritative (a fix made in PB IDE on a machine without `ws_objects/`).
- **`pb_compile_entry_import` does not update `ws_objects/`** (verified):
  ORCA writes the `.pbl`; you handle the SOT file with your host tools
  (write it with the header + the right codec, Recipe 1.5).
- **`pb_object_regenerate` is not "regenerate the `.src`"**: it re-emits
  internal p-code inside the `.pbl`, without touching the text file.
- **The `.pbd` deployable stays stale until the next build** —
  `pb-orca-mcp` doesn't produce `.pbd` files; consumers won't see your
  change until the build runs.
- **`pb_set_current_application` may rewrite `.pbw`** (non-deterministic):
  check `git status` and revert unless you changed the target list.
- **PB IDE silently regenerates `ws_objects/<entry>.<ext>` on save**: if
  you edited `ws_objects/` externally and then open the object in PB IDE
  **without** running Refresh PBL first, the IDE regenerates the `.src`
  from the (stale) `.pbl`, overwriting your edit. Refresh PBL first.

## TL;DR

> **Git project** (`ws_objects/` exists): SOT is `ws_objects/`. Edit the
> `.sr*`, propagate to the `.pbl` (Recipe 1 / 1.5, or `pb_scc_refresh_target`),
> commit both in the same commit, revert the `.pbw` unless the target list
> changed. **Standalone** (no `ws_objects/`): the `.pbl` is the SOT —
> export → modify → import, commit the `.pbl` alone. **Never** commit only
> `ws_objects/` (stale `.pbl`), and **never** overwrite `ws_objects/` from
> the `.pbl` on a git project.
