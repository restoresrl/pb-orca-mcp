"""Real-ORCA tests for the file-based editing loop. Skipped in CI.

These pin the properties the whole design rests on, and every one of them was
first established empirically against PB 22.0:

- ORCA's write-to-file export is **byte-identical** to what the PB IDE writes
  into `ws_objects/`, so refreshing an unmodified object leaves `git status`
  clean instead of producing a phantom diff.
- The `$PBExportHeader$` / `$PBExportComments$` lines are **ignored** on import,
  so a file straight off disk round-trips with no surgery.
- A `.pbl` write and its text projection move together, in one call.

Requires an interpreter whose arch matches `pborc.dll` (x86 for PB 19/22/25).
"""

from __future__ import annotations

import shutil
import struct
from pathlib import Path

import pytest

from pb_orca_mcp import workspace as ws
from pb_orca_mcp.discovery import discover_pb_installations
from pb_orca_mcp.orca.dll import OrcaArchMismatchError, load_orca
from pb_orca_mcp.orca.session import Session
from pb_orca_mcp.tools import compile as compile_tools
from pb_orca_mcp.tools import library as library_tools
from pb_orca_mcp.tools import source as source_tools

_FIXTURES = Path(__file__).parent / "fixtures"
_TITLE_MARKER = b'string title = "Main Window"'


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    Session._instance = None


def _open_session_or_skip(lib: Path, app: str = "genapp") -> Session | None:
    """Open a real ORCA session against `lib`, or skip when PB 22 is unusable."""
    ides, _ = discover_pb_installations()
    target = next((i for i in ides if i.version == "22.0"), None)
    if target is None:
        pytest.skip("PB 22.0 not installed on this machine")
    if target.arch == "x86" and struct.calcsize("P") != 4:
        with pytest.raises(OrcaArchMismatchError):
            load_orca(target)
        return None
    session = Session.instance()
    session.open(load_orca(target))
    session.set_library_list([str(lib)])
    session.set_current_application(str(lib), app)
    return session


def _ws_app(tmp_path: Path) -> Path:
    """A private copy of the workspace fixture — tests mutate the `.pbl`."""
    destination = tmp_path / "ws_app"
    shutil.copytree(_FIXTURES / "ws_app", destination)
    return destination


def _tiny_app(tmp_path: Path) -> Path:
    destination = tmp_path / "tiny_app"
    shutil.copytree(_FIXTURES / "tiny_app", destination)
    return destination


# --------------------------- the byte-identity property ---------------------------


@pytest.mark.requires_pb
def test_export_to_file_is_byte_identical_to_the_ide_output(tmp_path: Path) -> None:
    """The property the ws_objects sync depends on.

    If ORCA's export did not reproduce the IDE's bytes exactly, every sync
    would rewrite files that did not change and bury real diffs in noise.
    """
    project = _ws_app(tmp_path)
    lib = project / "genapp.pbl"
    reference = {
        path.name: path.read_bytes()
        for path in (project / "ws_objects" / "genapp.pbl.src").iterdir()
    }
    session = _open_session_or_skip(lib)
    if session is None:
        return
    out = tmp_path / "out"
    out.mkdir()
    try:
        for entry_name, entry_type, filename in (
            ("w_genapp_main", "window", "w_genapp_main.srw"),
            ("m_genapp_main", "menu", "m_genapp_main.srm"),
            ("genapp", "application", "genapp.sra"),
            ("w_genapp_about", "window", "w_genapp_about.srw"),
            ("d_genapp_dw_test", "datawindow", "d_genapp_dw_test.srd"),
        ):
            path, size = session.library_entry_export_to_file(
                str(lib), entry_name, entry_type, str(out), encoding="utf8"
            )
            assert Path(path).name == filename
            assert size > 0
            assert Path(path).read_bytes() == reference[filename]
    finally:
        session.close()


@pytest.mark.requires_pb
def test_export_writes_the_encoding_the_workspace_declares(tmp_path: Path) -> None:
    """UTF-8 gets a `EF BB BF` BOM, UTF-16 gets `FF FE`, ANSI gets none."""
    project = _ws_app(tmp_path)
    session = _open_session_or_skip(project / "genapp.pbl")
    if session is None:
        return
    try:
        for encoding, bom in (("utf8", b"\xef\xbb\xbf"), ("unicode", b"\xff\xfe"), ("ansi", b"$")):
            out = tmp_path / f"out_{encoding}"
            out.mkdir()
            path, _size = session.library_entry_export_to_file(
                str(project / "genapp.pbl"),
                "w_genapp_main",
                "window",
                str(out),
                encoding=encoding,
            )
            assert Path(path).read_bytes().startswith(bom)
    finally:
        session.close()


