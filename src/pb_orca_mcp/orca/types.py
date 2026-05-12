"""ctypes.Structure mirrors of ORCA C structs.

Definitions come from `PBORCA.H` distributed in each PB IDE install at
`<install>\\SDK\\ORCA\\pborca.h`. Each struct mirrors the C layout exactly.

Verified identical across PB 19/22/25 — single set of definitions covers
every modern release (see [[pborca-h]]).
"""

from __future__ import annotations

from ctypes import Structure, c_int, c_long, c_uint, c_wchar, c_wchar_p

from pb_orca_mcp.orca.constants import PBORCA_MAXCOMMENT

_COMMENT_BUF_SIZE = PBORCA_MAXCOMMENT + 1
"""`TCHAR szComments[PBORCA_MAXCOMMENT + 1]` — 256 wchars including NUL."""


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
    """Callback record for `PBORCA_REFPROC` (`ObjectQueryReference` — who refs whom)."""

    _fields_ = [
        ("lpszLibraryName", c_wchar_p),
        ("lpszEntryName", c_wchar_p),
        ("otEntryType", c_int),
        ("otEntryRefType", c_int),
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
