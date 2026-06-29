"""Tests for the `pb-format` CLI (detect / format / check).

These exercise the file-level formatting path that runs offline (no
ORCA, no PB install), so they are not marked `requires_pb` and run in
CI. The invariants under test:

- header (`$PBExportHeader$` / `$PBExportComments$`) is preserved;
- the on-disk encoding (UTF-16 LE BOM / UTF-8 BOM / UTF-8) round-trips;
- the body is normalized per the resolved config;
- `format` is idempotent and `check` agrees with `format`.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from pb_orca_mcp.cli_format import cli

# A deliberately unformatted entry: UPPER keywords, 4-space indent, no
# spaces around operators. Header block on top.
UNFORMATTED_BODY = (
    "$PBExportHeader$n_test.sru\r\n"
    "$PBExportComments$demo comment\r\n"
    "forward\r\n"
    "global type n_test from nonvisualobject\r\n"
    "end type\r\n"
    "\r\n"
    "PUBLIC FUNCTION integer of_test (integer ai_x);\r\n"
    "    IF ai_x<=0 THEN\r\n"
    "        return ai_x+1\r\n"
    "    END IF\r\n"
    "RETURN ai_x\r\n"
    "end function\r\n"
)


def _write(path: Path, text: str, encoding: str = "utf-16le-bom") -> None:
    if encoding == "utf-16le-bom":
        path.write_bytes(b"\xff\xfe" + text.encode("utf-16-le"))
    elif encoding == "utf-8-bom":
        path.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
    else:
        path.write_bytes(text.encode("utf-8"))


def _read(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe"):
        return raw[2:].decode("utf-16-le"), "utf-16le-bom"
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8"), "utf-8-bom"
    return raw.decode("utf-8"), "utf-8"


def _config(path: Path) -> None:
    path.write_text(
        '[style]\nindent = "spaces:4"\nkeyword_case = "lower"\n'
        'spaces_around_operators = true\nline_endings = "crlf"\n',
        encoding="utf-8",
    )


# --- detect ----------------------------------------------------------------


def test_detect_writes_config(tmp_path: Path) -> None:
    _write(tmp_path / "n_test.sru", UNFORMATTED_BODY)
    result = CliRunner().invoke(cli, ["detect", str(tmp_path)])
    assert result.exit_code == 0, result.output
    cfg = tmp_path / ".pb-format.toml"
    assert cfg.exists()
    assert "[style]" in cfg.read_text(encoding="utf-8")


def test_detect_refuses_overwrite_without_force(tmp_path: Path) -> None:
    _write(tmp_path / "n_test.sru", UNFORMATTED_BODY)
    (tmp_path / ".pb-format.toml").write_text("# existing\n", encoding="utf-8")
    result = CliRunner().invoke(cli, ["detect", str(tmp_path)])
    assert result.exit_code != 0
    assert "already exists" in result.output


def test_detect_force_overwrites(tmp_path: Path) -> None:
    _write(tmp_path / "n_test.sru", UNFORMATTED_BODY)
    (tmp_path / ".pb-format.toml").write_text("# existing\n", encoding="utf-8")
    result = CliRunner().invoke(cli, ["detect", str(tmp_path), "--force"])
    assert result.exit_code == 0, result.output
    assert "# existing" not in (tmp_path / ".pb-format.toml").read_text(encoding="utf-8")


def test_detect_no_sources_errors(tmp_path: Path) -> None:
    result = CliRunner().invoke(cli, ["detect", str(tmp_path)])
    assert result.exit_code != 0
    assert "No PowerScript source files" in result.output


# --- format ----------------------------------------------------------------


def test_format_normalizes_body(tmp_path: Path) -> None:
    _config(tmp_path / ".pb-format.toml")
    src = tmp_path / "n_test.sru"
    _write(src, UNFORMATTED_BODY)

    result = CliRunner().invoke(cli, ["format", str(src)])
    assert result.exit_code == 0, result.output
    assert "reformatted" in result.output

    text, encoding = _read(src)
    assert encoding == "utf-16le-bom"  # BOM preserved
    assert "\r\n" in text and "\n" not in text.replace("\r\n", "")  # CRLF preserved
    lines = text.split("\r\n")
    assert lines[0] == "$PBExportHeader$n_test.sru"  # header preserved
    assert lines[1] == "$PBExportComments$demo comment"
    assert "if ai_x <= 0 then" in text  # keyword lower + operator spacing
    assert "return ai_x + 1" in text


def test_format_is_idempotent(tmp_path: Path) -> None:
    _config(tmp_path / ".pb-format.toml")
    src = tmp_path / "n_test.sru"
    _write(src, UNFORMATTED_BODY)

    CliRunner().invoke(cli, ["format", str(src)])
    after_first = src.read_bytes()
    result = CliRunner().invoke(cli, ["format", str(src)])
    assert result.exit_code == 0, result.output
    assert "0 reformatted" in result.output
    assert src.read_bytes() == after_first


def test_format_preserves_utf8_bom_encoding(tmp_path: Path) -> None:
    _config(tmp_path / ".pb-format.toml")
    src = tmp_path / "n_test.sru"
    _write(src, UNFORMATTED_BODY, encoding="utf-8-bom")
    CliRunner().invoke(cli, ["format", str(src)])
    _, encoding = _read(src)
    assert encoding == "utf-8-bom"


def test_format_preserves_plain_utf8_encoding(tmp_path: Path) -> None:
    _config(tmp_path / ".pb-format.toml")
    src = tmp_path / "n_test.sru"
    _write(src, UNFORMATTED_BODY, encoding="utf-8")
    CliRunner().invoke(cli, ["format", str(src)])
    _, encoding = _read(src)
    assert encoding == "utf-8"


def test_format_dry_run_does_not_write(tmp_path: Path) -> None:
    _config(tmp_path / ".pb-format.toml")
    src = tmp_path / "n_test.sru"
    _write(src, UNFORMATTED_BODY)
    before = src.read_bytes()
    result = CliRunner().invoke(cli, ["format", "--dry-run", str(src)])
    assert result.exit_code == 0, result.output
    assert "would reformat" in result.output
    assert src.read_bytes() == before


def test_format_directory_recurses(tmp_path: Path) -> None:
    _config(tmp_path / ".pb-format.toml")
    sub = tmp_path / "src" / "app.pbl.src"
    sub.mkdir(parents=True)
    _write(sub / "n_a.sru", UNFORMATTED_BODY)
    _write(sub / "n_b.srf", UNFORMATTED_BODY)
    result = CliRunner().invoke(cli, ["format", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "2 reformatted" in result.output


def test_format_rejects_unsupported_extension(tmp_path: Path) -> None:
    bad = tmp_path / "n_dw.srd"  # DataWindow source: intentionally excluded
    _write(bad, UNFORMATTED_BODY)
    result = CliRunner().invoke(cli, ["format", str(bad)])
    assert result.exit_code != 0
    assert "not a PowerScript source file" in result.output


def test_format_explicit_config_option(tmp_path: Path) -> None:
    cfg = tmp_path / "mystyle.toml"
    cfg.write_text('[style]\nkeyword_case = "upper"\n', encoding="utf-8")
    src = tmp_path / "n_test.sru"
    _write(src, UNFORMATTED_BODY)
    result = CliRunner().invoke(cli, ["format", "--config", str(cfg), str(src)])
    assert result.exit_code == 0, result.output
    text, _ = _read(src)
    assert "IF ai_x <= 0 THEN" in text  # upper keyword case from explicit config


def test_format_invalid_config_errors(tmp_path: Path) -> None:
    cfg = tmp_path / "bad.toml"
    cfg.write_text('[style]\nindent = "spaces:99"\n', encoding="utf-8")
    src = tmp_path / "n_test.sru"
    _write(src, UNFORMATTED_BODY)
    result = CliRunner().invoke(cli, ["format", "--config", str(cfg), str(src)])
    assert result.exit_code != 0


# --- check -----------------------------------------------------------------


def test_check_flags_unformatted(tmp_path: Path) -> None:
    _config(tmp_path / ".pb-format.toml")
    src = tmp_path / "n_test.sru"
    _write(src, UNFORMATTED_BODY)
    result = CliRunner().invoke(cli, ["check", str(src)])
    assert result.exit_code == 1
    assert "would reformat" in result.output


def test_check_passes_on_formatted(tmp_path: Path) -> None:
    _config(tmp_path / ".pb-format.toml")
    src = tmp_path / "n_test.sru"
    _write(src, UNFORMATTED_BODY)
    CliRunner().invoke(cli, ["format", str(src)])
    result = CliRunner().invoke(cli, ["check", str(src)])
    assert result.exit_code == 0
    assert "already formatted" in result.output


def test_check_writes_nothing(tmp_path: Path) -> None:
    _config(tmp_path / ".pb-format.toml")
    src = tmp_path / "n_test.sru"
    _write(src, UNFORMATTED_BODY)
    before = src.read_bytes()
    CliRunner().invoke(cli, ["check", str(src)])
    assert src.read_bytes() == before
