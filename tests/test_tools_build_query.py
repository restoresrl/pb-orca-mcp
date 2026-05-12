"""Negative-path tests for `pb_orca_mcp.tools.build` and `tools.query`."""

from __future__ import annotations

import pytest

from pb_orca_mcp.orca.session import Session
from pb_orca_mcp.tools import build as build_tools
from pb_orca_mcp.tools import query as query_tools


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    Session._instance = None


def test_executable_create_without_session_returns_stateerror() -> None:
    out = build_tools.pb_executable_create("out.exe")
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"


def test_dynamic_library_create_without_session_returns_stateerror() -> None:
    out = build_tools.pb_dynamic_library_create("foo.pbl")
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"


def test_object_query_hierarchy_without_session_returns_stateerror() -> None:
    out = query_tools.pb_object_query_hierarchy("foo.pbl", "x", "userobject")
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"


def test_object_query_reference_without_session_returns_stateerror() -> None:
    out = query_tools.pb_object_query_reference("foo.pbl", "x", "userobject")
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"


def test_object_regenerate_without_session_returns_stateerror() -> None:
    out = query_tools.pb_object_regenerate("foo.pbl", "x", "userobject")
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"
