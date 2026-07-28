"""MCP tools for PBL library operations.

Wraps `pb_orca_mcp.orca.session.Session.library_*` methods with the
JSON-friendly input/output documented in `docs/tools.md`. Errors come back
as `{"error": {"code","name","message"}}`.

Tools exposed:
- `pb_library_create`: create a new PBL with an optional comment.
- `pb_library_delete`: delete a PBL.
- `pb_library_directory`: list entries; optional client-side `entry_type` filter.
- `pb_library_entry_information`: object metadata for a single entry.
- `pb_library_entry_export`: export an entry's source as a string, in memory.
- `pb_library_entry_delete`: delete an entry from a PBL.
- `pb_library_entry_move`: move an entry between PBLs.
- `pb_library_comment_modify`: change the PBL-level comment.

The two mutating tools keep the project's `ws_objects/` text projection in
step (`sync_sources`), for the same reason the compile tools do: an object that
leaves the `.pbl` but not the text tree comes back on the next Refresh.

ORCA exposes `PBORCA_LibraryEntryCopy` too; it is intentionally not
surfaced — its semantics overlap with `move` + `export` + import.
There is **no** `PBORCA_LibraryEntryCommentModify` in ORCA (verified
against `PBORCA.H` PB 19/22/25); to change an entry's comment, re-import
it via `pb_compile_entry_import` with the new comment.
"""

from __future__ import annotations

from typing import Any

from pb_orca_mcp import workspace as ws
from pb_orca_mcp.orca.errors import OrcaError
from pb_orca_mcp.orca.session import Session, SessionStateError
from pb_orca_mcp.tools.source import SYNC_MODES, sync_entry, sync_removal


def pb_library_create(lib_path: str, comments: str = "") -> dict[str, Any]:
    """Create an empty PBL at `lib_path`."""
    return _run(lambda s: s.library_create(lib_path, comments), ok={"lib_path": lib_path})


def pb_library_delete(lib_path: str) -> dict[str, Any]:
    """Delete the PBL at `lib_path`.

    Deliberately does **not** remove the library's `ws_objects/<lib>.pbl.src/`
    directory. Dropping a whole tree of version-controlled source as a side
    effect of one call is a worse failure than leaving it orphaned, and the
    orphan is visible in `git status`. Remove it yourself when the deletion is
    intentional.
    """
    return _run(lambda s: s.library_delete(lib_path), ok={"lib_path": lib_path})


def pb_library_comment_modify(lib_path: str, comments: str) -> dict[str, Any]:
    """Update the comment on the PBL at `lib_path`."""
    return _run(
        lambda s: s.library_comment_modify(lib_path, comments),
        ok={"lib_path": lib_path, "comments": comments},
    )


def pb_library_directory(lib_path: str, entry_type: str = "any") -> dict[str, Any]:
    """List entries in the PBL.

    `entry_type` is filtered Python-side after the callback delivers every
    entry — ORCA's `LibraryDirectory` itself has no type filter.
    """
    session = Session.instance()
    try:
        comment, entries = session.library_directory(lib_path)
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except OrcaError as exc:
        return {"error": exc.to_dict()}

    if entry_type != "any":
        wanted = entry_type.lower()
        entries = [e for e in entries if e["type"] == wanted]
    return {
        "lib_path": lib_path,
        "lib_comment": comment,
        "entry_type": entry_type,
        "count": len(entries),
        "entries": entries,
    }


def pb_library_entry_information(lib_path: str, entry_name: str, entry_type: str) -> dict[str, Any]:
    """Metadata for a single entry."""
    session = Session.instance()
    try:
        return session.library_entry_information(lib_path, entry_name, entry_type)
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except ValueError as exc:
        return _error("PB_ORCA_MCP_INVALIDARGS", str(exc))
    except OrcaError as exc:
        return {"error": exc.to_dict()}


