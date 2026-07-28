# How pb-orca works: the `.pbl`, the text projection, and git

This is the foundational document for the project. It explains how a
PowerBuilder object's source actually lives in a workspace, and how pb-orca
keeps the binary library and its text projection in agreement. The tool
reference, the usage recipes and the agent skills all derive from it. If
anything elsewhere disagrees with this file, this file is right and the other
should be corrected.

Read it once before your first write on a real workspace. The flow has one
silent failure mode, and the point of the document is to make it impossible to
hit by accident.

Everything stated here about ORCA's behaviour was verified against a real
PowerBuilder 22.0 workspace. Where something is inferred from the
specification rather than observed, it says so.

---

## 1. The two representations of an object

A PowerBuilder object exists in up to two forms:

- The **`.pbl` library** (binary). It holds the object's source *and* its
  compiled p-code. It is what the PowerBuilder IDE and the running `.exe`
  read. Every project has this.
- The **`ws_objects/<lib>.pbl.src/<entry>.<ext>` file** (text). A
  diff-friendly projection of the same source, one file per object. It exists
  *only* when the workspace was placed under source control inside the
  PowerBuilder IDE. Git and SVN can review and merge these text files; they
  cannot usefully merge the binary `.pbl`.

pb-orca drives everything through ORCA, and ORCA always operates on the `.pbl`
and on in-memory strings. Three facts follow from how the C API is built, and
they shape the whole document.

**In memory, source is always Unicode.** `pb_library_entry_export` returns the
object body as a wide-character string and `pb_compile_entry_import` takes one.
There is no byte-encoding at this layer, and the session must not be configured
as if there were (section 5.3).

**Export gives the body; import ignores the decoration.**
`pb_library_entry_export` returns the object source without the
`$PBExportHeader$` or `$PBExportComments$` lines that an on-disk `.sr*` file
carries. `pb_compile_entry_import` takes the object source as its `syntax` and
**ignores those two lines if they are present**, so the body you just exported
imports back unchanged, and so does the full on-disk file content. The ORCA
reference is explicit — "if an export header exists in the source code it is
ignored" — and all three shapes (body only, header + body, whole file) were
confirmed to import cleanly, on both an update and a create. You never add the
header lines yourself. The object's comment is set from the separate `comments`
argument, never from a `$PBExportComments$` line in the syntax; on the way out
it is the reverse, ORCA emits the stored comment as that line (section 5).

**ORCA can write the file itself.** Configured through
`PBORCA_ConfigureSession`, the same export call stops filling a buffer and
writes a `.sr*` file to a directory you choose, with the export header, the
comment line, the byte-order mark and CRLF — byte-identical to what the IDE
writes on Save. This is what lets pb-orca produce text sources without ever
formatting a byte of PowerScript itself, and it is the engine behind everything
in sections 4 and 7.

So encoding (UTF-8, UTF-16, ANSI) is never a property of what ORCA moves in
memory. It is only a property of a `.sr*` file once that file is on disk, and
choosing it correctly is delegated to ORCA.

---

## 2. Which case are you in?

Everything splits on one question: **is there a `ws_objects/<lib>.pbl.src/`
directory for this library?**

| | No `ws_objects/` | `ws_objects/` present |
| --- | --- | --- |
| Source of truth | the `.pbl` | the `ws_objects/` text files |
| The `.pbl` is | everything | the derived / built form |
| What you edit | a working file under `.pb-orca/` | the text file itself |
| What you commit | the `.pbl`, if it is tracked | the `.sr*` files, and the `.pbl` if the project tracks it |
| ORCA calls | identical | identical |

That last row is the key insight: **ORCA behaves the same in both cases.** It
always reads and writes the `.pbl`. The presence of `ws_objects/` does not
change a single ORCA call. It only changes whether a text file is *also*
persisted alongside — and pb-orca does that part for you.

