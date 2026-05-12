"""State-machine tests for the Session singleton, using a fake OrcaApi.

No real `pborc.dll` is touched: a stand-in `OrcaApi` records calls and
returns canned values. This exercises the open/close cycle, the
SetCurrentAppl / SetLibraryList wiring, and the state-error guards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from pb_orca_mcp.orca.constants import PBORCA_LIBLISTNOTSET, PBORCA_OK
from pb_orca_mcp.orca.errors import OrcaError
from pb_orca_mcp.orca.session import Session, SessionStateError


@dataclass
class _FakeSessionFns:
    """Records every call and replays canned return values."""

    open_returns: int = 0xDEADBEEF
    set_current_appl_returns: int = PBORCA_OK
    set_lib_list_returns: int = PBORCA_OK
    calls: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)

    def SessionOpen(self) -> int:
        self.calls.append(("SessionOpen", ()))
        return self.open_returns

    def SessionClose(self, handle: int) -> None:
        self.calls.append(("SessionClose", (handle,)))

    def SessionSetCurrentAppl(self, handle: int, lib: str, name: str) -> int:
        self.calls.append(("SessionSetCurrentAppl", (handle, lib, name)))
        return self.set_current_appl_returns

    def SessionSetLibraryList(self, handle: int, array: Any, count: int) -> int:
        self.calls.append(("SessionSetLibraryList", (handle, list(array), count)))
        return self.set_lib_list_returns

    def SessionGetError(self, handle: int, buf: Any, size: int) -> None:
        self.calls.append(("SessionGetError", (handle, size)))


@dataclass
class _FakeInstall:
    version: str = "22.0"
    orca_dll: str = "C:\\fake\\pborc.dll"


@dataclass
class _FakeApi:
    install: _FakeInstall = field(default_factory=_FakeInstall)
    session: _FakeSessionFns = field(default_factory=_FakeSessionFns)


@pytest.fixture
def fresh_session() -> Session:
    """Reset the singleton between tests."""
    Session._instance = None
    return Session.instance()


def test_open_and_close_cycle(fresh_session: Session) -> None:
    api = _FakeApi()
    fresh_session.open(api)  # type: ignore[arg-type]
    assert fresh_session.is_open
    assert fresh_session.install is api.install  # type: ignore[comparison-overlap]
    fresh_session.close()
    assert not fresh_session.is_open
    names = [c[0] for c in api.session.calls]
    assert names == ["SessionOpen", "SessionClose"]


def test_close_is_idempotent(fresh_session: Session) -> None:
    fresh_session.close()
    fresh_session.close()
    assert not fresh_session.is_open


def test_double_open_raises(fresh_session: Session) -> None:
    fresh_session.open(_FakeApi())  # type: ignore[arg-type]
    with pytest.raises(SessionStateError, match="already open"):
        fresh_session.open(_FakeApi())  # type: ignore[arg-type]


def test_open_failure_raises_when_handle_is_null(fresh_session: Session) -> None:
    api = _FakeApi(session=_FakeSessionFns(open_returns=0))
    with pytest.raises(OrcaError):
        fresh_session.open(api)  # type: ignore[arg-type]
    assert not fresh_session.is_open


def test_set_current_application_records_call(fresh_session: Session) -> None:
    api = _FakeApi()
    fresh_session.open(api)  # type: ignore[arg-type]
    fresh_session.set_current_application("foo.pbl", "foo")
    assert fresh_session.current_application == ("foo.pbl", "foo")
    last = api.session.calls[-1]
    assert last[0] == "SessionSetCurrentAppl"
    assert last[1] == (0xDEADBEEF, "foo.pbl", "foo")


def test_set_current_application_surfaces_orca_error(fresh_session: Session) -> None:
    api = _FakeApi(session=_FakeSessionFns(set_current_appl_returns=PBORCA_LIBLISTNOTSET))
    fresh_session.open(api)  # type: ignore[arg-type]
    with pytest.raises(OrcaError) as ei:
        fresh_session.set_current_application("foo.pbl", "foo")
    assert ei.value.code == PBORCA_LIBLISTNOTSET
    assert ei.value.name == "PBORCA_LIBLISTNOTSET"


def test_set_library_list_passes_array(fresh_session: Session) -> None:
    api = _FakeApi()
    fresh_session.open(api)  # type: ignore[arg-type]
    fresh_session.set_library_list(["a.pbl", "b.pbl", "..\\dep\\c.pbd"])
    last = api.session.calls[-1]
    assert last[0] == "SessionSetLibraryList"
    handle, libs, count = last[1]
    assert handle == 0xDEADBEEF
    assert libs == ["a.pbl", "b.pbl", "..\\dep\\c.pbd"]
    assert count == 3
    assert fresh_session.library_list == ("a.pbl", "b.pbl", "..\\dep\\c.pbd")


def test_set_library_list_rejects_empty(fresh_session: Session) -> None:
    fresh_session.open(_FakeApi())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="at least one"):
        fresh_session.set_library_list([])


def test_operations_require_open_session(fresh_session: Session) -> None:
    with pytest.raises(SessionStateError):
        fresh_session.set_current_application("a.pbl", "a")
    with pytest.raises(SessionStateError):
        fresh_session.set_library_list(["a.pbl"])
    with pytest.raises(SessionStateError):
        fresh_session.get_error_text()


def test_singleton_returns_same_instance() -> None:
    Session._instance = None
    a = Session.instance()
    b = Session.instance()
    assert a is b
