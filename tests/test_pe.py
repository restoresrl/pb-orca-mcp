"""Tests for `pb_orca_mcp._pe.read_pe_arch` using synthetic PE bytes."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from pb_orca_mcp._pe import read_pe_arch


def _make_pe_bytes(machine: int, pe_offset: int = 0x80) -> bytes:
    """Build the smallest byte sequence `read_pe_arch` accepts."""
    buf = bytearray(pe_offset + 6)
    buf[0:2] = b"MZ"
    struct.pack_into("<I", buf, 0x3C, pe_offset)
    struct.pack_into("<I", buf, pe_offset, 0x00004550)
    struct.pack_into("<H", buf, pe_offset + 4, machine)
    return bytes(buf)


def test_read_pe_arch_x86(tmp_path: Path) -> None:
    p = tmp_path / "tiny.dll"
    p.write_bytes(_make_pe_bytes(0x014C))
    assert read_pe_arch(p) == "x86"


def test_read_pe_arch_x64(tmp_path: Path) -> None:
    p = tmp_path / "tiny.dll"
    p.write_bytes(_make_pe_bytes(0x8664))
    assert read_pe_arch(p) == "x64"


def test_read_pe_arch_unknown_machine(tmp_path: Path) -> None:
    p = tmp_path / "tiny.dll"
    p.write_bytes(_make_pe_bytes(0x01C4))  # ARM
    assert read_pe_arch(p) == "unknown"


def test_read_pe_arch_rejects_non_pe(tmp_path: Path) -> None:
    p = tmp_path / "notpe.dll"
    p.write_bytes(b"This is not a PE file at all")
    with pytest.raises(ValueError, match="MZ"):
        read_pe_arch(p)


def test_read_pe_arch_rejects_mz_without_pe_signature(tmp_path: Path) -> None:
    buf = bytearray(0x100)
    buf[0:2] = b"MZ"
    struct.pack_into("<I", buf, 0x3C, 0x80)
    # No "PE\0\0" at offset 0x80.
    p = tmp_path / "fake.dll"
    p.write_bytes(bytes(buf))
    with pytest.raises(ValueError, match="PE signature"):
        read_pe_arch(p)
