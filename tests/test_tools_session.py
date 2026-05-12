"""Tests for the MCP tool wrappers in `pb_orca_mcp.tools.session`.

The negative paths (no install, ambiguous version, no session open) don't
need a real PB. The full open-cycle test goes through `pb_session_open`
on a real machine and is gated by `requires_pb`.
"""

from __future__ import annotations

from typing import Any

import pytest

from pb_orca_mcp.orca.session import Session
from pb_orca_mcp.tools import session as session_tools


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    Session._instance = None


def test_pb_session_open_without_args_returns_error() -> None:
    out = session_tools.pb_session_open()
    assert out == {
        "error": {
            "code": -1,
            "name": "PB_ORCA_MCP_INVALIDARGS",
            "message": "pb_session_open requires pb_version or install_path",
        }
    }


def test_pb_session_open_unknown_version_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_tools, "discover_pb_installations", lambda: ([], []))
    out = session_tools.pb_session_open(pb_version="99.0")
    assert "error" in out
    assert out["error"]["name"] == "PB_ORCA_MCP_VERSIONNOTFOUND"


def test_pb_session_open_unknown_install_path_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_tools, "discover_pb_installations", lambda: ([], []))
    out = session_tools.pb_session_open(install_path=r"C:\not\here")
    assert "error" in out
    assert out["error"]["name"] == "PB_ORCA_MCP_INSTALLNOTFOUND"


def test_pb_set_current_application_without_session_returns_error() -> None:
    out = session_tools.pb_set_current_application("foo.pbl", "foo")
    assert "error" in out
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"


def test_pb_set_library_list_rejects_empty() -> None:
    # Without an open session, the state check wins before the value check —
    # so we get STATEERROR, not INVALIDARGS. Verifies precedence.
    out = session_tools.pb_set_library_list([])
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"


def test_pb_set_library_list_rejects_empty_when_session_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a (fake) session open, the empty-list rule fires."""
    from dataclasses import dataclass, field

    @dataclass
    class _FakeFns:
        calls: list[Any] = field(default_factory=list)

        def SessionOpen(self) -> int:
            return 1

        def SessionClose(self, h: int) -> None:
            self.calls.append(("close", h))

        def SessionGetError(self, h: int, buf: Any, n: int) -> None:
            self.calls.append(("err", n))

    @dataclass
    class _FakeApi:
        install: Any = None
        session: Any = field(default_factory=_FakeFns)

    Session.instance().open(_FakeApi())  # type: ignore[arg-type]
    try:
        out = session_tools.pb_set_library_list([])
        assert out["error"]["name"] == "PB_ORCA_MCP_INVALIDARGS"
    finally:
        Session.instance().close()


def test_pb_session_close_idempotent() -> None:
    out = session_tools.pb_session_close()
    assert out == {"ok": True, "was_open": False}
