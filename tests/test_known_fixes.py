"""The five known bugs fixed in 0.5.1, against the fake Daz (and, for packages,
without Daz): photometric lights, Iray exposure, the floor of a two-storey
building, walls behind a camera_shot, and packages that need another product."""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

import pytest

from daz3d_mcp import packages
from daz3d_mcp.client import DazClient
from daz3d_mcp.settings import Settings
from test_dialogue_scenes import G9, add_eyes


@pytest.fixture
def client(bridge, content_library):
    c = DazClient(Settings(transport="http"))
    c.lib = content_library
    return c


def state(bridge) -> dict:
    return json.loads(bridge.state.read_text())


# ------------------------------------------------------------- lights ---
def test_new_lights_are_photometric_so_lumens_count(client, bridge, tmp_path):
    spot = client.run_tool("light_create", {"type": "spot", "label": "Key", "position": [0, 200, 200],
                                            "power": 4000})
    point = client.run_tool("light_create", {"type": "point", "label": "Fill", "position": [100, 200, 0]})
    sun = client.run_tool("light_create", {"type": "distant", "label": "Sun", "power": 2})
    assert spot["photometric"] is True and point["photometric"] is True
    assert sun["photometric"] is False  # a distant light uses Intensity, not lumens
    nodes = {n["label"]: n for n in state(bridge)["nodes"]}
    assert nodes["Key"]["props"]["Render Emitter"]["value"] is False
    client.run_tool("render", {"out_path": (tmp_path / "lit.png").as_posix(), "max_samples": 1})
    assert state(bridge)["renders"][-1]["lumens"] == 4000 + 1500


def test_light_set_power_turns_photometric_mode_on(client, bridge):
    client.run_tool("light_create", {"type": "spot", "label": "Old"})
    # a light saved before the fix (or made in another tool) with the mode off
    s = state(bridge)
    next(n for n in s["nodes"] if n["label"] == "Old")["props"]["Photometric Mode"]["value"] = False
    bridge.state.write_text(json.dumps(s))
    res = client.run_tool("light_set", {"light": "Old", "power": 800})
    assert res["photometric"] is True and "Photometric Mode was off" in res["note"]
    again = client.run_tool("light_set", {"light": "Old", "power": 900})
    assert "note" not in again


# ----------------------------------------------------------- exposure ---
def test_exposure_value_changes_the_shutter_iray_uses(client, bridge, tmp_path):
    res = client.run_tool("render_settings", {"exposure": 7.5})
    # f/8, ISO 100: 2^7.5 / 64 = 2.83
    assert res["exposure"] == {"ev": 7.5, "shutter": pytest.approx(2.828, abs=0.001), "f_stop": 8, "iso": 100}
    client.run_tool("render", {"out_path": (tmp_path / "ev.png").as_posix(), "max_samples": 1})
    assert state(bridge)["renders"][-1]["ev"] == pytest.approx(7.5, abs=1e-6)
    # the same through properties, as callers did before
    res = client.run_tool("render_settings", {"properties": {"Exposure Value": 9}})
    assert res["exposure"]["shutter"] == pytest.approx(8, abs=0.001) and res["not_found"] == []


def test_shutter_f_stop_and_iso_keep_exposure_value_in_step(client):
    res = client.run_tool("render_settings", {"properties": {"Film ISO": 400, "Shutter Speed (1/x)": 30}})
    # 2^EV = 64 * 30 * 100 / 400 = 480
    assert res["exposure"]["ev"] == pytest.approx(8.91, abs=0.01)
    res = client.run_tool("render_settings", {"exposure": 10, "properties": {"F/Stop": 4}})
    assert res["exposure"]["f_stop"] == 4
    assert res["exposure"]["shutter"] == pytest.approx(2 ** 10 * 400 / (100 * 16), abs=0.01)


