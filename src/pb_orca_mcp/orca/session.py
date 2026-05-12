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

Callback references (`_callback_refs`) keep Python `WINFUNCTYPE` instances
alive for the duration of an ORCA call. Without this, Python's GC can
collect the closure between when ORCA receives the function pointer and
when it invokes it, leading to a hard crash. The list is cleared on
`close()` and on each call site that scopes its callback locally.
"""

from __future__ import annotations

import asyncio
import contextlib
import ctypes
from ctypes import c_long, pointer
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pb_orca_mcp.orca.constants import (
    PBORCA_BUFFERTOOSMALL,
    PBORCA_MSGBUFFER,
    PBORCA_OK,
    entry_type_from_name,
    entry_type_to_name,
)
from pb_orca_mcp.orca.errors import OrcaError
from pb_orca_mcp.orca.types import PBORCA_ENTRYINFO

if TYPE_CHECKING:
    from pb_orca_mcp.discovery import PbInstall
    from pb_orca_mcp.orca.dll import OrcaApi


PBORCA_MAXCOMMENT_BUFSZ = 256
"""Comment buffer size for `LibraryDirectory` and friends (= PBORCA_MAXCOMMENT + 1)."""

_INITIAL_EXPORT_BUFFER = 64 * 1024
"""Starting buffer size (in wchars) for `library_entry_export`. Most PB objects fit."""

_MAX_EXPORT_ATTEMPTS = 3
"""Upper bound on grow-and-retry rounds for `library_entry_export`."""


def _strip_buffer(buf: Any) -> str:
    """Return the leading NUL-terminated portion of a fixed-size `c_wchar` array as a str."""
    return str(buf).rstrip("\x00") if not isinstance(buf, str) else buf.rstrip("\x00")


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

    # --------------------------- library group ---------------------------

    def library_create(self, lib_path: str, comments: str = "") -> None:
        """`PBORCA_LibraryCreate(handle, lib, comments)`."""
        state = self._require_open("library_create")
        rc = state.api.library.LibraryCreate(state.handle, lib_path, comments)
        if rc != PBORCA_OK:
            raise self._build_error(rc)

    def library_delete(self, lib_path: str) -> None:
        """`PBORCA_LibraryDelete(handle, lib)`."""
        state = self._require_open("library_delete")
        rc = state.api.library.LibraryDelete(state.handle, lib_path)
        if rc != PBORCA_OK:
            raise self._build_error(rc)

    def library_comment_modify(self, lib_path: str, comments: str) -> None:
        """`PBORCA_LibraryCommentModify(handle, lib, comments)`."""
        state = self._require_open("library_comment_modify")
        rc = state.api.library.LibraryCommentModify(state.handle, lib_path, comments)
        if rc != PBORCA_OK:
            raise self._build_error(rc)

    def library_directory(self, lib_path: str) -> tuple[str, list[dict[str, Any]]]:
        """`PBORCA_LibraryDirectory(handle, lib, libCommentsBuf, len, listProc, NULL)`.

        Returns `(library_comment, entries)` where entries is the list of
        every object the callback received, normalized to dicts with
        `name`, `type` (string), `size`, `create_time`, `comment`.
        """
        state = self._require_open("library_directory")
        from pb_orca_mcp.orca.dll import PBORCA_LISTPROC  # avoid cycle at import time

        entries: list[dict[str, Any]] = []

        def _on_entry(p_entry: Any, _user: Any) -> None:
            e = p_entry.contents
            entries.append(
                {
                    "name": e.lpszEntryName or "",
                    "type": entry_type_to_name(int(e.otEntryType)),
                    "size": int(e.lEntrySize),
                    "create_time": int(e.lCreateTime),
                    "comment": _strip_buffer(e.szComments),
                }
            )

        callback = PBORCA_LISTPROC(_on_entry)
        state.callback_refs.append(callback)
        comment_buf = ctypes.create_unicode_buffer(PBORCA_MAXCOMMENT_BUFSZ)
        try:
            rc = state.api.library.LibraryDirectory(
                state.handle, lib_path, comment_buf, PBORCA_MAXCOMMENT_BUFSZ, callback, None
            )
        finally:
            with contextlib.suppress(ValueError):
                state.callback_refs.remove(callback)
        if rc != PBORCA_OK:
            raise self._build_error(rc)
        return comment_buf.value, entries

    def library_entry_information(
        self, lib_path: str, entry_name: str, entry_type: str
    ) -> dict[str, Any]:
        """`PBORCA_LibraryEntryInformation(handle, lib, entry, type, &info)`."""
        state = self._require_open("library_entry_information")
        type_code = entry_type_from_name(entry_type)
        info = PBORCA_ENTRYINFO()
        rc = state.api.library.LibraryEntryInformation(
            state.handle, lib_path, entry_name, type_code, pointer(info)
        )
        if rc != PBORCA_OK:
            raise self._build_error(rc)
        return {
            "name": entry_name,
            "type": entry_type,
            "object_size": int(info.lObjectSize),
            "source_size": int(info.lSourceSize),
            "create_time": int(info.lCreateTime),
            "comment": _strip_buffer(info.szComments),
        }

    def library_entry_export(
        self, lib_path: str, entry_name: str, entry_type: str
    ) -> str:
        """`PBORCA_LibraryEntryExportEx` with auto-resizing buffer.

        Starts at 64 KiB; if ORCA returns `PBORCA_BUFFERTOOSMALL`, reads the
        required size from `pReturnSize` and retries (max 3 attempts).
        """
        state = self._require_open("library_entry_export")
        type_code = entry_type_from_name(entry_type)
        size = _INITIAL_EXPORT_BUFFER
        for _ in range(_MAX_EXPORT_ATTEMPTS):
            buf = ctypes.create_unicode_buffer(size)
            return_size = c_long(0)
            rc = state.api.library.LibraryEntryExportEx(
                state.handle, lib_path, entry_name, type_code, buf, size, pointer(return_size)
            )
            if rc == PBORCA_OK:
                return buf.value
            if rc == PBORCA_BUFFERTOOSMALL and return_size.value > size:
                size = return_size.value + 1
                continue
            raise self._build_error(rc)
        raise self._build_error(PBORCA_BUFFERTOOSMALL)

    def library_entry_delete(
        self, lib_path: str, entry_name: str, entry_type: str
    ) -> None:
        """`PBORCA_LibraryEntryDelete(handle, lib, entry, type)`."""
        state = self._require_open("library_entry_delete")
        type_code = entry_type_from_name(entry_type)
        rc = state.api.library.LibraryEntryDelete(state.handle, lib_path, entry_name, type_code)
        if rc != PBORCA_OK:
            raise self._build_error(rc)

    def library_entry_move(
        self, source_lib: str, dest_lib: str, entry_name: str, entry_type: str
    ) -> None:
        """`PBORCA_LibraryEntryMove(handle, source_lib, dest_lib, entry, type)`."""
        state = self._require_open("library_entry_move")
        type_code = entry_type_from_name(entry_type)
        rc = state.api.library.LibraryEntryMove(
            state.handle, source_lib, dest_lib, entry_name, type_code
        )
        if rc != PBORCA_OK:
            raise self._build_error(rc)

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
