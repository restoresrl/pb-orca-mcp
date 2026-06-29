"""Frequency-based auto-detect tests."""

from __future__ import annotations

from pathlib import Path

from pb_orca_mcp.format.config import CONFIG_FILENAME, FormatConfig
from pb_orca_mcp.format.detect import detect_workspace_style, write_config_file


def _make_source(path: Path, body: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding=encoding)


def _make_utf16_source(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xfe" + body.encode("utf-16-le"))


class TestDetect:
    def test_empty_root_returns_defaults(self, tmp_path: Path) -> None:
        result = detect_workspace_style(tmp_path)
        assert result.files_scanned == 0
        assert result.config == FormatConfig.default()

    def test_tabs_dominate(self, tmp_path: Path) -> None:
        body = "if a then\r\n\tif b then\r\n\t\treturn 1\r\n\tend if\r\nend if\r\n"
        _make_source(tmp_path / "n_foo.sru", body)
        result = detect_workspace_style(tmp_path)
        assert result.config.indent_style == "tab"
        assert result.indent_votes.get("tab", 0) > 0

    def test_two_space_indent_detected(self, tmp_path: Path) -> None:
        body = "if a then\r\n  return 1\r\n    return 2\r\n      return 3\r\n"
        _make_source(tmp_path / "n_foo.sru", body)
        result = detect_workspace_style(tmp_path)
        # Vote breakdown: 2 → spaces:2, 4 → spaces:4, 6 → spaces:2 (6%2==0
        # before 4). So spaces:2 wins 2-1.
        assert result.config.indent_style == "spaces"
        assert result.config.indent_spaces == 2

    def test_lowercase_keyword_wins(self, tmp_path: Path) -> None:
        body = "if a then return\r\nif b then return\r\n"
        _make_source(tmp_path / "n_foo.sru", body)
        result = detect_workspace_style(tmp_path)
        assert result.config.keyword_case == "lower"

    def test_uppercase_keyword_wins(self, tmp_path: Path) -> None:
        body = "IF a THEN RETURN\r\nIF b THEN RETURN\r\n"
        _make_source(tmp_path / "n_foo.sru", body)
        result = detect_workspace_style(tmp_path)
        assert result.config.keyword_case == "upper"

    def test_spaces_around_operators_true(self, tmp_path: Path) -> None:
        body = "a = 1\r\nb = 2\r\nc = 3\r\n"
        _make_source(tmp_path / "n_foo.sru", body)
        result = detect_workspace_style(tmp_path)
        assert result.config.spaces_around_operators is True

    def test_spaces_around_operators_false(self, tmp_path: Path) -> None:
        body = "a=1\r\nb=2\r\nc=3\r\n"
        _make_source(tmp_path / "n_foo.sru", body)
        result = detect_workspace_style(tmp_path)
        assert result.config.spaces_around_operators is False

    def test_srd_files_ignored(self, tmp_path: Path) -> None:
        # DataWindows have their own DSL — must not contribute votes.
        _make_source(tmp_path / "d_foo.srd", "// not powerscript\r\n")
        result = detect_workspace_style(tmp_path)
        assert result.files_scanned == 0

    def test_utf16_bom_file_decoded(self, tmp_path: Path) -> None:
        _make_utf16_source(tmp_path / "n_bom.sru", "\tIF a THEN return\r\n")
        result = detect_workspace_style(tmp_path)
        assert result.files_scanned == 1
        assert result.config.indent_style == "tab"
        assert result.config.keyword_case == "upper"

    def test_max_files_caps_sample(self, tmp_path: Path) -> None:
        for i in range(20):
            _make_source(tmp_path / f"n_{i}.sru", "")
        result = detect_workspace_style(tmp_path, max_files=5)
        assert result.files_scanned == 5


class TestWriteConfigFile:
    def test_writes_toml_and_round_trips(self, tmp_path: Path) -> None:
        _make_source(tmp_path / "n_foo.sru", "\tif a then return\r\n")
        result = detect_workspace_style(tmp_path)
        target = write_config_file(tmp_path, result)
        assert target.name == CONFIG_FILENAME
        roundtrip = FormatConfig.from_path(target)
        assert roundtrip == result.config

    def test_includes_vote_breakdown_as_comments(self, tmp_path: Path) -> None:
        _make_source(tmp_path / "n_foo.sru", "\tif a then return\r\n")
        result = detect_workspace_style(tmp_path)
        target = write_config_file(tmp_path, result)
        body = target.read_text(encoding="utf-8")
        assert "# indent votes:" in body
        assert "# keyword_case votes:" in body
        assert "# spaces_around_operators votes:" in body
