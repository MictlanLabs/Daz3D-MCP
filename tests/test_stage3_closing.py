"""Closing test of stage 3, without Daz: over MCP (stdio), an agent uses in
one scene a package bought in another store (.zip) and a loose FBX.

The steps are the ones the third-party-assets skill tells an agent to take:
inspect, install, find, load; inspect, import, convert to clothing, adjust;
then pose, frame and render to check it all follows the figure.
"""

from __future__ import annotations

import json
import os
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from asset_fixture import JACKET, build_store_zip, write_cape_fbx

STAGE3_TOOLS = {"package_inspect", "package_install", "package_list", "package_uninstall", "content_add_library",
                "mesh_inspect", "import_mesh", "wearable_from_mesh", "wearable_adjust"}


def _params(daz_home, home) -> StdioServerParameters:
    env = dict(os.environ, DAZ3D_MCP_HOME=str(daz_home), DAZ3D_MCP_TRANSPORT="http", HOME=str(home), USERPROFILE=str(home))
    return StdioServerParameters(command=sys.executable, args=["-m", "daz3d_mcp"], env=env)


def _text(result) -> str:
    return "\n".join(c.text for c in result.content if c.type == "text")


def test_agent_uses_an_external_zip_and_a_loose_fbx(bridge, daz_home, content_library, tmp_path):
    home = tmp_path / "home"
    downloads = home / "Downloads"
    store_zip = build_store_zip(downloads / "LeatherJacket_G9.zip")
    cape_fbx = write_cape_fbx(downloads)

    async def scenario():
        async with stdio_client(_params(daz_home, home)) as (read, write):
            async with ClientSession(read, write) as s:
                await s.initialize()

                async def tool(name, **args):
                    res = await s.call_tool(name, args)
                    assert not res.isError, f"{name}: {_text(res)}"
                    return json.loads(_text(res))

                assert STAGE3_TOOLS <= {t.name for t in (await s.list_tools()).tools}
                assert "third-party-assets" in {p.name for p in (await s.list_prompts()).prompts}

                await tool("scene_new")
                base = (await tool("content_search", query="genesis 9", kind="figure"))["results"][0]
                added = (await tool("content_load", path=base["path"]))["added"][0]
                await tool("node_set", node=added["label"], label="Ana")

                # 1. The store package: look inside, install, find, wear.
                inside = await tool("package_inspect", path=str(store_zip))
                assert inside["layout"] == "daz" and inside["content_root"] == "LeatherJacket_G9/Content"
                installed = await tool("package_install", path=str(store_zip))
                library = home / "Documents" / "DAZ 3D" / "Third Party Library"
                assert installed["library"] == library.as_posix()
                assert installed["daz_library"] == {"path": library.as_posix(), "added": True}
                jacket = next(i for i in installed["items"] if i["kind"] == "clothing")
                assert jacket["path"] == (library / JACKET).as_posix()

                libs = await tool("content_libraries")
                assert library.as_posix() in [p.replace("\\", "/") for p in libs["libraries"]]
                found = (await tool("content_search", query="leather jacket", kind="clothing",
                                    generation="Genesis 9"))["results"]
                assert [f["path"] for f in found] == [jacket["path"]]
                worn = await tool("content_load", path=jacket["path"], target="Ana")
                assert worn["added"][0]["fitted_to"] == "Ana"
                black = (await tool("content_search", query="leather jacket black", kind="material"))["results"][0]
                await tool("content_load", path=black["path"], target="Leather Jacket")
                assert (await tool("package_list"))["packages"][0]["package"] == "leatherjacket-g9"

                # 2. The loose FBX: look, import at the right size, make it clothing.
                mesh = await tool("mesh_inspect", path=str(cape_fbx))
                assert mesh["suggested_units"] == "m" and mesh["surfaces"] == ["Cape Lining", "Cape Outer"]
                imported = await tool("import_mesh", path=str(cape_fbx), label="Cape")
                assert imported["bbox"]["size"] == [64, 97, 16]
                cape = await tool("wearable_from_mesh", item="Cape", figure="Ana")
                assert cape["fitted_to"] == "Ana"
                adjusted = await tool("wearable_adjust", item="Cape", collision_iterations=4)
                assert adjusted["collide_with"] == "Ana" and adjusted["collision_iterations"] == 4

                # 3. Pose, frame, light, render: both items must follow the figure.
                pose = (await tool("content_search", query="waving", kind="pose"))["results"][0]
                await tool("content_load", path=pose["path"], target="Ana")
                await tool("node_set", node="Ana", position=[30, 0, -20], rotation=[0, 25, 0])
                info = await tool("figure_info", figure="Ana")
                assert {w["label"] for w in info["wearing"]} == {"Leather Jacket", "Cape"}
                await tool("camera_create", label="Shot", frame=["Ana"], yaw=-30)
                await tool("light_create", type="spot", label="Key", position=[200, 250, 300], look_at="Ana")
                rendered = await s.call_tool("render", {"camera": "Shot", "max_time": 60})
                assert not rendered.isError, _text(rendered)
                assert rendered.content[0].type == "image"

    anyio.run(scenario)

    final = json.loads(bridge.state.read_text())
    (ana,) = final["renders"][-1]["figures"]
    assert set(ana["wearing"]) == {"Leather Jacket", "Cape"}
    assert ana["posed_bones"] == 3 and ana["corners_in_frame"] == 8
    nodes = {n["label"]: n for n in final["nodes"]}
    ana_id = nodes["Ana"]["id"]
    assert nodes["Cape"]["fitted_to"] == ana_id and nodes["Leather Jacket"]["fitted_to"] == ana_id
    assert nodes["Leather Jacket"]["materials"][0]["props"]["Base Color"]["value"] == [0.03, 0.03, 0.03]
    assert all(i["options"]["RunSilent"] == 1 for i in final["imports"])
