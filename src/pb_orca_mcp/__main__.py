"""CLI entry point for pb-orca-mcp.

Invoked by the `pb-orca-mcp` console script (see pyproject.toml [project.scripts]).
"""

from __future__ import annotations

import sys

import click

from pb_orca_mcp import __version__


@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="pb-orca-mcp")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """pb-orca-mcp — MCP server for PowerBuilder ORCA."""
    if ctx.invoked_subcommand is None:
        # No subcommand → run the MCP server on stdio (default behavior for MCP servers).
        ctx.invoke(serve)


@cli.command()
def serve() -> None:
    """Run the MCP server on stdio (default when no subcommand is given)."""
    # Phase 1 stub — actual server wiring lands in phase 3.
    click.echo("pb-orca-mcp: server not implemented yet (phase 1 scaffolding)", err=True)
    sys.exit(2)


@cli.command()
def doctor() -> None:
    """Diagnose the local PowerBuilder installation(s)."""
    # Phase 1 stub — discovery lands in phase 2.
    click.echo("pb-orca-mcp doctor: not implemented yet (phase 1 scaffolding)", err=True)
    sys.exit(2)


if __name__ == "__main__":
    cli()
