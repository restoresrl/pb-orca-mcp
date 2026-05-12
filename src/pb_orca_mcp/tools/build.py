"""MCP tools for building EXE / PBD artifacts.

Tools:
- `pb_executable_create(exe_name, *, icon_name, pbr_name, flags, pbd_flags, exe_info)`
- `pb_dynamic_library_create(lib_path, *, pbr_name, flags)`

Flag names accepted (see `BUILD_FLAG_NAMES`):
  `machine_code`, `trace_info`, `error_context`, `optimize_speed`,
  `optimize_space`, `new_visual_style`, `x64`. p-code is the default.

`pbd_flags` is a list-of-lists: one inner list per PBL that the application
links via the library list (excluding the application PBL itself). If
provided, ORCA generates a `.pbd` per element with the given flags. Pass
`None` (default) to skip PBD generation.

`exe_info` is an optional dict — if provided, the wrapper calls
`PBORCA_SetExeInfo` before `ExecutableCreate`. Keys: `company_name`,
`product_name`, `description`, `copyright`, `file_version`,
`file_version_num`, `product_version`, `product_version_num`,
`manifest_info`. Each populated value lands in the produced EXE's
VS_VERSION_INFO resource.

The session must be open with a current application configured before
calling these tools (`pb_session_open` + `pb_set_library_list` +
`pb_set_current_application`).
"""

from __future__ import annotations

from typing import Any

from pb_orca_mcp.orca.errors import OrcaError
from pb_orca_mcp.orca.session import Session, SessionStateError


def pb_executable_create(
    exe_name: str,
    *,
    icon_name: str | None = None,
    pbr_name: str | None = None,
    flags: list[str] | None = None,
    pbd_flags: list[list[str]] | None = None,
    exe_info: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Build a standalone `.exe` for the current application."""
    session = Session.instance()
    try:
        success, errors = session.build_executable(
            exe_name,
            icon_name=icon_name,
            pbr_name=pbr_name,
            flags=flags,
            pbd_flags=pbd_flags,
            exe_info=exe_info,
        )
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except ValueError as exc:
        return _error("PB_ORCA_MCP_INVALIDARGS", str(exc))
    except OrcaError as exc:
        return {"error": exc.to_dict()}
    return {"success": success, "exe_name": exe_name, "errors": errors}


def pb_dynamic_library_create(
    lib_path: str,
    *,
    pbr_name: str | None = None,
    flags: list[str] | None = None,
) -> dict[str, Any]:
    """Build a `.pbd` from a single `.pbl`. No link callback (the C API
    doesn't expose one for this entry point) — failures surface as the
    raw ORCA return code."""
    session = Session.instance()
    try:
        session.build_dynamic_library(lib_path, pbr_name=pbr_name, flags=flags)
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except ValueError as exc:
        return _error("PB_ORCA_MCP_INVALIDARGS", str(exc))
    except OrcaError as exc:
        return {"error": exc.to_dict()}
    return {"ok": True, "lib_path": lib_path}


def _error(name: str, message: str) -> dict[str, Any]:
    return {"error": {"code": -1, "name": name, "message": message}}
