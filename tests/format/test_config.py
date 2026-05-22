"""FormatConfig parsing and ``.pb-format.toml`` discovery tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from pb_orca_mcp.format.config import (
    CONFIG_FILENAME,
    FormatConfig,
    discover_config,
)


class TestFromDict:
    def test_empty_dict_gives_defaults(self) -> None:
        cfg = FormatConfig.from_dict({})
        assert cfg == FormatConfig.default()

    def test_full_explicit_config(self) -> None:
        cfg = FormatConfig.from_dict(
            {
                "style": {
                    "indent": "spaces:2",
                    "keyword_case": "upper",
                    "line_endings": "crlf",
                    "spaces_around_operators": False,
                    "tab_width": 8,
                }
            }
        )
        assert cfg.indent_style == "spaces"
        assert cfg.indent_spaces == 2
        assert cfg.keyword_case == "upper"
        assert cfg.line_endings == "crlf"
        assert cfg.spaces_around_operators is False
        assert cfg.tab_width == 8

    def test_indent_tab(self) -> None:
        cfg = FormatConfig.from_dict({"style": {"indent": "tab"}})
        assert cfg.indent_style == "tab"

    def test_unknown_style_key_ignored(self) -> None:
        # Forward-compatibility: future keys must not break older parsers.
        cfg = FormatConfig.from_dict({"style": {"indent": "tab", "future_key": "x"}})
        assert cfg.indent_style == "tab"

    @pytest.mark.parametrize(
        "bad",
        ["spaces:", "spaces:abc", "spaces:0", "spaces:17", "  tab", "soft-tab"],
    )
    def test_bad_indent_value_rejected(self, bad: str) -> None:
        with pytest.raises(ValueError, match="indent"):
            FormatConfig.from_dict({"style": {"indent": bad}})

    def test_bad_keyword_case_rejected(self) -> None:
        with pytest.raises(ValueError, match="keyword_case"):
            FormatConfig.from_dict({"style": {"keyword_case": "TitleCase"}})

    def test_bad_line_endings_rejected(self) -> None:
        with pytest.raises(ValueError, match="line_endings"):
            FormatConfig.from_dict({"style": {"line_endings": "cr"}})

    def test_bad_spaces_around_rejected(self) -> None:
        with pytest.raises(ValueError, match="spaces_around_operators"):
            FormatConfig.from_dict({"style": {"spaces_around_operators": "yes"}})

    def test_bad_tab_width_rejected(self) -> None:
        with pytest.raises(ValueError, match="tab_width"):
            FormatConfig.from_dict({"style": {"tab_width": -1}})

    def test_style_not_a_table_rejected(self) -> None:
        with pytest.raises(ValueError, match="style"):
            FormatConfig.from_dict({"style": "tab"})


class TestFromPath:
    def test_load_from_file(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / CONFIG_FILENAME
        cfg_file.write_text(
            '[style]\nindent = "spaces:2"\nkeyword_case = "upper"\n',
            encoding="utf-8",
        )
        cfg = FormatConfig.from_path(cfg_file)
        assert cfg.indent_style == "spaces"
        assert cfg.indent_spaces == 2
        assert cfg.keyword_case == "upper"


class TestDiscoverConfig:
    def test_found_in_same_dir(self, tmp_path: Path) -> None:
        (tmp_path / CONFIG_FILENAME).write_text("", encoding="utf-8")
        assert discover_config(tmp_path) == (tmp_path / CONFIG_FILENAME).resolve()

    def test_walks_up_from_file(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / CONFIG_FILENAME
        cfg_file.write_text("", encoding="utf-8")
        deep = tmp_path / "ws_objects" / "src" / "mw_core.pbl.src"
        deep.mkdir(parents=True)
        source = deep / "n_foo.sru"
        source.write_text("", encoding="utf-8")
        assert discover_config(source) == cfg_file.resolve()

    def test_returns_none_when_not_present(self, tmp_path: Path) -> None:
        subdir = tmp_path / "a" / "b"
        subdir.mkdir(parents=True)
        # Ensure walking up from inside tmp_path stops before any real
        # ancestor config we'd accidentally pick up.
        assert discover_config(subdir) is None or discover_config(subdir) != (
            subdir / CONFIG_FILENAME
        )

    def test_first_match_wins(self, tmp_path: Path) -> None:
        outer = tmp_path / CONFIG_FILENAME
        outer.write_text("", encoding="utf-8")
        inner_dir = tmp_path / "inner"
        inner_dir.mkdir()
        inner = inner_dir / CONFIG_FILENAME
        inner.write_text("", encoding="utf-8")
        # Walking up from a file inside inner_dir hits the inner config
        # first, never the outer one.
        source = inner_dir / "n_foo.sru"
        source.write_text("", encoding="utf-8")
        assert discover_config(source) == inner.resolve()
