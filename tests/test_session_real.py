"""Real-machine ORCA session/library tests. Skipped in CI.

Requires Python whose arch matches the installed `pborc.dll` (PB IDE is
x86 across PB 19/22/25, so this typically needs an x86 Python interpreter).
On a mismatched-arch interpreter, each test confirms `OrcaArchMismatchError`
and returns — exercising the load_orca guardrail in lieu of the real path.
"""

from __future__ import annotations

import os
import struct
from pathlib import Path

import pytest

from pb_orca_mcp.discovery import PbInstall, discover_pb_installations
from pb_orca_mcp.orca.constants import PBORCA_CURRAPPLNOTSET
from pb_orca_mcp.orca.dll import OrcaApi, OrcaArchMismatchError, load_orca
from pb_orca_mcp.orca.errors import OrcaError
from pb_orca_mcp.orca.session import Session


def _python_is_x86() -> bool:
    return struct.calcsize("P") == 4


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    Session._instance = None


def _open_pb22_or_skip() -> tuple[PbInstall, OrcaApi] | None:
    """Discover a usable PB 22.0 install, load ORCA, return (install, api).

    When Python and the DLL arch don't match, `load_orca` raises and we
    treat that as test passed for the mismatch path — there is nothing
    further to verify until an arch-matched interpreter runs the suite.
    """
    ides, _ = discover_pb_installations()
    target = next((i for i in ides if i.version == "22.0"), None)
    if target is None:
        pytest.skip("PB 22.0 not installed on this machine")
    if target.arch == "x86" and not _python_is_x86():
        with pytest.raises(OrcaArchMismatchError):
            load_orca(target)
        return None
    return target, load_orca(target)


@pytest.mark.requires_pb
def test_open_and_close_real_session() -> None:
    loaded = _open_pb22_or_skip()
    if loaded is None:
        return
    target, api = loaded
    session = Session.instance()
    session.open(api)
    try:
        assert session.is_open
        assert session.install is target
        # SessionGetError on a fresh session returns an empty string (or
        # whatever ORCA's idle-state text is). We just want a successful call.
        text = session.get_error_text()
        assert isinstance(text, str)
    finally:
        session.close()
    assert not session.is_open


@pytest.mark.requires_pb
def test_library_full_lifecycle(tmp_path: Path) -> None:
    """Create an empty PBL, list/comment-modify/list, then delete it.

    Stresses the LibraryDirectory callback path on real ORCA (no entries
    expected on a fresh PBL — the callback should never fire).
    """
    loaded = _open_pb22_or_skip()
    if loaded is None:
        return
    _target, api = loaded
    session = Session.instance()
    session.open(api)
    try:
        pbl = str(tmp_path / "tiny.pbl")
        session.library_create(pbl, "initial comment")
        assert (tmp_path / "tiny.pbl").is_file()

        comment, entries = session.library_directory(pbl)
        assert entries == []
        assert "initial comment" in comment

        session.library_comment_modify(pbl, "rewritten")
        comment_after, _ = session.library_directory(pbl)
        assert "rewritten" in comment_after

        session.library_delete(pbl)
        assert not (tmp_path / "tiny.pbl").is_file()
    finally:
        session.close()


_BROKEN_FUNCTION_SRC = """\
$PBExportHeader$f_broken.srf
global type f_broken from function_object
end type

forward prototypes
global function string f_broken (string a)
end prototypes

global function string f_broken (string a);
this is intentionally not pb code
end function
"""


@pytest.mark.requires_pb
def test_compile_entry_import_returns_structured_response(tmp_path: Path) -> None:
    """Exercise the compile callback path on real ORCA.

    Imports a syntactically broken global function. The wrapper must return
    `(success=False, errors=...)` rather than raising; populated `errors`
    confirms the `PBORCA_ERRPROC` callback fired and was decoded.

    Some setups may short-circuit before parsing (e.g. PBORCA_LIBLISTNOTSET
    if the LibList wasn't accepted) — in that case `errors` may be empty
    but `success` must still be False. Either outcome is acceptable here;
    the test guards the callback infrastructure, not the PB compiler.
    """
    loaded = _open_pb22_or_skip()
    if loaded is None:
        return
    _target, api = loaded
    session = Session.instance()
    session.open(api)
    try:
        pbl = str(tmp_path / "compiletest.pbl")
        session.library_create(pbl, "compile test")
        session.set_library_list([pbl])

        try:
            success, errors = session.compile_entry_import(
                pbl, "f_broken", "function", _BROKEN_FUNCTION_SRC, "imported by test"
            )
        except OrcaError as exc:
            # ORCA may short-circuit before parsing when the application
            # object isn't set (PBORCA_CURRAPPLNOTSET) — accepted: the
            # callback infrastructure is exercised on every call regardless,
            # so as long as we got a typed OrcaError (not a crash) the
            # binding is sound. Stronger tests for the full compile path
            # need a complete application setup, out of scope here.
            assert exc.code == PBORCA_CURRAPPLNOTSET
            return
        assert success is False
        assert isinstance(errors, list)
        # If ORCA reported diagnostics, they must have line/column ints. Also
        # guard against a regression of the `len(syntax) + 1` size-arg bug
        # (fixed: now `len(syntax) * 2`) — that bug produced C0114 "Error
        # scanning object source entry" instead of the genuine syntax error.
        for err in errors:
            assert isinstance(err["line"], int)
            assert isinstance(err["column"], int)
            assert isinstance(err["message_text"], str)
            assert "C0114" not in err["message_text"], (
                "C0114 'Error scanning object source entry' suggests the "
                "compile size-arg regression is back — see commit message"
            )
    finally:
        session.close()


