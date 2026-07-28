"""Workspace layout detection: where a PBL's text sources live, and whether git is watching.

ORCA only ever reads and writes the binary `.pbl`. Whether a project *also*
keeps a text projection of every object — the `ws_objects/<lib>.pbl.src/*.sr*`
tree the PowerBuilder IDE creates when a workspace is put under source control
— is a property of the workspace on disk, not of ORCA. This module is the part
of pb-orca that answers that question, so the tool layer can keep both forms in
step without the caller having to know the layout.

Everything here is pure filesystem and text handling: no ORCA, no PB install
needed, fully unit-testable. It never parses PowerScript.

Two shapes of project, both first-class:

- **`pbl_only`** — no `ws_objects/`. The `.pbl` is the whole truth. Objects are
  edited through a scratch working file under `<root>/.pb-orca/`.
- **`ws_objects`** — the text files are the source of truth and the `.pbl` is
  the derived form. Every write to the `.pbl` must be mirrored into the matching
  `.sr*` file, or the next Refresh in the IDE silently reverts it.

The projection mirrors the library's path relative to the workspace root:

    <root>/src/app.pbl   ->  <root>/ws_objects/src/app.pbl.src/
    <root>/app.pbl       ->  <root>/ws_objects/app.pbl.src/

Older workspaces sometimes hold a flat tree instead, so the computed path is
only a starting point: an existing directory anywhere under `ws_objects/` wins.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

WS_OBJECTS_DIRNAME = "ws_objects"
"""Name of the directory the PB IDE creates for the text projection."""

SOURCE_DIR_SUFFIX = ".pbl.src"
"""Per-library subdirectory inside `ws_objects/`: `<library stem>.pbl.src`."""

WORK_DIRNAME = ".pb-orca"
"""Scratch directory pb-orca uses for working files, at the workspace root."""

DEFAULT_EXPORT_ENCODE = "UTF-8"
"""What `DefaultExportEncode` means when the `.pbw` does not say. PB 2022+ default."""

PBW_ENCODE_TO_ORCA: dict[str, str] = {
    "UTF-8": "utf8",
    "UTF8": "utf8",
    "UTF-16BOM": "unicode",
    "UTF-16": "unicode",
    "UNICODE": "unicode",
    "ANSI": "ansi",
}
"""`.pbw` `DefaultExportEncode` values → the `PBORCA_ENCODING` name to configure."""

_BOM_TO_CODEC: tuple[tuple[bytes, str, str], ...] = (
    (b"\xff\xfe", "utf-16-le", "unicode"),
    (b"\xfe\xff", "utf-16-be", "unicode"),
    (b"\xef\xbb\xbf", "utf-8-sig", "utf8"),
)
"""Byte-order marks pb-orca recognizes at the head of a `.sr*` file."""


class WorkspaceError(ValueError):
    """Raised when a path cannot be resolved to a usable workspace layout."""


@dataclass(frozen=True)
class LibrarySources:
    """Where one library's text projection lives (or would live)."""

    lib_path: str
    source_dir: str
    """`<root>/ws_objects/.../<lib>.pbl.src`. Populated even when it does not
    exist yet, so a bootstrap knows where to write."""
    exists: bool
    """`True` when `source_dir` is a directory on disk."""
    file_count: int
    """Number of `.sr*` files currently in `source_dir` (0 when absent)."""


