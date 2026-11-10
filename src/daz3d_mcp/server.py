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

from daz3d_mcp import __version__, asset_tools, scene_tools
from daz3d_mcp.client import DazClient
from daz3d_mcp.paths import config_dir
from daz3d_mcp.skills import get_skill, list_skills
from daz3d_mcp.transport import DazError

INSTRUCTIONS = """\
Tools to control a running Daz Studio (3D characters and scenes).
Start with daz_status, then scene_info to learn what is in the scene, and
viewport_capture to look at it. Units are centimeters and Y is up.
Never discard unsaved work without asking the user.
To build scenes: content_search finds installed figures, clothing, hair, poses
and props; content_load adds them (clothing, hair and poses need a target
figure); figure_info, morph_set and pose_bones adjust characters; camera_create,
light_create and environment_set set up the shot; render makes the final image.
Content from other stores: package_inspect and package_install put a .zip into
a content library; import_mesh brings in loose OBJ/FBX models;
wearable_from_mesh makes an imported garment follow a figure.
If your client has no skills, read the guides with daz_guide first: daz-basics,
then scene-building, characters, rendering and third-party-assets.
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
        return await call("scene_new", {"discard_changes": discard_changes})

    @mcp.tool(annotations=DESTRUCTIVE)
    async def scene_open(
        path: Annotated[str, Field(description="Absolute path to a .duf scene file.")],
        merge: Annotated[bool, Field(description="Add to the current scene instead of replacing it.")] = False,
        discard_changes: Annotated[bool, Field(description="Allow replacing a scene with unsaved changes.")] = False,
    ) -> dict:
        """Opens a Daz scene (.duf), or merges it into the current one."""
        return await call("scene_open", {"path": _daz_path(path), "merge": merge, "discard_changes": discard_changes})

    @mcp.tool(annotations=CHANGES_SCENE)
    async def scene_save(
        path: Annotated[str | None, Field(description="Absolute .duf path. Omit to save over the current file.")] = None,
        overwrite: Annotated[bool, Field(description="Allow replacing another existing file.")] = False,
    ) -> dict:
        """Saves the scene as a .duf file."""
        args: dict = {"overwrite": overwrite}
        if path:
            args["path"] = _daz_path(path)
        return await call("scene_save", args)

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

    forget_index = scene_tools.register(mcp, call, get_client)
    asset_tools.register(mcp, call, get_client, forget_index)

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
