"""Stage 3 DazScript tools against the fake Daz: libraries, OBJ/FBX import,
Transfer Utility and clothing adjustments."""

from __future__ import annotations

import json

import pytest

from asset_fixture import write_cape_fbx, write_fbx, box_vertices, write_obj
from daz3d_mcp.client import DazClient
from daz3d_mcp.settings import Settings
from daz3d_mcp.transport import DazError

G9 = "People/Genesis 9/Genesis 9.duf"


@pytest.fixture
def client(bridge, content_library):
    c = DazClient(Settings(transport="http"))
    c.lib = content_library
    return c


def state(bridge) -> dict:
    return json.loads(bridge.state.read_text())


def g9(client, label="Ana"):
    added = client.run_tool("content_load", {"path": (client.lib / G9).as_posix(), "kind": "figure"})["added"][0]
    client.run_tool("node_set", {"node": added["label"], "label": label})
    return label


def test_add_library(client, tmp_path):
    lib = tmp_path / "Third Party Library"
    lib.mkdir()
    res = client.run_tool("content_add_library", {"path": lib.as_posix()})
    assert res["added"] is True
    assert [d["path"] for d in res["libraries"]] == [str(client.lib), lib.as_posix()]
    again = client.run_tool("content_add_library", {"path": lib.as_posix() + "/"})
    assert again["added"] is False
    with pytest.raises(DazError) as err:
        client.run_tool("content_add_library", {"path": (tmp_path / "missing").as_posix()})
    assert err.value.code == "not_found"


def test_import_obj_silently_with_scale(client, bridge, tmp_path):
    obj = write_obj(tmp_path / "Table.obj", [-0.9, 0, -0.5], [0.9, 0.78, 0.5], materials=("Wood", "Metal"))
    res = client.run_tool("import_mesh", {"path": obj.as_posix(), "format": "obj", "scale_cm": 100,
                                          "label": "Tavern Table", "position": [120, 0, 0], "drop_to_floor": True})
    assert res["label"] == "Tavern Table" and res["type"] == "prop"
    assert res["bbox"]["size"] == [180, 78, 100]
    assert res["bbox"]["min"][1] == 0
    assert res["surfaces"] == ["Wood", "Metal"]
    opts = state(bridge)["imports"][-1]["options"]
    # Our settings replace the importer defaults (Poser preset, 243.84 scale) and keep it silent.
    assert opts["RunSilent"] == 1 and opts["Scale"] == 100 and opts["Preset"] == "Custom"
    assert opts["IncludeMtllib"] is True


def test_import_z_up_obj_and_height(client, tmp_path):
    obj = write_obj(tmp_path / "Statue.obj", [-20, -20, 0], [20, 20, 150], mtl=False)
    res = client.run_tool("import_mesh", {"path": obj.as_posix(), "scale_cm": 1, "up_axis": "Z", "height": 75})
    assert res["bbox"]["size"][1] == 75
    assert res["scale"] == 0.5


def test_import_fbx_and_bad_units_warning(client, tmp_path):
    cape = write_cape_fbx(tmp_path)
    res = client.run_tool("import_mesh", {"path": cape.as_posix()})
    assert res["label"] == "Hero Cape" and res["bbox"]["size"] == [64, 97, 16]
    tiny = write_fbx(tmp_path / "Ring.fbx", box_vertices([0, 0, 0], [0.01, 0.01, 0.002]))
    res = client.run_tool("import_mesh", {"path": tiny.as_posix()})
    assert any("units are probably wrong" in w for w in res["warnings"])


def test_rigged_fbx_imports_as_figure(client, tmp_path):
    f = write_fbx(tmp_path / "Robot.fbx", box_vertices([-30, 0, -20], [30, 170, 20]), bones=("Hips", "Spine"))
    res = client.run_tool("import_mesh", {"path": f.as_posix()})
    assert res["type"] == "figure" and res["bones"] == 2 and "wearable_from_mesh" in res["note"]


