"""Idempotency tests — the cornerstone invariant of the formatter.

Applying ``format_powerscript`` to its own output must yield the same
string. If this ever regresses, the engine becomes unsafe to wire into
``pb_edit_and_import`` because the first save and a no-op re-save would
disagree, producing phantom diffs.
"""

from __future__ import annotations

import pytest

from pb_orca_mcp.format.config import FormatConfig
from pb_orca_mcp.format.normalizer import format_powerscript


def _cfg(**overrides: object) -> FormatConfig:
    base = dict(
        indent_style="tab",
        indent_spaces=4,
        tab_width=4,
        keyword_case="lower",
        line_endings="crlf",
        spaces_around_operators=True,
    )
    base.update(overrides)
    return FormatConfig(**base)  # type: ignore[arg-type]


# A small but realistic sample of patterns that show up in real PB
# sources. Each is checked under three different configs.
_SAMPLES: list[str] = [
    "",
    "\r\n",
    "integer li = 5\r\n",
    "IF a > b THEN\r\n\treturn 1\r\nEND IF\r\n",
    "FOR i = 1 TO 10\r\n\tcall f(-i)\r\nNEXT\r\n",
    'ls_msg = "hello ~r~n world"\r\n',
    "// just a comment\r\n",
    "/* block\r\n   spanning\r\n   lines */\r\n",
    "n_foo.Integer = 1\r\n",  # member access shadowing
    "string ls = ~\r\n  &\r\n  \"continued\"\r\n",  # continuation
    "li = a + b * c - d / e ^ 2\r\n",
    "if a<=b and c<>d then return\r\n",
    "    a = 1\r\n        b = 2\r\n",
    "\ta = 1\r\n\t\tb = 2\r\n",
    "li_x=a-1\r\nli_y = -1\r\nli_z = -li_x\r\n",
]


_CONFIGS: list[FormatConfig] = [
    _cfg(),
    _cfg(indent_style="spaces", indent_spaces=4),
    _cfg(keyword_case="upper"),
    _cfg(spaces_around_operators=False),
]


@pytest.mark.parametrize("source", _SAMPLES)
@pytest.mark.parametrize("config", _CONFIGS)
def test_format_is_idempotent(source: str, config: FormatConfig) -> None:
    once = format_powerscript(source, config)
    twice = format_powerscript(once, config)
    assert once == twice


@pytest.mark.parametrize("config", _CONFIGS)
def test_already_formatted_source_unchanged(config: FormatConfig) -> None:
    """A source that already matches the config must be a fixed point."""
    if config.indent_style == "tab":
        canonical = (
            "if a > b then\r\n"
            "\treturn 1\r\n"
            "end if\r\n"
        )
    else:
        indent = " " * config.indent_spaces
        canonical = (
            "if a > b then\r\n"
            f"{indent}return 1\r\n"
            "end if\r\n"
        )
    if config.keyword_case == "upper":
        canonical = canonical.replace("if", "IF").replace("then", "THEN").replace(
            "return", "RETURN"
        ).replace("end IF", "END IF")
    if not config.spaces_around_operators:
        canonical = canonical.replace("a > b", "a>b")
    out = format_powerscript(canonical, config)
    assert out == canonical


def test_preserve_policy_does_not_touch_case() -> None:
    src = "If a THEN Return\r\n"
    out = format_powerscript(src, _cfg(keyword_case="preserve"))
    assert out == "If a THEN Return\r\n"


def test_string_body_byte_for_byte_identical() -> None:
    # The bytes inside the string literal must survive both passes
    # unchanged, regardless of how aggressive the surrounding rules are.
    src = 'ls = "  IF  THEN  END\tIF  ~r~n~tstuff"\r\n'
    out = format_powerscript(src, _cfg(keyword_case="upper"))
    assert '"  IF  THEN  END\tIF  ~r~n~tstuff"' in out