# -------------------------------------------------------------- floor ---
def write_building(path: Path) -> Path:
    """A two-storey building: ground floor top at 25, upper floor at 338, a flat
    roof at 661 that is bigger than both (eaves), and walls."""
    boxes = {
        "ground": ([-500, 5, -400], [500, 25, 400]),
        "upper": ([-500, 318, -400], [500, 338, 400]),
        "roof": ([-600, 641, -500], [600, 661, 500]),
        "wall_n": ([-500, 25, -410], [500, 641, -400]),
        "wall_s": ([-500, 25, 400], [500, 641, 410]),
    }
    lines = []
    for name, (mn, mx) in boxes.items():
        lines.append(f"g {name}")
        for x in (mn[0], mx[0]):
            for y in (mn[1], mx[1]):
                for z in (mn[2], mx[2]):
                    lines.append(f"v {x} {y} {z}")
    lines.append("usemtl Wood")
    path.write_text("\n".join(lines) + "\n")
    return path


def test_room_floor_is_the_ground_floor_not_the_roof(client, tmp_path):
    obj = write_building(tmp_path / "Saloon.obj")
    res = client.run_tool("import_mesh", {"path": obj.as_posix(), "scale_cm": 1, "drop_to_floor": True,
                                          "room": True})
    assert res["floor"]["was_at_y"] == 25
    assert res["floor"]["covered"] >= 0.5 and res["floor"]["levels"] == 3
    assert res["bbox"]["min"][1] == pytest.approx(-20, abs=0.01)  # its slab goes under Y = 0
    assert not any("Nothing was found over" in w for w in res["warnings"])


def test_open_set_without_ceiling_keeps_the_largest_surface(client, tmp_path):
    obj = tmp_path / "Stage.obj"
    lines = []
    for name, (mn, mx) in {"ground": ([-800, -50, -800], [800, -30, 800]),
                           "stage": ([-300, 0, -300], [300, 40, 300])}.items():
        lines.append(f"g {name}")
        lines += [f"v {x} {y} {z}" for x in (mn[0], mx[0]) for y in (mn[1], mx[1]) for z in (mn[2], mx[2])]
    obj.write_text("\n".join(lines) + "\n")
    res = client.run_tool("import_mesh", {"path": obj.as_posix(), "scale_cm": 1, "drop_to_floor": True,
                                          "room": True})
    assert res["floor"]["was_at_y"] == -30 and res["floor"]["covered"] == 0


# -------------------------------------------------------------- walls ---
def add_wall(bridge, z):
    s = state(bridge)
    node_id = s["nextId"]
    s["nextId"] += 1
    s["nodes"].append({"id": node_id, "class": "DzNode", "label": "Wall", "name": "Wall", "parent": None,
                       "position": [0, 0, 0], "rotation": [0, 0, 0],
                       "mesh_boxes": [[[-400, 0, z], [400, 300, z + 12]]],
                       "bbox": [[-400, 0, z], [400, 300, z + 12]]})
    bridge.state.write_text(json.dumps(s))


@pytest.fixture
def pair(client, bridge, content_library):
    for label, x, yaw in (("Ana", -50, 70), ("Beto", 50, -70)):
        client.run_tool("content_load", {"path": (content_library / G9).as_posix(), "kind": "figure"})
        client.run_tool("node_set", {"node": "Genesis 9", "label": label, "position": [x, 0, 0],
                                     "rotation": [0, yaw, 0]})
        add_eyes(bridge, label)
    client.run_tool("render_settings", {"width": 640, "height": 360})
    return client


def test_camera_shot_stays_in_front_of_a_wall(pair, bridge):
    free = pair.run_tool("camera_shot", {"subject": "Ana", "partner": "Beto", "shot": "close_up"})
    assert free["position"][2] > 72 and "wall_cm" not in free
    add_wall(bridge, 70)
    res = pair.run_tool("camera_shot", {"subject": "Ana", "partner": "Beto", "shot": "close_up"})
    assert res["wall"] == "Wall" and res["pulled_in_cm"] > 0
    assert res["position"][2] < 70 - 15  # in the room, clear of the wall
    # a shorter lens keeps the head the same size in the picture
    assert res["focal_length"] / res["distance_cm"] == pytest.approx(
        free["focal_length"] / free["distance_cm"], rel=0.03)
    off = pair.run_tool("camera_shot", {"subject": "Ana", "partner": "Beto", "shot": "close_up",
                                        "avoid_walls": False, "camera": "Off"})
    assert off["position"] == free["position"]


