"""Negative-path tests for `pb_orca_mcp.tools.scc` MCP wrappers.

Full state-machine coverage lives in `test_session_scc.py` (fake API).
This file focuses on the MCP-shape exceptions: STATEERROR when no session
is open, INVALIDARGS for malformed input.
"""

from __future__ import annotations

from typing import Any

import pytest

from pb_orca_mcp.orca.constants import PBORCA_GETCONNECT_REQ, PBORCA_REGREADERROR, PBORCA_SCCFAILURE
from pb_orca_mcp.orca.errors import OrcaError
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


class _StubSession:
    """Minimal `Session`-like stub for tool-layer tests that need a faked SCC layer."""

    def __init__(
        self,
        get_connect_returns: int | dict[str, Any],
        connect_offline_result: dict[str, Any] | None = None,
    ) -> None:
        self._get_connect_returns = get_connect_returns
        self._connect_offline_result = connect_offline_result or {"capabilities": 0}
        self.connect_offline_called_with: dict[str, Any] | None = None

    def scc_get_connect_properties(self, workspace_file: str) -> dict[str, Any]:
        if isinstance(self._get_connect_returns, int):
            raise OrcaError.from_code(self._get_connect_returns)
        return self._get_connect_returns

    def scc_connect_offline(self, config: dict[str, Any]) -> dict[str, Any]:
        self.connect_offline_called_with = config
        return self._connect_offline_result


@pytest.mark.parametrize("tolerated_code", [PBORCA_REGREADERROR, PBORCA_GETCONNECT_REQ])
def test_connect_offline_tolerates_workspace_without_scc_block(
    monkeypatch: pytest.MonkeyPatch, tolerated_code: int
) -> None:
    """git/svn `.pbw` has no SCC block — pre-read fails with -23/-31 but connect proceeds."""
    stub = _StubSession(get_connect_returns=tolerated_code)
    monkeypatch.setattr(Session, "instance", classmethod(lambda cls: stub))
    out = scc_tools.pb_scc_connect_offline(workspace_file="ws.pbw", local_proj_path="C:\\proj")
    assert out["ok"] is True
    assert stub.connect_offline_called_with is not None
    assert stub.connect_offline_called_with["local_proj_path"] == "C:\\proj"


def test_connect_offline_still_propagates_other_pre_read_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-tolerated codes (e.g. SCCFAILURE) must surface as errors, not be swallowed."""
    stub = _StubSession(get_connect_returns=PBORCA_SCCFAILURE)
    monkeypatch.setattr(Session, "instance", classmethod(lambda cls: stub))
    out = scc_tools.pb_scc_connect_offline(workspace_file="ws.pbw")
    assert "error" in out
    assert out["error"]["code"] == PBORCA_SCCFAILURE
    assert stub.connect_offline_called_with is None


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
