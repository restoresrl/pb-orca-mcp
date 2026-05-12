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


def test_server_exposes_23_tools() -> None:
    """Every PLAN tool is wired through to the MCP server."""
    from pb_orca_mcp.server import tool_names

    names = tool_names()
    assert len(names) == 23
    # Anchor a few names so a rename or accidental drop fails loudly.
    assert "pb_discover_pb_install" in names
    assert "pb_compile_entry_import" in names
    assert "pb_application_rebuild" in names
    assert "pb_executable_create" in names
    assert "pb_object_query_hierarchy" in names


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
