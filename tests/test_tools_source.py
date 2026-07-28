"""Tests for the source-file tools that need no PowerBuilder.

The ORCA-dependent behaviour lives in `test_source_real.py`. What is covered
here is the part that decides *where* files go and *whether* a projection is
touched — the logic that makes a change visible to git — plus the argument
validation and error envelopes. A fake session stands in for ORCA so the sync
decisions can be asserted in CI, where no PB install exists.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pb_orca_mcp import workspace as ws
from pb_orca_mcp.orca.session import Session
from pb_orca_mcp.tools import library as library_tools
from pb_orca_mcp.tools import source as source_tools

_MAGIC = "Save Format v3.0(19990112)\n"


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    Session._instance = None


class _FakeSession:
    """Records what would have been exported instead of calling ORCA."""

    is_open = True

    def __init__(self) -> None:
        self.exports: list[tuple[str, str, str, str]] = []

    def library_entry_export_to_file(
        self,
        lib_path: str,
        entry_name: str,
        entry_type: str,
        directory: str,
        *,
        encoding: str = "utf8",
        include_binary: bool = True,
    ) -> tuple[str, int]:
        self.exports.append((lib_path, entry_name, entry_type, directory))
        extension = {"window": "srw", "userobject": "sru", "menu": "srm"}[entry_type]
        target = Path(directory) / f"{entry_name}.{extension}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\xef\xbb\xbf$PBExportHeader$" + target.name.encode() + b"\r\n")
        return str(target), 42


def _project(tmp_path: Path, *, with_projection: bool, with_git: bool = False) -> Path:
    (tmp_path / "proj.pbw").write_text(
        _MAGIC + 'DefaultTarget "app.pbt";\nDefaultExportEncode "UTF-8";\n', encoding="utf-8"
    )
    (tmp_path / "app.pbl").write_bytes(b"")
    if with_projection:
        projection = tmp_path / "ws_objects" / "app.pbl.src"
        projection.mkdir(parents=True)
        (projection / "w_main.srw").write_bytes(b"\xef\xbb\xbf$PBExportHeader$w_main.srw\r\n")
    if with_git:
        (tmp_path / ".git").mkdir()
    return tmp_path / "app.pbl"


# --------------------------- pb_workspace_info ---------------------------


def test_workspace_info_needs_no_session(tmp_path: Path) -> None:
    """Detection is filesystem-only, so an agent can orient itself before
    opening a session — and on a machine with no PowerBuilder at all."""
    lib = _project(tmp_path, with_projection=True)
    info = source_tools.pb_workspace_info(str(lib))
    assert info["mode"] == "ws_objects"
    assert info["orca_encoding"] == "utf8"
    assert info["encoding_source"] == "pbw"
    assert info["sources"]["file_count"] == 1
    assert info["advice"]


def test_workspace_info_reports_pbl_only(tmp_path: Path) -> None:
    lib = _project(tmp_path, with_projection=False)
    info = source_tools.pb_workspace_info(str(lib))
    assert info["mode"] == "pbl_only"
    assert info["work_dir"] == str(tmp_path / ".pb-orca")


def test_workspace_info_reports_git(tmp_path: Path) -> None:
    lib = _project(tmp_path, with_projection=False, with_git=True)
    info = source_tools.pb_workspace_info(str(lib))
    assert info["git_root"] == str(tmp_path)
    assert "pb_library_export_sources" in info["advice"]
    assert info["outside_source_tree"] is False


def test_workspace_info_flags_a_library_outside_the_projection(tmp_path: Path) -> None:
    """The payload has to carry this as a field, not only as prose, so a
    downstream tool can branch on it."""
    _project(tmp_path, with_projection=True)
    vendored = tmp_path / "dep" / "vendor.pbl"
    vendored.parent.mkdir()
    vendored.write_bytes(b"")
    info = source_tools.pb_workspace_info(str(vendored))
    assert info["outside_source_tree"] is True
    assert info["mode"] == "pbl_only"


# --------------------------- destination selection ---------------------------


def test_export_targets_the_projection_when_there_is_one(tmp_path: Path) -> None:
    lib = _project(tmp_path, with_projection=True)
    fake = _FakeSession()
    Session._instance = fake  # type: ignore[assignment]
    out = source_tools.pb_object_export_file(str(lib), "w_main", "window")
    assert out["ok"]
    assert out["is_source_of_truth"]
    assert Path(out["file_path"]).parent == tmp_path / "ws_objects" / "app.pbl.src"
    assert fake.exports[0][3] == str(tmp_path / "ws_objects" / "app.pbl.src")


def test_export_targets_the_work_dir_without_a_projection(tmp_path: Path) -> None:
    lib = _project(tmp_path, with_projection=False)
    Session._instance = _FakeSession()  # type: ignore[assignment]
    out = source_tools.pb_object_export_file(str(lib), "w_main", "window")
    assert not out["is_source_of_truth"]
    assert Path(out["file_path"]).parent == tmp_path / ".pb-orca"


def test_explicit_dest_dir_wins_and_is_never_the_source_of_truth(tmp_path: Path) -> None:
    lib = _project(tmp_path, with_projection=True)
    Session._instance = _FakeSession()  # type: ignore[assignment]
    elsewhere = tmp_path / "scratch"
    out = source_tools.pb_object_export_file(str(lib), "w_main", "window", str(elsewhere))
    assert Path(out["file_path"]).parent == elsewhere
    assert not out["is_source_of_truth"]


def test_work_dir_ignores_itself_in_a_git_repo(tmp_path: Path) -> None:
    """Scratch copies must not show up in `git status`, and pb-orca will not
    edit the user's own .gitignore to achieve that."""
    lib = _project(tmp_path, with_projection=False, with_git=True)
    Session._instance = _FakeSession()  # type: ignore[assignment]
    source_tools.pb_object_export_file(str(lib), "w_main", "window")
    marker = tmp_path / ".pb-orca" / ".gitignore"
    assert marker.exists()
    assert marker.read_text(encoding="utf-8").strip().endswith("*")


