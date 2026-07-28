"""MCP tools for compilation and rebuild — the core agentic loop.

Closes the "edit → compile → read errors → fix" cycle for PowerBuilder.

Tools exposed:
- `pb_compile_entry_import(lib_path, entry_name, entry_type, syntax, comments="")`:
  import + compile a single entry from source text. Returns
  `{"success", "errors": [...]}`. Errors carry `level`, `level_name`,
  `message_number`, `message_text`, `column`, `line`.
- `pb_compile_entry_import_list(items)`: batch import. `items` is a list of
  dicts with the same keys as the single-entry call.
- `pb_application_rebuild(rebuild_type)`: full/incremental/migrate/3pass
  rebuild of the current application. Requires `pb_session_open` +
  `pb_set_library_list` + `pb_set_current_application` first.
- `pb_get_last_compile_errors()`: replays the diagnostics from the most
  recent compile/rebuild call. Useful when a caller dropped the response
  of the originating call.

These take the source as a string, which suits a small edit an agent can hold
in context. For the ordinary case — read an object, edit it with file tools,
put it back — `pb_object_export_file` / `pb_object_import_file` in
`tools.source` are the better pair.

Both import tools mirror the change into the project's `ws_objects/` text
projection when it has one, so a `.pbl` write and its reviewable text form
always land together. Pass `sync_sources="never"` to opt out.

ORCA returns `PBORCA_COMPERROR (-11)` and `PBORCA_LINKERROR (-12)` when
compile produced diagnostics — these are not raised as Python exceptions;
the wrapper surfaces them as `success: False` with populated `errors`.
Any other negative return code becomes an OrcaError envelope.
"""

from __future__ import annotations

from typing import Any

from pb_orca_mcp import workspace as ws
from pb_orca_mcp.orca.errors import OrcaError
from pb_orca_mcp.orca.session import Session, SessionStateError
from pb_orca_mcp.tools.source import SYNC_MODES, sync_entry


def pb_compile_entry_import(
    lib_path: str,
    entry_name: str,
    entry_type: str,
    syntax: str,
    comments: str = "",
    sync_sources: str = "auto",
) -> dict[str, Any]:
    """Compile + import a single entry's source into a PBL.

    `syntax` is the object's complete source; ORCA ignores any
    `$PBExportHeader$` / `$PBExportComments$` lines it carries, so both an
    exported body and the full contents of a `.sr*` file are valid input. The
    object's comment comes from `comments`.

    On success the matching `ws_objects/` file is rewritten through ORCA when
    the project keeps one (`sync_sources="auto"`), so the change is visible to
    git in both forms.
    """
    if sync_sources not in SYNC_MODES:
        return _error(
            "PB_ORCA_MCP_INVALIDARGS",
            f"sync_sources must be one of {SYNC_MODES}, got {sync_sources!r}",
        )
    session = Session.instance()
    try:
        success, errors = session.compile_entry_import(
            lib_path, entry_name, entry_type, syntax, comments
        )
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except ValueError as exc:
        return _error("PB_ORCA_MCP_INVALIDARGS", str(exc))
    except OrcaError as exc:
        return {"error": exc.to_dict(), "errors": session.last_compile_errors}
    result = {
        "success": success,
        "lib_path": lib_path,
        "entry_name": entry_name,
        "entry_type": entry_type,
        "errors": errors,
    }
    if success:
        info = ws.describe(lib_path)
        result.update(sync_entry(session, info, entry_name, entry_type, sync_sources))
    else:
        result["synced_files"] = []
    return result


def pb_compile_entry_import_list(
    items: list[dict[str, Any]], sync_sources: str = "auto"
) -> dict[str, Any]:
    """Compile + import a batch of entries in a single ORCA call.

    Faster than looping over `pb_compile_entry_import`: ORCA compiles the whole
    batch together and reuses parser state. All diagnostics land in one
    `errors` array; ORCA prefixes each `message_text` with the object name.

    Because the batch either compiles or does not, the projection is synced for
    every item only when the whole batch succeeds.
    """
    if sync_sources not in SYNC_MODES:
        return _error(
            "PB_ORCA_MCP_INVALIDARGS",
            f"sync_sources must be one of {SYNC_MODES}, got {sync_sources!r}",
        )
    session = Session.instance()
    try:
        success, errors = session.compile_entry_import_list(items)
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except ValueError as exc:
        return _error("PB_ORCA_MCP_INVALIDARGS", str(exc))
    except KeyError as exc:
        return _error("PB_ORCA_MCP_INVALIDARGS", f"missing required key in items: {exc}")
    except OrcaError as exc:
        return {"error": exc.to_dict(), "errors": session.last_compile_errors}
    synced: list[str] = []
    if success:
        described: dict[str, ws.WorkspaceInfo] = {}
        for item in items:
            lib_path = item["lib_path"]
            if lib_path not in described:
                described[lib_path] = ws.describe(lib_path)
            synced.extend(
                sync_entry(
                    session,
                    described[lib_path],
                    item["entry_name"],
                    item["entry_type"],
                    sync_sources,
                )["synced_files"]
            )
    return {
        "success": success,
        "count": len(items),
        "errors": errors,
        "synced_files": synced,
    }


def pb_application_rebuild(rebuild_type: str = "incremental") -> dict[str, Any]:
    """Full / incremental / migrate / 3pass rebuild of the current application.

    Requires the session to be opened, library list set, and current
    application configured.
    """
    session = Session.instance()
    try:
        success, errors = session.application_rebuild(rebuild_type)
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except ValueError as exc:
        return _error("PB_ORCA_MCP_INVALIDARGS", str(exc))
    except OrcaError as exc:
        return {"error": exc.to_dict(), "errors": session.last_compile_errors}
    return {"success": success, "rebuild_type": rebuild_type, "errors": errors}


def pb_get_last_compile_errors() -> dict[str, Any]:
    """Replay the diagnostics from the most recent compile/rebuild call.

    Returns an empty list if no compile has run on the open session, or if
    no session is open.
    """
    return {"errors": Session.instance().last_compile_errors}


def _error(name: str, message: str) -> dict[str, Any]:
    return {"error": {"code": -1, "name": name, "message": message}}
