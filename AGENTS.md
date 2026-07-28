# AGENTS.md: pb-orca-mcp

Instructions for AI coding agents working on **this repository's code** (the
cross-tool [AGENTS.md](https://agents.md) format, read by Codex, Cursor,
Copilot, Zed, Claude Code, …). This is the agent-facing companion to
[`CONTRIBUTING.md`](CONTRIBUTING.md), not the guide for end users driving the MCP
server (they read the [README](README.md) and [`docs/`](docs/)).

**Contributing needs no AI.** If you *are* an AI agent contributing here,
**follow [`CONTRIBUTING.md`](CONTRIBUTING.md)**: it is the source of truth for
setup, the `pytest` / `ruff` / `mypy` checks, code style, and the PR process.
This file does not restate it; it adds only the domain knowledge that guide is
not the place for.

## Context

`pb-orca-mcp` is a **Python MCP server** that exposes PowerBuilder's ORCA API
as MCP tools, letting any MCP agent (any client, any model) drive PB headless:
inspect PBLs, compile entries, rebuild targets, build EXE / PBD / dynamic
library. General-purpose, audience: anyone developing PowerBuilder who wants
an agentic workflow.

## Architectural constraints

- **This is a Python repo that talks *to* PowerBuilder via the DLL: no
  PowerBuilder syntax lives here.** Nothing parses, formats or validates
  PowerScript. If a change would require understanding the language, it belongs
  in another tool.
- **ORCA writes the `.sr*` files, never us.** The server does put source files
  on disk, but only through `PBORCA_ConfigureSession` +
  `PBORCA_LibraryEntryExportEx` in write-to-file mode, so the bytes come from
  the same engine the IDE uses. Do not hand-assemble an export header, a BOM,
  or CRLF line endings anywhere in this codebase.
- **The two forms move together.** Any tool that writes to a `.pbl` must also
  update the `ws_objects/` projection when the project has one. That is the
  single guarantee the design exists to provide; adding a mutating tool without
  a `sync_sources` path is a bug.
- **No git subprocess.** Git presence is detected from the filesystem
  (`workspace.find_git_root`). The server never runs `git`, so it works where
  git is not installed and cannot hang on a prompt.
- **No OrcaScript / batch-build workflow**: legacy batch/release path, out of scope.
- **No dependency on sibling projects.** Runtime dependencies are `mcp`,
  `pydantic`, `click`. Installing from the GitHub repo has to be the whole
  story.

## Gotchas

### Discovery / arch / OS

- **Multi-version**: the loader handles any install with `<install>\IDE\pborc.dll`.
  `KNOWN_VERSIONS = ("19.0","22.0","25.0")` are only the tested ones; others are
  found and marked `tested: false`. ORCA ABI stable since PB 2019.
- **IDE vs runtime**: discovery filters out runtime-only installs (no `pborc.dll`).
- **x86 vs x64**: Python must run in the same arch as the loaded DLL (see
  `docs/setup.md`).
- **Windows paths**: `/` is accepted on input and normalized internally with `Path`.

### ORCA / ctypes

- **Single-session per process and not thread-safe**: a global `asyncio.Lock`
  wraps every ORCA call.
- **Callback lifetime**: `WINFUNCTYPE` callbacks are kept in
  `Session._callback_refs` to avoid GC during the C calls (otherwise a silent crash).

### Source format / compile

- **`PBORCA_CompileEntryImport` lSrcSize is in BYTES, not chars** → for UTF-16
  LE, `len(syntax) * 2` (NOT `+1`, NOT `len`). A wrong value makes ORCA scan
  half the bytes and abort with `C0114 "Error scanning object source entry"`.
  Regression sentinel: `test_compile_entry_import_happy_path_application` in
  `tests/test_session_real.py`. Same for `compile_entry_import_list`.
- **The export header is NOT required on import.** ORCA ignores
  `$PBExportHeader$` / `$PBExportComments$` lines in `syntax` — body-only,
  header+body and whole-file-from-disk all import cleanly (verified on PB 22.0,
  update and create; pinned by `test_import_accepts_body_header_and_whole_file`).
  Earlier docs in this repo claimed the header was mandatory; that was a
  misdiagnosis of the `lSrcSize` bug above, which produces the same `C0114`.
  `library_entry_export` returns the body without those lines because they
  belong to the file format, not to the object.
- **PB export files (`.sra`/`.srf`/`.srw`/…)** = BOM + `$PBExportHeader$` +
  optional `$PBExportComments$` + body, CRLF throughout, in the encoding the
  `.pbw` `DefaultExportEncode` declares. Marked binary in `.gitattributes` so
  the fixtures survive round-tripping.
- **Never translate newlines when reading a `.sr*`.** Importing LF-normalized
  text succeeds and rewrites every line in the `.pbl`, producing a whole-file
  phantom diff on the next export. `workspace.read_source_file` reads bytes and
  decodes; do not replace it with `Path.read_text`.
- **`eExportEncoding` poisons the in-memory path too.** Set to UTF-8, ORCA packs
  UTF-8 bytes into the wide buffer and the decoded string is mojibake that then
  imports "successfully" and destroys the object. `Session._require_buffer_export_config`
  is the guard; keep it in front of every buffer export/import.
