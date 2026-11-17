"""The contact_bake tool: a hand pressing soft flesh, measured on the real posed geometry at every
frame and baked into one morph per frame (see contact.py)."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from daz3d_mcp import contact as ct
from daz3d_mcp.morph_tools import Generator, work_dir

CHANGES_SCENE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
PREFIX = "DazMcp_Contact_"

Call = Callable[..., Awaitable[Any]]


def offsets_file(frames: list[int], out: list[dict[int, ct.Vec]]) -> dict:
    return {"frames": frames, "offsets": [[x for i in sorted(o) for x in (i, *o[i])] for o in out]}


def register(mcp: FastMCP, call: Call, gen: Generator) -> None:
    @mcp.tool(annotations=CHANGES_SCENE)
    async def contact_bake(
        figure: Annotated[str, Field(description="Figure whose flesh is pressed (Genesis 9 or 8 / 8.1).")],
        region: Annotated[Literal["breast_left", "breast_right", "breasts"],
                          Field(description="Soft flesh that gives way (the figure's own left / right).")],
        hand: Annotated[Literal["right", "left"], Field(description="The figure's own hand that presses.")] = "right",
        start_frame: Annotated[int | None, Field(ge=0, description="Default: start of the timeline.")] = None,
        end_frame: Annotated[int | None, Field(ge=0, description="Default: end of the timeline.")] = None,
        stiffness: Annotated[float, Field(gt=0, le=1, description="Spring pull per frame; higher = firmer, "
                                                                  "snappier flesh.")] = 0.3,
        damping: Annotated[float, Field(ge=0, le=1, description="Lower = more wobble after release.")] = 0.33,
        bulge: Annotated[float, Field(ge=0, le=1, description="Share of the pushed-in depth that bulges out "
                                                              "around the hand.")] = 0.35,
        sag: Annotated[float, Field(ge=0, le=1, description="cm the breast drops per cm of press, then "
                                                            "bounces back.")] = 0.2,
        remove: Annotated[bool, Field(description="Only remove an earlier bake.")] = False,
    ) -> dict:
        """Makes a hand press soft flesh for real: at every frame of the animation it measures where
        the palm and each finger enter the breast, pushes the skin back to the hand's surface, lets
        the flesh around bulge, and gives it inertia (it lags, overshoots on release and settles).
        Bakes one hidden morph per frame (DazMcp_Contact_####), keyed on its own frame. Animate the
        hand into the flesh first (a few mm to 2 cm deep), then bake; bake again after changing the
        hand animation. Renders must use whole frames."""
        if remove:
            res = await call("contact_bake", {"figure": figure, "prefix": PREFIX, "remove_only": True})
            return {"figure": figure, "removed": res.get("removed", 0)}
        info = await call("figure_info", {"figure": figure})
        generation = str(info.get("generation") or "")
        if not generation.startswith(("Genesis 9", "Genesis 8")):
            raise ToolError(f"{figure} is {generation or 'not a Genesis figure'}; contact_bake needs Genesis 9 or 8.")
        mesh = await gen.body(figure, generation)
        sides = ("left", "right") if region == "breasts" else (region.split("_")[1],)
        soft = ct.breast_softness(mesh, sides)
        hand_verts = ct.hand_vertices(mesh, hand)
        if not soft or not hand_verts:
            raise ToolError("Could not find the breast or the hand on this figure's mesh.")
        timeline = await call("anim_timeline", {"list_animated": False})
        first = int(timeline.get("start_frame", 0) if start_frame is None else start_frame)
        last = int(timeline.get("end_frame", 30) if end_frame is None else end_frame)
        if last < first:
            raise ToolError("end_frame is before start_frame.")
        frames = list(range(first, last + 1))
        ring = set(hand_verts) | set(soft)
        for i in list(ring):
            ring |= mesh.neighbors[i]
        idx = sorted(ring)
        sample = work_dir() / "contact-sample.json"
        sampled = await call("contact_sample", {"figure": figure, "vertices": idx, "frames": frames,
                                                "path": sample.as_posix(), "remove_prefix": PREFIX}, 900)
        data = json.loads(sample.read_text(encoding="utf-8"))
        posed = [{i: tuple(row[3 * k:3 * k + 3]) for k, i in enumerate(idx)} for row in data["positions"]]
        settings = ct.Settings(stiffness=stiffness, damping=damping, bulge=bulge, sag=sag)
        scale = float(sampled.get("scale") or 1.0) or 1.0
        out = await anyio.to_thread.run_sync(lambda: ct.simulate(mesh, soft, hand_verts, posed, settings, scale))
        path = work_dir() / "contact-offsets.json"
        path.write_text(json.dumps(offsets_file(frames, out)), encoding="utf-8")
        baked = await call("contact_bake", {"figure": figure, "path": path.as_posix(), "prefix": PREFIX}, 900)
        return {"figure": figure, "region": region, "hand": hand, "frames": [first, last],
                "frames_with_contact_or_motion": sum(1 for o in out if o), "morphs": baked.get("morphs"),
                "hint": "Render whole frames (no motion blur between frames). Bake again after changing the "
                        "hand animation or the figure's shape; contact_bake(remove=true) takes the morphs away."}
