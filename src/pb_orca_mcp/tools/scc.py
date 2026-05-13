"""MCP tools for ORCA Source-Code-Control (SCC) operations.

Wraps `pb_orca_mcp.orca.session.Session.scc_*` methods with JSON-friendly
input/output. Errors come back as `{"error": {"code","name","message"}}`.

The primary use case is the offline-mode "Refresh PBL" flow described in
`docs/workflow.md`: on git-managed PB projects, `ws_objects/` is the
source of truth and the `.pbl` is derived. The sequence

    pb_scc_get_connect_properties → pb_scc_connect_offline →
    pb_scc_set_target → pb_scc_refresh_target → pb_scc_close

is the native equivalent of PB IDE's "Refresh PBL" command and reconciles
add/modify/delete from `ws_objects/` into the binary library.

Tools exposed (6):
- `pb_scc_get_connect_properties`: read SCC config from a workspace file.
- `pb_scc_connect_offline`: open an offline SCC connection.
- `pb_scc_set_target`: bind the connection to a target file (`.pbt`).
- `pb_scc_exclude_library_list`: exclude specific PBLs from SCC management.
- `pb_scc_refresh_target`: refresh PBLs from `ws_objects/`.
- `pb_scc_close`: close the SCC connection.

Online connect, get-latest-version, set-password and reset-revision-number
are intentionally not exposed in this phase — they require a live MSSCCI
provider and are out of scope for the git/offline workflow.
"""

from __future__ import annotations

from typing import Any

from pb_orca_mcp.orca.constants import PBORCA_GETCONNECT_REQ, PBORCA_REGREADERROR
from pb_orca_mcp.orca.errors import OrcaError
from pb_orca_mcp.orca.session import Session, SessionStateError

# Codes returned by `SccGetConnectProperties` on a `.pbw` that has no SCC
# connection block (the normal case for git/svn workflows — Appeon
# documents the corresponding OrcaScript command as silently ignored;
# `pborca.dll` surfaces it as `-23` or `-31` depending on whether the
# block is missing entirely or just unreadable). In offline mode the
# `.pbw` is not part of the connect contract, so we tolerate these
# specific failures and fall through to the explicit kwargs.
_PRE_READ_TOLERATED_CODES = frozenset({PBORCA_REGREADERROR, PBORCA_GETCONNECT_REQ})


def pb_scc_get_connect_properties(workspace_file: str) -> dict[str, Any]:
    """Read the SCC connection block from a `.pbw` workspace file.

    Returns a dict with `provider_name`, `user_id`, `project`,
    `local_proj_path`, `aux_path`, `log_file`, `capabilities`,
    `comment_max_len`, `append_log`, `delete_temp_files`,
    `delete_pbl_on_refresh`. Pure read-only — no connection is opened.
    """
    session = Session.instance()
    try:
        config = session.scc_get_connect_properties(workspace_file)
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except OrcaError as exc:
        return {"error": exc.to_dict()}
    return {"workspace_file": workspace_file, **config}


