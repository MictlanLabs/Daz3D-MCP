"""The Daz3D-MCP server (stdio)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated, Any

import anyio
from mcp.server.fastmcp import FastMCP, Image
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from daz3d_mcp import (
    __version__,
    anim_tools,
    asset_tools,
    character_tools,
    contact_tools,
    cull_tools,
    look_tools,
    morph_tools,
    scene_tools,
)
from daz3d_mcp.client import DazClient
from daz3d_mcp.paths import config_dir
from daz3d_mcp.skills import get_skill, list_skills
from daz3d_mcp.transport import DazError

INSTRUCTIONS = """\
Tools to control a running Daz Studio (3D characters and scenes).
Start with daz_status, then scene_info to learn what is in the scene, and
viewport_capture to look at it. Units are centimeters and Y is up.
Never discard unsaved work without asking the user.
If a call fails with dialog_open, Daz Studio stopped on a pop-up dialog: read
its text and buttons and answer it with daz_dialog; the call then finishes.
To build scenes: content_search finds installed figures, clothing, hair, poses
and props; content_load adds them (clothing, hair and poses need a target
figure); figure_info, morph_set and pose_bones adjust characters; prop_surfaces,
place_on and fit_check put a posed figure on a chair, sofa or bed without
floating or passing through it; face_expression, eyes_look_at and eye_color
set expressions, where the eyes look and iris color; camera_create,
light_create and environment_set set up the shot; render makes the final image.
Characters to reuse: character_create turns a description into a character
(body, every face detail, skin, eyes, hair, clothes) saved as an editable sheet;
character_load puts it in any scene, character_update changes only what is
asked, character_list lists them and the traits; morph_generate makes dials for
traits with no installed morph (nose, jaw, ears, age, weight, bust... on Genesis 9
and 8 / 8.1); morph_export / morph_import bring shapes sculpted in Blender.
Dialogue scenes (visual novels): camera_shot frames a close-up, over the shoulder
or two shot on a face, on one side of the line between the two speakers;
render_shots renders a whole conversation, one image per line.
Clothes from another Genesis generation: answer each Auto-Fit dialog with Accept
(an outfit asks once per piece), then wearable_refit(figure, fix=true) rebuilds
pieces left unconverted and repairs shoes that ended up misplaced.
Lighter renders: render_cull leaves out of the render what a camera cannot see
(out of the picture, behind it, under other clothing); render, render_shots and
render_animation do it per shot with cull=true.
Realistic, not plastic: surface_realism fixes shiny skin (two specular layers)
and gives imported props real materials; light_rig places a photographic key,
rim and fill from the camera (low_key on black, soft_studio, window, neon);
render_postwork (or render(postwork=...)) gives the image a film finish: tone
curve, split toning, local contrast, sharpening, grain and vignette.
Content from other stores: package_inspect and package_install put a .zip into
a content library; import_mesh brings in loose OBJ/FBX models;
wearable_from_mesh makes an imported garment follow a figure.
Animation: anim_keys_set keys poses at frames (anim_timeline sets the frame
rate and range); anim_preset_apply plays saved or built-in motions;
anim_import brings Mixamo FBX or mocap BVH onto a Genesis figure; anim_retime
and anim_offset change speed, timing and place; anim_foot_contact and
anim_preview check the result. contact_bake makes a figure's hand pressing a
breast dent the flesh frame by frame, with inertia.
If your client has no skills, read the guides with daz_guide first: daz-basics,
then scene-building, characters, character-design, faces, furniture-poses,
dialogue-scenes, rendering, realistic-renders, render-culling, cross-generation-clothing,
third-party-assets and animation.
run_script runs free DazScript (ES5 JavaScript) for anything the named tools
do not cover; prefer the named tools when they exist.
"""

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
CHANGES_SCENE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)


def _daz_path(path: str) -> str:
    """Absolute path with forward slashes, which DazScript expects on every OS."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise ToolError(f"Use an absolute path (got {path!r}).")
    return p.as_posix()