def test_two_shot_in_a_tight_room_warns_instead_of_a_fisheye(pair, bridge):
    add_wall(bridge, 50)
    res = pair.run_tool("camera_shot", {"subject": "Ana", "partner": "Beto", "shot": "two_shot"})
    assert res["focal_length"] == 14 and "too tight" in res["warning"]
    assert res["position"][2] < 50


# ----------------------------------------------------------- packages ---
G81F = "/data/DAZ%203D/Genesis%208/Female%208_1/Genesis8_1Female.dsf"


def build_addon_zip(path: Path) -> Path:
    preset = {"asset_info": {"type": "preset_shape"}, "scene": {"animations": [
        {"url": f"name://@selection#BL_Shape{i}:?value/value", "keys": [[0, 1 if i < 4 else 0]]} for i in range(9)
    ] + [{"url": "name://@selection#OwnMorph:?value/value", "keys": [[0, 1]]}],
        "modifiers": [{"url": f"{G81F}#Genesis8_1Female"}]}}
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Content/People/Genesis 8 Female/Shapes/Vendor/Pointy.duf", json.dumps(preset, indent=1))
        zf.writestr("Content/data/Vendor/Addon/Morphs/OwnMorph.dsf", '{"id": "OwnMorph"}')
    return path


def plan(path: Path, libs: list[Path]) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        return packages.missing_requirements(packages.plan_package(path, Path(tmp)), libs)


def test_package_needs_a_base_figure_and_a_morph_pack(tmp_path):
    z = build_addon_zip(tmp_path / "pointy.zip")
    lib = tmp_path / "lib"
    lib.mkdir()
    missing = plan(z, [lib])
    assert [p["product"] for p in missing] == ["Genesis 8.1 Female", "morphs named BL..."]
    assert missing[0]["base_figure"] is True and missing[0]["folder"] == "data/DAZ 3D/Genesis 8/Female 8_1"
    # only the dials set away from 0 count; the package's own morph is not missing
    assert missing[1]["missing_files"] == 4 and missing[1]["examples"] == ["BL_Shape0", "BL_Shape1", "BL_Shape2"]
    warnings = packages.requirement_warnings(missing)
    assert "Genesis 8.1 Female" in warnings[0] and "BL_Shape0" in warnings[1]


def test_installed_requirements_are_not_reported(tmp_path):
    z = build_addon_zip(tmp_path / "pointy.zip")
    lib = tmp_path / "lib"
    base = lib / "data/DAZ 3D/Genesis 8/Female 8_1/Genesis8_1Female.dsf"
    morphs = lib / "data/Miepe/Breastacular/Morphs"
    base.parent.mkdir(parents=True)
    morphs.mkdir(parents=True)
    base.write_text("{}")
    for i in range(4):
        (morphs / f"BL_Shape{i}.dsf").write_text("{}")
    assert plan(z, [lib]) == []


def test_package_install_reports_requirements(tmp_path):
    z = build_addon_zip(tmp_path / "pointy.zip")
    lib = tmp_path / "Third Party Library"
    res = packages.install(z, lib, libraries=[tmp_path / "My Library"])
    assert res["requires"][0]["product"] == "Genesis 8.1 Female"
    assert res["warnings"][0].startswith("Needs the base figure 'Genesis 8.1 Female'")


