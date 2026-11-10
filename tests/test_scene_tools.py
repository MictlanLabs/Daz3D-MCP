"""Stage 2 DazScript tools, run through the client against the fake Daz."""

from __future__ import annotations

import json

import pytest

from daz3d_mcp.client import DazClient
from daz3d_mcp.settings import Settings
from daz3d_mcp.transport import DazError

G9 = "People/Genesis 9/Genesis 9.duf"


@pytest.fixture
def client(bridge, content_library):
    c = DazClient(Settings(transport="http"))
    c.lib = content_library
    return c


def load(client, rel, kind, target=None):
    args = {"path": (client.lib / rel).as_posix(), "kind": kind}
    if target:
        args["target"] = target
    return client.run_tool("content_load", args)


def fake_state(bridge) -> dict:
    return json.loads(bridge.state.read_text())


def test_content_libraries(client):
    libs = client.run_tool("content_libraries")["libraries"]
    assert libs == [{"path": str(client.lib), "kind": "daz"}]


def test_load_figures_dress_and_pose(client):
    first = load(client, G9, "figure")
    assert first["added"] == [{"label": "Genesis 9", "type": "figure", "generation": "Genesis 9"}]
    second = load(client, G9, "figure")
    assert second["added"][0]["label"] == "Genesis 9 (2)"  # Daz numbers duplicate labels

    shirt = load(client, "People/Genesis 9/Clothing/Basic Wear/Basic Wear Shirt.duf", "clothing", "Genesis 9 (2)")
    assert shirt["added"] == [{"label": "Basic Wear Shirt", "type": "fitted_figure",
                               "fitted_to": "Genesis 9 (2)", "kind": "clothing"}]
    hair = load(client, "People/Genesis 9/Hair/Short Bob Hair.duf", "hair", "Genesis 9 (2)")
    assert hair["added"][0]["kind"] == "hair"

    # A pose aimed at the shirt goes to the figure wearing it.
    pose = load(client, "People/Genesis 9/Poses/Waving.duf", "pose", "Basic Wear Shirt")
    assert pose["target"] == "Genesis 9 (2)"

    info = client.run_tool("figure_info", {"figure": "Genesis 9 (2)"})
    assert info["generation"] == "Genesis 9"
    assert info["height_cm"] == 182  # the hair sticks out above the head
    assert {w["label"]: w["kind"] for w in info["wearing"]} == {"Basic Wear Shirt": "clothing", "Short Bob Hair": "hair"}
    assert {b["bone"] for b in info["posed_bones"]} == {"r_upperarm", "r_forearm", "head"}
    assert "Body" in info["surfaces"]

    untouched = client.run_tool("figure_info", {"figure": "Genesis 9"})
    assert untouched["wearing"] == [] and untouched["posed_bones"] == []


def test_presets_need_a_target(client):
    with pytest.raises(DazError) as err:
        load(client, "People/Genesis 9/Poses/Waving.duf", "pose")
    assert err.value.code == "bad_args" and "target" in err.value.message
    load(client, "Props/Furniture/Wooden Chair.duf", "prop")
    with pytest.raises(DazError) as err:
        load(client, "People/Genesis 9/Poses/Waving.duf", "pose", "Wooden Chair")
    assert "applies to a figure" in err.value.message
    with pytest.raises(DazError) as err:
        load(client, "People/Genesis 9/Poses/Waving.duf", "pose", "Nobody")
    assert err.value.code == "not_found"


def test_figure_load_does_not_fit_to_selection(client):
    load(client, G9, "figure")
    client.run_tool("node_set", {"node": "Genesis 9", "select": True})
    load(client, "Props/Furniture/Wooden Chair.duf", "prop")
    chair = [n for n in client.run_tool("scene_info")["nodes"] if n["label"] == "Wooden Chair"][0]
    assert chair["parent"] is None


def test_wrong_generation_warns_and_fit(client):
    load(client, G9, "figure")
    res = load(client, "People/Genesis 8 Female/Clothing/Old Jacket.duf", "clothing", "Genesis 9")
    assert "warning" in res and res["added"][0]["type"] == "figure"
    fit = client.run_tool("wearable_fit", {"item": "Old Jacket", "figure": "Genesis 9"})
    assert fit["fitted_to"] == "Genesis 9"
    assert client.run_tool("wearable_fit", {"item": "Old Jacket"})["fitted_to"] is None


