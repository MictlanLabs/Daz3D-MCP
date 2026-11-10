"""Closing test of stage 2, without Daz: over MCP (stdio), an agent builds a
scene with two dressed, posed characters and renders it.

The agent's steps are scripted here the way the scene-building skill tells
an agent to work: search, load, check, adjust, frame, light, render.
"""

from __future__ import annotations

import json
import os
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

STAGE2_TOOLS = {
    "content_libraries", "content_search", "content_thumbnail", "content_load", "node_set", "node_delete",
    "figure_info", "morph_list", "morph_set", "pose_bones", "pose_reset", "wearable_fit", "camera_create",
    "camera_set", "light_create", "light_set", "environment_set", "material_list", "material_set",
    "render_settings", "render",
}


def _params(daz_home) -> StdioServerParameters:
    env = dict(os.environ, DAZ3D_MCP_HOME=str(daz_home), DAZ3D_MCP_TRANSPORT="http")
    return StdioServerParameters(command=sys.executable, args=["-m", "daz3d_mcp"], env=env)


def _text(result) -> str:
    return "\n".join(c.text for c in result.content if c.type == "text")


def test_agent_builds_and_renders_two_dressed_posed_characters(bridge, daz_home, content_library):
    async def scenario():
        async with stdio_client(_params(daz_home)) as (read, write):
            async with ClientSession(read, write) as s:
                await s.initialize()

                async def tool(name, **args):
                    res = await s.call_tool(name, args)
                    assert not res.isError, f"{name}: {_text(res)}"
                    text = _text(res)
                    return json.loads(text) if res.structuredContent is not None or text.startswith("{") else res

                tools = {t.name for t in (await s.list_tools()).tools}
                assert STAGE2_TOOLS <= tools

                guides = {p.name for p in (await s.list_prompts()).prompts}
                assert {"daz-basics", "scene-building", "characters", "rendering"} <= guides

                await tool("scene_new")
                libs = await tool("content_libraries")
                assert libs["files"] == 16

                # 1. Two Genesis 9 figures, one per side.
                base = (await tool("content_search", query="genesis 9", kind="figure"))["results"][0]
                assert base["name"] == "Genesis 9"
                cast = [("Ana", "Ana 9", -55, 15), ("Leo", "Leo 9", 55, -15)]
                for name, character, x, turn in cast:
                    added = (await tool("content_load", path=base["path"]))["added"][0]
                    await tool("node_set", node=added["label"], label=name, position=[x, 0, 0], rotation=[0, turn, 0])
                    preset = (await tool("content_search", query=character, kind="character"))["results"][0]
                    await tool("content_load", path=preset["path"], target=name)

                # 2. Dress them: clothing, shoes and hair for the same generation.
                outfits = {"Ana": ["Summer Dress", "Canvas Sneakers", "Short Bob Hair"],
                           "Leo": ["Basic Wear Shirt", "Basic Wear Pants", "Canvas Sneakers", "Buzz Cut Hair"]}
                for name, items in outfits.items():
                    gen = (await tool("figure_info", figure=name))["generation"]
                    for item in items:
                        found = (await tool("content_search", query=item, generation=gen))["results"]
                        res = await tool("content_load", path=found[0]["path"], target=name)
                        assert res["added"][0]["fitted_to"] == name, res

                # A thumbnail helps choose between results.
                bob = (await tool("content_search", query="short bob", kind="hair"))["results"][0]
                thumb = await s.call_tool("content_thumbnail", {"path": bob["thumbnail"] and bob["path"]})
                assert not thumb.isError and thumb.content[0].type == "image"

                # 3. Pose them and fine-tune.
                poses = {p["name"]: p["path"] for p in
                         (await tool("content_search", kind="pose", generation="Genesis 9"))["results"]}
                await tool("content_load", path=poses["Arms Crossed"], target="Ana")
                await tool("content_load", path=poses["Waving"], target="Leo")
                await tool("pose_bones", figure="Ana", bones={"head": [0, -12, 0]}, relative=True)
                await tool("morph_set", node="Leo", values={"Height": 0.3})
                await tool("material_set", node="Summer Dress", properties={"Base Color": "#2a6f97"})

                # 4. Camera, lights, environment.
                cam = await tool("camera_create", label="Main Camera", frame=["Ana", "Leo"], focal_length=65)
                assert cam["active"]
                await tool("light_create", type="spot", label="Key Light", position=[250, 260, 300],
                           look_at="Ana", power=5000)
                await tool("light_create", type="spot", label="Fill Light", position=[-300, 180, 250],
                           look_at="Leo", power=1500)
                await tool("environment_set", mode="dome_and_scene", intensity=0.6)

                # 5. Check, then render.
                for name in ("Ana", "Leo"):
                    info = await tool("figure_info", figure=name)
                    assert len(info["wearing"]) >= 3 and info["posed_bones"]
                cap = await s.call_tool("viewport_capture", {"camera": "Main Camera", "max_size": 512})
                assert not cap.isError

                await tool("render_settings", width=1600, height=900)
                rendered = await s.call_tool("render", {"camera": "Main Camera", "max_time": 120, "max_samples": 500})
                assert not rendered.isError, _text(rendered)
                assert [c.type for c in rendered.content] == ["image", "text"]
                result = json.loads(_text(rendered))
                assert result["camera"] == "Main Camera" and result["path"].endswith(".png")
                assert os.path.isfile(result["path"])

                again = await s.call_tool("render", {"out_path": result["path"]})
                assert again.isError and "already exists" in _text(again)

    anyio.run(scenario)

    # What the fake Daz Studio actually rendered.
    final = json.loads(bridge.state.read_text())["renders"][-1]
    assert final["camera"] == "Main Camera"
    assert (final["width"], final["height"], final["max_time"], final["max_samples"]) == (1600, 900, 120, 500)
    assert final["lights"] == 2
    people = {f["label"]: f for f in final["figures"]}
    assert set(people) == {"Ana", "Leo"}
    assert set(people["Ana"]["wearing"]) == {"Summer Dress", "Canvas Sneakers", "Short Bob Hair"}
    assert set(people["Leo"]["wearing"]) == {"Basic Wear Shirt", "Basic Wear Pants", "Canvas Sneakers (2)",
                                             "Buzz Cut Hair"}
    for person in people.values():
        assert person["posed_bones"] >= 3
        assert person["morphs_in_use"] >= 2
        assert person["corners_in_frame"] == 8, person  # fully in the picture
