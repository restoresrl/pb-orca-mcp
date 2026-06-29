"""State-machine tokenizer for PowerScript source.

Emits a flat ``Token`` stream with stable position info. The lexer makes
string and comment bodies *opaque* — they show up as a single
``STRING`` or ``COMMENT`` token each — so the normalizer's
case-and-spacing rules cannot accidentally rewrite text inside them.

PowerScript specifics worth knowing:

- Strings: ``"..."`` or ``'...'``. Escape character is ``~`` (tilde),
  not backslash. A doubled quote inside a same-kind string is also a
  literal-quote escape (``"abc""def"`` → ``abc"def``).
- Comments: ``//`` to end of line, ``/* ... */`` non-nested.
- Continuation: ``&`` at end of a line. We emit it as a plain ``OP``
  token — callers can detect by checking for the following ``NEWLINE``.
- Identifiers: start with a letter or ``_``, continue with alnum or
  ``_``, ``$``, ``#``, ``%``. PB does **not** allow ``-`` in identifiers
  (it would clash with subtraction).
- Numbers: decimal with optional fraction and E-notation.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum


class TokenKind(Enum):
    WORD = "word"
    NUMBER = "number"
    STRING = "string"
    COMMENT = "comment"
    OP = "op"
    WHITESPACE = "whitespace"  # spaces and tabs, never newlines
    NEWLINE = "newline"
    OTHER = "other"


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    text: str
    pos: int


_TWO_CHAR_OPS: frozenset[str] = frozenset({"<=", ">=", "<>", "+=", "-=", "*=", "/=", "::"})

_SINGLE_CHAR_OPS: frozenset[str] = frozenset(set("=+-*/<>^.,;:()[]{}&!?@|"))

_IDENT_START: frozenset[str] = frozenset(
    set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_")
)
_IDENT_CONTINUE: frozenset[str] = frozenset(
    set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_$#%")
)
_DIGITS: frozenset[str] = frozenset(set("0123456789"))


def tokenize(source: str) -> Iterator[Token]:
    """Yield ``Token`` objects covering every character of ``source``.

    The concatenation of every emitted token's ``text`` reproduces the
    input exactly; this is the property the normalizer relies on for
    idempotency.
    """
    pos = 0
    n = len(source)
    while pos < n:
        ch = source[pos]

        if ch == "\r":
            if pos + 1 < n and source[pos + 1] == "\n":
                yield Token(TokenKind.NEWLINE, "\r\n", pos)
                pos += 2
            else:
                yield Token(TokenKind.NEWLINE, "\r", pos)
                pos += 1
            continue
        if ch == "\n":
            yield Token(TokenKind.NEWLINE, "\n", pos)
            pos += 1
            continue

        if ch == " " or ch == "\t":
            start = pos
            while pos < n and source[pos] in (" ", "\t"):
                pos += 1
            yield Token(TokenKind.WHITESPACE, source[start:pos], start)
            continue

        if ch == "/" and pos + 1 < n and source[pos + 1] == "/":
            start = pos
            while pos < n and source[pos] not in ("\r", "\n"):
                pos += 1
            yield Token(TokenKind.COMMENT, source[start:pos], start)
            continue

        if ch == "/" and pos + 1 < n and source[pos + 1] == "*":
            start = pos
            pos += 2
            while pos < n:
                if source[pos] == "*" and pos + 1 < n and source[pos + 1] == "/":
                    pos += 2
                    break
                pos += 1
            yield Token(TokenKind.COMMENT, source[start:pos], start)
            continue

        if ch == '"' or ch == "'":
            quote = ch
            start = pos
            pos += 1
            while pos < n:
                c = source[pos]
                if c == "~" and pos + 1 < n:
                    pos += 2
                    continue
                if c == quote:
                    if pos + 1 < n and source[pos + 1] == quote:
                        pos += 2
                        continue
                    pos += 1
                    break
                if c == "\n" or c == "\r":
                    break
                pos += 1
            yield Token(TokenKind.STRING, source[start:pos], start)
            continue

        if ch in _IDENT_START:
            start = pos
            pos += 1
            while pos < n and source[pos] in _IDENT_CONTINUE:
                pos += 1
            yield Token(TokenKind.WORD, source[start:pos], start)
            continue

        if ch in _DIGITS:
            start = pos
            pos += 1
            while pos < n and source[pos] in _DIGITS:
                pos += 1
            if pos + 1 < n and source[pos] == "." and source[pos + 1] in _DIGITS:
                pos += 1
                while pos < n and source[pos] in _DIGITS:
                    pos += 1
            if pos < n and source[pos] in ("e", "E"):
                save = pos
                pos += 1
                if pos < n and source[pos] in ("+", "-"):
                    pos += 1
                if pos < n and source[pos] in _DIGITS:
                    while pos < n and source[pos] in _DIGITS:
                        pos += 1
                else:
                    pos = save
            yield Token(TokenKind.NUMBER, source[start:pos], start)
            continue

        if pos + 1 < n and source[pos : pos + 2] in _TWO_CHAR_OPS:
            yield Token(TokenKind.OP, source[pos : pos + 2], pos)
            pos += 2
            continue
        if ch in _SINGLE_CHAR_OPS:
            yield Token(TokenKind.OP, ch, pos)
            pos += 1
            continue

        yield Token(TokenKind.OTHER, ch, pos)
        pos += 1
