"""Unit tests for workspace layout detection.

Pure filesystem logic, so these run everywhere — no PowerBuilder, no ORCA,
no git executable. They pin the two shapes of project pb-orca has to handle
(`pbl_only` and `ws_objects`) and the details that decide whether a write is
visible to git in a reviewable form.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pb_orca_mcp import workspace as ws

_MAGIC = "Save Format v3.0(19990112)\n"


def _pbw(directory: Path, name: str = "proj", encode: str | None = "UTF-8") -> Path:
    body = _MAGIC + '@begin Targets\n 0 "app.pbt";\n@end;\nDefaultTarget "app.pbt";\n'
    if encode is not None:
        body += f'DefaultExportEncode "{encode}";\n'
    path = directory / f"{name}.pbw"
    path.write_text(body, encoding="utf-8")
    return path


def _source_file(directory: Path, name: str, bom: bytes = b"\xef\xbb\xbf") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(bom + b"$PBExportHeader$" + name.encode() + b"\r\nforward\r\n")
    return path


# --------------------------- workspace file lookup ---------------------------


def test_find_workspace_file_walks_up(tmp_path: Path) -> None:
    _pbw(tmp_path)
    nested = tmp_path / "src" / "deep"
    nested.mkdir(parents=True)
    assert ws.find_workspace_file(nested / "app.pbl") == str(tmp_path / "proj.pbw")


def test_find_workspace_file_returns_none_without_one(tmp_path: Path) -> None:
    assert ws.find_workspace_file(tmp_path / "orphan.pbl") is None


def test_find_workspace_file_prefers_the_stem_matching_the_directory(tmp_path: Path) -> None:
    project = tmp_path / "myproj"
    project.mkdir()
    _pbw(project, name="aaa")
    _pbw(project, name="myproj")
    assert ws.find_workspace_file(project / "app.pbl") == str(project / "myproj.pbw")


# --------------------------- export encoding ---------------------------


@pytest.mark.parametrize(
    ("declared", "expected"),
    [("UTF-8", "utf8"), ("UTF-16BOM", "unicode"), ("ANSI", "ansi"), ("nonsense", "utf8")],
)
def test_orca_encoding_for(declared: str, expected: str) -> None:
    assert ws.orca_encoding_for(declared) == expected


def test_read_default_export_encode_is_case_insensitive(tmp_path: Path) -> None:
    path = tmp_path / "w.pbw"
    path.write_text(_MAGIC + 'defaultexportencode "UTF-16BOM";\n', encoding="utf-8")
    assert ws.read_default_export_encode(path) == "UTF-16BOM"


def test_read_default_export_encode_absent(tmp_path: Path) -> None:
    assert ws.read_default_export_encode(_pbw(tmp_path, encode=None)) is None


def test_encoding_falls_back_to_what_the_files_actually_are(tmp_path: Path) -> None:
    """A .pbw with no directive: trust the BOM on the existing projection."""
    _pbw(tmp_path, encode=None)
    (tmp_path / "app.pbl").write_bytes(b"")
    _source_file(tmp_path / "ws_objects" / "app.pbl.src", "w_main.srw", bom=b"\xff\xfe")
    info = ws.describe(tmp_path / "app.pbl")
    assert info.encoding_source == "observed"
    assert info.orca_encoding == "unicode"
    assert info.export_encode == "UTF-16BOM"


def test_declared_encoding_wins_but_mismatch_is_reported(tmp_path: Path) -> None:
    """The IDE writes what the .pbw declares, so that value wins — but a
    projection whose bytes disagree is a real inconsistency and is surfaced."""
    _pbw(tmp_path, encode="UTF-8")
    (tmp_path / "app.pbl").write_bytes(b"")
    _source_file(tmp_path / "ws_objects" / "app.pbl.src", "w_main.srw", bom=b"\xff\xfe")
    info = ws.describe(tmp_path / "app.pbl")
    assert info.orca_encoding == "utf8"
    assert info.encoding_source == "pbw"
    assert info.observed_encoding == "unicode"


# --------------------------- projection layout ---------------------------


def test_source_dir_mirrors_the_library_path(tmp_path: Path) -> None:
    computed = ws.source_dir_for_library(tmp_path / "src" / "app.pbl", tmp_path)
    assert computed == tmp_path / "ws_objects" / "src" / "app.pbl.src"


def test_source_dir_for_library_at_the_root(tmp_path: Path) -> None:
    computed = ws.source_dir_for_library(tmp_path / "app.pbl", tmp_path)
    assert computed == tmp_path / "ws_objects" / "app.pbl.src"


def test_existing_flat_layout_wins_over_the_computed_path(tmp_path: Path) -> None:
    """Older workspaces keep one flat tree; an existing directory is authoritative."""
    flat = tmp_path / "ws_objects" / "app.pbl.src"
    _source_file(flat, "w_main.srw")
    located = ws.locate_source_dir(tmp_path / "src" / "app.pbl", tmp_path)
    assert located == flat


def test_describe_detects_pbl_only(tmp_path: Path) -> None:
    _pbw(tmp_path)
    (tmp_path / "app.pbl").write_bytes(b"")
    info = ws.describe(tmp_path / "app.pbl")
    assert info.mode == "pbl_only"
    assert info.ws_objects_dir is None
    assert info.work_dir == str(tmp_path / ".pb-orca")
    assert info.sources is not None and not info.sources.exists


def test_describe_detects_ws_objects(tmp_path: Path) -> None:
    _pbw(tmp_path)
    (tmp_path / "app.pbl").write_bytes(b"")
    _source_file(tmp_path / "ws_objects" / "app.pbl.src", "w_main.srw")
    info = ws.describe(tmp_path / "app.pbl")
    assert info.mode == "ws_objects"
    assert info.sources is not None
    assert info.sources.exists and info.sources.file_count == 1
    assert "both" in info.advice or "same commit" in info.advice


def test_a_library_outside_the_projection_tree_is_flagged(tmp_path: Path) -> None:
    """A vendored or third-party library: the project keeps text sources, but
    this one has no directory under ws_objects/.

    Seen on real projects two ways — a customization pinning a built snapshot
    of its base product under dep/, and a commercial component sitting in
    src/. Both must not be offered a bootstrap.
    """
    _pbw(tmp_path)
    _source_file(tmp_path / "ws_objects" / "src" / "app.pbl.src", "w_main.srw")
    vendored = tmp_path / "dep" / "base" / "vendor.pbl"
    vendored.parent.mkdir(parents=True)
    vendored.write_bytes(b"")

    info = ws.describe(vendored)
    assert info.mode == "pbl_only"
    assert info.outside_source_tree
    assert "vendored" in info.advice
    assert "pb_library_export_sources" not in info.advice


def test_a_project_with_no_projection_at_all_is_not_flagged(tmp_path: Path) -> None:
    """The binary-only project is a first-class layout, not a suspicious one."""
    _pbw(tmp_path)
    (tmp_path / "app.pbl").write_bytes(b"")
    info = ws.describe(tmp_path / "app.pbl")
    assert info.mode == "pbl_only"
    assert not info.outside_source_tree


def test_a_projected_library_is_not_flagged(tmp_path: Path) -> None:
    _pbw(tmp_path)
    (tmp_path / "app.pbl").write_bytes(b"")
    _source_file(tmp_path / "ws_objects" / "app.pbl.src", "w_main.srw")
    assert not ws.describe(tmp_path / "app.pbl").outside_source_tree


def test_describe_without_a_workspace_file_uses_the_library_directory(tmp_path: Path) -> None:
    lib = tmp_path / "standalone" / "app.pbl"
    lib.parent.mkdir()
    lib.write_bytes(b"")
    info = ws.describe(lib)
    assert info.workspace_file is None
    assert info.root == str(lib.parent)
    assert info.export_encode == ws.DEFAULT_EXPORT_ENCODE
    assert info.encoding_source == "default"


# --------------------------- git detection ---------------------------


def test_find_git_root_walks_up_for_a_git_directory(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert ws.find_git_root(nested) == str(tmp_path)


def test_find_git_root_accepts_a_git_file(tmp_path: Path) -> None:
    """Worktrees and submodule checkouts carry a `.git` file, not a directory."""
    (tmp_path / ".git").write_text("gitdir: ../.git/worktrees/wt\n", encoding="utf-8")
    assert ws.find_git_root(tmp_path) == str(tmp_path)


def test_find_git_root_none_outside_a_repo(tmp_path: Path) -> None:
    assert ws.find_git_root(tmp_path) is None


# --------------------------- source file decoding ---------------------------


@pytest.mark.parametrize(
    ("raw", "expected_name"),
    [
        (b"\xef\xbb\xbfforward\r\n", "utf8"),
        (b"\xff\xfef\x00o\x00r\x00", "unicode"),
        (b"forward\r\n", "utf8"),
    ],
)
def test_decode_source_bytes_recognizes_the_bom(raw: bytes, expected_name: str) -> None:
    _text, name = ws.decode_source_bytes(raw, fallback="utf8")
    assert name == expected_name


def test_decode_preserves_crlf(tmp_path: Path) -> None:
    """The whole point: LF-normalized text imported into a .pbl rewrites every
    line and shows up as a whole-file phantom diff later."""
    path = tmp_path / "w_main.srw"
    path.write_bytes(b"\xef\xbb\xbfforward\r\nglobal type w_main\r\n")
    text, _name = ws.read_source_file(path)
    assert "\r\n" in text
    assert "\n\n" not in text


def test_decode_strips_the_bom_from_the_text(tmp_path: Path) -> None:
    path = tmp_path / "w_main.srw"
    path.write_bytes(b"\xef\xbb\xbfforward\r\n")
    text, _name = ws.read_source_file(path)
    assert text.startswith("forward")


def test_ansi_file_decodes_without_a_bom(tmp_path: Path) -> None:
    path = tmp_path / "w_main.srw"
    path.write_bytes(b"forward\r\n// caff\xe8\r\n")  # cp1252 e-grave
    text, name = ws.read_source_file(path, fallback="ansi")
    assert name == "ansi"
    assert "caff" in text


# --------------------------- export headers ---------------------------


def test_strip_export_headers_returns_body_and_comment() -> None:
    text = "$PBExportHeader$w_main.srw\r\n$PBExportComments$Main window\r\nforward\r\nend\r\n"
    body, comment = ws.strip_export_headers(text)
    assert comment == "Main window"
    assert body.startswith("forward")


def test_strip_export_headers_on_a_body_that_has_none() -> None:
    body, comment = ws.strip_export_headers("forward\r\nglobal type w_main\r\n")
    assert comment is None
    assert body.startswith("forward")


def test_strip_export_headers_keeps_a_dollar_line_inside_the_body() -> None:
    """Only the leading header lines are consumed; anything after the body
    starts is source, even if it looks similar."""
    text = "$PBExportHeader$w.srw\r\nforward\r\n$PBExportComments$ not a header\r\n"
    body, _comment = ws.strip_export_headers(text)
    assert "$PBExportComments$ not a header" in body


# --- Line-ending protection -------------------------------------------------
#
# The property these pin is the one that hid a real defect three times: git
# translating .sr* line endings means `git status` can stay clean while the
# .pbl and its projection disagree, so a correct write looks like a no-op.


def _git_repo(tmp_path: Path, attributes: str | None = None) -> Path:
    """A directory that `find_git_root` accepts, optionally with attributes."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".git").mkdir()
    if attributes is not None:
        (tmp_path / ".gitattributes").write_text(attributes, encoding="utf-8")
    return tmp_path


