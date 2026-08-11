# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.6] - 2026-08-11

### Corrected

- **`function_object` was rejected as an entry type.** A `.srf` file opens
  `global type gettext from function_object`, so that is the name anyone
  naming the type reads off the source — while ORCA's API calls the same
  thing `function`. The mismatch stopped an unattended apply loop dead on
  every global-function finding, with an error listing twelve valid names and
  not the one the file uses. Accepted as an alias now, and it appears in the
  error text so the next mismatch documents itself.
- The `advice` from `pb_workspace_info` told callers to run
  `git add --renormalize` with no pathspec — the exact form the skills that
  read this advice call an error, because bare it fails and the obvious repair
  (`git add --renormalize .`) stages every modified file, including review
  output that was deliberately left uncommitted. It carries the pathspec now.

## [0.2.5] - 2026-08-09

### Corrected

- The `bytes` field of `pb_object_export_file` and
  `pb_library_export_sources` is the size of the source text ORCA produced,
  not the size of the file on disk — a workspace with a byte-order mark writes
  that mark on top, so the file is larger by its length. Nothing said so, and
  a caller checking that two exports agree by comparing `bytes` against the
  file size gets a mismatch on every entry. Documented in the tool description
  and in `docs/tools.md`; the field itself is unchanged, since callers depend
  on it.

## [0.2.4] - 2026-08-09

### Corrected

- **v0.2.3 recommended the wrong rule.** It told callers to fix an unprotected
  workspace with `*.sr* binary`. That does stop the line-ending translation —
  and `binary` is a macro for `-diff -merge -text`, so git then answers
  `Binary files differ` for every change to a PowerBuilder object. It trades a
  silent-drift problem for an unreadable-diff one, and discards the reason a
  project keeps a text projection at all. The advice now says `*.sr* -text`,
  with `binary` kept for `*.pbl` and `*.pbd`, which really are opaque.

  Caught within hours, by an apply loop that followed the advice literally: it
  wrote the rule, renormalized, and the next `git diff` said `Binary files
  differ`.

### Added

- `pb_workspace_info` also reports **`sources_diffable`**, because *protected*
  and *reviewable* turn out to be different questions and the common advice
  answers the first by breaking the second. It is `false` when a rule marks
  the `.sr*` files `binary` or `-diff` — a state that reports as `protected`
  and would otherwise say nothing, which is how the mistake above survives in
  a repository once someone makes it. `advice` explains the swap.

## [0.2.3] - 2026-08-09

### Added

- `pb_workspace_info` now reports **`source_protection`**: whether a
  `.gitattributes` rule exempts the `.sr*` files from git's line-ending
  translation. `unprotected` is the dangerous value and the quiet one — git
  stores the sources with LF and checks them out with CRLF, so the index and
  the working tree differ by exactly the bytes ORCA writes. A change lands in
  the `.pbl` and in its projection while `git status` stays clean, and nobody
  sees the drift until a fresh checkout.

  This tool already answered "is git watching"; this is the other half of the
  same question, and the half that decides whether a write is reviewable. It
  is filesystem-only, like the rest of `workspace.py` — no `git` executable is
  invoked, so it still works where git is not installed and it cannot hang. It
  reports whether the protection *exists*; measuring what the index already
  holds needs `git ls-files --eol`, which is left to the caller.

  `eol=lf` counts as **unprotected**, which is the subtle case: it looks like
  a deliberate line-ending policy and it is, just the wrong one, since ORCA
  writes CRLF. `eol=crlf` is the same policy pointed the safe way. Partial
  coverage — some `.sr*` extensions exempted, others not — also counts as
  unprotected, because the files still being translated are exactly the ones
  nobody will think to check.

  `advice` leads with the warning and the fix when the value is `unprotected`.

  Found by running a real review against a repository where 56 of 61 sources
  were being normalized: nothing in the chain mentioned it.

## [0.2.2] - 2026-08-05

### Corrected

- **The server would not start.** `mcp` 2.0.0 removed `mcp.server.fastmcp`,
  which this server is built on, and the dependency had no upper bound — so
  any install resolving fresh got 2.x and died at startup on
  `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`. Pinned to
  `mcp>=1.0,<2`; lift the ceiling together with a port to the 2.x server API.

  Two things hid this. `doctor` and `check` never import the MCP layer, so
  the CLI kept working and looked like proof the package was fine. And the
  test suite only read the tool *registry*, a plain tuple, never calling
  `build_server()` — the one function that imports FastMCP. 196 tests were
  green against a build that could not serve a single request. There is now
  a test that builds the real server and counts its registered tools, so a
  resolution the server cannot run on fails in CI rather than in an editor.

## [0.2.1] - 2026-08-05

### Corrected

- `--version` reported `0.1.0` from a 0.2.0 install. `__version__` was a
  hardcoded string that the release bump missed; it now derives from the
  installed distribution's metadata, so it cannot drift from `pyproject.toml`
  again. Found by pinning an install to `@v0.2.0` and reading what it printed,
  which is the whole reason to pin.

## [0.2.0] - 2026-08-05

Nothing is published to PyPI yet. These tags exist so a team can pin a known
version instead of following the default branch, which is what an unpinned
`git+https://...` install does. `v0.1.0` was cut on 2026-05-13 and never
released anywhere, so this entry consolidates everything up to here.

**Breaking**: `pb_edit_and_import` was removed. The edit loop is
`pb_object_export_file` -> edit the file -> `pb_object_import_file`, which also
updates the text projection in the same call. Callers that used the old helper
have to move; there is no shim.

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
