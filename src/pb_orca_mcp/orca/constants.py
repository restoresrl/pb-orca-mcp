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


# On-disk source-file extension for each entry type. Convention from the
# PB IDE / SCC export: `<entry_name>.<extension>` placed under the
# `<lib>.pbl.src/` directory parallel to the `.pbl`.
ENTRY_TYPE_EXTENSIONS: dict[str, str] = {
    "application": "sra",
    "datawindow": "srd",
    "function": "srf",
    "menu": "srm",
    "pipeline": "srp",
    "query": "srq",
    "structure": "srs",
    "userobject": "sru",
    "window": "srw",
}


ENTRY_TYPE_BY_EXTENSION: dict[str, str] = {
    ext: name for name, ext in ENTRY_TYPE_EXTENSIONS.items()
}
"""Reverse of `ENTRY_TYPE_EXTENSIONS`: `"srw"` → `"window"`."""


def entry_type_for_extension(extension: str) -> str:
    """Resolve a `.sr*` file extension (with or without the dot) to an entry type name."""
    key = extension.lower().lstrip(".")
    try:
        return ENTRY_TYPE_BY_EXTENSION[key]
    except KeyError as exc:
        valid = ", ".join("." + e for e in sorted(ENTRY_TYPE_BY_EXTENSION))
        raise ValueError(
            f"{extension!r} is not a PowerBuilder source extension; valid: {valid}"
        ) from exc


def extension_for_entry_type(name: str) -> str:
    """Return the canonical `.sr*` extension for an entry type name.

    ORCA picks this extension itself when it writes a source file, so the
    mapping is only needed to *predict* the produced filename and to derive
    the entry type back from a file the caller hands us. Raises `ValueError`
    for types that have no on-disk source representation (`project`,
    `proxyobject`, `binary`).
    """
    try:
        return ENTRY_TYPE_EXTENSIONS[name.lower()]
    except KeyError as exc:
        raise ValueError(
            f"entry type {name!r} has no canonical .sr* extension "
            f"(only sources types have one: "
            f"{', '.join(sorted(ENTRY_TYPE_EXTENSIONS))})"
        ) from exc


# Source encodings (`enum pborca_encoding` in PBORCA.H). Applies to both the
# export side (`eExportEncoding`) and the import side (`eImportEncoding`) of
# `PBORCA_CONFIG_SESSION`.
PBORCA_UNICODE = 0
PBORCA_UTF8 = 1
PBORCA_HEXASCII = 2
PBORCA_ANSI_DBCS = 3

ENCODING_NAMES: dict[int, str] = {
    PBORCA_UNICODE: "unicode",
    PBORCA_UTF8: "utf8",
    PBORCA_HEXASCII: "hexascii",
    PBORCA_ANSI_DBCS: "ansi",
}

ENCODING_VALUES: dict[str, int] = {name: value for value, name in ENCODING_NAMES.items()}


def encoding_from_name(name: str) -> int:
    """Resolve an encoding name to its `PBORCA_ENCODING` int."""
    try:
        return ENCODING_VALUES[name.lower()]
    except KeyError as exc:
        valid = ", ".join(sorted(ENCODING_VALUES))
        raise ValueError(f"unknown encoding {name!r}; valid: {valid}") from exc


def encoding_to_name(value: int) -> str:
    """Map a `PBORCA_ENCODING` int to its string name."""
    return ENCODING_NAMES.get(value, f"unknown({value})")


# File-write behaviour when the export target file already exists
# (`enum pborca_clobber` in PBORCA.H).
#
# Verified against PB 22.0: only `PBORCA_CLOBBER` actually overwrites. The
# other three (including `CLOBBER_ALWAYS`, whose name suggests otherwise) leave
# the file alone and return `PBORCA_OBJEXISTS (-8)`. Re-exporting over an
# existing `.sr*` is the normal case for the ws_objects sync, so the session
# always sends `PBORCA_CLOBBER`.
PBORCA_NOCLOBBER = 0
PBORCA_CLOBBER = 1
PBORCA_CLOBBER_ALWAYS = 2
PBORCA_CLOBBER_DECIDED_BY_SYSTEM = 3


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


# Reference types (`enum pborca_reftype` in PBORCA.H).
PBORCA_REFTYPE_SIMPLE = 0
PBORCA_REFTYPE_OPEN = 1

REFTYPE_NAMES: dict[int, str] = {
    PBORCA_REFTYPE_SIMPLE: "simple",
    PBORCA_REFTYPE_OPEN: "open",
}