def test_protection_reports_no_git_outside_a_working_tree(tmp_path: Path) -> None:
    assert ws.line_ending_protection(tmp_path, None) == ws.PROTECTION_NO_GIT


def test_protection_unprotected_without_gitattributes(tmp_path: Path) -> None:
    root = _git_repo(tmp_path)
    assert ws.line_ending_protection(root, str(root)) == ws.PROTECTION_UNPROTECTED


@pytest.mark.parametrize(
    "rule",
    [
        "*.sr* binary\n",
        "*.sr* -text\n",
        "*.sr* text=false\n",
        "*.sr* text eol=crlf\n",
        # Every extension spelled out instead of the glob.
        "".join(f"*.sr{c} binary\n" for c in "adfmqsuw"),
    ],
)
def test_protection_recognizes_every_way_of_exempting_sources(tmp_path: Path, rule: str) -> None:
    root = _git_repo(tmp_path, rule)
    assert ws.line_ending_protection(root, str(root)) == ws.PROTECTION_PROTECTED


def test_text_auto_alone_is_not_protection(tmp_path: Path) -> None:
    """`* text=auto eol=lf` is the common setup that causes the problem.

    It looks deliberate, which is why it is worth a test: it configures the
    translation rather than exempting anything from it.
    """
    root = _git_repo(tmp_path, "* text=auto eol=lf\n")
    assert ws.line_ending_protection(root, str(root)) == ws.PROTECTION_UNPROTECTED