# ------------------------------------------------- review follow-ups ---
def test_exposure_past_the_shutter_limit_reports_what_renders(client):
    res = client.run_tool("render_settings", {"exposure": 25})
    # the fake's shutter stops at 1/100000 s: EV log2(64 * 100000) ~ 22.6, not 25
    assert res["exposure"]["shutter"] == 100000
    assert res["exposure"]["ev"] == pytest.approx(22.61, abs=0.01)


def test_no_photometric_note_when_properties_turn_it_off(client):
    client.run_tool("light_create", {"type": "spot", "label": "Key"})
    client.run_tool("light_set", {"light": "Key", "properties": {"Photometric Mode": False}})
    res = client.run_tool("light_set", {"light": "Key", "power": 900, "properties": {"Photometric Mode": False}})
    assert res["photometric"] is False and "note" not in res


def test_building_on_a_big_street_plane_still_finds_its_floor(client, tmp_path):
    obj = write_building(tmp_path / "Town.obj")
    text = obj.read_text()
    street = ["g street"] + [f"v {x} {y} {z}" for x in (-2000, 2000) for y in (-30, -10) for z in (-2000, 2000)]
    obj.write_text("\n".join(street) + "\n" + text)
    res = client.run_tool("import_mesh", {"path": obj.as_posix(), "scale_cm": 1, "drop_to_floor": True,
                                          "room": True})
    assert res["floor"]["was_at_y"] == 25


def test_props_held_by_a_figure_are_not_walls(pair, bridge):
    free = pair.run_tool("camera_shot", {"subject": "Ana", "partner": "Beto", "shot": "close_up"})
    add_wall(bridge, 70)
    s = state(bridge)
    wall = next(n for n in s["nodes"] if n["label"] == "Wall")
    wall["parent"] = next(n["id"] for n in s["nodes"] if n["label"] == "Beto")
    bridge.state.write_text(json.dumps(s))
    res = pair.run_tool("camera_shot", {"subject": "Ana", "partner": "Beto", "shot": "close_up"})
    assert "wall" not in res and res["position"] == free["position"]


def test_wall_right_at_the_face_warns_and_does_not_jump_past_it(pair, bridge):
    free = pair.run_tool("camera_shot", {"subject": "Ana", "partner": "Beto", "shot": "close_up"})
    add_wall(bridge, 8)
    res = pair.run_tool("camera_shot", {"subject": "Ana", "partner": "Beto", "shot": "close_up"})
    assert "no room for the camera" in res["warning"] and res["position"] == free["position"]


def test_tcb_keys_at_zero_are_not_counted_as_dials(tmp_path):
    preset = '{"scene": {"animations": [' + ",".join(
        f'{{"url": "name://@selection#BL_Shape{i}:?value/value", "keys": [[0, 0, ["TCB", 0, 0, 0]], '
        f'[0.0333, 0, ["TCB", 0, 0, 0]]]}}' for i in range(5)) + "]}}"
    z = tmp_path / "zeros.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("People/Genesis 8 Female/Poses/Vendor/Zero.duf", preset)
    lib = tmp_path / "lib"
    lib.mkdir()
    assert plan(z, [lib]) == []


def test_ground_under_the_floor_boards_is_not_the_floor(client, tmp_path):
    # the real Wild West Saloon has ground under its boards and a smaller back
    # room 22 cm lower, both under the roof
    obj = write_building(tmp_path / "Saloon.obj")
    extra = []
    for name, (mn, mx) in {"under": ([-500, -15, -400], [500, 2, 400]),
                           "back_room": ([-500, -20, 410], [-100, 3, 500])}.items():
        extra.append(f"g {name}")
        extra += [f"v {x} {y} {z}" for x in (mn[0], mx[0]) for y in (mn[1], mx[1]) for z in (mn[2], mx[2])]
    obj.write_text("\n".join(extra) + "\n" + obj.read_text())
    res = client.run_tool("import_mesh", {"path": obj.as_posix(), "scale_cm": 1, "drop_to_floor": True,
                                          "room": True})
    assert res["floor"]["was_at_y"] == 25
