"""Tools that make new shape dials (morphs) for traits that have none installed, bring in dials
sculpted in Blender or another modeler, save them in a content library, and make clothing, hair and
the other fitted items follow them."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from functools import partial
from pathlib import Path
from typing import Annotated, Any, Literal

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from daz3d_mcp import morphgen as mg
from daz3d_mcp.paths import config_dir

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
CHANGES_SCENE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)

Call = Callable[..., Awaitable[Any]]
Deltas = dict[int, mg.Vec]


def work_dir() -> Path:
    folder = config_dir() / "morphgen"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def sculpt_dir() -> Path:
    folder = work_dir() / "sculpted"
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

    async def deltas(self, mesh: mg.Mesh, recipe: mg.Recipe) -> Deltas:
        return await anyio.to_thread.run_sync(lambda: mg.build_deltas(mesh, recipe))

    async def create(self, node: str, recipe: mg.Recipe, deltas: Deltas, master: str | None) -> dict:
        path = work_dir() / f"{recipe.name}-deltas.json"
        await anyio.to_thread.run_sync(lambda: mg.write_deltas(path, deltas))
        args: dict = {"figure": node, "name": recipe.name, "label": recipe.label, "group": recipe.group,
                      "deltas": path.as_posix()}
        if master:
            args["master"] = master
        return await self.call("morph_create", args, 300)

    async def follow_deltas(self, figure: str, dials: list[tuple[mg.Recipe, Deltas]], mesh: mg.Mesh,
                            info: dict) -> list[dict]:
        out = []
        for item in [w["label"] for w in info.get("wearing") or []]:
            path = work_dir() / "item.json"
            await self.call("morph_mesh", {"figure": item, "path": path.as_posix(), "weights": False,
                                           "master": figure}, 300)
            verts = await anyio.to_thread.run_sync(partial(mg.read_vertices, path))
            for recipe, d in dials:
                projected = await anyio.to_thread.run_sync(partial(mg.project, mesh.vertices, d, verts))
                if projected:
                    await self.create(item, recipe, projected, figure)
                    out.append({"item": item, "morph": recipe.label, "vertices": len(projected)})
        return out

    async def follow(self, figure: str, recipes: list[mg.Recipe], info: dict | None = None) -> list[dict]:
        info = info or await self.call("figure_info", {"figure": figure})
        generation = str(info.get("generation") or "")
        mesh = await self.body(figure, generation)
        dials = []
        for recipe in recipes:
            if recipe.ops and generation in recipe.generations:
                dials.append((recipe, await self.deltas(mesh, recipe)))
            elif not recipe.ops:
                saved = load_sculpt(recipe.name, generation)
                if saved:
                    dials.append(saved)
        if not dials:
            return []
        return await self.follow_deltas(figure, dials, mesh, info)

    async def in_use(self, figure: str) -> list[mg.Recipe]:
        res = await self.call("morph_list", {"node": figure, "query": "daz3d-mcp", "limit": 1000})
        morphs = res.get("morphs") or []
        names = {m.get("name") for m in morphs}
        out = [r for r in mg.RECIPES.values() if r.name in names]
        known = {r.name for r in out}
        out += [mg.Recipe(str(m["name"]), str(m.get("label")), str(m.get("group")), "", "", ())
                for m in morphs if m.get("name") not in known]
        return out


def sculpt_file(name: str, generation: str) -> Path:
    return sculpt_dir() / f"{generation.replace(' ', '_')}-{name}.json"


def save_sculpt(recipe: mg.Recipe, generation: str, deltas: Deltas) -> None:
    flat: list[float] = []
    for i in sorted(deltas):
        flat += [i, *deltas[i]]
    sculpt_file(recipe.name, generation).write_text(json.dumps(
        {"name": recipe.name, "label": recipe.label, "group": recipe.group, "deltas": flat}), encoding="utf-8")


def load_sculpt(name: str, generation: str) -> tuple[mg.Recipe, Deltas] | None:
    path = sculpt_file(name, generation)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    flat = data["deltas"]
    deltas = {int(flat[i]): (flat[i + 1], flat[i + 2], flat[i + 3]) for i in range(0, len(flat), 4)}
    return mg.Recipe(data["name"], data["label"], data["group"], "", "", ()), deltas


def morph_name(label: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", label)
    return "DazMcp_" + "".join(w[:1].upper() + w[1:] for w in words)


def register(mcp: FastMCP, call: Call) -> Generator:
    gen = Generator(call)

    async def figure_generation(figure: str) -> tuple[dict, str]:
        info = await call("figure_info", {"figure": figure})
        if info.get("type") not in (None, "figure"):
            raise ToolError(f"{figure} is not a figure.")
        return info, str(info.get("generation") or "")

    async def save_to_library(figure: str, names: list[str], library: str | None) -> dict:
        args: dict = {"figure": figure, "morphs": names}
        if library:
            args["library"] = Path(library).expanduser().as_posix()
        return await call("morph_save", args, 300)

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
        age, weight, muscle, bust, areolas...) on Genesis 9 and 8 / 8.1, built from the figure's own
        mesh and bone weights, labeled "MCP <trait>". Character tools then use them like any other
        dial. Without traits, lists what can be made."""
        info, generation = await figure_generation(figure)
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
            out["saved"] = await save_to_library(figure, [r.name for r in recipes], library)
        if follow:
            out["followers"] = await gen.follow(figure, recipes, info)
        out["hint"] = ("Set them with morph_set or through traits; character_create / character_update find "
                       "them by trait. Items loaded later follow them after character_load or "
                       "morph_generate(follow) runs again.")
        return out

    @mcp.tool(annotations=READ_ONLY)
    async def morph_export(
        figure: Annotated[str, Field(description="Figure whose base mesh to export (Genesis 9 or 8 / 8.1).")],
        path: Annotated[str, Field(description="Absolute .obj path to write.")],
        units: Annotated[Literal["cm", "m", "mm"], Field(description="cm as in Daz; m for Blender at real "
                                                                     "size.")] = "m",
    ) -> dict:
        """Writes the figure's base mesh (no morphs, default pose, base resolution, Y up) as an OBJ to
        sculpt a new shape in Blender or another modeler; morph_import brings the sculpt back as a dial."""
        out = Path(path).expanduser()
        if not out.is_absolute() or out.suffix.lower() != ".obj":
            raise ToolError("Give an absolute .obj path.")
        _, generation = await figure_generation(figure)
        mesh = await gen.body(figure, generation)
        out.parent.mkdir(parents=True, exist_ok=True)
        await anyio.to_thread.run_sync(partial(mg.write_obj, out, mesh, units))
        return {"path": out.as_posix(), "generation": generation, "vertices": len(mesh.vertices), "units": units,
                "blender": "Import with Y forward / Z up conversions left as they are (the importer turns Y up "
                           "into Z up), sculpt without adding or removing vertices (no Remesh, Dyntopo or "
                           "Subdivision applied), keep the object's origin, and export the OBJ again with the "
                           "same axes, 'Selection only', no modifiers, and vertex order kept."}

    @mcp.tool(annotations=CHANGES_SCENE)
    async def morph_import(
        figure: Annotated[str, Field(description="Figure to add the dial to.")],
        obj: Annotated[str, Field(description="Absolute path of the sculpted .obj (same vertices as "
                                              "morph_export wrote).")],
        label: Annotated[str, Field(min_length=1, max_length=48, description="Dial label, e.g. \"Hooked "
                                                                            "Nose\"; shown as \"MCP <label>\".")],
        group: Annotated[str, Field(description="Parameters group, e.g. /Actor/Head/Face/Nose.")] =
            "/Actor/Daz3D-MCP",
        save: Annotated[bool, Field(description="Save it in a content library.")] = True,
        library: Annotated[str | None, Field(description="Content library to save into.")] = None,
        follow: Annotated[bool, Field(description="Make worn items follow it.")] = True,
    ) -> dict:
        """Brings back a shape sculpted in Blender (from morph_export's OBJ) as a new dial on the figure:
        size and axes are matched automatically; clothing, hair and other worn items follow it."""
        src = Path(obj).expanduser()
        if not src.is_file():
            raise ToolError(f"File not found: {obj}")
        info, generation = await figure_generation(figure)
        mesh = await gen.body(figure, generation)
        sculpt = await anyio.to_thread.run_sync(partial(mg.read_obj_vertices, src))
        try:
            deltas, fit = await anyio.to_thread.run_sync(partial(mg.sculpt_deltas, mesh.vertices, sculpt))
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        if not deltas:
            raise ToolError("The OBJ is the same as the base mesh: nothing was sculpted.")
        full_label = label if label.upper().startswith("MCP ") else f"MCP {label}"
        group = group if "daz3d-mcp" in group.lower() else group.rstrip("/") + "/Daz3D-MCP"
        recipe = mg.Recipe(morph_name(label), full_label, group, "", "", ())
        res = await gen.create(figure, recipe, deltas, None)
        await anyio.to_thread.run_sync(partial(save_sculpt, recipe, generation, deltas))
        out: dict[str, Any] = {"figure": figure, "generation": generation, "dial": full_label, "name": recipe.name,
                               "vertices": res.get("deltas"), "fit": fit}
        if save:
            out["saved"] = await save_to_library(figure, [recipe.name], library)
        if follow:
            out["followers"] = await gen.follow_deltas(figure, [(recipe, deltas)], mesh, info)
        return out

    return gen
