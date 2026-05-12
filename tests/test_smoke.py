"""Phase 1 smoke tests: package imports cleanly, version is set, CLI exits."""

from __future__ import annotations

from click.testing import CliRunner


def test_package_imports() -> None:
    import pb_orca_mcp

    assert pb_orca_mcp.__version__


def test_orca_submodule_imports() -> None:
    from pb_orca_mcp.orca import constants, dll, errors

    assert constants.PBORCA_OK == 0
    assert "19.0" in dll.KNOWN_VERSIONS
    assert "22.0" in dll.KNOWN_VERSIONS
    assert "25.0" in dll.KNOWN_VERSIONS
    assert errors.OrcaError(1, "X", "msg").code == 1


def test_cli_version() -> None:
    from pb_orca_mcp.__main__ import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "pb-orca-mcp" in result.output


def test_cli_doctor_stub_exits_nonzero() -> None:
    """Phase 1 stub: doctor is not implemented yet, exits 2."""
    from pb_orca_mcp.__main__ import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["doctor"])
    assert result.exit_code == 2


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
