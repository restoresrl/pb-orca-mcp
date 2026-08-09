"""MCP tools for the file-based editing loop: export to a file, edit, import back.

This is the layer that makes an agent able to change PowerBuilder code without
knowing anything about PowerScript, and without pb-orca knowing anything either.
The division of labour is strict:

- **ORCA** writes the `.sr*` file and reads the source back in. Every byte that
  matters — the `$PBExportHeader$` line, `$PBExportComments$`, the BOM, CRLF —
  is produced by the same engine the PowerBuilder IDE uses, so the result is
  byte-identical to what the IDE writes on Save.
- **pb-orca** decides *where* the file goes, moves bytes, and keeps the binary
  `.pbl` and the text projection from drifting apart.
- **The caller** edits the file with ordinary file tools. Nothing in this
  package parses, formats, or validates PowerScript.

The two shapes of project are handled by the same three calls; only the
destination changes, and it is detected, not configured:

    pb_object_export_file   ->  ws_objects/<lib>.pbl.src/<entry>.<ext>   (git projects)
                            ->  <root>/.pb-orca/<entry>.<ext>            (binary-only)
    (the caller edits that file)
    pb_object_import_file   ->  compiles into the .pbl, then rewrites the
                                projection file through ORCA so git sees both

`pb_library_export_sources` does the same for a whole library at once, which is
both the bulk-read path and the way to bootstrap a `ws_objects/` tree on a
project that never had one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pb_orca_mcp import workspace as ws
from pb_orca_mcp.orca.constants import entry_type_for_extension, extension_for_entry_type
from pb_orca_mcp.orca.errors import OrcaError
from pb_orca_mcp.orca.session import Session, SessionStateError

SYNC_MODES = ("auto", "never")
"""`auto` mirrors a `.pbl` write into the text projection when the project has
one; `never` leaves the projection alone (you are then responsible for it)."""

_WORK_DIR_GITIGNORE = """\
# Written by pb-orca: this directory holds throwaway working copies of
# PowerBuilder objects. Nothing in here belongs in version control.
*
"""


def pb_workspace_info(lib_path: str) -> dict[str, Any]:
    """Describe the workspace around a `.pbl`: text projection, encoding, git.

    Call this before the first write on an unfamiliar project. It answers, in
    one shot, whether the library keeps a `ws_objects/` text projection (and
    where), which encoding that projection uses, whether git is watching, and
    where working files go when there is no projection. It touches no ORCA
    session, so it works before `pb_session_open` and without PowerBuilder
    installed.

    Read `source_protection` before starting any edit loop. `unprotected` means
    no `.gitattributes` rule exempts the `.sr*` files from git's line-ending
    translation, so git stores them with LF and checks them out with CRLF: a
    write can land in both the `.pbl` and its projection while `git status`
    stays clean, and the drift only appears on someone else's checkout. `advice`
    spells out the fix. This is a filesystem answer about whether the protection
    exists, not a measurement of what the index already holds — for that, run
    `git ls-files --eol` yourself.
    """
    try:
        info = ws.describe(lib_path)
    except OSError as exc:
        return _error("PB_ORCA_MCP_WORKSPACEERROR", str(exc))
    return info.to_dict()


def pb_object_export_file(
    lib_path: str,
    entry_name: str,
    entry_type: str,
    dest_dir: str | None = None,
) -> dict[str, Any]:
    """Write an object's source to a `.sr*` file for editing, and return its path.

    ORCA writes the file itself, in the workspace's declared encoding and with
    the export headers, so it is byte-identical to the PB IDE's own output.

    The destination is detected unless `dest_dir` says otherwise: the library's
    `ws_objects/<lib>.pbl.src/` directory when the project keeps a text
    projection (the file *is* the source of truth there, so it is refreshed in
    place), otherwise a working copy under `<workspace>/.pb-orca/`.

    Edit the returned `file_path` with ordinary file tools, then hand it back to
    `pb_object_import_file`.
    """
    session = Session.instance()
    try:
        _require_session(session, "pb_object_export_file")
        info = ws.describe(lib_path)
        directory, is_projection = _resolve_dest(info, dest_dir)
        _ensure_dir(directory, info, is_projection)
        file_path, size = session.library_entry_export_to_file(
            lib_path, entry_name, entry_type, str(directory), encoding=info.orca_encoding
        )
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except ValueError as exc:
        return _error("PB_ORCA_MCP_INVALIDARGS", str(exc))
    except OSError as exc:
        return _error("PB_ORCA_MCP_IOERROR", str(exc))
    except OrcaError as exc:
        return {"error": exc.to_dict()}
    return {
        "ok": True,
        "file_path": file_path,
        "lib_path": lib_path,
        "entry_name": entry_name,
        "entry_type": entry_type,
        "encoding": info.orca_encoding,
        "export_encode": info.export_encode,
        "bytes": size,
        "mode": info.mode,
        "is_source_of_truth": is_projection,
    }


def pb_object_import_file(
    file_path: str,
    lib_path: str,
    entry_name: str | None = None,
    entry_type: str | None = None,
    comments: str | None = None,
    sync_sources: str = "auto",
) -> dict[str, Any]:
    """Compile a `.sr*` file into the `.pbl`, then refresh the text projection.

    `entry_name` and `entry_type` default to the file's stem and extension
    (`w_main.srw` → the window `w_main`), and `comments` defaults to the
    `$PBExportComments$` line the file carries, so a file produced by
    `pb_object_export_file` round-trips with no extra arguments. An entry that
    does not exist yet is created.

    The file is read without touching its line endings: PowerBuilder stores
    CRLF, and importing LF-normalized text rewrites every line inside the
    `.pbl` and shows up later as a whole-file phantom diff.

    On success, when the project keeps a text projection and `sync_sources` is
    `auto`, ORCA rewrites the projection file so the text on disk is exactly
    what the `.pbl` now holds. That is what keeps git honest: the `.pbl` and the
    `.sr*` change together, in one call, and belong in one commit.

    On a compile error nothing is synced and `errors` carries the diagnostics
    (object, line, column, message). Note that ORCA still writes the partial
    source into the `.pbl` in that case, so fix the file and re-import rather
    than assuming the entry was left untouched.
    """
    if sync_sources not in SYNC_MODES:
        return _error(
            "PB_ORCA_MCP_INVALIDARGS",
            f"sync_sources must be one of {SYNC_MODES}, got {sync_sources!r}",
        )
    session = Session.instance()
    source = Path(file_path)
    try:
        info = ws.describe(lib_path)
        if entry_type is None:
            entry_type = entry_type_for_extension(source.suffix)
        if entry_name is None:
            entry_name = source.stem
        text, file_encoding = ws.read_source_file(source, fallback=info.orca_encoding)
        _body, file_comment = ws.strip_export_headers(text)
        success, errors = session.compile_entry_import(
            lib_path,
            entry_name,
            entry_type,
            text,
            comments if comments is not None else (file_comment or ""),
        )
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except ValueError as exc:
        return _error("PB_ORCA_MCP_INVALIDARGS", str(exc))
    except OSError as exc:
        return _error("PB_ORCA_MCP_IOERROR", str(exc))
    except OrcaError as exc:
        return {"error": exc.to_dict(), "errors": session.last_compile_errors}

    result: dict[str, Any] = {
        "success": success,
        "lib_path": lib_path,
        "entry_name": entry_name,
        "entry_type": entry_type,
        "file_path": str(source),
        "file_encoding": file_encoding,
        "errors": errors,
    }
    if success:
        result.update(sync_entry(session, info, entry_name, entry_type, sync_sources))
    else:
        result["synced_files"] = []
    return result


def pb_library_export_sources(
    lib_path: str,
    dest_dir: str | None = None,
    entry_type: str = "any",
) -> dict[str, Any]:
    """Export every object in a library to `.sr*` files, through ORCA.

    Two uses. As a bulk read, it gives an agent the whole library as grep-able
    text in one call. As a bootstrap, it builds the `ws_objects/<lib>.pbl.src/`
    tree for a project that only ever had the binary `.pbl`, turning opaque
    binary commits into reviewable diffs; from then on the text files are the
    source of truth and the two forms have to move together.

    `dest_dir` defaults to the projection directory for the library (created if
    missing). `entry_type` filters the export; entry kinds with no source form
    (`project`, `proxyobject`, `binary`) are always skipped and listed under
    `skipped`.
    """
    session = Session.instance()
    try:
        _require_session(session, "pb_library_export_sources")
        info = ws.describe(lib_path)
        directory = Path(dest_dir) if dest_dir else Path(info.sources.source_dir)  # type: ignore[union-attr]
        _ensure_dir(directory, info, is_projection=dest_dir is None)
        _comment, entries = session.library_directory(lib_path)
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except OSError as exc:
        return _error("PB_ORCA_MCP_IOERROR", str(exc))
    except OrcaError as exc:
        return {"error": exc.to_dict()}

    wanted = entry_type.lower()
    written: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    failed: list[dict[str, Any]] = []
    for entry in entries:
        if wanted != "any" and entry["type"] != wanted:
            continue
        try:
            extension_for_entry_type(entry["type"])
        except ValueError as exc:
            skipped.append({"entry_name": entry["name"], "reason": str(exc)})
            continue
        try:
            path, size = session.library_entry_export_to_file(
                lib_path,
                entry["name"],
                entry["type"],
                str(directory),
                encoding=info.orca_encoding,
            )
        except OrcaError as exc:
            failed.append({"entry_name": entry["name"], "error": exc.to_dict()})
            continue
        written.append(
            {
                "entry_name": entry["name"],
                "entry_type": entry["type"],
                "file_path": path,
                "bytes": size,
            }
        )
    return {
        "ok": not failed,
        "lib_path": lib_path,
        "dest_dir": str(directory),
        "encoding": info.orca_encoding,
        "count": len(written),
        "written": written,
        "skipped": skipped,
        "failed": failed,
    }


def pb_session_configure(
    export_encoding: str = "unicode",
    export_headers: bool = False,
    export_include_binary: bool = False,
    export_to_file: bool = False,
    export_directory: str | None = None,
    import_encoding: str = "unicode",
    debug: bool = False,
) -> dict[str, Any]:
    """`PBORCA_ConfigureSession` — raw access to the session-wide ORCA options.

    The file-based tools set and restore this themselves, so you rarely need
    it; it is here because it is part of ORCA's public API and because `debug`
    has no other entry point. Calling it with no arguments resets the session
    to ORCA's defaults.

    Careful: `export_encoding` also applies to in-memory exports, where
    anything other than `unicode` silently mangles the returned string. The
    in-memory tools refuse to run while such a configuration is in effect.
    """
    session = Session.instance()
    try:
        applied = session.configure(
            export_encoding=export_encoding,
            export_headers=export_headers,
            export_include_binary=export_include_binary,
            export_to_file=export_to_file,
            export_directory=export_directory,
            import_encoding=import_encoding,
            debug=debug,
        )
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except ValueError as exc:
        return _error("PB_ORCA_MCP_INVALIDARGS", str(exc))
    except OrcaError as exc:
        return {"error": exc.to_dict()}
    return {"ok": True, "config": applied}


def sync_entry(
    session: Session,
    info: ws.WorkspaceInfo,
    entry_name: str,
    entry_type: str,
    sync_sources: str,
) -> dict[str, Any]:
    """Rewrite one entry's projection file after the `.pbl` changed.

    Shared by every tool that writes to a `.pbl`, so "the text form followed
    the binary" is a property of the server rather than of each call site.
    Returns the `synced_files` / `sync` fields to merge into a tool response;
    a project with no projection syncs nothing and says so.
    """
    if sync_sources == "never":
        return {"synced_files": [], "sync": "never"}
    if info.mode != "ws_objects" or info.sources is None:
        return {"synced_files": [], "sync": "not_applicable"}
    try:
        path, _size = session.library_entry_export_to_file(
            info.sources.lib_path,
            entry_name,
            entry_type,
            info.sources.source_dir,
            encoding=info.orca_encoding,
        )
    except (OrcaError, SessionStateError, ValueError, OSError) as exc:
        return {"synced_files": [], "sync": "failed", "sync_error": str(exc)}
    return {"synced_files": [path], "sync": "ok"}


def sync_removal(
    info: ws.WorkspaceInfo, entry_name: str, entry_type: str, sync_sources: str
) -> dict[str, Any]:
    """Delete one entry's projection file after the entry left the `.pbl`.

    The mirror image of `sync_entry` for deletes and moves: without it the
    `.sr*` file survives its object and the next Refresh resurrects the
    deleted entry from the stale text.
    """
    if sync_sources == "never":
        return {"removed_files": [], "sync": "never"}
    if info.mode != "ws_objects" or info.sources is None:
        return {"removed_files": [], "sync": "not_applicable"}
    try:
        extension = extension_for_entry_type(entry_type)
    except ValueError:
        return {"removed_files": [], "sync": "not_applicable"}
    target = Path(info.sources.source_dir) / f"{entry_name}.{extension}"
    if not target.exists():
        return {"removed_files": [], "sync": "ok"}
    try:
        target.unlink()
    except OSError as exc:
        return {"removed_files": [], "sync": "failed", "sync_error": str(exc)}
    return {"removed_files": [str(target)], "sync": "ok"}


def _require_session(session: Session, op: str) -> None:
    """Fail before any directory is created when there is no session to export from."""
    if not session.is_open:
        raise SessionStateError(f"Cannot {op}: no ORCA session open")


def _resolve_dest(info: ws.WorkspaceInfo, dest_dir: str | None) -> tuple[Path, bool]:
    """Pick the export destination and say whether it is the source of truth."""
    if dest_dir:
        return Path(dest_dir), False
    if info.mode == "ws_objects" and info.sources is not None:
        return Path(info.sources.source_dir), True
    return Path(info.work_dir), False


def _ensure_dir(directory: Path, info: ws.WorkspaceInfo, is_projection: bool) -> None:
    """Create the export directory — ORCA needs it to exist and will not make it.

    A freshly created working directory gets a self-ignoring `.gitignore`, so
    scratch copies never show up in `git status`. The projection directory is
    the opposite: its contents are meant to be committed, so it is left alone.
    """
    existed = directory.is_dir()
    directory.mkdir(parents=True, exist_ok=True)
    if existed or is_projection or info.git_root is None:
        return
    if directory.resolve() != Path(info.work_dir).resolve():
        return
    marker = directory / ".gitignore"
    if not marker.exists():
        marker.write_text(_WORK_DIR_GITIGNORE, encoding="utf-8")


def _error(name: str, message: str) -> dict[str, Any]:
    return {"error": {"code": -1, "name": name, "message": message}}