def test_eol_lf_is_not_protection(tmp_path: Path) -> None:
    """The trap: a deliberate line-ending policy that is the wrong one.

    ORCA writes CRLF. With `eol=lf` git hands the file back as LF on every
    checkout, so the projection and the .pbl disagree permanently. `eol=crlf`
    is the same policy pointed the safe way.
    """
    root = _git_repo(tmp_path / "lf", "*.sr* text eol=lf\n")
    assert ws.line_ending_protection(root, str(root)) == ws.PROTECTION_UNPROTECTED

    root2 = _git_repo(tmp_path / "crlf", "*.sr* text eol=crlf\n")
    assert ws.line_ending_protection(root2, str(root2)) == ws.PROTECTION_PROTECTED


def test_last_matching_line_wins(tmp_path: Path) -> None:
    """git resolves attributes with the last match, so a later rule can undo."""
    root = _git_repo(tmp_path, "*.sr* binary\n* text=auto\n")
    assert ws.line_ending_protection(root, str(root)) == ws.PROTECTION_UNPROTECTED

    root2 = _git_repo(tmp_path / "b", "* text=auto\n*.sr* binary\n")
    assert ws.line_ending_protection(root2, str(root2)) == ws.PROTECTION_PROTECTED


def test_partial_coverage_is_not_protection(tmp_path: Path) -> None:
    """Exempting only some extensions leaves the rest translated.

    A half-covered tree is the worst case to report as safe: the files that
    are still translated are exactly the ones nobody will think to check.
    """
    root = _git_repo(tmp_path, "*.srw binary\n*.sru binary\n")
    assert ws.line_ending_protection(root, str(root)) == ws.PROTECTION_UNPROTECTED


