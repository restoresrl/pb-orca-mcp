"""Shared pytest fixtures for pb-orca-mcp.

Fixtures that require a real PowerBuilder installation live here behind the
`requires_pb` marker. CI skips them; local runs on a developer machine with
PB installed exercise them.
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip `requires_pb` tests unless PB_INSTALL_PATH or a discovery hit is available."""
    import os

    if os.environ.get("PB_ORCA_MCP_HAS_PB") == "1":
        return  # operator says PB is installed → run all
    skip_marker = pytest.mark.skip(
        reason="No PowerBuilder install detected; set PB_ORCA_MCP_HAS_PB=1 to run"
    )
    for item in items:
        if "requires_pb" in item.keywords:
            item.add_marker(skip_marker)
