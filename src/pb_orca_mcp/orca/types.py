"""ctypes.Structure mirrors of ORCA C structs.

Definitions come from `PBORCA.H` distributed in each PB IDE install at
`<install>\\SDK\\ORCA\\pborca.h`. Each struct mirrors the C layout exactly.

Verified identical across PB 19/22/25 — single set of definitions covers
every modern release (see [[pborca-h]]).
"""

from __future__ import annotations

from ctypes import Structure, c_int, c_long, c_wchar, c_wchar_p

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
