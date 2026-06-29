"""Pure-function tests for the `edit_and_import` header / comment helpers.

These exercise the canonical PB IDE export header reconstruction path
without touching ORCA, the filesystem, or `pborc.dll`. Integration of
the full `Session.edit_and_import` flow lives behind the `requires_pb`
marker in `test_session_real.py`.
"""

from __future__ import annotations

import pytest

from pb_orca_mcp.orca.session import (
    _encode_for_disk,
    _escape_pb_comment,
    _normalize_pb_comment_newlines,
    _strip_export_headers,
)


class TestEscapePbComment:
    """`_escape_pb_comment` matches PB IDE's PowerScript-escape format."""

    def test_plain_text_is_unchanged(self) -> None:
        assert _escape_pb_comment("Generated SDI Application Object") == (
            "Generated SDI Application Object"
        )

    def test_unicode_is_preserved(self) -> None:
        # Em-dash, accented letters, smart quotes — all pass through.
        assert _escape_pb_comment("fix — refactor utenza") == "fix — refactor utenza"

    def test_crlf_becomes_tilde_r_tilde_n(self) -> None:
        # Verified empirically against PB 22.0 IDE export.
        assert _escape_pb_comment("a\r\nb") == "a~r~nb"

    def test_bare_lf(self) -> None:
        assert _escape_pb_comment("a\nb") == "a~nb"

    def test_bare_cr(self) -> None:
        assert _escape_pb_comment("a\rb") == "a~rb"

    def test_tab(self) -> None:
        assert _escape_pb_comment("a\tb") == "a~tb"

    def test_tilde_escapes_first(self) -> None:
        # `~` must be doubled before any other escape runs, otherwise
        # the introduced `~r`/`~n` sequences would get re-escaped to
        # `~~r`/`~~n`.
        assert _escape_pb_comment("a~b") == "a~~b"
        assert _escape_pb_comment("a~\nb") == "a~~~nb"

    def test_realistic_multiline_comment(self) -> None:
        # PB IDE's wizard-generated about-box comment shape, verified
        # empirically in the bug repro session.
        text = "Generated SDI About Box\r\n2 riga commento\r\n3 riga commento"
        assert _escape_pb_comment(text) == (
            "Generated SDI About Box~r~n2 riga commento~r~n3 riga commento"
        )


class TestStripExportHeaders:
    """`_strip_export_headers` drops caller-supplied header lines."""

    def test_no_headers_returned_unchanged(self) -> None:
        body = "forward\nglobal type x from window\nend type\n"
        assert _strip_export_headers(body) == body

    def test_strips_pbexport_header_only(self) -> None:
        text = "$PBExportHeader$x.srw\nforward\nend forward\n"
        assert _strip_export_headers(text) == "forward\nend forward\n"

    def test_strips_pbexport_header_and_comments(self) -> None:
        text = "$PBExportHeader$x.srw\n$PBExportComments$old comment\nforward\n"
        assert _strip_export_headers(text) == "forward\n"

    def test_strips_with_crlf_endings(self) -> None:
        text = "$PBExportHeader$x.srw\r\n$PBExportComments$x\r\nforward\r\n"
        assert _strip_export_headers(text) == "forward\r\n"

    def test_skips_leading_blank_lines(self) -> None:
        text = "\r\n\r\n$PBExportHeader$x.srw\nforward\n"
        assert _strip_export_headers(text) == "forward\n"

    def test_strips_bare_comments_line(self) -> None:
        # PB never emits `$PBExportComments$` without a preceding
        # `$PBExportHeader$`, but the stripper is intentionally lenient:
        # it just inspects the first two lines and drops whichever
        # matches. Cheaper than a strict parser and harmless — the
        # caller is going to rebuild the canonical block anyway.
        text = "$PBExportComments$x\nforward\n"
        assert _strip_export_headers(text) == "forward\n"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", ""),
        ("normal", "normal"),
        ("with~tilde", "with~~tilde"),
        ("line1\r\nline2", "line1~r~nline2"),
        ("line1\nline2", "line1~nline2"),
        ("a\tb\nc\rd~e", "a~tb~nc~rd~~e"),
    ],
)
def test_escape_pb_comment_parametric(raw: str, expected: str) -> None:
    assert _escape_pb_comment(raw) == expected


class TestNormalizePbCommentNewlines:
    """`_normalize_pb_comment_newlines` brings any newline style to CRLF."""

    def test_empty_string_unchanged(self) -> None:
        assert _normalize_pb_comment_newlines("") == ""

    def test_plain_text_unchanged(self) -> None:
        assert _normalize_pb_comment_newlines("hello world") == "hello world"

    def test_lf_becomes_crlf(self) -> None:
        # The case that surfaces when a comment is passed through JSON
        # or an XML tool call — newlines collapse to bare LF.
        assert _normalize_pb_comment_newlines("a\nb\nc") == "a\r\nb\r\nc"

    def test_cr_becomes_crlf(self) -> None:
        # Classic Mac style — uncommon but should normalize too.
        assert _normalize_pb_comment_newlines("a\rb\rc") == "a\r\nb\r\nc"

    def test_crlf_preserved(self) -> None:
        # Already-Windows newlines must not be doubled.
        assert _normalize_pb_comment_newlines("a\r\nb\r\nc") == "a\r\nb\r\nc"

    def test_mixed_normalizes_uniformly(self) -> None:
        assert _normalize_pb_comment_newlines("a\nb\rc\r\nd") == "a\r\nb\r\nc\r\nd"


class TestEncodeForDisk:
    """`_encode_for_disk` matches the BOM + codec PB IDE writes for each `.pbw` setting."""

    def test_utf_8_bom(self) -> None:
        out = _encode_for_disk("hello", "UTF-8")
        # EF BB BF + UTF-8 bytes
        assert out == b"\xef\xbb\xbf" + b"hello"

    def test_utf_16_bom_le(self) -> None:
        out = _encode_for_disk("hello", "UTF-16BOM")
        # FF FE + UTF-16 LE bytes (each ASCII char as 2 bytes)
        assert out == b"\xff\xfe" + "hello".encode("utf-16-le")

    def test_ansi_no_bom(self) -> None:
        # ASCII subset survives ANSI/mbcs cleanly on any Windows codepage.
        out = _encode_for_disk("hello", "ANSI")
        assert out == b"hello"

    def test_utf_8_preserves_unicode(self) -> None:
        out = _encode_for_disk("àbé—", "UTF-8")
        assert out == b"\xef\xbb\xbf" + "àbé—".encode()

    def test_utf_16_preserves_unicode(self) -> None:
        out = _encode_for_disk("àbé—", "UTF-16BOM")
        assert out == b"\xff\xfe" + "àbé—".encode("utf-16-le")

    def test_unknown_encoding_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported source_encoding"):
            _encode_for_disk("hello", "EBCDIC")

    def test_ansi_rejects_out_of_codepage_chars(self) -> None:
        # CJK ideograph (U+4E2D, "middle") is not in any single-byte
        # Western Windows codepage (CP1252, CP1250, …). PB IDE writes
        # ANSI `.sru` files in strict mode too — we surface this as
        # `UnicodeEncodeError`, mapped by the MCP wrapper to
        # `PB_ORCA_MCP_ENCODINGERROR`.
        import sys

        if sys.platform != "win32":
            pytest.skip("ANSI/mbcs codec is Windows-only")
        with pytest.raises(UnicodeEncodeError):
            _encode_for_disk("contains CJK 中 char", "ANSI")
