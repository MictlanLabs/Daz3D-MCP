"""End to end: an MCP client talks to `python -m daz3d_mcp` over stdio, which
talks to the fake bridge. This is the closing test of stage 1 without Daz."""

from __future__ import annotations

import json
import os
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _params(daz_home, **env) -> StdioServerParameters:
    full_env = dict(os.environ, DAZ3D_MCP_HOME=str(daz_home), DAZ3D_MCP_TRANSPORT="http", **env)
    return StdioServerParameters(command=sys.executable, args=["-m", "daz3d_mcp"], env=full_env)


def _text(result) -> str:
    return "\n".join(c.text for c in result.content if c.type == "text")


def test_agent_opens_describes_and_captures(bridge, daz_home, scene_file):
    async def scenario():
        async with stdio_client(_params(daz_home)) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                assert init.serverInfo.name == "daz3d"
                assert "Daz Studio" in (init.instructions or "")

                tools = {t.name for t in (await session.list_tools()).tools}
                assert {"daz_status", "scene_info", "scene_new", "scene_open", "scene_save",
                        "viewport_capture", "run_script", "daz_guide"} <= tools

                status = await session.call_tool("daz_status", {})
                assert not status.isError, _text(status)
                assert json.loads(_text(status))["daz"]["version"].startswith("6.")

                opened = await session.call_tool("scene_open", {"path": str(scene_file)})
                assert not opened.isError, _text(opened)

                info = await session.call_tool("scene_info", {})
                assert not info.isError
                data = json.loads(_text(info))
                assert {n["label"] for n in data["nodes"]} >= {"Genesis 9", "Sofa", "Camera 1"}

                cap = await session.call_tool("viewport_capture", {"max_size": 256})
                assert not cap.isError, _text(cap)
                images = [c for c in cap.content if c.type == "image"]
                assert images and images[0].mimeType == "image/png"

                relative = await session.call_tool("scene_open", {"path": "relative.duf"})
                assert relative.isError

                prompts = {p.name for p in (await session.list_prompts()).prompts}
                assert "daz-basics" in prompts
                guide = await session.call_tool("daz_guide", {"topic": "daz-basics"})
                assert "Y is up" in _text(guide)

                resources = {str(r.uri) for r in (await session.list_resources()).resources}
                assert "daz3d://skills/daz-basics" in resources

    anyio.run(scenario)


def test_run_script_can_be_disabled(bridge, daz_home):
    async def scenario():
        async with stdio_client(_params(daz_home, DAZ3D_MCP_ALLOW_SCRIPTS="0")) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool("run_script", {"code": "return 1;"})
                assert res.isError
                assert "disabled" in _text(res)

    anyio.run(scenario)


def test_clear_error_when_daz_is_closed(daz_home):
    async def scenario():
        async with stdio_client(_params(daz_home)) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool("daz_status", {})
                assert res.isError
                assert "doctor" in _text(res)

    anyio.run(scenario)
