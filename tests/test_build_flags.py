"""Tests for build-flag name↔int helpers and reftype mapping."""

from __future__ import annotations

import pytest

from pb_orca_mcp.orca.constants import (
    PBORCA_ERROR_CONTEXT,
    PBORCA_MACHINE_CODE,
    PBORCA_MACHINE_CODE_OPT_SPEED,
    PBORCA_REFTYPE_OPEN,
    PBORCA_REFTYPE_SIMPLE,
    PBORCA_TRACE_INFO,
    PBORCA_X64,
    build_flags_from_names,
    reftype_to_name,
)


def test_flags_empty_or_none_is_zero() -> None:
    assert build_flags_from_names(None) == 0
    assert build_flags_from_names([]) == 0


def test_flags_or_fold() -> None:
    result = build_flags_from_names(
        ["machine_code", "optimize_speed", "trace_info", "error_context"]
    )
    expected = (
        PBORCA_MACHINE_CODE
        | PBORCA_MACHINE_CODE_OPT_SPEED
        | PBORCA_TRACE_INFO
        | PBORCA_ERROR_CONTEXT
    )
    assert result == expected


def test_flags_case_insensitive() -> None:
    assert build_flags_from_names(["Machine_Code", "X64"]) == (PBORCA_MACHINE_CODE | PBORCA_X64)


def test_flags_unknown_raises_with_valid_list() -> None:
    with pytest.raises(ValueError, match="unknown build flag"):
        build_flags_from_names(["machine_code", "no_such_flag"])


def test_reftype_to_name() -> None:
    assert reftype_to_name(PBORCA_REFTYPE_SIMPLE) == "simple"
    assert reftype_to_name(PBORCA_REFTYPE_OPEN) == "open"
    assert reftype_to_name(99) == "unknown(99)"
