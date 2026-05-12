"""Discovery of local PowerBuilder IDE installations.

Enumerates every PB IDE install on the machine and returns:

- `ide_installations`: installs with `<install>\\IDE\\pborc.dll` present.
- `runtime_only_installations`: installs that don't ship the ORCA DLL
  (PB Runtime, PowerBuilderUtilities, PowerBuilder Installer, etc.).

Sources, merged in order with later sources only filling gaps:

1. Env `PB_INSTALL_PATH` — explicit override, can be a path or `;`-separated
   list of paths.
2. Registry `HKLM\\SOFTWARE\\WOW6432Node\\Sybase\\PowerBuilder\\<X.0>` — the
   legacy Sybase key that Appeon kept. Values used: `Location` (= parent
   dir), `IPS Name` (= subdir; install dir = `Location + "\\" + IPS Name`),
   `Build` (= full file version, e.g. `22.2.0.3397`), `BuildFlag` (= human
   product version, e.g. `2022 R3`), `VersionMajor`/`VersionMinor`.
3. Filesystem fallback — scan `C:\\Program Files{,(x86)}\\Appeon\\
   PowerBuilder *.0\\`. Sibling dirs without `IDE\\pborc.dll` are classified
   as runtime-only.

For each install we probe `IDE/pborc.dll`, read its arch (PE Machine field
via `_pe.read_pe_arch`), and — only when registry didn't already provide it
— pull `(FileVersion, ProductVersion)` from the DLL via `_pe.read_pe_file_version`.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pb_orca_mcp._pe import PeArch, read_pe_arch, read_pe_file_version
from pb_orca_mcp.orca.dll import KNOWN_VERSIONS

_REGISTRY_PATHS = (
    r"SOFTWARE\WOW6432Node\Sybase\PowerBuilder",
    r"SOFTWARE\Sybase\PowerBuilder",
)
_PROGRAM_FILES_DIRS = (
    os.environ.get("PROGRAMFILES(X86)") or r"C:\Program Files (x86)",
    os.environ.get("PROGRAMFILES") or r"C:\Program Files",
)
_APPEON_SUBDIR = "Appeon"
# Trailing space: matches "PowerBuilder 22.0", excludes "PowerBuilderUtilities 22.0" etc.
_PB_DIR_PREFIX = "PowerBuilder "
_ORCA_DLL_FILENAME = "pborc.dll"
_IDE_SUBDIR = "IDE"


@dataclass(frozen=True)
class PbInstall:
    """A PowerBuilder IDE installation with ORCA available."""

    version: str
    """Major version string, e.g. "22.0"."""
    file_version: str | None
    """Full build, e.g. "22.2.0.3397". `None` if no source supplied it."""
    product_version: str | None
    """Human-readable, e.g. "2022 R3". `None` if unavailable."""
    arch: PeArch
    """Arch of `pborc.dll` (`x86`/`x64`/`unknown`). Python must match."""
    install_path: str
    """Install root, e.g. "C:\\Program Files (x86)\\Appeon\\PowerBuilder 22.0"."""
    ide_path: str
    """`<install_path>\\IDE`."""
    orca_dll: str
    """`<install_path>\\IDE\\pborc.dll`."""
    tested: bool
    """`True` if `version` is in `KNOWN_VERSIONS`."""
    source: str
    """Where this install was discovered: `env`, `registry`, or `filesystem`."""


@dataclass(frozen=True)
class PbRuntimeOnly:
    """A PowerBuilder-related install that lacks ORCA (runtime, utilities, installer, etc.)."""

    path: str
    reason: str
    version: str | None = None
    """Major version if inferrable from the directory name, else `None`."""


def discover_pb_installations() -> tuple[list[PbInstall], list[PbRuntimeOnly]]:
    """Enumerate PB IDE installs and runtime-only siblings on this machine."""
    by_path: dict[str, PbInstall] = {}
    runtime: list[PbRuntimeOnly] = []
    seen_runtime_paths: set[str] = set()

    for inst in _from_env():
        by_path[_norm(inst.install_path)] = inst

    reg_ides, reg_runtime = _from_registry()
    for x in reg_ides:
        key = _norm(x.install_path)
        if key not in by_path:
            by_path[key] = x
    for r in reg_runtime:
        key = _norm(r.path)
        if key not in seen_runtime_paths:
            runtime.append(r)
            seen_runtime_paths.add(key)

    fs_ides, fs_runtime = _from_filesystem()
    for x in fs_ides:
        key = _norm(x.install_path)
        if key not in by_path:
            by_path[key] = x
    for r in fs_runtime:
        key = _norm(r.path)
        if key not in seen_runtime_paths and key not in by_path:
            runtime.append(r)
            seen_runtime_paths.add(key)

    ides = sorted(by_path.values(), key=lambda i: (i.version, i.install_path))
    runtime.sort(key=lambda r: r.path)
    return ides, runtime


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def _from_env() -> list[PbInstall]:
    raw = os.environ.get("PB_INSTALL_PATH")
    if not raw:
        return []
    out: list[PbInstall] = []
    for chunk in raw.split(";"):
        chunk = chunk.strip().strip('"')
        if not chunk:
            continue
        inst = _build_install(install_path=chunk, source="env")
        if inst is not None:
            out.append(inst)
    return out


def _from_registry() -> tuple[list[PbInstall], list[PbRuntimeOnly]]:
    if sys.platform != "win32":
        return [], []
    try:
        import winreg
    except ImportError:
        return [], []

    ides: list[PbInstall] = []
    runtime: list[PbRuntimeOnly] = []
    for base in _REGISTRY_PATHS:
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base)
        except OSError:
            continue
        try:
            for i in range(0, 1024):  # bounded loop; PB key has a handful of subkeys
                try:
                    subkey_name = winreg.EnumKey(key, i)
                except OSError:
                    break
                if not _looks_like_pb_major(subkey_name):
                    continue
                values = _read_registry_values(winreg, key, subkey_name)
                if values is None:
                    continue
                inst, ro = _install_from_registry_values(subkey_name, values)
                if inst is not None:
                    ides.append(inst)
                elif ro is not None:
                    runtime.append(ro)
        finally:
            key.Close()
    return ides, runtime


def _looks_like_pb_major(name: str) -> bool:
    """`19.0`, `22.0`, `25.0` — `MAJOR.MINOR` with integer parts."""
    parts = name.split(".")
    return len(parts) == 2 and all(p.isdigit() for p in parts)


def _read_registry_values(
    winreg_mod: Any, parent: Any, subkey_name: str
) -> dict[str, str] | None:
    try:
        sub = winreg_mod.OpenKey(parent, subkey_name)
    except OSError:
        return None
    values: dict[str, str] = {}
    try:
        for i in range(0, 256):
            try:
                name, value, _type = winreg_mod.EnumValue(sub, i)
            except OSError:
                break
            if isinstance(value, str):
                values[name] = value
            elif isinstance(value, int):
                values[name] = str(value)
    finally:
        sub.Close()
    return values


def _install_from_registry_values(
    version: str, values: dict[str, str]
) -> tuple[PbInstall | None, PbRuntimeOnly | None]:
    location = values.get("Location")
    ips_name = values.get("IPS Name")
    if not location or not ips_name:
        return None, None
    install_path = os.path.join(location, ips_name)
    file_version = values.get("Build")
    build_flag = values.get("BuildFlag")
    if build_flag and file_version:
        product_version: str | None = f"{build_flag} Build {file_version.split('.')[-1]}"
    else:
        product_version = build_flag
    inst = _build_install(
        install_path=install_path,
        source="registry",
        version=version,
        file_version=file_version,
        product_version=product_version,
    )
    if inst is not None:
        return inst, None
    # Registry pointed here but no pborc.dll — installer leftover or runtime entry.
    return None, PbRuntimeOnly(
        path=install_path,
        reason="pborc.dll missing under IDE/",
        version=version,
    )


def _from_filesystem() -> tuple[list[PbInstall], list[PbRuntimeOnly]]:
    ides: list[PbInstall] = []
    runtime: list[PbRuntimeOnly] = []
    for pf in _PROGRAM_FILES_DIRS:
        appeon_dir = Path(pf) / _APPEON_SUBDIR
        if not appeon_dir.is_dir():
            continue
        for child in appeon_dir.iterdir():
            if not child.is_dir():
                continue
            name = child.name
            if not name.startswith(_PB_DIR_PREFIX):
                continue
            version = _major_from_dir_name(name)
            install_path = str(child)
            inst = _build_install(install_path=install_path, source="filesystem", version=version)
            if inst is not None:
                ides.append(inst)
            else:
                runtime.append(
                    PbRuntimeOnly(
                        path=install_path,
                        reason="pborc.dll missing under IDE/",
                        version=version,
                    )
                )
    return ides, runtime


def _major_from_dir_name(name: str) -> str | None:
    """Extract `MAJOR.MINOR` from a `"PowerBuilder X.Y"` directory name."""
    tail = name[len(_PB_DIR_PREFIX):].strip()
    if _looks_like_pb_major(tail):
        return tail
    return None


def _build_install(
    *,
    install_path: str,
    source: str,
    version: str | None = None,
    file_version: str | None = None,
    product_version: str | None = None,
) -> PbInstall | None:
    """Probe `install_path` for ORCA. Return `None` if no `pborc.dll` is there."""
    ide_path = os.path.join(install_path, _IDE_SUBDIR)
    orca_dll = os.path.join(ide_path, _ORCA_DLL_FILENAME)
    if not os.path.isfile(orca_dll):
        return None
    try:
        arch = read_pe_arch(orca_dll)
    except (OSError, ValueError):
        arch = "unknown"
    if version is None:
        version = _major_from_dir_name(Path(install_path).name)
    if file_version is None or product_version is None:
        fv, pv = read_pe_file_version(orca_dll)
        file_version = file_version or fv
        product_version = product_version or pv
    return PbInstall(
        version=version or "",
        file_version=file_version,
        product_version=product_version,
        arch=arch,
        install_path=install_path,
        ide_path=ide_path,
        orca_dll=orca_dll,
        tested=(version in KNOWN_VERSIONS) if version else False,
        source=source,
    )
