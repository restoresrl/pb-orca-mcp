"""State-machine tests for `Session.library_*` via a fake `OrcaApi`.

Covers the simpler synchronous methods (create/delete/comment_modify/
entry_information/entry_delete/entry_move). The callback-driven path
(`library_directory`) and the auto-resizing path (`library_entry_export`)
are exercised against a real ORCA DLL in `test_session_real.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from pb_orca_mcp.orca.constants import (
    PBORCA_BADLIBRARY,
    PBORCA_OBJNOTFOUND,
    PBORCA_OK,
    PBORCA_USEROBJECT,
)
from pb_orca_mcp.orca.errors import OrcaError
from pb_orca_mcp.orca.session import Session
from pb_orca_mcp.orca.types import PBORCA_ENTRYINFO


@dataclass
class _FakeSession:
    open_returns: int = 0xDEADBEEF

    def SessionOpen(self) -> int:
        return self.open_returns

    def SessionClose(self, handle: int) -> None:
        pass

    def SessionGetError(self, handle: int, buf: Any, size: int) -> None:
        pass


@dataclass
class _FakeLibrary:
    create_returns: int = PBORCA_OK
    delete_returns: int = PBORCA_OK
    comment_returns: int = PBORCA_OK
    info_returns: int = PBORCA_OK
    entry_delete_returns: int = PBORCA_OK
    entry_move_returns: int = PBORCA_OK
    info_payload: tuple[int, int, int, str] = (1234, 5678, 9999, "demo comment")
    calls: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)

    def LibraryCreate(self, handle: int, lib: str, comments: str) -> int:
        self.calls.append(("LibraryCreate", (handle, lib, comments)))
        return self.create_returns

    def LibraryDelete(self, handle: int, lib: str) -> int:
        self.calls.append(("LibraryDelete", (handle, lib)))
        return self.delete_returns

    def LibraryCommentModify(self, handle: int, lib: str, comments: str) -> int:
        self.calls.append(("LibraryCommentModify", (handle, lib, comments)))
        return self.comment_returns

    def LibraryEntryInformation(
        self, handle: int, lib: str, entry: str, type_code: int, p_info: Any
    ) -> int:
        self.calls.append(("LibraryEntryInformation", (handle, lib, entry, type_code)))
        if self.info_returns == PBORCA_OK:
            create_time, obj_size, src_size, comment = self.info_payload
            info: PBORCA_ENTRYINFO = p_info.contents
            info.lCreateTime = create_time
            info.lObjectSize = obj_size
            info.lSourceSize = src_size
            # ctypes accepts assigning a str to a `c_wchar * N` field:
            # writes the chars and NUL-terminates if shorter than N.
            info.szComments = comment
        return self.info_returns

    def LibraryEntryDelete(self, handle: int, lib: str, entry: str, type_code: int) -> int:
        self.calls.append(("LibraryEntryDelete", (handle, lib, entry, type_code)))
        return self.entry_delete_returns

    def LibraryEntryMove(
        self, handle: int, source: str, dest: str, entry: str, type_code: int
    ) -> int:
        self.calls.append(("LibraryEntryMove", (handle, source, dest, entry, type_code)))
        return self.entry_move_returns


@dataclass
class _FakeApi:
    install: Any = None
    session: _FakeSession = field(default_factory=_FakeSession)
    library: _FakeLibrary = field(default_factory=_FakeLibrary)
    dll_search_handles: tuple[Any, ...] = ()
    original_path: str = ""


@pytest.fixture
def open_session() -> Session:
    Session._instance = None
    s = Session.instance()
    s.open(_FakeApi())  # type: ignore[arg-type]
    return s


def test_library_create_passes_through(open_session: Session) -> None:
    open_session.library_create("foo.pbl", "demo")
    api = open_session._state.api  # type: ignore[union-attr]
    assert api.library.calls[-1] == ("LibraryCreate", (0xDEADBEEF, "foo.pbl", "demo"))


def test_library_create_default_comment_is_empty(open_session: Session) -> None:
    open_session.library_create("foo.pbl")
    api = open_session._state.api  # type: ignore[union-attr]
    assert api.library.calls[-1] == ("LibraryCreate", (0xDEADBEEF, "foo.pbl", ""))


def test_library_create_surfaces_error(open_session: Session) -> None:
    api = open_session._state.api  # type: ignore[union-attr]
    api.library.create_returns = PBORCA_BADLIBRARY
    with pytest.raises(OrcaError) as ei:
        open_session.library_create("bad.pbl")
    assert ei.value.code == PBORCA_BADLIBRARY


def test_library_delete_passes_through(open_session: Session) -> None:
    open_session.library_delete("foo.pbl")
    api = open_session._state.api  # type: ignore[union-attr]
    assert api.library.calls[-1] == ("LibraryDelete", (0xDEADBEEF, "foo.pbl"))


def test_library_comment_modify_passes_through(open_session: Session) -> None:
    open_session.library_comment_modify("foo.pbl", "new comment")
    api = open_session._state.api  # type: ignore[union-attr]
    assert api.library.calls[-1] == (
        "LibraryCommentModify",
        (0xDEADBEEF, "foo.pbl", "new comment"),
    )


def test_library_entry_information_returns_struct_fields(open_session: Session) -> None:
    out = open_session.library_entry_information("foo.pbl", "n_cst_main", "userobject")
    assert out == {
        "name": "n_cst_main",
        "type": "userobject",
        "object_size": 5678,
        "source_size": 9999,
        "create_time": 1234,
        "comment": "demo comment",
    }
    api = open_session._state.api  # type: ignore[union-attr]
    last = api.library.calls[-1]
    assert last[0] == "LibraryEntryInformation"
    assert last[1] == (0xDEADBEEF, "foo.pbl", "n_cst_main", PBORCA_USEROBJECT)


def test_library_entry_information_unknown_type_raises(open_session: Session) -> None:
    with pytest.raises(ValueError, match="unknown entry type"):
        open_session.library_entry_information("foo.pbl", "x", "bogus")


def test_library_entry_information_surfaces_obj_not_found(open_session: Session) -> None:
    api = open_session._state.api  # type: ignore[union-attr]
    api.library.info_returns = PBORCA_OBJNOTFOUND
    with pytest.raises(OrcaError) as ei:
        open_session.library_entry_information("foo.pbl", "missing", "userobject")
    assert ei.value.code == PBORCA_OBJNOTFOUND


def test_library_entry_delete_passes_type_code(open_session: Session) -> None:
    open_session.library_entry_delete("foo.pbl", "n_cst_main", "userobject")
    api = open_session._state.api  # type: ignore[union-attr]
    assert api.library.calls[-1] == (
        "LibraryEntryDelete",
        (0xDEADBEEF, "foo.pbl", "n_cst_main", PBORCA_USEROBJECT),
    )


def test_library_entry_move_passes_args(open_session: Session) -> None:
    open_session.library_entry_move("a.pbl", "b.pbl", "n_cst_main", "userobject")
    api = open_session._state.api  # type: ignore[union-attr]
    assert api.library.calls[-1] == (
        "LibraryEntryMove",
        (0xDEADBEEF, "a.pbl", "b.pbl", "n_cst_main", PBORCA_USEROBJECT),
    )
