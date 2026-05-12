"""Real-machine discovery test. Skipped in CI; runs on dev with PB installed."""

from __future__ import annotations

import pytest

from pb_orca_mcp.discovery import discover_pb_installations


@pytest.mark.requires_pb
def test_discover_finds_known_pb_majors_on_dev_machine() -> None:
    """On Carlo's machine: PB 19.0, 22.0, 25.0 are all installed (x86)."""
    ides, _runtime = discover_pb_installations()
    majors = {i.version for i in ides}
    # Don't pin to exactly {19.0, 22.0, 25.0} — accept any superset, so the
    # test still works after Carlo installs additional majors.
    assert {"19.0", "22.0", "25.0"}.issubset(majors), f"got {majors}"
    for install in ides:
        if install.version in {"19.0", "22.0", "25.0"}:
            assert install.tested is True
            assert install.arch == "x86"
            assert install.orca_dll.lower().endswith("pborc.dll")
            assert install.file_version is not None
            assert install.file_version.startswith(install.version.split(".")[0])
