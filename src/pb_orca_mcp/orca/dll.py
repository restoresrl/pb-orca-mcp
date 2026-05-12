"""Version-aware loader for pborc.dll.

`load_orca(install)` takes a PbInstall (from discovery) and returns an
OrcaApi object wrapping the pborc.dll of that specific PowerBuilder
installation, with the correct ctypes prototypes. Multi-version is a day-1
requirement: a single machine can host several PB IDE installs side-by-side
(e.g. PB 2019 R3, PB 2022 R3, PB 2025), each shipping its own
`<install>\\IDE\\pborc.dll` (no version suffix on the filename); the loader
picks the right one per target.

The ORCA ABI has been stable since PB 2019, so a single set of prototypes
covers every modern release. KNOWN_VERSIONS lists the major versions that
are actively tested; the discovery accepts any installation that exposes
pborc.dll, marking unknown versions with `tested=False`.

Implemented in phase 2.
"""

KNOWN_VERSIONS = ("19.0", "22.0", "25.0")
"""PowerBuilder major versions actively tested by v1.

This is a guideline, not a gate: discovery returns every install that ships
`pborc.dll`, including versions outside this tuple (with `tested=False`).
Add a new release here once it has been smoke-tested against the loader.
"""
