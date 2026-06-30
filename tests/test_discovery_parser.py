"""Tests for `.pbt` and `.pbw` parsing in `pb_orca_mcp.tools.discovery`.

Format documented in AGENTS.md §"Design notes" (.pbt / .pbw format); fixtures
here are synthetic (no real customer paths committed, per public-repo hygiene).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pb_orca_mcp.tools.discovery import (
    PbProjectParseError,
    PbtInfo,
    PbwInfo,
    parse_pb_project_file,
    parse_pbt_text,
    parse_pbw_text,
    pb_target_info,
)


def test_parse_minimal_pbt() -> None:
    text = (
        "Save Format v3.0(19990112)\n"
        'appname "demo";\n'
        'applib "demo.pbl";\n'
        'LibList "demo.pbl;..\\\\dep\\\\foo.pbl;..\\\\dep\\\\bar.pbd";\n'
        'type "pb";\n'
    )
    info = parse_pbt_text(text, target_name="demo")
    assert info == PbtInfo(
        kind="pbt",
        target_name="demo",
        app_name="demo",
        app_lib="demo.pbl",
        lib_list=["demo.pbl", "..\\dep\\foo.pbl", "..\\dep\\bar.pbd"],
        type="pb",
    )


def test_parse_pbt_with_projects_block_is_ignored() -> None:
    text = (
        "Save Format v3.0(19990112)\n"
        "@begin Projects\n"
        ' 0 "1&p_demo_exe&demo.pbl";\n'
        "@end;\n"
        'appname "demo";\n'
        'applib "demo.pbl";\n'
        'LibList "demo.pbl";\n'
        'type "pb";\n'
    )
    info = parse_pbt_text(text, target_name="demo")
    assert info.app_name == "demo"
    assert info.lib_list == ["demo.pbl"]


def test_parse_pbt_case_insensitive_keywords() -> None:
    text = (
        "Save Format v3.0(19990112)\n"
        'APPNAME "x";\n'
        'AppLib "x.pbl";\n'
        'liblist "x.pbl;y.pbl";\n'
        'TYPE "pb";\n'
    )
    info = parse_pbt_text(text)
    assert info.app_name == "x"
    assert info.app_lib == "x.pbl"
    assert info.lib_list == ["x.pbl", "y.pbl"]
    assert info.type == "pb"


def test_parse_pbw_targets_block() -> None:
    text = (
        "Save Format v3.0(19990112)\n"
        "@begin Targets\n"
        ' 0 "src\\\\main.pbt";\n'
        ' 1 "src\\\\tools.pbt";\n'
        "@end;\n"
        'DefaultTarget "src\\\\main.pbt";\n'
        'DefaultExportEncode "UTF-8";\n'
        'DefaultRemoteTarget "src\\\\main.pbt";\n'
    )
    info = parse_pbw_text(text, workspace_name="myws")
    assert info == PbwInfo(
        kind="pbw",
        workspace_name="myws",
        targets=["src\\main.pbt", "src\\tools.pbt"],
        default_target="src\\main.pbt",
    )


def test_parse_pbw_unordered_indices_kept_in_file_order() -> None:
    """Real .pbw files write target indices in non-numeric order. The
    parser preserves file order rather than sorting by the leading
    integer."""
    text = (
        "Save Format v3.0(19990112)\n"
        "@begin Targets\n"
        ' 0 "a.pbt";\n'
        ' 10 "k.pbt";\n'
        ' 1 "b.pbt";\n'
        "@end;\n"
        'DefaultTarget "a.pbt";\n'
    )
    info = parse_pbw_text(text)
    assert info.targets == ["a.pbt", "k.pbt", "b.pbt"]


def test_parse_pb_project_file_dispatch_pbt(tmp_path: Path) -> None:
    p = tmp_path / "foo.pbt"
    p.write_text(
        "Save Format v3.0(19990112)\n"
        'appname "foo";\n'
        'applib "foo.pbl";\n'
        'LibList "foo.pbl";\n'
        'type "pb";\n',
        encoding="utf-8",
    )
    info = parse_pb_project_file(p)
    assert isinstance(info, PbtInfo)
    assert info.target_name == "foo"


def test_parse_pb_project_file_dispatch_pbw(tmp_path: Path) -> None:
    p = tmp_path / "ws.pbw"
    p.write_text(
        "Save Format v3.0(19990112)\n"
        "@begin Targets\n"
        ' 0 "src\\\\main.pbt";\n'
        "@end;\n"
        'DefaultTarget "src\\\\main.pbt";\n',
        encoding="utf-8",
    )
    info = parse_pb_project_file(p)
    assert isinstance(info, PbwInfo)
    assert info.workspace_name == "ws"


def test_parse_rejects_missing_magic_header() -> None:
    with pytest.raises(PbProjectParseError, match="magic header"):
        parse_pbt_text('appname "x";\n')


def test_parse_rejects_unknown_extension(tmp_path: Path) -> None:
    p = tmp_path / "weird.txt"
    p.write_text("Save Format v3.0(19990112)\n", encoding="utf-8")
    with pytest.raises(PbProjectParseError, match="unsupported"):
        parse_pb_project_file(p)


def test_pb_target_info_returns_dict_without_pb_version(tmp_path: Path) -> None:
    """The MCP-facing tool returns a serializable dict and never includes
    `pb_version` — see AGENTS.md §"Design notes" (explicit PB version selection)."""
    p = tmp_path / "demo.pbt"
    p.write_text(
        "Save Format v3.0(19990112)\n"
        'appname "demo";\n'
        'applib "demo.pbl";\n'
        'LibList "demo.pbl";\n'
        'type "pb";\n',
        encoding="utf-8",
    )
    out = pb_target_info(p)
    assert out["kind"] == "pbt"
    assert out["app_name"] == "demo"
    assert "pb_version" not in out
