"""New shape dials made from a mesh and its bone weights, projected onto worn items, and the
morph_generate tool against a stand-in for Daz."""

from __future__ import annotations

import json
import math
from pathlib import Path

import anyio
import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from daz3d_mcp import character_tools, morph_tools
from daz3d_mcp import characters as ch
from daz3d_mcp import morphgen as mg


def grid_mesh(n: int = 9) -> dict:
    verts, facets, left, right = [], [], [], []
    for j in range(n):
        for i in range(n):
            x = i - (n - 1) / 2
            verts += [x, float(j), 0.0]
            idx = j * n + i
            if x < 0:
                left += [idx, 1.0]
            elif x > 0:
                right += [idx, 1.0]
    for j in range(n - 1):
        for i in range(n - 1):
            a = j * n + i
            facets += [a, a + 1, a + n + 1, a + n]
    return {"figure": "Test", "generation": "Genesis 9", "vertices": verts, "facets": facets,
            "weights": {"l_nostril": left, "r_nostril": right}}


@pytest.fixture
def mesh(tmp_path) -> mg.Mesh:
    path = tmp_path / "mesh.json"
    path.write_text(json.dumps(grid_mesh()))
    return mg.Mesh.load(path)


def test_scale_is_symmetric(mesh):
    recipe = mg.RECIPES["nose_width"]
    deltas = mg.build_deltas(mesh, recipe)
    assert deltas
    for i, (dx, dy, dz) in deltas.items():
        x = mesh.vertices[i][0]
        mirror = next(k for k, v in enumerate(mesh.vertices) if v == (-x, mesh.vertices[i][1], 0.0))
        assert deltas.get(mirror, (0.0, 0.0, 0.0))[0] == pytest.approx(-dx, abs=1e-4)
        assert dy == pytest.approx(0) and dz == pytest.approx(0)
        assert dx * x >= 0


def test_inflate_follows_normals(mesh):
    recipe = mg.Recipe("T", "T", "/T", "t", "", (mg.Op("inflate", {"nostril": 1.0},
                                                       (1.0, 0.0, 0.0), smooth=0),), smooth=0)
    deltas = mg.build_deltas(mesh, recipe)
    assert len(deltas) > 50
    for dx, dy, dz in deltas.values():
        assert abs(dz) == pytest.approx(1.0, abs=1e-3) and dx == pytest.approx(0) and dy == pytest.approx(0)


def test_projection_carries_deltas_to_nearby_items(mesh):
    deltas = {i: (0.0, 0.0, 1.0) for i in range(len(mesh.vertices))}
    item = [(0.0, 4.0, 0.2), (1.0, 2.0, 0.3), (100.0, 100.0, 100.0)]
    out = mg.project(mesh.vertices, deltas, item)
    assert out[0][2] == pytest.approx(1.0, rel=0.1) and out[1][2] > 0.9
    assert 2 not in out


def test_write_deltas_is_flat(tmp_path):
    path = tmp_path / "d.json"
    mg.write_deltas(path, {3: (0.1, 0.0, -0.2), 1: (0.0, 0.5, 0.0)})
    assert json.loads(path.read_text()) == [1, 0.0, 0.5, 0.0, 3, 0.1, 0.0, -0.2]


def test_generated_dials_are_found_by_traits():
    figure = [{"label": "MCP Nose Width", "name": "DazMcp_NoseWidth", "group": "/Actor/Head/Face/Nose/Daz3D-MCP",
               "min": -1, "max": 1},
              {"label": "MCP Weight", "name": "DazMcp_Weight", "group": "/Actor/Full Body/Daz3D-MCP",
               "min": -1, "max": 1}]
    inv = ch.inventory_from({"figure": ("Bruno", figure)})
    res = ch.resolve({"nose_width": 0.4, "weight": -0.3}, inv, "Genesis 9")
    assert res.traits["nose_width"]["dials"] == {"Bruno": {"MCP Nose Width": 0.4}}
    assert res.traits["weight"]["dials"] == {"Bruno": {"MCP Weight": -0.3}}
    assert res.traits["weight"]["how"] == "generated"


def test_daz_pairs_win_over_generated_dials_and_generated_over_substitutes():
    figure = [{"label": f"Asymmetry Lip {p} Thickness {s}", "name": f"lip{p}{s}", "group": "/Actor/Head",
               "min": -1, "max": 1} for p in ("Upper", "Lower") for s in ("Left", "Right")]
    figure += [{"label": f"Asymmetry Nose Wing Size {s}", "name": f"nw{s}", "group": "/Actor/Head", "min": -1,
                "max": 1} for s in ("Left", "Right")]
    figure += [{"label": "MCP Lips Fullness", "name": "DazMcp_LipsFullness", "group": "/Actor/Head/Face/Daz3D-MCP",
                "min": -1, "max": 1},
               {"label": "MCP Nose Width", "name": "DazMcp_NoseWidth", "group": "/Actor/Head/Face/Nose/Daz3D-MCP",
                "min": -1, "max": 1}]
    res = ch.resolve({"lips_fullness": 0.4, "nose_width": 0.4}, ch.inventory_from({"figure": ("A", figure)}),
                     "Genesis 9")
    assert res.traits["lips_fullness"]["how"] == "pair"
    assert res.traits["nose_width"]["how"] == "generated" and "approximated" not in res.traits["nose_width"]
    assert all(r.trait in ch.TRAITS for r in mg.RECIPES.values())


