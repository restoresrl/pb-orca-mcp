"""Phase 1 smoke tests: package imports cleanly, version is set, CLI exits."""

from __future__ import annotations

from click.testing import CliRunner


def test_package_imports() -> None:
    import pb_orca_mcp

    assert pb_orca_mcp.__version__


def test_orca_submodule_imports() -> None:
    from pb_orca_mcp.orca import constants, dll, errors, session

    assert constants.PBORCA_OK == 0
    assert "19.0" in dll.KNOWN_VERSIONS
    assert "22.0" in dll.KNOWN_VERSIONS
    assert "25.0" in dll.KNOWN_VERSIONS
    assert errors.OrcaError(1, "X", "msg").code == 1
    assert constants.ORCA_ERROR_NAMES[-3] == "PBORCA_OBJNOTFOUND"
    # Singleton: instance() returns the same object across calls.
    session.Session._instance = None
    assert session.Session.instance() is session.Session.instance()


def test_cli_version() -> None:
    from pb_orca_mcp.__main__ import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "pb-orca-mcp" in result.output


def test_cli_doctor_runs_to_completion() -> None:
    """`doctor` enumerates PB installs and exits cleanly.

    Exit code is 0 if at least one arch-compatible IDE was loaded, else 1.
    On CI without PB or on x64 Python with only x86 installs, expect 1 —
    either way `doctor` must not crash and must emit version/arch info.
    """
    from pb_orca_mcp.__main__ import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["doctor"])
    assert result.exit_code in (0, 1)
    assert "pb-orca-mcp" in result.output
    assert "Python:" in result.output


def test_server_exposes_all_tools() -> None:
    """Every tool is wired through to the MCP server.

    Current count: 23 ORCA tools + 6 SCC offline-mode tools + 5 workspace /
    source-file tools = 34. Bump it when adding or removing a tool; the
    matching entry in `docs/tools.md` is enforced by `test_docs_in_sync`.
    """
    from pb_orca_mcp.server import tool_names

    names = tool_names()
    assert len(names) == 34
    # Anchor a few names so a rename or accidental drop fails loudly.
    assert "pb_discover_pb_install" in names
    assert "pb_compile_entry_import" in names
    assert "pb_application_rebuild" in names
    assert "pb_executable_create" in names
    assert "pb_object_query_hierarchy" in names
    assert "pb_workspace_info" in names
    assert "pb_object_export_file" in names
    assert "pb_object_import_file" in names
    assert "pb_scc_connect_offline" in names
    assert "pb_scc_refresh_target" in names


def test_server_actually_builds() -> None:
    """`build_server()` constructs the real FastMCP server and registers all 34.

    `test_server_exposes_all_tools` only reads the registry tuple, which needs
    no MCP import at all — so the whole suite passed green against an `mcp`
    release that had dropped `mcp.server.fastmcp`, and the failure surfaced
    only when a client started the server over stdio. `doctor` and `check`
    do not import it either, which is why the CLI looked healthy. This test
    performs the import and the registration, so a resolution the server
    cannot run on fails here instead of in a user's editor.
    """
    import asyncio

    from pb_orca_mcp.server import build_server

    tools = asyncio.run(build_server().list_tools())
    assert len(tools) == 34
    assert "pb_workspace_info" in {t.name for t in tools}


def test_discovery_is_importable_and_returns_tuple() -> None:
    """Phase 2: `discover_pb_installations()` is callable everywhere.

    On CI / non-Windows hosts it just returns two empty lists; on a dev
    machine with PB installed it returns populated ones. Either is fine
    here — we only check the contract.
    """
    from pb_orca_mcp.discovery import discover_pb_installations

    ides, runtime = discover_pb_installations()
    assert isinstance(ides, list)
    assert isinstance(runtime, list)
