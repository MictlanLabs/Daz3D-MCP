"""Faces: face_expression, eyes_look_at, eye_color and the figure-node face
controls in morph_list/morph_set, run against the fake Daz. The fake Genesis 9
gets face dials, eye bones and Genesis 9 Eyes (a layered eye image) here."""

from __future__ import annotations

import json
import math

import pytest

from daz3d_mcp.client import DazClient
from daz3d_mcp.settings import Settings
from daz3d_mcp.transport import DazError

G9 = "People/Genesis 9/Genesis 9.duf"
SPLIT = "Runtime/Textures/DAZ/Characters/Genesis9/Base/Eyes/Split"

FACE_CONTROLS = {
    # label: (name, group, default)
    "Eye Blink": ("facs_ctrl_EyeBlink", "/Pose Controls/Head/Eyes", 0),
    "Cheek Squint": ("facs_ctrl_CheekSquint", "/Pose Controls/Head/Cheek and Jaw", 0),
    "Eye Squint": ("facs_ctrl_EyeSquint", "/Pose Controls/Head/Eyes", 0),
    "Brow Up": ("facs_ctrl_BrowUp", "/Pose Controls/Head/Brow", 0),
    "Eye Look Side-Side": ("facs_ctrl_EyeLookSide-Side", "/Pose Controls/Head/Eyes", 0),
    "Mouth Sticky Power": ("facs_ctrl_MouthStickyPower", "/Pose Controls/Head/Mouth/Adjustments", 1),
    "Neck-Head Twist": ("body_ctrl_NeckHeadTwist", "/Pose Controls/Neck", 0),
}


@pytest.fixture
def client(bridge, content_library):
    c = DazClient(Settings(transport="http"))
    c.run_tool("content_load", {"path": (content_library / G9).as_posix(), "kind": "figure"})
    split = content_library / SPLIT
    split.mkdir(parents=True)
    for n in ("03", "15"):
        (split / f"Genesis9_Eyes_Iris_{n}.png").write_bytes(b"png")
    add_face(bridge)
    return c


def add_face(bridge):
    state = json.loads(bridge.state.read_text())
    fig = next(n for n in state["nodes"] if n["label"] == "Genesis 9")
    head = next(n for n in state["nodes"] if n.get("name") == "head" and n.get("skel") == fig["id"])
    fig["props"] = {label: {"type": "float", "name": name, "group": group, "value": d, "def": d,
                            "min": -1 if "Side" in label or "Twist" in label else 0, "max": 1}
                    for label, (name, group, d) in FACE_CONTROLS.items()}
    fig["morphs"].append({"name": "facs_ctrl_MouthSmile", "label": "Mouth Smile",
                          "group": "/Pose Controls/Head/Mouth", "value": 0, "min": 0, "max": 1})

    def node(**d):
        d["id"] = state["nextId"]
        state["nextId"] += 1
        state["nodes"].append(d)
        return d

    for side, x in (("l", 3.2), ("r", -3.2)):
        node(**{"class": "DzBone", "name": f"{side}_eye", "label": f"{side} eye", "parent": head["id"],
                "skel": fig["id"], "position": [0, 0, 0], "rotation": [0, 0, 0], "origin": [x, 168, 8],
                "end": [x, 168, 10], "order": "ZXY", "limits": [[-30, 30], [-30, 40], None]})
    state["layered"] = {"G9 Eye Color": {"size": [4096, 4096], "layers": [
        {"label": "Base", "imageFile": "", "color": [255, 255, 255], "blendMode": 0, "opacity": 1},
        {"label": "Sclera", "imageFile": "/lib/Sclera_01.jpg", "color": [0, 0, 0], "blendMode": 0, "opacity": 1},
        {"label": "Iris", "imageFile": "/lib/Genesis9_Eyes_Iris_09.png", "color": [0, 0, 0], "blendMode": 0,
         "opacity": 1}]}}
    eye_props = lambda: {"Base Color": {"type": "color", "value": [1, 1, 1], "mappable": True,  # noqa: E731
                                        "map": "layered://G9 Eye Color"}}
    node(**{"class": "DzFigure", "name": "Genesis9Eyes", "label": "Genesis 9 Eyes", "parent": fig["id"],
            "fitted_to": fig["id"], "geometry": True, "position": [0, 0, 0], "rotation": [0, 0, 0],
            "materials": [{"name": "Eye Left", "label": "Eye Left", "shader": "PBRSkin", "props": eye_props()},
                          {"name": "Eye Right", "label": "Eye Right", "shader": "PBRSkin", "props": eye_props()}]})
    node(**{"class": "DzBasicCamera", "label": "Cam", "name": "Cam", "parent": None,
            "position": [30, 168, 100], "rotation": [0, 0, 0]})
    bridge.state.write_text(json.dumps(state))


