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
    PBORCA_COMPERROR,
    PBORCA_LINKERROR,
    PBORCA_MSGBUFFER,
    PBORCA_OK,
    build_flags_from_names,
    compile_level_to_name,
    entry_type_from_name,
    entry_type_to_name,
    rebuild_type_from_name,
    reftype_to_name,
)
from pb_orca_mcp.orca.errors import OrcaError
from pb_orca_mcp.orca.types import PBORCA_ENTRYINFO, PBORCA_EXEINFO

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
    last_compile_errors: list[dict[str, Any]] = field(default_factory=list)
    """Diagnostics from the most recent compile/rebuild call. Replaced on each call."""


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

    # --------------------------- compile group ---------------------------

    @property
    def last_compile_errors(self) -> list[dict[str, Any]]:
        """Diagnostics from the most recent compile/rebuild call.

        Returns an empty list when no session is open or no compile has run.
        """
        if self._state is None:
            return []
        return list(self._state.last_compile_errors)

    def compile_entry_import(
        self,
        lib_path: str,
        entry_name: str,
        entry_type: str,
        syntax: str,
        comments: str = "",
    ) -> tuple[bool, list[dict[str, Any]]]:
        """`PBORCA_CompileEntryImport(handle, lib, entry, type, comments, syntax, len, cb, NULL)`.

        Returns `(success, errors)` where `success` is `rc == PBORCA_OK`
        (i.e. no compile errors). On `PBORCA_COMPERROR (-11)` returns
        `(False, errors)` with the diagnostics from the callback. Other
        negative codes raise `OrcaError`.
        """
        state = self._require_open("compile_entry_import")
        type_code = entry_type_from_name(entry_type)
        callback, errors = self._make_errproc(state)
        try:
            rc = state.api.compile.CompileEntryImport(
                state.handle, lib_path, entry_name, type_code, comments,
                syntax, len(syntax) + 1, callback, None,
            )
        finally:
            self._drop_callback(state, callback)
        return self._compile_result(state, rc, errors)

    def compile_entry_import_list(
        self, items: list[dict[str, Any]]
    ) -> tuple[bool, list[dict[str, Any]]]:
        """`PBORCA_CompileEntryImportList` over a batch of entries.

        Each `items[i]` must have keys: `lib_path`, `entry_name`,
        `entry_type` (string), `syntax`. Optional: `comments`.
        """
        state = self._require_open("compile_entry_import_list")
        if not items:
            raise ValueError("items must contain at least one entry")
        n = len(items)
        libs = (ctypes.c_wchar_p * n)(*[i["lib_path"] for i in items])
        names = (ctypes.c_wchar_p * n)(*[i["entry_name"] for i in items])
        types = (ctypes.c_int * n)(*[entry_type_from_name(i["entry_type"]) for i in items])
        comments = (ctypes.c_wchar_p * n)(*[i.get("comments", "") for i in items])
        syntaxes = (ctypes.c_wchar_p * n)(*[i["syntax"] for i in items])
        sizes = (c_long * n)(*[len(i["syntax"]) + 1 for i in items])
        callback, errors = self._make_errproc(state)
        try:
            rc = state.api.compile.CompileEntryImportList(
                state.handle, libs, names, types, comments, syntaxes, sizes,
                n, callback, None,
            )
        finally:
            self._drop_callback(state, callback)
        return self._compile_result(state, rc, errors)

    def compile_entry_regenerate(
        self, lib_path: str, entry_name: str, entry_type: str
    ) -> tuple[bool, list[dict[str, Any]]]:
        """`PBORCA_CompileEntryRegenerate(handle, lib, entry, type, cb, NULL)`."""
        state = self._require_open("compile_entry_regenerate")
        type_code = entry_type_from_name(entry_type)
        callback, errors = self._make_errproc(state)
        try:
            rc = state.api.compile.CompileEntryRegenerate(
                state.handle, lib_path, entry_name, type_code, callback, None
            )
        finally:
            self._drop_callback(state, callback)
        return self._compile_result(state, rc, errors)

    def application_rebuild(
        self, rebuild_type: str = "incremental"
    ) -> tuple[bool, list[dict[str, Any]]]:
        """`PBORCA_ApplicationRebuild(handle, rebld_type, cb, NULL)`.

        `rebuild_type` ∈ `{"full", "incremental", "migrate", "3pass"}`.
        Requires `set_current_application` + `set_library_list` first.
        """
        state = self._require_open("application_rebuild")
        type_code = rebuild_type_from_name(rebuild_type)
        callback, errors = self._make_errproc(state)
        try:
            rc = state.api.compile.ApplicationRebuild(
                state.handle, type_code, callback, None
            )
        finally:
            self._drop_callback(state, callback)
        return self._compile_result(state, rc, errors)

    def _make_errproc(self, state: _State) -> tuple[Any, list[dict[str, Any]]]:
        """Build a `PBORCA_ERRPROC` that accumulates diagnostics into a fresh list.

        The callback object is registered in `state.callback_refs` and
        must be removed by the caller via `_drop_callback` after the ORCA
        call returns (`finally` block).
        """
        from pb_orca_mcp.orca.dll import PBORCA_ERRPROC  # avoid import cycle

        errors: list[dict[str, Any]] = []

        def _on_error(p_err: Any, _user: Any) -> None:
            e = p_err.contents
            errors.append(
                {
                    "level": int(e.iLevel),
                    "level_name": compile_level_to_name(int(e.iLevel)),
                    "message_number": e.lpszMessageNumber or "",
                    "message_text": e.lpszMessageText or "",
                    "column": int(e.iColumnNumber),
                    "line": int(e.iLineNumber),
                }
            )

        callback = PBORCA_ERRPROC(_on_error)
        state.callback_refs.append(callback)
        return callback, errors

    @staticmethod
    def _drop_callback(state: _State, callback: Any) -> None:
        with contextlib.suppress(ValueError):
            state.callback_refs.remove(callback)

    def _compile_result(
        self, state: _State, rc: int, errors: list[dict[str, Any]]
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Translate an ORCA compile/rebuild return code to (success, errors).

        - `PBORCA_OK`: success, errors may still contain warnings.
        - `PBORCA_COMPERROR` / `PBORCA_LINKERROR`: not an exception — the
          callback already populated the diagnostics; report success=False.
        - Anything else: raise `OrcaError`.
        """
        state.last_compile_errors = list(errors)
        if rc == PBORCA_OK:
            return True, errors
        if rc in (PBORCA_COMPERROR, PBORCA_LINKERROR):
            return False, errors
        raise self._build_error(rc)

    # --------------------------- build group ---------------------------

    def set_exe_info(self, info: dict[str, str | None]) -> None:
        """`PBORCA_SetExeInfo(handle, &PBORCA_EXEINFO)` — populate version metadata.

        Keys (all optional, omit or pass None to skip): `company_name`,
        `product_name`, `description`, `copyright`, `file_version`,
        `file_version_num`, `product_version`, `product_version_num`,
        `manifest_info`. Each maps to the Windows VS_VERSION_INFO entry
        on the produced `.exe`.
        """
        state = self._require_open("set_exe_info")
        exe = PBORCA_EXEINFO()
        exe.lpszCompanyName = info.get("company_name")
        exe.lpszProductName = info.get("product_name")
        exe.lpszDescription = info.get("description")
        exe.lpszCopyright = info.get("copyright")
        exe.lpszFileVersion = info.get("file_version")
        exe.lpszFileVersionNum = info.get("file_version_num")
        exe.lpszProductVersion = info.get("product_version")
        exe.lpszProductVersionNum = info.get("product_version_num")
        exe.lpszManifestInfo = info.get("manifest_info")
        rc = state.api.build.SetExeInfo(state.handle, pointer(exe))
        if rc != PBORCA_OK:
            raise self._build_error(rc)

    def build_executable(
        self,
        exe_name: str,
        *,
        icon_name: str | None = None,
        pbr_name: str | None = None,
        flags: list[str] | None = None,
        pbd_flags: list[list[str]] | None = None,
        exe_info: dict[str, str | None] | None = None,
    ) -> tuple[bool, list[dict[str, Any]]]:
        """`PBORCA_ExecutableCreate` with optional `SetExeInfo` first.

        - `flags`: build flag names for the EXE itself (`machine_code`,
          `optimize_speed`, `trace_info`, `error_context`, `x64`, …; see
          `BUILD_FLAG_NAMES`).
        - `pbd_flags`: per-PBD flag-name lists (one inner list per PBL the
          application links via the library list, excluding the application
          PBL itself). If supplied, ORCA generates a `.pbd` per element
          with that flag set; if `None`, no PBDs are built.
        - `exe_info`: if not `None`, calls `set_exe_info` before
          `ExecutableCreate`.

        Returns `(success, link_errors)`; per-error dicts carry
        `message_text`.
        """
        state = self._require_open("build_executable")
        flag_int = build_flags_from_names(flags)
        if exe_info is not None:
            self.set_exe_info(exe_info)
        if pbd_flags:
            pbd_array_type = ctypes.c_int * len(pbd_flags)
            pbd_array = pbd_array_type(*[build_flags_from_names(p) for p in pbd_flags])
            num_pbd = len(pbd_flags)
        else:
            pbd_array = None
            num_pbd = 0
        callback, errors = self._make_linkproc(state)
        try:
            rc = state.api.build.ExecutableCreate(
                state.handle, exe_name, icon_name, pbr_name,
                callback, None,
                pbd_array, num_pbd, flag_int, None,
            )
        finally:
            self._drop_callback(state, callback)
        state.last_compile_errors = list(errors)
        if rc == PBORCA_OK:
            return True, errors
        if rc == PBORCA_LINKERROR:
            return False, errors
        raise self._build_error(rc)

    def build_dynamic_library(
        self, lib_path: str, *, pbr_name: str | None = None, flags: list[str] | None = None
    ) -> None:
        """`PBORCA_DynamicLibraryCreate(handle, lib, pbr, lFlags, NULL)` — build a single PBD."""
        state = self._require_open("build_dynamic_library")
        flag_int = build_flags_from_names(flags)
        rc = state.api.build.DynamicLibraryCreate(
            state.handle, lib_path, pbr_name, flag_int, None
        )
        if rc != PBORCA_OK:
            raise self._build_error(rc)

    def object_query_hierarchy(
        self, lib_path: str, entry_name: str, entry_type: str
    ) -> list[str]:
        """`PBORCA_ObjectQueryHierarchy` — return the ancestor chain as a list of names.

        Order is the order the callback delivers entries (closest ancestor
        first; the entry itself is not included).
        """
        state = self._require_open("object_query_hierarchy")
        type_code = entry_type_from_name(entry_type)
        from pb_orca_mcp.orca.dll import PBORCA_HIERPROC

        ancestors: list[str] = []

        def _on_ancestor(p_entry: Any, _user: Any) -> None:
            ancestors.append(p_entry.contents.lpszAncestorName or "")

        callback = PBORCA_HIERPROC(_on_ancestor)
        state.callback_refs.append(callback)
        try:
            rc = state.api.build.ObjectQueryHierarchy(
                state.handle, lib_path, entry_name, type_code, callback, None
            )
        finally:
            self._drop_callback(state, callback)
        if rc != PBORCA_OK:
            raise self._build_error(rc)
        return ancestors

    def object_query_reference(
        self, lib_path: str, entry_name: str, entry_type: str
    ) -> list[dict[str, Any]]:
        """`PBORCA_ObjectQueryReference` — list every entry that references this one."""
        state = self._require_open("object_query_reference")
        type_code = entry_type_from_name(entry_type)
        from pb_orca_mcp.orca.dll import PBORCA_REFPROC

        refs: list[dict[str, Any]] = []

        def _on_ref(p_entry: Any, _user: Any) -> None:
            r = p_entry.contents
            refs.append(
                {
                    "library": r.lpszLibraryName or "",
                    "entry_name": r.lpszEntryName or "",
                    "entry_type": entry_type_to_name(int(r.otEntryType)),
                    "ref_type": reftype_to_name(int(r.otEntryRefType)),
                }
            )

        callback = PBORCA_REFPROC(_on_ref)
        state.callback_refs.append(callback)
        try:
            rc = state.api.build.ObjectQueryReference(
                state.handle, lib_path, entry_name, type_code, callback, None
            )
        finally:
            self._drop_callback(state, callback)
        if rc != PBORCA_OK:
            raise self._build_error(rc)
        return refs

    def _make_linkproc(self, state: _State) -> tuple[Any, list[dict[str, Any]]]:
        """Build a `PBORCA_LNKPROC` that accumulates link errors. Mirrors `_make_errproc`."""
        from pb_orca_mcp.orca.dll import PBORCA_LNKPROC

        errors: list[dict[str, Any]] = []

        def _on_link_error(p_err: Any, _user: Any) -> None:
            errors.append({"message_text": p_err.contents.lpszMessageText or ""})

        callback = PBORCA_LNKPROC(_on_link_error)
        state.callback_refs.append(callback)
        return callback, errors

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