- **`eClobber` = `PBORCA_CLOBBER (1)` is the only value that overwrites.** The
  other three, including `CLOBBER_ALWAYS`, return `PBORCA_OBJEXISTS (-8)`.
- **The export directory must exist** — ORCA does not create it and returns
  `PBORCA_OBJEXISTS (-8)`.
- **Empty-PBL bootstrap catch-22**: `SessionSetCurrentAppl` rejects a
  non-existent app_name (`PBORCA_OBJNOTFOUND -3`), but `CompileEntryImport`
  requires current_app set even to import the FIRST application. No in-API way
  to create the initial app → pre-built PBL fixtures
  (`tests/fixtures/tiny_app/`, `tests/fixtures/ws_app/`).
- **`compile_entry_import` is not atomic**: on error ORCA still writes the
  source (possibly truncated) into the `.pbl` → a failed import can corrupt the
  entry. If you need atomicity, snapshot the bytes pre-call and restore on failure.
- **`pb_scc_refresh_target` has side effects**: it writes a flat `.sr*` export
  plus a `.pbg` into `local_proj_path`. Documented, not a bug, but it is why
  the per-object import loop is the recommended path.
- **`bExportIncludeBinary` is set on every file export**, and it is what writes
  the `Start of PowerBuilder Binary Data Section` block. Only **OLE/ActiveX
  controls** produce that block (verified by grepping a 2470-object codebase:
  exactly 2 hits, both `olecustomcontrol`-related, both carrying `binarykey`).
  A picture in a DataWindow does not — PB writes `bitmap(filename="…")`, a
  reference. Verified byte-identical against the IDE for an OLE-hosting window;
  dropping the flag shrank the same file from 10,934 to 2,760 bytes.
- **The OLE binary payload is deterministic within a PB build but not across
  builds.** Two consecutive exports match; an export from a newer PB than the
  one that wrote the committed file differed by 358 bytes, all inside the OLE
  compound-storage block. So on projects with OLE controls a sync can show a
  binary-only diff nobody caused. See `docs/how-it-works.md` §9.

## Design notes (why these choices)

- **Explicit PB version selection.** `pb_session_open` takes `pb_version` or
  `install_path`, never auto-picked. PB `.pbt`/`.pbw` files do **not** carry
  the PB version (only the frozen magic constant `Save Format v3.0(19990112)`),
  so there is nothing to infer from.
- **`.pbt` / `.pbw` format** (verified on real PB 19/22/25 files): `key "value";`
  lines, case-insensitive keywords (`LibList` ↔ `liblist`), C-string-escaped
  paths (`..\\dep\\x.pbl`), `LibList` separated by `;`. A `.pbw` lists targets in
  `@begin Targets … @end;` plus `DefaultTarget` / `DefaultExportEncode`. No PB
  version in either.
- **ORCA functions deliberately NOT exposed:** `PBORCA_BuildProject*` (deprecated
  in R3, use `ApplicationRebuild`); `PBORCA_LibraryEntryCopy` (redundant with
  `Move` + `Export` + `CompileEntryImport`); `Scc*` online / MSSCCI (only the
  offline git/svn flow is exposed = "Refresh PBL").
- **Functions that do NOT exist in ORCA** (verified against `PBORCA.H` 19/22/25):
  `PBORCA_LibraryEntryCommentModify`. Change an entry's comment by re-importing
  it with `CompileEntryImport` + a new `lpszComments`. (`PBORCA_LibraryCommentModify`
  exists, but edits the PBL's own comment.)

### Workspace detection

- **`workspace.py` must stay ORCA-free.** It is pure filesystem logic so it can
  be unit-tested on any machine, including CI with no PowerBuilder. Keep it
  that way.
- **The projection mirrors the library's relative path**:
  `<root>/src/app.pbl` → `<root>/ws_objects/src/app.pbl.src/`. Older workspaces
  keep one flat tree, so an existing `<lib>.pbl.src` found anywhere under
  `ws_objects/` wins over the computed path.
- **Encoding resolution order**: `.pbw` `DefaultExportEncode` → BOM sniffed off
  an existing `.sr*` → UTF-8. A declared value that disagrees with the files on
  disk is reported in `observed_encoding` rather than silently reconciled: the
  IDE will write what the `.pbw` says.
- **Whether the `.pbl` is tracked in git is the project's policy**, not ours.
  Both "commit the binary alongside the text" and "treat the binary as a build
  artifact" occur in the wild; the test workspace used during development is
  the second kind. Never assume either in code or docs.

## References

- Contributor guide (human, AI-free): [`CONTRIBUTING.md`](CONTRIBUTING.md).
- The model and the verified ORCA behaviour: [`docs/how-it-works.md`](docs/how-it-works.md).
- Contract for downstream tools: [`docs/integrating.md`](docs/integrating.md).
- ORCA Programmers Guide R3: <https://docs.appeon.com/pb2022r3/orca_guide>
- ORCA C header (canonical ABI): `<install>\SDK\ORCA\pborca.h`.
