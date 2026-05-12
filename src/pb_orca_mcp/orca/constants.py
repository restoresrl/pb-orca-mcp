"""ORCA return codes and enum constants from `PBORCA.H`.

`PBORCA_OK = 0`; non-zero values are errors. `ORCA_ERROR_NAMES` maps a
return code to the symbolic name from the C header — used by the error
decoder so callers see `PBORCA_OBJNOTFOUND` instead of `-3`.

Verified identical across PB 19/22/25 (single source of truth: each
install's `<install>\\SDK\\ORCA\\pborca.h`).
"""

from __future__ import annotations

PBORCA_OK = 0
PBORCA_INVALIDPARMS = -1
PBORCA_DUPOPERATION = -2
PBORCA_OBJNOTFOUND = -3
PBORCA_BADLIBRARY = -4
PBORCA_LIBLISTNOTSET = -5
PBORCA_LIBNOTINLIST = -6
PBORCA_LIBIOERROR = -7
PBORCA_OBJEXISTS = -8
PBORCA_INVALIDNAME = -9
PBORCA_BUFFERTOOSMALL = -10
PBORCA_COMPERROR = -11
PBORCA_LINKERROR = -12
PBORCA_CURRAPPLNOTSET = -13
PBORCA_OBJHASNOANCS = -14
PBORCA_OBJHASNOREFS = -15
PBORCA_PBDCOUNTERROR = -16
PBORCA_PBDCREATERROR = -17
PBORCA_CHECKOUTERROR = -18
PBORCA_CBCREATEERROR = -19
PBORCA_CBINITERROR = -20
PBORCA_CBBUILDERROR = -21
PBORCA_SCCFAILURE = -22
PBORCA_REGREADERROR = -23
PBORCA_LOADDLLFAILED = -24
PBORCA_SCCINITFAILED = -25
PBORCA_OPENPROJFAILED = -26
PBORCA_TARGETNOTFOUND = -27
PBORCA_TARGETREADERR = -28
PBORCA_GETINTERFACEERROR = -29
PBORCA_IMPORTONLY_REQ = -30
PBORCA_GETCONNECT_REQ = -31
PBORCA_PBCFILE_REQ = -32
PBORCA_DBCSERROR = -33

ORCA_ERROR_NAMES: dict[int, str] = {
    PBORCA_OK: "PBORCA_OK",
    PBORCA_INVALIDPARMS: "PBORCA_INVALIDPARMS",
    PBORCA_DUPOPERATION: "PBORCA_DUPOPERATION",
    PBORCA_OBJNOTFOUND: "PBORCA_OBJNOTFOUND",
    PBORCA_BADLIBRARY: "PBORCA_BADLIBRARY",
    PBORCA_LIBLISTNOTSET: "PBORCA_LIBLISTNOTSET",
    PBORCA_LIBNOTINLIST: "PBORCA_LIBNOTINLIST",
    PBORCA_LIBIOERROR: "PBORCA_LIBIOERROR",
    PBORCA_OBJEXISTS: "PBORCA_OBJEXISTS",
    PBORCA_INVALIDNAME: "PBORCA_INVALIDNAME",
    PBORCA_BUFFERTOOSMALL: "PBORCA_BUFFERTOOSMALL",
    PBORCA_COMPERROR: "PBORCA_COMPERROR",
    PBORCA_LINKERROR: "PBORCA_LINKERROR",
    PBORCA_CURRAPPLNOTSET: "PBORCA_CURRAPPLNOTSET",
    PBORCA_OBJHASNOANCS: "PBORCA_OBJHASNOANCS",
    PBORCA_OBJHASNOREFS: "PBORCA_OBJHASNOREFS",
    PBORCA_PBDCOUNTERROR: "PBORCA_PBDCOUNTERROR",
    PBORCA_PBDCREATERROR: "PBORCA_PBDCREATERROR",
    PBORCA_CHECKOUTERROR: "PBORCA_CHECKOUTERROR",
    PBORCA_CBCREATEERROR: "PBORCA_CBCREATEERROR",
    PBORCA_CBINITERROR: "PBORCA_CBINITERROR",
    PBORCA_CBBUILDERROR: "PBORCA_CBBUILDERROR",
    PBORCA_SCCFAILURE: "PBORCA_SCCFAILURE",
    PBORCA_REGREADERROR: "PBORCA_REGREADERROR",
    PBORCA_LOADDLLFAILED: "PBORCA_LOADDLLFAILED",
    PBORCA_SCCINITFAILED: "PBORCA_SCCINITFAILED",
    PBORCA_OPENPROJFAILED: "PBORCA_OPENPROJFAILED",
    PBORCA_TARGETNOTFOUND: "PBORCA_TARGETNOTFOUND",
    PBORCA_TARGETREADERR: "PBORCA_TARGETREADERR",
    PBORCA_GETINTERFACEERROR: "PBORCA_GETINTERFACEERROR",
    PBORCA_IMPORTONLY_REQ: "PBORCA_IMPORTONLY_REQ",
    PBORCA_GETCONNECT_REQ: "PBORCA_GETCONNECT_REQ",
    PBORCA_PBCFILE_REQ: "PBORCA_PBCFILE_REQ",
    PBORCA_DBCSERROR: "PBORCA_DBCSERROR",
}