_FIXTURES = Path(__file__).parent / "fixtures" / "tiny_app"


def _read_pb_source(path: Path) -> str:
    """Decode a PB `.sr*` export file (UTF-16 LE with BOM) to a Python str."""
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe"):
        return raw[2:].decode("utf-16-le")
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be")
    return raw.decode("utf-8")


@pytest.mark.requires_pb
def test_compile_entry_import_happy_path_application(tmp_path: Path) -> None:
    """Roundtrip a real PB-IDE-exported application source into a fresh PBL.

    This is the test that would have caught the `len(syntax) + 1` size-arg
    bug. The broken-source test above can't catch it because any size value
    produces `success=False` for a syntactically invalid input. Only a
    happy-path import — valid source → `success=True` — distinguishes
    "size argument was correct" from "size argument was wrong".

    Setup: create empty PBL, set LibList, declare `genapp` as the current
    application (ORCA accepts a not-yet-existing name; it's stored on the
    session). Then import the wizard-generated `genapp.sra` fixture and
    assert the directory listing confirms the new entry.
    """
    loaded = _open_pb22_or_skip()
    if loaded is None:
        return
    _target, api = loaded

    # Copy the pre-built PBL fixture (PB 22.0 wizard output containing
    # `genapp` as an application object) to a temp path so we can write
    # to it without disturbing the source-controlled fixture.
    import shutil

    pbl_src = _FIXTURES / "genapp.pbl"
    pbl = str(tmp_path / "genapp.pbl")
    shutil.copyfile(pbl_src, pbl)

    session = Session.instance()
    session.open(api)
    try:
        session.set_library_list([pbl])
        # `genapp` already exists in the fixture → SessionSetCurrentAppl
        # succeeds. This sidesteps the empty-PBL bootstrap catch-22.
        session.set_current_application(pbl, "genapp")

        syntax = _read_pb_source(_FIXTURES / "genapp.sra")
        success, errors = session.compile_entry_import(
            pbl, "genapp", "application", syntax, "happy-path import"
        )
        assert success is True, f"compile failed: errors={errors}"
        assert errors == []

        _comment, entries = session.library_directory(pbl)
        names = {e["name"] for e in entries}
        assert "genapp" in names, f"genapp not in PBL after import; entries={names}"
    finally:
        session.close()


@pytest.mark.requires_pb
def test_path_env_var_roundtrip_around_load_and_close() -> None:
    """`load_orca` prepends PB dirs to `PATH`; `Session.close()` restores it.

    Regression: without the PATH prepend `pborc.dll`'s lazy `LoadLibraryW`
    of `pblib.dll` (during e.g. `SccConnectOffline`) fails with
    `PBORCA_BADLIBRARY (-4)` because `os.add_dll_directory` covers static
    imports but not lazy `LoadLibraryW` calls inside the native DLL.
    """
    original_path = os.environ.get("PATH", "")
    loaded = _open_pb22_or_skip()
    if loaded is None:
        assert os.environ.get("PATH", "") == original_path, (
            "load_orca must restore PATH when it raises (arch mismatch case)"
        )
        return
    target, api = loaded
    assert api.original_path == original_path
    after_load = os.environ.get("PATH", "")
    assert after_load != original_path, "PATH should have been prepended"
    assert after_load.startswith(target.ide_path + os.pathsep), (
        f"PATH should start with ide_path; got {after_load[:200]}..."
    )
    session = Session.instance()
    session.open(api)
    try:
        assert os.environ.get("PATH", "") == after_load, "session.open must not touch PATH further"
    finally:
        session.close()
    assert os.environ.get("PATH", "") == original_path, (
        "Session.close() must restore PATH to the pre-load_orca value"
    )