def test_work_dir_gets_no_gitignore_outside_a_repo(tmp_path: Path) -> None:
    lib = _project(tmp_path, with_projection=False)
    Session._instance = _FakeSession()  # type: ignore[assignment]
    source_tools.pb_object_export_file(str(lib), "w_main", "window")
    assert not (tmp_path / ".pb-orca" / ".gitignore").exists()


# --------------------------- sync decisions ---------------------------


def test_sync_entry_writes_the_projection(tmp_path: Path) -> None:
    lib = _project(tmp_path, with_projection=True)
    fake = _FakeSession()
    info = ws.describe(lib)
    out = source_tools.sync_entry(fake, info, "w_main", "window", "auto")  # type: ignore[arg-type]
    assert out["sync"] == "ok"
    assert out["synced_files"] == [str(tmp_path / "ws_objects" / "app.pbl.src" / "w_main.srw")]


def test_sync_entry_is_a_no_op_without_a_projection(tmp_path: Path) -> None:
    lib = _project(tmp_path, with_projection=False)
    fake = _FakeSession()
    out = source_tools.sync_entry(fake, ws.describe(lib), "w_main", "window", "auto")  # type: ignore[arg-type]
    assert out["sync"] == "not_applicable"
    assert fake.exports == []


def test_sync_never_skips_the_export(tmp_path: Path) -> None:
    lib = _project(tmp_path, with_projection=True)
    fake = _FakeSession()
    out = source_tools.sync_entry(fake, ws.describe(lib), "w_main", "window", "never")  # type: ignore[arg-type]
    assert out["sync"] == "never"
    assert fake.exports == []


def test_sync_removal_deletes_the_projection_file(tmp_path: Path) -> None:
    lib = _project(tmp_path, with_projection=True)
    target = tmp_path / "ws_objects" / "app.pbl.src" / "w_main.srw"
    out = source_tools.sync_removal(ws.describe(lib), "w_main", "window", "auto")
    assert out["removed_files"] == [str(target)]
    assert not target.exists()


def test_sync_removal_tolerates_a_missing_file(tmp_path: Path) -> None:
    lib = _project(tmp_path, with_projection=True)
    out = source_tools.sync_removal(ws.describe(lib), "never_existed", "window", "auto")
    assert out["sync"] == "ok"
    assert out["removed_files"] == []


def test_sync_removal_skips_types_with_no_source_form(tmp_path: Path) -> None:
    lib = _project(tmp_path, with_projection=True)
    out = source_tools.sync_removal(ws.describe(lib), "p_deploy", "project", "auto")
    assert out["sync"] == "not_applicable"


# --------------------------- validation and error envelopes ---------------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda: source_tools.pb_object_import_file("f.srw", "a.pbl", sync_sources="sometimes"),
        lambda: library_tools.pb_library_entry_delete("a.pbl", "x", "window", "sometimes"),
        lambda: library_tools.pb_library_entry_move("a.pbl", "b.pbl", "x", "window", "sometimes"),
    ],
)
def test_unknown_sync_mode_is_rejected(call: Any) -> None:
    assert call()["error"]["name"] == "PB_ORCA_MCP_INVALIDARGS"


def test_import_file_rejects_a_non_source_extension(tmp_path: Path) -> None:
    lib = _project(tmp_path, with_projection=False)
    bogus = tmp_path / "notes.txt"
    bogus.write_text("hello", encoding="utf-8")
    out = source_tools.pb_object_import_file(str(bogus), str(lib))
    assert out["error"]["name"] == "PB_ORCA_MCP_INVALIDARGS"
    assert "source extension" in out["error"]["message"]


def test_import_file_reports_a_missing_file(tmp_path: Path) -> None:
    lib = _project(tmp_path, with_projection=False)
    out = source_tools.pb_object_import_file(str(tmp_path / "gone.srw"), str(lib))
    assert out["error"]["name"] == "PB_ORCA_MCP_IOERROR"


def test_export_file_without_a_session_returns_stateerror(tmp_path: Path) -> None:
    lib = _project(tmp_path, with_projection=False)
    out = source_tools.pb_object_export_file(str(lib), "w_main", "window")
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"


def test_session_configure_without_a_session_returns_stateerror() -> None:
    out = source_tools.pb_session_configure()
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"


def test_library_export_sources_without_a_session_returns_stateerror(tmp_path: Path) -> None:
    lib = _project(tmp_path, with_projection=False)
    out = source_tools.pb_library_export_sources(str(lib))
    assert out["error"]["name"] == "PB_ORCA_MCP_STATEERROR"
