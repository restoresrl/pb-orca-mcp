"""Version-aware loader for pborc.dll with ORCA function prototypes.

`load_orca(install)` takes a `PbInstall` (from discovery) and returns an
`OrcaApi` wrapping the `pborc.dll` of that specific PowerBuilder install,
with `ctypes` prototypes bound to the call sites used in this package.

Multi-version is a day-1 requirement: a single machine can host PB 2019 R3,
PB 2022 R3, and PB 2025 side by side, each shipping its own
`<install>\\IDE\\pborc.dll`. The loader picks the right one per caller-
supplied install. The ORCA ABI is stable since PB 2019 — session prototypes
verified identical across PB 19/22/25 headers — so a single set of
`argtypes`/`restype` covers every modern release.

Calling convention is `__stdcall` (`PBWINAPI_` in `PBORCA.H` expands to
`t WINAPI`). On x86 this dictates `ctypes.WinDLL`, not `CDLL`. Strings are
Unicode (`LPTSTR` resolves to `wchar_t*` when `UNICODE` is defined, which
is the modern default — the header keeps an ANSI shim `PBORCA_SessionOpenA`
that we do not use).

Phase 3 deliverable: session prototypes (Open/Close/SetCurrentAppl/
SetLibraryList/GetError). Library / compile / build prototypes land in
phases 4-6.
"""

from __future__ import annotations

import ctypes
import struct
import sys
from ctypes import POINTER, WINFUNCTYPE, c_int, c_long, c_void_p, c_wchar_p
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pb_orca_mcp.orca.types import PBORCA_COMPERR, PBORCA_DIRENTRY, PBORCA_ENTRYINFO

if TYPE_CHECKING:
    from pb_orca_mcp.discovery import PbInstall

PBORCA_LISTPROC = WINFUNCTYPE(None, POINTER(PBORCA_DIRENTRY), c_void_p)
"""ctypes type for `PBORCA_LISTPROC` — the `__stdcall` callback used by
`PBORCA_LibraryDirectory`. Instances of this type must outlive the call;
the Session stores them in `_callback_refs`."""

PBORCA_ERRPROC = WINFUNCTYPE(None, POINTER(PBORCA_COMPERR), c_void_p)
"""ctypes type for `PBORCA_ERRPROC` — the `__stdcall` callback fired by
the compile/rebuild functions for each diagnostic. Same callback-lifetime
caveat as `PBORCA_LISTPROC`."""

KNOWN_VERSIONS = ("19.0", "22.0", "25.0")
"""PowerBuilder major versions actively tested by v1.

This is a guideline, not a gate: discovery returns every install that ships
`pborc.dll`, including versions outside this tuple (with `tested=False`).
Add a new release here once it has been smoke-tested against the loader.
"""


class OrcaLoadError(RuntimeError):
    """Raised when `pborc.dll` cannot be loaded for the given install."""


class OrcaArchMismatchError(OrcaLoadError):
    """Raised when the DLL arch doesn't match the running Python interpreter."""


@dataclass(frozen=True)
class SessionFns:
    """Bound `__stdcall` entry points for the ORCA session group.

    The fields hold callable `ctypes` function pointers with their
    `argtypes`/`restype` already set by `_bind_session_fns`. Callers pass
    Python `int`/`str` arguments; ctypes handles marshalling.
    """

    SessionOpen: Any
    """`HPBORCA PBORCA_SessionOpen(void)` → returns the handle or 0/NULL on failure."""
    SessionClose: Any
    """`void PBORCA_SessionClose(HPBORCA)`."""
    SessionSetCurrentAppl: Any
    """`INT PBORCA_SessionSetCurrentAppl(HPBORCA, LPTSTR ApplLibName, LPTSTR ApplName)`."""
    SessionSetLibraryList: Any
    """`INT PBORCA_SessionSetLibraryList(HPBORCA, LPTSTR*, INT NumberOfLibs)`."""
    SessionGetError: Any
    """`void PBORCA_SessionGetError(HPBORCA, LPTSTR Buffer, INT BufferSize)`."""


