"""Tiny PE reader for arch detection and VS_VERSION_INFO extraction.

- `read_pe_arch(path)`: classifies a Windows DLL/EXE as `x86`, `x64`, or
  `unknown` from the PE `Machine` field. Used by discovery to flag arch of
  each `pborc.dll` found, so the loader can reject arch mismatches between
  Python and the DLL.
- `read_pe_file_version(path)`: returns `(FileVersion, ProductVersion)`
  strings from the VS_VERSION_INFO resource via Win32 `version.dll`. Used
  as a fallback when discovery finds an install only via filesystem (no
  registry entry).
"""

from __future__ import annotations

import ctypes
import struct
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Literal

PeArch = Literal["x86", "x64", "unknown"]

_MACHINE_X86 = 0x014C
_MACHINE_X64 = 0x8664
_PE_SIGNATURE = 0x00004550  # "PE\0\0"


def read_pe_arch(path: str | Path) -> PeArch:
    """Return the PE `Machine` field of `path` as `x86`/`x64`/`unknown`.

    Raises `OSError` if the file is unreadable, `ValueError` if it is not a
    PE image (no MZ/PE signatures).
    """
    with open(path, "rb") as f:
        mz = f.read(2)
        if mz != b"MZ":
            raise ValueError(f"{path}: not a PE image (no MZ signature)")
        f.seek(0x3C)
        (pe_offset,) = struct.unpack("<I", f.read(4))
        f.seek(pe_offset)
        (sig,) = struct.unpack("<I", f.read(4))
        if sig != _PE_SIGNATURE:
            raise ValueError(f"{path}: not a PE image (no PE signature at 0x{pe_offset:x})")
        (machine,) = struct.unpack("<H", f.read(2))
    if machine == _MACHINE_X86:
        return "x86"
    if machine == _MACHINE_X64:
        return "x64"
    return "unknown"


def read_pe_file_version(path: str | Path) -> tuple[str | None, str | None]:
    """Return `(FileVersion, ProductVersion)` from the PE's VS_VERSION_INFO resource.

    Returns `(None, None)` if the file lacks a VersionInfo resource, the
    queries fail, or the platform isn't Windows. Never raises.
    """
    if sys.platform != "win32":
        return None, None
    try:
        version_dll = ctypes.WinDLL("version", use_last_error=True)
    except OSError:
        return None, None

    get_size = version_dll.GetFileVersionInfoSizeW
    get_size.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    get_size.restype = wintypes.DWORD
    get_info = version_dll.GetFileVersionInfoW
    get_info.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID]
    get_info.restype = wintypes.BOOL
    ver_query = version_dll.VerQueryValueW
    ver_query.argtypes = [
        wintypes.LPCVOID,
        wintypes.LPCWSTR,
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(ctypes.c_uint),
    ]
    ver_query.restype = wintypes.BOOL

    path_str = str(path)
    dummy = wintypes.DWORD()
    size = get_size(path_str, ctypes.byref(dummy))
    if size == 0:
        return None, None
    buf = ctypes.create_string_buffer(size)
    if not get_info(path_str, 0, size, buf):
        return None, None

    lang_ptr = wintypes.LPVOID()
    lang_len = ctypes.c_uint()
    if not ver_query(
        buf, "\\VarFileInfo\\Translation", ctypes.byref(lang_ptr), ctypes.byref(lang_len)
    ):
        return None, None
    if lang_len.value < 4 or lang_ptr.value is None:
        return None, None
    # Read first lang/codepage pair (WORD lang, WORD codepage).
    pair = ctypes.cast(lang_ptr, ctypes.POINTER(ctypes.c_uint16 * 2))[0]
    lang_id = f"{pair[0]:04x}{pair[1]:04x}"

    def _query_string(name: str) -> str | None:
        ptr = wintypes.LPVOID()
        length = ctypes.c_uint()
        sub_block = f"\\StringFileInfo\\{lang_id}\\{name}"
        if not ver_query(buf, sub_block, ctypes.byref(ptr), ctypes.byref(length)):
            return None
        if length.value == 0 or ptr.value is None:
            return None
        # length is in chars including the trailing NUL.
        return ctypes.wstring_at(ptr.value, length.value).rstrip("\x00") or None

    return _query_string("FileVersion"), _query_string("ProductVersion")
