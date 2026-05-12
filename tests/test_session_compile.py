"""State-machine tests for `Session.compile_*` via a fake `OrcaApi`.

The fake compile group invokes the supplied error callback with synthetic
`PBORCA_COMPERR` entries before returning a configurable rc, exercising
the full callback path (lifetime, accumulation, level mapping) without
loading `pborc.dll`.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from typing import Any

import pytest

from pb_orca_mcp.orca.constants import (
    PBORCA_COMPERROR,
    PBORCA_FULL_REBUILD,
    PBORCA_LIBLISTNOTSET,
    PBORCA_OK,
    PBORCA_USEROBJECT,
)
from pb_orca_mcp.orca.errors import OrcaError
from pb_orca_mcp.orca.session import Session
from pb_orca_mcp.orca.types import PBORCA_COMPERR


@dataclass
class _FakeSession:
    def SessionOpen(self) -> int:
        return 0xDEADBEEF

    def SessionClose(self, h: int) -> None:
        pass

    def SessionGetError(self, h: int, buf: Any, n: int) -> None:
        pass


@dataclass
class _FakeCompile:
    rc: int = PBORCA_OK
    fake_errors: list[tuple[int, str, str, int, int]] = field(default_factory=list)
    """List of (level, message_number, message_text, column, line)."""
    calls: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)
    # Keep PBORCA_COMPERR instances alive for the duration of each call so
    # their c_wchar_p members aren't freed before the callback reads them.
    _live_records: list[PBORCA_COMPERR] = field(default_factory=list)

    def _replay(self, errproc: Any) -> None:
        self._live_records.clear()
        for level, num, text, col, line in self.fake_errors:
            rec = PBORCA_COMPERR()
            rec.iLevel = level
            rec.lpszMessageNumber = num
            rec.lpszMessageText = text
            rec.iColumnNumber = col
            rec.iLineNumber = line
            self._live_records.append(rec)
            errproc(ctypes.pointer(rec), None)

    def CompileEntryImport(
        self, handle: int, lib: str, entry: str, type_code: int,
        comments: str, syntax: str, size: int, errproc: Any, user: Any,
    ) -> int:
        self.calls.append(("CompileEntryImport", (handle, lib, entry, type_code, comments, size)))
        self._replay(errproc)
        return self.rc

    def CompileEntryImportList(
        self, handle: int, libs: Any, names: Any, types: Any, comments: Any,
        syntaxes: Any, sizes: Any, n: int, errproc: Any, user: Any,
    ) -> int:
        self.calls.append(("CompileEntryImportList", (handle, n)))
        self._replay(errproc)
        return self.rc

    def CompileEntryRegenerate(
        self, handle: int, lib: str, entry: str, type_code: int, errproc: Any, user: Any,
    ) -> int:
        self.calls.append(("CompileEntryRegenerate", (handle, lib, entry, type_code)))
        self._replay(errproc)
        return self.rc

    def ApplicationRebuild(
        self, handle: int, type_code: int, errproc: Any, user: Any,
    ) -> int:
        self.calls.append(("ApplicationRebuild", (handle, type_code)))
        self._replay(errproc)
        return self.rc


@dataclass
class _FakeApi:
    install: Any = None
    session: _FakeSession = field(default_factory=_FakeSession)
    library: Any = None
    compile: _FakeCompile = field(default_factory=_FakeCompile)


@pytest.fixture
def open_session() -> Session:
    Session._instance = None
    s = Session.instance()
    s.open(_FakeApi())  # type: ignore[arg-type]
    return s


def test_compile_entry_import_success_with_no_errors(open_session: Session) -> None:
    success, errors = open_session.compile_entry_import(
        "foo.pbl", "f_demo", "function", "global function int f_demo(); return 1 end function"
    )
    assert success is True
    assert errors == []
    last = open_session._state.api.compile.calls[-1]  # type: ignore[union-attr]
    assert last[0] == "CompileEntryImport"


def test_compile_entry_import_reports_errors_on_comperror(open_session: Session) -> None:
    api = open_session._state.api  # type: ignore[union-attr]
    api.compile.rc = PBORCA_COMPERROR
    api.compile.fake_errors = [
        (0, "C0042", "Undefined function: getfoo", 8, 142),
        (1, "C0099", "Unreferenced variable: ll_unused", 1, 158),
    ]
    success, errors = open_session.compile_entry_import(
        "foo.pbl", "n_cst_main", "userobject", "fake source"
    )
    assert success is False
    assert len(errors) == 2
    assert errors[0] == {
        "level": 0,
        "level_name": "error",
        "message_number": "C0042",
        "message_text": "Undefined function: getfoo",
        "column": 8,
        "line": 142,
    }
    assert errors[1]["level_name"] == "warning"
    assert open_session.last_compile_errors == errors


def test_compile_entry_import_other_error_raises(open_session: Session) -> None:
    api = open_session._state.api  # type: ignore[union-attr]
    api.compile.rc = PBORCA_LIBLISTNOTSET
    with pytest.raises(OrcaError) as ei:
        open_session.compile_entry_import(
            "foo.pbl", "n_cst_main", "userobject", "fake source"
        )
    assert ei.value.code == PBORCA_LIBLISTNOTSET


def test_compile_entry_import_unknown_type_raises(open_session: Session) -> None:
    with pytest.raises(ValueError, match="unknown entry type"):
        open_session.compile_entry_import(
            "foo.pbl", "f_demo", "bogus", "fake source"
        )


def test_compile_entry_import_list_passes_count(open_session: Session) -> None:
    items = [
        {"lib_path": "a.pbl", "entry_name": "f_a", "entry_type": "function", "syntax": "src1"},
        {"lib_path": "a.pbl", "entry_name": "f_b", "entry_type": "function", "syntax": "src2"},
    ]
    success, errors = open_session.compile_entry_import_list(items)
    assert success is True
    assert errors == []
    last = open_session._state.api.compile.calls[-1]  # type: ignore[union-attr]
    assert last == ("CompileEntryImportList", (0xDEADBEEF, 2))


def test_compile_entry_import_list_rejects_empty(open_session: Session) -> None:
    with pytest.raises(ValueError, match="at least one"):
        open_session.compile_entry_import_list([])


def test_application_rebuild_passes_type_code(open_session: Session) -> None:
    open_session.application_rebuild("full")
    last = open_session._state.api.compile.calls[-1]  # type: ignore[union-attr]
    assert last == ("ApplicationRebuild", (0xDEADBEEF, PBORCA_FULL_REBUILD))


def test_compile_entry_regenerate_passes_args(open_session: Session) -> None:
    open_session.compile_entry_regenerate("foo.pbl", "n_cst_main", "userobject")
    last = open_session._state.api.compile.calls[-1]  # type: ignore[union-attr]
    assert last == (
        "CompileEntryRegenerate",
        (0xDEADBEEF, "foo.pbl", "n_cst_main", PBORCA_USEROBJECT),
    )


def test_callback_refs_emptied_after_call(open_session: Session) -> None:
    open_session.compile_entry_import(
        "foo.pbl", "f_demo", "function", "src"
    )
    state = open_session._state  # type: ignore[union-attr]
    assert state.callback_refs == []


def test_last_compile_errors_independent_of_returned_list(open_session: Session) -> None:
    """Mutating the returned list mustn't affect the cached one."""
    api = open_session._state.api  # type: ignore[union-attr]
    api.compile.fake_errors = [(0, "C0001", "boom", 1, 1)]
    api.compile.rc = PBORCA_COMPERROR
    _, errors = open_session.compile_entry_import("foo.pbl", "x", "function", "src")
    errors.clear()
    assert len(open_session.last_compile_errors) == 1
