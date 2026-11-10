"""Stage 3 tools: third-party assets.

Packages from other stores (.zip), extra content libraries, OBJ and FBX
import, and turning imported meshes into clothing that follows a figure.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated, Any, Awaitable, Callable, Literal

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from daz3d_mcp import meshes, packages
from daz3d_mcp.client import DazClient

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
CHANGES_SCENE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)

Vec3 = Annotated[list[float], Field(min_length=3, max_length=3)]
Units = Literal["auto", "cm", "m", "mm", "in", "ft", "poser"]
Call = Callable[..., Awaitable[Any]]


def default_library() -> Path:
    return Path.home() / "Documents" / "DAZ 3D" / "Third Party Library"


def _abs(path: str, what: str = "path") -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise ToolError(f"Use an absolute {what} (got {path!r}).")
    return p


def _clean(**kwargs) -> dict:
    return {k: v for k, v in kwargs.items() if v is not None}


def register(mcp: FastMCP, call: Call, get_client: Callable[[], DazClient], forget_index: Callable[[], None]) -> None:

    def install_library(library: str | None) -> Path:
        if library:
            return _abs(library, "library folder")
        configured = get_client().settings.install_library
        return Path(configured).expanduser() if configured else default_library()

    async def register_library(path: Path, kind: str) -> dict:
        result = await call("content_add_library", {"path": path.as_posix(), "kind": kind})
        forget_index()
        return result

    # ------------------------------------------------------ packages ----
    @mcp.tool(annotations=READ_ONLY)
    async def package_inspect(
        path: Annotated[str, Field(description="Absolute path of a .zip from another store, or of a folder "
                                               "already unpacked.")],
    ) -> dict:
        """Looks inside a content package before installing it: where its Daz content root is (data,
        People, Props, Runtime...), which files can be loaded, loose OBJ/FBX meshes, extras and
        problems. Nothing is written."""
        source = _abs(path)
        max_bytes = int(get_client().settings.max_package_gb * 1e9)

        def run() -> dict:
            with tempfile.TemporaryDirectory(prefix="dazmcp-pkg-") as tmp:
                return packages.summarize(packages.plan_package(source, Path(tmp), max_bytes))

        try:
            return await anyio.to_thread.run_sync(run)
        except packages.PackageError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(annotations=CHANGES_SCENE)
    async def package_install(
        path: Annotated[str, Field(description="Absolute path of the .zip (or unpacked folder).")],
        library: Annotated[str | None, Field(description="Content library folder to install into; default the "
                                                         "third-party library (~/Documents/DAZ 3D/Third Party "
                                                         "Library), which is added to Daz if needed.")] = None,
        overwrite: Annotated[bool, Field(description="Replace files that another package installed with "
                                                     "different contents.")] = False,
        name: Annotated[str | None, Field(description="Name to record the package under (default: the file "
                                                      "name).")] = None,
    ) -> dict:
        """Installs a content package from another store (Renderosity, RuntimeDNA, CGBytes, free sites):
        finds its content root, copies it into a content library, makes sure Daz Studio has that
        library, and returns the new items (paths for content_load) and any loose meshes (paths for
        import_mesh). Records every file so package_uninstall can remove them."""
        source = _abs(path)
        lib = install_library(library)
        settings = get_client().settings
        try:
            result = await anyio.to_thread.run_sync(
                lambda: packages.install(source, lib, overwrite, int(settings.max_package_gb * 1e9), name))
        except packages.PackageError as exc:
            raise ToolError(str(exc)) from exc
        result["daz_library"] = None
        if result["layout"] in ("daz", "poser"):
            try:
                reg = await register_library(lib, "daz")
                if result["layout"] == "poser":
                    await register_library(lib, "poser")
                result["daz_library"] = {"path": reg["path"], "added": reg["added"]}
            except ToolError as exc:
                result["warnings"].append(f"Installed, but Daz Studio did not add the library ({exc}). Run "
                                          f"content_add_library(path={lib.as_posix()!r}) once Daz is open.")
        forget_index()
        if result["layout"] == "meshes":
            result["next"] = "This package has no Daz content, only meshes: use import_mesh on the paths in meshes."
        return result

    @mcp.tool(annotations=READ_ONLY)
    async def package_list() -> dict:
        """Lists the packages installed with package_install."""
        return {"packages": await anyio.to_thread.run_sync(packages.list_packages)}

    @mcp.tool(annotations=DESTRUCTIVE)
    async def package_uninstall(
        package: Annotated[str, Field(description="Package name from package_list.")],
    ) -> dict:
        """Deletes the files a package_install wrote (not files other packages share). Ask the user first;
        scenes that use the package will miss it."""
        try:
            result = await anyio.to_thread.run_sync(lambda: packages.uninstall(package))
        except packages.PackageError as exc:
            raise ToolError(str(exc)) from exc
        forget_index()
        return result

    @mcp.tool(annotations=CHANGES_SCENE)
    async def content_add_library(
        path: Annotated[str, Field(description="Absolute path of a folder that holds Daz content (data, People, "
                                               "Props... inside).")],
        kind: Annotated[Literal["daz", "poser"], Field(description="poser for a folder with a Runtime folder "
                                                                   "(Poser format content).")] = "daz",
    ) -> dict:
        """Adds a folder to Daz Studio's content libraries (it stays after a restart), so its content can
        be searched and loaded and finds its data files."""
        p = _abs(path)
        if not p.is_dir():
            raise ToolError(f"{p} is not a folder.")
        result = await register_library(p, kind)
        return {"path": result["path"], "kind": kind, "added": result["added"],
                "libraries": [lib["path"] for lib in result.get("libraries", [])]}

    # -------------------------------------------------------- meshes ----
    @mcp.tool(annotations=READ_ONLY)
    async def mesh_inspect(
        path: Annotated[str, Field(description="Absolute path of an .obj or .fbx file.")],
    ) -> dict:
        """Reads an OBJ or FBX without importing it: size in file units, the units it most likely uses,
        surfaces, textures found and missing, whether it is rigged or animated."""
        p = _abs(path)
        try:
            info = await anyio.to_thread.run_sync(lambda: meshes.inspect_mesh(p))
            scale, units, why = meshes.import_scale(info, "auto")
        except meshes.MeshError as exc:
            raise ToolError(str(exc)) from exc
        info["suggested_units"] = units
        info["suggested_units_why"] = why
        box = info.get("bbox_raw")
        if box and info["format"] == "obj":
            info["size_cm_with_suggested_units"] = [round(v * scale, 2) for v in box["size"]]
        return info

    @mcp.tool(annotations=CHANGES_SCENE)
    async def import_mesh(
        path: Annotated[str, Field(description="Absolute path of an .obj or .fbx file.")],
        units: Annotated[Units, Field(description="Units the file is in. auto: OBJ is guessed from its size, FBX "
                                                  "uses the units stored in the file.")] = "auto",
        up_axis: Annotated[Literal["Y", "Z"], Field(description="OBJ only: Z for Z-up files that import "
                                                                "lying down.")] = "Y",
        height: Annotated[float | None, Field(gt=0, description="Scale it uniformly to this height in cm "
                                                                "(e.g. 180 for a person).")] = None,
        label: Annotated[str | None, Field(description="Label for the imported node.")] = None,
        position: Annotated[Vec3 | None, Field(description="[x, y, z] cm.")] = None,
        drop_to_floor: Annotated[bool, Field(description="Put its lowest point on the floor. Leave off for "
                                                         "clothing modeled around a figure.")] = False,
        take: Annotated[str | None, Field(description="FBX: animation take to import.")] = None,
        options: Annotated[dict[str, Any] | None, Field(description="Extra importer settings (advanced).")] = None,
    ) -> dict:
        """Imports a loose OBJ or FBX model (Sketchfab, CGTrader, Blender, a package's meshes) into the
        scene with the right size, without the importer dialog. Returns the new node, its size in cm
        and its surfaces. Clothing modeled for a figure then goes through wearable_from_mesh."""
        p = _abs(path)
        info: dict = {}
        try:
            info = await anyio.to_thread.run_sync(lambda: meshes.inspect_mesh(p))
            scale, used, why = meshes.import_scale(info, units)
        except meshes.MeshError as exc:
            if units == "auto" or not p.is_file() or p.suffix.lower() not in (".obj", ".fbx"):
                raise ToolError(str(exc)) from exc
            scale, used, why = meshes.UNITS_CM[units], units, "given"
        fmt = p.suffix.lower().lstrip(".")
        post_scale = None
        if fmt == "fbx" and units != "auto":
            file_unit = ((info.get("units_in_file") or {}).get("cm_per_unit")) or 1.0
            post_scale = meshes.UNITS_CM[units] / file_unit
            scale = None
        result = await call("import_mesh", _clean(
            path=p.as_posix(), format=fmt, scale_cm=scale if fmt == "obj" else None,
            up_axis=up_axis if fmt == "obj" else None, post_scale=post_scale, height=height, label=label,
            position=position, drop_to_floor=drop_to_floor, take=take, options=options))
        result["units"] = used
        result["units_why"] = why
        if info:
            result["file"] = {k: info.get(k) for k in ("vertices", "rigged", "animated", "missing_textures")}
            result["warnings"] = list(info.get("warnings", [])) + list(result.get("warnings", []))
        return result

    @mcp.tool(annotations=CHANGES_SCENE)
    async def wearable_from_mesh(
        item: Annotated[str, Field(description="Label of the imported mesh (or of clothing made for another "
                                               "figure).")],
        figure: Annotated[str, Field(description="Label of the figure it should follow.")],
        kind: Literal["clothing", "hair"] = "clothing",
        shape: Annotated[Literal["base", "current"], Field(description="base: modeled around the figure's default "
                                                                       "shape; current: around its shape now "
                                                                       "(character morphs dialed in).")] = "base",
        morphs: Annotated[bool, Field(description="Copy shape and pose morphs so it follows body changes.")] = True,
        smoothing: Annotated[bool, Field(description="Add mesh smoothing with collision against the "
                                                     "figure.")] = True,
        label: Annotated[str | None, Field(description="Label for the new item.")] = None,
        allow_posed: Annotated[bool, Field(description="Convert even though the figure is posed.")] = False,
    ) -> dict:
        """Makes an imported garment, hat, armor or hair follow a figure (Daz Transfer Utility): copies
        the figure's rigging and morphs onto it and fits it, so it moves with poses and shapes. The mesh
        must already sit on the figure in its default pose. Also re-rigs clothing made for another
        figure generation."""
        return await call("wearable_from_mesh", _clean(item=item, figure=figure, kind=kind, shape=shape,
                                                       morphs=morphs, smoothing=smoothing, label=label,
                                                       allow_posed=allow_posed))

    @mcp.tool(annotations=CHANGES_SCENE)
    async def wearable_adjust(
        item: Annotated[str, Field(description="Clothing or hair label.")],
        smoothing: bool | None = None,
        smoothing_iterations: Annotated[int | None, Field(ge=0, le=100)] = None,
        collision_iterations: Annotated[int | None, Field(ge=0, le=100, description="Raise it (3-10) when skin "
                                                                                    "pokes through.")] = None,
        collide_with: Annotated[str | None, Field(description="Figure to collide with; \"\" for none. Default: "
                                                              "the figure it is fitted to.")] = None,
        properties: Annotated[dict[str, Any] | None, Field(description="{label: value} other properties of the "
                                                                       "item.")] = None,
    ) -> dict:
        """Fixes how clothing sits on a figure: mesh smoothing and collision (cures skin poking through)
        and other item properties. Without arguments it reports the current values. For loose or tight
        fit dials use morph_list/morph_set on the item."""
        return await call("wearable_adjust", _clean(item=item, smoothing=smoothing,
                                                    smoothing_iterations=smoothing_iterations,
                                                    collision_iterations=collision_iterations,
                                                    collide_with=collide_with, properties=properties))
