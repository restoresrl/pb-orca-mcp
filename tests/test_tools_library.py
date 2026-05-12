"""Negative-path tests for `pb_orca_mcp.tools.library` MCP wrappers.

Full happy-path coverage lives in `test_session_library.py` (state machine
via fake API) and `test_session_real.py` (`requires_pb`).
"""

from __future__ import annotations

import pytest

from pb_orca_mcp.orca.session import Session
from pb_orca_mcp.tools import library as lib_tools


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    Session._instance = None


def test_create_without_session_returns_stateerror() -> None:
    out = lib_tools.pb_library_create("foo.pbl")
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"


def test_directory_without_session_returns_stateerror() -> None:
    out = lib_tools.pb_library_directory("foo.pbl")
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"


def test_entry_information_unknown_type_returns_invalidargs() -> None:
    """The type-name validation lives behind the state check; with no
    session this gets STATEERROR. With a session it'd be INVALIDARGS.
    Verifies precedence — see PBL state machine."""
    out = lib_tools.pb_library_entry_information("foo.pbl", "x", "bogus")
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"


def test_entry_move_without_session_returns_stateerror() -> None:
    out = lib_tools.pb_library_entry_move("a.pbl", "b.pbl", "x", "userobject")
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"