def reftype_to_name(value: int) -> str:
    """Map a `PBORCA_REFTYPE` int to its string name."""
    return REFTYPE_NAMES.get(value, f"unknown({value})")


# Executable / dynamic-library `lFlags` bitfield (from PBORCA.H).
# Bit 0: code generation mode (0=p-code, 1=machine-code).
PBORCA_P_CODE = 0x00000000
PBORCA_MACHINE_CODE = 0x00000001
PBORCA_MACHINE_CODE_NATIVE = 0x00000001
# Bit 4-5: debug context.
PBORCA_TRACE_INFO = 0x00000010
PBORCA_ERROR_CONTEXT = 0x00000020
# Bit 8-9: optimization.
PBORCA_MACHINE_CODE_OPT = 0x00000100
PBORCA_MACHINE_CODE_OPT_SPEED = 0x00000100
PBORCA_MACHINE_CODE_OPT_SPACE = 0x00000200
PBORCA_MACHINE_CODE_OPT_NONE = 0x00000000
# Bit 10: visual style.
PBORCA_NEW_VISUAL_STYLE_CONTROLS = 0x00000400
# Bit 11: x64 deployment.
PBORCA_X64 = 0x00000800

BUILD_FLAG_NAMES: dict[str, int] = {
    "p_code": PBORCA_P_CODE,
    "machine_code": PBORCA_MACHINE_CODE,
    "trace_info": PBORCA_TRACE_INFO,
    "error_context": PBORCA_ERROR_CONTEXT,
    "optimize_speed": PBORCA_MACHINE_CODE_OPT_SPEED,
    "optimize_space": PBORCA_MACHINE_CODE_OPT_SPACE,
    "new_visual_style": PBORCA_NEW_VISUAL_STYLE_CONTROLS,
    "x64": PBORCA_X64,
}
"""Subset of `PBORCA_*` build flags safe to expose by name in MCP tools.

p-code mode is the default (`lFlags=0`). Pocket PB targets (PPCARM/PPCX86/
SPHONE*) are intentionally omitted — they are legacy and don't apply to
modern PB development."""


def build_flags_from_names(names: list[str] | None) -> int:
    """OR-fold a list of build-flag names into a single `lFlags` int.

    `None` or empty list → `0` (p-code, no debug, no optimization).
    Raises `ValueError` on any unknown name.
    """
    if not names:
        return 0
    result = 0
    unknown: list[str] = []
    for name in names:
        key = name.lower()
        flag = BUILD_FLAG_NAMES.get(key)
        if flag is None:
            unknown.append(name)
        else:
            result |= flag
    if unknown:
        valid = ", ".join(sorted(BUILD_FLAG_NAMES))
        raise ValueError(f"unknown build flag(s): {unknown}; valid: {valid}")
    return result


# SCC (Source Code Control) constants from `PBORCA.H`.
# Field lengths (the +1 NUL terminator is included in the struct array size).
PBORCA_SCC_NAME_LEN = 31
PBORCA_SCC_USER_LEN = 31
PBORCA_SCC_PATH_LEN = 300

# `lFlags` bitmask for `PBORCA_SccSetTarget`.
PBORCA_SCC_REFRESH_ALL = 0x00000001
PBORCA_SCC_OUTOFDATE = 0x00000002
PBORCA_SCC_IMPORTONLY = 0x00000004
PBORCA_SCC_EXCLUDE_CHECKOUT = 0x00000008

SCC_REFRESH_FLAG_NAMES: dict[str, int] = {
    "refresh_all": PBORCA_SCC_REFRESH_ALL,
    "outofdate": PBORCA_SCC_OUTOFDATE,
    "importonly": PBORCA_SCC_IMPORTONLY,
    "exclude_checkout": PBORCA_SCC_EXCLUDE_CHECKOUT,
}


def scc_refresh_flags_from_names(names: list[str] | None) -> int:
    """OR-fold a list of SCC-target-flag names into a single `lFlags` int.

    `None` or empty list → `0`. Raises `ValueError` on any unknown name.
    """
    if not names:
        return 0
    result = 0
    unknown: list[str] = []
    for name in names:
        key = name.lower()
        flag = SCC_REFRESH_FLAG_NAMES.get(key)
        if flag is None:
            unknown.append(name)
        else:
            result |= flag
    if unknown:
        valid = ", ".join(sorted(SCC_REFRESH_FLAG_NAMES))
        raise ValueError(f"unknown SCC refresh flag(s): {unknown}; valid: {valid}")
    return result
