"""Real-machine ORCA DLL load test. Skipped in CI; load only, no session."""

from __future__ import annotations

import struct

import pytest

from pb_orca_mcp.discovery import discover_pb_installations
from pb_orca_mcp.orca.dll import KNOWN_VERSIONS, OrcaArchMismatchError, load_orca


def _python_is_x86() -> bool:
    return struct.calcsize("P") == 4


@pytest.mark.requires_pb
@pytest.mark.parametrize("version", ["22.0", "25.0"])
def test_load_orca_succeeds_for_tested_versions(version: str) -> None:
    ides, _ = discover_pb_installations()
    candidates = [i for i in ides if i.version == version]
    if not candidates:
        pytest.skip(f"PB {version} not installed on this machine")
    install = candidates[0]
    if install.arch == "x86" and not _python_is_x86():
        with pytest.raises(OrcaArchMismatchError):
            load_orca(install)
        return
    api = load_orca(install)
    assert api.install is install
    assert api.dll is not None
    assert api.tested is (version in KNOWN_VERSIONS)


@pytest.mark.requires_pb
def test_load_orca_arch_mismatch_is_explicit() -> None:
    """A fake x64 install on an x86 Python (or vice versa) must raise the
    typed mismatch error rather than crashing inside ctypes."""
    ides, _ = discover_pb_installations()
    if not ides:
        pytest.skip("no PB IDE installs found")
    real = ides[0]
    wrong = "x64" if _python_is_x86() else "x86"
    if real.arch == wrong:
        pytest.skip(f"no install with arch != Python ({real.arch})")
    # Build a synthetic PbInstall with mismatched arch pointing at the
    # real DLL — load_orca must reject it on the arch check before touching
    # ctypes.
    from pb_orca_mcp.discovery import PbInstall

    fake = PbInstall(
        version=real.version,
        file_version=real.file_version,
        product_version=real.product_version,
        arch=wrong,  # type: ignore[arg-type]
        install_path=real.install_path,
        ide_path=real.ide_path,
        orca_dll=real.orca_dll,
        tested=real.tested,
        source=real.source,
    )
    with pytest.raises(OrcaArchMismatchError):
        load_orca(fake)
