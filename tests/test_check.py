"""Tests for `pb-orca-mcp check`.

The target resolution and the report formatting are pure logic and are tested
here without PowerBuilder. The full run against a real workspace is a
`requires_pb` test at the bottom — that is the whole point of the command, so
it gets exercised for real rather than mocked.
"""

from __future__ import annotations

import shutil
import struct
from pathlib import Path

import pytest

from pb_orca_mcp import check as chk
from pb_orca_mcp.discovery import discover_pb_installations
from pb_orca_mcp.orca.session import Session

_MAGIC = "Save Format v3.0(19990112)\n"
_FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    Session._instance = None


def _pbt(
    directory: Path, name: str = "app", liblist: str = "app.pbl", applib: str = "app.pbl"
) -> Path:
    path = directory / f"{name}.pbt"
    path.write_text(
        _MAGIC + f'appname "{name}";\napplib "{applib}";\nliblist "{liblist}";\ntype "pb";\n',
        encoding="utf-8",
    )
    return path


def _pbw(directory: Path, targets: list[str], default: str = "") -> Path:
    block = "".join(f' {i} "{t}";\n' for i, t in enumerate(targets))
    body = _MAGIC + f"@begin Targets\n{block}@end;\n"
    if default:
        body += f'DefaultTarget "{default}";\n'
    path = directory / "ws.pbw"
    path.write_text(body, encoding="utf-8")
    return path


# --------------------------- target resolution ---------------------------


def test_resolve_a_pbl_directly(tmp_path: Path) -> None:
    lib = tmp_path / "app.pbl"
    lib.write_bytes(b"")
    target = chk.resolve_target(str(lib))
    assert target.libraries == [lib.resolve()]
    assert not target.app_name


def test_resolve_a_pbt_resolves_relative_libraries(tmp_path: Path) -> None:
    """LibList paths are relative to the .pbt, and dependencies routinely sit
    outside the target's own directory."""
    (tmp_path / "src").mkdir()
    (tmp_path / "dep").mkdir()
    pbt = _pbt(tmp_path / "src", liblist="app.pbl;..\\dep\\core.pbl")
    target = chk.resolve_target(str(pbt))
    assert target.app_name == "app"
    assert target.libraries == [
        (tmp_path / "src" / "app.pbl").resolve(),
        (tmp_path / "dep" / "core.pbl").resolve(),
    ]


def test_resolve_a_pbw_follows_the_default_target(tmp_path: Path) -> None:
    _pbt(tmp_path, name="first")
    _pbt(tmp_path, name="second")
    pbw = _pbw(tmp_path, ["first.pbt", "second.pbt"], default="second.pbt")
    target = chk.resolve_target(str(pbw))
    assert target.target_file is not None
    assert target.target_file.name == "second.pbt"
    assert "of 2" in target.note


def test_resolve_a_pbw_without_a_default_takes_the_first(tmp_path: Path) -> None:
    _pbt(tmp_path, name="only")
    pbw = _pbw(tmp_path, ["only.pbt"])
    assert chk.resolve_target(str(pbw)).target_file is not None


def test_missing_target_is_a_clear_failure(tmp_path: Path) -> None:
    with pytest.raises(chk.CheckError) as exc:
        chk.resolve_target(str(tmp_path / "nope.pbt"))
    assert "does not exist" in str(exc.value)
    assert exc.value.hint


def test_a_non_powerbuilder_file_is_rejected(tmp_path: Path) -> None:
    other = tmp_path / "notes.txt"
    other.write_text("hello", encoding="utf-8")
    with pytest.raises(chk.CheckError, match="not a PowerBuilder project file"):
        chk.resolve_target(str(other))


def test_a_workspace_pointing_at_a_missing_target_says_so(tmp_path: Path) -> None:
    pbw = _pbw(tmp_path, ["gone.pbt"], default="gone.pbt")
    with pytest.raises(chk.CheckError, match="does not exist"):
        chk.resolve_target(str(pbw))


