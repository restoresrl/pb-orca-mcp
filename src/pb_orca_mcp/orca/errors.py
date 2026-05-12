"""Pythonic exceptions for ORCA errors.

ORCA functions return non-zero codes on failure. This module wraps them
into `OrcaError(code, name, message)` so tool implementations can `raise`
instead of checking return values, and so the MCP layer can surface
human-readable error payloads.
"""

from __future__ import annotations

from pb_orca_mcp.orca.constants import ORCA_ERROR_NAMES


class OrcaError(Exception):
    """Raised when an ORCA call returns a non-zero status."""

    def __init__(self, code: int, name: str = "", message: str = "") -> None:
        self.code = code
        self.name = name or ORCA_ERROR_NAMES.get(code, f"PBORCA_UNKNOWN({code})")
        self.message = message
        suffix = f": {message}" if message else ""
        super().__init__(f"ORCA error {code} ({self.name}){suffix}")

    @classmethod
    def from_code(cls, code: int, message: str = "") -> OrcaError:
        """Build an `OrcaError` from a raw ORCA return code, resolving the symbolic name."""
        return cls(code=code, name=ORCA_ERROR_NAMES.get(code, ""), message=message)

    def to_dict(self) -> dict[str, int | str]:
        """Serialize for the MCP tool error payload shape (see PLAN §"Schema input/output")."""
        return {"code": self.code, "name": self.name, "message": self.message}
