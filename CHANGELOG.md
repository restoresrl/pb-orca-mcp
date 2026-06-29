# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Refactored to keep `pb-orca-mcp` strictly an ORCA read/write server.
  Two things that briefly lived here were removed: the PowerScript style
  formatter, and the well-formed `.sr*` writer (export header +
  encoding/BOM). The short-lived `pb_edit_and_import` tool — which wrote
  the `.sr*` and imported in one call — is **removed**; the documented
  workflow is now to write the `.sr*` yourself (header + encoding/BOM +
  CRLF, see `docs/usage.md` Recipe 1.5), then call `pb_compile_entry_import`
  to import it. The `tomli` dependency is dropped. Tool count is 29.
- Documentation consolidated: `docs/recipes.md` + `docs/workflow.md` merged
  into a single [`docs/usage.md`](docs/usage.md). Internal development docs
  (dev process + design rationale) consolidated into a root `DEVELOPMENT.md`,
  kept out of the package; `CLAUDE.md` trimmed.

### Fixed

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