def pb_library_entry_export(lib_path: str, entry_name: str, entry_type: str) -> dict[str, Any]:
    """Export the source of a single entry as a string, in memory.

    Returns the object **body**: no `$PBExportHeader$` line, no
    `$PBExportComments$` line, since those belong to the on-disk file format
    rather than to the object. Use `pb_object_export_file` when you want the
    file — it is what an agent edits, and ORCA writes it byte-identical to the
    PB IDE.
    """
    session = Session.instance()
    try:
        source = session.library_entry_export(lib_path, entry_name, entry_type)
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except ValueError as exc:
        return _error("PB_ORCA_MCP_INVALIDARGS", str(exc))
    except OrcaError as exc:
        return {"error": exc.to_dict()}
    return {
        "lib_path": lib_path,
        "entry_name": entry_name,
        "entry_type": entry_type,
        "source": source,
    }


def pb_library_entry_delete(
    lib_path: str, entry_name: str, entry_type: str, sync_sources: str = "auto"
) -> dict[str, Any]:
    """Delete a single entry from a PBL, and its text projection file with it.

    Leaving the `.sr*` behind would be worse than a cosmetic leak: the next
    Refresh reads the text tree back into the `.pbl` and resurrects the object
    you just deleted. Pass `sync_sources="never"` to keep the file.
    """
    if sync_sources not in SYNC_MODES:
        return _error(
            "PB_ORCA_MCP_INVALIDARGS",
            f"sync_sources must be one of {SYNC_MODES}, got {sync_sources!r}",
        )
    session = Session.instance()
    try:
        info = ws.describe(lib_path)
        session.library_entry_delete(lib_path, entry_name, entry_type)
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except ValueError as exc:
        return _error("PB_ORCA_MCP_INVALIDARGS", str(exc))
    except OrcaError as exc:
        return {"error": exc.to_dict()}
    return {
        "ok": True,
        "lib_path": lib_path,
        "entry_name": entry_name,
        "entry_type": entry_type,
        **sync_removal(info, entry_name, entry_type, sync_sources),
    }


def pb_library_entry_move(
    source_lib: str,
    dest_lib: str,
    entry_name: str,
    entry_type: str,
    sync_sources: str = "auto",
) -> dict[str, Any]:
    """Move an entry between PBLs, moving its text projection file too.

    The projection follows the object: the `.sr*` is removed from the source
    library's directory and written fresh into the destination's, so both
    libraries stay consistent with their text form.
    """
    if sync_sources not in SYNC_MODES:
        return _error(
            "PB_ORCA_MCP_INVALIDARGS",
            f"sync_sources must be one of {SYNC_MODES}, got {sync_sources!r}",
        )
    session = Session.instance()
    try:
        source_info = ws.describe(source_lib)
        dest_info = ws.describe(dest_lib)
        session.library_entry_move(source_lib, dest_lib, entry_name, entry_type)
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except ValueError as exc:
        return _error("PB_ORCA_MCP_INVALIDARGS", str(exc))
    except OrcaError as exc:
        return {"error": exc.to_dict()}
    removed = sync_removal(source_info, entry_name, entry_type, sync_sources)
    added = sync_entry(session, dest_info, entry_name, entry_type, sync_sources)
    return {
        "ok": True,
        "source_lib": source_lib,
        "dest_lib": dest_lib,
        "entry_name": entry_name,
        "entry_type": entry_type,
        "removed_files": removed["removed_files"],
        "synced_files": added["synced_files"],
        "sync": added["sync"],
    }


def _run(action: Any, *, ok: dict[str, Any]) -> dict[str, Any]:
    session = Session.instance()
    try:
        action(session)
    except SessionStateError as exc:
        return _error("PB_ORCA_MCP_STATEERROR", str(exc))
    except ValueError as exc:
        return _error("PB_ORCA_MCP_INVALIDARGS", str(exc))
    except OrcaError as exc:
        return {"error": exc.to_dict()}
    return {"ok": True, **ok}


def _error(name: str, message: str) -> dict[str, Any]:
    return {"error": {"code": -1, "name": name, "message": message}}
