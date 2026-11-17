"""Realistic look: materials that are not plastic, photographic light rigs and
postwork on finished renders (see the realistic-renders skill)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Awaitable, Callable, Literal

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from daz3d_mcp import postwork, video
from daz3d_mcp.client import DazClient

CHANGES_SCENE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
WRITES_FILE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)

Call = Callable[..., Awaitable[Any]]
Color = Annotated[list[float] | str, Field(description="[r, g, b] from 0 to 1, or \"#rrggbb\".")]
LookName = Literal["film", "soft", "punchy", "neutral"]


def _clean(**kwargs) -> dict:
    return {k: v for k, v in kwargs.items() if v is not None}


async def run_postwork(get_client: Callable[[], DazClient], image: Path, out: Path, look: str, strength: float,
                       background: Any, grain: float | None, vignette: float | None,
                       sharpen: float | None) -> Path:
    """Shared by render_postwork and render(postwork=...)."""
    ffmpeg = video.find_ffmpeg(get_client().settings.extra.get("ffmpeg"))
    if not ffmpeg:
        raise ToolError("No ffmpeg found (looked on PATH and in the Daz Studio folder). Install ffmpeg or set "
                        "\"ffmpeg\" in ~/.daz3d-mcp/settings.json.")
    try:
        return await anyio.to_thread.run_sync(
            lambda: postwork.apply(ffmpeg, image, out, look, strength, background, grain, vignette, sharpen))
    except (ValueError, video.VideoError) as exc:
        raise ToolError(str(exc)) from exc


def register(mcp: FastMCP, call: Call, get_client: Callable[[], DazClient]) -> None:

    @mcp.tool(annotations=CHANGES_SCENE)
    async def surface_realism(
        node: Annotated[str, Field(description="Figure, clothing or prop label (a car, a set: its parts too).")],
        skin: Annotated[Literal["natural", "matte", "oily", "none"],
                        Field(description="Skin finish on figures. natural: one soft specular, as real skin; "
                                          "matte: powdered, no shine; oily: sweaty or wet.")] = "natural",
        upgrade: Annotated[bool, Field(description="Rebuild \"Physically Based Rendering\" surfaces (FBX/OBJ "
                                                   "imports) as Iray Uber with the finish their name suggests: "
                                                   "leather, cloth, plastic, chrome, car paint, rubber, glass, "
                                                   "wood, metal.")] = True,
        children: Annotated[bool, Field(description="Also the props parented to node.")] = True,
        worn: Annotated[bool, Field(description="Also what a figure wears.")] = False,
        dry_run: Annotated[bool, Field(description="Only report what would change.")] = False,
    ) -> dict:
        """Takes the plastic look off: skin that stacks two specular layers (Glossy plus Dual Lobe) gets one
        soft dual-lobe specular, and imported props get real Iray Uber materials instead of one flat sheen."""
        return await call("surface_realism", _clean(node=node, skin=skin, upgrade=upgrade, children=children,
                                                    worn=worn or None, dry_run=dry_run or None))

    @mcp.tool(annotations=CHANGES_SCENE)
    async def light_rig(
        subject: Annotated[str, Field(description="Figure (lit at the head) or prop (at its center).")],
        preset: Annotated[Literal["low_key", "soft_studio", "window", "neon"],
                          Field(description="low_key: black background, side key, a cool and a warm rim, "
                                            "almost no fill (dramatic portrait). soft_studio: big soft key, "
                                            "fill and hair light on light grey. window: warm daylight from one "
                                            "side and a cool fill, keeps the environment (interiors). neon: "
                                            "dim warm key, cyan and magenta rims on black.")] = "low_key",
        camera: Annotated[str | None, Field(description="Camera the lights are placed from; default the "
                                                        "active viewport's.")] = None,
        side: Annotated[Literal["left", "right"], Field(description="Side of the picture the key light comes "
                                                                   "from.")] = "left",
        power_scale: Annotated[float, Field(gt=0, le=10, description="Multiplies every light.")] = 1,
        background: Annotated[Literal["auto", "keep"] | list[float] | str,
                              Field(description="auto: the preset's (black for low_key and neon); keep; or a "
                                                "color.")] = "auto",
        solo: Annotated[bool, Field(description="Switch off the scene's other lights.")] = True,
    ) -> dict:
        """Places a photographic light setup (key, rims, fill) around a subject from the camera's point of
        view, sets the background and exposure for it, and replaces the previous rig."""
        return await call("light_rig", _clean(subject=subject, preset=preset, camera=camera, side=side,
                                              power_scale=power_scale, background=background,
                                              solo=solo))

    @mcp.tool(annotations=WRITES_FILE)
    async def render_postwork(
        image: Annotated[str, Field(description="Absolute path of a finished render (.png/.jpg).")],
        out_path: Annotated[str | None, Field(description="Absolute output path; default <name>-post.png "
                                                          "next to the image.")] = None,
        look: Annotated[LookName, Field(description="film: lifted blacks, soft highlights, cool shadows and "
                                                    "warm highlights; soft: gentler, for portraits and bright "
                                                    "scenes; punchy: more contrast for night and action; "
                                                    "neutral: keeps the colors, only background, sharpening "
                                                    "and grain.")] = "film",
        strength: Annotated[float, Field(ge=0, le=2, description="How strong the look is (1 = as designed).")] = 1,
        background: Annotated[list[float] | str | None,
                              Field(description="Color behind transparent pixels (renders with no backdrop "
                                                "drawn are transparent there); null keeps transparency.")]
        = "#000000",
        grain: Annotated[float | None, Field(ge=0, le=40, description="Film grain, 0 = none.")] = None,
        vignette: Annotated[float | None, Field(ge=0, le=1.2, description="Vignette strength, 0 = none.")] = None,
        sharpen: Annotated[float | None, Field(ge=0, le=2, description="Lens sharpening, 0 = none.")] = None,
        overwrite: bool = True,
    ) -> dict:
        """Photographic finish for a render, with ffmpeg (Daz Studio ships one): film tone curve, split
        toning, local contrast, sharpening, grain and vignette, so it reads as a photo instead of 3D."""
        src = Path(image).expanduser()
        if not src.is_absolute() or not src.is_file():
            raise ToolError(f"No image at {image!r} (use an absolute path).")
        out = Path(out_path).expanduser() if out_path else postwork.default_output(src)
        if not out.is_absolute():
            raise ToolError("out_path must be absolute.")
        if out.exists() and not overwrite:
            raise ToolError(f"{out} already exists. Pass overwrite=true or another path.")
        done = await run_postwork(get_client, src, out, look, strength, background, grain, vignette, sharpen)
        return {"image": src.as_posix(), "out": done.as_posix(), "look": look, "strength": strength,
                "background": background}
