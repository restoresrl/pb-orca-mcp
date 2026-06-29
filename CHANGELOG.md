# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `pb_edit_and_import` MCP tool: atomic write-then-import for a single
  entry. Persists `syntax` to disk in the workspace export encoding,
  rebuilds the `$PBExportHeader$` / `$PBExportComments$` block, then
  imports — replacing the three-step edit + re-encode + import pattern.
- Token-based PowerScript body formatter (`pb_orca_mcp.format`): four
  opt-in invariants (indent, line endings, keyword case, operator
  spacing), enabled per workspace by committing a `.pb-format.toml`.
  `pb_edit_and_import` gained a `format` parameter (`"auto"` / `True` /
  `False`, default `"auto"`).
- `pb-format` CLI (`detect` / `format` / `check`) console script for
  using the formatter offline, without an ORCA session. Preserves the
  export header and on-disk encoding (UTF-16 LE / UTF-8, with or without
  BOM); `check` exits non-zero on drift for pre-commit / CI use.

### Fixed

- Declare `tomli` as a runtime dependency on Python `< 3.11`. The
  formatter reads `.pb-format.toml`, and the format module is imported
  eagerly by the compile tools — without this the server crashed at
  import on a stock Python 3.10 interpreter.
- Lint and formatting brought back to a clean `ruff check` /
  `ruff format --check` so CI passes.

## [0.1.0] - 2026-05-13

### Added

- Initial release. MCP server wrapping the PowerBuilder ORCA API
  (`pborc.dll`) as tools, closing the edit → compile → read errors → fix
  loop for an AI coding agent.
- Multi-version discovery and a version-aware DLL loader (registry +
  filesystem scan, IDE vs runtime distinction, PE-arch detection).
- `.pbt` / `.pbw` parser (`pb_target_info`).
- Session lifecycle, library operations, the compile/import loop,
  application rebuild, EXE/PBD build, object hierarchy/reference queries,
  and the offline SCC "Refresh PBL" flow.
- `pb-orca-mcp doctor` diagnostic command.
- Documentation: installation, Claude Code setup, tool reference,
  recipes; design rationale in `PLAN.md`.

[Unreleased]: https://github.com/restoresrl/pb-orca-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/restoresrl/pb-orca-mcp/releases/tag/v0.1.0
