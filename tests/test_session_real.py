"""Real-machine ORCA session open/close test. Skipped in CI.

Requires Python whose arch matches the installed `pborc.dll` (PB IDE is
x86 across PB 19/22/25, so this typically needs an x86 Python interpreter).
"""

from __future__ import annotations

import struct

import pytest

from pb_orca_mcp.discovery import discover_pb_installations
from pb_orca_mcp.orca.dll import OrcaArchMismatchError, load_orca
from pb_orca_mcp.orca.session import Session


def _python_is_x86() -> bool:
    return struct.calcsize("P") == 4


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    Session._instance = None


@pytest.mark.requires_pb
def test_open_and_close_real_session() -> None:
    ides, _ = discover_pb_installations()
    target = next((i for i in ides if i.version == "22.0"), None)
    if target is None:
        pytest.skip("PB 22.0 not installed on this machine")
    if target.arch == "x86" and not _python_is_x86():
        with pytest.raises(OrcaArchMismatchError):
            load_orca(target)
        return
    api = load_orca(target)
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
