# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

No stable version has been published yet; the project is in internal
dogfooding. Everything below is the content of the first release.

### Added

- MCP server that exposes the PowerBuilder ORCA API (`pborc.dll`) as MCP
  tools, closing the edit → compile → read errors → fix loop for an AI
  coding agent. Usable from any MCP client (Claude Code, Cursor, Codex CLI,
  …) and any model.
- Multi-version discovery and a version-aware DLL loader: registry +
  filesystem scan, IDE vs runtime distinction, PE-architecture detection.
- `.pbt` / `.pbw` parser (`pb_target_info`), including the
  `DefaultExportEncode` directive.
- The ORCA surface as tools: session lifecycle, library operations, the
  compile/import loop, application rebuild, EXE/PBD build, object
  hierarchy/reference queries, and the offline SCC "Refresh PBL" flow.
- **File-based editing loop.** `pb_object_export_file` has ORCA write an
  object's source to a `.sr*` file — byte-identical to the PB IDE's own
  output — and `pb_object_import_file` compiles it back, inferring the entry
  name, type and comment from the file. Nothing in the server parses
  PowerScript, and no caller has to construct PowerBuilder's file format.
  `pb_library_export_sources` does the same for a whole library.
- **Workspace awareness.** `pb_workspace_info` reports, with no ORCA session
  and no PowerBuilder installed, whether a library keeps a `ws_objects/` text
  projection, where it is, which encoding it uses, whether git is watching,
  and where working files go otherwise.
- **Automatic `ws_objects/` sync.** Every tool that writes to a `.pbl` —
  `pb_object_import_file`, `pb_compile_entry_import` and its list form,
  `pb_library_entry_delete`, `pb_library_entry_move` — now updates the
  matching text file in the same call and reports what it touched, so a
  change is never half-applied. `sync_sources="never"` opts out.
- `pb_session_configure` (`PBORCA_ConfigureSession`): export encoding, export
  headers, write-to-file mode, import encoding, debug directive.
- **`pb-orca-mcp check <target>`**: point it at a `.pbw`, `.pbt` or `.pbl` and
  it runs the whole stack against that project — target parsing, workspace
  detection, install selection, DLL load, session, library read, and a real
  ORCA source export whose bytes it verifies. No MCP client involved, and
  nothing in the project is written, so it answers "does this work on *my*
  project" before any of it is wired to an assistant, and isolates the layer at
  fault when something breaks.
- `pb-orca-mcp doctor` diagnostic command.
- Two optional cross-agent skills (`pb-orca`, `pb-workflow`) in
  [`skills/`](skills/), written to the [Agent Skills](https://agentskills.io)
  `SKILL.md` standard, plus [`AGENTS.md`](AGENTS.md) agent instructions in the
  cross-tool [agents.md](https://agents.md) standard.
- Documentation, organized as a reading path rather than a pile: the README is
  a front door and an index, and each document under `docs/` has one job —
  [`getting-started.md`](docs/getting-started.md) (install to first compiled
  change), [`how-it-works.md`](docs/how-it-works.md) (the model everything
  derives from), [`recipes.md`](docs/recipes.md) (call sequences),
  [`tools.md`](docs/tools.md) (reference, kept in sync with the registry by a
  CI guard), [`troubleshooting.md`](docs/troubleshooting.md) (symptom → cause →
  fix, gathered in one place), and
  [`integrating.md`](docs/integrating.md) (the contract for tools built on top
  of this one).

### Corrected

- **The documented install command did not work on a clean machine.**
  `cryptography` — reached transitively through `mcp` → `pyjwt[crypto]` —
  stopped publishing 32-bit Windows wheels at 49.0, and this package must run
  on an x86 interpreter to load `pborc.dll`. So `uvx --python 3.12-x86`
  resolved the newest cryptography, found no win32 wheel, tried to build it
  from source, and failed on the Rust and OpenSSL toolchain. It only appeared
  to work where an environment had been built earlier, against a version that
  still had wheels. Constrained to `cryptography<49`; revisit if upstream
  ships win32 wheels again, or if `mcp` drops the `pyjwt[crypto]` dependency.
- The tool description of `pb_object_query_reference` stated the opposite of
  what it does — "list every entry that references the named object" — while
  the implementation, the ORCA callback and `docs/tools.md` all correctly
  described the outgoing direction. The docstring is what a model reads as the
  tool's description, so it was the copy that mattered. Both query tools now
  also state that "nothing to report" arrives as `PBORCA_OBJHASNOANCS (-14)`
  or `PBORCA_OBJHASNOREFS (-15)`, which mean empty rather than broken.
- Earlier drafts of the documentation stated that
  `PBORCA_CompileEntryImport` **requires** a `$PBExportHeader$` line as the
  first line of the source. It does not: ORCA ignores that line and
  `$PBExportComments$` if present. The original symptom was a `C0114` caused
  by passing a character count where `lSrcSize` wants bytes. All three input
  shapes — body only, header + body, whole file from disk — are now covered
  by a test.