def test_mesh_to_clothing(client, bridge, tmp_path):
    g9(client)
    cape = write_cape_fbx(tmp_path)
    client.run_tool("import_mesh", {"path": cape.as_posix(), "label": "Cape"})

    res = client.run_tool("wearable_from_mesh", {"item": "Cape", "figure": "Ana"})
    assert res["fitted_to"] == "Ana" and res["type"] == "fitted_figure"
    assert res["bones"] == 22 and res["morphs"] > 0 and res["smoothing"] is True
    t = state(bridge)["transfers"][-1]
    assert t["content_type"] == "Follower/Wardrobe" and t["morphs"] is True and t["base"] == "base"
    labels = [n["label"] for n in client.run_tool("scene_info")["nodes"]]
    assert labels.count("Cape") == 1  # the loose mesh was replaced

    info = client.run_tool("figure_info", {"figure": "Ana"})
    assert [w["label"] for w in info["wearing"]] == ["Cape"]

    # It follows the figure now.
    client.run_tool("node_set", {"node": "Ana", "position": [100, 0, 0]})
    box = client.run_tool("node_set", {"node": "Cape"})["bbox_ws"]
    assert box["min"][0] == 68


def test_mesh_to_clothing_checks(client, tmp_path):
    g9(client)
    cape = write_cape_fbx(tmp_path)
    client.run_tool("import_mesh", {"path": cape.as_posix(), "label": "Cape", "position": [300, 0, 0]})
    with pytest.raises(DazError) as err:
        client.run_tool("wearable_from_mesh", {"item": "Cape", "figure": "Ana"})
    assert err.value.code == "not_on_figure"

    client.run_tool("node_set", {"node": "Cape", "position": [0, 0, 0]})
    client.run_tool("content_load", {"path": (client.lib / "People/Genesis 9/Poses/Waving.duf").as_posix(),
                                     "kind": "pose", "target": "Ana"})
    with pytest.raises(DazError) as err:
        client.run_tool("wearable_from_mesh", {"item": "Cape", "figure": "Ana"})
    assert err.value.code == "figure_posed" and "pose_reset" in err.value.message

    with pytest.raises(DazError) as err:
        client.run_tool("wearable_from_mesh", {"item": "Cape", "figure": "Cape"})
    assert err.value.code == "bad_args"


def test_wearable_adjust(client, tmp_path):
    g9(client)
    client.run_tool("import_mesh", {"path": write_cape_fbx(tmp_path).as_posix(), "label": "Cape"})
    client.run_tool("wearable_from_mesh", {"item": "Cape", "figure": "Ana"})
    now = client.run_tool("wearable_adjust", {"item": "Cape"})
    assert now["collide_with"] == "Ana" and now["collision_iterations"] == 1
    res = client.run_tool("wearable_adjust", {"item": "Cape", "collision_iterations": 5, "smoothing_iterations": 4})
    assert res["collision_iterations"] == 5 and res["smoothing_iterations"] == 4 and res["not_found"] == []

    client.run_tool("content_load", {"path": (client.lib / "People/Genesis 9/Clothing/Basic Wear/Basic Wear Shirt.duf")
                                     .as_posix(), "kind": "clothing", "target": "Ana"})
    plain = client.run_tool("wearable_adjust", {"item": "Basic Wear Shirt", "collision_iterations": 3})
    assert "no mesh smoothing" in plain["hint"]


def test_parent_prop_to_hand(client, tmp_path):
    g9(client)
    obj = write_obj(tmp_path / "Sword.obj", [-2, 0, -1], [2, 90, 1], mtl=False)
    client.run_tool("import_mesh", {"path": obj.as_posix(), "label": "Sword", "position": [50, 100, 0]})
    res = client.run_tool("node_set", {"node": "Sword", "parent": "Ana", "parent_bone": "r_hand"})
    assert res["parent"] == "Right Hand"
    assert res["position_ws"] == [50, 100, 0]  # kept its place
    res = client.run_tool("node_set", {"node": "Sword", "parent": ""})
    assert res["parent"] is None and res["position_ws"] == [50, 100, 0]
    with pytest.raises(DazError):
        client.run_tool("node_set", {"node": "Sword", "parent": "Ana", "parent_bone": "tail"})