def dials(client, query):
    return {m["label"]: m for m in client.run_tool("morph_list", {"node": "Genesis 9", "query": query,
                                                                  "include_hidden": True})["morphs"]}


def test_morph_tools_see_face_controls(client):
    found = dials(client, "pose controls head")
    assert found["Eye Blink"]["control"] is True and "control" not in found["Mouth Smile"]
    res = client.run_tool("morph_set", {"node": "Genesis 9", "values": {"Eye Blink": 1}})
    assert res["set"] == [{"morph": "Eye Blink", "value": 1}]
    used = client.run_tool("figure_info", {"figure": "Genesis 9"})["morphs_in_use"]
    names = {m["name"] for m in used}
    assert "facs_ctrl_EyeBlink" in names
    assert "facs_ctrl_MouthStickyPower" not in names  # at its default of 1


def test_face_expression_clears_the_face_but_not_the_pose(client):
    client.run_tool("morph_set", {"node": "Genesis 9", "values": {"Eye Blink": 1, "Neck-Head Twist": 0.5,
                                                                 "Mouth Sticky Power": 0.2}})
    res = client.run_tool("face_expression", {"figure": "Genesis 9", "expression": "smile"})
    assert {s["dial"]: s["value"] for s in res["set"]} == {"Mouth Smile": 0.8, "Cheek Squint": 0.35,
                                                          "Eye Squint": 0.15}
    after = dials(client, "")
    assert after["Eye Blink"]["value"] == 0
    assert after["Mouth Sticky Power"]["value"] == 1      # back to its default
    assert after["Neck-Head Twist"]["value"] == 0.5       # a pose dial: kept

    res = client.run_tool("face_expression", {"figure": "Genesis 9", "expression": "surprised", "strength": 0.5,
                                              "values": {"Eye Blink": 0.2, "Nope": 1}})
    assert {"dial": "Brow Up", "name": "facs_ctrl_BrowUp", "value": 0.5} in res["set"]
    assert "eye_wide" in res["missing"] and res["not_found"] == ["Nope"]
    assert dials(client, "smile")["Mouth Smile"]["value"] == 0

    with pytest.raises(DazError, match="Unknown expression"):
        client.run_tool("face_expression", {"figure": "Genesis 9", "expression": "grumpy"})


def test_eyes_look_at_a_camera(client):
    client.run_tool("morph_set", {"node": "Genesis 9", "values": {"Eye Look Side-Side": 0.4}})
    res = client.run_tool("eyes_look_at", {"figure": "Genesis 9", "target": "Cam"})
    assert dials(client, "look")["Eye Look Side-Side"]["value"] == 0
    left, right = res["eyes"]["left"], res["eyes"]["right"]
    assert left["off_by_deg"] < 0.1 and right["off_by_deg"] < 0.1
    assert left["rotation"][1] == pytest.approx(math.degrees(math.atan2(30 - 3.2, 92)), abs=0.1)
    assert right["rotation"][1] > left["rotation"][1]  # each eye aims on its own
    assert "limited" not in res

    res = client.run_tool("eyes_look_at", {"figure": "Genesis 9", "target": [300, 168, 20]})
    assert res["limited"] == ["left", "right"] and "head" in res["hint"]
    res = client.run_tool("eyes_look_at", {"figure": "Genesis 9", "target": [300, 168, 20], "head": 0.8})
    assert res["head"]["rotation"][1] > 30 and "limited" not in res


def test_eye_color(client, bridge):
    res = client.run_tool("eye_color", {"figure": "Genesis 9", "color": "#3a7bd5", "eyes": "left"})
    assert res["node"] == "Genesis 9 Eyes"
    assert res["changed"] == [{"surface": "Eye Left", "iris": "Genesis9_Eyes_Iris_03.png",
                               "tint": [0.227, 0.482, 0.835], "strength": 0.85}]
    state = json.loads(bridge.state.read_text())
    mine = state["layered"]["Genesis 9 Eye Left Iris (DazMcp)"]["layers"]
    assert [l["label"] for l in mine] == ["Base", "Sclera", "Iris", "Iris Tint"]
    assert mine[3]["blendMode"] == 15 and mine[3]["mask"]["imageFile"].endswith("Iris_03.png")
    assert state["layered"]["G9 Eye Color"]["layers"][2]["imageFile"].endswith("Iris_09.png")  # untouched

    # again on the same eye: edits its own copy, one tint layer only
    client.run_tool("eye_color", {"figure": "Genesis 9", "iris": 15, "eyes": "left"})
    state = json.loads(bridge.state.read_text())
    mine = state["layered"]["Genesis 9 Eye Left Iris (DazMcp)"]["layers"]
    assert [l["label"] for l in mine] == ["Base", "Sclera", "Iris"]
    assert mine[2]["imageFile"].endswith("Iris_15.png")

    with pytest.raises(DazError, match="Give a color"):
        client.run_tool("eye_color", {"figure": "Genesis 9"})
