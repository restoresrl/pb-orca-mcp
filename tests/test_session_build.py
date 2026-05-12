"""State-machine tests for `Session.build_*` and `object_query_*` via a fake API.

Verifies that:
- Build flags are folded and forwarded as ints to `ExecutableCreate`.
- Link errors come back as `(success=False, errors=[...])` on `PBORCA_LINKERROR`.
- Hierarchy / reference callbacks accumulate into Python lists with the
  right name + type mapping, without crashing the WINFUNCTYPE lifetime.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from typing import Any

import pytest

from pb_orca_mcp.orca.constants import (
    PBORCA_LINKERROR,
    PBORCA_MACHINE_CODE,
    PBORCA_OBJNOTFOUND,
    PBORCA_OK,
    PBORCA_REFTYPE_OPEN,
    PBORCA_REFTYPE_SIMPLE,
    PBORCA_USEROBJECT,
    PBORCA_WINDOW,
)
from pb_orca_mcp.orca.errors import OrcaError
from pb_orca_mcp.orca.session import Session
from pb_orca_mcp.orca.types import PBORCA_HIERARCHY, PBORCA_LINKERR, PBORCA_REFERENCE


@dataclass
class _FakeSession:
    def SessionOpen(self) -> int:
        return 0xDEADBEEF

    def SessionClose(self, h: int) -> None:
        pass

    def SessionGetError(self, h: int, buf: Any, n: int) -> None:
        pass


@dataclass
class _FakeBuild:
    exe_rc: int = PBORCA_OK
    pbd_rc: int = PBORCA_OK
    hier_rc: int = PBORCA_OK
    ref_rc: int = PBORCA_OK
    fake_link_errors: list[str] = field(default_factory=list)
    fake_ancestors: list[str] = field(default_factory=list)
    fake_refs: list[tuple[str, str, int, int]] = field(default_factory=list)
    calls: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)
    _live: list[Any] = field(default_factory=list)

    def SetExeInfo(self, handle: int, p_info: Any) -> int:
        self.calls.append(("SetExeInfo", (handle,)))
        return PBORCA_OK

    def ExecutableCreate(
        self, handle: int, exe: str, icon: str | None, pbr: str | None,
        linkproc: Any, user: Any, pbd_arr: Any, n_pbd: int, lflags: int, pbcpara: Any,
    ) -> int:
        self.calls.append(("ExecutableCreate", (handle, exe, icon, pbr, n_pbd, lflags)))
        self._live.clear()
        for text in self.fake_link_errors:
            rec = PBORCA_LINKERR()
            rec.lpszMessageText = text
            self._live.append(rec)
            linkproc(ctypes.pointer(rec), None)
        return self.exe_rc

    def DynamicLibraryCreate(
        self, handle: int, lib: str, pbr: str | None, lflags: int, pbcpara: Any,
    ) -> int:
        self.calls.append(("DynamicLibraryCreate", (handle, lib, pbr, lflags)))
        return self.pbd_rc

    def ObjectQueryHierarchy(
        self, handle: int, lib: str, entry: str, type_code: int, hierproc: Any, user: Any,
    ) -> int:
        self.calls.append(("ObjectQueryHierarchy", (handle, lib, entry, type_code)))
        self._live.clear()
        for name in self.fake_ancestors:
            rec = PBORCA_HIERARCHY()
            rec.lpszAncestorName = name
            self._live.append(rec)
            hierproc(ctypes.pointer(rec), None)
        return self.hier_rc

    def ObjectQueryReference(
        self, handle: int, lib: str, entry: str, type_code: int, refproc: Any, user: Any,
    ) -> int:
        self.calls.append(("ObjectQueryReference", (handle, lib, entry, type_code)))
        self._live.clear()
        for lib_name, entry_name, ent_type, ref_type in self.fake_refs:
            rec = PBORCA_REFERENCE()
            rec.lpszLibraryName = lib_name
            rec.lpszEntryName = entry_name
            rec.otEntryType = ent_type
            rec.otEntryRefType = ref_type
            self._live.append(rec)
            refproc(ctypes.pointer(rec), None)
        return self.ref_rc


@dataclass
class _FakeApi:
    install: Any = None
    session: _FakeSession = field(default_factory=_FakeSession)
    library: Any = None
    compile: Any = None
    build: _FakeBuild = field(default_factory=_FakeBuild)


@pytest.fixture
def open_session() -> Session:
    Session._instance = None
    s = Session.instance()
    s.open(_FakeApi())  # type: ignore[arg-type]
    return s


def test_build_executable_flags_folded(open_session: Session) -> None:
    success, errors = open_session.build_executable(
        "out.exe", flags=["machine_code", "optimize_speed"]
    )
    assert success is True
    assert errors == []
    call = open_session._state.api.build.calls[-1]  # type: ignore[union-attr]
    assert call[0] == "ExecutableCreate"
    lflags = call[1][5]
    # machine_code (0x1) + optimize_speed (0x100)
    assert lflags == (PBORCA_MACHINE_CODE | 0x100)


def test_build_executable_link_errors_on_linkerror(open_session: Session) -> None:
    api = open_session._state.api  # type: ignore[union-attr]
    api.build.exe_rc = PBORCA_LINKERROR
    api.build.fake_link_errors = [
        "Cannot resolve external reference: n_cst_missing",
        "Multiple definitions of f_dup",
    ]
    success, errors = open_session.build_executable("out.exe")
    assert success is False
    assert len(errors) == 2
    assert errors[0]["message_text"] == "Cannot resolve external reference: n_cst_missing"
    assert open_session.last_compile_errors == errors


def test_build_executable_other_error_raises(open_session: Session) -> None:
    api = open_session._state.api  # type: ignore[union-attr]
    api.build.exe_rc = PBORCA_OBJNOTFOUND
    with pytest.raises(OrcaError) as ei:
        open_session.build_executable("out.exe")
    assert ei.value.code == PBORCA_OBJNOTFOUND


def test_build_dynamic_library_passes_args(open_session: Session) -> None:
    open_session.build_dynamic_library("foo.pbl", flags=["machine_code"])
    call = open_session._state.api.build.calls[-1]  # type: ignore[union-attr]
    assert call == ("DynamicLibraryCreate", (0xDEADBEEF, "foo.pbl", None, PBORCA_MACHINE_CODE))


def test_set_exe_info_called_before_executable_create(open_session: Session) -> None:
    open_session.build_executable(
        "out.exe", exe_info={"company_name": "Restore srl", "product_name": "TestApp"}
    )
    api = open_session._state.api  # type: ignore[union-attr]
    names = [c[0] for c in api.build.calls]
    assert names == ["SetExeInfo", "ExecutableCreate"]


def test_object_query_hierarchy_returns_ancestor_chain(open_session: Session) -> None:
    api = open_session._state.api  # type: ignore[union-attr]
    api.build.fake_ancestors = ["n_cst_base", "nonvisualobject"]
    out = open_session.object_query_hierarchy("foo.pbl", "n_cst_derived", "userobject")
    assert out == ["n_cst_base", "nonvisualobject"]


def test_object_query_hierarchy_propagates_error(open_session: Session) -> None:
    api = open_session._state.api  # type: ignore[union-attr]
    api.build.hier_rc = PBORCA_OBJNOTFOUND
    with pytest.raises(OrcaError):
        open_session.object_query_hierarchy("foo.pbl", "missing", "userobject")


def test_object_query_reference_decodes_types(open_session: Session) -> None:
    api = open_session._state.api  # type: ignore[union-attr]
    api.build.fake_refs = [
        ("a.pbl", "w_main", PBORCA_WINDOW, PBORCA_REFTYPE_SIMPLE),
        ("a.pbl", "n_cst_main", PBORCA_USEROBJECT, PBORCA_REFTYPE_OPEN),
    ]
    refs = open_session.object_query_reference("foo.pbl", "n_cst_lib", "userobject")
    assert refs == [
        {
            "library": "a.pbl",
            "entry_name": "w_main",
            "entry_type": "window",
            "ref_type": "simple",
        },
        {
            "library": "a.pbl",
            "entry_name": "n_cst_main",
            "entry_type": "userobject",
            "ref_type": "open",
        },
    ]


def test_callback_refs_emptied_after_query(open_session: Session) -> None:
    api = open_session._state.api  # type: ignore[union-attr]
    api.build.fake_ancestors = ["base"]
    open_session.object_query_hierarchy("foo.pbl", "derived", "userobject")
    assert open_session._state.callback_refs == []  # type: ignore[union-attr]