@dataclass(frozen=True)
class WorkspaceInfo:
    """Everything the tool layer needs to keep a `.pbl` and its text form in step."""

    root: str
    """Workspace root: the directory holding the `.pbw`, else the library's own
    directory when the project has no workspace file."""
    workspace_file: str | None
    """Absolute path of the `.pbw`, or `None` if none was found."""
    mode: str
    """`ws_objects` when a text projection exists for this library, else `pbl_only`."""
    ws_objects_dir: str | None
    """`<root>/ws_objects` when present."""
    sources: LibrarySources | None
    """Projection details for the library this info was resolved for."""
    export_encode: str
    """The `.pbw` `DefaultExportEncode` value in effect (declared or defaulted)."""
    orca_encoding: str
    """`export_encode` translated to the `PBORCA_ENCODING` name to configure."""
    encoding_source: str
    """`pbw` (declared), `observed` (sniffed from an existing `.sr*`), or `default`."""
    observed_encoding: str | None
    """Encoding actually seen on the existing `.sr*` files, when there are any.
    A value different from `export_encode` means the workspace is already
    inconsistent and the IDE will rewrite those files on its next export."""
    git_root: str | None
    """Root of the git working tree containing the library, or `None`."""
    work_dir: str
    """`<root>/.pb-orca` — where working files go when there is no projection."""

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly form for the MCP tool payload."""
        data = asdict(self)
        data["advice"] = self.advice
        return data

    @property
    def advice(self) -> str:
        """One line telling a caller what this layout implies for its next write."""
        if self.mode == "ws_objects":
            return (
                "Text projection present: every write to the .pbl must also rewrite the "
                "matching .sr* file, and both go in the same commit. The file-based tools "
                "and sync_sources='auto' do that for you."
            )
        if self.git_root:
            return (
                "No text projection: git can only see opaque .pbl changes. "
                "pb_library_export_sources bootstraps ws_objects/ from the .pbl if you "
                "want reviewable diffs."
            )
        return (
            "No text projection and no git: the .pbl is the whole truth. "
            f"Working files go under {self.work_dir}."
        )


def find_workspace_file(start: str | os.PathLike[str]) -> str | None:
    """Walk up from a file or directory to the nearest `.pbw`.

    Returns the absolute path, or `None` when the tree holds no workspace file.
    When a directory holds several, the one whose stem matches the directory
    name wins; otherwise the first in sorted order, so the result is stable.
    """
    for directory in _ancestors(start):
        candidates = sorted(directory.glob("*.pbw"))
        if not candidates:
            continue
        for candidate in candidates:
            if candidate.stem.lower() == directory.name.lower():
                return str(candidate)
        return str(candidates[0])
    return None


def find_git_root(start: str | os.PathLike[str]) -> str | None:
    """Walk up from a file or directory to the nearest git working tree root.

    Recognizes both a `.git` directory and the `.git` *file* a worktree or
    submodule checkout uses. Purely filesystem-based: no `git` executable is
    invoked, so this works on a machine without git installed and cannot hang.
    """
    for directory in _ancestors(start):
        if (directory / ".git").exists():
            return str(directory)
    return None


def read_default_export_encode(workspace_file: str | os.PathLike[str]) -> str | None:
    """Read `DefaultExportEncode` out of a `.pbw`, or `None` when absent.

    The directive is `DefaultExportEncode "UTF-8";`. Keywords in PB project
    files are case-insensitive, so the match is too.
    """
    text = Path(workspace_file).read_text(encoding="utf-8-sig", errors="replace")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.lower().startswith("defaultexportencode"):
            continue
        first = stripped.find('"')
        last = stripped.rfind('"')
        if first != -1 and last > first:
            return stripped[first + 1 : last]
    return None


def orca_encoding_for(export_encode: str) -> str:
    """Translate a `.pbw` `DefaultExportEncode` value to a `PBORCA_ENCODING` name.

    Unknown values fall back to `utf8` rather than raising: an unreadable
    directive should not block an export, and UTF-8 is the modern default.
    """
    return PBW_ENCODE_TO_ORCA.get(export_encode.strip().upper(), "utf8")


def source_dir_for_library(lib_path: str | os.PathLike[str], root: str | os.PathLike[str]) -> Path:
    """Compute where `lib_path`'s projection directory belongs under `root`.

    Mirrors the library's path relative to the workspace root, which is what
    the PB IDE does. A library outside the root (a vendored dependency reached
    through `..`) collapses to a flat entry directly under `ws_objects/`.
    """
    lib = Path(lib_path).resolve()
    ws_objects = Path(root).resolve() / WS_OBJECTS_DIRNAME
    try:
        relative_dir = lib.parent.relative_to(Path(root).resolve())
    except ValueError:
        relative_dir = Path()
    return ws_objects / relative_dir / f"{lib.stem}{SOURCE_DIR_SUFFIX}"


def locate_source_dir(lib_path: str | os.PathLike[str], root: str | os.PathLike[str]) -> Path:
    """Find the projection directory for a library, preferring one that exists.

    The mirrored path (`source_dir_for_library`) is checked first. Workspaces
    that predate the per-library layout keep a flat tree instead, so an
    existing `<lib>.pbl.src` found anywhere under `ws_objects/` wins over the
    computed location. When nothing exists, the computed path is returned so a
    bootstrap knows where to create it.
    """
    computed = source_dir_for_library(lib_path, root)
    if computed.is_dir():
        return computed
    ws_objects = Path(root).resolve() / WS_OBJECTS_DIRNAME
    if ws_objects.is_dir():
        wanted = f"{Path(lib_path).stem}{SOURCE_DIR_SUFFIX}".lower()
        matches = sorted(
            p for p in ws_objects.rglob(f"*{SOURCE_DIR_SUFFIX}") if p.name.lower() == wanted
        )
        if matches:
            return matches[0]
    return computed


def describe(lib_path: str | os.PathLike[str]) -> WorkspaceInfo:
    """Resolve the full workspace layout around one `.pbl`.

    This is the single entry point the tool layer uses before any write: it
    answers "does this project keep text sources, where, in which encoding, and
    is git watching" in one shot. It never fails on a missing workspace file or
    a missing projection — those are legitimate layouts, reported as such.
    """
    lib = Path(lib_path)
    workspace_file = find_workspace_file(lib)
    root = Path(workspace_file).parent if workspace_file else lib.resolve().parent

    ws_objects = root / WS_OBJECTS_DIRNAME
    ws_objects_dir = str(ws_objects) if ws_objects.is_dir() else None

    source_dir = locate_source_dir(lib, root)
    source_files = _source_files(source_dir)
    sources = LibrarySources(
        lib_path=str(lib),
        source_dir=str(source_dir),
        exists=source_dir.is_dir(),
        file_count=len(source_files),
    )

    declared = read_default_export_encode(workspace_file) if workspace_file else None
    observed = _observed_encoding(source_files)
    if declared:
        export_encode, encoding_source = declared, "pbw"
    elif observed:
        export_encode, encoding_source = _export_encode_for_orca(observed), "observed"
    else:
        export_encode, encoding_source = DEFAULT_EXPORT_ENCODE, "default"

    return WorkspaceInfo(
        root=str(root),
        workspace_file=workspace_file,
        mode="ws_objects" if sources.exists else "pbl_only",
        ws_objects_dir=ws_objects_dir,
        sources=sources,
        export_encode=export_encode,
        orca_encoding=orca_encoding_for(export_encode),
        encoding_source=encoding_source,
        observed_encoding=observed,
        git_root=find_git_root(lib),
        work_dir=str(root / WORK_DIRNAME),
    )


def decode_source_bytes(data: bytes, *, fallback: str = "utf8") -> tuple[str, str]:
    """Decode a `.sr*` file's bytes, preserving line endings exactly.

    Returns `(text, encoding_name)` where `encoding_name` is the
    `PBORCA_ENCODING`-style name of what was found. The BOM decides when there
    is one; otherwise `fallback` (the workspace encoding) is tried and the
    system code page is the last resort, since an ANSI workspace carries no BOM.

    Line endings are **not** translated. PowerBuilder stores CRLF, and feeding
    LF-normalized text back through an import rewrites every line in the `.pbl`,
    which shows up later as a whole-file phantom diff.
    """
    for bom, codec, name in _BOM_TO_CODEC:
        if data.startswith(bom):
            return data.decode(codec), name
    if fallback == "unicode":
        return data.decode("utf-16-le"), "unicode"
    if fallback == "utf8":
        try:
            return data.decode("utf-8"), "utf8"
        except UnicodeDecodeError:
            pass
    return data.decode("mbcs", errors="replace"), "ansi"


def read_source_file(path: str | os.PathLike[str], *, fallback: str = "utf8") -> tuple[str, str]:
    """Read a `.sr*` file into `(text, encoding_name)` without touching line endings."""
    return decode_source_bytes(Path(path).read_bytes(), fallback=fallback)


def strip_export_headers(text: str) -> tuple[str, str | None]:
    """Split the leading `$PBExport*$` lines off a source file's text.

    Returns `(body, comment)`; `comment` is the `$PBExportComments$` payload
    when the file carries one, else `None`.

    ORCA ignores these lines on import, so this is not needed to *import* a
    file. It is needed to recover the object comment a caller edited in the
    file, since the comment reaches ORCA as a separate argument and would
    otherwise be silently dropped.
    """
    comment: str | None = None
    index = 0
    lines = text.split("\n")
    for line in lines:
        stripped = line.rstrip("\r")
        if stripped.startswith("$PBExportHeader$"):
            index += 1
            continue
        if stripped.startswith("$PBExportComments$"):
            comment = stripped[len("$PBExportComments$") :]
            index += 1
            continue
        break
    return "\n".join(lines[index:]), comment


def _ancestors(start: str | os.PathLike[str]) -> list[Path]:
    """The starting directory and each of its parents, nearest first."""
    path = Path(start).resolve()
    directory = path if path.is_dir() else path.parent
    return [directory, *directory.parents]


def _source_files(source_dir: Path) -> list[Path]:
    if not source_dir.is_dir():
        return []
    return sorted(
        p for p in source_dir.iterdir() if p.is_file() and p.suffix.lower().startswith(".sr")
    )


def _observed_encoding(source_files: list[Path]) -> str | None:
    """Sniff the encoding of the projection from the first file that has a BOM.

    A file with no BOM is reported as `ansi` only when it is the sole evidence,
    since that is what an ANSI workspace looks like.
    """
    for path in source_files:
        with path.open("rb") as handle:
            head = handle.read(4)
        for bom, _codec, name in _BOM_TO_CODEC:
            if head.startswith(bom):
                return name
    return "ansi" if source_files else None


def _export_encode_for_orca(orca_name: str) -> str:
    """Inverse of `orca_encoding_for`, for reporting a sniffed encoding as a `.pbw` value."""
    return {"utf8": "UTF-8", "unicode": "UTF-16BOM", "ansi": "ANSI"}.get(
        orca_name, DEFAULT_EXPORT_ENCODE
    )
