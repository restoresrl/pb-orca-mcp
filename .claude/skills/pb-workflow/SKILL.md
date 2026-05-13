---
name: pb-workflow
description: Use this when modifying PowerBuilder objects (.sru, .srf, .srw, .sra) via the pb-orca MCP server. Covers the source-of-truth model (ws_objects/ on git projects, .pbl on standalone), how to propagate edits correctly without breaking the .pbl ↔ ws_objects/ consistency, and the integrity check for add/delete operations.
---

# PowerBuilder object-editing workflow

Use this skill whenever you are about to modify a PB object (`.sru`,
`.srf`, `.srw`, `.sra`) in a project that uses `pb-orca-mcp`. Read the
short flow below before the first write call; the full version with
cheat sheet, pitfalls, and future improvements lives in
`pb-orca-mcp/docs/workflow.md`.

## Decide who is the source of truth

- Is there a `ws_objects/` folder in the project root?
  - **Yes** (git-managed project): `ws_objects/<lib>.pbl.src/<entry>.<ext>`
    is the source of truth. The `.pbl` is the derived form. Use Variant A.
  - **No** (standalone PB project): the `.pbl` is the source of truth.
    Use Variant B.

The rationale: git can't merge binary `.pbl` files, so Appeon mirrors
each object as a text file under `ws_objects/`. The "Refresh PBL"
command in PB IDE reads the text files and rebuilds the `.pbl` —
proof that on git projects the textual form is canonical.

## Variant A — git project (`ws_objects/` is SOT)

1. Check `git status` for the target file under
   `ws_objects/<lib>.pbl.src/<entry>.<ext>`. Pending changes are
   intentional — use them as baseline. If clean, the file is the
   canonical SOT to start from.

2. Edit the file with your normal text-edit tools.

3. Open an ORCA session and set up the target:

   ```jsonc
   pb_session_open      {"pb_version": "22.0"}
   pb_set_library_list  {"libraries": [<absolute paths>]}
   pb_set_current_application {"app_lib": ..., "app_name": ...}
   ```

4. Read the file you just edited and propagate to the `.pbl`:

   ```jsonc
   pb_compile_entry_import {
     "lib_path": "...\\src\\<lib>.pbl",
     "entry_name": "<entry>",
     "entry_type": "<userobject|function|window|application|...>",
     "syntax": "<full file content>"
   }
   ```

   Expect `{"success": true, "errors": []}`. On failure, fix the SOT
   file and retry — never patch the `.pbl` separately.

5. **Integrity check** when adding or removing entries (skippable for a
   pure edit of one existing entry):

   - `pb_library_directory` → entries in the `.pbl`.
   - List files in `ws_objects/<lib>.pbl.src/` from the filesystem.
   - Entries in `.pbl` but not in `ws_objects/` → delete from the `.pbl`
     with `pb_library_entry_delete`.
   - Files in `ws_objects/` but no matching entry → import with
     `pb_compile_entry_import`.

6. `pb_session_close`.

7. `git status` should show **both** modified:

   ```
   modified:  src/<lib>.pbl
   modified:  ws_objects/src/<lib>.pbl.src/<entry>.<ext>
   ```

   If `<project>.pbw` also appears modified, revert it (workspace
   target preference, not a shared truth) unless you actually changed
   the target list.

8. Commit both files in the same commit.

## Variant B — standalone project (no `ws_objects/`)

The `.pbl` is canonical. Work in memory.

1. Open session, set library list, set current application.
2. `pb_library_entry_export` → `source` as a string with `\r\n`
   separators.
3. Modify the string (regex, replace, AST manipulation).
4. `pb_compile_entry_import` with the modified syntax.
5. `pb_session_close`. Commit just the `.pbl`.

## Pitfalls

- **Never commit only the `ws_objects/` files** leaving the `.pbl`
  stale. The build pipeline reads from the `.pbl`. (This was the
  `135c784` failure mode that motivated this skill.)
- **Never commit only the `.pbl`** on a git project. Without the SOT
  file the next merge or Refresh PBL will undo your change.
- **Never overwrite `ws_objects/<entry>.<ext>` from the `.pbl`** on a
  git project. That propagates the derived form back onto the SOT.
- **Close PB IDE before ORCA write operations**: it holds an exclusive
  lock on the `.pbl`.
- **The `.pbd` stays stale until the next build** — `pb-orca` does not
  produce `.pbd` files.
- **`pb_compile_entry_import` does not auto-update `ws_objects/`**
  (verified experimentally). On git projects you handle the SOT file
  with your host tools; ORCA's job is the `.pbl`.
- **`pb_set_current_application` may rewrite `.pbw`** non-deterministically.
  Always check `git status` and revert unless you added a target.

## Future: native sync via ORCA SCC

The ORCA API exposes `scc *` commands that work with git in offline
mode and provide the equivalent of "Refresh PBL" (with add / modify /
delete) in one call:

```
scc set connect property localprojpath "<parent of ws_objects>"
scc connect offline
scc refresh target incremental
scc close
```

If `pb-orca-mcp` exposes these commands (check the current tool list
when you open a session), prefer them over the manual sync of steps
4–5 of Variant A. Reference:
<https://docs.appeon.com/pb2025/pbug/usage_notes_2.html>

## Full documentation

`pb-orca-mcp/docs/workflow.md` has the complete version with cheat
sheet, JSON examples, workspace-file rules, the PowerGen-replacement
vision, and all pitfalls in detail. Read it the first time you onboard
to a PB project; this skill is the operational summary.
