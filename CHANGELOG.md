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
- `pb-orca-mcp doctor` diagnostic command.
- Two optional cross-agent skills (`pb-orca`, `pb-workflow`) in
  [`skills/`](skills/), written to the [Agent Skills](https://agentskills.io)
  `SKILL.md` standard, plus [`AGENTS.md`](AGENTS.md) agent instructions in the
  cross-tool [agents.md](https://agents.md) standard.
- Documentation: [`docs/how-it-works.md`](docs/how-it-works.md) (the model
  everything derives from), [`docs/setup.md`](docs/setup.md) (install and
  per-client registration), [`docs/usage.md`](docs/usage.md) (recipes),
  [`docs/tools.md`](docs/tools.md) (tool reference, kept in sync with the
  registry by a CI guard), and [`docs/integrating.md`](docs/integrating.md)
  (the contract for tools built on top of this one).

### Corrected

- Earlier drafts of the documentation stated that
  `PBORCA_CompileEntryImport` **requires** a `$PBExportHeader$` line as the
  first line of the source. It does not: ORCA ignores that line and
  `$PBExportComments$` if present. The original symptom was a `C0114` caused
  by passing a character count where `lSrcSize` wants bytes. All three input
  shapes — body only, header + body, whole file from disk — are now covered
  by a test.
