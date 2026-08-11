"""Tests for the PBORCA_TYPE name↔int helpers."""

from __future__ import annotations

import pytest

from pb_orca_mcp.orca.constants import (
    ENTRY_TYPE_NAMES,
    PBORCA_APPLICATION,
    PBORCA_BINARY,
    PBORCA_USEROBJECT,
    entry_type_from_name,
    entry_type_to_name,
)


def test_round_trip_all_known_types() -> None:
    for value, name in ENTRY_TYPE_NAMES.items():
        assert entry_type_to_name(value) == name
        assert entry_type_from_name(name) == value


def test_anchor_values_from_header() -> None:
    """The C enum starts at 0 and increments. Pin two anchors so we notice
    if PB ever reorders them."""
    assert PBORCA_APPLICATION == 0
    assert PBORCA_USEROBJECT == 6
    assert PBORCA_BINARY == 11


def test_from_name_is_case_insensitive() -> None:
    assert entry_type_from_name("UserObject") == PBORCA_USEROBJECT
    assert entry_type_from_name("WINDOW") == 7


def test_from_name_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown entry type"):
        entry_type_from_name("nonexistent")


def test_to_name_fallback_for_unknown_int() -> None:
    assert entry_type_to_name(999) == "unknown(999)"


def test_powerscript_type_names_are_accepted_where_they_differ() -> None:
    """A `.srf` says `global type gettext from function_object`, and ORCA calls
    that same thing `function`.

    Anyone naming an entry type — a plan file, a person, a model — reads it off
    the source, so the PowerScript spelling is the one that turns up. Rejecting
    it stopped an unattended apply loop dead on every global-function finding,
    with an error that listed twelve valid names and not the one the file uses.
    """
    from pb_orca_mcp.orca.constants import entry_type_from_name

    assert entry_type_from_name("function_object") == entry_type_from_name("function")
    assert entry_type_from_name("FUNCTION_OBJECT") == entry_type_from_name("function")
    # Names that agree between the two vocabularies are untouched.
    for name in ("userobject", "window", "menu", "datawindow", "structure"):
        assert entry_type_from_name(name) == entry_type_from_name(name.upper())
    # And an alias appears in the error text, so the next mismatch self-documents.
    try:
        entry_type_from_name("nonsense")
    except ValueError as exc:
        assert "function_object" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
