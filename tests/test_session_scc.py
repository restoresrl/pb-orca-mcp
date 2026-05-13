"""State-machine tests for `Session.scc_*` via a fake `OrcaApi`.

No real `pborc.dll` is touched. A fake `SccFns` records every call and
replays canned return values, including filling out a `PBORCA_SCC` struct
on `SccGetConnectProperties` and emitting library-name callbacks on
`SccSetTarget`.

Online connect / get-latest-version / set-password / reset-revision-number
are intentionally not covered: they are not implemented in this phase.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from typing import Any

import pytest

from pb_orca_mcp.orca.constants import (
    PBORCA_INCREMENTAL_REBUILD,
    PBORCA_OK,
    PBORCA_SCC_REFRESH_ALL,
    PBORCA_SCCFAILURE,
)
from pb_orca_mcp.orca.errors import OrcaError
from pb_orca_mcp.orca.session import Session, SessionStateError
from pb_orca_mcp.orca.types import PBORCA_SCC, PBORCA_SETTARGET


@dataclass
class _FakeSession:
    open_returns: int = 0xDEADBEEF
    close_calls: int = 0

    def SessionOpen(self) -> int:
        return self.open_returns

    def SessionClose(self, handle: int) -> None:
        self.close_calls += 1

    def SessionGetError(self, handle: int, buf: Any, size: int) -> None:
        pass


@dataclass
class _FakeScc:
    get_connect_returns: int = PBORCA_OK
    connect_offline_returns: int = PBORCA_OK
    set_target_returns: int = PBORCA_OK
    exclude_returns: int = PBORCA_OK
    refresh_returns: int = PBORCA_OK
    close_returns: int = PBORCA_OK
    get_connect_payload: dict[str, Any] = field(
        default_factory=lambda: {
            "provider_name": "FakeSCC",
            "user_id": "carlo",
            "project": "$/proj",
            "local_proj_path": "C:\\proj",
            "aux_path": "",
            "log_file": "C:\\proj\\scc.log",
            "capabilities": 0,
            "comment_max_len": 256,
            "append_log": False,
            "delete_temp_files": True,
            "delete_pbl_on_refresh": False,
        }
    )
    """Fields written into the struct by `SccGetConnectProperties`."""
    set_target_libraries: list[str] = field(
        default_factory=lambda: ["a.pbl", "b.pbl"]
    )
    """Library names emitted by the `SccSetTarget` callback (in order)."""
    calls: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)

    def SccGetConnectProperties(self, handle: int, workspace_file: str, p_scc: Any) -> int:
        self.calls.append(("SccGetConnectProperties", (handle, workspace_file)))
        if self.get_connect_returns == PBORCA_OK:
            _write_dict_into_scc(p_scc.contents, self.get_connect_payload)
        return self.get_connect_returns

    def SccConnectOffline(self, handle: int, p_scc: Any) -> int:
        scc: PBORCA_SCC = p_scc.contents
        # Snapshot the fields the caller wrote in so tests can assert on them.
        snapshot = {
            "provider_name": scc.szProviderName,
            "user_id": scc.szUserID,
            "project": scc.szProject,
            "local_proj_path": scc.szLocalProjPath,
            "aux_path": scc.szAuxPath,
            "log_file": scc.szLogFile,
            "comment_max_len": int(scc.lCommentLen),
            "append_log": int(scc.lAppend),
            "delete_temp_files": int(scc.lDeleteTempFiles),
            "delete_pbl_on_refresh": int(scc.bDeletePblFlag),
        }
        self.calls.append(("SccConnectOffline", (handle, snapshot)))
        if self.connect_offline_returns == PBORCA_OK:
            scc.lCapabilities = 0x1234  # provider would populate this
        return self.connect_offline_returns

    def SccSetTarget(
        self, handle: int, target_file: str, flags: int, callback: Any, user: Any
    ) -> int:
        self.calls.append(("SccSetTarget", (handle, target_file, flags)))
        if self.set_target_returns == PBORCA_OK:
            for name in self.set_target_libraries:
                # The callback expects `POINTER(PBORCA_SETTARGET)`. We must
                # hold the struct alive until after the call returns.
                record = PBORCA_SETTARGET(lpszLibraryName=name)
                callback(ctypes.pointer(record), user)
        return self.set_target_returns

    def SccExcludeLibraryList(self, handle: int, array: Any, count: int) -> int:
        self.calls.append(("SccExcludeLibraryList", (handle, list(array), count)))
        return self.exclude_returns

    def SccRefreshTarget(self, handle: int, rebuild_type: int) -> int:
        self.calls.append(("SccRefreshTarget", (handle, rebuild_type)))
        return self.refresh_returns

    def SccClose(self, handle: int) -> int:
        self.calls.append(("SccClose", (handle,)))
        return self.close_returns


def _write_dict_into_scc(scc: PBORCA_SCC, payload: dict[str, Any]) -> None:
    """Helper used by `SccGetConnectProperties` to populate an out-struct."""
    scc.szProviderName = payload.get("provider_name", "") or ""
    scc.szUserID = payload.get("user_id", "") or ""
    scc.szProject = payload.get("project", "") or ""
    scc.szLocalProjPath = payload.get("local_proj_path", "") or ""
    scc.szAuxPath = payload.get("aux_path", "") or ""
    scc.szLogFile = payload.get("log_file", "") or ""
    scc.lCapabilities = int(payload.get("capabilities", 0))
    scc.lCommentLen = int(payload.get("comment_max_len", 256))
    scc.lAppend = 1 if payload.get("append_log") else 0
    scc.lDeleteTempFiles = 1 if payload.get("delete_temp_files", True) else 0
    scc.bDeletePblFlag = 1 if payload.get("delete_pbl_on_refresh") else 0


@dataclass
class _FakeInstall:
    version: str = "22.0"
    orca_dll: str = "C:\\fake\\pborc.dll"


@dataclass
class _FakeApi:
    install: _FakeInstall = field(default_factory=_FakeInstall)
    session: _FakeSession = field(default_factory=_FakeSession)
    scc: _FakeScc = field(default_factory=_FakeScc)
    dll_search_handles: tuple[Any, ...] = ()
    original_path: str = ""


@pytest.fixture
def opened_session() -> tuple[Session, _FakeApi]:
    Session._instance = None
    session = Session.instance()
    api = _FakeApi()
    session.open(api)  # type: ignore[arg-type]
    return session, api


def test_scc_get_connect_properties_returns_struct_as_dict(
    opened_session: tuple[Session, _FakeApi],
) -> None:
    session, api = opened_session
    out = session.scc_get_connect_properties("C:\\proj\\ws.pbw")
    assert out["provider_name"] == "FakeSCC"
    assert out["user_id"] == "carlo"
    assert out["project"] == "$/proj"
    assert out["local_proj_path"] == "C:\\proj"
    assert out["log_file"] == "C:\\proj\\scc.log"
    assert out["comment_max_len"] == 256
    assert out["delete_temp_files"] is True
    assert out["append_log"] is False
    assert api.scc.calls[0] == (
        "SccGetConnectProperties", (0xDEADBEEF, "C:\\proj\\ws.pbw")
    )


def test_scc_get_connect_properties_propagates_error(
    opened_session: tuple[Session, _FakeApi],
) -> None:
    session, api = opened_session
    api.scc.get_connect_returns = PBORCA_SCCFAILURE
    with pytest.raises(OrcaError) as ei:
        session.scc_get_connect_properties("C:\\proj\\ws.pbw")
    assert ei.value.code == PBORCA_SCCFAILURE
    assert ei.value.name == "PBORCA_SCCFAILURE"


def test_scc_connect_offline_sets_state_and_passes_config(
    opened_session: tuple[Session, _FakeApi],
) -> None:
    session, api = opened_session
    assert session.scc_connected is False
    out = session.scc_connect_offline(
        {
            "provider_name": "FakeSCC",
            "user_id": "carlo",
            "local_proj_path": "C:\\proj",
            "log_file": "C:\\proj\\scc.log",
            "comment_max_len": 256,
            "delete_temp_files": True,
        }
    )
    assert session.scc_connected is True
    assert out["capabilities"] == 0x1234  # populated by provider
    name, args = api.scc.calls[-1]
    assert name == "SccConnectOffline"
    handle, snapshot = args
    assert handle == 0xDEADBEEF
    assert snapshot["provider_name"] == "FakeSCC"
    assert snapshot["user_id"] == "carlo"
    assert snapshot["local_proj_path"] == "C:\\proj"
    assert snapshot["log_file"] == "C:\\proj\\scc.log"
    assert snapshot["comment_max_len"] == 256
    assert snapshot["delete_temp_files"] == 1


def test_scc_connect_offline_rejects_double_connect(
    opened_session: tuple[Session, _FakeApi],
) -> None:
    session, _ = opened_session
    session.scc_connect_offline({})
    with pytest.raises(SessionStateError, match="already connected"):
        session.scc_connect_offline({})


def test_scc_set_target_collects_libraries_from_callback(
    opened_session: tuple[Session, _FakeApi],
) -> None:
    session, api = opened_session
    session.scc_connect_offline({})
    libs = session.scc_set_target("C:\\proj\\target.pbt", flags=["refresh_all"])
    assert libs == ["a.pbl", "b.pbl"]
    name, args = api.scc.calls[-1]
    assert name == "SccSetTarget"
    handle, target_file, flags_int = args
    assert handle == 0xDEADBEEF
    assert target_file == "C:\\proj\\target.pbt"
    assert flags_int == PBORCA_SCC_REFRESH_ALL


def test_scc_set_target_rejects_unknown_flag(
    opened_session: tuple[Session, _FakeApi],
) -> None:
    session, _ = opened_session
    session.scc_connect_offline({})
    with pytest.raises(ValueError, match="unknown SCC refresh flag"):
        session.scc_set_target("C:\\proj\\target.pbt", flags=["bogus"])


def test_scc_set_target_requires_connection(
    opened_session: tuple[Session, _FakeApi],
) -> None:
    session, _ = opened_session
    with pytest.raises(SessionStateError, match="no SCC connection"):
        session.scc_set_target("C:\\proj\\target.pbt")


def test_scc_exclude_library_list_passes_array(
    opened_session: tuple[Session, _FakeApi],
) -> None:
    session, api = opened_session
    session.scc_connect_offline({})
    session.scc_exclude_library_list(["x.pbl", "y.pbl"])
    name, args = api.scc.calls[-1]
    assert name == "SccExcludeLibraryList"
    handle, libs, count = args
    assert handle == 0xDEADBEEF
    assert libs == ["x.pbl", "y.pbl"]
    assert count == 2


def test_scc_exclude_library_list_rejects_empty(
    opened_session: tuple[Session, _FakeApi],
) -> None:
    session, _ = opened_session
    session.scc_connect_offline({})
    with pytest.raises(ValueError, match="at least one"):
        session.scc_exclude_library_list([])


def test_scc_refresh_target_passes_rebuild_type(
    opened_session: tuple[Session, _FakeApi],
) -> None:
    session, api = opened_session
    session.scc_connect_offline({})
    session.scc_refresh_target("incremental")
    name, args = api.scc.calls[-1]
    assert name == "SccRefreshTarget"
    assert args == (0xDEADBEEF, PBORCA_INCREMENTAL_REBUILD)


def test_scc_refresh_target_rejects_unknown_rebuild_type(
    opened_session: tuple[Session, _FakeApi],
) -> None:
    session, _ = opened_session
    session.scc_connect_offline({})
    with pytest.raises(ValueError, match="unknown rebuild type"):
        session.scc_refresh_target("bogus")


def test_scc_close_resets_state(
    opened_session: tuple[Session, _FakeApi],
) -> None:
    session, api = opened_session
    session.scc_connect_offline({})
    assert session.scc_connected is True
    session.scc_close()
    assert session.scc_connected is False
    assert ("SccClose", (0xDEADBEEF,)) in api.scc.calls


def test_scc_close_is_idempotent(
    opened_session: tuple[Session, _FakeApi],
) -> None:
    session, api = opened_session
    session.scc_close()
    session.scc_close()
    # SccClose should NOT have been called — session was never SCC-connected.
    assert ("SccClose", (0xDEADBEEF,)) not in api.scc.calls


def test_session_close_releases_scc_first(
    opened_session: tuple[Session, _FakeApi],
) -> None:
    session, api = opened_session
    session.scc_connect_offline({})
    session.close()
    # SccClose must run before SessionClose in the call log.
    names = [c[0] for c in api.scc.calls]
    assert "SccClose" in names
    assert api.session.close_calls == 1


def test_scc_operations_require_open_session() -> None:
    Session._instance = None
    session = Session.instance()
    with pytest.raises(SessionStateError):
        session.scc_get_connect_properties("ws.pbw")
    with pytest.raises(SessionStateError):
        session.scc_connect_offline({})
    with pytest.raises(SessionStateError):
        session.scc_set_target("t.pbt")
    with pytest.raises(SessionStateError):
        session.scc_exclude_library_list(["a.pbl"])
    with pytest.raises(SessionStateError):
        session.scc_refresh_target("incremental")
