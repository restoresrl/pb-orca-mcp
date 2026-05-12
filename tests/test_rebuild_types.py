"""Tests for the PBORCA_REBLD_TYPE name↔int helpers and compile-level mapping."""

from __future__ import annotations

import pytest

from pb_orca_mcp.orca.constants import (
    PBORCA_3PASS,
    PBORCA_FULL_REBUILD,
    PBORCA_INCREMENTAL_REBUILD,
    PBORCA_MIGRATE,
    REBUILD_TYPE_NAMES,
    compile_level_to_name,
    rebuild_type_from_name,
)


def test_rebuild_type_round_trip() -> None:
    assert rebuild_type_from_name("full") == PBORCA_FULL_REBUILD == 0
    assert rebuild_type_from_name("incremental") == PBORCA_INCREMENTAL_REBUILD == 1
    assert rebuild_type_from_name("migrate") == PBORCA_MIGRATE == 2
    assert rebuild_type_from_name("3pass") == PBORCA_3PASS == 3


def test_rebuild_type_case_insensitive() -> None:
    assert rebuild_type_from_name("FULL") == PBORCA_FULL_REBUILD
    assert rebuild_type_from_name("Incremental") == PBORCA_INCREMENTAL_REBUILD


def test_rebuild_type_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown rebuild type"):
        rebuild_type_from_name("rebuild")


def test_rebuild_type_names_complete() -> None:
    assert set(REBUILD_TYPE_NAMES.values()) == {"full", "incremental", "migrate", "3pass"}


def test_compile_level_to_name() -> None:
    assert compile_level_to_name(0) == "error"
    assert compile_level_to_name(1) == "warning"
    assert compile_level_to_name(2) == "information"
    assert compile_level_to_name(99) == "unknown(99)"
