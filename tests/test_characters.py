"""Character sheets: traits mapped to the dials installed on each generation, and the
character_create / character_load / character_update / character_list tools against a small
stand-in for Daz. The dial lists are the ones of the starter Genesis 9 and Genesis 8.1 Female."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import anyio
import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from daz3d_mcp import character_tools
from daz3d_mcp import characters as ch
from daz3d_mcp.scene_tools import ContentAccess
from daz3d_mcp.settings import Settings


def dial(label, lo=-1.0, hi=1.0, group="/Actor/Head/Face/Base", name=None):
    return {"label": label, "name": name or label.replace(" ", ""), "group": group, "min": lo, "max": hi}


def pairs(*parts):
    return [dial(f"Asymmetry {p} {side}") for p in parts for side in ("Left", "Right")]


G9_FIGURE = [
    dial("Base Feminine", 0, 1, "/Actor/People/Feminine", "BaseFeminine_figure_ctrl_Character"),
    dial("Base Masculine", 0, 1, "/Actor/People/Masculine"),
    dial("Base Feminine Head", 0, 1, "/Actor/Head/People/Feminine"),
    dial("Laura Head", 0, 1, "/Actor/Head/People/Feminine"),
    dial("Proportion Height", -2, 2, "/Actor/Full Body/Base", "body_bs_ProportionHeight"),
    dial("Proportion Chest Size", -2, 2, "/Actor/Chest/Base"),
    dial("Proportion Legs Length", -2, 2, "/Actor/Legs/Base"),
    dial("Proportion Head Size", -2, 2, "/Actor/Head/Base"),
    dial("Toon Teeth Canines Upper", 0, 1, "/Actor/Head/Face/Mouth/Base Anime"),
    dial("Eyelashes Length Uniform Upper", 0, 1, "/Actor/Head/Face/Eyes/Eyelashes/Base"),
    dial("Eyelashes Length Uniform Lower", 0, 1, "/Actor/Head/Face/Eyes/Eyelashes/Base"),
    dial("Mouth Realism", 0, 1, "/Actor/Head/Face/Mouth/Base"),
    dial("Eye Blink", 0, 1, "/Pose Controls/Head/Eyes"),
] + pairs("Face Round", "Face Square", "Face Heart", "Brow Height", "Brow Size", "Cheek Size", "Eyes Angle",
          "Eyes Position Width", "Eyes Position Height", "Eyes Position Depth", "Eyelids Upper Relax",
          "Eyelids Lower Relax", "Eyelids Crease Height", "Mouth Angle", "Mouth Mid Curve",
          "Lip Upper Thickness", "Lip Lower Thickness", "Nose Wing Size", "Nose Wing Height Position",
          "Ears Position Height")
G9_MOUTH = [dial("Teeth Size Upper"), dial("Teeth Size Lower"), dial("Teeth Center Gap Upper", 0, 1),
            dial("Teeth Irregular"), dial("Mouth Width")]
G9_EYES = [dial("Eye Pupil Slit", 0, 1), dial("Eye Iris Size Larger", 0, 1), dial("Eye Iris Size Smaller", 0, 1)]
G81_FIGURE = [
    dial("Ears Elf Long", 0, 1, "/Actor/Head/Ears/Fantasy SciFi", "PHMEarsElfLong"),
    dial("Emaciated", 0, 1, "/Actor/Full Body/Real World", "FBMEmaciated"),
    dial("Pear Figure", 0, 1, "/Actor/Full Body/Real World", "FBMPearFigure"),
    dial("Bodybuilder Size", 0, 1, "/Actor/Full Body/Real World", "FBMBodybuilderSize"),
    dial("Bodybuilder Details", 0, 1, "/Actor/Full Body/Real World", "FBMBodybuilderDetails"),
    dial("Bodybuilder", 0, 1, "/Actor/Full Body/Real World", "CTRLBodybuilder"),
    dial("Chest Scale", -1, 1, "/Actor/Chest/Real World", "SCLPropagatingChest"),
    dial("Head Propagating Scale", -1, 1, "/Actor/Head/Real World", "SCLPropagatingHead"),
    dial("Legacy Eyelashes Length Upper", -1, 1, "/Actor/Head/Face/Eyes/Eyelashes/Real World"),
]


def g9() -> ch.Inventory:
    return ch.inventory_from({"figure": ("Ana", G9_FIGURE), "mouth": ("Genesis 9 Mouth (2)", G9_MOUTH),
                              "eyes": ("Genesis 9 Eyes (2)", G9_EYES)})


def g81(extra=()) -> ch.Inventory:
    return ch.inventory_from({"figure": ("Bea", G81_FIGURE + list(extra))})


# ------------------------------------------------------------ resolve ----
def test_genesis_9_traits_use_its_own_dials():
    res = ch.resolve({"feminine": 1, "height": 0.5, "lips_fullness": 0.6, "eyes_tilt": 0.4, "teeth_gap": 0.5,
                      "pupils_slit": 1, "iris_size": -0.5, "eyelashes_length": 0.4}, g9(), "Genesis 9")
    assert res.values["Ana"]["Base Feminine"] == 1
    assert res.values["Ana"]["Proportion Height"] == pytest.approx(0.15)
    for side in ("Left", "Right"):
        assert res.values["Ana"][f"Asymmetry Lip Upper Thickness {side}"] == 0.6
        assert res.values["Ana"][f"Asymmetry Lip Lower Thickness {side}"] == 0.6
        assert res.values["Ana"][f"Asymmetry Eyes Angle {side}"] == 0.4
    assert res.traits["lips_fullness"]["how"] == "pair"
    assert res.values["Genesis 9 Mouth (2)"] == {"Teeth Center Gap Upper": 0.5}
    assert res.values["Genesis 9 Eyes (2)"] == {"Eye Pupil Slit": 1.0, "Eye Iris Size Smaller": 0.5}
    assert res.values["Ana"]["Eyelashes Length Uniform Upper"] == 0.4
    assert res.missing == []


def test_signs_follow_what_the_trait_says():
    res = ch.resolve({"eyes_deep": 0.5}, g9(), "Genesis 9")
    assert res.values["Ana"]["Asymmetry Eyes Position Depth Left"] == -0.5
    res = ch.resolve({"eyes_deep": -0.5}, g9(), "Genesis 9")
    assert res.values["Ana"]["Asymmetry Eyes Position Depth Right"] == 0.5


def test_missing_and_approximated_are_reported():
    res = ch.resolve({"weight": 0.3, "age": 0.6, "nose_width": 0.4, "fangs": 0.8, "bust": 0.5}, g9(), "Genesis 9")
    assert {m["trait"] for m in res.missing} == {"weight", "age"}
    assert res.traits["nose_width"]["approximated"] is True
    assert res.traits["fangs"]["dials"] == {"Ana": {"Toon Teeth Canines Upper": 0.8}}
    assert res.traits["bust"]["dials"] == {"Ana": {"Proportion Chest Size": 0.2}}


def test_genesis_8_1_maps_the_same_sheet_to_other_dials():
    traits = {"feminine": 1, "masculine": 0.5, "weight": -0.5, "muscle": 0.5, "ears_pointed": 0.7, "height": 0.5,
              "lips_fullness": 0.6, "head_size": 0.4, "hips": 0.5}
    res = ch.resolve(traits, g81(), "Genesis 8.1 Female")
    assert res.traits["feminine"]["how"] == "base figure"
    assert res.values["Bea"]["Emaciated"] == pytest.approx(0.3)
    assert res.values["Bea"]["Bodybuilder"] == pytest.approx(0.3)
    assert res.values["Bea"]["Ears Elf Long"] == 0.7
    assert res.values["Bea"]["Head Propagating Scale"] == pytest.approx(0.06)
    assert res.values["Bea"]["Pear Figure"] == pytest.approx(0.3)
    assert res.traits["height"]["how"] == "scale"
    assert res.scale_factor == pytest.approx(1.035)
    assert {m["trait"] for m in res.missing} == {"masculine", "lips_fullness"}


def test_a_morph_made_for_the_trait_wins_over_a_substitute():
    pack = [dial("Lips Fullness", -1, 1, "/Actor/Head/Face/Mouth"), dial("Nose Width", -1, 1, "/Actor/Head/Nose"),
            dial("Nose Width Left", -1, 1, "/Actor/Head/Nose"), dial("Heavy", 0, 1, "/Actor/Full Body"),
            dial("Thin", 0, 1, "/Actor/Full Body"), dial("Breasts Size", -1, 1, "/Actor/Chest")]
    inv = ch.inventory_from({"figure": ("Ana", G9_FIGURE + pack)})
    res = ch.resolve({"lips_fullness": 0.5, "nose_width": -0.4, "weight": -0.3, "bust": 0.4}, inv, "Genesis 9")
    assert res.traits["lips_fullness"]["dials"] == {"Ana": {"Lips Fullness": 0.5}}
    assert res.traits["nose_width"]["dials"] == {"Ana": {"Nose Width": -0.4}}
    assert res.traits["weight"]["dials"] == {"Ana": {"Thin": 0.3}}
    assert res.traits["bust"]["dials"] == {"Ana": {"Breasts Size": 0.4}}
    assert "approximated" not in res.traits["nose_width"]


def test_traits_on_one_dial_add_up():
    res = ch.resolve({"lips_fullness": 0.4, "lip_upper": 0.3}, g9(), "Genesis 9")
    assert res.values["Ana"]["Asymmetry Lip Upper Thickness Left"] == pytest.approx(0.7)
    assert res.values["Ana"]["Asymmetry Lip Lower Thickness Left"] == pytest.approx(0.4)


def test_catalog_and_unknown_traits():
    names = [t["trait"] for t in ch.catalog()]
    assert len(names) == len(set(names)) > 70
    for name in names:
        assert name in character_tools.TRAITS_HELP
    unknown = ch.unknown_traits(["nose_width", "nose_curve"])
    assert unknown[0]["trait"] == "nose_curve" and "nose_width" in unknown[0]["similar"]


# -------------------------------------------------------- sheet files ----
def test_sheet_round_trip_and_helpers(tmp_path):
    sheet = ch.new_sheet("Ána López")
    ch.set_traits(sheet, {"height": 0.3, "nose_width": 0.4})
    assert sheet["body"] == {"height": 0.3} and sheet["face"] == {"nose_width": 0.4}
    ch.set_traits(sheet, {"height": None})
    assert ch.traits_of(sheet) == {"nose_width": 0.4}
    path = ch.sheet_path(tmp_path, sheet["name"])
    assert path.name == "ana-lopez.json"
    ch.write_sheet(path, sheet)
    again = ch.read_sheet(path)
    assert again["face"] == {"nose_width": 0.4}
    assert ch.list_sheets(tmp_path)[0]["name"] == "Ána López"
    sheet["preset_file"] = "ana-lopez.duf"
    sheet["preset_of"] = ch.content_hash(sheet)
    assert ch.preset_current(sheet)
    ch.set_traits(sheet, {"nose_width": 0.6})
    assert not ch.preset_current(sheet)
    (tmp_path / "other.json").write_text('{"format": "something else"}')
    assert len(ch.list_sheets(tmp_path)) == 1


def test_small_helpers():
    assert ch.follower_roles([{"label": "Genesis 9 Eyelashes (2)"}, {"label": "Genesis 9 Mouth (2)"},
                              {"label": "Genesis 9 Eyes (2)"}]) == {"mouth": "Genesis 9 Mouth (2)",
                                                                    "eyes": "Genesis 9 Eyes (2)"}
    assert ch.skin_surfaces(["Head", "Body", "Arms", "Legs", "Fingernails", "Irises", "Mouth Cavity", "Lips",
                             "EyeSocket", "Teeth"]) == ["Head", "Body", "Arms", "Legs", "Lips"]
    assert ch.zeroed({"Ana": {"A": 1, "B": 2}}, {"Ana": {"A": 0.5}}) == {"Ana": {"B": 0.0}}


# ------------------------------------------------------ the MCP tools ----
class FakeDaz:
    def __init__(self, tmp: Path):
        self.nodes: dict[str, dict] = {}
        self.calls: list[tuple[str, dict]] = []
        self.tmp = tmp
        self.library: list[dict] = []

    def _add(self, label: str, **node) -> str:
        base, n = label, 2
        while label in self.nodes:
            label = f"{base} ({n})"
            n += 1
        self.nodes[label] = node
        return label

    def load(self, path: str, target: str | None) -> dict:
        if path in ch.BASE_FIGURES.values():
            gen = next(g for g, p in ch.BASE_FIGURES.items() if p == path)
            fig = "Genesis 9" if gen == "Genesis 9" else gen
            label = self._add(fig, type="figure", generation=gen, scale=1.0, position=[0, 0, 0],
                              dials={d["label"]: 0.0 for d in (G9_FIGURE if gen == "Genesis 9" else G81_FIGURE)},
                              meta=G9_FIGURE if gen == "Genesis 9" else G81_FIGURE)
            added = [{"label": label, "type": "figure", "generation": gen}]
            if gen == "Genesis 9":
                for part, meta in (("Mouth", G9_MOUTH), ("Eyes", G9_EYES)):
                    sub = self._add(f"Genesis 9 {part}", type="fitted_figure", fitted_to=label,
                                    dials={d["label"]: 0.0 for d in meta}, meta=meta)
                    added.append({"label": sub, "type": "fitted_figure", "fitted_to": label})
            return {"added": added}
        assert target in self.nodes, (path, target)
        if "Hair" in path or "Clothing" in path or "Anatomy" in path:
            label = self._add(Path(path).stem, type="fitted_figure", fitted_to=target, dials={}, meta=[])
            return {"added": [{"label": label, "type": "fitted_figure", "fitted_to": target}]}
        self.nodes[target].setdefault("presets", []).append(path)
        return {"added": []}

    async def call(self, tool: str, args: dict | None = None, timeout: float | None = None) -> dict:
        args = dict(args or {})
        self.calls.append((tool, args))
        handler = getattr(self, "t_" + tool)
        return handler(**args)

    def t_scene_info(self, **_):
        return {"nodes": [{"label": k} for k in self.nodes]}

    def t_node_set(self, node, label=None, scale=None, position=None, **_):
        data = self.nodes[node]
        if scale is not None:
            data["scale"] = scale
        if position is not None:
            data["position"] = position
        if label and label != node:
            self.nodes[label] = self.nodes.pop(node)
            for other in self.nodes.values():
                if other.get("fitted_to") == node:
                    other["fitted_to"] = label
            node = label
        return {"label": node, "scale": self.nodes[node].get("scale", 1)}

    def t_figure_info(self, figure):
        data = self.nodes[figure]
        height = 170 * (1 + 0.39 * data["dials"].get("Proportion Height", 0)) * data.get("scale", 1)
        wearing = [{"label": k} for k, v in self.nodes.items() if v.get("fitted_to") == figure]
        return {"label": figure, "type": data["type"], "generation": data.get("generation"),
                "transform": {"scale": data.get("scale", 1)}, "height_cm": round(height, 1), "wearing": wearing,
                "surfaces": ["Head", "Body", "Arms", "Legs", "Fingernails", "Mouth Cavity"]}

    def t_morph_list(self, node, limit=100):
        meta = self.nodes[node]["meta"]
        return {"morphs": [dict(d, value=self.nodes[node]["dials"].get(d["label"], 0)) for d in meta]}

    def t_morph_set(self, node, values):
        dials = self.nodes[node]["dials"]
        not_found = []
        for key, value in values.items():
            if key in dials:
                dials[key] = value
            else:
                not_found.append({"morph": key, "similar": []})
        return {"set": [], "not_found": not_found}

    def t_eye_color(self, **args):
        self.nodes[args["figure"]]["eyes"] = args
        return {"changed": [{}]}

    def t_material_set(self, node, properties, surfaces=None):
        self.nodes[node].setdefault("materials", []).append((properties, surfaces))
        return {"changed": [{"surface": "s"}]}

    def t_content_load(self, path, kind, target):
        self.nodes[target].setdefault("presets", []).append(path)
        return {"added": []}

    def t_character_preset_save(self, figure, path, overwrite):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps({"figure": figure, "dials": self.nodes[figure]["dials"]}))
        return {"saved": path}

    def t_node_delete(self, nodes, with_fitted=True):
        for n in nodes:
            self.nodes.pop(n, None)
        return {"deleted": nodes}


@pytest.fixture
def setup(tmp_path):
    daz = FakeDaz(tmp_path)
    mcp = FastMCP("test")
    settings = Settings(characters_dir=str(tmp_path / "chars"))
    client = SimpleNamespace(settings=settings)

    async def load(path, target):
        return daz.load(path, target)

    async def relative(path):
        return path

    async def search(query, kind, generation):
        return [r for r in daz.library if query.lower() in r["path"].lower()]

    content = ContentAccess(lambda: None, load, relative, search)
    character_tools.register(mcp, daz.call, lambda: client, content)

    def run(tool, **args):
        async def go():
            return await mcp.call_tool(tool, args)
        res = anyio.run(go)
        parts = res[0] if isinstance(res, tuple) else res
        return json.loads(parts[0].text)
    return daz, run, tmp_path / "chars"


HAIR = "People/Genesis 9/Hair/Pixie Hair.duf"
SHIRT = "People/Genesis 9/Clothing/Base Shirt.duf"
SHORTS = "People/Genesis 9/Clothing/Base Shorts.duf"


def test_create_load_update_list(setup):
    daz, run, folder = setup
    out = run("character_create", name="Ana", description="tall, full lips", traits={"feminine": 1,
              "lips_fullness": 0.5, "weight": 0.3, "teeth_gap": 0.4}, height_cm=165,
              eyes={"color": "#3f8f4a", "iris": 15}, skin={"tone": "#e8d0c0", "details": "freckles"},
              hair={"items": [HAIR], "color": "#2a1a12"}, clothing=[SHIRT, SHORTS], position=[-80, 0, 0])
    assert out["figure"] == "Ana" and out["errors"] == []
    assert out["missing"][0]["trait"] == "weight" and "missing_hint" in out
    assert out["height_cm"] == pytest.approx(165, abs=0.2)
    ana = daz.nodes["Ana"]
    assert ana["dials"]["Base Feminine"] == 1 and ana["position"] == [-80, 0, 0]
    assert daz.nodes["Genesis 9 Mouth"]["dials"]["Teeth Center Gap Upper"] == 0.4
    assert ana["eyes"]["iris"] == 15
    assert ana["materials"][0][1] == ["Head", "Body", "Arms", "Legs"]
    assert daz.nodes["Pixie Hair"]["materials"][0][0]["Hair Root Color"] == "#2a1a12"
    sheet = json.loads((folder / "ana.json").read_text(encoding="utf-8"))
    assert sheet["face"] == {"lips_fullness": 0.5, "teeth_gap": 0.4} and sheet["preset_file"] == "ana.duf"
    assert (folder / "ana.duf").is_file()

    with pytest.raises(ToolError, match="already exists"):
        run("character_create", name="Ana")

    loaded = run("character_load", name="Ana", position=[80, 0, 0])
    assert loaded["figure"] == "Ana (2)" and loaded["preset"].endswith("ana.duf")
    assert daz.nodes["Ana (2)"]["dials"]["Asymmetry Lip Upper Thickness Left"] == 0.5

    updated = run("character_update", name="Ana", traits={"lips_fullness": None, "eyes_tilt": 0.3},
                  remove_clothing=["shorts"])
    assert updated["changed"] == ["clothing", "height", "shape"]
    assert updated["removed"] == ["Base Shorts"]
    assert "Base Shorts" not in daz.nodes and "Base Shirt" in daz.nodes
    assert ana["dials"]["Asymmetry Lip Upper Thickness Left"] == 0
    assert ana["dials"]["Asymmetry Eyes Angle Right"] == 0.3
    sheet = json.loads((folder / "ana.json").read_text(encoding="utf-8"))
    assert sheet["face"] == {"teeth_gap": 0.4, "eyes_tilt": 0.3} and sheet["clothing"] == [SHIRT]
    assert ch.preset_current(ch.read_sheet(folder / "ana.json"))

    listed = run("character_list", include_traits=True)
    assert listed["characters"][0]["name"] == "Ana" and listed["characters"][0]["preset"]
    assert any(t["trait"] == "nose_width" for t in listed["traits"])
    assert run("character_list", name="ana")["sheet"]["name"] == "Ana"


def test_sheet_moves_to_genesis_8_1_and_skips_the_preset(setup):
    daz, run, _ = setup
    run("character_create", name="Ana", traits={"feminine": 1, "ears_pointed": 0.6, "lips_fullness": 0.5},
        eyes={"color": "#3f8f4a", "iris": 15})
    bea = daz.load(ch.BASE_FIGURES["Genesis 8.1 Female"], None)["added"][0]["label"]
    out = run("character_load", name="Ana", figure=bea)
    assert out["generation"] == "Genesis 8.1 Female"
    assert out["preset_skipped"] == "the preset was made for another generation"
    assert daz.nodes[bea]["dials"]["Ears Elf Long"] == 0.6
    assert "iris" not in daz.nodes[bea]["eyes"] and any("Genesis 9" in n for n in out["notes"])
    assert [m["trait"] for m in out["missing"]] == ["lips_fullness"]


def test_update_without_the_figure_only_changes_the_sheet(setup):
    daz, run, folder = setup
    run("character_create", name="Ana", traits={"feminine": 1})
    daz.nodes.clear()
    out = run("character_update", name="Ana", traits={"nose_size": 0.3}, notes="the quiet one")
    assert "note" in out
    sheet = ch.read_sheet(folder / "ana.json")
    assert sheet["notes"] == "the quiet one" and not ch.preset_current(sheet)
    loaded = run("character_load", name="Ana")
    assert "sheet changed" in loaded["preset_skipped"]


def test_bad_input_is_refused(setup):
    _, run, _ = setup
    with pytest.raises(ToolError, match="Unknown traits"):
        run("character_create", name="X", traits={"nose_curviness": 0.3})
    with pytest.raises(ToolError, match="out of range"):
        run("character_create", name="X", traits={"fangs": -0.5})
    with pytest.raises(ToolError, match="No character"):
        run("character_load", name="Nobody")


def test_new_face_traits_on_genesis_9():
    extra_mouth = [dial("Teeth Individual Taper"), dial("Teeth Tucked Gumline", 0, 1)]
    extra_figure = [dial("Asymmetry Nose Bridge Horizontal"), dial("Asymmetry Nose Base Twist"),
                    dial("Asymmetry Jaw Horizontal Balance"), dial("Asymmetry Nose Tip Balance Left", 0, 1),
                    dial("Eyelashes Large Uniform Upper", 0, 1), dial("Eyelashes Large Uniform Lower", 0, 1)]
    inv = ch.inventory_from({"figure": ("Ana", G9_FIGURE + extra_figure),
                             "mouth": ("Genesis 9 Mouth (2)", G9_MOUTH + extra_mouth),
                             "eyes": ("Genesis 9 Eyes (2)", G9_EYES + [dial("Eye Whole Size")])})
    res = ch.resolve({"teeth_taper": 0.6, "gums_hidden": 0.5, "nose_crooked": -0.4, "jaw_shift": 0.5,
                      "asymmetry": 1, "lashes_volume": 0.5, "eyes_size": 0.5, "philtrum": 0.3}, inv, "Genesis 9")
    mouth = res.values["Genesis 9 Mouth (2)"]
    assert mouth["Teeth Individual Taper"] == 0.6 and mouth["Teeth Tucked Gumline"] == 0.5
    assert res.values["Ana"]["Asymmetry Nose Bridge Horizontal"] == pytest.approx(-0.2)
    assert res.values["Ana"]["Asymmetry Jaw Horizontal Balance"] == pytest.approx(0.15 + 0.06)
    assert res.values["Ana"]["Asymmetry Brow Height Left"] == pytest.approx(0.12)
    assert res.values["Ana"]["Eyelashes Large Uniform Lower"] == 0.5
    assert res.values["Genesis 9 Eyes (2)"]["Eye Whole Size"] == pytest.approx(0.15)
    assert res.traits["eyes_size"]["approximated"] is True
    assert [m["trait"] for m in res.missing] == ["philtrum"]


def test_role_prefixed_dials_and_unknown_traits_in_a_hand_edited_sheet():
    assert ch.split_dial("mouth:Teeth Size Lower") == ("mouth", "Teeth Size Lower")
    assert ch.split_dial("Laura Head") == ("figure", "Laura Head")
    assert ch.split_dial("Note: something") == ("figure", "Note: something")
    sheet = ch.new_sheet("X")
    sheet["face"] = {"nose_widht": 0.3, "nose_width": 0.2}
    assert ch.unknown_in_sheet(sheet) == ["nose_widht"]
    assert ch.traits_of(sheet) == {"nose_width": 0.2}


def test_looks_colors_brows_extras_and_materials(setup):
    daz, run, _ = setup
    brows = "People/Genesis 9/Hair/Eyebrows Fiber.duf"
    beard = "People/Genesis 9/Hair/Short Beard.duf"
    horns = "People/Genesis 9/Clothing/Horns.duf"
    out = run("character_create", name="Kael", traits={"masculine": 1, "teeth_taper": 0.5},
              dials={"mouth:Teeth Size Lower": 0.3, "eyes:Eye Pupil Slit": 1},
              eyes={"left": {"color": "#3060c0", "iris": 13}, "right": {"color": "#40a040"}, "sclera": "#202020"},
              brows={"items": [brows], "color": "#202020"},
              facial_hair={"items": [beard], "color": "#a04020", "tip_color": "#c08060"},
              colors={"teeth": "#e8dcb0", "nails": "#202020", "lips": "#a03030"},
              extras=[horns], materials=[{"on": horns, "properties": {"Base Color": "#303030"}}])
    assert out["errors"] == []
    assert daz.nodes["Genesis 9 Mouth"]["dials"]["Teeth Size Lower"] == 0.3
    assert daz.nodes["Genesis 9 Eyes"]["dials"]["Eye Pupil Slit"] == 1
    eye_calls = [a for t, a in daz.calls if t == "eye_color"]
    assert {a.get("eyes") for a in eye_calls if "color" in a} == {"left", "right"}
    assert any(a.get("sclera") == "#202020" for a in eye_calls)
    beard_props = daz.nodes["Short Beard"]["materials"][0][0]
    assert beard_props["Hair Root Color"] == "#a04020" and beard_props["Hair Tip Color"] == "#c08060"
    assert daz.nodes["Genesis 9 Mouth"]["materials"][0] == ({"Base Color": "#e8dcb0"}, ["Teeth"])
    assert any("Lips" in n for n in out["notes"])
    assert daz.nodes["Horns"]["materials"][0][0] == {"Base Color": "#303030"}

    out = run("character_update", name="Kael", extras=[], brows={"color": "#808080"})
    assert "Horns" not in daz.nodes and out["removed"] == ["Horns"]
    assert daz.nodes["Eyebrows Fiber"]["materials"][-1][0]["Hair Root Color"] == "#808080"
    assert "materials" in run("character_list", name="Kael")["sheet"]


def test_skill_explains_every_trait():
    skill = (Path(__file__).resolve().parents[1] / "skills" / "character-design" / "SKILL.md").read_text(
        encoding="utf-8")
    missing = [name for name in ch.TRAITS if f"`{name}`" not in skill]
    assert missing == []


def test_how_a_trait_was_made():
    res = ch.resolve({"lips_fullness": 0.3, "eyes_deep": 0.3, "asymmetry": 1}, g9(), "Genesis 9")
    assert res.traits["lips_fullness"]["how"] == "pair"
    assert res.traits["eyes_deep"]["how"] == "pair"


FEM = "People/Genesis 9/Anatomy/Genesis 9 Feminine Anatomical Elements.duf"
MAS = "People/Genesis 9/Anatomy/Genesis 9 Masculine Anatomical Elements.duf"


def test_anatomy_auto_picks_the_installed_geograft_and_reports_when_missing(setup):
    daz, run, _ = setup
    out = run("character_create", name="Nadia", traits={"feminine": 1}, anatomy=["auto"])
    assert any("No anatomy geograft" in n for n in out["notes"])
    daz.library = [{"name": "Feminine", "path": FEM, "generation": "Genesis 9"},
                   {"name": "Feminine MAT", "path": "People/Genesis 9/Anatomy/Materials/Anatomical Elements MAT.duf",
                    "generation": "Genesis 9"},
                   {"name": "Masculine", "path": MAS, "generation": "Genesis 9"}]
    listed = run("character_list", include_anatomy="Genesis 9")
    assert {a["path"] for a in listed["anatomy"]} == {FEM, MAS}
    out = run("character_create", name="Omar", traits={"masculine": 1}, anatomy=["auto"],
              dials={"anatomy:Size": 0.4})
    assert out["anatomy"] == MAS
    assert daz.nodes["Genesis 9 Masculine Anatomical Elements"]["fitted_to"] == "Omar"
    out = run("character_update", name="Omar", anatomy=[])
    assert out["removed"] == ["Genesis 9 Masculine Anatomical Elements"]


def test_pick_anatomy_prefers_the_right_body():
    found = [{"path": FEM}, {"path": MAS}, {"path": "x/Anatomical Elements Shader.duf"}]
    assert character_tools.pick_anatomy(found, "masculine")[0]["path"] == MAS
    assert character_tools.pick_anatomy(found, "feminine")[0]["path"] == FEM
    assert len(character_tools.pick_anatomy(found, None)) == 2
    assert ch.follower_roles([{"label": "Genesis 9 Feminine Anatomical Elements"}]) == {
        "anatomy": "Genesis 9 Feminine Anatomical Elements"}
