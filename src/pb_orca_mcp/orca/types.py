"""ctypes.Structure mirrors of ORCA C structs.

Definitions come from `PBORCA.H` distributed in each PB IDE install at
`<install>\\SDK\\ORCA\\pborca.h`. Each struct mirrors the C layout exactly.

Verified identical across PB 19/22/25 — single set of definitions covers
every modern release (see [[pborca-h]]).
"""

from __future__ import annotations

from ctypes import Structure, c_int, c_long, c_uint, c_void_p, c_wchar, c_wchar_p

from pb_orca_mcp.orca.constants import (
    PBORCA_MAXCOMMENT,
    PBORCA_SCC_NAME_LEN,
    PBORCA_SCC_PATH_LEN,
    PBORCA_SCC_USER_LEN,
)

_COMMENT_BUF_SIZE = PBORCA_MAXCOMMENT + 1
"""`TCHAR szComments[PBORCA_MAXCOMMENT + 1]` — 256 wchars including NUL."""

_SCC_NAME_BUF = PBORCA_SCC_NAME_LEN + 1
_SCC_USER_BUF = PBORCA_SCC_USER_LEN + 1
_SCC_PATH_BUF = PBORCA_SCC_PATH_LEN + 1


class PBORCA_DIRENTRY(Structure):
    """Callback record for `PBORCA_LibraryDirectory`.

    The header places `szComments` first as a fixed-size inline array, then
    the longs, then pointers. ctypes mirrors the layout exactly.
    """

    _fields_ = [
        ("szComments", c_wchar * _COMMENT_BUF_SIZE),
        ("lCreateTime", c_long),
        ("lEntrySize", c_long),
        ("lpszEntryName", c_wchar_p),
        ("otEntryType", c_int),
    ]


class PBORCA_ENTRYINFO(Structure):
    """Output struct for `PBORCA_LibraryEntryInformation`."""

    _fields_ = [
        ("szComments", c_wchar * _COMMENT_BUF_SIZE),
        ("lCreateTime", c_long),
        ("lObjectSize", c_long),
        ("lSourceSize", c_long),
    ]


class PBORCA_COMPERR(Structure):
    """Callback record for `PBORCA_ERRPROC` (compile/rebuild error reporting).

    `iLevel` semantics aren't formally documented in `PBORCA.H`; observed
    convention from PB ATL/build tools is `0=error`, `1=warning`,
    `2=information`. The wrapper exposes the raw int alongside a best-
    effort name so callers can rely on whichever they trust.
    """

    _fields_ = [
        ("iLevel", c_int),
        ("lpszMessageNumber", c_wchar_p),
        ("lpszMessageText", c_wchar_p),
        ("iColumnNumber", c_uint),
        ("iLineNumber", c_uint),
    ]


class PBORCA_LINKERR(Structure):
    """Callback record for `PBORCA_LNKPROC` (executable-build link errors)."""

    _fields_ = [
        ("lpszMessageText", c_wchar_p),
    ]


class PBORCA_HIERARCHY(Structure):
    """Callback record for `PBORCA_HIERPROC` (`ObjectQueryHierarchy` ancestor chain)."""

    _fields_ = [
        ("lpszAncestorName", c_wchar_p),
    ]


class PBORCA_REFERENCE(Structure):
    """Callback record for `PBORCA_REFPROC` (`ObjectQueryReference`).

    Carries the outgoing refs of the queried object: what it calls/uses.
    """

    _fields_ = [
        ("lpszLibraryName", c_wchar_p),
        ("lpszEntryName", c_wchar_p),
        ("otEntryType", c_int),
        ("otEntryRefType", c_int),
    ]


