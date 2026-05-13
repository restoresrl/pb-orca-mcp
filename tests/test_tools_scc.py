"""Negative-path tests for `pb_orca_mcp.tools.scc` MCP wrappers.

Full state-machine coverage lives in `test_session_scc.py` (fake API).
This file focuses on the MCP-shape exceptions: STATEERROR when no session
is open, INVALIDARGS for malformed input.
"""

from __future__ import annotations

import pytest

from pb_orca_mcp.orca.session import Session
from pb_orca_mcp.tools import scc as scc_tools


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    Session._instance = None


def test_get_connect_properties_without_session_returns_stateerror() -> None:
    out = scc_tools.pb_scc_get_connect_properties("ws.pbw")
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"


def test_connect_offline_without_session_returns_stateerror() -> None:
    out = scc_tools.pb_scc_connect_offline(workspace_file="ws.pbw")
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"


def test_connect_offline_without_workspace_still_validates_session() -> None:
    out = scc_tools.pb_scc_connect_offline()
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"


def test_set_target_without_session_returns_stateerror() -> None:
    out = scc_tools.pb_scc_set_target("target.pbt")
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"


def test_exclude_library_list_without_session_returns_stateerror() -> None:
    out = scc_tools.pb_scc_exclude_library_list(["a.pbl"])
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"


def test_refresh_target_without_session_returns_stateerror() -> None:
    out = scc_tools.pb_scc_refresh_target("incremental")
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"


def test_close_without_session_is_ok() -> None:
    """`scc_close` is idempotent — returns `ok` even with no session open."""
    out = scc_tools.pb_scc_close()
    assert out == {"ok": True}


def test_tools_registered_in_server() -> None:
    """Smoke check: the 6 SCC tools are part of `tool_names()`."""
    from pb_orca_mcp.server import tool_names

    names = tool_names()
    for expected in (
        "pb_scc_get_connect_properties",
        "pb_scc_connect_offline",
        "pb_scc_set_target",
        "pb_scc_exclude_library_list",
        "pb_scc_refresh_target",
        "pb_scc_close",
    ):
        assert expected in names, f"{expected} not registered"
