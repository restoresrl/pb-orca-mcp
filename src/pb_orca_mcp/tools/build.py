"""MCP tools for building EXE / PBD artifacts.

Tools:
- `pb_executable_create(exe_name, *, icon_name, pbr_name, flags, pbd, pbd_flags, exe_info)`
- `pb_dynamic_library_create(lib_path, *, pbr_name, flags)`

Flag names accepted (see `BUILD_FLAG_NAMES`):
  `machine_code`, `trace_info`, `error_context`, `optimize_speed`,
  `optimize_space`, `new_visual_style`, `x64`. p-code is the default.

`pbd` is one boolean per library in the session library list, in order:
`True` for a library already deployed as a PBD/DLL (its objects stay out
of the exe), `False` to link it in. `None` links everything. ORCA requires
exactly one entry per library and a non-NULL icon; the wrapper fills both
(a bundled default icon) so the plain call works. `pbd_flags` is the older
list-of-lists spelling; only masks 0 and 1 are accepted.

Existing outputs are rejected. Build to a new path, check the result, then
replace the old deployment explicitly. A failure may leave a partial output.

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
    pbd: list[bool] | None = None,
) -> dict[str, Any]:
    """Build a standalone `.exe` for the current application.

    `pbd`: one boolean per library in the session library list, `True` when
    that library is already a PBD/DLL and must stay out of the exe. Omit it
    to link every library in. `icon_name` defaults to a bundled icon because
    ORCA rejected a NULL one in the tested builds. Existing outputs are
    rejected without changes; use a new path and replace the old deployment
    only after success. A failed build may leave a partial new output.
    """
    session = Session.instance()
    try:
        success, errors = session.build_executable(
            exe_name,
            icon_name=icon_name,
            pbr_name=pbr_name,
            flags=flags,
            pbd_flags=pbd_flags,
            exe_info=exe_info,
            pbd=pbd,
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