class FakeDaz:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.calls: list[tuple[str, dict]] = []
        self.morphs: dict[str, dict] = {}

    async def call(self, tool: str, args: dict | None = None, timeout: float | None = None) -> dict:
        args = dict(args or {})
        self.calls.append((tool, args))
        if tool == "figure_info":
            if args["figure"] == "Bruno":
                return {"generation": "Genesis 9", "wearing": [{"label": "Shirt"}]}
            return {"generation": "Genesis 3 Female", "wearing": []}
        if tool == "morph_mesh":
            data = grid_mesh()
            if args.get("weights") is False:
                data["weights"] = {}
            Path(args["path"]).write_text(json.dumps(data))
            return {"vertices": len(data["vertices"]) // 3}
        if tool == "morph_create":
            flat = json.loads(Path(args["deltas"]).read_text())
            self.morphs[f"{args['figure']}:{args['name']}"] = {"master": args.get("master"),
                                                               "deltas": len(flat) // 4}
            return {"deltas": len(flat) // 4, "value": 0}
        if tool == "morph_save":
            return {"library": "lib", "morphs": args["morphs"]}
        if tool == "morph_list":
            names = [k.split(":")[1] for k in self.morphs if k.startswith(args["node"] + ":")]
            return {"morphs": [{"name": n} for n in names]}
        raise AssertionError(tool)


@pytest.fixture
def tool(tmp_path, monkeypatch):
    monkeypatch.setenv("DAZ3D_MCP_HOME", str(tmp_path / "home"))
    daz = FakeDaz(tmp_path)
    mcp = FastMCP("test")
    morph_tools.register(mcp, daz.call)

    def run(name, **args):
        async def go():
            return await mcp.call_tool(name, args)
        res = anyio.run(go)
        parts = res[0] if isinstance(res, tuple) else res
        return json.loads(parts[0].text)
    return daz, run


def test_morph_generate_makes_saves_and_follows(tool):
    daz, run = tool
    listed = run("morph_generate", figure="Bruno")
    assert {a["trait"] for a in listed["available"]} == set(mg.ALL_RECIPES)
    assert all(set(mg.ALL) == set(r.generations) for r in mg.RECIPES.values())
    out = run("morph_generate", figure="Bruno", traits=["nose_width", "weight"])
    assert [m["dial"] for m in out["made"]] == ["MCP Nose Width", "MCP Weight"]
    assert out["saved"]["morphs"] == ["DazMcp_NoseWidth", "DazMcp_Weight"]
    assert daz.morphs["Shirt:DazMcp_NoseWidth"]["master"] == "Bruno"
    assert "Shirt:DazMcp_Weight" not in daz.morphs
    assert any(f["item"] == "Shirt" for f in out["followers"])
    meshes = [a for t, a in daz.calls if t == "morph_mesh"]
    assert meshes[0].get("weights") is not False and meshes[-1]["master"] == "Bruno"


def test_morph_generate_refuses_other_generations_and_unknown_traits(tool):
    _, run = tool
    with pytest.raises(ToolError, match="Genesis 3 Female"):
        run("morph_generate", figure="Old", traits=["weight"])
    with pytest.raises(ToolError, match="No recipe"):
        run("morph_generate", figure="Bruno", traits=["horns"])


def test_character_tools_make_items_follow_generated_dials(tool):
    daz, _ = tool
    gen = morph_tools.Generator(daz.call)
    daz.morphs["Bruno:DazMcp_Weight"] = {"master": None, "deltas": 1}
    recipes = anyio.run(gen.in_use, "Bruno")
    assert [r.trait for r in recipes] == ["weight"]
    assert character_tools.FOLLOW_AFTER == {"shape", "anatomy", "hair", "clothing", "extras"}


def test_every_region_names_bones_for_both_generations():
    used = {name for r in mg.RECIPES.values() for op in r.ops for name in op.bones}
    assert used <= set(mg.CANON)
    for name in used:
        assert set(mg.CANON[name]) == {"g9", "g8"}
    assert mg.gen_key("Genesis 9") == "g9" and mg.gen_key("Genesis 8.1 Female") == "g8"


def test_genesis_8_mesh_uses_its_own_bone_names(tmp_path):
    data = grid_mesh()
    data["generation"] = "Genesis 8.1 Female"
    data["weights"] = {"lNostril": data["weights"]["l_nostril"], "rNostril": data["weights"]["r_nostril"]}
    path = tmp_path / "g8.json"
    path.write_text(json.dumps(data))
    mesh = mg.Mesh.load(path)
    assert mesh.key == "g8"
    assert mg.build_deltas(mesh, mg.RECIPES["nose_width"])


def test_peak_sets_the_strongest_move(mesh):
    deltas = mg.build_deltas(mesh, mg.RECIPES["nose_width"])
    top = max(sum(c * c for c in d) ** 0.5 for d in deltas.values())
    assert top == pytest.approx(mg.RECIPES["nose_width"].peak, rel=1e-3)


def test_spheres_find_the_nose_tip(tmp_path):
    data = grid_mesh()
    verts = data["vertices"]
    mid = (len(verts) // 3) // 2
    verts[mid * 3 + 2] = 2.0
    data["weights"]["head"] = [i for v in range(len(verts) // 3) for i in (v, 1.0)]
    path = tmp_path / "m.json"
    path.write_text(json.dumps(data))
    mesh = mg.Mesh.load(path)
    assert mesh.landmarks["nose_tip"][2] == 2.0
    region = mesh.sphere(mg.Sphere("nose_tip", (0.0, 0.0, 0.0), (1.5, 1.5, 3.0)))
    assert region[mid] == pytest.approx(1.0) and len(region) < 15


def test_sculpt_from_blender_is_matched_in_size_and_axes(mesh, tmp_path):
    path = tmp_path / "base.obj"
    mg.write_obj(path, mesh, "m")
    verts = mg.read_obj_vertices(path)
    sculpt = [(x, -z, y) for x, y, z in verts]
    sculpt[10] = (sculpt[10][0], sculpt[10][1] - 0.005, sculpt[10][2])
    deltas, fit = mg.sculpt_deltas(mesh.vertices, sculpt)
    assert fit["axis"] == "z_up" and fit["scale"] == 100.0
    assert list(deltas) == [10] and deltas[10][2] == pytest.approx(0.5, abs=1e-3)
    with pytest.raises(ValueError, match="vertices"):
        mg.sculpt_deltas(mesh.vertices, sculpt[:-1])
    with pytest.raises(ValueError, match="line up"):
        mg.sculpt_deltas(mesh.vertices, list(reversed(sculpt)))


def test_morph_import_tool_makes_a_dial_from_an_obj(tool, tmp_path):
    daz, run = tool
    grid = grid_mesh()
    flat = grid["vertices"]
    lines = [f"v {flat[i]} {flat[i + 1]} {flat[i + 2] + (0.3 if i == 0 else 0.0)}" for i in range(0, len(flat), 3)]
    obj = tmp_path / "sculpt.obj"
    obj.write_text("\n".join(lines))
    out = run("morph_import", figure="Bruno", obj=str(obj), label="Hooked Nose", group="/Actor/Head/Face/Nose")
    assert out["dial"] == "MCP Hooked Nose" and out["name"] == "DazMcp_HookedNose"
    assert daz.morphs["Bruno:DazMcp_HookedNose"]["deltas"] == 1
    assert daz.morphs["Shirt:DazMcp_HookedNose"]["master"] == "Bruno"
    assert out["saved"]["morphs"] == ["DazMcp_HookedNose"]
    exported = run("morph_export", figure="Bruno", path=str(tmp_path / "out.obj"), units="cm")
    assert exported["vertices"] == 81 and (tmp_path / "out.obj").read_text().count("\nf ") == 64


def test_bust_press_dents_one_side_only():
    path = Path(__file__).parent / "_press_mesh.json"
    verts, facets, pecs = [], [], []
    n = 21
    for j in range(n):
        for i in range(n):
            x, y = i - 10.0, j - 10.0
            z = 8.0 - 0.05 * (min(abs(x - 6), abs(x + 6)) ** 2 + y * y)
            verts += [x, y + 120.0, z]
            if abs(x) > 1:
                pecs += [j * n + i, 1.0]
    for j in range(n - 1):
        for i in range(n - 1):
            a = j * n + i
            facets += [a, a + n, a + n + 1, a + 1]
    path.write_text(json.dumps({"generation": "Genesis 9", "vertices": verts, "facets": facets,
                                "weights": {"l_pectoral": pecs[: len(pecs) // 2], "r_pectoral": pecs[len(pecs) // 2:]}}))
    try:
        mesh = mg.Mesh.load(path)
        mesh.weights = {"l_pectoral": {i: 1.0 for i, v in enumerate(mesh.vertices) if v[0] > 1},
                        "r_pectoral": {i: 1.0 for i, v in enumerate(mesh.vertices) if v[0] < -1}}
        mesh.landmarks = mesh.find_landmarks()
        assert "bust_press_left" in mg.ALL_RECIPES and "bust_press_left" not in mg.RECIPES
        for side, sign in (("left", 1), ("right", -1)):
            d = mg.build_deltas(mesh, mg.CONTACT[f"bust_press_{side}"])
            deepest = min(d, key=lambda i: d[i][2])
            assert d[deepest][2] < -0.5
            assert mesh.vertices[deepest][0] * sign > 0
            top = max(math.dist((0, 0, 0), v) for v in d.values())
            assert top == pytest.approx(mg.PEAKS[f"bust_press_{side}"], rel=1e-3)
    finally:
        path.unlink(missing_ok=True)