def test_comments_and_blank_lines_are_ignored(tmp_path: Path) -> None:
    root = _git_repo(tmp_path, "# keep PB sources byte-exact\n\n*.sr* binary\n")
    assert ws.line_ending_protection(root, str(root)) == ws.PROTECTION_PROTECTED


def test_deeper_gitattributes_overrides_the_root(tmp_path: Path) -> None:
    root = _git_repo(tmp_path, "* text=auto eol=lf\n")
    deep = root / "ws_objects" / "app.pbl.src"
    deep.mkdir(parents=True)
    (deep / ".gitattributes").write_text("*.sr* binary\n", encoding="utf-8")
    assert ws.line_ending_protection(deep, str(root)) == ws.PROTECTION_PROTECTED


def test_describe_surfaces_protection_and_warns_in_advice(tmp_path: Path) -> None:
    root = _git_repo(tmp_path)
    _pbw(root)
    lib = root / "app.pbl"
    lib.write_bytes(b"")
    _source_file(root / ws.WS_OBJECTS_DIRNAME / "app.pbl.src", "w_main.srw")

    info = ws.describe(lib)
    assert info.source_protection == ws.PROTECTION_UNPROTECTED
    assert "WARNING" in info.advice
    assert "renormalize" in info.advice
    # The layout advice is still there — the warning leads, it does not replace.
    assert "Text projection present" in info.advice
    assert info.to_dict()["source_protection"] == ws.PROTECTION_UNPROTECTED

    (root / ".gitattributes").write_text("*.sr* binary\n", encoding="utf-8")
    clean = ws.describe(lib)
    assert clean.source_protection == ws.PROTECTION_PROTECTED
    assert "WARNING" not in clean.advice