@pytest.mark.requires_pb
def test_configure_for_files_is_reversible(tmp_path: Path) -> None:
    """Entering and leaving file mode must not disturb in-memory exports."""
    project = _ws_app(tmp_path)
    lib = str(project / "genapp.pbl")
    session = _open_session_or_skip(project / "genapp.pbl")
    if session is None:
        return
    out = tmp_path / "out"
    out.mkdir()
    try:
        before = session.library_entry_export(lib, "w_genapp_main", "window")
        session.library_entry_export_to_file(lib, "w_genapp_main", "window", str(out))
        after = session.library_entry_export(lib, "w_genapp_main", "window")
        assert after == before
        assert "\r\n" in after
    finally:
        session.close()


@pytest.mark.requires_pb
def test_in_memory_export_refuses_a_corrupting_configuration(tmp_path: Path) -> None:
    """A non-Unicode export encoding would mangle the buffer silently, so the
    session refuses rather than returning plausible-looking garbage."""
    from pb_orca_mcp.orca.session import SessionStateError

    project = _ws_app(tmp_path)
    session = _open_session_or_skip(project / "genapp.pbl")
    if session is None:
        return
    try:
        session.configure(export_encoding="utf8")
        with pytest.raises(SessionStateError, match="corrupt"):
            session.library_entry_export(
                str(project / "genapp.pbl"), "w_genapp_main", "window"
            )
    finally:
        session.close()


# --------------------------- import accepts what export produced ---------------------------


@pytest.mark.requires_pb
def test_import_accepts_body_header_and_whole_file(tmp_path: Path) -> None:
    """ORCA ignores the export header lines, so all three shapes are valid input.

    This is the fact that lets a caller hand back a `.sr*` file unmodified.
    """
    project = _ws_app(tmp_path)
    lib = str(project / "genapp.pbl")
    session = _open_session_or_skip(project / "genapp.pbl")
    if session is None:
        return
    try:
        body = session.library_entry_export(lib, "w_genapp_about", "window")
        assert not body.startswith("$PBExportHeader$")
        whole_file, _enc = ws.read_source_file(
            project / "ws_objects" / "genapp.pbl.src" / "w_genapp_about.srw"
        )
        assert whole_file.startswith("$PBExportHeader$")

        for label, syntax in (
            ("body only", body),
            ("header + body", "$PBExportHeader$w_genapp_about.srw\r\n" + body),
            ("whole file", whole_file),
        ):
            success, errors = session.compile_entry_import(
                lib, "w_genapp_about", "window", syntax, "roundtrip"
            )
            assert success, f"{label} failed to import: {errors}"
    finally:
        session.close()


@pytest.mark.requires_pb
def test_import_preserves_crlf_in_the_pbl(tmp_path: Path) -> None:
    """LF-normalized input rewrites every line in the .pbl and later shows up
    as a whole-file phantom diff, so the reader must not translate newlines."""
    project = _ws_app(tmp_path)
    lib = str(project / "genapp.pbl")
    session = _open_session_or_skip(project / "genapp.pbl")
    if session is None:
        return
    try:
        original = session.library_entry_export(lib, "w_genapp_about", "window")
        session.compile_entry_import(
            lib, "w_genapp_about", "window", original.replace("\r\n", "\n"), "lf"
        )
        after_lf = session.library_entry_export(lib, "w_genapp_about", "window")
        assert after_lf != original, "the LF import was expected to change the stored source"

        session.compile_entry_import(lib, "w_genapp_about", "window", original, "crlf")
        assert session.library_entry_export(lib, "w_genapp_about", "window") == original
    finally:
        session.close()


# --------------------------- the tool-level round trip ---------------------------


