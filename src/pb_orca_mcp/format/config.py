"""Format configuration: dataclass, TOML parsing, walking-up discovery.

A workspace opts in to formatting by committing a ``.pb-format.toml``
file at (or above) the directory containing its sources. The discovery
walks upward from the source path until it finds one or hits the
filesystem root. See ``pb-format detect`` for an auto-generated starter.

Schema (current MVP):

.. code-block:: toml

    [style]
    indent = "tab"              # "tab" | "spaces:N" (N in 1..16)
    keyword_case = "lower"      # "lower" | "upper" | "preserve"
    line_endings = "crlf"       # "crlf" | "lf"
    spaces_around_operators = true
    tab_width = 4               # input tab width when converting from spaces

Forward-compatibility: unknown keys under ``[style]`` are ignored. The
``[style]`` section itself is optional — an empty file gives defaults.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - 3.10 fallback path
    import tomli as tomllib  # type: ignore[import-not-found,no-redef,unused-ignore]

IndentStyle = Literal["tab", "spaces"]
KeywordCase = Literal["lower", "upper", "preserve"]
LineEndings = Literal["crlf", "lf"]

CONFIG_FILENAME = ".pb-format.toml"


@dataclass(frozen=True)
class FormatConfig:
    """Workspace-wide style preferences.

    All fields have safe defaults so an empty file (or a missing file
    with ``format=True`` opt-in) still produces consistent output.
    """

    indent_style: IndentStyle = "tab"
    indent_spaces: int = 4  # only meaningful when indent_style == "spaces"
    tab_width: int = 4  # input tab width used when emitting tabs from spaces
    keyword_case: KeywordCase = "lower"
    line_endings: LineEndings = "crlf"
    spaces_around_operators: bool = True

    @classmethod
    def default(cls) -> FormatConfig:
        return cls()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FormatConfig:
        style_section = data.get("style", {})
        if not isinstance(style_section, dict):
            raise ValueError("'style' must be a TOML table")

        indent_style, indent_spaces = _parse_indent(style_section.get("indent", "tab"))

        kw_case_raw = style_section.get("keyword_case", "lower")
        if kw_case_raw not in ("lower", "upper", "preserve"):
            raise ValueError(
                f"keyword_case must be 'lower', 'upper', or 'preserve' (got {kw_case_raw!r})"
            )
        keyword_case: KeywordCase = kw_case_raw

        line_endings_raw = style_section.get("line_endings", "crlf")
        if line_endings_raw not in ("crlf", "lf"):
            raise ValueError(
                f"line_endings must be 'crlf' or 'lf' (got {line_endings_raw!r})"
            )
        line_endings: LineEndings = line_endings_raw

        spaces_around = style_section.get("spaces_around_operators", True)
        if not isinstance(spaces_around, bool):
            raise ValueError("spaces_around_operators must be a boolean")

        tab_width = style_section.get("tab_width", 4)
        if not isinstance(tab_width, int) or isinstance(tab_width, bool) or tab_width < 1:
            raise ValueError("tab_width must be a positive integer")

        return cls(
            indent_style=indent_style,
            indent_spaces=indent_spaces,
            tab_width=tab_width,
            keyword_case=keyword_case,
            line_endings=line_endings,
            spaces_around_operators=spaces_around,
        )

    @classmethod
    def from_path(cls, path: Path) -> FormatConfig:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
        return cls.from_dict(data)


def _parse_indent(value: object) -> tuple[IndentStyle, int]:
    if not isinstance(value, str):
        raise ValueError(f"indent must be a string (got {type(value).__name__})")
    if value == "tab":
        return "tab", 4
    if value.startswith("spaces:"):
        suffix = value.split(":", 1)[1]
        try:
            n = int(suffix)
        except ValueError as exc:
            raise ValueError(f"indent 'spaces:N' has non-integer N: {value!r}") from exc
        if n < 1 or n > 16:
            raise ValueError(f"indent 'spaces:N' must have 1 <= N <= 16 (got {n})")
        return "spaces", n
    raise ValueError(f"indent must be 'tab' or 'spaces:N' (got {value!r})")


def discover_config(start: Path) -> Path | None:
    """Walk upward from ``start`` looking for ``.pb-format.toml``.

    ``start`` may be a file (its parent is walked) or a directory.
    Returns the absolute path of the first match, or ``None`` if no
    config file exists between ``start`` and the filesystem root.
    """
    current = Path(start).resolve()
    if current.is_file():
        current = current.parent
    while True:
        candidate = current / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            return None
        current = parent
