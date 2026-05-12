"""Negative-path tests for `pb_orca_mcp.tools.compile` MCP wrappers."""

from __future__ import annotations

import pytest

from pb_orca_mcp.orca.session import Session
from pb_orca_mcp.tools import compile as compile_tools


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    Session._instance = None


def test_compile_entry_import_without_session_returns_stateerror() -> None:
    out = compile_tools.pb_compile_entry_import("foo.pbl", "f", "function", "src")
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"


def test_compile_entry_import_list_without_session_returns_stateerror() -> None:
    out = compile_tools.pb_compile_entry_import_list(
        [{"lib_path": "a.pbl", "entry_name": "x", "entry_type": "function", "syntax": "src"}]
    )
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"


def test_application_rebuild_without_session_returns_stateerror() -> None:
    out = compile_tools.pb_application_rebuild("incremental")
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"


def test_application_rebuild_unknown_type_without_session_returns_stateerror() -> None:
    """State guard wins over type validation. With a session it'd be INVALIDARGS."""
    out = compile_tools.pb_application_rebuild("rebuild")
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"


def test_get_last_compile_errors_no_session_returns_empty() -> None:
    out = compile_tools.pb_get_last_compile_errors()
    assert out == {"errors": []}
