---
name: pb-workflow
description: Use this when modifying PowerBuilder objects (.sru, .srf, .srw, .sra) via the pb-orca MCP server. Covers the source-of-truth model (ws_objects/ on git projects, .pbl on standalone), how to propagate edits correctly without breaking the .pbl ↔ ws_objects/ consistency, and the integrity check for add/delete operations.
---

# PowerBuilder object-editing workflow

Use this before modifying a PB object (`.sru`, `.srf`, `.srw`, `.sra`) in a
project that uses `pb-orca-mcp`. This is the operational summary; the full
version (recipes, JSON examples, SCC sync, encoding, all pitfalls) is in
`pb-orca-mcp/docs/usage.md` (Part 2 — the editing model).

## Decide who is the source of truth

Is there a `ws_objects/` folder in the project root?

- **Yes** (git-managed): `ws_objects/<lib>.pbl.src/<entry>.<ext>` is the SOT;
  the `.pbl` is the derived form. Use Variant A.
- **No** (standalone): the `.pbl` is the SOT. Use Variant B.

Rationale: git can't merge binary `.pbl` files, so Appeon mirrors each object
as a text file under `ws_objects/`; "Refresh PBL" rebuilds the `.pbl` from
those text files — so on git projects the text form is canonical.

## Variant A — git project (`ws_objects/` is SOT)

1. Check `git status` on `ws_objects/<lib>.pbl.src/<entry>.<ext>`. Pending
   changes are the baseline; if clean, that file is the SOT.
2. Edit the file.
3. Bootstrap the session (`pb_session_open` → `pb_set_library_list` →
   `pb_set_current_application`).
4. Propagate to the `.pbl`. `pb-orca` never writes a `.sr*` itself — two
   composable steps: write the SOT file with **`pb-format write`** (correct
   header + encoding/BOM), then import it with **`pb_compile_entry_import`**
   (its `syntax` must start with `$PBExportHeader$<name>.<ext>`). On failure,
   fix the SOT file and retry — never patch the `.pbl` separately. Full
   commands: `docs/usage.md` Recipe 1 / 1.5.
5. **Integrity check** (only when adding/removing entries): compare
   `pb_library_directory` against the files in `ws_objects/<lib>.pbl.src/`;
   delete orphans from the `.pbl` (`pb_library_entry_delete`), import new
   files (`pb_compile_entry_import`).
6. `pb_session_close`.
7. `git status` should show **both** `src/<lib>.pbl` and the `.sr*` modified.
   If `<project>.pbw` is also modified, revert it unless you changed the
   target list.
8. Commit both files in the same commit.

The native ORCA SCC flow (`pb_scc_connect_offline` → `pb_scc_set_target` →
`pb_scc_refresh_target` → `pb_scc_close`) collapses steps 4–5 into one call
sequence — see `docs/usage.md` "Refresh PBL & native SCC sync". Note:
`pb_scc_set_target` already sets the library list + current application, so
skip `pb_set_library_list` / `pb_set_current_application` in that flow (they
return `PBORCA_DUPOPERATION (-2)`).

## Variant B — standalone project (no `ws_objects/`)

The `.pbl` is canonical; work in memory: bootstrap → `pb_library_entry_export`
→ modify the string → `pb_compile_entry_import` → close. Commit the `.pbl` alone.

## Pitfalls (the never-rules)

- **Never commit only the `ws_objects/` files** leaving the `.pbl` stale — the
  build reads from the `.pbl`.
- **Never commit only the `.pbl`** on a git project — the next merge / Refresh
  PBL undoes a binary-only change.
- **Never overwrite `ws_objects/<entry>.<ext>` from the `.pbl`** on a git
  project — that pushes the derived form onto the SOT.
- **Close PB IDE before ORCA writes** — it holds an exclusive lock on the `.pbl`.
- **`pb_compile_entry_import` does not update `ws_objects/`** — you write the
  SOT file yourself (`pb-format write`); ORCA writes the `.pbl`.
- **Editors flip `.sr*` to UTF-8/LF** and break the BOM/encoding — write with
  `pb-format write --encoding <UTF-8|UTF-16BOM|ANSI>` (match the `.pbw`
  `DefaultExportEncode`), don't hand-encode. See `docs/usage.md` "Encoding caveat".
- **`pb_set_current_application` may rewrite `.pbw`** non-deterministically —
  check `git status` and revert unless you changed the target list.

Full pitfall list + SCC limitations: `docs/usage.md` Part 2.
