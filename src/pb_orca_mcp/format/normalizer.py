"""Body normalizer: applies the four MVP style rules to a token stream.

All rules are individually idempotent and globally idempotent when
composed (re-running ``format_powerscript`` on its own output yields the
same string). Each rule operates only on tokens that survived the
lexer's classification, so text inside ``STRING`` and ``COMMENT`` tokens
is preserved verbatim — case and spacing transforms cannot bleed in.

Rules:

1. **Indent** — leading whitespace on each line is converted between TAB
   and ``N``-space forms. This is a 1:1 substitution, not a re-indent:
   we don't try to derive logical nesting levels (that would need an
   AST). Sub-unit residue (e.g. 2 stray spaces under ``tab_width=4``)
   is preserved.
2. **Line endings** — final pass forces every newline to ``\\r\\n`` when
   ``line_endings == "crlf"``. Applies inside block comments too; PB
   source files always store CRLF on disk.
3. **Keyword case** — ``WORD`` tokens whose lowercase form appears in
   the reserved set are folded to the configured case. Words immediately
   preceded by ``.`` or ``::`` are member or scope references and are
   left untouched (a user-defined member can legitimately share a
   keyword's spelling).
4. **Operator spacing** — binary ``=``, ``+``, ``-``, ``*``, ``/``,
   ``^``, ``<``, ``>``, ``<=``, ``>=``, ``<>`` and the compound
   assignments get exactly one space on each side. Unary ``+``/``-``
   (detected from the previous significant token's expression-start
   position) are not padded. ``&`` (line continuation) and ``,``/``;``
   (separators) are not touched.
"""

from __future__ import annotations

import re

from pb_orca_mcp.format.config import FormatConfig
from pb_orca_mcp.format.keywords import RESERVED, UNARY_PREFIX_KEYWORDS
from pb_orca_mcp.format.lexer import Token, TokenKind, tokenize

_SPACED_OPS: frozenset[str] = frozenset(
    {
        "=",
        "+",
        "-",
        "*",
        "/",
        "^",
        "<",
        ">",
        "<=",
        ">=",
        "<>",
        "+=",
        "-=",
        "*=",
        "/=",
    }
)

_POTENTIALLY_UNARY: frozenset[str] = frozenset({"+", "-"})

# Operator tokens after which the next ``+``/``-`` is unary, not binary.
# Includes the spaced ops themselves (``a = -5``), parens / brackets /
# separators (``f(-5)``, ``a[-1]``, ``foo, -2``), and continuation ``&``.
_EXPRESSION_START_OPS: frozenset[str] = frozenset(
    {
        "(",
        "[",
        "{",
        ",",
        ";",
        "=",
        "+",
        "-",
        "*",
        "/",
        "^",
        "<",
        ">",
        "<=",
        ">=",
        "<>",
        "+=",
        "-=",
        "*=",
        "/=",
        "&",
        "::",
    }
)

_NEWLINE_RE = re.compile(r"\r\n?|\n")


def format_powerscript(source: str, config: FormatConfig) -> str:
    """Apply the configured rules to a PowerScript body and return it.

    ``source`` is the entry body only: any ``$PBExportHeader$`` /
    ``$PBExportComments$`` lines are the caller's responsibility
    (``pb_edit_and_import`` rebuilds them upstream from this call).
    """
    tokens = list(tokenize(source))
    rendered = _render(tokens, config)
    if config.line_endings == "crlf":
        rendered = _NEWLINE_RE.sub("\r\n", rendered)
    else:
        rendered = _NEWLINE_RE.sub("\n", rendered)
    return rendered


