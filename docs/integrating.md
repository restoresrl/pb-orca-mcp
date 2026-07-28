# Integrating pb-orca-mcp into another tool

For people building something *on top of* this server — an agentic dev kit, a
migration script, a CI helper, a higher-level skill pack. It states the
contract you can rely on, the invariants you must not break, and the things
this server deliberately leaves to you.

If you are driving the server directly rather than wrapping it, read
[`recipes.md`](recipes.md) instead. If you want to know *why* the design is shaped
this way, read [`how-it-works.md`](how-it-works.md).

---

## 1. What the server is

A thin, faithful bridge from PowerBuilder's ORCA C API to MCP tools, plus the
minimum workspace awareness needed to keep a binary library and its text
projection from drifting apart.

**It is:**

- A **stdio MCP server**, a standard `mcpServers` entry, usable by any MCP
  client driving any model.
- **Self-contained**: a Python package with three dependencies (`mcp`,
  `pydantic`, `click`) and no dependency on any other tool of ours or anyone
  else's. Installing it from its GitHub repository is the whole story.
- **Stateful within a session** — the ORCA session handle, the library list and
  the current application live in the server process.

**It is not:**

- A PowerScript parser, formatter, or linter. It moves source bytes; it never
  interprets them. Any syntax knowledge in your tool stays in your tool.
- A release build runner. Batch/OrcaScript pipelines keep their job (see the
  anti-recipe in [`recipes.md`](recipes.md)).
- A git client. It reports whether git is watching; it never runs git.
- An orchestrator. It has no notion of a task, a plan, or a retry policy.

That boundary is the point: everything above the ORCA line is yours to build,
and nothing you build has to fight this server for the same responsibility.

---

## 2. The response contract

Every tool returns a JSON object. There are exactly two shapes.

**Success** — tool-specific fields, and either `ok: true` for imperative
operations or `success: <bool>` for anything that compiles:

```json
{"success": true, "entry_name": "w_main", "errors": [], "synced_files": ["..."], "sync": "ok"}
```

**Failure** — a single `error` envelope:

```json
{"error": {"code": -3, "name": "PBORCA_OBJNOTFOUND", "message": "..."}}
```

`name` is the symbolic ORCA constant when the failure came from ORCA, or a
`PB_ORCA_MCP_*` name when it came from the server's own validation and state
guards. `code` is the raw ORCA return code, or `-1` for server-originated
errors. The full list is in [`tools.md`](tools.md).

**Compile diagnostics are data, not errors.** A compile that produces
diagnostics returns `success: false` with a populated `errors` array — *not* an
`error` envelope. Treat these as the normal outcome of the edit loop:

```json
{"level": 0, "level_name": "error", "message_number": "C0042",
 "message_text": "Undefined function: getfoo", "column": 8, "line": 142}
```

`level_name` follows the conventional `0=error / 1=warning / 2=information`
mapping; the raw `level` is always present if you would rather not trust it.
`ORCA` link errors carry only `message_text` — the linker callback has no line
or column.

**Practical rule for a wrapper**: branch on `"error" in response` first, then on
`response["success"]`. Do not treat a compile failure as a tool failure, and do
not retry it blindly — the diagnostics are the point.

---

## 3. The session state machine

```text
[closed] --pb_session_open--> [open] --pb_set_library_list--> [libs set]
                                                    |
                                        pb_set_current_application
                                                    v
                                              [ready for compile/rebuild/query]
```

Constraints you must design around:

- **One ORCA session per process, and ORCA is not thread-safe.** The server
  enforces the single session and serializes calls. If you need two PB versions
  in one workflow, you need two server processes, or a close-and-reopen between
  phases — a process can only ever hold one PB runtime, because Windows caches
  the loaded `pbvm.dll` by basename.
- **Version selection is always explicit.** `pb_session_open` requires
  `pb_version` or `install_path`. There is no auto-pick, because `.pbt`/`.pbw`
  files do not record a PowerBuilder release. If your tool wants a default,
  choose it in your layer from `pb_discover_pb_install`, and say so to the user.
- **`pb_set_current_application` is a prerequisite** for compile, rebuild and
  object-query calls, and it may rewrite the `.pbw` as a side effect. If your
  workflow ends by inspecting `git status`, expect to advise reverting it.
- **The SCC flow configures the session itself.** `pb_scc_set_target` sets the
  library list and current application; calling those tools afterwards returns
  `PBORCA_DUPOPERATION (-2)`.
