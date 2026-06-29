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

4. Read the file you just edited and propagate to the `.pbl`.

   **Preferred (single tool call)** — `pb_edit_and_import` writes the
   SOT file with the workspace `DefaultExportEncode` (UTF-8 BOM by
   default, UTF-16BOM or ANSI on demand) + CRLF, rebuilds the
   canonical header block (`$PBExportHeader$` plus `$PBExportComments$`
   when `comments` is non-empty, with PowerScript-escaped CRLF-
   normalized content), and imports atomically:

   ```jsonc
   pb_edit_and_import {
     "lib_path":         "...\\src\\<lib>.pbl",
     "entry_name":       "<entry>",
     "entry_type":       "<userobject|function|window|application|...>",
     "syntax":           "<edited body — header optional>",
     "source_path":      "...\\ws_objects\\<lib>.pbl.src\\<entry>.<ext>",
     "comments":         "optional commit-style message",
     "source_encoding":  "UTF-8",  // match the .pbw DefaultExportEncode
     "format":           "auto"    // normalize body if .pb-format.toml is present
   }
   ```

   The `format` parameter (default `"auto"`) runs the optional
   PowerScript body normalizer — but only when the workspace has opted
   in by committing a `.pb-format.toml`. Without that file `"auto"` is a
   no-op, so behaviour is unchanged for workspaces that don't use it. The
   response includes `formatted: bool`. The same engine is exposed
   offline as the `pb-format` CLI. See
   `pb-orca-mcp/docs/formatter.md` for the contract and config.

   **Manual three-step form** — use when you want fine control over
   the encoding step, or when the SOT file is not under `ws_objects/`:

   ```jsonc
   // (4a) The agent edits the .sr* file via host tools.
   // (4b) Re-encode the file to match the workspace DefaultExportEncode
   //      (UTF-8 BOM by default — see "Pitfalls" below).
   // (4c) Then call pb_compile_entry_import directly:
   pb_compile_entry_import {
     "lib_path": "...\\src\\<lib>.pbl",
     "entry_name": "<entry>",
     "entry_type": "<userobject|function|window|application|...>",
     "syntax": "$PBExportHeader$<entry>.<ext>\r\n<full file content>"
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
  with your host tools; ORCA's job is the `.pbl`. **Mitigation**: use
  `pb_edit_and_import` instead — it writes the SOT file and imports
  in a single atomic call.
- **Edit tools may flip `.sr*` files to UTF-8 no-BOM or LF on save**,
  or change the BOM away from the workspace `DefaultExportEncode`.
  PB rejects the file or re-exports it on the next Refresh
  (encoding-mismatch cascade). After any host-tool edit on a
  `.sra`/`.srf`/`.srw`/`.srm`/`.sru`/`.srd`, reconvert with PowerShell
  using the codec that matches the workspace `.pbw`:
  `[System.IO.File]::WriteAllText($path, $content, [System.Text.UTF8Encoding]::new($true))`
  for UTF-8 BOM, `[System.Text.Encoding]::Unicode` for UTF-16 LE BOM,
  `[System.Text.Encoding]::Default` for ANSI. See `docs/workflow.md`
  "Encoding caveat" for details. **Mitigation**: use
  `pb_edit_and_import` with the matching `source_encoding` parameter —
  it writes the right BOM + codec natively, no host-tool round-trip.
- **Export/import asymmetry**: `pb_library_entry_export` returns the
  body only (no `$PBExportHeader$`, no `$PBExportComments$`);
  `pb_compile_entry_import` requires `$PBExportHeader$<name>.<ext>`
  as the first line of `syntax`. Re-prepend it manually for round-
  trips. **Mitigation**: `pb_edit_and_import` rebuilds the canonical
  header block (header + comments line + PowerScript-escaped CRLF-
  normalized comment) automatically.
- **`pb_set_current_application` may rewrite `.pbw`** non-deterministically.
  Always check `git status` and revert unless you added a target.

## Native sync via ORCA SCC

The ORCA API exposes `scc *` commands that work with git/svn in offline
mode and provide the equivalent of "Refresh PBL" (with add / modify /
delete) in one call. Exposed via `pb_scc_*` MCP tools — prefer them
over the manual sync of steps 4–5 of Variant A:

```jsonc
{"tool": "pb_scc_connect_offline", "args": {
    "workspace_file":  "<.pbw>",
    "local_proj_path": "<parent of ws_objects>"
}}
{"tool": "pb_scc_set_target", "args": {
    "target_file": "<.pbt>", "flags": ["refresh_all", "importonly"]
}}
{"tool": "pb_scc_refresh_target", "args": {"rebuild_type": "incremental"}}
{"tool": "pb_scc_close", "args": {}}
```

`local_proj_path` must be the parent directory of `ws_objects/`.
`pb_scc_set_target` also configures the session's library list and
current application — calling `pb_set_library_list` or
`pb_set_current_application` after it returns `PBORCA_DUPOPERATION (-2)`.
Skip them in the SCC flow; you can go straight to `pb_application_rebuild`.

See `docs/workflow.md` "Native ORCA SCC sync" for details and limitations.
Reference:
<https://docs.appeon.com/pb2025/pbug/usage_notes_2.html>

## Full documentation

`pb-orca-mcp/docs/workflow.md` has the complete version with cheat
sheet, JSON examples, workspace-file rules, the PowerGen-replacement
vision, and all pitfalls in detail. Read it the first time you onboard
to a PB project; this skill is the operational summary.
