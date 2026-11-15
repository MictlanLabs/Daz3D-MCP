"""Render culling: leave out of the render what a camera cannot see.

render_cull works out, for one camera (and a set of frames), which nodes are
out of the picture or covered by other clothing, and switches off their
"Visible in Render". The viewport, "Visible" and the saved scene are not
changed: the record of what was hidden lives in ~/.daz3d-mcp/cull-active.json
so it can always be undone, and scene_save puts everything back before it
writes the file.
"""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, AsyncIterator, Awaitable, Callable, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from daz3d_mcp.paths import config_dir

CHANGES_SCENE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)

Call = Callable[..., Awaitable[Any]]

MAX_SAMPLED_FRAMES = 12


def sample_frames(start: int, end: int, samples: int) -> list[int]:
    """Up to `samples` frames spread evenly from start to end, both included."""
    if end < start:
        start, end = end, start
    count = end - start + 1
    if count <= samples:
        return list(range(start, end + 1))
    if samples <= 1:
        return [start]
    return sorted({start + round(i * (count - 1) / (samples - 1)) for i in range(samples)})


class Culler:
    """Hides and restores nodes for a render, and remembers what it hid."""

    def __init__(self, call: Call, record_path: Path | None = None) -> None:
        self.call = call
        self.path = record_path or config_dir() / "cull-active.json"

    # ---------------------------------------------------------- record --
    def active(self) -> dict | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if data.get("nodes") else None

    def _write(self, record: dict | None) -> None:
        if not record or not record.get("nodes"):
            try:
                self.path.unlink()
            except OSError:
                pass
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")

    def forget(self) -> None:
        """The scene was replaced: the record no longer means anything."""
        self._write(None)

    # --------------------------------------------------------- actions --
    async def check(self, args: dict) -> dict:
        return await self.call("render_cull", dict(args, action="check"))

    async def hide(self, args: dict) -> dict:
        """Restores an earlier cull, then hides what this camera does not see."""
        restored = await self.restore()
        result = await self.call("render_cull", dict(args, action="hide"))
        ids = result.pop("hidden_ids", [])
        self._write({"camera": result.get("camera"), "frames": result.get("frames"), "nodes": ids,
                     "time": time.strftime("%Y-%m-%d %H:%M:%S")})
        if restored.get("restored"):
            result["restored_first"] = len(restored["restored"])
        return result

    async def restore(self) -> dict:
        record = self.active()
        if not record:
            return {"restored": [], "missing": []}
        res = await self.call("render_cull", {"action": "set", "ids": record["nodes"], "visible": True})
        self._write(None)
        return {"restored": res.get("changed", []), "missing": res.get("missing", []),
                "camera": record.get("camera")}

    async def reapply(self, record: dict) -> None:
        await self.call("render_cull", {"action": "set", "ids": record["nodes"], "visible": False})
        self._write(record)

    @asynccontextmanager
    async def during(self, enabled: bool, args: dict) -> AsyncIterator[dict | None]:
        """Hides for one render and always restores afterwards."""
        if not enabled:
            yield None
            return
        result = await self.hide(args)
        try:
            yield result
        finally:
            await self.restore()


def summary(result: dict | None) -> dict | None:
    """The short form of a cull put into a render's result."""
    if not result:
        return None
    out = {"hidden": result.get("hidden", []), "savings": result.get("savings")}
    if result.get("kept"):
        out["kept"] = result["kept"]
    if result.get("warnings"):
        out["warnings"] = result["warnings"]
    return out


def cull_args(camera: str | None, frames: list[int] | None, keep: list[str] | None) -> dict:
    return {k: v for k, v in {"camera": camera, "frames": frames, "keep": keep}.items() if v is not None}


def register(mcp: FastMCP, call: Call) -> Culler:
    culler = Culler(call)

    @mcp.tool(annotations=CHANGES_SCENE)
    async def render_cull(
        action: Annotated[Literal["check", "hide", "restore"],
                          Field(description="check: only report; hide: take out of the render what the camera "
                                            "does not see; restore: put back what an earlier hide took out.")
                          ] = "check",
        camera: Annotated[str | None, Field(description="Camera label; default the viewport camera.")] = None,
        start_frame: Annotated[int | None, Field(ge=0, description="With end_frame: an animation range; what "
                                                                   "is seen at any sampled frame is kept.")] = None,
        end_frame: Annotated[int | None, Field(ge=0)] = None,
        samples: Annotated[int, Field(ge=1, le=60, description="Frames of the range to test (spread evenly, "
                                                               "ends included).")] = MAX_SAMPLED_FRAMES,
        occlusion: Annotated[Literal["worn", "none"],
                             Field(description="worn: also drop clothing hidden under other clothing of the "
                                               "same figure (underwear under a long skirt). none: only what "
                                               "is out of the picture.")] = "worn",
        keep: Annotated[list[str] | None, Field(description="Labels never to drop (a figure keeps what it "
                                                            "wears).")] = None,
        shadow_margin: Annotated[float, Field(ge=0, description="cm: keep out-of-picture things this close to "
                                                                "the picture (contact shadows, bounce "
                                                                "light).")] = 30,
        frame_margin: Annotated[float, Field(ge=0, le=1, description="Share of the picture added on each side "
                                                                     "before testing.")] = 0.05,
        resolution: Annotated[int, Field(ge=32, le=2000, description="Width of the depth buffer for the "
                                                                     "covered-clothing test.")] = 400,
        depth_margin: Annotated[float, Field(ge=0, description="cm a worn item must sit behind other "
                                                               "clothing to count as covered.")] = 0.3,
        ignore_reflections: Annotated[bool, Field(description="Drop out-of-picture things even with a "
                                                              "mirror in view.")] = False,
        detail: Annotated[bool, Field(description="List every node with its status.")] = False,
    ) -> dict:
        """Finds what a camera cannot see and leaves it out of the render, so Iray loads less geometry
        and fewer textures (faster, and less memory on CPU or a small GPU). Out of the picture, behind
        the camera, or worn under other clothing: those nodes get "Visible in Render" off. The
        viewport and the saved file do not change, and restore puts everything back. Keeps things
        that still matter off screen: walls and ceilings that hold light in, things between a light
        and the subject, things close to it, lamps that glow, and everything when a mirror is in
        view. render, render_shots and render_animation do this per shot with cull=true."""
        if action == "restore":
            return await culler.restore()
        frames: list[int] | None = None
        if start_frame is not None or end_frame is not None:
            tl = await call("anim_timeline", {"list_animated": False})
            a = int(tl["start_frame"]) if start_frame is None else start_frame
            b = int(tl["end_frame"]) if end_frame is None else end_frame
            frames = sample_frames(a, b, samples)
        args: dict[str, Any] = {
            "occlusion": occlusion, "shadow_margin": shadow_margin, "frame_margin": frame_margin,
            "resolution": resolution, "depth_margin": depth_margin, "ignore_reflections": ignore_reflections,
            "detail": detail,
        }
        args.update(cull_args(camera, frames, keep))
        if action == "check":
            result = await culler.check(args)
            record = culler.active()
            if record:
                result["active_cull"] = {"camera": record.get("camera"), "hidden": len(record["nodes"]),
                                         "note": "An earlier hide is still in effect; restore puts it back."}
            return result
        return await culler.hide(args)

    return culler
