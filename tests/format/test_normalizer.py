"""Behavioural tests for the four MVP normalization rules.

Each rule lives in its own test class so a failure points directly at
the offending invariant. Cross-cutting concerns (interaction between
rules, idempotency) are in ``test_idempotency.py``.
"""

from __future__ import annotations

from pb_orca_mcp.format.config import FormatConfig
from pb_orca_mcp.format.normalizer import format_powerscript


def _cfg(**overrides: object) -> FormatConfig:
    """Build a FormatConfig with a base of all rules active and CRLF."""
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


class TestKeywordCase:
    def test_uppercase_keyword_folds_to_lower(self) -> None:
        out = format_powerscript("IF a THEN return\r\n", _cfg())
        assert out == "if a then return\r\n"

    def test_mixed_keyword_folds_to_lower(self) -> None:
        out = format_powerscript("If A Then Return\r\n", _cfg())
        assert out == "if A then return\r\n"

    def test_keyword_inside_string_not_touched(self) -> None:
        src = 'ls = "IF this THEN that"\r\n'
        out = format_powerscript(src, _cfg())
        # Only the assignment got spacing; the string body is untouched.
        assert '"IF this THEN that"' in out

    def test_keyword_inside_line_comment_not_touched(self) -> None:
        src = "// IF this THEN that\r\n"
        out = format_powerscript(src, _cfg())
        assert out == "// IF this THEN that\r\n"

    def test_keyword_inside_block_comment_not_touched(self) -> None:
        src = "/* IF nested\r\n  THEN end */\r\n"
        out = format_powerscript(src, _cfg())
        assert "IF nested" in out
        assert "THEN end" in out

    def test_member_access_preserves_case(self) -> None:
        # `Integer` is reserved but here it's a property name on `foo`
        # — the `.` in front must prevent rewriting.
        out = format_powerscript("foo.Integer = 1\r\n", _cfg())
        assert "foo.Integer = 1" in out

    def test_scope_access_preserves_case(self) -> None:
        out = format_powerscript("u_base::Integer\r\n", _cfg())
        assert "u_base::Integer" in out

    def test_upper_case_policy(self) -> None:
        out = format_powerscript("if a then return\r\n", _cfg(keyword_case="upper"))
        assert out == "IF a THEN RETURN\r\n"

    def test_preserve_policy_keeps_case(self) -> None:
        src = "If a Then Return\r\n"
        out = format_powerscript(src, _cfg(keyword_case="preserve"))
        assert out == "If a Then Return\r\n"

    def test_non_keyword_identifier_unchanged(self) -> None:
        out = format_powerscript("ls_Foo = 1\r\n", _cfg())
        assert "ls_Foo" in out


class TestOperatorSpacing:
    def test_equals_gets_spaces(self) -> None:
        out = format_powerscript("a=1\r\n", _cfg())
        assert out == "a = 1\r\n"

    def test_existing_spaces_normalized(self) -> None:
        out = format_powerscript("a   =   1\r\n", _cfg())
        assert out == "a = 1\r\n"

    def test_binary_minus_gets_spaces(self) -> None:
        out = format_powerscript("li_x=a-1\r\n", _cfg())
        assert out == "li_x = a - 1\r\n"

    def test_unary_minus_after_equals_no_spaces(self) -> None:
        out = format_powerscript("li_x = -1\r\n", _cfg())
        assert out == "li_x = -1\r\n"

    def test_unary_minus_after_return_no_spaces(self) -> None:
        out = format_powerscript("return -1\r\n", _cfg())
        assert out == "return -1\r\n"

    def test_unary_minus_inside_parens_no_spaces(self) -> None:
        out = format_powerscript("call f(-5)\r\n", _cfg())
        assert "f(-5)" in out

    def test_compound_assignment(self) -> None:
        out = format_powerscript("a+=1\r\n", _cfg())
        assert out == "a += 1\r\n"

    def test_less_than_or_equal(self) -> None:
        out = format_powerscript("if a<=b then return\r\n", _cfg())
        assert "a <= b" in out

    def test_not_equal_token(self) -> None:
        out = format_powerscript("if a<>b then return\r\n", _cfg())
        assert "a <> b" in out

    def test_continuation_amp_not_spaced(self) -> None:
        # `&` at EOL is a continuation marker, not a binary operator.
        src = "string ls = ~\r\n  &\r\n  \"continued\"\r\n"
        out = format_powerscript(src, _cfg())
        assert "& " not in out
        assert " &" not in out.replace(" &\r\n", "")  # tolerate "  &\r\n"

    def test_spacing_disabled_keeps_source_as_is(self) -> None:
        out = format_powerscript("a=1\r\n", _cfg(spaces_around_operators=False))
        assert out == "a=1\r\n"

    def test_no_trailing_space_before_newline(self) -> None:
        # `a = ` at EOL must not have a synthesized trailing space.
        # (Unusual but possible if the source has `a =\r\n  1`.)
        src = "a =\r\n  1\r\n"
        out = format_powerscript(src, _cfg())
        assert "= \r\n" not in out
        assert "=\r\n" in out


class TestIndent:
    def test_spaces_to_tabs(self) -> None:
        src = "    a = 1\r\n        b = 2\r\n"
        out = format_powerscript(src, _cfg(indent_style="tab", tab_width=4))
        assert out == "\ta = 1\r\n\t\tb = 2\r\n"

    def test_tabs_to_spaces(self) -> None:
        src = "\ta = 1\r\n\t\tb = 2\r\n"
        out = format_powerscript(src, _cfg(indent_style="spaces", indent_spaces=2))
        assert out == "  a = 1\r\n    b = 2\r\n"

    def test_tab_residue_preserved(self) -> None:
        # 6 spaces under tab_width=4 → 1 tab + 2 residue spaces.
        src = "      a = 1\r\n"
        out = format_powerscript(src, _cfg(indent_style="tab", tab_width=4))
        assert out == "\t  a = 1\r\n"

    def test_mixed_indent_normalized(self) -> None:
        src = "\t    a = 1\r\n"  # 1 tab + 4 spaces
        out = format_powerscript(src, _cfg(indent_style="tab", tab_width=4))
        assert out == "\t\ta = 1\r\n"


class TestLineEndings:
    def test_lf_becomes_crlf(self) -> None:
        out = format_powerscript("a = 1\nb = 2\n", _cfg())
        assert out == "a = 1\r\nb = 2\r\n"

    def test_mixed_endings_normalized(self) -> None:
        out = format_powerscript("a\r\nb\rc\nd", _cfg())
        assert out == "a\r\nb\r\nc\r\nd"

    def test_crlf_in_block_comment_normalized(self) -> None:
        # LF inside block comment body should also become CRLF.
        out = format_powerscript("/* one\ntwo */\n", _cfg())
        assert out == "/* one\r\ntwo */\r\n"

    def test_lf_policy_collapses_crlf_to_lf(self) -> None:
        out = format_powerscript("a\r\nb\r\n", _cfg(line_endings="lf"))
        assert out == "a\nb\n"
