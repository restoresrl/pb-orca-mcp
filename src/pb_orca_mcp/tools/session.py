"""MCP tools for ORCA session lifecycle and application setup.

Wraps `pb_orca_mcp.orca.session.Session` with the input/output shape
documented in `docs/tools.md`. Errors are surfaced as
`{"error": {"code", "name", "message"}}` payloads rather than raised
exceptions, so the MCP layer can pass them straight through.

Tools exposed:
- `pb_session_open(pb_version=..., install_path=...)`: explicit version
  selection (no auto-pick — see PLAN §"Decisioni di scope").
- `pb_session_close()`: idempotent.
- `pb_set_current_application(app_lib, app_name)`: requires session open.
- `pb_set_library_list(libraries)`: requires session open.
"""

from __future__ import annotations

from typing import Any

from pb_orca_mcp.discovery import PbInstall, discover_pb_installations
from pb_orca_mcp.orca.dll import OrcaLoadError, load_orca
from pb_orca_mcp.orca.errors import OrcaError
from pb_orca_mcp.orca.session import Session, SessionStateError


def pb_session_open(
    *, pb_version: str | None = None, install_path: str | None = None
) -> dict[str, Any]:
    """Open the ORCA session against an explicitly-selected PB install.

    Exactly one of `pb_version` (e.g. `"22.0"`) or `install_path` must be
    supplied; the project policy is "no auto-pick" (PLAN §"Decisioni di
    scope"). When both are supplied, `install_path` wins.
    """
    if not pb_version and not install_path:
        return _error(
            code=-1,
            name="PB_ORCA_MCP_INVALIDARGS",
            message="pb_session_open requires pb_version or install_path",
        )

    install = _resolve_install(pb_version=pb_version, install_path=install_path)
    if isinstance(install, dict):
        return install  # an error payload from the resolver

    try:
        api = load_orca(install)
    except OrcaLoadError as exc:
        return _error(code=-1, name="PB_ORCA_MCP_LOADFAILED", message=str(exc))

    session = Session.instance()
    try:
        session.open(api)
    except SessionStateError as exc:
        return _error(code=-1, name="PB_ORCA_MCP_STATEERROR", message=str(exc))
    except OrcaError as exc:
        return _error_from_orca(exc)

    return {
        "ok": True,
        "pb_version": install.version,
        "file_version": install.file_version,
        "product_version": install.product_version,
        "arch": install.arch,
        "install_path": install.install_path,
        "orca_dll": install.orca_dll,
        "tested": install.tested,
    }


def pb_session_close() -> dict[str, Any]:
    """Close the ORCA session if open. Idempotent."""
    session = Session.instance()
    was_open = session.is_open
    session.close()
    return {"ok": True, "was_open": was_open}


def pb_set_current_application(app_lib: str, app_name: str) -> dict[str, Any]:
    """`PBORCA_SessionSetCurrentAppl(app_lib, app_name)`.

    Requires `pb_session_open` first and `pb_set_library_list` to have set
    the LibList (otherwise ORCA returns `PBORCA_LIBLISTNOTSET`).
    """
    session = Session.instance()
    try:
        session.set_current_application(app_lib, app_name)
    except SessionStateError as exc:
        return _error(code=-1, name="PB_ORCA_MCP_STATEERROR", message=str(exc))
    except OrcaError as exc:
        return _error_from_orca(exc)
    return {"ok": True, "app_lib": app_lib, "app_name": app_name}


def pb_set_library_list(libraries: list[str]) -> dict[str, Any]:
    """`PBORCA_SessionSetLibraryList(libraries)`."""
    session = Session.instance()
    try:
        session.set_library_list(libraries)
    except SessionStateError as exc:
        return _error(code=-1, name="PB_ORCA_MCP_STATEERROR", message=str(exc))
    except ValueError as exc:
        return _error(code=-1, name="PB_ORCA_MCP_INVALIDARGS", message=str(exc))
    except OrcaError as exc:
        return _error_from_orca(exc)
    return {"ok": True, "libraries": list(libraries)}


def _resolve_install(
    *, pb_version: str | None, install_path: str | None
) -> PbInstall | dict[str, Any]:
    """Pick a `PbInstall` from discovery + explicit args, or return an error dict."""
    ides, _runtime = discover_pb_installations()
    if install_path:
        norm = install_path.replace("/", "\\").rstrip("\\")
        for candidate in ides:
            if candidate.install_path.rstrip("\\").lower() == norm.lower():
                return candidate
        return _error(
            code=-1,
            name="PB_ORCA_MCP_INSTALLNOTFOUND",
            message=f"No PB IDE install with ORCA found at {install_path!r}",
        )
    matches = [c for c in ides if c.version == pb_version]
    if not matches:
        return _error(
            code=-1,
            name="PB_ORCA_MCP_VERSIONNOTFOUND",
            message=f"No PB {pb_version} IDE install with ORCA found on this machine",
        )
    if len(matches) > 1:
        # Multiple installs of the same major (e.g. parallel R2 and R3 of
        # the same year) — caller must disambiguate with install_path.
        return _error(
            code=-1,
            name="PB_ORCA_MCP_VERSIONAMBIGUOUS",
            message=(
                f"Found {len(matches)} PB {pb_version} installs; "
                "specify install_path to disambiguate"
            ),
        )
    return matches[0]


def _error(*, code: int, name: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "name": name, "message": message}}


def _error_from_orca(exc: OrcaError) -> dict[str, Any]:
    return {"error": exc.to_dict()}