PBORCA_MSGBUFFER = 256
"""Suggested buffer size for `PBORCA_SessionGetError` (from `PBORCA.H`)."""

PBORCA_MAXCOMMENT = 255
"""Max library/entry comment length (from `PBORCA.H`). Used by library tools (phase 4)."""

# ORCA entry types (`enum pborca_type` in PBORCA.H). Order matters: values are
# implicit-incrementing C enum integers starting at 0.
PBORCA_APPLICATION = 0
PBORCA_DATAWINDOW = 1
PBORCA_FUNCTION = 2
PBORCA_MENU = 3
PBORCA_QUERY = 4
PBORCA_STRUCTURE = 5
PBORCA_USEROBJECT = 6
PBORCA_WINDOW = 7
PBORCA_PIPELINE = 8
PBORCA_PROJECT = 9
PBORCA_PROXYOBJECT = 10
PBORCA_BINARY = 11

ENTRY_TYPE_NAMES: dict[int, str] = {
    PBORCA_APPLICATION: "application",
    PBORCA_DATAWINDOW: "datawindow",
    PBORCA_FUNCTION: "function",
    PBORCA_MENU: "menu",
    PBORCA_QUERY: "query",
    PBORCA_STRUCTURE: "structure",
    PBORCA_USEROBJECT: "userobject",
    PBORCA_WINDOW: "window",
    PBORCA_PIPELINE: "pipeline",
    PBORCA_PROJECT: "project",
    PBORCA_PROXYOBJECT: "proxyobject",
    PBORCA_BINARY: "binary",
}

ENTRY_TYPE_VALUES: dict[str, int] = {name: value for value, name in ENTRY_TYPE_NAMES.items()}


def entry_type_to_name(value: int) -> str:
    """Resolve a `PBORCA_TYPE` int to its string name, falling back to `unknown(N)`."""
    return ENTRY_TYPE_NAMES.get(value, f"unknown({value})")


def entry_type_from_name(name: str) -> int:
    """Resolve a string entry type name to its `PBORCA_TYPE` int.

    Raises `ValueError` for unknown names (call sites validate caller input).
    """
    try:
        return ENTRY_TYPE_VALUES[name.lower()]
    except KeyError as exc:
        valid = ", ".join(sorted(ENTRY_TYPE_VALUES))
        raise ValueError(f"unknown entry type {name!r}; valid: {valid}") from exc


# Rebuild types (`enum pborca_rebuild_type` in PBORCA.H).
PBORCA_FULL_REBUILD = 0
PBORCA_INCREMENTAL_REBUILD = 1
PBORCA_MIGRATE = 2
PBORCA_3PASS = 3

REBUILD_TYPE_NAMES: dict[int, str] = {
    PBORCA_FULL_REBUILD: "full",
    PBORCA_INCREMENTAL_REBUILD: "incremental",
    PBORCA_MIGRATE: "migrate",
    PBORCA_3PASS: "3pass",
}

REBUILD_TYPE_VALUES: dict[str, int] = {name: value for value, name in REBUILD_TYPE_NAMES.items()}


def rebuild_type_from_name(name: str) -> int:
    """Resolve a string rebuild type to its `PBORCA_REBLD_TYPE` int."""
    try:
        return REBUILD_TYPE_VALUES[name.lower()]
    except KeyError as exc:
        valid = ", ".join(sorted(REBUILD_TYPE_VALUES))
        raise ValueError(f"unknown rebuild type {name!r}; valid: {valid}") from exc


# Compile-error severity (`PBORCA_COMPERR.iLevel`). Not formally specified in
# the header; this mapping reflects the conventional PB tooling values.
COMPILE_LEVEL_NAMES: dict[int, str] = {
    0: "error",
    1: "warning",
    2: "information",
}


def compile_level_to_name(level: int) -> str:
    """Map a `PBORCA_COMPERR.iLevel` int to a string severity, falling back to `unknown(N)`."""
    return COMPILE_LEVEL_NAMES.get(level, f"unknown({level})")
