"""Real-machine ORCA session/library tests. Skipped in CI.

Requires Python whose arch matches the installed `pborc.dll` (PB IDE is
x86 across PB 19/22/25, so this typically needs an x86 Python interpreter).
On a mismatched-arch interpreter, each test confirms `OrcaArchMismatchError`
and returns — exercising the load_orca guardrail in lieu of the real path.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from pb_orca_mcp.discovery import PbInstall, discover_pb_installations
from pb_orca_mcp.orca.dll import OrcaApi, OrcaArchMismatchError, load_orca
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

        success, errors = session.compile_entry_import(
            pbl, "f_broken", "function", _BROKEN_FUNCTION_SRC, "imported by test"
        )
        assert success is False
        assert isinstance(errors, list)
        # If ORCA reported diagnostics, they must have line/column ints.
        for err in errors:
            assert isinstance(err["line"], int)
            assert isinstance(err["column"], int)
            assert isinstance(err["message_text"], str)
    finally:
        session.close()
