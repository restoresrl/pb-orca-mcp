"""MCP server bootstrap — registers every `pb_*` tool with FastMCP.

`build_server()` returns a configured `FastMCP` instance. `run_stdio()` is
the entry point used by the CLI (`pb-orca-mcp serve`).

FastMCP introspects each tool function's signature and docstring to derive
the input/output schema and tool description automatically. The wrappers
themselves live in `pb_orca_mcp.tools.*`; this module only assembles them.

The MCP `stdio` transport runs each tool call sequentially in a single
event loop — ORCA's single-session-per-process / not-thread-safe
constraints are naturally honored without additional locking. If a future
transport (SSE, streamable-http) introduces concurrency, the `asyncio.Lock`
exposed by `Session.lock` is the integration point.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from pb_orca_mcp.tools import build as build_tools
from pb_orca_mcp.tools import compile as compile_tools
from pb_orca_mcp.tools import discovery as discovery_tools
from pb_orca_mcp.tools import library as library_tools
from pb_orca_mcp.tools import query as query_tools
from pb_orca_mcp.tools import session as session_tools

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


# Tool registry: tuples of (callable, MCP tool name). The names mirror the
# PLAN's §"Tool MCP esposti" table 1:1. Adding a new tool here also picks
# up its docstring as the MCP-visible description.
_TOOLS: tuple[tuple[Callable[..., object], str], ...] = (
    # Discovery
    (discovery_tools.pb_discover_pb_install, "pb_discover_pb_install"),
    (discovery_tools.pb_target_info, "pb_target_info"),
    # Session
    (session_tools.pb_session_open, "pb_session_open"),
    (session_tools.pb_session_close, "pb_session_close"),
    (session_tools.pb_set_current_application, "pb_set_current_application"),
    (session_tools.pb_set_library_list, "pb_set_library_list"),
    # Library
    (library_tools.pb_library_create, "pb_library_create"),
    (library_tools.pb_library_delete, "pb_library_delete"),
    (library_tools.pb_library_directory, "pb_library_directory"),
    (library_tools.pb_library_entry_information, "pb_library_entry_information"),
    (library_tools.pb_library_entry_export, "pb_library_entry_export"),
    (library_tools.pb_library_entry_delete, "pb_library_entry_delete"),
    (library_tools.pb_library_entry_move, "pb_library_entry_move"),
    (library_tools.pb_library_comment_modify, "pb_library_comment_modify"),
    # Compile
    (compile_tools.pb_compile_entry_import, "pb_compile_entry_import"),
    (compile_tools.pb_compile_entry_import_list, "pb_compile_entry_import_list"),
    (compile_tools.pb_application_rebuild, "pb_application_rebuild"),
    (compile_tools.pb_get_last_compile_errors, "pb_get_last_compile_errors"),
    # Build artifacts
    (build_tools.pb_executable_create, "pb_executable_create"),
    (build_tools.pb_dynamic_library_create, "pb_dynamic_library_create"),
    # Object queries
    (query_tools.pb_object_query_hierarchy, "pb_object_query_hierarchy"),
    (query_tools.pb_object_query_reference, "pb_object_query_reference"),
    (query_tools.pb_object_regenerate, "pb_object_regenerate"),
)


def build_server() -> FastMCP:
    """Construct a FastMCP server with every `pb_*` tool registered."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("pb-orca-mcp")
    for fn, name in _TOOLS:
        mcp.add_tool(fn, name=name)
    return mcp


def run_stdio() -> None:
    """Run the MCP server over stdio. Blocks until the client disconnects."""
    build_server().run(transport="stdio")


def tool_names() -> list[str]:
    """Return the MCP tool names this server exposes, in registration order.

    Useful for the `doctor` CLI and for tests that verify the registry is
    in sync with the PLAN's tool table.
    """
    return [name for _fn, name in _TOOLS]
