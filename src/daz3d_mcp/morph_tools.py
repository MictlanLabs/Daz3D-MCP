"""Tools that make new shape dials (morphs) for traits that have none installed, save them in a
content library, and make clothing, hair and the other fitted items follow them."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import partial
from pathlib import Path
from typing import Annotated, Any

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from daz3d_mcp import morphgen as mg
from daz3d_mcp.paths import config_dir

CHANGES_SCENE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)

Call = Callable[..., Awaitable[Any]]


def work_dir() -> Path:
    folder = config_dir() / "morphgen"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


class Generator:
    def __init__(self, call: Call):
        self.call = call
        self.meshes: dict[str, mg.Mesh] = {}

    async def body(self, figure: str, generation: str) -> mg.Mesh:
        key = generation.replace(" ", "_")
        if key in self.meshes:
            return self.meshes[key]
        path = work_dir() / f"{key}.json"
        if not path.is_file():
            await self.call("morph_mesh", {"figure": figure, "path": path.as_posix()}, 300)
        mesh = await anyio.to_thread.run_sync(lambda: mg.Mesh.load(path))
        self.meshes[key] = mesh
        return mesh

    async def deltas(self, mesh: mg.Mesh, recipe: mg.Recipe) -> dict[int, mg.Vec]:
        return await anyio.to_thread.run_sync(lambda: mg.build_deltas(mesh, recipe))

    async def create(self, node: str, recipe: mg.Recipe, deltas: dict[int, mg.Vec], master: str | None) -> dict:
        path = work_dir() / f"{recipe.name}-deltas.json"
        await anyio.to_thread.run_sync(lambda: mg.write_deltas(path, deltas))
        args: dict = {"figure": node, "name": recipe.name, "label": recipe.label, "group": recipe.group,
                      "deltas": path.as_posix()}
        if master:
            args["master"] = master
        return await self.call("morph_create", args, 300)

    async def follow(self, figure: str, recipes: list[mg.Recipe], info: dict | None = None) -> list[dict]:
        info = info or await self.call("figure_info", {"figure": figure})
        generation = str(info.get("generation") or "")
        recipes = [r for r in recipes if generation in r.generations]
        if not recipes:
            return []
        mesh = await self.body(figure, generation)
        out = []
        for item in [w["label"] for w in info.get("wearing") or []]:
            path = work_dir() / "item.json"
            await self.call("morph_mesh", {"figure": item, "path": path.as_posix(), "weights": False,
                                           "master": figure}, 300)
            verts = await anyio.to_thread.run_sync(partial(mg.read_vertices, path))
            for recipe in recipes:
                d = await self.deltas(mesh, recipe)
                projected = await anyio.to_thread.run_sync(partial(mg.project, mesh.vertices, d, verts))
                if projected:
                    await self.create(item, recipe, projected, figure)
                    out.append({"item": item, "morph": recipe.label, "vertices": len(projected)})
        return out

    async def in_use(self, figure: str) -> list[mg.Recipe]:
        res = await self.call("morph_list", {"node": figure, "query": "daz3d-mcp", "limit": 1000})
        names = {m.get("name") for m in res.get("morphs") or []}
        return [r for r in mg.RECIPES.values() if r.name in names]


def register(mcp: FastMCP, call: Call) -> Generator:
    gen = Generator(call)

    @mcp.tool(annotations=CHANGES_SCENE)
    async def morph_generate(
        figure: Annotated[str, Field(description="Figure label (Genesis 9 or 8 / 8.1).")],
        traits: Annotated[list[str] | None, Field(description="Traits to make dials for; omit to list what "
                                                              "can be made.")] = None,
        save: Annotated[bool, Field(description="Save the new dials in a content library, so every new "
                                                "figure of this generation has them.")] = True,
        library: Annotated[str | None, Field(description="Content library to save into (default: Daz's "
                                                         "first one).")] = None,
        follow: Annotated[bool, Field(description="Make the clothing, hair and other items the figure "
                                                  "wears follow the new dials.")] = True,
    ) -> dict:
        """Makes new shape dials for traits that have no installed dial (nose, chin, jaw, cheeks, ears,
        age, weight, muscle...) on Genesis 9 and 8 / 8.1,
        built from the figure's own mesh and bone weights, labeled "MCP <trait>". Character tools then
        use them like any other dial. Without traits, lists what can be made."""
        info = await call("figure_info", {"figure": figure})
        generation = str(info.get("generation") or "")
        available = [{"trait": r.trait, "dial": r.label, "plus": r.plus} for r in mg.RECIPES.values()
                     if generation in r.generations]
        if not traits:
            return {"figure": figure, "generation": generation, "available": available}
        unknown = [t for t in traits if t not in mg.RECIPES]
        if unknown:
            raise ToolError(f"No recipe for {unknown}. Available: {[a['trait'] for a in available]}.")
        recipes = [mg.RECIPES[t] for t in traits]
        wrong = [r.trait for r in recipes if generation not in r.generations]
        if wrong:
            raise ToolError(f"{wrong} can only be made on {sorted({g for r in recipes for g in r.generations})}; "
                            f"{figure} is {generation or 'not a Genesis figure'}.")
        mesh = await gen.body(figure, generation)
        made = []
        for recipe in recipes:
            res = await gen.create(figure, recipe, await gen.deltas(mesh, recipe), None)
            made.append({"trait": recipe.trait, "dial": recipe.label, "name": recipe.name,
                         "vertices": res.get("deltas")})
        out: dict[str, Any] = {"figure": figure, "generation": generation, "made": made}
        if save:
            args: dict = {"figure": figure, "morphs": [r.name for r in recipes]}
            if library:
                args["library"] = Path(library).expanduser().as_posix()
            out["saved"] = await call("morph_save", args, 300)
        if follow:
            out["followers"] = await gen.follow(figure, recipes, info)
        out["hint"] = ("Set them with morph_set or through traits; character_create / character_update find "
                       "them by trait. Items loaded later follow them after character_load or "
                       "morph_generate(follow) runs again.")
        return out

    return gen
