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

ORCA returns `PBORCA_COMPERROR (-11)` and `PBORCA_LINKERROR (-12)` when
compile produced diagnostics — these are not raised as Python exceptions;
the wrapper surfaces them as `success: False` with populated `errors`.
Any other negative return code becomes an OrcaError envelope.
"""

from __future__ import annotations

from typing import Any

from pb_orca_mcp.orca.errors import OrcaError
from pb_orca_mcp.orca.session import Session, SessionStateError


def pb_compile_entry_import(
    lib_path: str,
    entry_name: str,
    entry_type: str,
    syntax: str,
    comments: str = "",
) -> dict[str, Any]:
    """Compile + import a single entry's source into a PBL."""
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
    return {
        "success": success,
        "lib_path": lib_path,
        "entry_name": entry_name,
        "entry_type": entry_type,
        "errors": errors,
    }


def pb_compile_entry_import_list(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Compile + import a batch of entries in a single ORCA call."""
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
    return {"success": success, "count": len(items), "errors": errors}


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