def test_a_target_naming_no_library_at_all_is_rejected(tmp_path: Path) -> None:
    """An empty LibList alone is survivable — the applib still gives ORCA one
    library to open. Only a target that names neither is unusable."""
    assert chk.resolve_target(str(_pbt(tmp_path, liblist=""))).libraries

    pbt = _pbt(tmp_path, name="hollow", liblist="", applib="")
    with pytest.raises(chk.CheckError, match="empty library list"):
        chk.resolve_target(str(pbt))


# --------------------------- reporting ---------------------------


def test_report_renders_warnings_and_a_verdict() -> None:
    report = chk.CheckReport()
    report.section("Target")
    report.item("file", "x.pbt")
    report.warn("something to know")
    out = chk.format_report(report, "x.pbt")
    assert "Target" in out
    assert "! something to know" in out
    assert "Check OK" in out
    assert "Not exercised: the compile path" in out


def test_failure_includes_the_hint() -> None:
    out = chk.format_failure(chk.CheckError("it broke", "try this instead"))
    assert "Check failed: it broke" in out
    assert "try this instead" in out


@pytest.mark.parametrize(
    ("encoding", "raw", "expect_ok"),
    [
        ("utf8", b"\xef\xbb\xbf$PBExportHeader$w_main.srw\r\nforward\r\n", True),
        ("utf8", b"$PBExportHeader$w_main.srw\r\nforward\r\n", False),
        ("utf8", b"\xef\xbb\xbf$PBExportHeader$w_main.srw\nforward\n", False),
    ],
)
def test_export_description_flags_bad_bytes(encoding: str, raw: bytes, expect_ok: bool) -> None:
    """A missing BOM or LF endings must show up as a problem, not pass quietly."""
    details = chk._describe_export(raw, "w_main.srw", encoding)
    all_ok = all(d.startswith("[ok]") for d in details)
    assert all_ok is expect_ok


# --------------------------- the real run ---------------------------


@pytest.mark.requires_pb
def test_check_runs_end_to_end_on_a_real_workspace(tmp_path: Path) -> None:
    """The command's reason to exist: prove the whole stack on a real project."""
    ides, _ = discover_pb_installations()
    target_install = next((i for i in ides if i.version == "22.0"), None)
    if target_install is None:
        pytest.skip("PB 22.0 not installed on this machine")
    if target_install.arch == "x86" and struct.calcsize("P") != 4:
        pytest.skip("x86 PB needs an x86 interpreter")

    project = tmp_path / "ws_app"
    shutil.copytree(_FIXTURES / "ws_app", project)
    report = chk.run_check(str(project / "ws_app.pbw"), pb_version="22.0")
    rendered = chk.format_report(report, "ws_app.pbw")

    assert "source of truth : ws_objects" in rendered
    assert "orca            : loaded" in rendered
    assert "library list    : accepted" in rendered
    assert "[ok] byte-order mark matches utf8" in rendered
    assert "[ok] export header present" in rendered
    assert "[ok] CRLF line endings" in rendered


@pytest.mark.requires_pb
def test_check_leaves_the_project_untouched(tmp_path: Path) -> None:
    """A check that modifies what it inspects is not a check."""
    ides, _ = discover_pb_installations()
    target_install = next((i for i in ides if i.version == "22.0"), None)
    if target_install is None or (target_install.arch == "x86" and struct.calcsize("P") != 4):
        pytest.skip("PB 22.0 not usable from this interpreter")

    project = tmp_path / "ws_app"
    shutil.copytree(_FIXTURES / "ws_app", project)
    before = {p: p.read_bytes() for p in sorted(project.rglob("*")) if p.is_file()}

    chk.run_check(str(project / "ws_app.pbw"), pb_version="22.0")

    after = {p: p.read_bytes() for p in sorted(project.rglob("*")) if p.is_file()}
    assert after == before, "check must not modify the project it inspects"
