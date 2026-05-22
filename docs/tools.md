# MCP tool reference

Every tool returns a JSON-friendly Python dict. Errors come back as
`{"error": {"code", "name", "message"}}`; success payloads are tool-specific.
ORCA error codes are mapped to their symbolic name (e.g. `PBORCA_OBJNOTFOUND`)
via `ORCA_ERROR_NAMES`. Errors originating from the server wrapper itself
(state guards, argument validation) use names prefixed with `PB_ORCA_MCP_*`.

Tools are grouped by functional area.

---

## Discovery

### `pb_discover_pb_install()`

Enumerate PowerBuilder IDE installations on the local machine.

**Input**: none.

**Output**:
```json
{
  "ide_installations": [
    {
      "version": "22.0",
      "file_version": "22.2.0.3397",
      "product_version": "2022 R3 Build 3397",
      "arch": "x86",
      "install_path": "C:\\Program Files (x86)\\Appeon\\PowerBuilder 22.0",
      "ide_path": "C:\\Program Files (x86)\\Appeon\\PowerBuilder 22.0\\IDE",
      "orca_dll": "C:\\Program Files (x86)\\Appeon\\PowerBuilder 22.0\\IDE\\pborc.dll",
      "tested": true,
      "source": "registry"
    }
  ],
  "runtime_only_installations": [
    {"path": "C:\\...\\Runtime 22.0", "reason": "pborc.dll missing under IDE/", "version": "22.0"}
  ]
}
```

`tested: true` means the major version is in the project's `KNOWN_VERSIONS`
tuple (`19.0`, `22.0`, `25.0`) — the actively tested set. Untested majors
are still returned with `tested: false`; load is attempted optimistically.

### `pb_target_info(path)`

Parse a PowerBuilder `.pbt` (target) or `.pbw` (workspace) file. Does **not**
return the PB version — `.pbt`/`.pbw` carry only the file-format magic
constant (`Save Format v3.0(19990112)` since 1999), not a release marker.
Version selection must be explicit on `pb_session_open`.

**Input**: `{"path": "C:\\projects\\foo\\foo.pbt"}`.

**Output** (`.pbt`):
```json
{
  "kind": "pbt",
  "target_name": "foo",
  "app_name": "foo",
  "app_lib": "foo.pbl",
  "lib_list": ["foo.pbl", "..\\dep\\bar.pbl"],
  "type": "pb"
}
```

**Output** (`.pbw`):
```json
{
  "kind": "pbw",
  "workspace_name": "myws",
  "targets": ["src\\main.pbt", "src\\tools.pbt"],
  "default_target": "src\\main.pbt"
}
```

---

## Session

### `pb_session_open(*, pb_version=None, install_path=None)`

Open the singleton ORCA session against a specific PB install. **Exactly one**
of `pb_version` or `install_path` is required. `install_path` wins if both
are passed. ORCA is single-session-per-process; calling `open` a second
time raises `PB_ORCA_MCP_STATEERROR`.

**Output** (success):
```json
{
  "ok": true,
  "pb_version": "22.0",
  "file_version": "22.2.0.3397",
  "product_version": "2022 R3 Build 3397",
  "arch": "x86",
  "install_path": "C:\\Program Files (x86)\\Appeon\\PowerBuilder 22.0",
  "orca_dll": "...",
  "tested": true
}
```

