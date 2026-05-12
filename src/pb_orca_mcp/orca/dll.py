"""Version-aware loader for pborc.dll.

`load_orca(install)` takes a `PbInstall` (from discovery) and returns an
`OrcaApi` wrapping the `pborc.dll` of that specific PowerBuilder install.
Multi-version is a day-1 requirement: a single machine can host PB 2019 R3,
PB 2022 R3, and PB 2025 side by side, each shipping its own
`<install>\\IDE\\pborc.dll` (no version suffix); the loader picks the right
one per caller-supplied install.

The ORCA ABI has been stable since PB 2019, so a single set of ctypes
prototypes covers every modern release. `KNOWN_VERSIONS` lists the majors
actively tested; discovery accepts any install that exposes `pborc.dll`,
marking unknown majors with `tested=False`.

Phase 2 deliverable: DLL load + arch validation + handle exposure. The
ORCA function prototypes themselves land in Phase 3 (`PBORCA_SessionOpen`
et al.).
"""

from __future__ import annotations

import ctypes
import struct
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pb_orca_mcp.discovery import PbInstall

KNOWN_VERSIONS = ("19.0", "22.0", "25.0")
"""PowerBuilder major versions actively tested by v1.

This is a guideline, not a gate: discovery returns every install that ships
`pborc.dll`, including versions outside this tuple (with `tested=False`).
Add a new release here once it has been smoke-tested against the loader.
"""


class OrcaLoadError(RuntimeError):
    """Raised when `pborc.dll` cannot be loaded for the given install."""


class OrcaArchMismatchError(OrcaLoadError):
    """Raised when the DLL arch doesn't match the running Python interpreter."""


@dataclass(frozen=True)
class OrcaApi:
    """A loaded `pborc.dll` ready for ORCA calls.

    Phase 2: exposes the raw `CDLL` handle and the source `PbInstall`. The
    Pythonic ORCA wrappers (`session_open`, `library_directory`, etc.) land
    in subsequent phases.
    """

    install: PbInstall
    dll: ctypes.CDLL
    tested: bool


def _python_arch() -> str:
    """`x86` if Python is 32-bit, `x64` if 64-bit."""
    return "x86" if struct.calcsize("P") == 4 else "x64"


def load_orca(install: PbInstall) -> OrcaApi:
    """Load `pborc.dll` from `install.orca_dll`.

    Raises:
    - `OrcaArchMismatchError` if the DLL arch doesn't match Python's.
    - `OrcaLoadError` if `ctypes.CDLL` fails to load the DLL.
    """
    py_arch = _python_arch()
    if install.arch != "unknown" and install.arch != py_arch:
        raise OrcaArchMismatchError(
            f"Cannot load {install.orca_dll}: DLL is {install.arch}, "
            f"Python is {py_arch}. Use a {install.arch} Python interpreter."
        )
    if sys.platform != "win32":
        raise OrcaLoadError(f"pborc.dll is Windows-only; running on {sys.platform!r}")
    try:
        dll = ctypes.CDLL(install.orca_dll)
    except OSError as exc:
        raise OrcaLoadError(f"Failed to load {install.orca_dll}: {exc}") from exc
    return OrcaApi(install=install, dll=dll, tested=install.version in KNOWN_VERSIONS)