def pb_scc_connect_offline(
    workspace_file: str | None = None,
    provider_name: str | None = None,
    user_id: str | None = None,
    project: str | None = None,
    local_proj_path: str | None = None,
    aux_path: str | None = None,
    log_file: str | None = None,
    append_log: bool = False,
    delete_temp_files: bool = True,
    delete_pbl_on_refresh: bool = False,
    comment_max_len: int = 256,
) -> dict[str, Any]:
    """Open an offline SCC connection.

    Offline mode does not contact a remote SCC provider; it operates on the
    `ws_objects/` source-of-truth alone. Use this for the git-managed
    workflow where `ws_objects/` is canonical and `.pbl` is derived.

    If `workspace_file` is supplied and contains an SCC connection block,
    its values seed the config as best-effort defaults; any explicit kwarg
    then overrides them. If the workspace has no SCC block (`-23`/`-31` —
    the normal case for git/svn workspaces where offline mode is the only
    supported flow) the pre-read is silently skipped and the connection is
    built from the kwargs alone. Other read errors propagate.

    Note: per Appeon's OrcaScript reference (`ug36631.html`), in offline
    mode **only** `local_proj_path`, `log_file`, and `append_log` actually
    take effect; the other kwargs (`provider_name`, `user_id`, `project`,
    `aux_path`, `comment_max_len`, `delete_temp_files`, `delete_pbl_on_refresh`)
    are silently ignored by the underlying SCC layer. The signature still
    accepts them for symmetry with a future online-mode tool.
    """
    session = Session.instance()
    config: dict[str, Any] = {}
    if workspace_file is not None:
        try:
            config.update(session.scc_get_connect_properties(workspace_file))
        except SessionStateError as exc:
            return _error("PB_ORCA_MCP_STATEERROR", str(exc))
        except OrcaError as exc:
            if exc.code not in _PRE_READ_TOLERATED_CODES:
                return {"error": exc.to_dict()}
    _maybe_set(config, "provider_name", provider_name)
    _maybe_set(config, "user_id", user_id)
    _maybe_set(config, "project", project)
    _maybe_set(config, "local_proj_path", local_proj_path)
    _maybe_set(config, "aux_path", aux_path)
    _maybe_set(config, "log_file", log_file)
    config["append_log"] = append_log
    config["delete_temp_files"] = delete_temp_files
    config["delete_pbl_on_refresh"] = delete_pbl_on_refresh
    config["comment_max_len"] = comment_max_len
    try:
        result = session.scc_connect_offline(config)
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except OrcaError as exc:
        return {"error": exc.to_dict()}
    return {"ok": True, **result}


def pb_scc_set_target(
    target_file: str, flags: list[str] | None = None
) -> dict[str, Any]:
    """Bind the SCC connection to a target (`.pbt`) and return affected PBLs.

    `flags` is an optional list of SCC refresh-flag names:
    `refresh_all`, `outofdate`, `importonly`, `exclude_checkout`. Defaults
    to no flags (`0`).
    """
    session = Session.instance()
    try:
        libraries = session.scc_set_target(target_file, flags)
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except ValueError as exc:
        return _error("PB_ORCA_MCP_INVALIDARGS", str(exc))
    except OrcaError as exc:
        return {"error": exc.to_dict()}
    return {
        "ok": True,
        "target_file": target_file,
        "flags": flags or [],
        "count": len(libraries),
        "libraries": libraries,
    }


def pb_scc_exclude_library_list(lib_names: list[str]) -> dict[str, Any]:
    """Exclude specific PBLs from SCC management for the current target."""
    session = Session.instance()
    try:
        session.scc_exclude_library_list(lib_names)
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except ValueError as exc:
        return _error("PB_ORCA_MCP_INVALIDARGS", str(exc))
    except OrcaError as exc:
        return {"error": exc.to_dict()}
    return {"ok": True, "count": len(lib_names), "libraries": list(lib_names)}


def pb_scc_refresh_target(rebuild_type: str = "incremental") -> dict[str, Any]:
    """Refresh PBLs from `ws_objects/` — the native "Refresh PBL".

    `rebuild_type` ∈ `{"full", "incremental", "migrate", "3pass"}`. Default
    `"incremental"` (the value the workflow doc recommends).
    """
    session = Session.instance()
    try:
        session.scc_refresh_target(rebuild_type)
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except ValueError as exc:
        return _error("PB_ORCA_MCP_INVALIDARGS", str(exc))
    except OrcaError as exc:
        return {"error": exc.to_dict()}
    return {"ok": True, "rebuild_type": rebuild_type}


def pb_scc_close() -> dict[str, Any]:
    """Close the SCC connection. No-op when not connected."""
    session = Session.instance()
    try:
        session.scc_close()
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except OrcaError as exc:
        return {"error": exc.to_dict()}
    return {"ok": True}


def _maybe_set(d: dict[str, Any], key: str, value: Any) -> None:
    """Overwrite `d[key]` only when `value` is not None."""
    if value is not None:
        d[key] = value


def _error(name: str, message: str) -> dict[str, Any]:
    return {"error": {"code": -1, "name": name, "message": message}}
