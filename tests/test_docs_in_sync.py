r"""Guard against doc drift: the tool reference must match the live registry.

`docs/tools.md` documents one `### \`pb_xxx(...)\`` header per MCP tool. The
server's real source of truth is the `_TOOLS` registry in
`pb_orca_mcp.server` (exposed via `tool_names()`). This test asserts the two
agree, so adding or removing a tool without updating the reference fails CI
instead of drifting silently.
"""

from __future__ import annotations

import re
from pathlib import Path

from pb_orca_mcp.server import tool_names

_TOOLS_MD = Path(__file__).resolve().parent.parent / "docs" / "tools.md"

# Headers look like:  ### `pb_session_open(*, pb_version=None, ...)`
_TOOL_HEADER = re.compile(r"^### `(pb_[a-z0-9_]+)\(", re.MULTILINE)


def _documented_tool_names() -> set[str]:
    return set(_TOOL_HEADER.findall(_TOOLS_MD.read_text(encoding="utf-8")))


def test_tools_md_matches_registered_tools() -> None:
    registered = set(tool_names())
    documented = _documented_tool_names()

    undocumented = sorted(registered - documented)
    stale = sorted(documented - registered)

    assert not undocumented, (
        f"registered tools missing a `### ` entry in docs/tools.md: {undocumented}"
    )
    assert not stale, f"docs/tools.md documents tools the server does not register: {stale}"


def test_no_duplicate_tool_registration() -> None:
    names = tool_names()
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, f"duplicate tool names in the registry: {dupes}"