**Output** (errors): `PB_ORCA_MCP_INVALIDARGS` (neither arg supplied),
`PB_ORCA_MCP_VERSIONNOTFOUND`, `PB_ORCA_MCP_VERSIONAMBIGUOUS` (multiple installs
of the same major — disambiguate with `install_path`),
`PB_ORCA_MCP_INSTALLNOTFOUND` (path didn't match any discovered install),
`PB_ORCA_MCP_LOADFAILED` (DLL refused to load), `PB_ORCA_MCP_STATEERROR`
(session already open).

### `pb_session_close()`

Close the ORCA session if open. Idempotent.

**Output**: `{"ok": true, "was_open": <bool>}`.

### `pb_set_current_application(app_lib, app_name)`

Configure the current target's application object. `PBORCA_LIBLISTNOTSET (-5)`
is the most common error here — call `pb_set_library_list` first.

**Output** (success): `{"ok": true, "app_lib": "...", "app_name": "..."}`.

### `pb_set_library_list(libraries)`

Set the library list (`.pbl`/`.pbd` paths) for the current session. The
list cannot be empty. Path separators are passed through as-is to ORCA.

**Output** (success): `{"ok": true, "libraries": [...]}`.

---

## Library

### `pb_library_create(lib_path, comments="")`

Create an empty `.pbl` at `lib_path`. `comments` is the PBL-level comment.

### `pb_library_delete(lib_path)`

Delete a `.pbl` from disk.

### `pb_library_directory(lib_path, entry_type="any")`

List entries in a PBL. ORCA returns every entry via callback; the
`entry_type` filter is applied client-side after collection. Valid filters
correspond to `PBORCA_TYPE` names: `application`, `datawindow`, `function`,
`menu`, `query`, `structure`, `userobject`, `window`, `pipeline`, `project`,
`proxyobject`, `binary`, plus `any`.

**Output**:
```json
{
  "lib_path": "foo.pbl",
  "lib_comment": "PBL-level comment",
  "entry_type": "userobject",
  "count": 12,
  "entries": [
    {
      "name": "n_cst_main",
      "type": "userobject",
      "size": 12450,
      "create_time": 1717245734,
      "comment": "main application service"
    }
  ]
}
```

### `pb_library_entry_information(lib_path, entry_name, entry_type)`

Metadata for a single entry.

**Output**:
```json
{
  "name": "n_cst_main",
  "type": "userobject",
  "object_size": 8920,
  "source_size": 12450,
  "create_time": 1717245734,
  "comment": "..."
}
```

### `pb_library_entry_export(lib_path, entry_name, entry_type)`

Export the source of an entry as a string. The wrapper auto-resizes the
buffer (64 KiB initial, retries on `PBORCA_BUFFERTOOSMALL`).

**Output**: `{"lib_path", "entry_name", "entry_type", "source": "<text>"}`.

### `pb_library_entry_delete(lib_path, entry_name, entry_type)`

Remove a single entry from a PBL.

### `pb_library_entry_move(source_lib, dest_lib, entry_name, entry_type)`

Move an entry between PBLs.

### `pb_library_comment_modify(lib_path, comments)`

Update the PBL-level comment. **There is no per-entry comment-modify in
ORCA** — to change an entry's comment, re-import it via
`pb_compile_entry_import` with the new `comments` argument.

---

## Compile loop — the core agentic value

All compile/rebuild tools return `{"success": bool, "errors": [...]}`. The
`errors` array carries per-diagnostic dicts:

```json
{
  "level": 0,
  "level_name": "error",
  "message_number": "C0042",
  "message_text": "Undefined function: getfoo",
  "column": 8,
  "line": 142
}
```

`level_name` follows the convention `0=error / 1=warning / 2=information`
(the C header doesn't formalize this; raw `level` is always available).
`PBORCA_COMPERROR (-11)` and `PBORCA_LINKERROR (-12)` are **not** raised
as exceptions — they're normal "compile produced diagnostics" outcomes
and surface as `success: false` with populated `errors`.

### `pb_compile_entry_import(lib_path, entry_name, entry_type, syntax, comments="")`

Compile + import a single entry's source into a PBL. `syntax` is the full
PB-style source text including the `$PBExportHeader$<name>.<ext>` first line.

### `pb_compile_entry_import_list(items)`

Batch version. `items` is a list of dicts:

```json
[
  {
    "lib_path": "foo.pbl",
    "entry_name": "f_demo",
    "entry_type": "function",
    "syntax": "<text>",
    "comments": "optional"
  }
]
```

### `pb_edit_and_import(lib_path, entry_name, entry_type, syntax, source_path, comments="", source_encoding="UTF-8", format="auto")`

Atomic write-then-import. Persists `syntax` to `source_path` on disk
with the encoding PB IDE writes for the workspace, rebuilds the
canonical PB IDE export header block, and then imports `syntax` into
`lib_path`.

`source_encoding` accepts one of the three values PB IDE writes in the
`.pbw` `DefaultExportEncode` directive:

- `"UTF-8"` — UTF-8 with BOM (`EF BB BF`). Default in PB 2022 and
  observed across every Restore workspace surveyed.
- `"UTF-16BOM"` — UTF-16 LE with BOM (`FF FE`). PB legacy default
  pre-2019.
- `"ANSI"` — system codepage, no BOM. Older Windows workspaces only.

The caller should read `DefaultExportEncode` from the target's `.pbw`
and pass the matching value. Mismatched encoding silently triggers a
refresh cascade in PB IDE: the IDE re-exports the file using the
workspace's configured encoding on the next Refresh, producing a
"phantom" diff against what the tool wrote. ORCA itself is
encoding-agnostic — strings cross the C ABI as wide chars — so
`source_encoding` only affects the on-disk representation.

The header block is reconstructed from scratch on every call:

- Line 1: `$PBExportHeader$<entry_name>.<ext>`
- Line 2 (only when `comments` is non-empty):
  `$PBExportComments$<escaped>` where `<escaped>` applies PowerScript
  escape sequences to control characters — `~r` for CR, `~n` for LF
  (so a CRLF-bearing comment becomes `…~r~n…`), `~t` for TAB, and
  `~~` for `~` itself. Before escape, the `comments` string is
  normalized so every newline style (CRLF / LF / CR) is stored as
  CRLF; otherwise the Library Painter Properties dialog would render
  bare LF without a visible line break (Windows multi-line edit
  control behavior). The end result matches PB IDE's own export
  format byte for byte, so the IDE's next Refresh on the entry is a
  no-op rather than triggering an import + compile + regenerate
  cascade.

Any `$PBExportHeader$` / `$PBExportComments$` lines the caller leaves
at the top of `syntax` are stripped before rebuild — the `comments`
parameter is the single source of truth for entry comment metadata.

Replaces the three-step "agent writes file + agent re-encodes + agent
calls `pb_compile_entry_import`" pattern with a single call. Same
response shape as `pb_compile_entry_import` plus `source_path` echoed
back. A `UnicodeEncodeError` (text contains characters outside the
chosen codepage, typically with `"ANSI"`) surfaces as
`PB_ORCA_MCP_ENCODINGERROR`.

The on-disk extension is derived from `entry_type` via the
`ENTRY_TYPE_EXTENSIONS` map in `pb_orca_mcp.orca.constants` (`sru`,
`srw`, `srf`, `srd`, `srm`, `srs`, `sra`, `srp`, `srq`). Entry types
without a canonical source extension (`project`, `proxyobject`,
`binary`) raise `PB_ORCA_MCP_INVALIDARGS`.

`source_path` parent directories must already exist; the write is
atomic (temp-file + replace on the same volume). On filesystem error
the tool returns `PB_ORCA_MCP_IOERROR`.

The optional `format` parameter (`"auto"` / `True` / `False`,
default `"auto"`) controls the PowerScript body normalizer. In
`"auto"` mode the tool walks up from `source_path` looking for a
`.pb-format.toml`; when found, it normalizes the body (indent,
keyword case, operator spacing, line endings) before writing. With
no config file in any ancestor directory, behaviour is identical to
the pre-formatter contract. `True` forces the normalizer on with
defaults if no config is discovered; `False` skips it entirely.
DataWindow entries and entry types without a `.sr*` extension are
always skipped regardless of `format`. A malformed `.pb-format.toml`
surfaces as `PB_ORCA_MCP_INVALIDARGS` before any disk side-effect.
See [`formatter.md`](formatter.md) for the schema and the four
invariants.

**Output**: `{"success", "lib_path", "entry_name", "entry_type",
"source_path", "formatted", "errors": [...]}`. `formatted` is `true`
when the body was normalized, `false` otherwise.

### `pb_application_rebuild(rebuild_type="incremental")`

Full / incremental / migrate / 3-pass rebuild of the current application.
Valid `rebuild_type`: `"full"`, `"incremental"`, `"migrate"`, `"3pass"`.

Requires `pb_session_open` + `pb_set_library_list` + `pb_set_current_application`.

### `pb_get_last_compile_errors()`

Replay diagnostics from the most recent compile/rebuild call. Useful when
a caller discarded the originating response.

**Output**: `{"errors": [...]}` (empty list if no compile has run).

---

## Build artifacts

### `pb_executable_create(exe_name, *, icon_name=None, pbr_name=None, flags=None, pbd_flags=None, exe_info=None)`

Build a standalone `.exe` for the current application. Returns
`{"success", "exe_name", "errors": [...]}` with link errors when present.

`flags`: list of flag names OR-folded into `lFlags`:

| Flag name | `PBORCA_*` constant | Meaning |
|---|---|---|
| `machine_code` | `PBORCA_MACHINE_CODE` | Compile to machine code (default: p-code) |
| `optimize_speed` | `PBORCA_MACHINE_CODE_OPT_SPEED` | Optimize for speed (default: none) |
| `optimize_space` | `PBORCA_MACHINE_CODE_OPT_SPACE` | Optimize for size |
| `trace_info` | `PBORCA_TRACE_INFO` | Embed trace info |
| `error_context` | `PBORCA_ERROR_CONTEXT` | Embed runtime error context (line numbers) |
| `new_visual_style` | `PBORCA_NEW_VISUAL_STYLE_CONTROLS` | Use XP-and-later visual style controls |
| `x64` | `PBORCA_X64` | x64 deployment |

`pbd_flags`: list-of-lists of flag names, one inner list per non-application
PBL in the library list. When present, ORCA generates a `.pbd` per element.
`None` (default) skips PBD generation.

`exe_info`: optional dict for the EXE's Windows `VS_VERSION_INFO` resource:
`company_name`, `product_name`, `description`, `copyright`, `file_version`,
`file_version_num`, `product_version`, `product_version_num`, `manifest_info`.
Each populated value lands in the produced EXE; omitted keys are left
unset.

### `pb_dynamic_library_create(lib_path, *, pbr_name=None, flags=None)`

Build a single `.pbd` from a `.pbl`. No link callback (the C API doesn't
expose one for this entry point) — failures surface as the raw ORCA return
code in an `error` envelope.

---

## Object queries

### `pb_object_query_hierarchy(lib_path, entry_name, entry_type)`

Walk the inheritance chain of an entry. Returns the ancestor list closest-
first, not including the entry itself.

**Output**: `{"lib_path", "entry_name", "entry_type", "ancestors": ["base", "nonvisualobject"]}`.

### `pb_object_query_reference(lib_path, entry_name, entry_type)`

List the entries that the named object references — its **outgoing**
dependencies (callees, ancestors used, types declared, windows opened,
etc.). This is the outgoing direction of the cross-reference graph;
ORCA does not expose an incoming-direction primitive, so finding
"who calls this entry" requires inverting the index by querying every
candidate caller in the library list.

**Output**:
```json
{
  "lib_path": "foo.pbl",
  "entry_name": "n_cst_lib",
  "entry_type": "userobject",
  "count": 5,
  "references": [
    {
      "library": "main.pbl",
      "entry_name": "w_main",
      "entry_type": "window",
      "ref_type": "open"
    }
  ]
}
```

`ref_type` is `"simple"` (declarative reference) or `"open"` (runtime open).

### `pb_object_regenerate(lib_path, entry_name, entry_type)`

Re-emit object code for a single entry, without touching its source. Same
response shape as the compile tools: `{"success", "errors", ...}`.

---

## Error name reference

`PB_ORCA_MCP_*` codes (from the server wrapper):

| Name | Meaning |
|---|---|
| `PB_ORCA_MCP_INVALIDARGS` | Caller-supplied argument failed validation |
| `PB_ORCA_MCP_STATEERROR` | Operation requires (or forbids) an open session |
| `PB_ORCA_MCP_VERSIONNOTFOUND` | No PB install with the requested `pb_version` |
| `PB_ORCA_MCP_VERSIONAMBIGUOUS` | Multiple installs share a major — pass `install_path` |
| `PB_ORCA_MCP_INSTALLNOTFOUND` | `install_path` didn't match a discovered install |
| `PB_ORCA_MCP_LOADFAILED` | `WinDLL` refused to load `pborc.dll` |

`PBORCA_*` codes (passed through from the ORCA C API): see
`PBORCA.H` in your PB SDK or `src/pb_orca_mcp/orca/constants.py` for the
full list (`PBORCA_OK = 0` and 33 negative codes).
