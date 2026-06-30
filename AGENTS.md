# AGENTS.md — pb-orca-mcp

Instructions for AI coding agents working on **this repository's code** (the
cross-tool [AGENTS.md](https://agents.md) format, read by Codex, Cursor,
Copilot, Zed, Claude Code, …). This is the agent-facing companion to
[`CONTRIBUTING.md`](CONTRIBUTING.md) — **not** for end users driving the MCP
server (they read the [README](README.md) and [`docs/`](docs/)).

**Contributing needs no AI.** If you *are* an AI agent contributing here,
**follow [`CONTRIBUTING.md`](CONTRIBUTING.md)** — it is the source of truth for
setup, the `pytest` / `ruff` / `mypy` checks, code style, and the PR process.
This file does not restate it; it adds only the domain knowledge that guide is
not the place for.

## Context

`pb-orca-mcp` is a **Python MCP server** that exposes PowerBuilder's ORCA API
as MCP tools, letting any MCP agent (any client, any model) drive PB headless:
inspect PBLs, compile entries, rebuild targets, build EXE / PBD / dynamic
library. General-purpose — audience: anyone developing PowerBuilder who wants
an agentic workflow.

## Architectural constraints

- **This is a Python repo that talks *to* PowerBuilder via the DLL — no
  PowerBuilder syntax lives here.**
- **Pure ORCA: never write `.sr*` files to disk.** The server works in-memory →
  `.pbl`. Writing the source-of-truth file (the `$PBExportHeader$` header +
  encoding/BOM + CRLF) is the caller's job (see `docs/usage.md` Recipe 1.5);
  this repo is independent of any external tool for that step.
- **No PowerGen / OrcaScript / `.gen` files** — legacy batch workflow, out of scope.

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
- **PB export (`.sra`/`.srf`/`.srw`/…)** = UTF-16 LE + BOM + CRLF + first line
  `$PBExportHeader$<name>.<ext>`. Marked binary in `.gitattributes`.
- **Export/import asymmetry**: `library_entry_export` returns **only the body**;
  `compile_entry_import` **requires** the header. No direct round-trip without
  re-attaching it. See `docs/usage.md` Recipe 1.
- **Empty-PBL bootstrap catch-22**: `SessionSetCurrentAppl` rejects a
  non-existent app_name (`PBORCA_OBJNOTFOUND -3`), but `CompileEntryImport`
  requires current_app set even to import the FIRST application. No in-API way
  to create the initial app → pre-built PBL fixture
  (`tests/fixtures/tiny_app/genapp.pbl`).
- **`compile_entry_import` is not atomic**: on error ORCA still writes the
  source (possibly truncated) into the `.pbl` → a failed import can corrupt the
  entry. If you need atomicity, snapshot the bytes pre-call and restore on failure.

## Design notes (why these choices)

- **Explicit PB version selection.** `pb_session_open` takes `pb_version` or
  `install_path` — never auto-picked. PB `.pbt`/`.pbw` files do **not** carry
  the PB version (only the frozen magic constant `Save Format v3.0(19990112)`),
  so there is nothing to infer from.
- **`.pbt` / `.pbw` format** (verified on real PB 19/22/25 files): `key "value";`
  lines, case-insensitive keywords (`LibList` ↔ `liblist`), C-string-escaped
  paths (`..\\dep\\x.pbl`), `LibList` separated by `;`. A `.pbw` lists targets in
  `@begin Targets … @end;` plus `DefaultTarget` / `DefaultExportEncode`. No PB
  version in either.
- **ORCA functions deliberately NOT exposed:** `PBORCA_BuildProject*` (deprecated
  in R3 — use `ApplicationRebuild`); `PBORCA_LibraryEntryCopy` (redundant with
  `Move` + `Export` + `CompileEntryImport`); `Scc*` online / MSSCCI (only the
  offline git/svn flow is exposed = "Refresh PBL").
- **Functions that do NOT exist in ORCA** (verified against `PBORCA.H` 19/22/25):
  `PBORCA_LibraryEntryCommentModify` — change an entry's comment by re-importing
  it with `CompileEntryImport` + a new `lpszComments`. (`PBORCA_LibraryCommentModify`
  exists, but edits the PBL's own comment.)

## References

- Contributor guide (human, AI-free): [`CONTRIBUTING.md`](CONTRIBUTING.md).
- ORCA Programmers Guide R3: <https://docs.appeon.com/pb2022r3/orca_guide>
- ORCA C header (canonical ABI): `<install>\SDK\ORCA\pborca.h`.
