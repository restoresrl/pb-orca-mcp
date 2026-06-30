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
- `.pbt` / `.pbw` parser (`pb_target_info`).
- The ORCA surface as tools: session lifecycle, library operations, the
  compile/import loop, application rebuild, EXE/PBD build, object
  hierarchy/reference queries, and the offline SCC "Refresh PBL" flow.
- `pb-orca-mcp doctor` diagnostic command.
- Two optional cross-agent skills (`pb-orca`, `pb-workflow`) in the
  [Agent Skills](https://agentskills.io) `SKILL.md` standard, plus
  [`AGENTS.md`](AGENTS.md) agent instructions in the cross-tool
  [agents.md](https://agents.md) standard.
- Documentation: [`docs/setup.md`](docs/setup.md) (install and per-client
  registration), [`docs/tools.md`](docs/tools.md) (tool reference, kept in
  sync with the registry by a CI guard), and [`docs/usage.md`](docs/usage.md)
  (recipes plus the `.pbl` ↔ `ws_objects/` editing model).