class PBORCA_SCC(Structure):
    """Connection/config struct shared by all `PBORCA_Scc*` functions.

    The C layout is documented in `PBORCA.H`. Field widths come from
    `PBORCA_SCC_NAME_LEN+1`, `_USER_LEN+1`, `_PATH_LEN+1` in the header.

    `fpSccMsgHandler` (`LPTEXTOUTPROC`) takes an ANSI (`LPCSTR`) buffer —
    unlike every other callback in ORCA which is Unicode. `fpOrcaMsgHandler`
    (`PBORCA_BLDPROC`) is Unicode. Both pointers are stored as `c_void_p`
    here; the Session installs `ctypes` `WINFUNCTYPE` instances when needed
    and keeps them alive in `scc_callback_refs` for the connect lifetime.

    `pCommBlk` is the opaque SCC communication block. Always `None` from
    Python.
    """

    _fields_ = [
        ("hWnd", c_void_p),
        ("szProviderName", c_wchar * _SCC_NAME_BUF),
        ("lCapabilities", c_long),
        ("szUserID", c_wchar * _SCC_USER_BUF),
        ("szProject", c_wchar * _SCC_PATH_BUF),
        ("szLocalProjPath", c_wchar * _SCC_PATH_BUF),
        ("szAuxPath", c_wchar * _SCC_PATH_BUF),
        ("szLogFile", c_wchar * _SCC_PATH_BUF),
        ("fpSccMsgHandler", c_void_p),
        ("fpOrcaMsgHandler", c_void_p),
        ("lCommentLen", c_long),
        ("lAppend", c_long),
        ("pCommBlk", c_void_p),
        ("lDeleteTempFiles", c_long),
        ("bDeletePblFlag", c_int),
    ]


class PBORCA_SETTARGET(Structure):
    """Callback record for `PBORCA_SETTGTPROC` fired by `PBORCA_SccSetTarget`.

    The callback fires once per library affected by the target setup. The
    Session accumulates `lpszLibraryName` values into a list returned to the
    caller.
    """

    _fields_ = [
        ("lpszLibraryName", c_wchar_p),
    ]


class PBORCA_CONFIG_SESSION(Structure):
    """Session-wide options for `PBORCA_ConfigureSession`.

    This is the struct that turns ORCA's source export from "fill a wide
    buffer" into "write a `.sr*` file to disk", which is how pb-orca produces
    text sources without ever formatting a byte itself.

    Field notes, all verified against a real PB 22.0 workspace:

    - `eClobber`: only `PBORCA_CLOBBER` overwrites an existing file; the other
      three values return `PBORCA_OBJEXISTS (-8)`.
    - `eExportEncoding`: affects the **buffer** path too, not just files. With
      `PBORCA_UTF8` set, `LibraryEntryExportEx` packs UTF-8 bytes into the
      wide buffer and the returned Python string is mojibake. Keep it at
      `PBORCA_UNICODE` for every buffer export.
    - `bExportHeaders`: prepends `$PBExportHeader$<entry>.<ext>` and, when the
      object carries a comment, `$PBExportComments$<comment>`.
    - `bExportIncludeBinary`: required for objects with a binary part
      (DataWindows) or that part is dropped from the exported source.
    - `bExportCreateFile` + `pExportDirectory`: write-to-file mode. **The
      directory must already exist** — ORCA does not create it and returns
      `PBORCA_OBJEXISTS (-8)` if it is missing.
    - `eImportEncoding`: describes the bytes behind the `syntax` pointer of
      `CompileEntryImport`. ctypes always marshals `str` as UTF-16, so this
      must stay `PBORCA_UNICODE`; anything else makes the import fail with
      `C0114`.
    - `bDebug`: compile with the debug directive (also settable via
      `PBORCA_SetDebug`).

    The call replaces the whole configuration, so a zeroed struct restores the
    defaults, and the effect is reversible: switching to file mode and back
    leaves buffer exports byte-for-byte as they were.
    """

    _fields_ = [
        ("eClobber", c_int),
        ("eExportEncoding", c_int),
        ("bExportHeaders", c_int),
        ("bExportIncludeBinary", c_int),
        ("bExportCreateFile", c_int),
        ("pExportDirectory", c_wchar_p),
        ("eImportEncoding", c_int),
        ("bDebug", c_int),
        ("filler2", c_void_p),
        ("filler3", c_void_p),
        ("filler4", c_void_p),
    ]


class PBORCA_EXEINFO(Structure):
    """Optional version-info struct for `PBORCA_SetExeInfo` before `ExecutableCreate`.

    All fields are nullable `LPTSTR`; pass `None` to leave a field unset.
    Each populated field maps to the corresponding Windows VS_VERSION_INFO
    string entry in the produced `.exe`.
    """

    _fields_ = [
        ("lpszCompanyName", c_wchar_p),
        ("lpszProductName", c_wchar_p),
        ("lpszDescription", c_wchar_p),
        ("lpszCopyright", c_wchar_p),
        ("lpszFileVersion", c_wchar_p),
        ("lpszFileVersionNum", c_wchar_p),
        ("lpszProductVersion", c_wchar_p),
        ("lpszProductVersionNum", c_wchar_p),
        ("lpszManifestInfo", c_wchar_p),
    ]