def _render(tokens: list[Token], config: FormatConfig) -> str:
    out: list[str] = []
    prev_sig: Token | None = None
    at_line_start = True
    i = 0
    n = len(tokens)

    while i < n:
        tok = tokens[i]

        if tok.kind == TokenKind.NEWLINE:
            out.append(tok.text)
            at_line_start = True
            i += 1
            continue

        if at_line_start and tok.kind == TokenKind.WHITESPACE:
            out.append(_transform_indent(tok.text, config))
            i += 1
            continue

        if tok.kind == TokenKind.WHITESPACE:
            out.append(tok.text)
            i += 1
            continue

        if (
            tok.kind == TokenKind.OP
            and tok.text in _SPACED_OPS
            and config.spaces_around_operators
            and not (tok.text in _POTENTIALLY_UNARY and _is_unary_context(prev_sig))
        ):
            _strip_trailing_inline_whitespace(out)
            out.append(" ")
            out.append(tok.text)
            # Trailing space — but skip if the next non-whitespace token
            # is a NEWLINE, to avoid emitting trailing whitespace at EOL.
            j = i + 1
            if j < n and tokens[j].kind == TokenKind.WHITESPACE:
                j += 1
            if j >= n or tokens[j].kind != TokenKind.NEWLINE:
                out.append(" ")
            prev_sig = tok
            at_line_start = False
            # Consume the next whitespace (if any) — we just synthesized
            # our own trailing space.
            if i + 1 < n and tokens[i + 1].kind == TokenKind.WHITESPACE:
                i += 2
            else:
                i += 1
            continue

        if tok.kind == TokenKind.WORD:
            out.append(_apply_keyword_case(tok.text, prev_sig, config))
            prev_sig = tok
            at_line_start = False
            i += 1
            continue

        # Catch-all: NUMBER, STRING, COMMENT, OP (non-spaced or unary),
        # OTHER. WHITESPACE and NEWLINE are handled above.
        out.append(tok.text)
        prev_sig = tok
        at_line_start = False
        i += 1

    return "".join(out)


def _strip_trailing_inline_whitespace(out: list[str]) -> None:
    """Drop trailing space/tab chunks from ``out`` before emitting an OP.

    Walks back across pure-whitespace strings only; stops at any string
    containing a newline or a non-whitespace character.
    """
    while out:
        last = out[-1]
        if not last:
            out.pop()
            continue
        if all(c in " \t" for c in last):
            out.pop()
            continue
        break


def _is_unary_context(prev_sig: Token | None) -> bool:
    if prev_sig is None:
        return True
    if prev_sig.kind == TokenKind.NEWLINE:
        return True
    if prev_sig.kind == TokenKind.OP:
        return prev_sig.text in _EXPRESSION_START_OPS
    if prev_sig.kind == TokenKind.WORD:
        return prev_sig.text.lower() in UNARY_PREFIX_KEYWORDS
    return False


def _apply_keyword_case(word: str, prev_sig: Token | None, config: FormatConfig) -> str:
    if config.keyword_case == "preserve":
        return word
    if prev_sig is not None and prev_sig.kind == TokenKind.OP and prev_sig.text in (".", "::"):
        return word
    if word.lower() not in RESERVED:
        return word
    if config.keyword_case == "upper":
        return word.upper()
    return word.lower()


def _transform_indent(leading: str, config: FormatConfig) -> str:
    """Round-trip the leading whitespace into the configured form.

    ``"tab"`` output: every run of ``tab_width`` consecutive spaces is
    collapsed to one TAB; existing TABs are kept. Sub-unit residue is
    preserved as spaces.

    ``"spaces"`` output: every TAB is expanded to ``indent_spaces``
    spaces; existing space runs are kept untouched.
    """
    if config.indent_style == "tab":
        result: list[str] = []
        run = 0
        for ch in leading:
            if ch == "\t":
                if run:
                    result.append(" " * run)
                    run = 0
                result.append("\t")
            elif ch == " ":
                run += 1
                if run == config.tab_width:
                    result.append("\t")
                    run = 0
            else:  # pragma: no cover - WHITESPACE tokens only carry space/tab
                if run:
                    result.append(" " * run)
                    run = 0
                result.append(ch)
        if run:
            result.append(" " * run)
        return "".join(result)

    expansion = " " * config.indent_spaces
    return "".join(expansion if ch == "\t" else ch for ch in leading)