@dataclass(frozen=True)
class LibraryFns:
    """Bound entry points for the ORCA library-management group."""

    LibraryCreate: Any
    """`INT PBORCA_LibraryCreate(HPBORCA, LPTSTR LibName, LPTSTR LibComments)`."""
    LibraryDelete: Any
    """`INT PBORCA_LibraryDelete(HPBORCA, LPTSTR LibName)`."""
    LibraryDirectory: Any
    """`INT PBORCA_LibraryDirectory(HPBORCA, LPTSTR LibName, LPTSTR LibComments,
    INT CmntsBuffLen, PBORCA_LISTPROC ListProc, LPVOID UserData)`."""
    LibraryEntryInformation: Any
    """`INT PBORCA_LibraryEntryInformation(HPBORCA, LPTSTR LibName, LPTSTR EntryName,
    PBORCA_TYPE EntryType, PBORCA_ENTRYINFO *pEntryInfo)`."""
    LibraryEntryExportEx: Any
    """`INT PBORCA_LibraryEntryExportEx(HPBORCA, LPTSTR LibName, LPTSTR EntryName,
    PBORCA_TYPE, LPTSTR Buffer, LONG BufferSize, LONG *pReturnSize)`."""
    LibraryEntryDelete: Any
    """`INT PBORCA_LibraryEntryDelete(HPBORCA, LPTSTR LibName, LPTSTR EntryName, PBORCA_TYPE)`."""
    LibraryEntryMove: Any
    """`INT PBORCA_LibraryEntryMove(HPBORCA, LPTSTR SourceLib, LPTSTR DestLib,
    LPTSTR EntryName, PBORCA_TYPE)`."""
    LibraryCommentModify: Any
    """`INT PBORCA_LibraryCommentModify(HPBORCA, LPTSTR LibName, LPTSTR LibComments)`."""


@dataclass(frozen=True)
class CompileFns:
    """Bound entry points for the ORCA compile/rebuild group."""

    CompileEntryImport: Any
    """`INT PBORCA_CompileEntryImport(HPBORCA, LPTSTR LibName, LPTSTR EntryName,
    PBORCA_TYPE EntryType, LPTSTR Comments, LPTSTR EntrySyntax, LONG SyntaxBuffSize,
    PBORCA_ERRPROC, LPVOID UserData)`."""
    CompileEntryImportList: Any
    """`INT PBORCA_CompileEntryImportList(HPBORCA, LPTSTR* LibNames, LPTSTR* EntryNames,
    PBORCA_TYPE* EntryTypes, LPTSTR* Comments, LPTSTR* SyntaxBuffers, LONG* SyntaxBuffSizes,
    INT NumberOfEntries, PBORCA_ERRPROC, LPVOID UserData)`."""
    CompileEntryRegenerate: Any
    """`INT PBORCA_CompileEntryRegenerate(HPBORCA, LPTSTR LibName, LPTSTR EntryName,
    PBORCA_TYPE, PBORCA_ERRPROC, LPVOID)`."""
    ApplicationRebuild: Any
    """`INT PBORCA_ApplicationRebuild(HPBORCA, PBORCA_REBLD_TYPE, PBORCA_ERRPROC, LPVOID)`."""


@dataclass(frozen=True)
class OrcaApi:
    """A loaded `pborc.dll` ready for ORCA calls."""

    install: PbInstall
    dll: ctypes.WinDLL
    tested: bool
    session: SessionFns
    library: LibraryFns
    compile: CompileFns


def _python_arch() -> str:
    """`x86` if Python is 32-bit, `x64` if 64-bit."""
    return "x86" if struct.calcsize("P") == 4 else "x64"


def _bind_session_fns(dll: ctypes.WinDLL) -> SessionFns:
    """Apply `argtypes`/`restype` to the session group entry points."""
    session_open = dll.PBORCA_SessionOpen
    session_open.argtypes = []
    session_open.restype = c_void_p  # HPBORCA

    session_close = dll.PBORCA_SessionClose
    session_close.argtypes = [c_void_p]
    session_close.restype = None

    set_current_appl = dll.PBORCA_SessionSetCurrentAppl
    set_current_appl.argtypes = [c_void_p, c_wchar_p, c_wchar_p]
    set_current_appl.restype = c_int

    set_lib_list = dll.PBORCA_SessionSetLibraryList
    set_lib_list.argtypes = [c_void_p, POINTER(c_wchar_p), c_int]
    set_lib_list.restype = c_int

    get_error = dll.PBORCA_SessionGetError
    get_error.argtypes = [c_void_p, c_wchar_p, c_int]
    get_error.restype = None

    return SessionFns(
        SessionOpen=session_open,
        SessionClose=session_close,
        SessionSetCurrentAppl=set_current_appl,
        SessionSetLibraryList=set_lib_list,
        SessionGetError=get_error,
    )


