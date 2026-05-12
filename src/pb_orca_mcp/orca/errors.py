"""Pythonic exceptions for ORCA errors.

ORCA functions return non-zero codes on failure. This module wraps them
into `OrcaError(code, name, message)` so tool implementations can `raise`
instead of checking return values, and so the MCP layer can surface
human-readable error payloads.

Implemented in phase 2.
"""


class OrcaError(Exception):
    """Raised when an ORCA call returns a non-zero status."""

    def __init__(self, code: int, name: str = "", message: str = "") -> None:
        self.code = code
        self.name = name
        self.message = message
        super().__init__(f"ORCA error {code} ({name}): {message}".rstrip(": "))