@pytest.mark.requires_pb
def test_ws_objects_project_round_trip(tmp_path: Path) -> None:
    """Export → edit → import on a project with a text projection.

    The export must land in `ws_objects/`, leave the file byte-unchanged when
    the object did not change, and the import must push the edit into the
    `.pbl` *and* rewrite the text file.
    """
    project = _ws_app(tmp_path)
    lib = str(project / "genapp.pbl")
    projection = project / "ws_objects" / "genapp.pbl.src" / "w_genapp_main.srw"
    before = projection.read_bytes()

    session = _open_session_or_skip(project / "genapp.pbl")
    if session is None:
        return
    try:
        exported = source_tools.pb_object_export_file(lib, "w_genapp_main", "window")
        assert exported["ok"]
        assert exported["mode"] == "ws_objects"
        assert exported["is_source_of_truth"]
        assert Path(exported["file_path"]) == projection
        assert projection.read_bytes() == before, "a plain export must not dirty the file"

        projection.write_bytes(before.replace(_TITLE_MARKER, b'string title = "Edited"'))
        result = source_tools.pb_object_import_file(str(projection), lib)
        assert result["success"], result["errors"]
        assert result["sync"] == "ok"
        assert result["synced_files"] == [str(projection)]

        rewritten = projection.read_bytes()
        assert b'string title = "Edited"' in rewritten
        assert rewritten.startswith(b"\xef\xbb\xbf")
        assert b"\r\n" in rewritten
        assert session.library_entry_export(lib, "w_genapp_main", "window").count("Edited") == 1
    finally:
        session.close()


@pytest.mark.requires_pb
def test_pbl_only_project_round_trip(tmp_path: Path) -> None:
    """The same three calls on a project with no projection: the working file
    goes to `.pb-orca/`, and nothing is synced because there is nothing to sync."""
    project = _tiny_app(tmp_path)
    lib = str(project / "genapp.pbl")
    session = _open_session_or_skip(project / "genapp.pbl")
    if session is None:
        return
    try:
        info = source_tools.pb_workspace_info(lib)
        assert info["mode"] == "pbl_only"

        exported = source_tools.pb_object_export_file(lib, "w_genapp_main", "window")
        assert exported["ok"], exported
        work_file = Path(exported["file_path"])
        assert work_file.parent.name == ws.WORK_DIRNAME
        assert not exported["is_source_of_truth"]

        work_file.write_bytes(
            work_file.read_bytes().replace(_TITLE_MARKER, b'string title = "Standalone"')
        )
        result = source_tools.pb_object_import_file(str(work_file), lib)
        assert result["success"], result["errors"]
        assert result["sync"] == "not_applicable"
        assert result["synced_files"] == []
        assert "Standalone" in session.library_entry_export(lib, "w_genapp_main", "window")
    finally:
        session.close()


@pytest.mark.requires_pb
def test_datawindow_round_trips_through_a_file(tmp_path: Path) -> None:
    """`.srd` gets its own round trip rather than riding on the window cases.

    The fixture's DataWindow is plain text, with no `Start of PowerBuilder
    Binary Data Section` block — only objects hosting an OLE/ActiveX control
    produce one, and a fixture with such a control would only export
    identically on a machine where the control is registered. So this pins the
    `.srd` extension mapping and the round trip; `bExportIncludeBinary` itself
    is verified against a real codebase, see `docs/how-it-works.md` §9.
    """
    project = _ws_app(tmp_path)
    lib = str(project / "genapp.pbl")
    projection = project / "ws_objects" / "genapp.pbl.src" / "d_genapp_dw_test.srd"
    session = _open_session_or_skip(project / "genapp.pbl")
    if session is None:
        return
    try:
        exported = source_tools.pb_object_export_file(lib, "d_genapp_dw_test", "datawindow")
        assert Path(exported["file_path"]) == projection
        first = projection.read_bytes()

        result = source_tools.pb_object_import_file(str(projection), lib)
        assert result["entry_type"] == "datawindow"
        assert result["success"], result["errors"]
        assert result["synced_files"] == [str(projection)]
        assert projection.read_bytes() == first, "the round trip must be byte-stable"
    finally:
        session.close()


@pytest.mark.requires_pb
def test_entry_type_and_comment_are_inferred_from_the_file(tmp_path: Path) -> None:
    """A file produced by the export tool imports back with no extra arguments."""
    project = _ws_app(tmp_path)
    lib = str(project / "genapp.pbl")
    session = _open_session_or_skip(project / "genapp.pbl")
    if session is None:
        return
    try:
        exported = source_tools.pb_object_export_file(lib, "m_genapp_main", "menu")
        result = source_tools.pb_object_import_file(exported["file_path"], lib)
        assert result["entry_type"] == "menu"
        assert result["entry_name"] == "m_genapp_main"
        assert result["success"], result["errors"]
        info = session.library_entry_information(lib, "m_genapp_main", "menu")
        assert info["comment"] == "Generated SDI Main Menu"
    finally:
        session.close()


