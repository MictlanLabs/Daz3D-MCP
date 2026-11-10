"""Builds the DazScript code sent to Daz Studio for each tool."""

from __future__ import annotations

import re
from functools import lru_cache

from daz3d_mcp.paths import scripts_dir

ENTRY_FUNCTION = "dazmcp_entry"
_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


@lru_cache(maxsize=None)
def _read(relative: str) -> str:
    return (scripts_dir() / relative).read_text(encoding="utf-8")


def available_tools() -> list[str]:
    return sorted(p.stem for p in (scripts_dir() / "tools").glob("*.dsa"))


def build_tool_code(tool: str) -> str:
    """core library + tool script + entry point, as one program."""
    if not _TOOL_NAME.match(tool):
        raise ValueError(f"Invalid tool name: {tool!r}")
    path = scripts_dir() / "tools" / f"{tool}.dsa"
    if not path.is_file():
        raise ValueError(f"Unknown DazScript tool: {tool}")
    return "\n".join(
        [
            _read("lib/core.dsa"),
            f"// ---- tool: {tool} ----",
            _read(f"tools/{tool}.dsa"),
            _read("lib/entry.dsa"),
        ]
    )


def build_user_code(code: str) -> str:
    """Wraps free-form agent code so it runs like a tool.

    The code runs as the body of dazmcpTool(args): it can read `args`, call
    DazMcp.log(...) and `return` a JSON-serializable value.
    """
    return "\n".join(
        [
            _read("lib/core.dsa"),
            "// ---- run_script ----",
            "function dazmcpTool(args) {",
            code,
            "}",
            _read("lib/entry.dsa"),
        ]
    )
