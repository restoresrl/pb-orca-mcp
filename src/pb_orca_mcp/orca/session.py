"""Singleton ORCA session wrapper.

ORCA is single-session per process and not thread-safe. The `Session`
class owns the `HPBORCA` handle, the loaded `OrcaApi`, and an `asyncio.Lock`
that the MCP layer takes around every ORCA call (an asyncio MCP server can
otherwise drive multiple tool calls concurrently and corrupt session state).

State machine:

    [closed] --open--> [opened] --set_current_application--> [appl_set]
       ^                  |                                       |
       |              set_library_list                       set_library_list
       |                  |                                       |
       +------close-------+---------------------------------------+

`set_library_list` is legal in both `opened` and `appl_set` states. ORCA
treats LibList configuration as orthogonal-but-prerequisite to compile/
rebuild; we don't enforce a stricter contract than the C API does.

Callback references (`_callback_refs`) are tracked here even though
phase 3 doesn't register any — phase 5 (compile loop) will append into
this list and clear it on `close()`. The list lives on the Session
because callbacks captured during a compile call must outlive the call.
"""

from __future__ import annotations

import asyncio
import ctypes
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pb_orca_mcp.orca.constants import PBORCA_MSGBUFFER, PBORCA_OK
from pb_orca_mcp.orca.errors import OrcaError

if TYPE_CHECKING:
    from pb_orca_mcp.discovery import PbInstall
    from pb_orca_mcp.orca.dll import OrcaApi


class SessionStateError(RuntimeError):
    """Raised when a session operation is invoked from the wrong state."""


@dataclass
class _State:
    """Mutable state of a single open ORCA session."""

    api: OrcaApi
    handle: int
    current_app_lib: str | None = None
    current_app_name: str | None = None
    library_list: tuple[str, ...] | None = None
    callback_refs: list[Any] = field(default_factory=list)


class Session:
    """Process-wide singleton ORCA session.

    Use `Session.instance()` to get the singleton; `open()` / `close()`
    transition between `closed` and `opened`. All ORCA calls go through
    methods on this object, never directly on the `OrcaApi`.
    """

    _instance: Session | None = None

    def __init__(self) -> None:
        self._state: _State | None = None
        self._lock = asyncio.Lock()

    @classmethod
    def instance(cls) -> Session:
        """Return the process-wide singleton, creating it on first call."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def is_open(self) -> bool:
        return self._state is not None

    @property
    def install(self) -> PbInstall | None:
        return self._state.api.install if self._state is not None else None

    @property
    def current_application(self) -> tuple[str, str] | None:
        if self._state is None or self._state.current_app_lib is None:
            return None
        return self._state.current_app_lib, self._state.current_app_name or ""

    @property
    def library_list(self) -> tuple[str, ...] | None:
        return self._state.library_list if self._state is not None else None

    @property
    def lock(self) -> asyncio.Lock:
        """The `asyncio.Lock` that MCP tool handlers MUST acquire around every call."""
        return self._lock

    def open(self, api: OrcaApi) -> None:
        """Call `PBORCA_SessionOpen` and start tracking state.

        Raises `SessionStateError` if a session is already open (call
        `close()` first; ORCA is single-session per process).
        """
        if self._state is not None:
            raise SessionStateError(
                "A session is already open (ORCA is single-session per process). "
                "Call close() before opening a new one."
            )
        handle = api.session.SessionOpen()
        if not handle:
            raise OrcaError.from_code(
                code=-1,
                message=f"PBORCA_SessionOpen returned NULL for {api.install.orca_dll}",
            )
        self._state = _State(api=api, handle=handle)

    def close(self) -> None:
        """Call `PBORCA_SessionClose` and clear state. No-op if not open."""
        if self._state is None:
            return
        try:
            self._state.api.session.SessionClose(self._state.handle)
        finally:
            self._state.callback_refs.clear()
            self._state = None

    def set_current_application(self, app_lib: str, app_name: str) -> None:
        """`PBORCA_SessionSetCurrentAppl(handle, ApplLibName, ApplName)`.

        Note: ORCA requires the library list to be set *before* this call
        (see `PBORCA_LIBLISTNOTSET = -5`). The MCP tool wrapper calls
        `set_library_list` first.
        """
        state = self._require_open("set_current_application")
        rc = state.api.session.SessionSetCurrentAppl(state.handle, app_lib, app_name)
        if rc != PBORCA_OK:
            raise self._build_error(rc)
        state.current_app_lib = app_lib
        state.current_app_name = app_name

    def set_library_list(self, libraries: list[str]) -> None:
        """`PBORCA_SessionSetLibraryList(handle, LPTSTR*, INT)`."""
        state = self._require_open("set_library_list")
        if not libraries:
            raise ValueError("library list must contain at least one .pbl/.pbd path")
        # Build a NULL-terminated array of c_wchar_p; ctypes keeps the
        # Python strings alive for the duration of the call.
        array_type = ctypes.c_wchar_p * len(libraries)
        array = array_type(*libraries)
        rc = state.api.session.SessionSetLibraryList(state.handle, array, len(libraries))
        if rc != PBORCA_OK:
            raise self._build_error(rc)
        state.library_list = tuple(libraries)

    def get_error_text(self) -> str:
        """`PBORCA_SessionGetError(handle, buffer, size)` — last error text."""
        state = self._require_open("get_error_text")
        buf = ctypes.create_unicode_buffer(PBORCA_MSGBUFFER)
        state.api.session.SessionGetError(state.handle, buf, PBORCA_MSGBUFFER)
        return buf.value

    def _require_open(self, op: str) -> _State:
        if self._state is None:
            raise SessionStateError(f"Cannot {op}: no ORCA session open")
        return self._state

    def _build_error(self, code: int) -> OrcaError:
        """Resolve an ORCA error code into an exception, pulling SessionGetError text."""
        try:
            message = self.get_error_text()
        except Exception:
            message = ""
        return OrcaError.from_code(code, message=message)