`pb_workspace_info(lib_path)` answers the question in one call, without an ORCA
session and without PowerBuilder installed: it reports `mode`
(`ws_objects` / `pbl_only`), where the projection is, which encoding it uses,
whether git is watching, and where working files go. The detection rule it
implements: the projection mirrors the library's path relative to the workspace
root, so `<root>/src/app.pbl` projects to
`<root>/ws_objects/src/app.pbl.src/`. Older workspaces sometimes keep one flat
tree instead, so an existing `<lib>.pbl.src` directory found anywhere under
`ws_objects/` wins over the computed location.

---

## 3. Case A: no `ws_objects/` (the `.pbl` is the source of truth)

The simple case. There is no text file to keep in step, so there is no
encoding question, no two-file commit, and no Refresh. The `.pbl` *is* the
source.

**The working file.** `pb_compile_entry_import` always takes the **complete**
object source: there is no patch call and pb-orca keeps no draft between calls.
So you edit through a file. `pb_object_export_file` writes it for you, named
`<entry>.<ext>` after the object, into `<workspace>/.pb-orca/`. That directory
is throwaway — only your editor and the next import touch it — and when the
project is a git repository pb-orca drops a self-ignoring `.gitignore` inside
it on creation, so scratch copies never appear in `git status`. The
repository's own `.gitignore` is never modified. Pass `dest_dir` if you want
the file somewhere else.

If you would rather have a permanent, reviewable home for these files, that is
Case B: bootstrap a `ws_objects/` tree (section 7) and edit there instead.

### Set up the session

```text
pb_session_open(pb_version)                        # explicit, see below
pb_set_library_list([...])
pb_set_current_application(app_lib, app_name)
```

`.pbt` and `.pbw` files do not record which PowerBuilder release built them
(they carry the frozen 1999 format constant, not a release marker), so choose
`pb_version` explicitly. `pb_discover_pb_install` lists what is installed. The
recipes below assume the session is set up.

### Edit an existing object

```text
# 1. write the object out to a working file:
path = pb_object_export_file(lib, "w_main", "window")["file_path"]
#      ->  <workspace>\.pb-orca\w_main.srw

# 2. edit that file with ordinary file tools

# 3. import it back; this updates the .pbl:
pb_object_import_file(path, lib)
```

`pb_object_import_file` infers the entry name from the file stem, the type from
the extension, and the object comment from the file's `$PBExportComments$`
line, so a round trip needs no extra arguments. It compiles as it imports: on a
compile error it returns `success: false` with the diagnostics in `errors`
(message number, text, line, column; also available from
`pb_get_last_compile_errors`). Fix the working file and import again. ORCA may
leave partially-written source in the `.pbl` after a failed import, so
re-import the full corrected file rather than assuming the entry is untouched.
No IDE window is ever opened.

### Create a new object

The same loop, but you write the file from scratch and the entry does not exist
yet:

```text
# 1. write a complete object source to  .pb-orca\n_order.sru
#    (forward, global type ... end type, then the body;
#     no $PBExportHeader$ line needed — import ignores it)

# 2. import it; because "n_order" does not exist yet, the entry is created:
pb_object_import_file(".pb-orca\\n_order.sru", lib)
```

The quickest route to a correct skeleton is to export a similar existing
object, save it under the new name, and adapt it. After the import the object
is in the `.pbl` and appears in `pb_library_directory`.

### Delete an object

```text
pb_library_entry_delete(lib, entry, type)
```

### What you commit

If the project is in git, the only artifact that changed is the binary `.pbl`,
so you commit that alone. Git cannot diff it, which is exactly the limitation
`ws_objects/` exists to remove — and section 7 shows how to get there without
the IDE.

---

## 4. Case B: with `ws_objects/` (the text projection is the source of truth)

Here the text files are canonical and the `.pbl` is the *derived* form,
regenerated from them. The discipline is one rule with two halves:

> **Every change must land in both the `.pbl` and the `.sr*` file.**