def _bind_library_fns(dll: ctypes.WinDLL) -> LibraryFns:
    """Apply `argtypes`/`restype` to the library-management entry points."""
    lib_create = dll.PBORCA_LibraryCreate
    lib_create.argtypes = [c_void_p, c_wchar_p, c_wchar_p]
    lib_create.restype = c_int

    lib_delete = dll.PBORCA_LibraryDelete
    lib_delete.argtypes = [c_void_p, c_wchar_p]
    lib_delete.restype = c_int

    lib_directory = dll.PBORCA_LibraryDirectory
    lib_directory.argtypes = [c_void_p, c_wchar_p, c_wchar_p, c_int, PBORCA_LISTPROC, c_void_p]
    lib_directory.restype = c_int

    entry_info = dll.PBORCA_LibraryEntryInformation
    entry_info.argtypes = [c_void_p, c_wchar_p, c_wchar_p, c_int, POINTER(PBORCA_ENTRYINFO)]
    entry_info.restype = c_int

    entry_export_ex = dll.PBORCA_LibraryEntryExportEx
    entry_export_ex.argtypes = [
        c_void_p, c_wchar_p, c_wchar_p, c_int, c_wchar_p, c_long, POINTER(c_long)
    ]
    entry_export_ex.restype = c_int

    entry_delete = dll.PBORCA_LibraryEntryDelete
    entry_delete.argtypes = [c_void_p, c_wchar_p, c_wchar_p, c_int]
    entry_delete.restype = c_int

    entry_move = dll.PBORCA_LibraryEntryMove
    entry_move.argtypes = [c_void_p, c_wchar_p, c_wchar_p, c_wchar_p, c_int]
    entry_move.restype = c_int

    comment_modify = dll.PBORCA_LibraryCommentModify
    comment_modify.argtypes = [c_void_p, c_wchar_p, c_wchar_p]
    comment_modify.restype = c_int

    return LibraryFns(
        LibraryCreate=lib_create,
        LibraryDelete=lib_delete,
        LibraryDirectory=lib_directory,
        LibraryEntryInformation=entry_info,
        LibraryEntryExportEx=entry_export_ex,
        LibraryEntryDelete=entry_delete,
        LibraryEntryMove=entry_move,
        LibraryCommentModify=comment_modify,
    )


def _bind_compile_fns(dll: ctypes.WinDLL) -> CompileFns:
    """Apply `argtypes`/`restype` to the compile/rebuild entry points."""
    entry_import = dll.PBORCA_CompileEntryImport
    entry_import.argtypes = [
        c_void_p, c_wchar_p, c_wchar_p, c_int, c_wchar_p, c_wchar_p, c_long,
        PBORCA_ERRPROC, c_void_p,
    ]
    entry_import.restype = c_int

    entry_import_list = dll.PBORCA_CompileEntryImportList
    entry_import_list.argtypes = [
        c_void_p,
        POINTER(c_wchar_p), POINTER(c_wchar_p), POINTER(c_int),
        POINTER(c_wchar_p), POINTER(c_wchar_p), POINTER(c_long),
        c_int, PBORCA_ERRPROC, c_void_p,
    ]
    entry_import_list.restype = c_int

    entry_regenerate = dll.PBORCA_CompileEntryRegenerate
    entry_regenerate.argtypes = [c_void_p, c_wchar_p, c_wchar_p, c_int, PBORCA_ERRPROC, c_void_p]
    entry_regenerate.restype = c_int

    app_rebuild = dll.PBORCA_ApplicationRebuild
    app_rebuild.argtypes = [c_void_p, c_int, PBORCA_ERRPROC, c_void_p]
    app_rebuild.restype = c_int

    return CompileFns(
        CompileEntryImport=entry_import,
        CompileEntryImportList=entry_import_list,
        CompileEntryRegenerate=entry_regenerate,
        ApplicationRebuild=app_rebuild,
    )


def load_orca(install: PbInstall) -> OrcaApi:
    """Load `pborc.dll` from `install.orca_dll` and bind ORCA prototypes.

    Raises:
    - `OrcaArchMismatchError` if the DLL arch doesn't match Python's.
    - `OrcaLoadError` if `WinDLL` fails to load the DLL, or required ORCA
      entry points are missing from it.
    """
    py_arch = _python_arch()
    if install.arch != "unknown" and install.arch != py_arch:
        raise OrcaArchMismatchError(
            f"Cannot load {install.orca_dll}: DLL is {install.arch}, "
            f"Python is {py_arch}. Use a {install.arch} Python interpreter."
        )
    if sys.platform != "win32":
        raise OrcaLoadError(f"pborc.dll is Windows-only; running on {sys.platform!r}")
    try:
        dll = ctypes.WinDLL(install.orca_dll)
    except OSError as exc:
        raise OrcaLoadError(f"Failed to load {install.orca_dll}: {exc}") from exc
    try:
        session = _bind_session_fns(dll)
        library = _bind_library_fns(dll)
        compile_ = _bind_compile_fns(dll)
    except AttributeError as exc:
        raise OrcaLoadError(
            f"{install.orca_dll}: missing required ORCA entry point ({exc})"
        ) from exc
    return OrcaApi(
        install=install,
        dll=dll,
        tested=install.version in KNOWN_VERSIONS,
        session=session,
        library=library,
        compile=compile_,
    )
