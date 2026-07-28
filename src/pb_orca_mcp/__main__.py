"""CLI entry point for pb-orca-mcp.

Invoked by the `pb-orca-mcp` console script (see pyproject.toml [project.scripts]).
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from pb_orca_mcp import __version__


@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="pb-orca-mcp")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """pb-orca-mcp — MCP server for PowerBuilder ORCA."""
    if ctx.invoked_subcommand is None:
        # No subcommand → run the MCP server on stdio (the standard MCP behavior).
        ctx.invoke(serve)


@cli.command()
def serve() -> None:
    """Run the MCP server on stdio (default when no subcommand is given)."""
    from pb_orca_mcp.server import run_stdio

    run_stdio()


@cli.command()
@click.argument("target", type=click.Path())
@click.option("--pb-version", default=None, help='PowerBuilder version to use, e.g. "22.0".')
@click.option("--install-path", default=None, help="Exact PB install directory to use.")
def check(target: str, pb_version: str | None, install_path: str | None) -> None:
    """Verify pb-orca works against YOUR project. TARGET is a .pbw, .pbt or .pbl.

    `doctor` tells you PowerBuilder is installed and ORCA loads. This tells you
    the thing you actually want to know: that the whole stack works on the
    project in front of you. It parses the target, detects the workspace
    layout, opens a real ORCA session, reads the library, and exports one
    object to a temporary directory to confirm the bytes come out right.

    Nothing in the project is modified. It deliberately stops short of the
    compile path, which needs the current application set, and ORCA can rewrite
    the .pbw as a side effect of that.
    """
    from pb_orca_mcp.check import CheckError, format_failure, format_report, preamble, run_check

    click.echo(preamble())
    try:
        report = run_check(target, pb_version=pb_version, install_path=install_path)
    except CheckError as exc:
        click.echo("")
        click.echo(format_failure(exc), err=True)
        sys.exit(1)
    click.echo(format_report(report, Path(target).name))


@cli.command()
def doctor() -> None:
    """Diagnose the local PowerBuilder installation(s).

    Lists every PB IDE install on this machine, marks tested vs untested
    majors, attempts a `pborc.dll` load for each arch-compatible install,
    and exits non-zero if no usable install is found.
    """
    import struct

    from pb_orca_mcp.discovery import discover_pb_installations
    from pb_orca_mcp.orca.dll import OrcaArchMismatchError, OrcaLoadError, load_orca

    py_arch = "x86" if struct.calcsize("P") == 4 else "x64"
    click.echo(f"pb-orca-mcp {__version__}")
    click.echo(f"Python: {sys.version.split()[0]} ({py_arch})")
    click.echo("")

    ides, runtime_only = discover_pb_installations()

    if not ides:
        click.echo("No PowerBuilder IDE installation found.", err=True)
        if runtime_only:
            click.echo("Runtime-only installs detected (no pborc.dll):", err=True)
            for r in runtime_only:
                click.echo(f"  - {r.path} ({r.reason})", err=True)
        click.echo("", err=True)
        click.echo(
            "Install PowerBuilder IDE (2019 R3+) and ensure pborc.dll exists "
            "under <install>\\IDE\\.",
            err=True,
        )
        sys.exit(1)

    # The first arch-compatible install is the only one we attempt to load:
    # Windows caches DLLs by basename, so the version-keyed `pbvm.dll`,
    # `pbshr.dll` etc. from one PB install poison the namespace for any
    # subsequent install loaded in the same process. The doctor lists
    # everything and marks load status accordingly.
    load_attempted = False
    usable = 0
    for inst in ides:
        marker = "[OK]" if inst.tested else "[??]"
        click.echo(f"{marker} PB {inst.version}  [{inst.arch}]  {inst.install_path}")
        click.echo(f"    file_version : {inst.file_version or '(unknown)'}")
        click.echo(f"    product      : {inst.product_version or '(unknown)'}")
        click.echo(f"    source       : {inst.source}")
        click.echo(f"    runtime      : {inst.runtime_path or '(not found)'}")

        if inst.arch != py_arch:
            click.echo(
                f"    skip load    : Python is {py_arch}, DLL is {inst.arch} "
                "(install matching Python)"
            )
            click.echo("")
            continue
        if load_attempted:
            click.echo(
                "    skip load    : another PB install already loaded in this "
                "process (single PB runtime per process)"
            )
            click.echo("")
            continue
        load_attempted = True
        try:
            api = load_orca(inst)
        except OrcaArchMismatchError as exc:
            click.echo(f"    load failed  : {exc}")
        except OrcaLoadError as exc:
            click.echo(f"    load failed  : {exc}")
        else:
            click.echo("    load         : OK (session entry points bound)")
            click.echo(
                f"    api          : session={bool(api.session.SessionOpen)} "
                f"library={bool(api.library.LibraryCreate)}"
            )
            usable += 1
        click.echo("")

    if runtime_only:
        click.echo("Runtime-only installs (skipped):")
        for r in runtime_only:
            click.echo(f"  - {r.path}")
        click.echo("")

    if usable == 0:
        click.echo(
            f"No PB install is usable from this Python ({py_arch}). "
            f"Install a matching-arch Python interpreter and retry.",
            err=True,
        )
        sys.exit(1)
    click.echo(f"Doctor OK: {usable} usable install(s) for {py_arch} Python.")


if __name__ == "__main__":
    cli()
