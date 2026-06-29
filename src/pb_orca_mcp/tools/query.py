"""MCP tools for object hierarchy and reference queries, plus single-object regen.

Tools:
- `pb_object_query_hierarchy(lib_path, entry_name, entry_type)`: return the
  ancestor chain (list of ancestor names, closest first).
- `pb_object_query_reference(lib_path, entry_name, entry_type)`: list the
  entries that the named object references — its **outgoing** dependencies
  (callees, ancestors used, types declared, windows opened, etc.). Each
  result has `library`, `entry_name`, `entry_type`, and `ref_type`
  (`simple`/`open`). ORCA does not expose an incoming-direction primitive;
  finding "who calls this entry" requires inverting the index.
- `pb_object_regenerate(lib_path, entry_name, entry_type)`: alias for
  `PBORCA_CompileEntryRegenerate` from phase 5 — re-emit object code for a
  single entry without touching the source.

All three require the session open + library list set. Hierarchy and
reference queries additionally need the current application configured.
"""

from __future__ import annotations

from typing import Any

from pb_orca_mcp.orca.errors import OrcaError
from pb_orca_mcp.orca.session import Session, SessionStateError


def pb_object_query_hierarchy(lib_path: str, entry_name: str, entry_type: str) -> dict[str, Any]:
    """Walk the ancestor chain of a single entry."""
    session = Session.instance()
    try:
        ancestors = session.object_query_hierarchy(lib_path, entry_name, entry_type)
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except ValueError as exc:
        return _error("PB_ORCA_MCP_INVALIDARGS", str(exc))
    except OrcaError as exc:
        return {"error": exc.to_dict()}
    return {
        "lib_path": lib_path,
        "entry_name": entry_name,
        "entry_type": entry_type,
        "ancestors": ancestors,
    }


def pb_object_query_reference(lib_path: str, entry_name: str, entry_type: str) -> dict[str, Any]:
    """List every entry that references the named object."""
    session = Session.instance()
    try:
        refs = session.object_query_reference(lib_path, entry_name, entry_type)
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except ValueError as exc:
        return _error("PB_ORCA_MCP_INVALIDARGS", str(exc))
    except OrcaError as exc:
        return {"error": exc.to_dict()}
    return {
        "lib_path": lib_path,
        "entry_name": entry_name,
        "entry_type": entry_type,
        "references": refs,
        "count": len(refs),
    }


def pb_object_regenerate(lib_path: str, entry_name: str, entry_type: str) -> dict[str, Any]:
    """Re-emit object code for a single entry. Returns `{success, errors}`."""
    session = Session.instance()
    try:
        success, errors = session.compile_entry_regenerate(lib_path, entry_name, entry_type)
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


def _error(name: str, message: str) -> dict[str, Any]:
    return {"error": {"code": -1, "name": name, "message": message}}