def create_server(client: DazClient | None = None) -> FastMCP:
    mcp = FastMCP("daz3d", instructions=INSTRUCTIONS)
    state: dict[str, Any] = {"client": client}

    def get_client() -> DazClient:
        if state["client"] is None:
            state["client"] = DazClient()
        return state["client"]

    async def call(tool: str, args: dict | None = None, timeout: float | None = None) -> Any:
        try:
            return await anyio.to_thread.run_sync(lambda: get_client().run_tool(tool, args or {}, timeout))
        except DazError as exc:
            raise ToolError(str(exc)) from exc

    culler = cull_tools.register(mcp, call)

    # ------------------------------------------------------------ session --
    @mcp.tool(annotations=READ_ONLY)
    async def daz_status() -> dict:
        """Checks that Daz Studio is reachable and reports its version and the open scene."""
        try:
            bridge = await anyio.to_thread.run_sync(lambda: get_client().bridge_status())
        except DazError as exc:
            raise ToolError(str(exc)) from exc
        info = await call("status")
        return {"mcp_version": __version__, "bridge": bridge, "daz": info}

    def _look_for_more(out: dict, settle: float = 4.0, longest: float = 120.0) -> None:
        """Daz can open the next dialog only after the call it stopped has finished: loading an
        outfit from another generation asks Auto-Fit once per item, and the items whose dialog
        nobody answers stay unconverted (still in the other generation's shape and bones)."""
        client = get_client()
        start = last_busy = time.monotonic()
        while True:
            try:
                listing = client.dialogs()
            except DazError:
                return
            open_ = [d for d in listing.get("dialogs", []) if not d.get("progress")]
            if open_:
                out["more_dialogs"] = open_
                out["hint"] = ("Daz opened another dialog after this one" +
                               (" (Auto-Fit asks once for each item of an outfit)" if any(
                                   "Auto-Fit" in str(d.get("title")) for d in open_) else "") +
                               ": answer it with daz_dialog too, or that item stays as it is.")
                return
            now = time.monotonic()
            if any(d.get("progress") for d in listing.get("dialogs", [])):
                last_busy = now   # a conversion is running: the next dialog may follow it
            if now - last_busy > settle or now - start > longest:
                return
            time.sleep(0.5)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def daz_dialog(
        button: Annotated[str | None, Field(description="Button to press, as listed (e.g. \"Yes\", \"Replace\"); "
                                                        "\"escape\" cancels. Omit to only look.")] = None,
        check: Annotated[list[str] | None, Field(description="Check boxes or radio buttons to turn on "
                                                             "before pressing.")] = None,
        uncheck: Annotated[list[str] | None, Field(description="Check boxes to turn off before pressing.")] = None,
        dialog_id: Annotated[str | None, Field(description="Which dialog, when several are open (id from "
                                                           "the list).")] = None,
        wait: Annotated[float, Field(ge=0, le=7200, description="Seconds to wait for the stopped call to "
                                                                "finish after answering.")] = 600,
    ) -> dict:
        """Sees and answers the pop-up dialogs Daz Studio opens (overwrite?, replace or add?, limits...).
        A tool that stops on one fails with dialog_open and lists its text and buttons; press one here
        and the stopped call's result comes back as call_result. Without button: lists open dialogs
        and, if a call was left waiting, waits for it. Ask the user before an answer that would
        overwrite or discard their work. Needs the bridge plugin 0.2+."""
        client = get_client()

        def work() -> dict:
            if button or check or uncheck:
                out = client.answer_dialog(button, dialog_id, check, uncheck, wait)
                if "call_result" in out:
                    _look_for_more(out)
                return out
            listing = client.dialogs()
            if listing.get("waiting_call") and not [d for d in listing["dialogs"] if not d.get("progress")]:
                done = client.wait_pending(wait)
                if done is not None:
                    listing.update(done)
                    listing["waiting_call"] = False
            return listing

        try:
            return await anyio.to_thread.run_sync(work)
        except DazError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(annotations=READ_ONLY)
    async def scene_info(
        include_bones: Annotated[bool, Field(description="Also list figure bones (long).")] = False,
        include_hidden: Annotated[bool, Field(description="Include nodes hidden in the viewport.")] = True,
        max_nodes: Annotated[int, Field(ge=1, le=2000, description="Maximum nodes to list.")] = 200,
    ) -> dict:
        """Describes the open scene: file, frames, and every figure, prop, camera and light with
        its parent, world position (cm), rotation (degrees), scale and bounding box."""
        return await call(
            "scene_info",
            {"include_bones": include_bones, "include_hidden": include_hidden, "max_nodes": max_nodes},
        )

    @mcp.tool(annotations=DESTRUCTIVE)
    async def scene_new(
        discard_changes: Annotated[bool, Field(description="Allow clearing a scene with unsaved changes.")] = False,
    ) -> dict:
        """Clears the scene. Fails on unsaved changes unless discard_changes is true; ask the user first."""
        result = await call("scene_new", {"discard_changes": discard_changes})
        culler.forget()
        return result

    @mcp.tool(annotations=DESTRUCTIVE)
    async def scene_open(
        path: Annotated[str, Field(description="Absolute path to a .duf scene file.")],
        merge: Annotated[bool, Field(description="Add to the current scene instead of replacing it.")] = False,
        discard_changes: Annotated[bool, Field(description="Allow replacing a scene with unsaved changes.")] = False,
    ) -> dict:
        """Opens a Daz scene (.duf), or merges it into the current one."""
        result = await call("scene_open", {"path": _daz_path(path), "merge": merge,
                                           "discard_changes": discard_changes})
        if not merge:
            culler.forget()
        return result

    @mcp.tool(annotations=CHANGES_SCENE)
    async def scene_save(
        path: Annotated[str | None, Field(description="Absolute .duf path. Omit to save over the current file.")] = None,
        overwrite: Annotated[bool, Field(description="Allow replacing another existing file.")] = False,
    ) -> dict:
        """Saves the scene as a .duf file. Nodes render_cull took out of the render are put back
        for the save, so the file never keeps them switched off."""
        args: dict = {"overwrite": overwrite}
        if path:
            args["path"] = _daz_path(path)
        record = culler.active()
        if not record:
            return await call("scene_save", args)
        await culler.restore()
        try:
            result = await call("scene_save", args)
        finally:
            await culler.reapply(record)
        result["render_cull"] = (f"{len(record['nodes'])} nodes hidden from the render by render_cull were "
                                 "saved visible, and are hidden again now.")
        return result

    # ---------------------------------------------------------- see it ----
    @mcp.tool(annotations=READ_ONLY, structured_output=False)
    async def viewport_capture(
        max_size: Annotated[int, Field(ge=64, le=4096, description="Longest side in pixels.")] = 1024,
        camera: Annotated[str | None, Field(description="Camera label to look through; default is the viewport's.")] = None,
        frame: Annotated[int | None, Field(ge=0, description="Timeline frame to show.")] = None,
    ) -> list:
        """Returns an image of the active 3D viewport so you can see the scene."""
        captures = config_dir() / "captures"
        captures.mkdir(parents=True, exist_ok=True)
        out = captures / f"viewport-{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}.png"
        args: dict = {"out_path": out.as_posix(), "max_size": max_size}
        if camera:
            args["camera"] = camera
        if frame is not None:
            args["frame"] = frame
        result = await call("viewport_capture", args)
        path = Path(result.get("path") or out)
        if not path.is_file():
            raise ToolError(f"Daz Studio reported a capture but {path} does not exist.")
        data = path.read_bytes()
        _prune_captures(captures, get_client().settings.keep_captures)
        return [Image(data=data, format="png"), json.dumps(result)]

    # --------------------------------------------------------- escape -----
    @mcp.tool(annotations=DESTRUCTIVE)
    async def run_script(
        code: Annotated[str, Field(description="DazScript (ES5 JavaScript) run as a function body; `return` a JSON value.")],
        args: Annotated[dict | None, Field(description="Object available to the code as `args`.")] = None,
    ) -> dict:
        """Runs DazScript inside Daz Studio for anything the named tools do not cover.
        Globals: Scene, App, MainWindow, DazMcp (helpers such as DazMcp.findNode, DazMcp.log).
        Use DazMcp.log(msg) for messages and `return` the result."""
        client = get_client()
        if not client.settings.allow_run_script:
            raise ToolError("run_script is disabled in ~/.daz3d-mcp/settings.json (allow_run_script).")
        try:
            result, log = await anyio.to_thread.run_sync(lambda: client.run_code(code, args or {}))
        except DazError as exc:
            raise ToolError(str(exc)) from exc
        return {"result": result, "log": log}

    # ---------------------------------------------------------- guides ----
    @mcp.tool(annotations=READ_ONLY)
    def daz_guide(
        topic: Annotated[str | None, Field(description="Guide name, e.g. daz-basics. Omit to list guides.")] = None,
    ) -> str:
        """Returns a usage guide (the same text as the Daz3D-MCP skills) for clients without skills support."""
        if not topic:
            lines = [f"- {s.name}: {s.description}" for s in list_skills()]
            return "Available guides:\n" + "\n".join(lines)
        skill = get_skill(topic)
        if skill is None:
            raise ToolError(f"No guide named {topic!r}. Call daz_guide without a topic to list them.")
        return skill.body

    content = scene_tools.register(mcp, call, get_client, culler)
    asset_tools.register(mcp, call, get_client, content.forget)
    anim_tools.register(mcp, call, get_client)
    morphs = morph_tools.register(mcp, call)
    contact_tools.register(mcp, call, morphs)
    character_tools.register(mcp, call, get_client, content, morphs)
    look_tools.register(mcp, call, get_client)

    for skill in list_skills():
        _register_skill(mcp, skill.name, skill.description)

    return mcp


def _register_skill(mcp: FastMCP, name: str, description: str) -> None:
    def prompt() -> str:
        skill = get_skill(name)
        return skill.body if skill else ""

    def resource() -> str:
        skill = get_skill(name)
        return skill.text if skill else ""

    mcp.prompt(name=name, description=description)(prompt)
    mcp.resource(f"daz3d://skills/{name}", name=name, description=description, mime_type="text/markdown")(resource)


def _prune_captures(folder: Path, keep: int) -> None:
    files = sorted(folder.glob("viewport-*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[max(keep, 1):]:
        try:
            old.unlink()
        except OSError:
            pass


def run() -> None:
    create_server().run("stdio")
