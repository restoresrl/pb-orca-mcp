"""Discovery tools: `pb_target_info` parser and `pb_discover_pb_install` wrapper.

`pb_target_info` parses PowerBuilder `.pbt` (target) and `.pbw` (workspace)
files. Format verified across PB 19/22/25:

    Save Format v3.0(19990112)        <- constant magic header, NOT a PB version
    @begin Projects ... @end;          <- optional block
    appname "myapp";
    applib "myapp.pbl";
    LibList "a.pbl;b.pbl;..\\dep\\c.pbl";
    type "pb";

`.pbw` uses `@begin Targets ... @end;` + `DefaultTarget`/`DefaultExportEncode`
/`DefaultRemoteTarget` directives with the same syntax.

Notes:
- Keywords are case-insensitive (`LibList` and `liblist` both seen).
- String values use C-style backslash escapes (`..\\dep\\foo.pbl`).
- The magic header is constant since 1999-01-12 (Sybase format freeze) — it
  does NOT identify the PowerBuilder release. PB version selection is
  always explicit on the caller side (`pb_session_open` requires
  `install_path` or `pb_version`).

`pb_discover_pb_install` is the MCP-facing wrapper around
`pb_orca_mcp.discovery.discover_pb_installations()`.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

_MAGIC_HEADER = "Save Format v3.0(19990112)"

_DIRECTIVE_RE = re.compile(
    r'^\s*(?P<key>[A-Za-z_][A-Za-z0-9_ ]*?)\s+"(?P<value>(?:[^"\\]|\\.)*)"\s*;\s*$'
)
_BLOCK_START_RE = re.compile(r"^\s*@begin\s+(?P<name>\w+)\s*$")
_BLOCK_END_RE = re.compile(r"^\s*@end\s*;\s*$")
_BLOCK_ENTRY_RE = re.compile(r'^\s*(?P<index>\d+)\s+"(?P<value>(?:[^"\\]|\\.)*)"\s*;\s*$')


@dataclass(frozen=True)
class PbtInfo:
    """Parsed `.pbt` target file."""

    kind: Literal["pbt"] = "pbt"
    target_name: str = ""
    app_name: str = ""
    app_lib: str = ""
    lib_list: list[str] = field(default_factory=list)
    type: str = ""


@dataclass(frozen=True)
class PbwInfo:
    """Parsed `.pbw` workspace file."""

    kind: Literal["pbw"] = "pbw"
    workspace_name: str = ""
    targets: list[str] = field(default_factory=list)
    default_target: str = ""


class PbProjectParseError(ValueError):
    """Raised when a `.pbt`/`.pbw` file cannot be parsed."""


def _unescape(value: str) -> str:
    """Resolve C-style backslash escapes in a PB project string."""
    return value.replace("\\\\", "\\").replace('\\"', '"')


def _parse_directives(text: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Tokenize a `.pbt`/`.pbw` body into directives and `@begin/@end` blocks.

    Returns `(directives, blocks)` where:
    - `directives` maps lowercased key → string value (last wins on duplicates),
    - `blocks` maps block name (preserved-case) → list of entry values in
      file order (not by index — the index in the file is ignored).

    The magic header line is consumed before this is called.
    """
    directives: dict[str, str] = {}
    blocks: dict[str, list[str]] = {}
    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        m_block = _BLOCK_START_RE.match(line)
        if m_block:
            block_name = m_block.group("name")
            entries: list[str] = []
            i += 1
            while i < n and not _BLOCK_END_RE.match(lines[i]):
                m_entry = _BLOCK_ENTRY_RE.match(lines[i])
                if m_entry:
                    entries.append(_unescape(m_entry.group("value")))
                i += 1
            if i >= n:
                raise PbProjectParseError(f"unterminated @begin {block_name} block")
            blocks[block_name] = entries
            i += 1
            continue
        m_dir = _DIRECTIVE_RE.match(line)
        if m_dir:
            key = m_dir.group("key").strip().lower()
            directives[key] = _unescape(m_dir.group("value"))
            i += 1
            continue
        # Unknown line shape — skip rather than fail; PB has historically added
        # new directive flavors without breaking back-compat readers.
        i += 1
    return directives, blocks


def _strip_magic(text: str) -> str:
    """Strip the constant magic header line, raising if it's missing."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != _MAGIC_HEADER:
        raise PbProjectParseError(
            f"missing or unexpected magic header (expected {_MAGIC_HEADER!r})"
        )
    return "\n".join(lines[1:])


def _split_lib_list(value: str) -> list[str]:
    return [part.strip() for part in value.split(";") if part.strip()]


def parse_pbt_text(text: str, target_name: str = "") -> PbtInfo:
    """Parse `.pbt` body text. `target_name` defaults to the file stem when called from disk."""
    body = _strip_magic(text)
    directives, _blocks = _parse_directives(body)
    return PbtInfo(
        target_name=target_name,
        app_name=directives.get("appname", ""),
        app_lib=directives.get("applib", ""),
        lib_list=_split_lib_list(directives.get("liblist", "")),
        type=directives.get("type", ""),
    )


def parse_pbw_text(text: str, workspace_name: str = "") -> PbwInfo:
    """Parse `.pbw` body text. `workspace_name` defaults to the file stem when called from disk."""
    body = _strip_magic(text)
    directives, blocks = _parse_directives(body)
    return PbwInfo(
        workspace_name=workspace_name,
        targets=blocks.get("Targets", []),
        default_target=directives.get("defaulttarget", ""),
    )


def parse_pb_project_file(path: str | Path) -> PbtInfo | PbwInfo:
    """Dispatch on file extension and parse a `.pbt` or `.pbw` from disk."""
    p = Path(path)
    text = p.read_text(encoding="utf-8-sig")
    suffix = p.suffix.lower()
    if suffix == ".pbt":
        return parse_pbt_text(text, target_name=p.stem)
    if suffix == ".pbw":
        return parse_pbw_text(text, workspace_name=p.stem)
    raise PbProjectParseError(f"unsupported PB project file extension: {p.suffix!r}")


def pb_target_info(path: str | Path) -> dict[str, Any]:
    """MCP tool: structural info for a `.pbt` or `.pbw` file.

    Does NOT return `pb_version` — PB project files don't embed the
    PowerBuilder release (see PLAN.md §"Parser .pbt / .pbw"). Selection of
    the ORCA DLL is always explicit on `pb_session_open`.
    """
    return asdict(parse_pb_project_file(path))


def pb_discover_pb_install() -> dict[str, Any]:
    """MCP tool: enumerate PowerBuilder IDE installations on this machine."""
    from pb_orca_mcp.discovery import discover_pb_installations

    ide, runtime = discover_pb_installations()
    return {
        "ide_installations": [asdict(i) for i in ide],
        "runtime_only_installations": [asdict(r) for r in runtime],
    }
