"""End-to-end validation of pb-orca against a real PowerBuilder project.

`pb-orca-mcp doctor` answers "is PowerBuilder installed and can I load ORCA".
This answers the question a developer actually has first: **does it work on my
project?** It runs the whole stack — target parsing, workspace detection,
install selection, DLL load, session, library read, and a real ORCA source
export — against a `.pbw`, `.pbt` or `.pbl` the caller names, and reports each
step. No MCP client is involved, so when something is wrong there is nothing
between the failure and the message.

It does not modify the project. The only thing written is one exported source
file in a temporary directory, deleted before the command returns. In
particular it does **not** set the current application, because ORCA can
rewrite the `.pbw` as a side effect of that call; the cost is that the compile
path is not exercised, which the report says out loud.
"""

from __future__ import annotations

import contextlib
import shutil
import struct
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from pb_orca_mcp import workspace as ws
from pb_orca_mcp.discovery import discover_pb_installations
from pb_orca_mcp.orca.dll import OrcaLoadError, load_orca
from pb_orca_mcp.orca.errors import OrcaError
from pb_orca_mcp.orca.session import Session
from pb_orca_mcp.tools.discovery import (
    PbProjectParseError,
    PbtInfo,
    PbwInfo,
    parse_pb_project_file,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pb_orca_mcp.discovery import PbInstall


class CheckError(RuntimeError):
    """A step failed in a way that stops the check. Carries a caller-facing hint."""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


@dataclass
class Target:
    """What the caller pointed at, resolved to something ORCA can be pointed at."""

    path: Path
    app_name: str = ""
    app_lib: Path | None = None
    libraries: list[Path] = field(default_factory=list)
    target_file: Path | None = None
    """The `.pbt` in play, when the caller named a `.pbw` or a `.pbt`."""
    note: str = ""


def resolve_target(raw: str) -> Target:
    """Turn a `.pbw`, `.pbt` or `.pbl` path into an application and a library list.

    A `.pbw` resolves through its default target (or its only one). Library
    paths inside a `.pbt` are relative to the `.pbt`, and are returned resolved.
    """
    path = Path(raw).expanduser()
    if not path.exists():
        raise CheckError(f"{path} does not exist", "Point at a .pbw, .pbt or .pbl file.")
    suffix = path.suffix.lower()

    if suffix == ".pbl":
        return Target(path=path, libraries=[path.resolve()], note="library only, no target file")

    if suffix not in (".pbw", ".pbt"):
        raise CheckError(
            f"{path.name} is not a PowerBuilder project file",
            "Expected a .pbw (workspace), .pbt (target) or .pbl (library).",
        )

    try:
        parsed = parse_pb_project_file(path)
    except (PbProjectParseError, OSError) as exc:
        raise CheckError(f"cannot parse {path.name}: {exc}") from exc

    if isinstance(parsed, PbwInfo):
        return _target_from_workspace(path, parsed)
    return _target_from_pbt(path, parsed)


def _target_from_workspace(pbw: Path, parsed: PbwInfo) -> Target:
    if not parsed.targets:
        raise CheckError(
            f"{pbw.name} lists no targets",
            "Point at a .pbt directly, or check the workspace file.",
        )
    chosen = parsed.default_target or parsed.targets[0]
    pbt = (pbw.parent / chosen).resolve()
    if not pbt.exists():
        raise CheckError(
            f"target {chosen!r} referenced by {pbw.name} does not exist at {pbt}",
            "The workspace points at a target file that is missing.",
        )
    try:
        pbt_info = parse_pb_project_file(pbt)
    except (PbProjectParseError, OSError) as exc:
        raise CheckError(f"cannot parse {pbt.name}: {exc}") from exc
    if not isinstance(pbt_info, PbtInfo):
        raise CheckError(f"{pbt.name} did not parse as a target file")
    target = _target_from_pbt(pbt, pbt_info)
    extra = "" if len(parsed.targets) == 1 else f" of {len(parsed.targets)}"
    target.note = f"target {pbt.name}{extra}, from {pbw.name}"
    return target


def _target_from_pbt(pbt: Path, parsed: PbtInfo) -> Target:
    base = pbt.parent
    libraries = [(base / lib).resolve() for lib in parsed.lib_list]
    app_lib = (base / parsed.app_lib).resolve() if parsed.app_lib else None
    if app_lib and app_lib not in libraries:
        libraries.insert(0, app_lib)
    if not libraries:
        raise CheckError(
            f"{pbt.name} has an empty library list",
            "A target with no LibList has nothing for ORCA to open.",
        )
    return Target(
        path=pbt,
        app_name=parsed.app_name,
        app_lib=app_lib,
        libraries=libraries,
        target_file=pbt,
    )


def select_install(pb_version: str | None, install_path: str | None) -> tuple[PbInstall, list[str]]:
    """Pick the PowerBuilder install to load, or explain why none fits.

    Auto-picks only when exactly one install matches the interpreter's
    architecture — a diagnostic that refuses to run because it was not told
    which of one installs to use would be obtuse. The report always names what
    it chose and how to override it.
    """
    ides, _runtime = discover_pb_installations()
    if not ides:
        raise CheckError(
            "no PowerBuilder IDE installation found",
            "Runtime-only installs do not ship pborc.dll. Run `pb-orca-mcp doctor`.",
        )
    if install_path:
        wanted = install_path.replace("/", "\\").rstrip("\\").lower()
        for candidate in ides:
            if candidate.install_path.rstrip("\\").lower() == wanted:
                return candidate, []
        raise CheckError(f"no PB install with ORCA at {install_path!r}")
    if pb_version:
        matches = [c for c in ides if c.version == pb_version]
        if not matches:
            available = ", ".join(sorted({c.version for c in ides}))
            raise CheckError(
                f"no PB {pb_version} install found", f"Installed versions: {available}."
            )
        if len(matches) > 1:
            raise CheckError(
                f"{len(matches)} installs share version {pb_version}",
                "Disambiguate with --install-path.",
            )
        return matches[0], []

    py_arch = "x86" if struct.calcsize("P") == 4 else "x64"
    usable = [c for c in ides if c.arch == py_arch]
    if not usable:
        arches = ", ".join(sorted({c.arch for c in ides}))
        raise CheckError(
            f"no PB install matches this interpreter ({py_arch}); installed: {arches}",
            f"ctypes cannot load a {arches} DLL from {py_arch} Python. "
            "Install a matching interpreter, e.g. `uv python install 3.12 --arch x86`.",
        )
    if len(usable) > 1:
        versions = ", ".join(c.version for c in usable)
        raise CheckError(
            f"several PowerBuilder installs are usable ({versions})",
            "Pick one with --pb-version, e.g. --pb-version 22.0.",
        )
    return usable[0], ["auto-selected the only usable install; override with --pb-version"]


@dataclass
class CheckReport:
    """Everything the run learned, in the order a reader wants it."""

    lines: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def section(self, title: str) -> None:
        self.lines.append("")
        self.lines.append(title)

    def item(self, label: str, value: str) -> None:
        self.lines.append(f"  {label:<16}: {value}")

    def bullet(self, text: str) -> None:
        self.lines.append(f"    {text}")

    def warn(self, text: str) -> None:
        self.warnings.append(text)


def run_check(
    raw_target: str, *, pb_version: str | None = None, install_path: str | None = None
) -> CheckReport:
    """Run every step and return the report. Raises `CheckError` on a hard stop."""
    report = CheckReport()

    target = resolve_target(raw_target)
    report.section("Target")
    report.item("file", str(target.path))
    if target.note:
        report.item("resolved", target.note)
    if target.app_name:
        report.item("application", f"{target.app_name} in {_name(target.app_lib)}")
    report.item("libraries", str(len(target.libraries)))
    missing = [lib for lib in target.libraries if not lib.exists()]
    for lib in target.libraries[:12]:
        mark = "ok" if lib.exists() else "!!"
        suffix = "" if lib.exists() else "   (not found)"
        report.bullet(f"[{mark}] {lib}{suffix}")
    if len(target.libraries) > 12:
        report.bullet(f"... and {len(target.libraries) - 12} more")
    if missing:
        report.warn(
            f"{len(missing)} librar{'y' if len(missing) == 1 else 'ies'} in the list do not "
            "exist on disk; ORCA will not be able to resolve objects from them"
        )

    probe_lib = next((lib for lib in target.libraries if lib.exists()), None)
    if probe_lib is None:
        raise CheckError(
            "none of the libraries in the target exist on disk",
            "Check the LibList paths in the target file.",
        )

    info = ws.describe(probe_lib)
    report.section("Workspace")
    report.item("root", info.root)
    report.item("workspace file", info.workspace_file or "(none found)")
    if info.mode == "ws_objects" and info.sources is not None:
        report.item(
            "source of truth",
            f"ws_objects  ({info.sources.source_dir}, {info.sources.file_count} files)",
        )
    else:
        report.item("source of truth", f"the .pbl  (working files go to {info.work_dir})")
    if info.outside_source_tree:
        report.warn(
            f"{probe_lib.name} sits outside this project's ws_objects/ tree — that is what a "
            "vendored dependency or a third-party component looks like; check before writing"
        )
    report.item(
        "encoding", f"{info.export_encode} (from: {info.encoding_source}) -> {info.orca_encoding}"
    )
    if info.observed_encoding and info.observed_encoding != info.orca_encoding:
        report.warn(
            f"the .pbw declares {info.export_encode} but the existing .sr* files are "
            f"{info.observed_encoding}: the workspace is already inconsistent and the IDE "
            "will rewrite those files on its next export"
        )
    report.item("git", info.git_root or "(not a git working tree)")

    install, notes = select_install(pb_version, install_path)
    report.section("PowerBuilder")
    report.item("install", f"PB {install.version} [{install.arch}]  {install.install_path}")
    report.item("build", install.file_version or "(unknown)")
    if not install.tested:
        report.warn(
            f"PB {install.version} is outside the tested set; the ORCA ABI has been stable "
            "since PB 2019 so it should work, but it is not in the CI matrix"
        )
    for note in notes:
        report.item("note", note)

    try:
        api = load_orca(install)
    except OrcaLoadError as exc:
        raise CheckError(
            f"could not load {install.orca_dll}: {exc}",
            "An arch mismatch or a blocked DLL (antivirus, SmartScreen) usually causes this.",
        ) from exc
    report.item("orca", "loaded")

    with _temporary_directory() as scratch:
        _check_session(report, api, target, probe_lib, info, scratch)
    return report


def _check_session(
    report: CheckReport,
    api: object,
    target: Target,
    probe_lib: Path,
    info: ws.WorkspaceInfo,
    scratch: Path,
) -> None:
    """Open a real session and exercise the read + export path."""
    session = Session.instance()
    session.open(api)  # type: ignore[arg-type]
    report.section("Session")
    try:
        existing = [str(lib) for lib in target.libraries if lib.exists()]
        try:
            session.set_library_list(existing)
        except OrcaError as exc:
            raise CheckError(f"ORCA refused the library list: {exc}") from exc
        report.item("library list", f"accepted ({len(existing)} libraries)")

        try:
            comment, entries = session.library_directory(str(probe_lib))
        except OrcaError as exc:
            raise CheckError(
                f"could not read {probe_lib.name}: {exc}",
                "A locked library usually means the PowerBuilder IDE has it open.",
            ) from exc
        label = f"{len(entries)} entries in {probe_lib.name}"
        report.item("directory", label + (f'  ("{comment}")' if comment else ""))

        sample = _pick_sample(entries)
        if sample is None:
            report.item("export", "skipped: the library holds no exportable object")
            report.warn(
                "the source export could not be exercised because this library has no "
                "object with a text form"
            )
            return
        name, kind = sample
        try:
            path, size = session.library_entry_export_to_file(
                str(probe_lib), name, kind, str(scratch), encoding=info.orca_encoding
            )
        except OrcaError as exc:
            raise CheckError(f"could not export {name}: {exc}") from exc
        raw = Path(path).read_bytes()
        report.item("export", f"{Path(path).name}  ({size} bytes as {info.orca_encoding})")
        for detail in _describe_export(raw, name, info.orca_encoding):
            report.bullet(detail)
    finally:
        session.close()


def _pick_sample(entries: list[dict[str, object]]) -> tuple[str, str] | None:
    """Choose a small object to export, preferring the cheapest kinds."""
    preference = ("structure", "function", "userobject", "window", "menu", "application")
    exportable = [e for e in entries if str(e["type"]) in preference]
    if not exportable:
        return None
    exportable.sort(key=lambda e: (preference.index(str(e["type"])), int(e["size"])))  # type: ignore[call-overload]
    chosen = exportable[0]
    return str(chosen["name"]), str(chosen["type"])


def _describe_export(raw: bytes, entry_name: str, encoding: str) -> list[str]:
    """Say whether the exported bytes look like what PowerBuilder expects."""
    expected_bom = {"utf8": b"\xef\xbb\xbf", "unicode": b"\xff\xfe", "ansi": b""}.get(encoding, b"")
    out = []
    if expected_bom:
        ok = raw.startswith(expected_bom)
        out.append(f"[{'ok' if ok else '!!'}] byte-order mark matches {encoding}")
    else:
        out.append("[ok] no byte-order mark, as ANSI expects")
    body = raw[len(expected_bom) :]
    header = f"$PBExportHeader${entry_name}".encode(
        "utf-16-le" if encoding == "unicode" else "utf-8"
    )
    out.append(f"[{'ok' if body.startswith(header) else '!!'}] export header present")
    crlf = b"\r\x00\n\x00" if encoding == "unicode" else b"\r\n"
    out.append(f"[{'ok' if crlf in raw else '!!'}] CRLF line endings")
    return out


@contextlib.contextmanager
def _temporary_directory() -> Iterator[Path]:
    """A scratch directory that is removed even if a step raises.

    The export has to land somewhere, and it must not be inside the caller's
    project: a check that leaves files behind is not a check.
    """
    directory = Path(tempfile.mkdtemp(prefix="pb-orca-check-"))
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _name(path: Path | None) -> str:
    return path.name if path else "(unknown library)"


def format_report(report: CheckReport, target: str) -> str:
    """Render the report, closing with a verdict and what was not covered."""
    lines = list(report.lines)
    lines.append("")
    if report.warnings:
        lines.append("Warnings")
        for warning in report.warnings:
            lines.append(f"  ! {warning}")
        lines.append("")
    lines.append(f"Check OK: pb-orca can read and export from {target}.")
    lines.append(
        "Not exercised: the compile path. It needs the current application set, and ORCA "
        "can rewrite the .pbw as a side effect of that, which a check should not do."
    )
    return "\n".join(lines)


def format_failure(exc: CheckError) -> str:
    """Render a hard stop as a message plus, when there is one, a way forward."""
    out = f"Check failed: {exc}"
    if exc.hint:
        out += f"\n  {exc.hint}"
    return out


def preamble() -> str:
    """The version/interpreter banner shared with `doctor`."""
    from pb_orca_mcp import __version__

    arch = "x86" if struct.calcsize("P") == 4 else "x64"
    return f"pb-orca-mcp {__version__}\nPython: {sys.version.split()[0]} ({arch})"
