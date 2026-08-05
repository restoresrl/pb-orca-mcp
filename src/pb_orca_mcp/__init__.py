"""pb-orca-mcp — MCP server exposing PowerBuilder's ORCA API to MCP clients."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _installed_version

try:
    # Single source of truth: the version declared in pyproject.toml and
    # recorded in the installed distribution's metadata. Hardcoding it here
    # meant `--version` reported 0.1.0 from a 0.2.0 install, which is a
    # debugging trap in a project whose whole point is pinning a known build.
    __version__ = _installed_version("pb-orca-mcp")
except PackageNotFoundError:  # running from a source tree, not installed
    __version__ = "0.0.0+source"
