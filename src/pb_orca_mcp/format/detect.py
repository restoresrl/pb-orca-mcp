"""Frequency-based auto-detect of PowerScript style from a workspace.

Used by the ``pb-format detect`` CLI to produce a starter
``.pb-format.toml``. The detector samples a handful of source files,
counts votes per style dimension, and picks the most popular option per
dimension independently. The result is a *starting point*, not a
verdict — the user is expected to review the generated file before
committing it.

Sampling deliberately stops at ``max_files`` (default 50): on a real
PB workspace with thousands of entries, a small uniform sample
identifies the dominant convention reliably and keeps detection well
under a second.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast, get_args

from pb_orca_mcp.format.config import (
    CONFIG_FILENAME,
    FormatConfig,
    KeywordCase,
)
from pb_orca_mcp.format.keywords import RESERVED
from pb_orca_mcp.format.lexer import TokenKind, tokenize

# Extensions of PowerScript source files PB exports as text. ``.srd``
# is intentionally excluded: DataWindow sources are a different mini-DSL
# and the formatter must not touch them.
SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {".sra", ".sru", ".srw", ".srf", ".srs", ".srj", ".srm", ".srq"}
)


@dataclass(frozen=True)
class DetectionResult:
    """Vote tallies + the ``FormatConfig`` derived from them."""

    config: FormatConfig
    files_scanned: int
    indent_votes: dict[str, int] = field(default_factory=dict)
    keyword_case_votes: dict[str, int] = field(default_factory=dict)
    spaces_around_ops_votes: dict[str, int] = field(default_factory=dict)


def detect_workspace_style(root: Path, max_files: int = 50) -> DetectionResult:
    """Sample up to ``max_files`` source files under ``root`` and derive
    a ``FormatConfig`` from the observed frequencies."""
    indent_votes: Counter[str] = Counter()
    case_votes: Counter[str] = Counter()
    op_votes: Counter[str] = Counter()
    scanned = 0

    for path in _iter_sources(root, max_files):
        try:
            text = _read_source(path)
        except OSError:
            continue
        scanned += 1
        _vote_indent(text, indent_votes)
        _vote_keyword_case(text, case_votes)
        _vote_operator_spacing(text, op_votes)

    indent_choice = _winner(indent_votes, "tab")
    case_choice_raw = _winner(case_votes, "lower")
    case_choice: KeywordCase = cast(
        KeywordCase,
        case_choice_raw if case_choice_raw in get_args(KeywordCase) else "lower",
    )
    spaces_choice_raw = _winner(op_votes, "true")
    spaces_choice = spaces_choice_raw == "true"

    if indent_choice == "tab":
        cfg = FormatConfig(
            indent_style="tab",
            keyword_case=case_choice,
            spaces_around_operators=spaces_choice,
        )
    else:
        n_spaces = int(indent_choice.split(":", 1)[1])
        cfg = FormatConfig(
            indent_style="spaces",
            indent_spaces=n_spaces,
            keyword_case=case_choice,
            spaces_around_operators=spaces_choice,
        )

    return DetectionResult(
        config=cfg,
        files_scanned=scanned,
        indent_votes=dict(indent_votes),
        keyword_case_votes=dict(case_votes),
        spaces_around_ops_votes=dict(op_votes),
    )


def write_config_file(target_dir: Path, result: DetectionResult) -> Path:
    """Write ``result`` as ``<target_dir>/.pb-format.toml``.

    Emits commented-out vote tallies so a reviewer can audit the choices.
    """
    cfg = result.config
    indent_str = "tab" if cfg.indent_style == "tab" else f"spaces:{cfg.indent_spaces}"
    indent_votes = _format_votes(result.indent_votes)
    case_votes = _format_votes(result.keyword_case_votes)
    op_votes = _format_votes(result.spaces_around_ops_votes)
    body = (
        "# pb-format style for this PowerBuilder workspace.\n"
        f"# Auto-generated from {result.files_scanned} sampled source files.\n"
        "# Review and edit before committing — this is just a starting point.\n"
        "\n"
        "[style]\n"
        f"# indent votes: {indent_votes}\n"
        f'indent = "{indent_str}"\n'
        "\n"
        f"# keyword_case votes: {case_votes}\n"
        f'keyword_case = "{cfg.keyword_case}"\n'
        "\n"
        f"# spaces_around_operators votes: {op_votes}\n"
        f"spaces_around_operators = {str(cfg.spaces_around_operators).lower()}\n"
        "\n"
        "# CRLF is the format PB IDE writes on export — keep this locked.\n"
        'line_endings = "crlf"\n'
    )
    target = target_dir / CONFIG_FILENAME
    target.write_text(body, encoding="utf-8")
    return target


def _iter_sources(root: Path, max_files: int) -> Iterator[Path]:
    count = 0
    for path in sorted(root.rglob("*")):
        if count >= max_files:
            return
        if not path.is_file():
            continue
        if path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        yield path
        count += 1


def _read_source(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe"):
        return raw[2:].decode("utf-16-le", errors="replace")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace")
    return raw.decode("utf-8", errors="replace")


_LEADING_RE = re.compile(r"^([ \t]+)\S", re.MULTILINE)


def _vote_indent(text: str, votes: Counter[str]) -> None:
    for match in _LEADING_RE.finditer(text):
        run = match.group(1)
        if "\t" in run:
            votes["tab"] += 1
            continue
        n = len(run)
        # Bucket by likely unit (favour 4, then 2, then exact width).
        for unit in (4, 2):
            if n % unit == 0:
                votes[f"spaces:{unit}"] += 1
                break
        else:
            votes[f"spaces:{n}"] += 1


def _vote_keyword_case(text: str, votes: Counter[str]) -> None:
    for tok in tokenize(text):
        if tok.kind != TokenKind.WORD:
            continue
        if tok.text.lower() not in RESERVED:
            continue
        if tok.text == tok.text.lower():
            votes["lower"] += 1
        elif tok.text == tok.text.upper():
            votes["upper"] += 1
        else:
            votes["mixed"] += 1


def _vote_operator_spacing(text: str, votes: Counter[str]) -> None:
    tokens = list(tokenize(text))
    for i, tok in enumerate(tokens):
        if tok.kind != TokenKind.OP or tok.text != "=":
            continue
        prev_tok = tokens[i - 1] if i > 0 else None
        next_tok = tokens[i + 1] if i + 1 < len(tokens) else None
        if prev_tok is None or next_tok is None:
            continue
        has_space_before = prev_tok.kind == TokenKind.WHITESPACE
        has_space_after = next_tok.kind == TokenKind.WHITESPACE
        if has_space_before and has_space_after:
            votes["true"] += 1
        elif not has_space_before and not has_space_after:
            votes["false"] += 1


def _winner(votes: Counter[str], default: str) -> str:
    if not votes:
        return default
    return votes.most_common(1)[0][0]


def _format_votes(votes: dict[str, int]) -> str:
    if not votes:
        return "{} (no samples)"
    items = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))
    return "{" + ", ".join(f"{k!r}: {v}" for k, v in items) + "}"