- **Sessions are not cheap to churn.** Open once per unit of work, not once per
  object.

---

## 4. The sync contract

This is the part most worth relying on, and the part with the sharpest edges.

**What is guaranteed.** Any tool that writes to a `.pbl` —
`pb_object_import_file`, `pb_compile_entry_import` and its list form,
`pb_library_entry_delete`, `pb_library_entry_move` — also updates the matching
`ws_objects/<lib>.pbl.src/<entry>.<ext>` file when the project has one, in the
same call, and reports what it touched:

| field | meaning |
| --- | --- |
| `sync: "ok"` | the projection was written (or removed) |
| `sync: "not_applicable"` | the project keeps no projection; nothing to do |
| `sync: "never"` | the caller passed `sync_sources="never"` |
| `sync: "failed"` | the write failed; `sync_error` says why. **The `.pbl` still changed.** |
| `synced_files` | absolute paths written |
| `removed_files` | absolute paths deleted |

**What is not guaranteed.**

- **Nothing is synced when the compile fails.** The `.pbl` may hold partial
  source — ORCA writes as it parses — while the text file still holds what the
  caller wrote. That asymmetry is deliberate: it is what lets an agent iterate
  on the file. Your retry logic should re-import the whole corrected file, not
  assume the entry is intact.
- **`sync: "failed"` leaves the two forms disagreeing.** Surface it; do not
  swallow it.
- **No transaction spans two tool calls.** If you need all-or-nothing across
  several objects, snapshot the `.pbl` yourself before you start.
- **The server never stages or commits.** Deciding what goes into a commit —
  and whether the `.pbl` is even tracked, which varies by project — is yours.

**Determinism you can lean on.** ORCA's file export is byte-stable: exporting
an object that did not change reproduces the same bytes. So "export everything,
then diff" is a valid way to detect drift, and a sync of an unchanged object
does not dirty the working tree.

---

## 5. Choosing between the file API and the string API

Both exist and both keep the projection in step.

**Use `pb_object_export_file` / `pb_object_import_file`** as the default. The
source never passes through your context as a tool argument, the file format is
handled by ORCA, and the entry name, type and comment are inferred from the
file. This is the flow designed for an agent that edits with ordinary file
tools.

**Use `pb_library_entry_export` / `pb_compile_entry_import`** when the object is
small, when you are applying a mechanical transform to a string you already
hold, or when you genuinely have no filesystem to write to. Remember that the
export returns the **body** (no header lines) and the import ignores header
lines if present — there is no asymmetry to compensate for.

**Use `pb_library_export_sources`** to read a whole library at once, or to
bootstrap a `ws_objects/` tree on a binary-only project.

Never construct a `.sr*` file yourself. See
[`how-it-works.md`](how-it-works.md) §5 for what goes wrong.

---

## 6. Discovery and environment

- `pb_discover_pb_install` enumerates every PB IDE install, with arch, file
  version and whether the major is in the tested set. Runtime-only installs are
  reported separately rather than silently dropped.
- **Arch matters.** The Python running the server must match `pborc.dll`
  (x86 through PB 2025). If your tool installs the server, pin the interpreter:
  `--python 3.12-x86`. `pb-orca-mcp doctor` is a non-MCP CLI that reports the
  whole picture and exits non-zero when nothing is usable — a good preflight
  for an installer.
- `PB_INSTALL_PATH` (single path or `;`-separated list) restricts discovery.
  Setting it in the server's `env` block is how you pin a version per server
  entry rather than per session.
- **Classic workspace format only.** ORCA does not operate on the PB 2025
  *solution* format (`.pbproj` + PBL folders). PB 2025 still supports classic
  workspaces, where this works.

---

## 7. Stability

Alpha, pre-1.0. What that means concretely:

- Tool **names** and the **error envelope shape** are the parts most worth
  depending on; they are meant to be stable and a change would be called out in
  [`CHANGELOG.md`](../CHANGELOG.md).
- Success payloads may gain fields. Read defensively: index by key, do not
  assume a fixed set.
- `docs/tools.md` is enforced against the live registry by a test, so it never
  silently drifts from what the server exposes. It is a safe thing to generate
  documentation from.
- ORCA's own behaviour is fixed by Appeon and has been ABI-stable since
  PB 2019, so the underlying semantics are not where churn will come from.

If you are building on this and need a guarantee that is not listed here, open
an issue and say what you are building — it is easier to make a promise
deliberately than to discover one was assumed.