def test_node_set_and_delete(client):
    load(client, G9, "figure")
    load(client, "People/Genesis 9/Clothing/Basic Wear/Basic Wear Pants.duf", "clothing", "Genesis 9")
    res = client.run_tool("node_set", {"node": "Genesis 9", "position": [-60, 10, 0], "rotation": [0, 20, 0],
                                       "label": "Ana"})
    assert res["label"] == "Ana" and res["position"] == [-60, 10, 0] and res["rotation"] == [0, 20, 0]
    res = client.run_tool("node_set", {"node": "Ana", "position": [5, 0, 0], "relative": True, "drop_to_floor": True})
    assert res["position"] == [-55, 0, 0]
    assert client.run_tool("node_set", {"node": "Ana", "scale": 0.5})["bbox_ws"]["max"][1] == 89
    with pytest.raises(DazError) as err:
        client.run_tool("node_set", {"node": "ana", "position": [0, 0]})
    assert err.value.code == "bad_args"

    deleted = client.run_tool("node_delete", {"nodes": ["Ana"]})
    assert set(deleted["deleted"]) == {"Ana", "Basic Wear Pants"}
    assert deleted["node_count"] == 0  # bones went with the figure


def test_morphs(client):
    load(client, G9, "figure")
    load(client, "People/Genesis 9/Characters/Leo 9.duf", "character", "Genesis 9")
    used = client.run_tool("morph_list", {"node": "Genesis 9", "only_nonzero": True})
    assert {m["label"] for m in used["morphs"]} == {"Leo 9 Body", "Leo 9 Head"}
    assert all(m["label"] != "pJCM Shoulder Down" for m in client.run_tool("morph_list", {"node": "Genesis 9"})["morphs"])
    found = client.run_tool("morph_list", {"node": "Genesis 9", "query": "proportion"})
    assert [m["label"] for m in found["morphs"]] == ["Height"]

    res = client.run_tool("morph_set", {"node": "Genesis 9", "values": {"Body Tone": 0.6, "body_ctrl_Height": 3,
                                                                        "Body": 1}})
    assert {s["morph"]: s["value"] for s in res["set"]} == {"Body Tone": 0.6, "Height": 1}  # clamped to the max
    assert res["not_found"][0]["morph"] == "Body"
    assert "Body Tone" in res["not_found"][0]["similar"]


def test_pose_bones_and_reset(client):
    load(client, G9, "figure")
    res = client.run_tool("pose_bones", {"figure": "Genesis 9", "bones": {"Left Upper Arm": [0, 0, -45],
                                                                          "head": [0, 15, 0], "tail": [1, 1, 1]}})
    assert {s["bone"] for s in res["set"]} == {"l_upperarm", "head"}
    assert res["not_found"] == ["tail"] and "all_bones" in res["hint"]
    client.run_tool("pose_bones", {"figure": "Genesis 9", "bones": {"head": [0, 5, 0]}, "relative": True})
    info = client.run_tool("figure_info", {"figure": "Genesis 9", "all_bones": True})
    assert {b["bone"]: b["rotation"] for b in info["posed_bones"]}["head"] == [0, 20, 0]
    assert len(info["bones"]) == 22
    reset = client.run_tool("pose_reset", {"figure": "Genesis 9"})
    assert reset["values_reset"] == 2
    assert client.run_tool("figure_info", {"figure": "Genesis 9"})["posed_bones"] == []


def test_materials(client, tmp_path):
    load(client, G9, "figure")
    load(client, "People/Genesis 9/Clothing/Basic Wear/Basic Wear Shirt.duf", "clothing", "Genesis 9")
    shirt = client.run_tool("material_list", {"node": "Basic Wear Shirt"})["surfaces"]
    assert shirt[0]["surface"] == "Shirt" and shirt[0]["shader"] == "Iray Uber"
    assert {p["label"] for p in shirt[0]["properties"]} >= {"Base Color", "Glossy Roughness"}

    load(client, "People/Genesis 9/Materials/Basic Wear Shirt Red.duf", "material", "Basic Wear Shirt")
    color = client.run_tool("material_list", {"node": "Basic Wear Shirt", "query": "base"})["surfaces"][0]
    assert color["properties"][0]["value"] == [0.702, 0.102, 0.102]

    tex = tmp_path / "denim.png"
    tex.write_bytes(b"png")
    res = client.run_tool("material_set", {"node": "Basic Wear Shirt", "properties": {
        "Base Color": "#204080", "Glossy Roughness": 0.25, "Normal Map": 1, }})
    assert res["not_found_anywhere"] == ["Normal Map"] and "hint" in res
    res = client.run_tool("material_set", {"node": "Genesis 9", "surfaces": ["Body", "arms"],
                                           "properties": {"Base Color": {"map": tex.as_posix(), "value": [1, 1, 1]}}})
    assert [c["surface"] for c in res["changed"]] == ["Body", "Arms"]
    assert res["changed"][0]["set"][0]["map"] == tex.as_posix()
    with pytest.raises(DazError) as err:
        client.run_tool("material_set", {"node": "Genesis 9", "surfaces": ["Tail"], "properties": {"x": 1}})
    assert "Head" in json.dumps(err.value.details)
    with pytest.raises(DazError):
        client.run_tool("material_set", {"node": "Genesis 9", "properties": {"Glossy Roughness": "shiny"}})