@pytest.mark.requires_pb
def test_compile_errors_do_not_sync_the_projection(tmp_path: Path) -> None:
    """A broken edit must leave the text file exactly as the caller wrote it,
    so they can fix it and retry."""
    project = _ws_app(tmp_path)
    lib = str(project / "genapp.pbl")
    projection = project / "ws_objects" / "genapp.pbl.src" / "w_genapp_main.srw"
    session = _open_session_or_skip(project / "genapp.pbl")
    if session is None:
        return
    try:
        broken = projection.read_bytes().replace(
            _TITLE_MARKER, b"string title = no_such_variable"
        )
        projection.write_bytes(broken)
        result = source_tools.pb_object_import_file(str(projection), lib)
        assert not result["success"]
        assert result["errors"], "expected ORCA diagnostics"
        assert result["synced_files"] == []
        assert projection.read_bytes() == broken
    finally:
        session.close()


# --------------------------- mutations keep the two forms together ---------------------------


@pytest.mark.requires_pb
def test_entry_delete_removes_the_projection_file(tmp_path: Path) -> None:
    """A surviving `.sr*` would resurrect the object on the next Refresh."""
    project = _ws_app(tmp_path)
    lib = str(project / "genapp.pbl")
    projection = project / "ws_objects" / "genapp.pbl.src" / "w_genapp_about.srw"
    session = _open_session_or_skip(project / "genapp.pbl")
    if session is None:
        return
    try:
        result = library_tools.pb_library_entry_delete(lib, "w_genapp_about", "window")
        assert result["ok"]
        assert result["removed_files"] == [str(projection)]
        assert not projection.exists()
    finally:
        session.close()


@pytest.mark.requires_pb
def test_sync_never_leaves_the_projection_alone(tmp_path: Path) -> None:
    project = _ws_app(tmp_path)
    lib = str(project / "genapp.pbl")
    projection = project / "ws_objects" / "genapp.pbl.src" / "w_genapp_about.srw"
    session = _open_session_or_skip(project / "genapp.pbl")
    if session is None:
        return
    try:
        result = library_tools.pb_library_entry_delete(
            lib, "w_genapp_about", "window", sync_sources="never"
        )
        assert result["sync"] == "never"
        assert projection.exists()
    finally:
        session.close()


@pytest.mark.requires_pb
def test_string_import_also_syncs_the_projection(tmp_path: Path) -> None:
    """The in-memory tool is not a back door around the sync rule."""
    project = _ws_app(tmp_path)
    lib = str(project / "genapp.pbl")
    projection = project / "ws_objects" / "genapp.pbl.src" / "w_genapp_main.srw"
    session = _open_session_or_skip(project / "genapp.pbl")
    if session is None:
        return
    try:
        body = session.library_entry_export(lib, "w_genapp_main", "window")
        result = compile_tools.pb_compile_entry_import(
            lib,
            "w_genapp_main",
            "window",
            body.replace('title = "Main Window"', 'title = "Via String"'),
            "string import",
        )
        assert result["success"], result["errors"]
        assert result["synced_files"] == [str(projection)]
        assert b"Via String" in projection.read_bytes()
    finally:
        session.close()


@pytest.mark.requires_pb
def test_bootstrap_a_projection_from_a_binary_only_library(tmp_path: Path) -> None:
    """`pb_library_export_sources` turns opaque binary commits into reviewable text."""
    project = _tiny_app(tmp_path)
    lib = str(project / "genapp.pbl")
    session = _open_session_or_skip(project / "genapp.pbl")
    if session is None:
        return
    try:
        result = source_tools.pb_library_export_sources(lib)
        assert result["ok"], result
        assert result["count"] >= 1
        assert not result["failed"]
        produced = {Path(item["file_path"]).name for item in result["written"]}
        assert "genapp.sra" in produced
        assert Path(result["dest_dir"]).is_dir()
        # The project is now a ws_objects project as far as detection goes.
        assert source_tools.pb_workspace_info(lib)["mode"] == "ws_objects"
    finally:
        session.close()
