"""Unit tests for `_resolve_format` — the discovery + skip-rules layer
that maps the public `format` argument to a `FormatConfig | None`.

These tests don't touch the session or the filesystem beyond `tmp_path`;
they verify the decision tree in isolation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pb_orca_mcp.format import CONFIG_FILENAME, FormatConfig
from pb_orca_mcp.tools.compile import _resolve_format


def _write_config(directory: Path, body: str) -> Path:
    target = directory / CONFIG_FILENAME
    target.write_text(body, encoding="utf-8")
    return target


class TestModeFalse:
    def test_returns_none_unconditionally(self, tmp_path: Path) -> None:
        _write_config(tmp_path, '[style]\nindent = "tab"\n')
        source = tmp_path / "n_foo.sru"
        out = _resolve_format(False, str(source), "userobject")
        assert out is None


class TestModeAutoNoConfig:
    def test_returns_none_when_walking_up_finds_nothing(self, tmp_path: Path) -> None:
        source = tmp_path / "n_foo.sru"
        # Resolve against tmp_path itself so we don't accidentally hit
        # the project's own root config (none exists at the moment).
        out = _resolve_format("auto", str(source), "userobject")
        # If a real .pb-format.toml ever appears above tmp_path, this
        # would resolve to a FormatConfig; today there isn't one.
        # Verify either no config found, or it came from outside tmp_path.
        if out is not None:  # pragma: no cover - defensive
            pytest.skip("Ancestor .pb-format.toml in fs unrelated to test")
        assert out is None


class TestModeAutoWithConfig:
    def test_picks_up_workspace_config(self, tmp_path: Path) -> None:
        _write_config(tmp_path, '[style]\nindent = "spaces:2"\nkeyword_case = "upper"\n')
        source = tmp_path / "ws" / "src" / "n_foo.sru"
        source.parent.mkdir(parents=True)
        out = _resolve_format("auto", str(source), "userobject")
        assert out is not None
        assert out.indent_style == "spaces"
        assert out.indent_spaces == 2
        assert out.keyword_case == "upper"

    def test_walks_up_from_deep_source(self, tmp_path: Path) -> None:
        _write_config(tmp_path, '[style]\nindent = "tab"\n')
        source = tmp_path / "a" / "b" / "c" / "d" / "n_foo.sru"
        source.parent.mkdir(parents=True)
        out = _resolve_format("auto", str(source), "userobject")
        assert out is not None
        assert out.indent_style == "tab"


class TestModeTrue:
    def test_uses_defaults_when_no_config(self, tmp_path: Path) -> None:
        source = tmp_path / "n_foo.sru"
        out = _resolve_format(True, str(source), "userobject")
        assert out is not None
        assert out == FormatConfig.default()

    def test_uses_discovered_config_when_present(self, tmp_path: Path) -> None:
        _write_config(tmp_path, '[style]\nindent = "spaces:4"\nkeyword_case = "upper"\n')
        source = tmp_path / "n_foo.sru"
        out = _resolve_format(True, str(source), "userobject")
        assert out is not None
        assert out.indent_style == "spaces"
        assert out.keyword_case == "upper"


class TestSkipByEntryType:
    @pytest.mark.parametrize("mode", ["auto", True])
    def test_datawindow_skipped(self, tmp_path: Path, mode: object) -> None:
        _write_config(tmp_path, '[style]\nindent = "tab"\n')
        source = tmp_path / "d_foo.srd"
        out = _resolve_format(mode, str(source), "datawindow")  # type: ignore[arg-type]
        assert out is None

    @pytest.mark.parametrize("entry_type", ["project", "proxyobject", "binary"])
    @pytest.mark.parametrize("mode", ["auto", True])
    def test_non_source_entries_skipped(
        self, tmp_path: Path, entry_type: str, mode: object
    ) -> None:
        _write_config(tmp_path, '[style]\nindent = "tab"\n')
        source = tmp_path / "x.sru"
        out = _resolve_format(mode, str(source), entry_type)  # type: ignore[arg-type]
        assert out is None

    @pytest.mark.parametrize(
        "entry_type",
        ["application", "userobject", "window", "function", "structure"],
    )
    def test_powerscript_entries_pass_through(self, tmp_path: Path, entry_type: str) -> None:
        _write_config(tmp_path, '[style]\nindent = "tab"\n')
        source = tmp_path / "x.sru"
        out = _resolve_format("auto", str(source), entry_type)
        assert out is not None


class TestInvalidMode:
    @pytest.mark.parametrize("mode", ["yes", "no", "true", "off", 1, 0, None])
    def test_unknown_mode_raises(self, tmp_path: Path, mode: object) -> None:
        source = tmp_path / "n_foo.sru"
        with pytest.raises(ValueError, match="format"):
            _resolve_format(mode, str(source), "userobject")  # type: ignore[arg-type]


class TestBadConfig:
    def test_malformed_toml_surfaces_as_value_error(self, tmp_path: Path) -> None:
        _write_config(tmp_path, "this is not [valid toml")
        source = tmp_path / "n_foo.sru"
        # tomllib raises TOMLDecodeError, which is a ValueError subclass.
        with pytest.raises(ValueError):
            _resolve_format("auto", str(source), "userobject")

    def test_unknown_indent_value_raises(self, tmp_path: Path) -> None:
        _write_config(tmp_path, '[style]\nindent = "soft-tab"\n')
        source = tmp_path / "n_foo.sru"
        with pytest.raises(ValueError, match="indent"):
            _resolve_format("auto", str(source), "userobject")