def test_camera_frames_two_figures(client, bridge):
    load(client, G9, "figure")
    load(client, G9, "figure")
    client.run_tool("node_set", {"node": "Genesis 9", "position": [-50, 0, 0]})
    client.run_tool("node_set", {"node": "Genesis 9 (2)", "position": [50, 0, 0]})
    cam = client.run_tool("camera_create", {"label": "Shot", "frame": ["Genesis 9", "Genesis 9 (2)"],
                                            "focal_length": 50, "yaw": 20})
    assert cam["active"] is True and cam["focal_length"] == 50
    assert cam["looking_at"] == [0, 89, 1.5]
    assert cam["position"][2] > 300 and cam["position"][0] > 0  # in front, a bit to their left
    client.run_tool("render", {"out_path": (bridge.home / "r.png").as_posix()})
    figures = fake_state(bridge)["renders"][-1]["figures"]
    assert [f["corners_in_frame"] for f in figures] == [8, 8]

    tight = client.run_tool("camera_set", {"camera": "Shot", "focal_length": 200})
    assert tight["active"] is True  # still the viewport camera
    client.run_tool("render", {"out_path": (bridge.home / "r2.png").as_posix()})
    assert fake_state(bridge)["renders"][-1]["figures"][0]["corners_in_frame"] < 8

    aimed = client.run_tool("camera_set", {"camera": "Shot", "position": [0, 160, 400], "look_at": [0, 160, 0],
                                           "label": "Front"})
    assert aimed["rotation"] == [0, 0, 0] and aimed["label"] == "Front"
    side = client.run_tool("camera_set", {"camera": "Front", "position": [400, 100, 0], "look_at": [0, 100, 0]})
    assert side["rotation"] == [0, 90, 0]
    with pytest.raises(DazError):
        client.run_tool("camera_set", {"camera": "Genesis 9"})


def test_lights_and_environment(client):
    load(client, G9, "figure")
    key = client.run_tool("light_create", {"type": "spot", "label": "Key", "position": [200, 250, 200],
                                           "look_at": "Genesis 9", "power": 4000, "color": "#fff0e0",
                                           "spread_angle": 35})
    assert key["class"] == "DzSpotLight" and key["not_found"] == []
    assert {s["label"]: s["value"] for s in key["set"]}["Luminous Flux (Lumen)"] == 4000
    sun = client.run_tool("light_create", {"type": "distant", "rotation": [-40, 30, 0], "power": 2})
    assert sun["label"] == "Distant Light" and sun["set"][0]["label"] == "Intensity"
    assert sun["rotation"] == [-40, 30, 0]
    off = client.run_tool("light_set", {"light": "Key", "on": False})
    assert off["set"][-1]["value"] == "Off"
    assert any(n["type"] == "light" for n in client.run_tool("scene_info")["nodes"])
    with pytest.raises(DazError):
        client.run_tool("light_set", {"light": "Genesis 9", "power": 1})

    env = client.run_tool("environment_set", {"mode": "scene_only", "intensity": 0.5, "draw_dome": False})
    assert env["environment"]["mode"] == "Scene Only" and env["environment"]["draw_dome"] is False
    with pytest.raises(DazError):
        client.run_tool("environment_set", {"mode": "sunny"})


def test_light_preset_adds_lights(client):
    res = load(client, "Light Presets/Studio/Three Point Lights.duf", "light")
    assert [a["label"] for a in res["added"]] == ["Key", "Fill", "Rim"]
    assert {a["type"] for a in res["added"]} == {"light"}


def test_render_settings_and_render(client, bridge, tmp_path):
    s = client.run_tool("render_settings", {"width": 1280, "height": 720, "max_samples": 200, "max_time": 60})
    assert s["renderer"] == "NVIDIA Iray"
    assert (s["width"], s["height"], s["max_samples"], s["max_time"]) == (1280, 720, 200, 60)
    assert client.run_tool("render_settings", {"width": 640})["height"] == 360  # keeps the aspect

    client.run_tool("camera_create", {"label": "Cam", "position": [0, 150, 300], "look_at": [0, 100, 0]})
    out = tmp_path / "shot.png"
    res = client.run_tool("render", {"out_path": out.as_posix(), "preview_path": (tmp_path / "p.png").as_posix(),
                                     "preview_size": 256, "max_time": 30})
    assert res["path"] == out.as_posix() and out.is_file()
    assert res["preview"] and res["camera"] == "Cam" and res["settings"]["max_time"] == 30
    with pytest.raises(DazError) as err:
        client.run_tool("render", {"out_path": (tmp_path / "nope" / "x.png").as_posix()})
    assert err.value.code == "not_found"
