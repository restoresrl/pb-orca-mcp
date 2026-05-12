"""Tests for the OrcaError decoder."""

from __future__ import annotations

from pb_orca_mcp.orca.constants import PBORCA_LIBLISTNOTSET, PBORCA_OBJNOTFOUND
from pb_orca_mcp.orca.errors import OrcaError


def test_from_code_resolves_known_name() -> None:
    err = OrcaError.from_code(PBORCA_OBJNOTFOUND)
    assert err.code == -3
    assert err.name == "PBORCA_OBJNOTFOUND"
    assert "ORCA error -3" in str(err)
    assert "PBORCA_OBJNOTFOUND" in str(err)


def test_from_code_with_message() -> None:
    err = OrcaError.from_code(PBORCA_LIBLISTNOTSET, message="call set_library_list first")
    assert err.message == "call set_library_list first"
    assert "call set_library_list first" in str(err)


def test_from_code_unknown_falls_back() -> None:
    err = OrcaError.from_code(-9999)
    assert err.code == -9999
    assert "PBORCA_UNKNOWN" in err.name


def test_to_dict_shape() -> None:
    err = OrcaError.from_code(PBORCA_OBJNOTFOUND, message="x")
    assert err.to_dict() == {"code": -3, "name": "PBORCA_OBJNOTFOUND", "message": "x"}