Miss either half and you get the silent failure in section 6. pb-orca closes
both halves in one call, so the rule is a property of the server rather than
something you have to remember:

```text
              edit the ws_objects/<entry>.<ext> file
                        |
        pb_object_import_file  ->  .pbl updated (compiled, errors reported)
                        |      ->  ws_objects/<entry>.<ext> rewritten by ORCA,
                        |          byte-identical to the IDE's own output
                  commit what changed
```

### Edit an object

```text
# 1. write the current source out. On a Case B project the export lands in
#    ws_objects/ — the file IS the source of truth, so it is refreshed in place:
path = pb_object_export_file(lib, "w_main", "window")["file_path"]
#      ->  <root>\ws_objects\app.pbl.src\w_main.srw

# 2. edit that file

# 3. import; the .pbl is updated AND the text file is rewritten through ORCA:
pb_object_import_file(path, lib)
#      ->  {"success": true, "synced_files": [...], "sync": "ok"}
```

Step 1 is safe to run on an unmodified object: ORCA reproduces the same bytes,
so `git status` stays clean. You can also skip it and edit the file that is
already there.

Then check `git status` and commit. The `.sr*` shows as modified; whether the
`.pbl` also shows depends on whether the project tracks it (section 8).

### Create an object

Same as an edit, with two differences: you author the full source from scratch
into the projection directory, and the new `.sr*` is untracked in `git status`,
so you `git add` it rather than seeing it as modified. Pass `comments` to
`pb_object_import_file` (or put a `$PBExportComments$` line in the file) — the
value becomes the `$PBExportComments$` line ORCA writes back out.

### Delete an object, text and binary together

```text
pb_library_entry_delete(lib, entry, type)
#   -> removes the entry from the .pbl AND deletes ws_objects/<entry>.<ext>
```

Both removals go in the same commit. `pb_library_entry_move` behaves the same
way across two libraries: the text file is removed from the source library's
directory and written fresh into the destination's.

### Why the round trip goes through ORCA, not by hand

The fragile part of Case B is producing the `.sr*` file: the header, the
comment line, the BOM, the CRLF. A hand-built file whose encoding does not
match `DefaultExportEncode`, or whose line endings or BOM are wrong, causes a
confusing Refresh failure in the IDE later. Letting ORCA write the file removes
that entire class of bug, because the engine that defines the bytes is the one
producing them. Byte-identity was verified against the IDE's own `ws_objects/`
output for a window, a menu, an application object, a DataWindow, and a window
hosting an OLE control (binary block included). Section 9 has the one caveat,
which concerns OLE objects across PowerBuilder builds.

---

## 5. The `.sr*` file format (reference)

You do not need this to use the tools — ORCA handles it. It is here because
reading a diff, or debugging a workspace someone else built by hand, is easier
when you know what the bytes mean.

### 5.1 Layout

```text
<BOM>                                  # depends on the encoding, see below
$PBExportHeader$<entry>.<ext>          # line 1
$PBExportComments$<object comment>     # line 2, only if the object has a comment
<body>                                 # the object source, CRLF throughout
Start of PowerBuilder Binary Data Section : Do NOT Edit
<hex>                                  # only for objects hosting an OLE control
End of PowerBuilder Binary Data Section : No Source Expected After This Point
```

The `<body>` is, character for character, the same source text
`pb_library_entry_export` returns in memory: the file is that body with the
header (and optional comment) prepended and the chosen BOM in front. Nothing
else is added, except the binary section on the rare objects that have one
(section 9).

### 5.2 Encoding

Fixed per workspace by the `.pbw` directive `DefaultExportEncode`. All three
values use CRLF line endings.

| `DefaultExportEncode` | First bytes (BOM) | ORCA encoding |
| --- | --- | --- |
| `"UTF-8"` | `EF BB BF` | `PBORCA_UTF8` |
| `"UTF-16BOM"` | `FF FE` | `PBORCA_UNICODE` |
| `"ANSI"` | none | `PBORCA_ANSI_DBCS` |

