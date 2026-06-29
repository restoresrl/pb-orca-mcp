"""CLI for the PowerScript body formatter (the ``pb-format`` console script).

Three subcommands, all usable without an ORCA session or a running PB
install — they operate purely on ``.sr*`` files on disk:

- ``pb-format detect [PATH]`` — sample the workspace and write a starter
  ``.pb-format.toml`` (see :mod:`pb_orca_mcp.format.detect`).
- ``pb-format format PATHS...`` — normalize the body of each ``.sr*``
  file in place, preserving its export header and on-disk encoding.
- ``pb-format check PATHS...`` — report which files *would* change
  without writing; exit non-zero if any would (for pre-commit / CI).

The file-level formatting here is deliberately separate from
``pb_edit_and_import``: that tool rebuilds the ``$PBExportHeader$`` block
from caller-supplied metadata while importing into a PBL, whereas this
CLI edits a file that already exists on disk. So it must *preserve* the
existing header and encoding rather than regenerate them, and it never
touches ORCA.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from pathlib import Path

import click

from pb_orca_mcp import __version__
from pb_orca_mcp.format import (
    CONFIG_FILENAME,
    SOURCE_EXTENSIONS,
    FormatConfig,
    detect_workspace_style,
    discover_config,
    format_powerscript,
    write_config_file,
)

# UTF-16 LE is what PB IDE writes by default; some workspaces use UTF-8
# (with or without BOM) via the .pbw DefaultExportEncode directive. We
# detect the encoding from the BOM and round-trip it unchanged.
_BOM_UTF16_LE = b"\xff\xfe"
_BOM_UTF8 = b"\xef\xbb\xbf"

_ENC_UTF16_LE_BOM = "utf-16le-bom"
_ENC_UTF8_BOM = "utf-8-bom"
_ENC_UTF8 = "utf-8"

_NEWLINE_RE = re.compile(r"\r\n?|\n")
_HEADER_PREFIX = "$PBExport"


@click.group(invoke_without_command=False)
@click.version_option(__version__, prog_name="pb-format")
def cli() -> None:
    """pb-format — normalize PowerScript source style.

    A workspace opts in to a specific style by committing a
    ``.pb-format.toml`` file (generate one with ``pb-format detect``).
    The four invariants enforced — indent, line endings, keyword case,
    operator spacing — are documented in ``docs/formatter.md``.
    """


@cli.command()
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".",
)
@click.option(
    "--max-files",
    type=click.IntRange(min=1),
    default=50,
    show_default=True,
    help="Maximum number of source files to sample.",
)
@click.option(
    "--force",
    is_flag=True,
    help=f"Overwrite an existing {CONFIG_FILENAME}.",
)
def detect(path: Path, max_files: int, force: bool) -> None:
    """Sample PATH (default: cwd) and write a starter .pb-format.toml.

    The generated file is a *starting point* — it carries the raw vote
    tallies as comments so you can review the inferred style before
    committing it.
    """
    target = path / CONFIG_FILENAME
    if target.exists() and not force:
        raise click.ClickException(f"{target} already exists; pass --force to overwrite it.")

    result = detect_workspace_style(path, max_files=max_files)
    if result.files_scanned == 0:
        raise click.ClickException(
            f"No PowerScript source files found under {path} "
            f"(looked for {', '.join(sorted(SOURCE_EXTENSIONS))})."
        )

    written = write_config_file(path, result)
    click.echo(f"Scanned {result.files_scanned} source file(s).")
    click.echo(f"  indent          : {result.indent_votes or '(no samples)'}")
    click.echo(f"  keyword_case    : {result.keyword_case_votes or '(no samples)'}")
    click.echo(f"  spaces_around_op: {result.spaces_around_ops_votes or '(no samples)'}")
    click.echo(f"Wrote {written}")
    click.echo("Review the generated file before committing it.")


@cli.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(path_type=Path))
@click.option(
    "--config",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Use this .pb-format.toml for every file (skip per-file discovery).",
)
@click.option(
    "-n",
    "--dry-run",
    is_flag=True,
    help="Show what would change without writing.",
)
def format(paths: tuple[Path, ...], config: Path | None, dry_run: bool) -> None:
    """Normalize the body of each .sr* file in PATHS, in place.

    PATHS may be files or directories (directories are scanned
    recursively for .sr* sources). The export header and the file's
    on-disk encoding are preserved; only the entry body is normalized.

    Config resolution: ``--config`` if given, else the nearest
    ``.pb-format.toml`` found walking up from each file, else the
    engine defaults (tab indent, lowercase keywords, CRLF, spaces).
    """
    forced = _load_forced_config(config)
    changed = 0
    unchanged = 0
    for file in _iter_files(paths):
        try:
            cfg = forced if forced is not None else _resolve_file_config(file)
            new_bytes, did_change = _format_file_bytes(file, cfg)
        except ValueError as exc:
            raise click.ClickException(f"{file}: {exc}") from exc
        if did_change:
            changed += 1
            if not dry_run:
                file.write_bytes(new_bytes)
            verb = "would reformat" if dry_run else "reformatted"
            click.echo(f"{verb}: {file}")
        else:
            unchanged += 1

    suffix = " (dry run, nothing written)" if dry_run else ""
    click.echo(f"{changed} reformatted, {unchanged} already formatted{suffix}.")


@cli.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(path_type=Path))
@click.option(
    "--config",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Use this .pb-format.toml for every file (skip per-file discovery).",
)
def check(paths: tuple[Path, ...], config: Path | None) -> None:
    """Report which .sr* files would change; exit non-zero if any would.

    Writes nothing. Intended for pre-commit hooks and CI: a clean tree
    exits 0, a tree needing reformatting exits 1 and lists the files.
    """
    forced = _load_forced_config(config)
    would_change = []
    total = 0
    for file in _iter_files(paths):
        total += 1
        try:
            cfg = forced if forced is not None else _resolve_file_config(file)
            _, did_change = _format_file_bytes(file, cfg)
        except ValueError as exc:
            raise click.ClickException(f"{file}: {exc}") from exc
        if did_change:
            would_change.append(file)
            click.echo(f"would reformat: {file}")

    if would_change:
        click.echo(f"{len(would_change)} of {total} file(s) would be reformatted.")
        sys.exit(1)
    click.echo(f"All {total} file(s) already formatted.")


# --- helpers ---------------------------------------------------------------


def _load_forced_config(config: Path | None) -> FormatConfig | None:
    if config is None:
        return None
    try:
        return FormatConfig.from_path(config)
    except ValueError as exc:
        raise click.ClickException(f"{config}: {exc}") from exc


def _resolve_file_config(file: Path) -> FormatConfig:
    """Per-file config: nearest .pb-format.toml, or engine defaults.

    Unlike ``pb_edit_and_import`` in ``auto`` mode, an explicit
    ``pb-format`` invocation always formats — so a missing config falls
    back to defaults rather than skipping the file.
    """
    config_path = discover_config(file)
    if config_path is None:
        return FormatConfig.default()
    return FormatConfig.from_path(config_path)


def _iter_files(paths: tuple[Path, ...]) -> Iterator[Path]:
    """Yield .sr* files from the given file/directory paths, in order."""
    for path in paths:
        if not path.exists():
            raise click.ClickException(f"path does not exist: {path}")
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in SOURCE_EXTENSIONS:
                    yield child
        elif path.suffix.lower() in SOURCE_EXTENSIONS:
            yield path
        else:
            # An explicitly named file with an unsupported extension is a
            # user error worth surfacing (a directory scan silently skips).
            raise click.ClickException(
                f"{path}: not a PowerScript source file "
                f"(expected one of {', '.join(sorted(SOURCE_EXTENSIONS))})."
            )


def _format_file_bytes(file: Path, config: FormatConfig) -> tuple[bytes, bool]:
    """Return the normalized bytes for ``file`` and whether they differ.

    Preserves the ``$PBExportHeader$`` / ``$PBExportComments$`` block and
    the file's BOM-detected encoding; only the entry body is normalized.
    """
    raw = file.read_bytes()
    text, encoding = _decode(raw)
    header, body = _split_header(text)
    formatted_body = format_powerscript(body, config)
    sep = "\r\n" if config.line_endings == "crlf" else "\n"
    header = _NEWLINE_RE.sub(sep, header)
    new_text = header + formatted_body
    new_bytes = _encode(new_text, encoding)
    return new_bytes, new_bytes != raw


def _decode(raw: bytes) -> tuple[str, str]:
    if raw.startswith(_BOM_UTF16_LE):
        return raw[2:].decode("utf-16-le"), _ENC_UTF16_LE_BOM
    if raw.startswith(_BOM_UTF8):
        return raw[3:].decode("utf-8"), _ENC_UTF8_BOM
    return raw.decode("utf-8"), _ENC_UTF8


def _encode(text: str, encoding: str) -> bytes:
    if encoding == _ENC_UTF16_LE_BOM:
        return _BOM_UTF16_LE + text.encode("utf-16-le")
    if encoding == _ENC_UTF8_BOM:
        return _BOM_UTF8 + text.encode("utf-8")
    return text.encode("utf-8")


def _split_header(text: str) -> tuple[str, str]:
    """Split leading ``$PBExport*`` lines (header) from the entry body.

    Returns ``(header, body)`` where ``header`` keeps its trailing
    newline so ``header + body == text``. A file with no header (a bare
    body fragment) returns ``("", text)``.
    """
    pos = 0
    n = len(text)
    while text.startswith(_HEADER_PREFIX, pos):
        match = _NEWLINE_RE.search(text, pos)
        if match is None:  # header line with no trailing newline (EOF)
            pos = n
            break
        pos = match.end()
    return text[:pos], text[pos:]


if __name__ == "__main__":
    cli()
