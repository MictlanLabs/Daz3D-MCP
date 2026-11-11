"""Stage 2 tools: content library, nodes, characters, cameras, lights,
materials and rendering."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated, Any, Awaitable, Callable, Literal

import anyio
from mcp.server.fastmcp import Context, FastMCP, Image
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from daz3d_mcp.client import DazClient
from daz3d_mcp.content import KINDS, ContentIndex, thumbnail_of
from daz3d_mcp import video
from daz3d_mcp.paths import config_dir

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
CHANGES_SCENE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)

Vec3 = Annotated[list[float], Field(min_length=3, max_length=3)]
Color = Annotated[list[float] | str, Field(description="[r, g, b] from 0 to 1, or \"#rrggbb\".")]
Target = Annotated[str | Vec3, Field(description="A node label (aims at its center) or [x, y, z] in cm.")]
ContentKind = Literal[tuple(KINDS)]  # type: ignore[valid-type]

PREVIEW_MAX_BYTES = 8 * 1024 * 1024

Call = Callable[..., Awaitable[Any]]


def _abs(path: str) -> str:
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise ToolError(f"Use an absolute path (got {path!r}).")
    return p.as_posix()


def _maps_to_abs(properties: dict) -> dict:
    out = {}
    for key, value in properties.items():
        if isinstance(value, dict) and isinstance(value.get("map"), str) and value["map"]:
            value = dict(value, map=_abs(value["map"]))
        out[key] = value
    return out


def _clean(**kwargs) -> dict:
    """Drops arguments the agent did not give, so the scripts keep their defaults."""
    return {k: v for k, v in kwargs.items() if v is not None}


def register(mcp: FastMCP, call: Call, get_client: Callable[[], DazClient]) -> Callable[[], None]:
    """Adds the tools; returns a function that forgets the cached libraries and index."""
    state: dict[str, Any] = {"libraries": None, "index": None}

    def forget() -> None:
        state["libraries"] = None
        state["index"] = None
        # The saved index would still be "fresh" (under 24 h) and hide files a
        # package just installed, so drop it and rebuild on the next search.
        try:
            (config_dir() / "content-index.json").unlink()
        except OSError:
            pass

    async def libraries(refresh: bool = False) -> list[str]:
        if state["libraries"] is None or refresh:
            result = await call("content_libraries")
            paths = [lib["path"] for lib in result.get("libraries", []) if lib.get("kind") == "daz"]
            extra = [p for p in (get_client().settings.content_libraries or []) if p not in paths]
            state["libraries"] = [str(Path(p).expanduser()) for p in paths + extra]
            state["index"] = None
        return state["libraries"]

    async def index(refresh: bool = False) -> ContentIndex:
        libs = await libraries(refresh)
        if not libs:
            raise ToolError("Daz Studio reports no content libraries. Add one in Daz (Content Directory "
                            "Manager) or list folders in content_libraries in ~/.daz3d-mcp/settings.json.")
        if state["index"] is None or refresh:
            hours = get_client().settings.content_index_max_age_hours
            idx = ContentIndex(libs, max_age_hours=hours)
            await anyio.to_thread.run_sync(lambda: idx.load(refresh))
            state["index"] = idx
        return state["index"]

    # ------------------------------------------------------- content ----
    @mcp.tool(annotations=READ_ONLY)
    async def content_libraries(
        refresh: Annotated[bool, Field(description="Ask Daz again and rebuild the file index.")] = False,
    ) -> dict:
        """Lists the user's Daz content libraries (My Library, My DAZ 3D Library...) and how many
        content files the search index holds."""
        idx = await index(refresh)
        return {"libraries": idx.libraries, "files": idx.file_count}

    @mcp.tool(annotations=READ_ONLY)
    async def content_search(
        query: Annotated[str, Field(description="Words that must all appear in the file path, e.g. 'jeans' or "
                                                "'genesis 9 walk'. Empty lists everything that matches the filters.")] = "",
        kind: Annotated[ContentKind | None, Field(description="figure, character, clothing, hair, pose, material, "
                                                             "shape, prop, light, scene, scene_subset...")] = None,
        generation: Annotated[str | None, Field(description="Only content made for this figure generation, "
                                                            "e.g. 'Genesis 9' (figure_info reports it).")] = None,
        folder: Annotated[str | None, Field(description="Only inside this library folder, e.g. "
                                                        "'People/Genesis 9/Poses'.")] = None,
        limit: Annotated[int, Field(ge=1, le=200)] = 20,
        offset: Annotated[int, Field(ge=0)] = 0,
        refresh_index: Annotated[bool, Field(description="Rebuild the index (after installing content).")] = False,
    ) -> dict:
        """Searches the installed content: figures, characters, clothing, hair, poses, materials, props,
        lights. Returns absolute paths to pass to content_load, and thumbnails for content_thumbnail."""
        idx = await index(refresh_index)
        return await anyio.to_thread.run_sync(
            lambda: idx.search(query, kind, generation, folder, limit, offset))

    @mcp.tool(annotations=READ_ONLY, structured_output=False)
    async def content_thumbnail(
        path: Annotated[str, Field(description="Content file path from content_search.")],
    ) -> list:
        """Shows the thumbnail image of a content file, to choose between search results."""
        p = Path(path).expanduser()
        thumb = thumbnail_of(p) if p.suffix.lower() != ".png" else p
        if thumb is None or not thumb.is_file():
            raise ToolError(f"{p.name} has no thumbnail.")
        fmt = "jpeg" if thumb.suffix.lower() in (".jpg", ".jpeg") else "png"
        return [Image(data=thumb.read_bytes(), format=fmt), thumb.as_posix()]

    @mcp.tool(annotations=CHANGES_SCENE)
    async def content_load(
        path: Annotated[str, Field(description="Content file from content_search (absolute, or relative to a "
                                               "library such as 'People/Genesis 9/Genesis 9.duf').")],
        target: Annotated[str | None, Field(description="Label of the node it applies to. Required for clothing, "
                                                        "hair, poses, characters, shapes and materials; "
                                                        "omit for figures, props and lights.")] = None,
    ) -> dict:
        """Loads content into the scene: adds a figure or prop, dresses a figure (clothing, hair),
        applies a pose, character, shape or material preset to the target. Returns the new nodes."""
        idx = await index()
        resolved = idx.resolve(path)
        if resolved is None:
            raise ToolError(f"Content file not found: {path}. Use content_search to find it.")
        kind = await anyio.to_thread.run_sync(lambda: idx.kind_for(resolved))
        return await call("content_load", _clean(path=resolved.as_posix(), kind=kind, target=target))

    # --------------------------------------------------------- nodes ----
    @mcp.tool(annotations=CHANGES_SCENE)
    async def node_set(
        node: Annotated[str, Field(description="Node label.")],
        position: Annotated[Vec3 | None, Field(description="[x, y, z] cm (relative to its parent).")] = None,
        rotation: Annotated[Vec3 | None, Field(description="[x, y, z] degrees.")] = None,
        scale: Annotated[float | None, Field(gt=0, description="1 = 100 %.")] = None,
        relative: Annotated[bool, Field(description="Add position/rotation to the current values.")] = False,
        visible: bool | None = None,
        label: Annotated[str | None, Field(description="New label.")] = None,
        drop_to_floor: Annotated[bool, Field(description="Move it so its lowest point touches Y = 0.")] = False,
        select: Annotated[bool, Field(description="Select it in Daz.")] = False,
        parent: Annotated[str | None, Field(description="Attach it to this node (it keeps its place in the "
                                                        "world); \"\" detaches it.")] = None,
        parent_bone: Annotated[str | None, Field(description="With parent = a figure: the bone to attach to, "
                                                             "e.g. 'r_hand' for a sword, 'head' for a hat.")] = None,
    ) -> dict:
        """Moves, rotates, scales, shows/hides, renames, selects or attaches (parents) a figure, prop,
        camera or light."""
        return await call("node_set", _clean(node=node, position=position, rotation=rotation, scale=scale,
                                             relative=relative, visible=visible, label=label,
                                             drop_to_floor=drop_to_floor, select=select, parent=parent,
                                             parent_bone=parent_bone))

    @mcp.tool(annotations=DESTRUCTIVE)
    async def node_delete(
        nodes: Annotated[list[str], Field(min_length=1, description="Labels of the nodes to delete.")],
        with_fitted: Annotated[bool, Field(description="Also delete clothing and hair fitted to a figure.")] = True,
    ) -> dict:
        """Deletes nodes (figures, clothing, hair, props, cameras, lights) from the scene."""
        return await call("node_delete", {"nodes": nodes, "with_fitted": with_fitted})

    # ----------------------------------------------------- characters ----
    @mcp.tool(annotations=READ_ONLY)
    async def figure_info(
        figure: Annotated[str, Field(description="Figure label.")],
        all_bones: Annotated[bool, Field(description="List every bone name (for pose_bones).")] = False,
    ) -> dict:
        """Describes a figure: generation, height, what it wears, the shape dials in use, the posed
        bones and its surfaces."""
        return await call("figure_info", {"figure": figure, "all_bones": all_bones})

    @mcp.tool(annotations=READ_ONLY)
    async def morph_list(
        node: Annotated[str, Field(description="Figure (or item) label.")],
        query: Annotated[str | None, Field(description="Words in the dial's label, name or group, "
                                                       "e.g. 'height' or 'head'.")] = None,
        only_nonzero: Annotated[bool, Field(description="Only dials that are in use.")] = False,
        include_hidden: bool = False,
        limit: Annotated[int, Field(ge=1, le=1000)] = 100,
    ) -> dict:
        """Lists the shape dials (morphs) of a figure with their value and range."""
        return await call("morph_list", _clean(node=node, query=query, only_nonzero=only_nonzero,
                                               include_hidden=include_hidden, limit=limit))

    @mcp.tool(annotations=CHANGES_SCENE)
    async def morph_set(
        node: Annotated[str, Field(description="Figure (or item) label.")],
        values: Annotated[dict[str, float], Field(description="{dial label or name: value}, usually 0 to 1.")],
    ) -> dict:
        """Sets shape dials (morphs), e.g. {"Body Tone": 0.5}. Unknown dials come back with similar names."""
        return await call("morph_set", {"node": node, "values": values})

    @mcp.tool(annotations=CHANGES_SCENE)
    async def pose_bones(
        figure: Annotated[str, Field(description="Figure label.")],
        bones: Annotated[dict[str, Vec3], Field(description="{bone name: [x, y, z] degrees}, e.g. "
                                                            "{\"l_upperarm\": [0, 0, -40]}.")],
        relative: Annotated[bool, Field(description="Add to the current rotation.")] = False,
    ) -> dict:
        """Rotates figure bones, for adjustments after a pose preset (head turn, arm angle)."""
        return await call("pose_bones", {"figure": figure, "bones": bones, "relative": relative})

    @mcp.tool(annotations=CHANGES_SCENE)
    async def pose_reset(figure: Annotated[str, Field(description="Figure label.")]) -> dict:
        """Returns all the bones of a figure to the default pose."""
        return await call("pose_reset", {"figure": figure})

    @mcp.tool(annotations=CHANGES_SCENE)
    async def wearable_fit(
        item: Annotated[str, Field(description="Clothing or hair label.")],
        figure: Annotated[str | None, Field(description="Figure to fit it to; omit to unfit it.")] = None,
    ) -> dict:
        """Fits clothing or hair already in the scene to a figure (Daz "Fit To"), or unfits it."""
        return await call("wearable_fit", _clean(item=item, figure=figure))

    # -------------------------------------------------------- cameras ----
    @mcp.tool(annotations=CHANGES_SCENE)
    async def camera_create(
        label: str = "Camera",
        frame: Annotated[list[str] | None, Field(description="Labels to fit in the picture, e.g. both "
                                                             "figures. Places and aims the camera.")] = None,
        yaw: Annotated[float, Field(description="With frame: degrees around them; 0 = in front, 90 = their "
                                                "left, -90 = their right.")] = 0,
        pitch: Annotated[float, Field(description="With frame: degrees above their center.")] = 5,
        margin: Annotated[float, Field(ge=1, le=5, description="With frame: 1.1 leaves 10 % of room.")] = 1.1,
        position: Annotated[Vec3 | None, Field(description="[x, y, z] cm.")] = None,
        look_at: Target | None = None,
        rotation: Annotated[Vec3 | None, Field(description="[x, y, z] degrees when not aiming.")] = None,
        focal_length: Annotated[float | None, Field(ge=1, le=1000, description="mm; 35 wide, 65 default, "
                                                                               "85-135 portraits.")] = None,
        make_active: Annotated[bool, Field(description="Look through it (captures and renders use it).")] = True,
    ) -> dict:
        """Adds a camera, either framing nodes automatically or at a position aimed at a target."""
        return await call("camera_create", _clean(label=label, frame=frame, yaw=yaw, pitch=pitch, margin=margin,
                                                  position=position, look_at=look_at, rotation=rotation,
                                                  focal_length=focal_length, make_active=make_active))

    @mcp.tool(annotations=CHANGES_SCENE)
    async def camera_set(
        camera: Annotated[str, Field(description="Camera label.")],
        frame: Annotated[list[str] | None, Field(description="Labels to fit in the picture.")] = None,
        yaw: float = 0,
        pitch: float = 5,
        margin: Annotated[float, Field(ge=1, le=5)] = 1.1,
        position: Vec3 | None = None,
        look_at: Target | None = None,
        rotation: Vec3 | None = None,
        focal_length: Annotated[float | None, Field(ge=1, le=1000)] = None,
        make_active: bool = False,
        label: Annotated[str | None, Field(description="New label.")] = None,
    ) -> dict:
        """Moves, aims or reframes an existing camera, or makes it the active one."""
        return await call("camera_set", _clean(camera=camera, frame=frame, yaw=yaw, pitch=pitch, margin=margin,
                                               position=position, look_at=look_at, rotation=rotation,
                                               focal_length=focal_length, make_active=make_active, label=label))

    # --------------------------------------------------------- lights ----
    @mcp.tool(annotations=CHANGES_SCENE)
    async def light_create(
        type: Annotated[Literal["spot", "point", "distant"], Field(description="spot, point, or distant (sun).")] = "spot",
        label: str | None = None,
        position: Annotated[Vec3 | None, Field(description="[x, y, z] cm.")] = None,
        look_at: Target | None = None,
        rotation: Vec3 | None = None,
        power: Annotated[float | None, Field(ge=0, description="Lumens for spot/point (Iray default 1500); "
                                                               "intensity for distant.")] = None,
        color: Color | None = None,
        spread_angle: Annotated[float | None, Field(ge=0, le=180, description="Spot cone, degrees.")] = None,
        properties: Annotated[dict[str, Any] | None, Field(description="{label: value} other light "
                                                                       "properties.")] = None,
    ) -> dict:
        """Adds a light, placed and aimed at a node or point."""
        return await call("light_create", _clean(type=type, label=label, position=position, look_at=look_at,
                                                 rotation=rotation, power=power, color=color,
                                                 spread_angle=spread_angle, properties=properties))

    @mcp.tool(annotations=CHANGES_SCENE)
    async def light_set(
        light: Annotated[str, Field(description="Light label.")],
        position: Vec3 | None = None,
        look_at: Target | None = None,
        rotation: Vec3 | None = None,
        power: Annotated[float | None, Field(ge=0)] = None,
        color: Color | None = None,
        spread_angle: Annotated[float | None, Field(ge=0, le=180)] = None,
        on: Annotated[bool | None, Field(description="Switch the light on or off.")] = None,
        label: Annotated[str | None, Field(description="New label.")] = None,
        properties: dict[str, Any] | None = None,
    ) -> dict:
        """Changes a light: placement, aim, power, color, on/off."""
        return await call("light_set", _clean(light=light, position=position, look_at=look_at, rotation=rotation,
                                              power=power, color=color, spread_angle=spread_angle, on=on,
                                              label=label, properties=properties))

    @mcp.tool(annotations=CHANGES_SCENE)
    async def environment_set(
        mode: Annotated[Literal["dome_and_scene", "dome_only", "sun_sky", "scene_only"] | None,
                        Field(description="scene_only turns the dome off so only scene lights count.")] = None,
        intensity: Annotated[float | None, Field(ge=0, description="Dome strength, 1 = default.")] = None,
        hdri: Annotated[str | None, Field(description="Absolute path of an .hdr/.exr image; \"\" removes it.")] = None,
        rotation: Annotated[float | None, Field(description="Dome rotation, degrees.")] = None,
        draw_dome: Annotated[bool | None, Field(description="Show the HDRI as the background.")] = None,
    ) -> dict:
        """Sets the Iray environment (dome light, HDRI, sun-sky). Without arguments it reports it."""
        return await call("environment_set", _clean(mode=mode, intensity=intensity,
                                                    hdri=_abs(hdri) if hdri else hdri, rotation=rotation,
                                                    draw_dome=draw_dome))

    # ------------------------------------------------------ materials ----
    @mcp.tool(annotations=READ_ONLY)
    async def material_list(
        node: Annotated[str, Field(description="Label of a figure, clothing, hair or prop.")],
        surfaces: Annotated[list[str] | None, Field(description="Only these surfaces.")] = None,
        all_properties: Annotated[bool, Field(description="Every property, not only the main ones (long).")] = False,
        query: Annotated[str | None, Field(description="Only properties whose label contains this.")] = None,
    ) -> dict:
        """Lists the surfaces of a node with their shader and main values (color, roughness, maps...)."""
        return await call("material_list", _clean(node=node, surfaces=surfaces, all_properties=all_properties,
                                                  query=query))

    @mcp.tool(annotations=CHANGES_SCENE)
    async def material_set(
        node: Annotated[str, Field(description="Node label.")],
        properties: Annotated[dict[str, Any], Field(description="{property label: value}: number, bool, color "
                                                                "[r,g,b] 0..1 or \"#rrggbb\", option name, or "
                                                                "{\"map\": \"/abs/image.png\" or null}.")],
        surfaces: Annotated[list[str] | None, Field(description="Surfaces to change; omit for all.")] = None,
    ) -> dict:
        """Changes material properties, e.g. {"Base Color": "#802020", "Glossy Roughness": 0.3}."""
        return await call("material_set", _clean(node=node, surfaces=surfaces, properties=_maps_to_abs(properties)))

    # -------------------------------------------------------- render -----
    @mcp.tool(annotations=CHANGES_SCENE)
    async def render_settings(
        width: Annotated[int | None, Field(ge=16, le=16384)] = None,
        height: Annotated[int | None, Field(ge=16, le=16384)] = None,
        max_samples: Annotated[int | None, Field(ge=1)] = None,
        max_time: Annotated[float | None, Field(ge=1, description="Seconds.")] = None,
        quality: Annotated[float | None, Field(gt=0, description="Iray Rendering Quality, 1 = default.")] = None,
        properties: Annotated[dict[str, Any] | None, Field(description="{label: value} other render "
                                                                       "settings.")] = None,
    ) -> dict:
        """Reads the render settings (renderer, size, limits) and changes the ones given."""
        return await call("render_settings", _clean(width=width, height=height, max_samples=max_samples,
                                                    max_time=max_time, quality=quality, properties=properties))

    @mcp.tool(annotations=CHANGES_SCENE, structured_output=False)
    async def render(
        camera: Annotated[str | None, Field(description="Camera label; default is the active one.")] = None,
        width: Annotated[int | None, Field(ge=16, le=16384)] = None,
        height: Annotated[int | None, Field(ge=16, le=16384)] = None,
        max_samples: Annotated[int | None, Field(ge=1)] = None,
        max_time: Annotated[float | None, Field(ge=1, description="Stop after this many seconds.")] = None,
        quality: Annotated[float | None, Field(gt=0)] = None,
        out_path: Annotated[str | None, Field(description="Absolute .png or .jpg path; default "
                                                          "~/.daz3d-mcp/renders/.")] = None,
        overwrite: bool = False,
        preview_size: Annotated[int, Field(ge=64, le=4096)] = 1024,
        frame: Annotated[int | None, Field(ge=0, description="Timeline frame to render; default the "
                                                             "current one.")] = None,
    ) -> list:
        """Renders the scene with the current renderer (Iray), waits until it is done and returns the
        image. Set max_time or max_samples so a test render does not run for long."""
        settings = get_client().settings
        if out_path:
            out = Path(_abs(out_path))
            if out.suffix.lower() not in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"):
                out = out.with_name(out.name + ".png")
            if out.exists() and not overwrite:
                raise ToolError(f"{out} already exists. Pass overwrite=true or another path.")
        else:
            folder = Path(settings.render_dir).expanduser() if settings.render_dir else config_dir() / "renders"
            folder.mkdir(parents=True, exist_ok=True)
            out = folder / f"render-{time.strftime('%Y%m%d-%H%M%S')}.png"
        captures = config_dir() / "captures"
        captures.mkdir(parents=True, exist_ok=True)
        preview = captures / f"render-preview-{int(time.time() * 1000)}.png"
        result = await call("render", _clean(out_path=out.as_posix(), preview_path=preview.as_posix(),
                                             preview_size=preview_size, camera=camera, width=width, height=height,
                                             max_samples=max_samples, max_time=max_time, quality=quality,
                                             frame=frame),
                            timeout=settings.render_timeout)
        content: list = []
        shown = Path(result["preview"]) if result.get("preview") else Path(result["path"])
        if shown.is_file() and shown.stat().st_size <= PREVIEW_MAX_BYTES:
            fmt = "jpeg" if shown.suffix.lower() in (".jpg", ".jpeg") else "png"
            if shown.suffix.lower() in (".png", ".jpg", ".jpeg"):
                content.append(Image(data=shown.read_bytes(), format=fmt))
        content.append(json.dumps(result))
        return content

    @mcp.tool(annotations=CHANGES_SCENE, structured_output=False)
    async def render_animation(
        ctx: Context,
        camera: Annotated[str | None, Field(description="Camera label; default is the active one.")] = None,
        start_frame: Annotated[int | None, Field(ge=0, description="Default: start of the timeline range.")] = None,
        end_frame: Annotated[int | None, Field(ge=0, description="Default: end of the timeline range.")] = None,
        step: Annotated[int, Field(ge=1, le=100, description="Render every n-th frame (2 = half the frames).")] = 1,
        width: Annotated[int | None, Field(ge=16, le=16384)] = None,
        height: Annotated[int | None, Field(ge=16, le=16384)] = None,
        max_samples: Annotated[int | None, Field(ge=1, description="Per frame.")] = None,
        max_time: Annotated[float | None, Field(ge=1, description="Seconds per frame. Set it: the total "
                                                                  "is about frames x max_time.")] = None,
        quality: Annotated[float | None, Field(gt=0)] = None,
        out_dir: Annotated[str | None, Field(description="Absolute folder for the frames and the video; "
                                                         "default a new folder in ~/.daz3d-mcp/renders/.")] = None,
        name: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$",
                                   description="File name start: <name>_0000.png ...")] = "frame",
        image_format: Literal["png", "jpg"] = "png",
        video_format: Annotated[Literal["mp4", "gif", "none"], Field(description="Also join the frames into "
                                                                                 "a video (needs ffmpeg; Daz "
                                                                                 "Studio ships one).")] = "mp4",
        fps: Annotated[float | None, Field(gt=0, le=240, description="Video frame rate; default timeline "
                                                                     "fps / step.")] = None,
        resume: Annotated[bool, Field(description="Keep frames already in out_dir and render only the missing "
                                                  "ones (to continue a stopped render).")] = True,
        previews: Annotated[int, Field(ge=0, le=6, description="Frames to return as images.")] = 3,
        preview_size: Annotated[int, Field(ge=64, le=2048)] = 512,
    ) -> list:
        """Renders the whole animation (or a frame range) with Iray, one image per frame, and joins
        them into an MP4 or GIF. Waits until it is done. It takes about frames x max_time: render a
        short range or a few frames (step) first, and ask the user before a long render."""
        settings = get_client().settings
        tl = await call("anim_timeline", {"list_animated": False})
        tl_fps = float(tl.get("fps") or 30)
        a = int(tl["start_frame"]) if start_frame is None else start_frame
        b = int(tl["end_frame"]) if end_frame is None else end_frame
        if b < a:
            raise ToolError(f"end_frame ({b}) is before start_frame ({a}).")
        frames = list(range(a, b + 1, step))
        if out_dir:
            folder = Path(_abs(out_dir))
        else:
            base = Path(settings.render_dir).expanduser() if settings.render_dir else config_dir() / "renders"
            folder = base / f"anim-{time.strftime('%Y%m%d-%H%M%S')}"
        folder.mkdir(parents=True, exist_ok=True)
        ext = "." + image_format
        files = {f: folder / f"{name}_{f:04d}{ext}" for f in frames}
        if not resume:
            taken = [p for p in files.values() if p.exists()]
            if taken:
                raise ToolError(f"{len(taken)} frames already exist in {folder}. Pass resume=true to keep "
                                "them, or another out_dir.")
        todo = [f for f in frames if not files[f].exists()]

        used = await call("render_settings", _clean(width=width, height=height, max_samples=max_samples,
                                                    max_time=max_time, quality=quality))

        n_prev = min(previews, len(frames))
        preview_frames = sorted({frames[round(i * (len(frames) - 1) / max(n_prev - 1, 1))]
                                 for i in range(n_prev)})
        captures = config_dir() / "captures"
        captures.mkdir(parents=True, exist_ok=True)
        preview_files: dict[int, Path] = {}

        started = time.time()
        seconds: list[float] = []
        cam_used = camera
        for i, f in enumerate(todo):
            args = _clean(out_path=files[f].as_posix(), camera=camera, frame=f)
            if f in preview_frames:
                pv = captures / f"anim-preview-{int(time.time() * 1000)}-{f}.png"
                args.update(preview_path=pv.as_posix(), preview_size=preview_size)
            try:
                res = await call("render", args, timeout=settings.render_timeout)
            except ToolError as exc:
                done = len(frames) - len(todo) + i
                raise ToolError(f"Frame {f} failed: {exc} {done} of {len(frames)} frames are in {folder}; "
                                "call render_animation again with this out_dir to continue.") from exc
            seconds.append(float(res.get("seconds") or 0))
            cam_used = res.get("camera") or cam_used
            if res.get("preview"):
                preview_files[f] = Path(res["preview"])
            try:
                await ctx.report_progress(i + 1, len(todo), f"frame {f} ({i + 1}/{len(todo)})")
            except Exception:  # progress is optional; not every client asks for it
                pass

        result: dict[str, Any] = {
            "folder": folder.as_posix(),
            "frames": len(frames),
            "first_frame": frames[0],
            "last_frame": frames[-1],
            "step": step,
            "rendered": len(todo),
            "kept": len(frames) - len(todo),
            "files": f"{name}_####{ext}",
            "camera": cam_used,
            "seconds": round(time.time() - started, 1),
            "seconds_per_frame": round(sum(seconds) / len(seconds), 1) if seconds else None,
            "settings": used,
            "video": None,
        }
        if video_format != "none":
            vfps = fps or tl_fps / step
            ffmpeg = video.find_ffmpeg(settings.extra.get("ffmpeg"))
            if not ffmpeg:
                result["video_error"] = ("No ffmpeg found (looked on PATH and in the Daz Studio folder). "
                                         "Install ffmpeg or set \"ffmpeg\" in ~/.daz3d-mcp/settings.json.")
            else:
                out = folder / f"{name}.{video_format}"
                try:
                    await anyio.to_thread.run_sync(
                        lambda: video.encode(ffmpeg, [files[f] for f in frames], out, vfps, video_format))
                    result["video"] = out.as_posix()
                    result["video_fps"] = round(vfps, 3)
                    result["video_seconds"] = round(len(frames) / vfps, 2)
                except video.VideoError as exc:
                    result["video_error"] = str(exc)

        content: list = []
        for f in preview_frames:
            shown = preview_files.get(f) or files[f]
            suffix = shown.suffix.lower()
            if shown.is_file() and shown.stat().st_size <= PREVIEW_MAX_BYTES and suffix in (".png", ".jpg", ".jpeg"):
                content.append(f"frame {f}")
                content.append(Image(data=shown.read_bytes(), format="png" if suffix == ".png" else "jpeg"))
        content.append(json.dumps(result))
        return content

    return forget