All three outputs were verified directly. (`PBORCA_HEXASCII` also exists and
produces a file with an `HA` prefix; no `.pbw` value maps to it, so pb-orca
does not use it.) `"UTF-8"` is the PowerBuilder 2022 default; `"UTF-16BOM"` is
the legacy default for workspaces created before 2019; `"ANSI"` appears on
older workspaces and uses the system code page.

**A file written in a different encoding than `DefaultExportEncode` is
mis-decoded the next time the IDE refreshes the library.** So the encoding is
read, not assumed: `pb_target_info` surfaces `default_export_encode` from the
`.pbw`, and `pb_workspace_info` resolves the value actually in effect. When the
`.pbw` is silent, pb-orca sniffs the BOM of an existing `.sr*` and uses that,
falling back to UTF-8 only when there is no evidence at all. When the `.pbw`
declares one encoding and the files on disk are another, the declared value
wins (it is what the IDE will write) and the mismatch is reported in
`observed_encoding`, because that workspace is already inconsistent.

### 5.3 Two ways to corrupt source silently

Both of these produce no error from ORCA. They are the reason pb-orca reads
files the way it does and guards the session configuration.

**Line endings.** PowerBuilder stores CRLF. Importing LF-normalized text
succeeds, and rewrites every line inside the `.pbl`; the next export then
differs from the file in the repository on every line. pb-orca reads source
files without newline translation, and you should make sure your editor does
not "fix" them either.

**Session encoding.** `eExportEncoding` applies to the in-memory export path as
well as to files. With it set to UTF-8, ORCA packs UTF-8 bytes into the
wide-character buffer and the string that comes back is mojibake — which then
imports "successfully" and destroys the object. pb-orca's file tools set and
restore the configuration around their own calls, and the in-memory tools
refuse to run while a corrupting configuration is in effect. If you call
`pb_session_configure` by hand, reset it before using them.

### 5.4 File extensions

ORCA chooses the extension from the object type, by the standard convention:

| Object type | Extension |
| --- | --- |
| application | `.sra` |
| window | `.srw` |
| menu | `.srm` |
| user object | `.sru` |
| function | `.srf` |
| structure | `.srs` |
| datawindow | `.srd` |
| query | `.srq` |
| pipeline | `.srp` |

You never compute it on export; pb-orca uses the same table in reverse to infer
an entry's type from a file you hand it. Object kinds with no source form
(`project`, `proxyobject`, `binary`) have no extension and are skipped by the
bulk export.

### 5.5 Details of ORCA's file export

Relevant if you read the code or drive `pb_session_configure` yourself:

- **The export directory must exist.** ORCA does not create it and returns
  `PBORCA_OBJEXISTS (-8)` if it is missing. pb-orca creates it first.
- **Only `PBORCA_CLOBBER` overwrites** an existing file. The other three
  `pborca_clobber` values, including the promisingly-named `CLOBBER_ALWAYS`,
  return `PBORCA_OBJEXISTS (-8)`. Since re-exporting over an existing `.sr*` is
  the normal case, pb-orca always sends `PBORCA_CLOBBER`.
- **The configuration is reversible.** Switching into file mode and back leaves
  in-memory exports byte-for-byte as they were, which is what makes the
  set-and-restore wrapper safe.

---

## 6. The danger zone: how Case B breaks

The failure mode is silent, which is why it gets its own section. It comes from
one fact: **a headless ORCA import updates the `.pbl` only.** It does not touch
`ws_objects/`, and nothing flags the object as out of sync. pb-orca's automatic
sync exists to close exactly this hole; the failure modes below are what you
get when it is bypassed — with `sync_sources="never"`, with a tool outside
pb-orca, or by editing files by hand.

- **Import without writing the text file.** The `.pbl` changes, the
  `ws_objects/` file still holds the old source, and `git status` shows only
  the binary as modified (or nothing at all, if the `.pbl` is untracked).
  Whoever refreshes or merges next silently reverts your change, because
  Refresh goes `ws_objects/` → `.pbl`.
