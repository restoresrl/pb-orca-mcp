"""Token-based PowerScript body formatter.

Public API:

- ``format_powerscript(source, config) -> str``: apply the configured
  normalization rules to a PowerScript entry body and return the
  formatted source. Idempotent.
- ``FormatConfig``: dataclass holding the per-workspace style choices,
  loaded from ``.pb-format.toml`` or constructed programmatically.
- ``discover_config(start)``: walking-up lookup for ``.pb-format.toml``.
- ``detect_workspace_style(root)`` + ``write_config_file(...)``: helpers
  behind the ``pb-format detect`` CLI.

The engine is deliberately token-based (no AST). It owns four
invariants — indent, line endings, keyword case, operator spacing —
chosen so they can be enforced without parsing PowerScript. Anything
beyond that scope (blank-line policy, continuation-line alignment,
identifier rewrites) is explicitly deferred to a future AST-aware
Layer-3.
"""

from __future__ import annotations

from pb_orca_mcp.format.config import (
    CONFIG_FILENAME,
    FormatConfig,
    IndentStyle,
    KeywordCase,
    LineEndings,
    discover_config,
)
from pb_orca_mcp.format.detect import (
    SOURCE_EXTENSIONS,
    DetectionResult,
    detect_workspace_style,
    write_config_file,
)
from pb_orca_mcp.format.lexer import Token, TokenKind, tokenize
from pb_orca_mcp.format.normalizer import format_powerscript

__all__ = [
    "CONFIG_FILENAME",
    "SOURCE_EXTENSIONS",
    "DetectionResult",
    "FormatConfig",
    "IndentStyle",
    "KeywordCase",
    "LineEndings",
    "Token",
    "TokenKind",
    "detect_workspace_style",
    "discover_config",
    "format_powerscript",
    "tokenize",
    "write_config_file",
]
