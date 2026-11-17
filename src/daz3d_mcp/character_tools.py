"""Character sheets: create a character from a description, save it, load it into any scene and
change it later."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from daz3d_mcp import characters as ch
from daz3d_mcp.client import DazClient
from daz3d_mcp.morph_tools import Generator
from daz3d_mcp.scene_tools import ContentAccess

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
CHANGES_SCENE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)

Call = Callable[..., Awaitable[Any]]
Vec3 = Annotated[list[float], Field(min_length=3, max_length=3)]
Color = Annotated[list[float] | str, Field(description="[r, g, b] from 0 to 1, or \"#rrggbb\".")]
Generation = Literal["Genesis 9", "Genesis 8.1 Female", "Genesis 8.1 Male", "Genesis 8 Female", "Genesis 8 Male"]
Step = Literal["character", "preset", "presets", "anatomy", "shape", "eyes", "skin", "colors", "hair", "clothing",
               "extras", "follow", "materials", "height", "position"]
STEPS: list[str] = ["character", "preset", "presets", "anatomy", "shape", "eyes", "skin", "colors", "hair", "clothing",
                    "extras", "follow", "materials", "height", "position"]
FOLLOW_AFTER = {"shape", "anatomy", "hair", "clothing", "extras"}
ANATOMY_QUERIES = ("anatomical elements", "genitalia", "geograft", "gens")
ANATOMY_SKIP = re.compile(r"material|\bmat\b|shader|texture|\bpose|hide|remove|\bfix", re.IGNORECASE)


def sex_of(sheet: dict, generation: str | None) -> str | None:
    gen = str(generation or "")
    body = sheet.get("body") or {}
    if "Female" in gen or (body.get("feminine") or 0) > (body.get("masculine") or 0):
        return "feminine"
    if "Male" in gen or (body.get("masculine") or 0) > 0:
        return "masculine"
    return None


def pick_anatomy(found: list[dict], sex: str | None) -> list[dict]:
    seen: set[str] = set()
    out = []
    for item in found:
        path = str(item.get("path") or "")
        if path in seen or ANATOMY_SKIP.search(Path(path).stem):
            continue
        seen.add(path)
        text = path.lower()
        fem = bool(re.search(r"femin|female|\bf\b|g9f|g8f", text))
        mas = bool(re.search(r"mascul|\bmale\b|\bm\b|g9m|g8m", text))
        score = 0 if sex is None else (2 if (sex == "feminine" and fem) or (sex == "masculine" and mas) else
                                        (0 if fem or mas else 1))
        out.append({**item, "score": score})
    out.sort(key=lambda x: -x["score"])
    return out
ROOT_PROPS = ("Hair Root Color", "Root Transmission Color", "Base Color")
TIP_PROPS = ("Hair Tip Color", "Tip Transmission Color")

TRAITS_HELP = ("{trait: value from -1 to 1}; 0 is the base figure, 0.3 a clear change, 1 the strongest. "
               + ch.traits_help() + " character_list(include_traits=true) says what each end means.")
DIALS_HELP = ("Exact installed dials {label or name: value} for anything traits do not cover, e.g. "
              "{\"Laura Head\": 0.4}. Prefix \"mouth:\" or \"eyes:\" for dials of the Genesis 9 Mouth or Eyes "
              "figures, e.g. {\"mouth:Teeth Size Lower\": 0.3}. A value is added to what traits set on the "
              "same dial.")


class SkinSpec(BaseModel):
    preset: Annotated[str | None, Field(description="Skin material preset (content_search kind=material).")] = None
    tone: Annotated[Color | None, Field(description="Tint over the skin images; it multiplies them, so stay "
                                                    "near white (#e8d0c0) except for fantasy skin.")] = None
    details: Annotated[str | None, Field(description="Freckles, moles, scars, tattoos, makeup... in words; kept "
                                                     "in the sheet. Apply them with presets.")] = None


class EyeSide(BaseModel):
    color: Annotated[Color | None, Field(description="Iris color of this eye.")] = None
    iris: Annotated[int | None, Field(ge=1, le=16, description="Genesis 9 iris image 1-16.")] = None


class EyesSpec(BaseModel):
    color: Annotated[Color | None, Field(description="Iris color.")] = None
    iris: Annotated[int | None, Field(ge=1, le=16, description="Genesis 9 iris image 1-16 (see eye_color).")] = None
    preset: Annotated[str | None, Field(description="Eye material preset.")] = None
    left: Annotated[EyeSide | None, Field(description="Genesis 9: the left eye's own iris (heterochromia).")] = None
    right: Annotated[EyeSide | None, Field(description="Genesis 9: the right eye's own iris.")] = None
    sclera: Annotated[Color | None, Field(description="Color of the whites (red, black, yellow...); it "
                                                      "multiplies them.")] = None


class HairSpec(BaseModel):
    items: Annotated[list[str] | None, Field(description="Content files (hair, eyebrows, beard...).")] = None
    color: Annotated[Color | None, Field(description="Color (root, and tip when tip_color is not given).")] = None
    tip_color: Annotated[Color | None, Field(description="Tip color, for ombre, dyed ends or grey "
                                                         "tips.")] = None


class ColorsSpec(BaseModel):
    teeth: Annotated[Color | None, Field(description="Teeth color; multiplies them (#e8dcb0 yellowed).")] = None
    gums: Annotated[Color | None, Field(description="Gums and mouth color.")] = None
    nails: Annotated[Color | None, Field(description="Finger and toe nail color (polish).")] = None
    lips: Annotated[Color | None, Field(description="Lip color where the figure has a Lips surface "
                                                    "(Genesis 8 / 8.1); on Genesis 9 use a makeup preset.")] = None


class MaterialEdit(BaseModel):
    on: Annotated[str, Field(description="\"figure\", \"mouth\", \"eyes\", a content file of the sheet (hair, "
                                         "clothing, extras) or a scene label.")]
    surfaces: Annotated[list[str] | None, Field(description="Surfaces; omit for all.")] = None
    properties: Annotated[dict[str, Any], Field(description="{property label: value} as for material_set.")]


def _check_traits(traits: dict[str, float | None]) -> None:
    unknown = ch.unknown_traits(list(traits))
    if unknown:
        raise ToolError(f"Unknown traits: {unknown}. character_list(include_traits=true) lists them; put "
                        "other installed dials in `dials`.")
    bad = [f"{k}={v} (range {ch.TRAITS[k].low:g} to 1)" for k, v in traits.items()
           if v is not None and not ch.TRAITS[k].low <= v <= 1]
    if bad:
        raise ToolError("Trait values out of range: " + ", ".join(bad))


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    return [str(v) for v in value] if isinstance(value, list) else [str(value)]


def _color(value: Any) -> Any:
    if isinstance(value, str) and not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ToolError(f"Colors are \"#rrggbb\" or [r, g, b] (got {value!r}).")
    if isinstance(value, dict):
        return {k: _color(v) if k == "color" else v for k, v in value.items()}
    return value


def register(mcp: FastMCP, call: Call, get_client: Callable[[], DazClient], content: ContentAccess,
             morphs: Generator | None = None) -> None:

    async def find_anatomy(generation: str | None, sex: str | None) -> list[dict]:
        gen = str(generation or "")
        family = "Genesis 9" if gen.startswith("Genesis 9") else gen.replace(" Female", "").replace(" Male", "")
        found: list[dict] = []
        for query in ANATOMY_QUERIES:
            for item in await content.search(query, None, None):
                g = str(item.get("generation") or "")
                if not g or g.startswith(family) or family.startswith(g):
                    found.append(item)
        return pick_anatomy(found, sex)

    def folder() -> Path:
        return ch.characters_dir(get_client().settings.characters_dir)

    def locate(name: str) -> Path:
        path = ch.sheet_path(folder(), name)
        if path.is_file():
            return path
        for entry in ch.list_sheets(folder()):
            if entry["name"].lower() == name.lower():
                return Path(entry["sheet"])
        raise ToolError(f"No character named {name!r} in {folder().as_posix()}. character_list shows them.")

    def load_sheet(path: Path) -> dict:
        try:
            return ch.read_sheet(path)
        except (OSError, ValueError) as exc:
            raise ToolError(str(exc)) from exc

    async def rel(path: str | None) -> str | None:
        return await content.relative(path) if path else None

    async def labels_in_scene() -> set[str]:
        info = await call("scene_info", {"include_hidden": True, "max_nodes": 2000})
        return {str(n.get("label")) for n in info.get("nodes", [])}

    async def free_label(wanted: str) -> str:
        taken = await labels_in_scene()
        if wanted not in taken:
            return wanted
        n = 2
        while f"{wanted} ({n})" in taken:
            n += 1
        return f"{wanted} ({n})"

    async def add_figure(sheet: dict, label: str) -> str:
        fig = sheet["figure"]
        base = fig.get("base") or ch.BASE_FIGURES.get(fig.get("generation") or "Genesis 9")
        loaded = await content.load(base, None)
        figures = [a for a in loaded.get("added", []) if a.get("type") == "figure"]
        if not figures:
            raise ToolError(f"{base} did not add a figure to the scene.")
        wanted = await free_label(label)
        renamed = await call("node_set", {"node": figures[0]["label"], "label": wanted})
        return str(renamed.get("label") or wanted)

    async def inventory(label: str, roles: dict) -> ch.Inventory:
        listings: dict = {}
        for role, node in roles.items():
            res = await call("morph_list", {"node": node, "limit": 100000})
            listings[role] = (node, res.get("morphs") or [])
        return ch.inventory_from(listings)

    async def apply(sheet: dict, label: str, steps: list[str], preset: Path | None = None,
                    position: list[float] | None = None, previous: dict | None = None) -> dict:
        info = await call("figure_info", {"figure": label})
        generation = info.get("generation")
        g9 = str(generation or "").startswith("Genesis 9")
        roles: dict = {"figure": label, **ch.follower_roles(info.get("wearing") or [])}
        surfaces = list(info.get("surfaces") or [])
        report: dict[str, Any] = {"figure": label, "generation": generation, "done": [], "errors": []}
        applied: dict[str, Any] = {"generation": generation, "figure": label,
                                   "worn": dict((sheet.get("applied") or {}).get("worn") or {})}
        resolution = ch.Resolution()
        unknown = ch.unknown_in_sheet(sheet)
        if unknown:
            report["unknown_traits"] = unknown

        def note(text: str) -> None:
            report.setdefault("notes", []).append(text)

        async def load_on(path: str) -> dict:
            return await content.load(path, label)

        async def step_character() -> None:
            if sheet["figure"].get("character"):
                await load_on(sheet["figure"]["character"])

        async def step_preset() -> None:
            if preset is not None:
                await call("content_load", {"path": preset.as_posix(), "kind": "character", "target": label})

        async def step_anatomy() -> None:
            paths = list(sheet.get("anatomy") or [])
            if "auto" in paths:
                paths.remove("auto")
                found = await find_anatomy(generation, sex_of(sheet, generation))
                if found and found[0]["score"] > 0:
                    paths.insert(0, found[0]["path"])
                    report["anatomy"] = applied["anatomy_auto"] = found[0]["path"]
                else:
                    note(f"No anatomy geograft for {generation} is installed (Genesis 9 Anatomical Elements, or "
                         "a Genesis 8 / 8.1 one). Install one, then load the character again.")
            await wear(paths)

        async def step_presets() -> None:
            for path in [sheet["skin"].get("preset"), sheet["eyes"].get("preset"), *(sheet.get("presets") or [])]:
                if path:
                    await load_on(path)

        async def step_shape() -> None:
            nonlocal resolution
            inv = await inventory(label, roles)
            resolution = ch.resolve(ch.traits_of(sheet), inv, generation)
            values = {node: dict(d) for node, d in resolution.values.items()}
            for key, value in (sheet.get("dials") or {}).items():
                role, dial = ch.split_dial(key)
                node = roles.get(role)
                if node is None:
                    note(f"Dial {key!r}: this figure has no {role} part.")
                    continue
                mine = values.setdefault(node, {})
                mine[dial] = round(mine.get(dial, 0.0) + value, 4)
            if previous:
                for node, zeros in ch.zeroed(previous, values).items():
                    values.setdefault(node, {}).update(zeros)
            not_found: list = []
            for node, dials in values.items():
                if dials:
                    out = await call("morph_set", {"node": node, "values": dials})
                    not_found += out.get("not_found") or []
            applied["dials"] = {n: {k: v for k, v in d.items() if v} for n, d in values.items()}
            applied["traits"] = resolution.traits
            applied["missing"] = resolution.missing
            report["traits"] = resolution.traits
            if resolution.missing:
                report["missing"] = resolution.missing
                report["missing_hint"] = ch.MISSING_HINT
            if not_found:
                applied["dials_not_found"] = not_found
                report["dials_not_found"] = not_found

        async def step_eyes() -> None:
            eyes = sheet["eyes"]
            sides = [("both", eyes)] + [(side, eyes.get(side)) for side in ("left", "right") if eyes.get(side)]
            for which, spec in sides:
                args: dict = {"figure": label}
                if which != "both":
                    if not g9:
                        note("One iris per eye works on Genesis 9 only; Genesis 8 has one Irises surface.")
                        continue
                    args["eyes"] = which
                if spec.get("color"):
                    args["color"] = spec["color"]
                if spec.get("iris") and g9:
                    args["iris"] = spec["iris"]
                elif spec.get("iris"):
                    note("Iris images are for Genesis 9; only the color was used.")
                if len(args) > (1 if which == "both" else 2):
                    await call("eye_color", args)
            if eyes.get("sclera"):
                await call("eye_color", {"figure": label, "sclera": eyes["sclera"], "keep_iris": True})

        async def step_skin() -> None:
            tone = sheet["skin"].get("tone")
            if tone:
                await call("material_set", {"node": label, "surfaces": ch.skin_surfaces(surfaces),
                                            "properties": {"Base Color": tone}})

        async def step_colors() -> None:
            colors = sheet.get("colors") or {}
            mouth = roles.get("mouth", label)
            plan = [("teeth", mouth, ["Teeth"]), ("gums", mouth, ["Gums", "Mouth"]),
                    ("nails", label, ["Fingernails", "Toenails"]), ("lips", label, ["Lips"])]
            for key, node, wanted in plan:
                color = colors.get(key)
                if not color:
                    continue
                if key == "lips" and "Lips" not in surfaces:
                    note("This figure has no Lips surface (Genesis 9): lip color needs a makeup or lipstick "
                         "preset in presets.")
                    continue
                await call("material_set", {"node": node, "surfaces": wanted, "properties": {"Base Color": color}})

        async def wear(paths: list[str]) -> list[str]:
            worn = applied["worn"]
            current = set(await labels_in_scene())
            labels = []
            for path in paths:
                present = [w for w in _as_list(worn.get(path)) if w in current]
                if present:
                    labels += present
                    continue
                out = await load_on(path)
                added = [a["label"] for a in out.get("added", []) if a.get("fitted_to") or a.get("type") != "figure"]
                if added:
                    worn[path] = added
                    labels += added
            return labels

        async def color_hair(items: list[str], spec: dict) -> None:
            root, tip = spec.get("color"), spec.get("tip_color") or spec.get("color")
            if not root and not tip:
                return
            props: dict = {}
            if root:
                props.update({p: root for p in ROOT_PROPS})
            if tip:
                props.update({p: tip for p in TIP_PROPS})
            for item in items:
                res = await call("material_set", {"node": item, "properties": props})
                report.setdefault("hair_color", []).append({"item": item,
                                                           "surfaces": len(res.get("changed") or [])})

        async def step_hair() -> None:
            for key in ("hair", "brows", "facial_hair"):
                spec = sheet.get(key) or {}
                labels = await wear(spec.get("items") or [])
                await color_hair(labels, spec)

        async def step_clothing() -> None:
            await wear(sheet.get("clothing") or [])

        async def step_extras() -> None:
            await wear(sheet.get("extras") or [])

        async def step_follow() -> None:
            if morphs is None or not FOLLOW_AFTER & set(steps):
                return
            recipes = await morphs.in_use(label)
            if recipes:
                done = await morphs.follow(label, recipes)
                if done:
                    report["followers"] = sorted({d["item"] for d in done})

        async def step_materials() -> None:
            current = await labels_in_scene()
            for edit in sheet.get("materials") or []:
                on = str(edit.get("on") or "figure")
                nodes = [roles[on]] if on in roles else _as_list(applied["worn"].get(on))
                if not nodes and on in current:
                    nodes = [on]
                if not nodes:
                    note(f"materials: nothing in the scene for {on!r}.")
                    continue
                for node in nodes:
                    args: dict = {"node": node, "properties": edit.get("properties") or {}}
                    if edit.get("surfaces"):
                        args["surfaces"] = edit["surfaces"]
                    await call("material_set", args)

        async def step_height() -> None:
            target = sheet.get("height_cm")
            now = await call("figure_info", {"figure": label})
            scale = float((now.get("transform") or {}).get("scale") or 1)
            if target:
                natural = float(now["height_cm"]) / scale
                new = target / natural
            else:
                new = resolution.scale_factor if "shape" in steps else float((sheet.get("applied") or {})
                                                                             .get("scale") or 1)
            if abs(new - scale) > 1e-4:
                await call("node_set", {"node": label, "scale": round(new, 4)})
            applied["scale"] = round(new, 4)
            measured = await call("figure_info", {"figure": label})
            report["height_cm"] = measured.get("height_cm")

        async def step_position() -> None:
            if position is not None:
                await call("node_set", {"node": label, "position": position})

        actions = {"character": step_character, "preset": step_preset, "presets": step_presets,
                   "shape": step_shape, "eyes": step_eyes, "skin": step_skin, "colors": step_colors,
                   "hair": step_hair, "clothing": step_clothing, "extras": step_extras, "follow": step_follow,
                   "anatomy": step_anatomy,
                   "materials": step_materials, "height": step_height, "position": step_position}
        order = [s for s in STEPS if s in steps]
        for i, step in enumerate(order):
            try:
                await actions[step]()
                report["done"].append(step)
            except ToolError as exc:
                text = str(exc)
                report["errors"].append({"step": step, "error": text})
                if "[dialog_open]" in text:
                    report["stopped"] = True
                    report["remaining_steps"] = order[i + 1:]
                    report["hint"] = ("Daz is showing a dialog: answer it with daz_dialog, then call "
                                      f"character_load(name, figure=\"{label}\", steps={order[i + 1:]}) to finish.")
                    break
        report["applied"] = applied
        return report

    async def save_preset(sheet: dict, path: Path, label: str) -> str | None:
        duf = path.with_suffix(".duf")
        out = await call("character_preset_save", {"figure": label, "path": duf.as_posix(), "overwrite": True})
        sheet["preset_file"] = Path(out["saved"]).name
        sheet["preset_of"] = ch.content_hash(sheet)
        return out["saved"]

    async def fill_hair(sheet: dict, key: str, spec: HairSpec) -> None:
        data = spec.model_dump(exclude_unset=True)
        if "items" in data:
            sheet[key]["items"] = [await rel(p) for p in data["items"] or []]
        for field in ("color", "tip_color"):
            if field in data:
                sheet[key][field] = _color(data[field])

    async def fill(sheet: dict, **given: Any) -> set[str]:
        changed: set[str] = set()
        for key in ("description", "notes"):
            if given.get(key) is not None:
                sheet[key] = given[key]
        traits = given.get("traits")
        if traits:
            _check_traits(traits)
            ch.set_traits(sheet, traits)
            changed |= {"shape", "height"}
        dials = given.get("dials")
        if dials:
            for key, value in dials.items():
                if value is None:
                    sheet["dials"].pop(key, None)
                else:
                    sheet["dials"][key] = value
            changed.add("shape")
        if given.get("height_cm") is not None:
            sheet["height_cm"] = given["height_cm"] or None
            changed.add("height")
        skin: SkinSpec | None = given.get("skin")
        if skin is not None:
            for key, value in skin.model_dump(exclude_unset=True).items():
                sheet["skin"][key] = await rel(value) if key == "preset" else _color(value) if key == "tone" else value
            changed |= {"presets", "skin"}
        eyes: EyesSpec | None = given.get("eyes")
        if eyes is not None:
            for key, value in eyes.model_dump(exclude_unset=True).items():
                sheet["eyes"][key] = await rel(value) if key == "preset" else _color(value)
            changed |= {"presets", "eyes"}
        for key in ("hair", "brows", "facial_hair"):
            if given.get(key) is not None:
                await fill_hair(sheet, key, given[key])
                changed.add("hair")
        colors: ColorsSpec | None = given.get("colors")
        if colors is not None:
            for key, value in colors.model_dump(exclude_unset=True).items():
                sheet["colors"][key] = _color(value)
            changed.add("colors")
        for key, step in (("clothing", "clothing"), ("extras", "extras"), ("presets", "presets"),
                          ("anatomy", "anatomy")):
            if given.get(key) is not None:
                sheet[key] = [p if p == "auto" else await rel(p) for p in given[key]]
                changed.add(step)
        materials: list[MaterialEdit] | None = given.get("materials")
        if materials is not None:
            sheet["materials"] = [m.model_dump(exclude_none=True) for m in materials]
            changed.add("materials")
        return changed

    def summary(sheet: dict, path: Path, report: dict | None, preset: str | None) -> dict:
        out: dict[str, Any] = {"name": sheet["name"], "sheet": path.as_posix()}
        if preset:
            out["preset"] = preset
        if report:
            rep = dict(report)
            rep.pop("applied", None)
            out.update(rep)
        return out

    @mcp.tool(annotations=CHANGES_SCENE)
    async def character_create(
        name: Annotated[str, Field(min_length=1, max_length=64, description="Character name; also the figure's "
                                                                            "label and the file name.")],
        description: Annotated[str | None, Field(description="The user's own description, kept in the sheet.")] = None,
        notes: Annotated[str | None, Field(description="Anything else to remember: personality, role, voice, "
                                                       "assumptions made...")] = None,
        generation: Annotated[Generation | None, Field(description="Base figure to load (default Genesis 9).")] = None,
        base_figure: Annotated[str | None, Field(description="Another base figure file instead, e.g. Genesis 9 "
                                                             "Base Anime Feminine.")] = None,
        figure: Annotated[str | None, Field(description="Use this figure already in the scene instead of "
                                                        "loading one.")] = None,
        character_preset: Annotated[str | None, Field(description="Character preset to start from "
                                                                  "(content_search kind=character).")] = None,
        traits: Annotated[dict[str, float] | None, Field(description=TRAITS_HELP)] = None,
        dials: Annotated[dict[str, float] | None, Field(description=DIALS_HELP)] = None,
        height_cm: Annotated[float | None, Field(ge=40, le=300, description="Exact standing height; the figure "
                                                                            "is scaled to it.")] = None,
        skin: SkinSpec | None = None,
        eyes: EyesSpec | None = None,
        hair: Annotated[HairSpec | None, Field(description="Head hair.")] = None,
        brows: Annotated[HairSpec | None, Field(description="Eyebrow items (Genesis 9) and their color.")] = None,
        facial_hair: Annotated[HairSpec | None, Field(description="Beard, mustache, stubble items and their "
                                                                  "color.")] = None,
        colors: ColorsSpec | None = None,
        clothing: Annotated[list[str] | None, Field(description="Clothing and shoe content files.")] = None,
        anatomy: Annotated[list[str] | None, Field(description="Anatomy geografts (genitals) for the figure, "
                                                              "or [\"auto\"] to use the installed one that "
                                                              "matches; character_list(include_anatomy=true) "
                                                              "lists them.")] = None,
        extras: Annotated[list[str] | None, Field(description="Add-ons that are part of the body: horns, tail, "
                                                              "wings, animal ears (kept when the outfit "
                                                              "changes).")] = None,
        presets: Annotated[list[str] | None, Field(description="Other presets for the figure: makeup, skin "
                                                               "details (freckles, tattoos).")] = None,
        materials: Annotated[list[MaterialEdit] | None, Field(description="Other material changes to keep, "
                                                                          "e.g. glowing eyes, fantasy "
                                                                          "skin.")] = None,
        position: Annotated[Vec3 | None, Field(description="[x, y, z] cm.")] = None,
        overwrite: Annotated[bool, Field(description="Replace a saved character with the same name.")] = False,
    ) -> dict:
        """Creates a character from a description and saves it as a reusable character sheet (JSON) plus a
        Daz character preset (.duf): base figure, body and face traits mapped to the dials installed on
        that generation, skin, eyes, teeth and nail colors, hair, eyebrows, facial hair, clothes and
        add-ons. Reports which traits found no installed dial."""
        path = ch.sheet_path(folder(), name)
        if path.is_file() and not overwrite:
            raise ToolError(f"A character named {name!r} already exists ({path.as_posix()}). Change it with "
                            "character_update, or pass overwrite=true.")
        sheet = ch.new_sheet(name)
        if character_preset:
            sheet["figure"]["character"] = await rel(character_preset)
        await fill(sheet, description=description, notes=notes, traits=traits, dials=dials, height_cm=height_cm,
                   skin=skin, eyes=eyes, hair=hair, brows=brows, facial_hair=facial_hair, colors=colors,
                   clothing=clothing, extras=extras, presets=presets, materials=materials, anatomy=anatomy)
        if figure:
            label = figure
            info = await call("figure_info", {"figure": figure})
            if info.get("type") != "figure":
                raise ToolError(f"{figure} is not a figure.")
            sheet["figure"]["generation"] = info.get("generation")
            sheet["figure"]["base"] = ch.BASE_FIGURES.get(info.get("generation") or "")
        else:
            if base_figure:
                sheet["figure"]["base"] = await rel(base_figure)
            else:
                sheet["figure"]["base"] = ch.BASE_FIGURES[generation or "Genesis 9"]
            sheet["figure"]["generation"] = generation
            label = await add_figure(sheet, name)
        report = await apply(sheet, label, STEPS, position=position)
        sheet["figure"]["generation"] = report.get("generation") or sheet["figure"]["generation"]
        sheet["applied"] = report["applied"]
        preset = None
        if not report.get("stopped"):
            preset = await save_preset(sheet, path, label)
        ch.write_sheet(path, sheet)
        return summary(sheet, path, report, preset)

    @mcp.tool(annotations=CHANGES_SCENE)
    async def character_load(
        name: Annotated[str, Field(description="Character name, or the absolute path of its .json sheet.")],
        figure: Annotated[str | None, Field(description="Apply it to this figure already in the scene instead "
                                                        "of loading a new one.")] = None,
        label: Annotated[str | None, Field(description="Label for the new figure (default: the name).")] = None,
        position: Annotated[Vec3 | None, Field(description="[x, y, z] cm.")] = None,
        use_preset: Annotated[bool, Field(description="Also apply the saved Daz preset when it is for the same "
                                                      "generation (keeps skin and material edits).")] = True,
        steps: Annotated[list[Step] | None, Field(description="Only these steps (to finish after a dialog).")] = None,
    ) -> dict:
        """Loads a saved character into the current scene: the base figure, its shape (traits are mapped
        again to the dials installed on the figure's generation, so a sheet also works on Genesis 8 / 8.1
        / 9), skin, eyes, colors, hair, clothes and add-ons."""
        path = locate(name)
        sheet = load_sheet(path)
        if figure:
            target = figure
        else:
            target = await add_figure(sheet, label or sheet["name"])
        info = await call("figure_info", {"figure": target})
        preset = None
        skipped = None
        if use_preset and sheet.get("preset_file"):
            candidate = path.parent / sheet["preset_file"]
            same = (sheet.get("applied") or {}).get("generation") == info.get("generation")
            if not candidate.is_file():
                skipped = "the preset file is gone"
            elif not same:
                skipped = "the preset was made for another generation"
            elif not ch.preset_current(sheet):
                skipped = ("the sheet changed after the preset was saved; character_update(name, refresh=true) "
                           "saves it again")
            else:
                preset = candidate
        sheet["applied"] = {**(sheet.get("applied") or {}), "worn": {}}
        report = await apply(sheet, target, list(steps or STEPS), preset=preset, position=position)
        if preset:
            report["preset"] = preset.as_posix()
        if skipped:
            report["preset_skipped"] = skipped
        return summary(sheet, path, report, None)

    @mcp.tool(annotations=CHANGES_SCENE)
    async def character_update(
        name: Annotated[str, Field(description="Character name, or the absolute path of its .json sheet.")],
        figure: Annotated[str | None, Field(description="Figure in the scene to update too (default: the one "
                                                        "labeled with the name, if any).")] = None,
        description: str | None = None,
        notes: str | None = None,
        traits: Annotated[dict[str, float | None] | None,
                          Field(description="Traits to change; other traits keep their value. 0 or null "
                                            "removes one. " + TRAITS_HELP)] = None,
        dials: Annotated[dict[str, float | None] | None, Field(description="Exact dials to change; null "
                                                                           "removes one. " + DIALS_HELP)] = None,
        height_cm: Annotated[float | None, Field(ge=0, le=300, description="Exact height; 0 removes it.")] = None,
        skin: SkinSpec | None = None,
        eyes: EyesSpec | None = None,
        hair: HairSpec | None = None,
        brows: HairSpec | None = None,
        facial_hair: HairSpec | None = None,
        colors: ColorsSpec | None = None,
        clothing: Annotated[list[str] | None, Field(description="The whole new outfit (replaces it).")] = None,
        add_clothing: Annotated[list[str] | None, Field(description="Items to add to the outfit.")] = None,
        remove_clothing: Annotated[list[str] | None, Field(description="Items to take off: file paths or words "
                                                                       "of their names.")] = None,
        extras: Annotated[list[str] | None, Field(description="Replaces the add-ons (horns, tail...).")] = None,
        anatomy: Annotated[list[str] | None, Field(description="Replaces the anatomy geografts; [] removes "
                                                              "them, [\"auto\"] picks the installed one.")] = None,
        presets: Annotated[list[str] | None, Field(description="Replaces the other presets.")] = None,
        materials: Annotated[list[MaterialEdit] | None, Field(description="Replaces the kept material "
                                                                          "changes.")] = None,
        refresh: Annotated[bool, Field(description="Apply the whole sheet to the figure again and save the "
                                                   "preset (after editing the JSON by hand).")] = False,
    ) -> dict:
        """Changes only what is asked in a saved character (a trait, the hair, one piece of clothing...)
        and keeps the rest. Updates the sheet, the figure in the scene when there is one, and the Daz
        preset."""
        path = locate(name)
        sheet = load_sheet(path)
        new_clothing = clothing
        if add_clothing or remove_clothing:
            base = list(clothing if clothing is not None else sheet.get("clothing") or [])
            base += [await rel(p) for p in add_clothing or []]
            for word in remove_clothing or []:
                low = word.lower().replace("\\", "/")
                base = [p for p in base if low not in p.lower()]
            new_clothing = base
        changed = await fill(sheet, description=description, notes=notes, traits=traits, dials=dials,
                             height_cm=height_cm, skin=skin, eyes=eyes, hair=hair, brows=brows,
                             facial_hair=facial_hair, colors=colors, clothing=new_clothing, extras=extras,
                             anatomy=anatomy,
                             presets=presets, materials=materials)
        target = figure
        if target is None and sheet["name"] in await labels_in_scene():
            target = sheet["name"]
        report = None
        preset = None
        if refresh:
            changed |= set(STEPS) - {"preset", "position"}
        if target and changed:
            applied = sheet.get("applied") or {}
            worn = dict(applied.get("worn") or {})
            keep = set(ch.worn_paths(sheet))
            if "auto" in (sheet.get("anatomy") or []) and applied.get("anatomy_auto"):
                keep.add(applied["anatomy_auto"])
            gone = [g for p in list(worn) if p not in keep for g in _as_list(worn.pop(p))]
            current = await labels_in_scene()
            gone = [g for g in gone if g in current]
            if gone:
                await call("node_delete", {"nodes": gone, "with_fitted": True})
            sheet["applied"] = {**applied, "worn": worn}
            previous = applied.get("dials") if applied.get("figure") == target else None
            todo = [s for s in STEPS if s in changed or (s == "follow" and changed & FOLLOW_AFTER)]
            report = await apply(sheet, target, todo, previous=previous)
            sheet["applied"] = {**applied, **report["applied"]}
            if gone:
                report["removed"] = gone
            if not report.get("stopped"):
                preset = await save_preset(sheet, path, target)
        ch.write_sheet(path, sheet)
        out = summary(sheet, path, report, preset)
        out["changed"] = sorted(changed)
        if not target:
            out["note"] = "Only the sheet changed: the character is not in the scene. character_load shows it."
        return out

    @mcp.tool(annotations=READ_ONLY)
    async def character_list(
        include_traits: Annotated[bool, Field(description="Also list every trait and what its ends mean.")] = False,
        include_anatomy: Annotated[str | None, Field(description="Generation (e.g. \"Genesis 9\") whose installed "
                                                                 "anatomy geografts to list.")] = None,
        name: Annotated[str | None, Field(description="Show this character's whole sheet.")] = None,
    ) -> dict:
        """Lists the saved characters (sheet and Daz preset files), or shows one sheet; optionally the
        trait vocabulary used to describe bodies and faces."""
        out: dict[str, Any] = {"folder": folder().as_posix()}
        if name:
            path = locate(name)
            out["sheet"] = load_sheet(path)
            out["path"] = path.as_posix()
        else:
            out["characters"] = ch.list_sheets(folder())
        if include_anatomy:
            found = await find_anatomy(include_anatomy, None)
            out["anatomy"] = [{"name": f.get("name"), "path": f.get("path"), "generation": f.get("generation")}
                              for f in found]
            if not found:
                out["anatomy_note"] = (f"No anatomy geograft for {include_anatomy} is installed (Genesis 9 "
                                       "Anatomical Elements, or a Genesis 8 / 8.1 one).")
        if include_traits:
            out["traits"] = ch.catalog()
        return out