- **Edit the text file without importing.** The `.sr*` changes, the `.pbl`
  still holds the old code. Anyone building from that commit gets stale
  behaviour, because the build reads the `.pbl`. The commit reviews clean and
  the build is wrong.
- **A malformed hand-written `.sr*`.** A file whose encoding does not match
  `DefaultExportEncode`, or with LF instead of CRLF, or with a stripped BOM,
  can still import through `pb_compile_entry_import` (the import path is more
  tolerant than Refresh) while failing the IDE's Refresh later. Letting ORCA
  write the file avoids this. Note that a file *missing* the
  `$PBExportComments$` line still refreshes successfully, so that particular
  omission is not what breaks Refresh; encoding and line-ending mismatches are
  the real risk.

Two facts about how the IDE behaves:

- The IDE writes `ws_objects/` from the `.pbl` only when you **Save** the
  object in the IDE. Merely opening it does nothing. Worse, opening an object
  whose text file you edited externally, without refreshing first, regenerates
  the text from the stale `.pbl` and overwrites your edit. You cannot rely on
  "the IDE will sync it later".
- The IDE's **Refresh PBL** goes the other way, `ws_objects/` → `.pbl`. If the
  `.pbl` is ahead (you imported but the text file did not follow), a Refresh
  overwrites your change with the older text. Refresh is a reconciliation step,
  not a way to push a `.pbl`-only edit outward.

### The native SCC Refresh through ORCA

ORCA exposes the IDE's Refresh PBL offline, through the `pb_scc_*` tools
(`pb_scc_connect_offline` → `pb_scc_set_target` → `pb_scc_refresh_target` →
`pb_scc_close`), which reconcile a whole `ws_objects/` tree into the `.pbl`
(add, modify, delete) in one call sequence. It is the right tool after a merge
or a branch switch. Three things to know:

- `importonly` is a **required** flag in offline mode, and it is passed in the
  `flags` argument of `pb_scc_set_target` (one of `refresh_all`, `outofdate`,
  `importonly`, `exclude_checkout`), not to `pb_scc_refresh_target`. Without it
  the connect fails with `PBORCA_IMPORTONLY_REQ`.
- It operates on the whole tree at once, so a single malformed file fails the
  batch with no per-object diagnostic, while `pb_object_import_file` reports
  per-line errors for one object. For the per-object edit loop, prefer the
  import.
- It writes a flat `.sr*` export plus a `.pbg` registry file into
  `local_proj_path` as a side effect. In a git repository that is untracked
  noise; check `git status` afterwards.

Also note that `pb_scc_set_target` already sets the session's library list and
current application, so calling `pb_set_library_list` /
`pb_set_current_application` afterwards returns `PBORCA_DUPOPERATION (-2)`.
Skip them in the SCC flow. And `pb_scc_get_connect_properties` always returns
`PBORCA_REGREADERROR (-23)` on a git/svn workspace, because the `.pbw` has no
SCC block; `pb_scc_connect_offline` tolerates that and proceeds. Remote SCC
operations (`get latest version`, server connections) do not work with git/svn
by design — use the git CLI.

---

## 7. Bootstrapping `ws_objects/` from a binary-only `.pbl`

If a project has only the binary `.pbl` and you want reviewable source under
git, you do not need the IDE:

```text
pb_library_export_sources(lib_path)
```

It enumerates every entry, configures the export to the workspace encoding, and
writes each object into `ws_objects/<lib>.pbl.src/`. In testing this produced
files byte-identical to the IDE's own `ws_objects/`, extensions and all. Commit
the `.pbl` and the new tree, and from then on the project is a Case B project:
follow section 4.

The same call with an explicit `dest_dir` is also the fast way to read a whole
library as text without changing anything the project depends on.

---

## 8. Git: what actually gets committed

