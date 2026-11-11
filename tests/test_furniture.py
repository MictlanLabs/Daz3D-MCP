"""Putting figures on furniture: prop_surfaces, place_on, fit_check and joint
limits, run against the fake Daz (whose figures have a tube "skin" around
each bone and whose props are made of boxes)."""

from __future__ import annotations

import json

import pytest

from daz3d_mcp.client import DazClient
from daz3d_mcp.settings import Settings

G9 = "People/Genesis 9/Genesis 9.duf"

# A chair facing its local +Z: seat top at 45 cm, backrest behind it.
CHAIR_BOXES = [
    [[-23, 40, -23], [23, 45, 23]],      # seat
    [[-23, 45, -27], [23, 92, -23]],     # backrest
    [[-23, 0, -23], [-19, 40, -19]],     # legs
    [[19, 0, -23], [23, 40, -19]],
    [[-23, 0, 19], [-19, 40, 23]],
    [[19, 0, 19], [23, 40, 23]],
]


@pytest.fixture
def client(bridge, content_library):
    c = DazClient(Settings(transport="http"))
    c.lib = content_library
    c.run_tool("content_load", {"path": (content_library / G9).as_posix(), "kind": "figure"})
    add_prop(bridge, "Chair", CHAIR_BOXES, position=[100, 0, 50], rotation=[0, 90, 0])
    return c


def add_prop(bridge, label, boxes, position, rotation):
    state = json.loads(bridge.state.read_text())
    node_id = state["nextId"]
    state["nextId"] = node_id + 1
    xs = [p for b in boxes for p in (b[0], b[1])]
    state["nodes"].append({"id": node_id, "class": "DzNode", "label": label, "name": label, "parent": None,
                           "position": position, "rotation": rotation, "mesh_boxes": boxes,
                           "bbox": [[position[0] - 30, 0, position[2] - 30], [position[0] + 30, max(p[1] for p in xs),
                                                                              position[2] + 30]]})
    bridge.state.write_text(json.dumps(state))


def sit(client):
    client.run_tool("pose_bones", {"figure": "Genesis 9", "bones": {
        "l_thigh": [-90, 0, 0], "r_thigh": [-90, 0, 0], "l_shin": [90, 0, 0], "r_shin": [90, 0, 0]}})


def test_prop_surfaces_finds_the_seat_and_its_front(client):
    res = client.run_tool("prop_surfaces", {"node": "Chair"})
    seat = res["surfaces"][0]
    assert seat["height"] == 45
    assert seat["size_cm"] == [46, 46]
    assert seat["center"] == [100, 45, 50]
    assert seat["facing_yaw"] == 90  # the chair is turned 90 degrees: it faces +X
    assert seat["front"] == [1, 0, 0]
    tops = {s["height"] for s in res["surfaces"]}
    assert 92 in tops  # the top of the backrest is a (small) surface too


def test_place_on_seat(client):
    sit(client)
    knees = client.run_tool("anim_sample", {"figure": "Genesis 9", "frames": [0], "bones": ["l_shin", "l_foot"]})
    knee, ankle = knees["frames"]["0"]["bones"]["l_shin"], knees["frames"]["0"]["bones"]["l_foot"]
    assert knee[2] > 30 and ankle[1] < knee[1] - 30  # thighs forward, shins down: sitting

    res = client.run_tool("place_on", {"figure": "Genesis 9", "prop": "Chair"})
    assert res["transform"]["rotation"][1] == 90
    assert res["gap_to_backrest_cm"] == pytest.approx(1, abs=0.6)
    fit = res["fit"]
    assert not fit["overlapping"] and fit["hints"] == []
    assert fit["parts"]["pelvis"]["max_depth_cm"] == 0.5  # the sink
    assert {"pelvis", "left_thigh", "right_thigh"} <= set(fit["touching"])
    for name, part in fit["parts"].items():  # nothing goes into the backrest or the seat front
        assert part.get("max_depth_cm", 0) <= 1, (name, part)

    low = client.run_tool("figure_info", {"figure": "Genesis 9", "landmarks": True})["lowest_points"]
    assert low["pelvis"][1] == pytest.approx(44.5, abs=0.3)  # sunk 0.5 cm into the seat
    assert low["pelvis"][0] < 100  # behind the seat center, toward the backrest (the chair faces +X)


def test_fit_check_reports_sinking_and_floating(client):
    sit(client)
    client.run_tool("place_on", {"figure": "Genesis 9", "prop": "Chair", "check": False})
    client.run_tool("node_set", {"node": "Genesis 9", "position": [0, -3, 0], "relative": True})
    fit = client.run_tool("fit_check", {"figure": "Genesis 9", "against": ["Chair"]})
    assert fit["overlapping"]
    assert fit["parts"]["pelvis"]["way_out"] == "up"
    sunk = max(p["max_depth_cm"] for p in fit["parts"].values() if p.get("way_out") == "up")
    assert sunk == pytest.approx(3.5, abs=0.3)  # 3 cm down + the 0.5 cm sink
    assert "raise the figure" in fit["hints"][0]

    client.run_tool("node_set", {"node": "Genesis 9", "position": [0, 7, 0], "relative": True})
    fit = client.run_tool("fit_check", {"figure": "Genesis 9", "against": ["Chair"], "floor_y": 0})
    assert not fit["overlapping"]
    assert fit["parts"]["pelvis"]["gap_below_cm"] == pytest.approx(3.5, abs=0.6)
    assert fit["feet"]["left_foot"]["above_floor_cm"] > 0


def test_fit_check_default_against_and_side_overlap(client):
    sit(client)
    client.run_tool("place_on", {"figure": "Genesis 9", "prop": "Chair", "check": False})
    # push the figure back into the backrest
    client.run_tool("node_set", {"node": "Genesis 9", "position": [-5, 0, 0], "relative": True})
    fit = client.run_tool("fit_check", {"figure": "Genesis 9"})
    assert [a["node"] for a in fit["against"]] == ["Chair"]
    ways = {p.get("way_out") for p in fit["parts"].values() if p.get("max_depth_cm")}
    assert "forward" in ways


def test_place_on_without_a_surface(client, bridge):
    add_prop(bridge, "Pole", [[[-2, 0, -2], [2, 200, 2]]], position=[-100, 0, 0], rotation=[0, 0, 0])
    from daz3d_mcp.transport import DazError
    with pytest.raises(DazError, match="No surface"):
        client.run_tool("place_on", {"figure": "Genesis 9", "prop": "Pole"})


def test_joint_limits(client):
    res = client.run_tool("pose_bones", {"figure": "Genesis 9", "bones": {"spine1": [0, 30, 0]}})
    assert res["set"][0]["rotation"] == [0, 15, 0]
    assert res["clamped"] == [{"bone": "spine1", "axis": "Y", "asked": 30, "got": 15, "limits": [-15, 15]}]
    assert "ignore_limits" in res["limits_hint"]
    info = client.run_tool("figure_info", {"figure": "Genesis 9", "limits": ["spine1", "head"]})
    assert info["limits"]["spine1"] == {"x": None, "y": [-15, 15], "z": [-15, 15], "now": [0, 15, 0]}
    assert info["limits"]["head"]["y"] is None
    res = client.run_tool("pose_bones", {"figure": "Genesis 9", "bones": {"spine1": [0, 30, 0]},
                                         "ignore_limits": True})
    assert res["set"][0]["rotation"] == [0, 30, 0] and "clamped" not in res
