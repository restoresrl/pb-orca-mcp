"""Tokenizer state-machine tests.

Two invariants drive every test:

- **Reconstructibility**: ``"".join(t.text for t in tokenize(s)) == s``.
  The formatter relies on this for idempotency.
- **Opaqueness**: text inside string and comment tokens is preserved
  verbatim — no inner tokenization, no transformation.
"""

from __future__ import annotations

import pytest

from pb_orca_mcp.format.lexer import Token, TokenKind, tokenize


def _kinds(source: str) -> list[TokenKind]:
    return [t.kind for t in tokenize(source)]


def _texts(source: str) -> list[str]:
    return [t.text for t in tokenize(source)]


class TestReconstructibility:
    """Every input must be exactly reproducible by joining token texts."""

    @pytest.mark.parametrize(
        "source",
        [
            "",
            "x",
            "integer li = 5",
            "if a > b then return\r\n",
            "// comment\r\nif a then\r\nend if\r\n",
            "/* block\r\n comment */",
            '"hello ~r~n world"',
            'string ls = "a"  +  "b"',
            "li_count++\r\nNext",
            "a-1",
            "a - 1",
            "1.5e-3",
            "n_foo.integer = 1",
            "  \t  leading mixed",
        ],
    )
    def test_join_text_equals_input(self, source: str) -> None:
        assert "".join(t.text for t in tokenize(source)) == source


class TestWordsAndNumbers:
    def test_simple_identifier(self) -> None:
        toks = list(tokenize("integer"))
        assert toks == [Token(TokenKind.WORD, "integer", 0)]

    def test_identifier_with_dollar_hash_percent(self) -> None:
        # PB allows $, #, % inside identifiers (legacy hungarian-like
        # suffixes still occur in the wild).
        assert _kinds("of_get_$count#tot%") == [TokenKind.WORD]

    def test_integer_literal(self) -> None:
        assert _kinds("42") == [TokenKind.NUMBER]

    def test_decimal_literal(self) -> None:
        assert _texts("3.14") == ["3.14"]

    def test_e_notation(self) -> None:
        assert _texts("1.5e-3") == ["1.5e-3"]

    def test_member_access_keeps_dot_separate(self) -> None:
        # foo.bar → WORD . WORD (no glued token).
        kinds = _kinds("foo.bar")
        assert kinds == [TokenKind.WORD, TokenKind.OP, TokenKind.WORD]

    def test_e_without_digits_does_not_consume(self) -> None:
        # `1e` alone is just a number followed by an identifier.
        toks = list(tokenize("1ex"))
        assert toks[0].text == "1"
        assert toks[1].kind == TokenKind.WORD
        assert toks[1].text == "ex"


class TestStrings:
    def test_simple_double_quoted(self) -> None:
        toks = list(tokenize('"hello"'))
        assert len(toks) == 1
        assert toks[0].kind == TokenKind.STRING
        assert toks[0].text == '"hello"'

    def test_simple_single_quoted(self) -> None:
        toks = list(tokenize("'hello'"))
        assert toks[0].kind == TokenKind.STRING
        assert toks[0].text == "'hello'"

    def test_tilde_escape_protects_inner_quote(self) -> None:
        # ~" is a PB escape for an embedded double-quote.
        toks = list(tokenize('"a~"b"'))
        assert toks[0].kind == TokenKind.STRING
        assert toks[0].text == '"a~"b"'

    def test_doubled_quote_is_escape(self) -> None:
        toks = list(tokenize('"abc""def"'))
        assert toks[0].kind == TokenKind.STRING
        assert toks[0].text == '"abc""def"'

    def test_keyword_inside_string_is_part_of_string(self) -> None:
        # The `if` is inside a string literal — must not become a WORD.
        toks = list(tokenize('"if then end if"'))
        assert len(toks) == 1
        assert toks[0].kind == TokenKind.STRING

    def test_unterminated_string_stops_at_newline(self) -> None:
        toks = list(tokenize('"abc\r\nrest'))
        assert toks[0].kind == TokenKind.STRING
        assert toks[0].text == '"abc'
        assert toks[1].kind == TokenKind.NEWLINE


class TestComments:
    def test_line_comment_to_end_of_line(self) -> None:
        toks = list(tokenize("// hi\r\n"))
        assert toks[0].kind == TokenKind.COMMENT
        assert toks[0].text == "// hi"
        assert toks[1].kind == TokenKind.NEWLINE

    def test_quote_inside_line_comment_is_not_a_string(self) -> None:
        toks = list(tokenize('// "not a string\r\n'))
        assert toks[0].kind == TokenKind.COMMENT
        assert toks[0].text == '// "not a string'

    def test_block_comment_can_span_lines(self) -> None:
        src = "/* spanning\r\nmultiple lines */"
        toks = list(tokenize(src))
        assert len(toks) == 1
        assert toks[0].kind == TokenKind.COMMENT
        assert toks[0].text == src

    def test_quote_inside_block_comment_is_not_a_string(self) -> None:
        src = '/* with "quote" inside */'
        toks = list(tokenize(src))
        assert len(toks) == 1
        assert toks[0].kind == TokenKind.COMMENT


class TestOperators:
    @pytest.mark.parametrize(
        "op", ["<=", ">=", "<>", "+=", "-=", "*=", "/=", "::"]
    )
    def test_two_char_ops_recognised(self, op: str) -> None:
        toks = list(tokenize(op))
        assert toks == [Token(TokenKind.OP, op, 0)]

    def test_lt_then_neq_pair(self) -> None:
        # `<<` is two single < ops.
        kinds = _kinds("<<")
        assert kinds == [TokenKind.OP, TokenKind.OP]


class TestWhitespaceAndNewlines:
    def test_crlf_emitted_as_single_token(self) -> None:
        toks = list(tokenize("\r\n"))
        assert toks == [Token(TokenKind.NEWLINE, "\r\n", 0)]

    def test_lone_cr_and_lone_lf_each_one_token(self) -> None:
        assert _texts("\r") == ["\r"]
        assert _texts("\n") == ["\n"]

    def test_spaces_and_tabs_grouped(self) -> None:
        toks = list(tokenize("  \t  x"))
        assert toks[0].kind == TokenKind.WHITESPACE
        assert toks[0].text == "  \t  "
        assert toks[1].kind == TokenKind.WORD
