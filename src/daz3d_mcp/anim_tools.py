"""Stage 4 tools: animation.

Keyframes, the timeline, presets (clips), moving and retiming animations,
BVH and FBX motion import with bone maps, foot contact, and previews.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated, Any, Awaitable, Callable, Literal

import anyio
from mcp.server.fastmcp import FastMCP, Image
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from daz3d_mcp import clips, motion
from daz3d_mcp.client import DazClient
from daz3d_mcp.paths import config_dir

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
CHANGES_SCENE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)

Vec3 = Annotated[list[float], Field(min_length=3, max_length=3)]
Axes = Annotated[list[float | None], Field(min_length=3, max_length=3, description="[x, y, z]; null skips an axis.")]
Call = Callable[..., Awaitable[Any]]

BONES_PER_CALL = 12
CONVENTION_GOOD = 3.0  # degrees of mean joint-angle error that count as a match


class KeyPose(BaseModel):
    """What to key at one frame."""
    frame: Annotated[float, Field(ge=0, description="Frame number (30 per second by default).")]
    bones: Annotated[dict[str, Axes] | None, Field(description="{bone: [x, y, z] degrees}, e.g. "
                                                              "{\"l_thigh\": [-25, 0, 0]}.")] = None
    bone_positions: Annotated[dict[str, Axes] | None, Field(description="{bone: [x, y, z] cm} bone translation; "
                                                                       "mostly the hip, to move the body up, "
                                                                       "down or along its path.")] = None
    position: Annotated[Axes | None, Field(description="The node's own position [x, y, z] cm.")] = None
    rotation: Annotated[Axes | None, Field(description="The node's own rotation [x, y, z] degrees.")] = None
    scale: Annotated[float | None, Field(gt=0)] = None
    morphs: Annotated[dict[str, float] | None, Field(description="{dial label: value}, e.g. facial expressions.")] = None
    properties: Annotated[dict[str, float] | None, Field(description="{property label: number}, e.g. a light's "
                                                                    "power or a camera's focal length.")] = None


def _clean(**kwargs) -> dict:
    return {k: v for k, v in kwargs.items() if v is not None}


def poses_to_tracks(keys: list[KeyPose]) -> dict:
    tracks: dict = {}

    def add(group: str, item: str | None, kind: str | None, row: list) -> None:
        g = tracks.setdefault(group, {})
        if group == "bones":
            g.setdefault(item, {}).setdefault(kind, []).append(row)
        elif group == "node":
            g.setdefault(kind, []).append(row)
        else:
            g.setdefault(item, []).append(row)

    for k in sorted(keys, key=lambda p: p.frame):
        f = k.frame
        for bone, v in (k.bones or {}).items():
            add("bones", bone, "rotation", [f] + list(v))
        for bone, v in (k.bone_positions or {}).items():
            add("bones", bone, "position", [f] + list(v))
        if k.position:
            add("node", None, "position", [f] + list(k.position))
        if k.rotation:
            add("node", None, "rotation", [f] + list(k.rotation))
        if k.scale:
            add("node", None, "scale", [f, k.scale])
        for name, v in (k.morphs or {}).items():
            add("morphs", name, None, [f, v])
        for name, v in (k.properties or {}).items():
            add("properties", name, None, [f, v])
    return tracks


def _chunks(tracks: dict, size: int) -> list[dict]:
    """Splits bone tracks over several calls so each request stays small."""
    bones = list((tracks.get("bones") or {}).items())
    rest = {k: v for k, v in tracks.items() if k != "bones" and v}
    out: list[dict] = []
    for i in range(0, max(len(bones), 1), size):
        part = dict(bones[i:i + size])
        chunk = {"bones": part} if part else {}
        if i == 0:
            chunk.update(rest)
        if chunk:
            out.append(chunk)
    return out or [{}]


def _calibration_file() -> Path:
    return config_dir() / "animation.json"


def load_convention(settings_extra: dict) -> str | None:
    forced = settings_extra.get("rotation_convention")
    if forced in motion.CONVENTIONS:
        return forced
    try:
        data = json.loads(_calibration_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    c = data.get("convention")
    return c if c in motion.CONVENTIONS else None


def save_convention(convention: str, error: float | None, daz_version: str | None) -> None:
    path = _calibration_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"convention": convention, "mean_error_deg": error, "daz_version": daz_version,
                                "measured": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=2) + "\n", encoding="utf-8")


def register(mcp: FastMCP, call: Call, get_client: Callable[[], DazClient]) -> None:

    async def skeleton(figure: str) -> motion.TargetSkeleton:
        data = await call("anim_skeleton", {"figure": figure})
        try:
            return motion.TargetSkeleton.from_daz(data)
        except motion.MotionError as exc:
            raise ToolError(str(exc)) from exc

    async def set_tracks(node: str, tracks: dict, replace: list[float] | None = None,
                         extend_range: bool = True) -> dict:
        total = {"keys_set": 0, "not_found": {"bones": [], "morphs": [], "properties": []}}
        last: dict = {}
        for chunk in _chunks(tracks, BONES_PER_CALL):
            last = await call("anim_keys_set", _clean(node=node, tracks=chunk, replace=replace,
                                                      extend_range=None if extend_range else False))
            total["keys_set"] += last.get("keys_set", 0)
            for k, v in (last.get("not_found") or {}).items():
                total["not_found"][k] += v
        out = dict(last, keys_set=total["keys_set"])
        out.pop("not_found", None)
        out.pop("hint", None)
        nf = {k: v for k, v in total["not_found"].items() if v}
        if nf:
            out["not_found"] = nf
            if nf.get("bones"):
                out["hint"] = "figure_info with all_bones=true lists the bone names of this figure."
        return out

    def convention_now() -> str | None:
        return load_convention(get_client().settings.extra)

    # ------------------------------------------------------ timeline ----
    @mcp.tool(annotations=CHANGES_SCENE)
    async def anim_timeline(
        fps: Annotated[float | None, Field(gt=0, le=1000, description="New frame rate (Daz default 30).")] = None,
        keep: Annotated[Literal["duration", "frames"], Field(description="With fps: duration keeps keys at their "
                                                                         "time in seconds; frames keeps them on "
                                                                         "their frame numbers (plays faster or "
                                                                         "slower).")] = "duration",
        start_frame: Annotated[int | None, Field(ge=0)] = None,
        end_frame: Annotated[int | None, Field(ge=0, description="Last frame of the animation range.")] = None,
        frame: Annotated[int | None, Field(ge=0, description="Go to this frame (poses and presets apply here).")] = None,
    ) -> dict:
        """Reads or sets the timeline: frame rate, animation range, current frame. Also lists which
        nodes are animated and over which frames."""
        return await call("anim_timeline", _clean(fps=fps, keep=keep if fps else None, start_frame=start_frame,
                                                  end_frame=end_frame, frame=frame))

    # ---------------------------------------------------------- keys ----
    @mcp.tool(annotations=CHANGES_SCENE)
    async def anim_keys_set(
        node: Annotated[str, Field(description="Label of a figure, prop, camera or light.")],
        keys: Annotated[list[KeyPose] | None, Field(description="Key poses, one per frame: bone rotations, hip "
                                                                "translation, the node's own transform, dials.")] = None,
        tracks: Annotated[dict | None, Field(description="Advanced: the tracks format anim_keys_get returns "
                                                         "({bones: {bone: {rotation: [[frame, x, y, z], ...]}}, "
                                                         "node: {...}, morphs: {...}}).")] = None,
        replace: Annotated[list[float] | None, Field(min_length=2, max_length=2, description="[first, last] frame: "
                                                     "first delete the old keys there on every channel that "
                                                     "gets keys.")] = None,
    ) -> dict:
        """Sets keyframes. Each key pose says what a node looks like at one frame; Daz fills in the
        frames between. Rotations are the same dials as pose_bones (degrees). The scene range grows to
        the last key."""
        if not keys and not tracks:
            raise ToolError("Give keys (a list of key poses) or tracks.")
        t = poses_to_tracks(keys) if keys else {}
        for group, items in (tracks or {}).items():
            if group == "bones":
                for bone, kinds in items.items():
                    for kind, rows in kinds.items():
                        t.setdefault("bones", {}).setdefault(bone, {}).setdefault(kind, []).extend(rows)
            elif group == "node":
                for kind, rows in items.items():
                    t.setdefault("node", {}).setdefault(kind, []).extend(rows)
            else:
                for item, rows in items.items():
                    t.setdefault(group, {}).setdefault(item, []).extend(rows)
        return await set_tracks(node, t, replace)

    @mcp.tool(annotations=READ_ONLY)
    async def anim_keys_get(
        node: Annotated[str, Field(description="Node label.")],
        bones: Annotated[list[str] | None, Field(description="Only these bones.")] = None,
        start_frame: float | None = None,
        end_frame: float | None = None,
        summary: Annotated[bool, Field(description="Only which bones and dials are keyed and over which "
                                                   "frames.")] = False,
    ) -> dict:
        """Reads keyframes of a node as tracks ({bones: {bone: {rotation: [[frame, x, y, z], ...]}}...}),
        the same format anim_keys_set takes."""
        return await call("anim_keys_get", _clean(node=node, bones=bones, start_frame=start_frame,
                                                  end_frame=end_frame, summary=summary or None))

    @mcp.tool(annotations=DESTRUCTIVE)
    async def anim_keys_delete(
        node: Annotated[str, Field(description="Node label.")],
        what: Annotated[list[Literal["node", "bones", "morphs"]] | None, Field(description="Default all.")] = None,
        bones: Annotated[list[str] | None, Field(description="Only these bones.")] = None,
        start_frame: float | None = None,
        end_frame: float | None = None,
    ) -> dict:
        """Deletes keyframes (all of a node's, or some bones', or a frame range). The pose at the current
        frame stays as a still pose."""
        return await call("anim_keys_delete", _clean(node=node, what=what, bones=bones, start_frame=start_frame,
                                                     end_frame=end_frame))

    @mcp.tool(annotations=CHANGES_SCENE)
    async def anim_key_pose(
        figure: Annotated[str, Field(description="Figure label.")],
        frames: Annotated[list[float], Field(min_length=1, description="Frames to key the current pose at.")],
        all_bones: Annotated[bool, Field(description="Key every bone (default: posed or animated ones and the "
                                                     "hip).")] = False,
        with_node: Annotated[bool, Field(description="Also key the figure's position and rotation.")] = False,
        morphs: Annotated[list[str] | None, Field(description="Also key these dials (expressions).")] = None,
    ) -> dict:
        """Keys the figure's current pose at frames: after a pose preset or pose_bones, this turns the
        pose into a key pose of the animation."""
        return await call("anim_key_pose", _clean(figure=figure, frames=frames, all_bones=all_bones,
                                                  with_node=with_node, morphs=morphs))

    # --------------------------------------------------- reshape it ----
    @mcp.tool(annotations=CHANGES_SCENE)
    async def anim_retime(
        node: Annotated[str, Field(description="Node label.")],
        speed: Annotated[float | None, Field(gt=0, description="2 = twice as fast, 0.5 = half speed.")] = None,
        length: Annotated[float | None, Field(gt=0, description="Or: frames the part should last.")] = None,
        start_frame: Annotated[float | None, Field(ge=0, description="Part to retime; default the whole "
                                                                     "animation.")] = None,
        end_frame: float | None = None,
        snap: Annotated[bool, Field(description="Keep keys on whole frames.")] = True,
        with_followers: Annotated[bool, Field(description="Also retime clothing and hair keys.")] = False,
    ) -> dict:
        """Changes the rhythm of an animation: speeds it up, slows it down or fits it to a length.
        Keys after the part move with it."""
        if speed is None and length is None:
            raise ToolError("Give speed or length.")
        return await call("anim_retime", _clean(node=node, speed=speed, length=length, start_frame=start_frame,
                                                end_frame=end_frame, snap=snap, with_followers=with_followers))

    @mcp.tool(annotations=CHANGES_SCENE)
    async def anim_offset(
        node: Annotated[str, Field(description="Node label.")],
        frames: Annotated[float | None, Field(description="Start it this many frames later (negative: "
                                                          "earlier).")] = None,
        move: Annotated[Vec3 | None, Field(description="Carry the whole motion by [x, y, z] cm.")] = None,
        turn: Annotated[float | None, Field(description="Turn the whole motion (its path too) by degrees "
                                                        "around Y.")] = None,
        start_at: Annotated[list[float] | None, Field(min_length=2, max_length=2, description="[x, z] cm where "
                                                      "the figure's hip should be at the first key.")] = None,
        with_followers: Annotated[bool, Field(description="With frames: shift clothing and hair keys too.")] = False,
    ) -> dict:
        """Relocates an animation: in time (later or earlier) and in space (move it, turn its path,
        or make it start at a spot). The motion itself does not change."""
        return await call("anim_offset", _clean(node=node, frames=frames, move=move, turn=turn, start_at=start_at,
                                                with_followers=with_followers))

    # --------------------------------------------------- look at it ----
    @mcp.tool(annotations=READ_ONLY)
    async def anim_sample(
        figure: Annotated[str, Field(description="Figure (or node) label.")],
        frames: Annotated[list[float], Field(min_length=1, max_length=500)],
        bones: Annotated[list[str] | None, Field(description="Bones whose world position to report, e.g. "
                                                             "[\"l_foot\", \"r_foot\", \"l_hand\"].")] = None,
    ) -> dict:
        """World positions (cm, Y up) of bones at some frames, as Daz computes them. Use it to check a
        motion with numbers: is the left foot in front at frame 8, does the hand reach the cup."""
        return await call("anim_sample", _clean(figure=figure, frames=frames, bones=bones))

    @mcp.tool(annotations=READ_ONLY, structured_output=False)
    async def anim_preview(
        frames: Annotated[list[int] | None, Field(max_length=12, description="Frames to show; default 6 "
                                                                            "spread over the range.")] = None,
        camera: Annotated[str | None, Field(description="Camera to look through.")] = None,
        max_size: Annotated[int, Field(ge=64, le=2048)] = 512,
    ) -> list:
        """Viewport images of several frames, to watch the motion (a contact sheet, one image each)."""
        if not frames:
            tl = await call("anim_timeline", {"list_animated": False})
            a, b = int(tl["start_frame"]), int(tl["end_frame"])
            n = 6 if b - a >= 5 else b - a + 1
            frames = sorted({round(a + (b - a) * i / max(n - 1, 1)) for i in range(n)})
        captures = config_dir() / "captures"
        captures.mkdir(parents=True, exist_ok=True)
        content: list = []
        for f in frames:
            out = captures / f"viewport-anim-{int(time.time() * 1000)}-{f}.png"
            result = await call("viewport_capture", _clean(out_path=out.as_posix(), max_size=max_size, frame=f,
                                                           camera=camera))
            path = Path(result.get("path") or out)
            if path.is_file():
                content.append(f"frame {f}")
                content.append(Image(data=path.read_bytes(), format="png"))
        return content

    @mcp.tool(annotations=CHANGES_SCENE)
    async def anim_foot_contact(
        figure: Annotated[str, Field(description="Figure label.")],
        start_frame: Annotated[int | None, Field(ge=0)] = None,
        end_frame: Annotated[int | None, Field(ge=0)] = None,
        fix: Annotated[Literal["none", "lift", "plant"], Field(description="lift: raise the body where a foot goes "
                                                                           "through the floor; plant: also lower it "
                                                                           "where both feet float (not for jumps).")] = "none",
        floor: Annotated[float, Field(description="Floor height in cm.")] = 0.0,
        tolerance: Annotated[float, Field(ge=0, le=20, description="cm that still count as touching.")] = 1.0,
    ) -> dict:
        """Checks the feet over an animation: frames where a foot goes through the floor, frames where
        the figure floats, and how far planted feet slide. With fix it moves the hip up or down per
        frame so the lowest foot touches the floor."""
        skel = await skeleton(figure)
        feet = motion.foot_bones(skel)
        bones = [b for side in feet.values() for b in side]
        if not bones:
            raise ToolError(f"No foot bones found on {figure}.")
        first, last = start_frame, end_frame
        if first is None or last is None:
            got = await call("anim_keys_get", {"node": figure, "summary": True})
            tl = await call("anim_timeline", {"list_animated": False})
            if first is None:
                first = int(got["first_frame"]) if got.get("first_frame") is not None else int(tl["start_frame"])
            if last is None:
                last = int(round(got["last_frame"])) if got.get("last_frame") is not None else int(tl["end_frame"])
        frames = list(range(int(first), int(last) + 1))
        if len(frames) > 2000:
            raise ToolError("At most 2000 frames at a time; give start_frame and end_frame.")
        root = skel.root()
        conv = convention_now() or motion.DEFAULT_CONVENTION

        async def measure() -> tuple[dict, dict]:
            data = await call("anim_sample", {"figure": figure, "frames": frames, "bones": bones,
                                              "dial_bones": [root]})
            samples = {int(float(f)): row["bones"] for f, row in data["frames"].items()}
            heights = motion.contact_heights(skel, feet, samples, floor, data.get("scale") or 1.0)
            return data, heights

        data, heights = await measure()
        report = motion.contact_report(heights, tolerance)
        out: dict = {"figure": figure, "frames": [frames[0], frames[-1]], "feet": feet, "before": report}
        if fix != "none":
            scale = data.get("scale") or 1.0
            rows = []
            changed = 0
            orient = skel.bones[root].orient
            for f in frames:
                row = heights.get(f) or {}
                if not row:
                    continue
                low = min(v["height"] for v in row.values())
                delta = 0.0
                if low < -tolerance / 4 or (fix == "plant" and low > tolerance / 4):
                    delta = -low
                dials = data["frames"][str(f) if str(f) in data["frames"] else str(float(f))]["dials"][root]["position"]
                if abs(delta) > 1e-4:
                    changed += 1
                d = motion.dial_translation((0.0, delta / scale, 0.0), orient, conv)
                rows.append([f, round(dials[0] + d[0], 3), round(dials[1] + d[1], 3), round(dials[2] + d[2], 3)])
            if changed:
                await set_tracks(figure, {"bones": {root: {"position": rows}}})
            _data, heights = await measure()
            out["frames_changed"] = changed
            out["after"] = motion.contact_report(heights, tolerance)
        slide = max(report["slide_cm"].values()) if report["slide_cm"] else 0
        if slide > 3:
            out["note"] = (f"A planted foot slides up to {slide} cm. Root motion that does not match the steps "
                           "causes it: retime the motion, or for a cycle use anim_import(in_place=true) and move "
                           "the figure with anim_offset/keys.")
        return out

    # ------------------------------------------------------ presets ----
    @mcp.tool(annotations=READ_ONLY)
    async def anim_preset_list(
        query: Annotated[str | None, Field(description="Words in the name or description.")] = None,
    ) -> dict:
        """Lists animation presets: built-in ones and the ones saved with anim_preset_save. Animated
        presets bought for Daz are in the content library: content_search(kind="animation")."""
        found = await anyio.to_thread.run_sync(lambda: clips.list_clips(query))
        return {"presets": found, "library": "content_search(kind='animation') finds Daz animation presets "
                                             "in the content library; apply them with anim_preset_apply(path)."}

    @mcp.tool(annotations=CHANGES_SCENE)
    async def anim_preset_save(
        figure: Annotated[str, Field(description="Figure whose animation to save.")],
        name: Annotated[str, Field(description="Preset name, e.g. 'walk-cycle-relaxed'.")],
        start_frame: Annotated[float | None, Field(ge=0, description="Default: the first key.")] = None,
        end_frame: Annotated[float | None, Field(ge=0, description="Default: the last key.")] = None,
        description: str = "",
        loop: Annotated[bool, Field(description="It is a cycle: the last frame matches the first, and repeats "
                                                "carry on walking from where the last cycle ended.")] = False,
        morphs: Annotated[bool, Field(description="Include animated dials (expressions).")] = True,
        with_node: Annotated[bool, Field(description="Include the figure's own position and rotation keys.")] = False,
        overwrite: bool = False,
    ) -> dict:
        """Saves a figure's animation as a reusable preset (~/.daz3d-mcp/animations), to apply later to
        any figure of the same generation with anim_preset_apply."""
        got = await call("anim_keys_get", _clean(node=figure, start_frame=start_frame, end_frame=end_frame,
                                                 morphs=morphs))
        if not with_node:
            (got.get("tracks") or {}).pop("node", None)
        if got.get("truncated"):
            raise ToolError("The animation has too many keys for one preset; save a shorter frame range.")
        start = start_frame if start_frame is not None else (got.get("first_frame") or 0)
        try:
            saved = await anyio.to_thread.run_sync(lambda: clips.save_clip(
                name, got, start=start, end=end_frame, description=description, loop=loop, overwrite=overwrite,
                fps=got.get("fps") or 30))
        except clips.ClipError as exc:
            raise ToolError(str(exc)) from exc
        bones = saved["tracks"].get("bones") or {}
        return {"name": saved["name"], "path": saved["path"], "frames": saved["frames"], "bones": len(bones),
                "morphs": len(saved["tracks"].get("morphs") or {}), "generation": saved.get("generation"),
                "loop": loop}

    @mcp.tool(annotations=CHANGES_SCENE)
    async def anim_preset_apply(
        figure: Annotated[str, Field(description="Figure label.")],
        preset: Annotated[str, Field(description="Preset name from anim_preset_list, or an absolute path of a "
                                                 ".json preset or of a Daz .duf animation from content_search.")],
        start_frame: Annotated[float, Field(ge=0)] = 0,
        speed: Annotated[float, Field(gt=0, description="2 = twice as fast.")] = 1.0,
        repeat: Annotated[int, Field(ge=1, le=100, description="Play it this many times in a row (cycles).")] = 1,
        in_place: Annotated[bool, Field(description="Drop the hip's travel, so a walk stays on the spot.")] = False,
        replace: Annotated[bool, Field(description="Delete the figure's old keys over the frames it "
                                                   "covers.")] = True,
    ) -> dict:
        """Applies an animation preset to a figure from a frame on, at any speed, repeated as a cycle."""
        p = Path(preset).expanduser()
        if p.suffix.lower() in (".duf", ".dsf", ".dsa") and p.is_absolute():
            return await call("anim_preset_load", {"path": p.as_posix(), "figure": figure, "frame": start_frame})
        try:
            clip = await anyio.to_thread.run_sync(lambda: clips.find_clip(preset))
        except clips.ClipError as exc:
            raise ToolError(str(exc)) from exc
        skel = await skeleton(figure)
        try:
            tracks, warnings, last = clips.clip_tracks(clip, start=start_frame, speed=speed, repeat=repeat,
                                                       generation=skel.generation, in_place=in_place,
                                                       root=skel.root())
        except clips.ClipError as exc:
            raise ToolError(str(exc)) from exc
        result = await set_tracks(figure, tracks, [start_frame, last] if replace else None)
        result.update({"preset": clip["name"], "start_frame": start_frame, "last_frame": last, "repeat": repeat,
                       "speed": speed})
        if warnings:
            result["warnings"] = warnings
        return result

    # ------------------------------------------------------- import -----
    @mcp.tool(annotations=READ_ONLY)
    async def anim_file_inspect(
        path: Annotated[str, Field(description="Absolute path of a .bvh or .fbx animation (Mixamo, mocap...).")],
        figure: Annotated[str | None, Field(description="Figure to check the bone map against.")] = None,
        take: Annotated[str | None, Field(description="FBX: animation take.")] = None,
    ) -> dict:
        """Reads a BVH or FBX animation without importing it: frames, frame rate, length, bones, which
        rig it is (Mixamo, CMU mocap, Unreal, 3ds Max Biped, Genesis) and, with figure, which bones map."""
        p = Path(path).expanduser()
        if not p.is_absolute():
            raise ToolError(f"Use an absolute path (got {path!r}).")
        try:
            src = await anyio.to_thread.run_sync(lambda: motion.read_motion(p, take))
            info = motion.describe(src, p)
        except motion.MotionError as exc:
            raise ToolError(str(exc)) from exc
        if figure:
            skel = await skeleton(figure)
            try:
                bmap = motion.build_map(src, skel)
            except motion.MotionError as exc:
                info["bone_map"] = {"error": str(exc)}
                return info
            info["bone_map"] = {"source_rig": bmap.source_rig, "figure_rig": bmap.target_rig,
                                "pairs": {src.names[j]: t for t, j in bmap.pairs.items()},
                                "file_bones_unused": bmap.unmapped_source[:60],
                                "figure_bones_missing": bmap.missing_target}
        return info

    async def calibrate(skel: motion.TargetSkeleton, bmap: motion.BoneMap, figure: str,
                        frame: int) -> tuple[str, float | None, dict]:
        """Finds how this Daz Studio turns bones: keys a test pose (several bones turned on all three
        axes) and compares the joint angles Daz shows with the ones each convention predicts. The test
        keys are on mapped bones at the first imported frame, so the import overwrites them."""
        names = list(skel.bones)
        before = await call("anim_sample", {"figure": figure, "frames": [frame], "dial_bones": names})
        row = before["frames"].get(str(frame)) or before["frames"][str(float(frame))]
        dials = {b: tuple(v["rotation"]) for b, v in (row.get("dials") or {}).items()}
        root = skel.root()
        root_t = tuple((row.get("dials") or {}).get(root, {}).get("position") or (0.0, 0.0, 0.0))
        tilted = [b for b in bmap.pairs if skel.children(b) and motion.rot_angle(skel.bones[b].orient) > 5]
        straight = [b for b in bmap.pairs if skel.children(b) and b not in tilted and b != root]
        probe = (tilted[:3] + straight[:4]) or [b for b in bmap.pairs if b != root][:6]
        test = {}
        for i, b in enumerate(probe):
            test[b] = (23.0 + 3 * i, -31.0 + 2 * i, 37.0 - 4 * i)
        await set_tracks(figure, {"bones": {b: {"rotation": [[frame, *v]]} for b, v in test.items()}},
                         extend_range=False)
        after = await call("anim_sample", {"figure": figure, "frames": [frame], "bones": names})
        measured = (after["frames"].get(str(frame)) or after["frames"][str(float(frame))])["bones"]
        errors: dict[str, float | None] = {}
        for conv in motion.CONVENTIONS:
            pose = dict(dials, **test)
            predicted, _ = skel.fk(pose, root_t, conv)
            errors[conv] = motion.pose_error(skel, predicted, measured)
        scored = [(e, c) for c, e in errors.items() if e is not None]
        if not scored:
            return motion.DEFAULT_CONVENTION, None, errors
        best = min(scored)
        return best[1], best[0], errors

    @mcp.tool(annotations=CHANGES_SCENE)
    async def anim_import(
        path: Annotated[str, Field(description="Absolute path of a .bvh or .fbx animation (Mixamo 'FBX Binary', "
                                               "CMU or other mocap BVH, Daz-exported BVH).")],
        figure: Annotated[str, Field(description="Genesis figure to animate.")],
        start_frame: Annotated[int, Field(ge=0, description="Scene frame where the motion starts.")] = 0,
        take: Annotated[str | None, Field(description="FBX: animation take (default the first).")] = None,
        rig: Annotated[Literal["auto", "mixamo", "cmu", "unreal", "biped", "genesis9", "genesis8"],
                       Field(description="Naming of the file's skeleton; auto detects it.")] = "auto",
        bone_map: Annotated[dict[str, str | None] | None, Field(description="{file bone: figure bone} to add or fix "
                                                                            "pairs; null drops a bone.")] = None,
        source_start: Annotated[float | None, Field(ge=0, description="First frame of the file to use.")] = None,
        source_end: Annotated[float | None, Field(ge=0, description="Last frame of the file to use.")] = None,
        speed: Annotated[float, Field(gt=0, le=10)] = 1.0,
        in_place: Annotated[bool, Field(description="Keep the hips over the same spot (for cycles).")] = False,
        root_motion: Annotated[bool, Field(description="Move the hip up/down and along the path.")] = True,
        match_fps: Annotated[bool, Field(description="Set the scene to the file's frame rate first.")] = False,
        replace: Annotated[bool, Field(description="Delete the figure's old keys over the imported "
                                                   "frames.")] = True,
    ) -> dict:
        """Imports a BVH or FBX motion (Mixamo, mocap) onto a Genesis figure: reads the file, maps its
        bones to the figure's (built-in maps for Mixamo, CMU, Unreal, Biped, Genesis; bone_map to fix),
        adapts the rest pose (T pose vs Genesis A pose) and the body size, and keys every frame. No
        importer dialog. Then check it with anim_preview and anim_foot_contact."""
        p = Path(path).expanduser()
        if not p.is_absolute():
            raise ToolError(f"Use an absolute path (got {path!r}).")
        try:
            src = await anyio.to_thread.run_sync(lambda: motion.read_motion(p, take))
        except motion.MotionError as exc:
            raise ToolError(str(exc)) from exc
        skel = await skeleton(figure)
        try:
            bmap = motion.build_map(src, skel, rig, bone_map)
        except motion.MotionError as exc:
            raise ToolError(str(exc)) from exc
        if match_fps:
            tl = await call("anim_timeline", {"fps": round(src.fps, 3), "keep": "duration", "list_animated": False})
        else:
            tl = await call("anim_timeline", {"list_animated": False})
        fps = float(tl["fps"])
        s0 = (source_start or 0) / src.fps
        s1 = source_end / src.fps if source_end is not None else None
        opts = {"start_frame": start_frame, "source_start": s0, "source_end": s1, "speed": speed,
                "in_place": in_place, "root_motion": root_motion}
        try:
            plan = await anyio.to_thread.run_sync(lambda: motion.retarget(src, skel, bmap, fps, frames_only=[],
                                                                          **opts))
        except motion.MotionError as exc:
            raise ToolError(str(exc)) from exc
        frames_total = plan.frames
        last_frame = start_frame + frames_total - 1

        warnings = list(src.warnings)
        conv = convention_now()
        calibration = None
        if conv is None:
            conv, err, errors = await calibrate(skel, bmap, figure, start_frame)
            calibration = {"convention": conv, "mean_error_deg": round(err, 2) if err is not None else None,
                           "tried": {c: (round(e, 2) if e is not None else None) for c, e in errors.items()}}
            if err is not None and err < CONVENTION_GOOD:
                daz = None
                try:
                    daz = (await call("status")).get("version")
                except ToolError:
                    pass
                save_convention(conv, round(err, 3), daz)
            else:
                warnings.append("Could not confirm how this Daz Studio turns bones (joint angles differ by "
                                f"{calibration['mean_error_deg']} degrees). Look at the result with anim_preview.")

        try:
            res = await anyio.to_thread.run_sync(lambda: motion.retarget(src, skel, bmap, fps, convention=conv,
                                                                         **opts))
        except motion.MotionError as exc:
            raise ToolError(str(exc)) from exc
        tracks: dict = {"bones": {b: {"rotation": rows} for b, rows in res.rotations.items()}}
        if res.root_positions:
            tracks["bones"].setdefault(res.root, {})["position"] = res.root_positions
        result = await set_tracks(figure, tracks, [start_frame, last_frame] if replace else None)

        # Check: do the joint angles Daz shows match the motion?
        check_frames = sorted(res.predicted)
        check = None
        if check_frames:
            data = await call("anim_sample", {"figure": figure, "frames": check_frames,
                                              "bones": sorted(set(bmap.pairs) | {res.root})})
            errs = []
            for f in check_frames:
                row = data["frames"].get(str(f)) or data["frames"].get(str(float(f)))
                e = motion.pose_error(skel, res.predicted[f], row["bones"]) if row else None
                if e is not None:
                    errs.append(e)
            check = round(sum(errs) / len(errs), 2) if errs else None
            if check is not None and check > 10:
                warnings.append(f"Daz shows joint angles {check} degrees away from the motion: check bone_map and "
                                "look at it with anim_preview.")
        if bmap.missing_target:
            warnings.append("These figure bones got no motion: " + ", ".join(bmap.missing_target) +
                            ". Map them with bone_map if the file has them.")
        out = {
            "figure": figure, "file": p.name, "format": src.format, "take": src.take,
            "frames": [start_frame, last_frame], "frame_count": frames_total, "fps": fps, "file_fps": round(src.fps, 3),
            "source_rig": bmap.source_rig, "figure_rig": bmap.target_rig,
            "bones_mapped": len(bmap.pairs), "pairs": {src.names[j]: t for t, j in sorted(bmap.pairs.items())},
            "file_bones_unused": bmap.unmapped_source[:40],
            "body_scale": res.scale, "root_travel_cm": res.root_travel, "turned_to_face_z_deg": res.facing_fix,
            "file_up_axis": res.up_fix, "rest_pose": src.rest_source, "floor": res.floor,
            "keys_set": result.get("keys_set"), "check_joint_angle_error_deg": check,
            "rotation_convention": conv,
            "next": "anim_preview to watch it; anim_foot_contact(fix='lift') if feet go through the floor; "
                    "anim_offset to place it; anim_retime to change its speed.",
        }
        if calibration:
            out["calibration"] = calibration
        if result.get("not_found"):
            out["not_found"] = result["not_found"]
        if warnings:
            out["warnings"] = warnings
        return out