pb-orca guarantees the two forms agree **on disk**. What you commit is the
project's policy, and there are two common ones:

- **The `.pbl` is tracked** alongside the text files. Both change together and
  both belong in the same commit. This is the shape the "commit both" rule
  assumes.
- **The `.pbl` is untracked**, treated as a build artifact, and regenerated
  from `ws_objects/` by a Refresh. Then only the `.sr*` files are committed and
  `git status` never mentions the binary.

Both are valid; `git status` tells you which one you are in. pb-orca never
stages or commits anything.

Two other files to watch:

- **`<project>.pbw`** carries the workspace target list, the
  `DefaultExportEncode` directive, and the current-target preference
  (`DefaultTarget`, `DefaultRemoteTarget`). That preference is per user, not
  shared truth. `pb_set_current_application` may rewrite the `.pbw` as a side
  effect, non-deterministically. After a session, check `git status`: if only
  the current-target lines changed, revert it. Commit it only when you actually
  added or removed a target.
- **`<lib>.pbg`**, on workspaces that keep one, lists which objects belong to
  which library for the IDE's source control. ORCA does not manage it, and
  pb-orca does not touch it. A newly created object may need it updated for the
  IDE to register the object fully — to be confirmed on a workspace that uses
  one; the workspaces tested here had none, and objects created through ORCA
  were seen correctly and survived a Refresh.

---

## 9. Limits and open questions

**Objects with a binary part.** Some objects export with an extra
`Start of PowerBuilder Binary Data Section` block, which is only written when
`bExportIncludeBinary` is set. pb-orca sets it on every file export.

What produces that block, established by grepping a real 2470-object codebase:
**OLE / ActiveX controls**, and nothing else. Exactly two files in that
codebase carry a binary section — an `olecustomcontrol` user object and the
window that hosts it — and both also carry the `binarykey` property that names
the embedded stream. A picture in a DataWindow does *not*: PowerBuilder writes
it as `bitmap(... filename="image.png" ...)`, a reference to a file on disk,
with no embedded bytes. Neither do plain windows, menus, functions,
structures or ordinary DataWindows.

Exporting one of those two objects through pb-orca reproduces the binary
section, and the window came out **byte-identical** to the file the IDE had
committed. Dropping the flag shrinks the same file from 10,934 to 2,760 bytes,
so the option demonstrably does what it says.

One caveat worth knowing if your project uses OLE controls. Two consecutive
exports from the same PowerBuilder build are byte-identical, so the export is
deterministic — but the *binary payload* of an OLE object can differ across PB
builds. The other of the two objects came out the same length as the committed
file with 358 bytes differing, all of them inside the OLE compound-storage
block, when exported with a newer PB build than the one that had produced the
committed file. So on a project with OLE-bearing objects, a sync can show a
diff in the binary block even though nobody changed the source. The text part
is unaffected.

**`.pbg` registration**, as described in section 8.

**Encoding coverage.** UTF-8, UTF-16 and ANSI file output were all verified
directly. The claim that a given workspace's IDE will read them back
identically rests on the PowerBuilder specification for the `.pbw`
`DefaultExportEncode` values.

**What pb-orca deliberately does not do.** It does not run git, so it cannot
tell you whether a file is tracked — run `git status` yourself. It does not
format PowerScript. It is not a release build runner: batch and OrcaScript
pipelines stay where they are (see the anti-recipe in
[`usage.md`](usage.md)).

---

## 10. Summary

ORCA always works on the binary `.pbl` and on Unicode strings in memory; it
never cares whether `ws_objects/` exists. If it is absent, the `.pbl` is the
whole truth: export to a working file, edit, import, commit the `.pbl`. If it
is present, the text files are the truth and the `.pbl` is derived: edit the
`.sr*`, import it — which updates the `.pbl` and rewrites the text file through
ORCA in the same call — and commit what `git status` shows. The single mistake
to never make is to change one of the two and not the other, and the server is
built so that you have to go out of your way to make it.
