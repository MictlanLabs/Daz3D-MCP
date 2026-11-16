"""render_cull: leave out of the render what a camera cannot see, against the fake Daz.

The scenes are boxes. A camera 300 cm in front of a figure (on +Z, at chest
height, 50 mm lens, 16:9) frames it from the knees up: the picture spans about
Y 53..187 and X -118..118 at the figure."""

from __future__ import annotations

import json

import anyio
import pytest

from daz3d_mcp.client import DazClient
from daz3d_mcp.cull_tools import sample_frames
from daz3d_mcp.server import create_server
from daz3d_mcp.settings import Settings


def mats(*names, cutout=1.0, extra=None):
    out = []
    for n in names:
        props = {"Base Color": {"type": "color", "value": [0.7, 0.7, 0.7], "mappable": True, "map": None},
                 "Cutout Opacity": {"type": "float", "value": cutout, "min": 0, "max": 1, "mappable": True},
                 "Glossy Roughness": {"type": "float", "value": 0.6, "min": 0, "max": 1, "mappable": True}}
        props.update(extra or {})
        out.append({"name": n, "label": n, "props": json.loads(json.dumps(props))})
    return out


class Scene:
    def __init__(self, path):
        self.path = path
        self.nodes = []
        self.next = 1

    def add(self, label, boxes, cls="DzNode", position=(0, 0, 0), fitted_to=None, materials=None, **extra):
        d = {"id": self.next, "class": cls, "label": label, "name": label.replace(" ", "_"), "parent": None,
             "position": list(position), "rotation": [0, 0, 0], "geometry": True, "mesh_boxes": boxes,
             "bbox_local": [[min(b[0][i] for b in boxes) for i in range(3)],
                            [max(b[1][i] for b in boxes) for i in range(3)]],
             "materials": materials or mats("Surface")}
        if fitted_to:
            d["fitted_to"] = next(n["id"] for n in self.nodes if n["label"] == fitted_to)
        d.update(extra)
        self.nodes.append(d)
        self.next += 1
        return d

    def camera(self, label, position, rotation=(0, 0, 0), focal=89):   # 89 mm: Daz spreads the 36 mm frame over the height
        self.nodes.append({"id": self.next, "class": "DzBasicCamera", "label": label, "name": label,
                           "parent": None, "position": list(position), "rotation": list(rotation),
                           "props": {"Focal Length": {"type": "float", "value": focal, "min": 1, "max": 10000}}})
        self.next += 1

    def light(self, label, position, cls="DzPointLight"):
        self.nodes.append({"id": self.next, "class": cls, "label": label, "name": label, "parent": None,
                           "position": list(position), "rotation": [0, 0, 0]})
        self.next += 1

    def write(self):
        self.path.write_text(json.dumps({
            "filename": "", "modified": False, "frame": 0, "endFrame": 30, "nodes": self.nodes,
            "viewportCamera": "Cam", "nextId": self.next, "render": {"width": 1600, "height": 900},
        }))


def figure_scene(state, lace=False):
    s = Scene(state)
    s.add("Mia", [[[-20, 0, -10], [20, 175, 10]]], cls="DzFigure")
    s.add("Top", [[[-21, 100, -11], [21, 150, 11]]], cls="DzFigure", fitted_to="Mia")
    s.add("Skirt", [[[-25, 40, -14], [25, 100, 14]]], cls="DzFigure", fitted_to="Mia",
          materials=mats("Skirt", cutout=0.6 if lace else 1.0))
    s.add("Panties", [[[-18, 80, -11], [18, 92, 11]]], cls="DzFigure", fitted_to="Mia")
    s.add("Shoes", [[[-15, 0, -12], [15, 10, 15]]], cls="DzFigure", fitted_to="Mia")
    s.camera("Cam", [0, 120, 300])
    return s


@pytest.fixture
def client(bridge):
    return DazClient(Settings(transport="http"))


def state_nodes(bridge):
    return {n["label"]: n for n in json.loads(bridge.state.read_text())["nodes"]}


def off_in_render(bridge):
    return sorted(k for k, n in state_nodes(bridge).items() if n.get("render_visible") is False)


def cull(client, **args):
    return client.run_tool("render_cull", args)


def test_long_skirt_from_the_knees_up(bridge, client):
    figure_scene(bridge.state).write()
    res = cull(client, camera="Cam", detail=True)
    status = {n["label"]: n["status"] for n in res["nodes"]}
    assert status == {"Mia": "in_view", "Top": "in_view", "Skirt": "in_view",
                      "Panties": "covered", "Shoes": "out_of_frame"}
    assert sorted(res["would_hide"]) == ["Panties (covered)", "Shoes"]
    assert 0 < res["savings"]["facets"] < res["savings"]["facets_total"]
    assert off_in_render(bridge) == []          # check changes nothing

    hid = cull(client, camera="Cam", action="hide")
    assert sorted(h["label"] for h in hid["hidden_ids"]) == ["Panties", "Shoes"]
    assert off_in_render(bridge) == ["Panties", "Shoes"]
    assert all(n.get("visible", True) for n in state_nodes(bridge).values())  # the viewport keeps them

    back = client.run_tool("render_cull", {"action": "set", "ids": hid["hidden_ids"], "visible": True})
    assert sorted(back["changed"]) == ["Panties", "Shoes"] and off_in_render(bridge) == []


def test_see_through_clothes_cover_nothing_and_occlusion_can_be_off(bridge, client):
    figure_scene(bridge.state, lace=True).write()
    res = cull(client, camera="Cam")
    assert res["would_hide"] == ["Shoes"]
    figure_scene(bridge.state).write()
    assert cull(client, camera="Cam", occlusion="none")["would_hide"] == ["Shoes"]


def test_wide_shot_keeps_the_shoes_and_keep_list(bridge, client):
    s = figure_scene(bridge.state)
    s.nodes[-1]["position"] = [0, 90, 500]   # the whole figure fits
    s.write()
    assert cull(client, camera="Cam")["would_hide"] == ["Panties (covered)"]
    figure_scene(bridge.state).write()
    res = cull(client, camera="Cam", keep=["Mia"])
    assert res["would_hide"] == []
    assert {k["label"] for k in res["kept"]} == {"Panties", "Shoes"}


def park(state, mirror=False):
    s = Scene(state)
    s.add("Ground", [[[-5000, -1, -5000], [5000, 0, 5000]]])
    s.add("Ana", [[[-20, 0, -10], [20, 170, 10]]], cls="DzFigure")
    s.add("Tree in view", [[[-60, 0, -560], [60, 600, -440]]])
    s.add("Tree behind camera", [[[-60, 0, 1940], [60, 600, 2060]]])
    s.add("Tree far left", [[[-3060, 0, -60], [-2940, 600, 60]]])
    s.add("Tree at the edge", [[[-100, 0, 150], [-75, 600, 210]]])
    s.add("Glowing lamp", [[[2000, 0, 2000], [2020, 300, 2020]]],
          materials=mats("Bulb", extra={"Emission Color": {"type": "color", "value": [1, 0.9, 0.7]},
                                        "Luminance": {"type": "float", "value": 1500}}))
    s.add("Wall", [[[-400, 0, 700], [400, 300, 720]]])
    s.add("Shed", [[[1950, 0, -1050], [2050, 300, -950]]])
    s.light("Lamp light", [3000, 300, -1500])
    if mirror:
        s.add("Mirror", [[[-50, 0, -100], [50, 200, -95]]],
              materials=mats("Glass", extra={"Metallic Weight": {"type": "float", "value": 1, "min": 0, "max": 1},
                                             "Glossy Roughness": {"type": "float", "value": 0.02}}))
    s.camera("Cam", [0, 120, 300])
    return s


def test_park_drops_far_trees_and_keeps_what_shapes_the_light(bridge, client):
    park(bridge.state).write()
    res = cull(client, camera="Cam", detail=True)
    status = {n["label"]: (n["status"], n.get("reason")) for n in res["nodes"]}
    assert status["Ground"] == ("in_view", None) and status["Ana"] == ("in_view", None)
    assert status["Tree in view"] == ("in_view", None)
    assert status["Tree behind camera"] == ("out_of_frame", None)
    assert status["Tree far left"] == ("out_of_frame", None)
    assert status["Tree at the edge"] == ("kept", "near_view")
    assert status["Glowing lamp"] == ("kept", "emits_light")
    assert status["Wall"] == ("kept", "holds_light_in")
    # the lamp light at (3000, 300, -1500) shines on Ana through the shed
    assert status["Shed"] == ("kept", "light_path")
    assert sorted(res["would_hide"]) == ["Tree behind camera", "Tree far left"]

    assert cull(client, camera="Cam", shadow_margin=0)["would_hide"].count("Tree at the edge") == 1


def test_mirror_in_view_keeps_everything_out_of_frame(bridge, client):
    park(bridge.state, mirror=True).write()
    res = cull(client, camera="Cam")
    assert res["would_hide"] == [] and "mirror" in res["warnings"][0]
    assert "Tree behind camera" in cull(client, camera="Cam", ignore_reflections=True)["would_hide"]


def test_animation_keeps_what_any_frame_sees(bridge, client):
    park(bridge.state).write()
    # the camera turns 90 degrees left over 30 frames: it ends looking at the far-left tree
    client.run_tool("anim_keys_set", {"node": "Cam", "tracks": {"node": {"rotation": [[0, 0, 0, 0],
                                                                                    [30, 0, 90, 0]]}}})
    still = cull(client, camera="Cam", frames=[0])
    moving = cull(client, camera="Cam", frames=sample_frames(0, 30, 12))
    assert "Tree far left" in still["would_hide"]
    assert "Tree far left" not in moving["would_hide"]
    assert "Tree behind camera" in moving["would_hide"]
    assert moving["frames"] == [0, 3, 5, 8, 11, 14, 16, 19, 22, 25, 27, 30]


def test_sample_frames():
    assert sample_frames(0, 5, 12) == [0, 1, 2, 3, 4, 5]
    assert sample_frames(10, 10, 4) == [10]
    assert sample_frames(0, 179, 4) == [0, 60, 119, 179]


# ------------------------------------------------------- through the MCP ----
def call(server, tool, **args):
    async def go():
        return await server.call_tool(tool, args)
    result = anyio.run(go)
    content = result[0] if isinstance(result, tuple) else result
    texts = [c.text for c in content if getattr(c, "type", "") == "text"]
    return json.loads(texts[-1])


@pytest.fixture
def server(bridge):
    return create_server(DazClient(Settings(transport="http")))


def renders(bridge):
    return json.loads(bridge.state.read_text())["renders"]


def test_render_with_cull_hides_only_for_that_render(bridge, server, tmp_path):
    figure_scene(bridge.state).write()
    res = call(server, "render", camera="Cam", out_path=str(tmp_path / "a.png"), max_time=5, cull=True)
    assert renders(bridge)[-1]["not_in_render"] == ["Panties", "Shoes"]
    assert sorted(res["cull"]["hidden"]) == ["Panties (covered)", "Shoes"]
    assert off_in_render(bridge) == []
    call(server, "render", camera="Cam", out_path=str(tmp_path / "b.png"), max_time=5)
    assert renders(bridge)[-1]["not_in_render"] == []


def test_hide_restore_and_save_never_keeps_them_hidden(bridge, server, tmp_path, daz_home):
    figure_scene(bridge.state).write()
    hid = call(server, "render_cull", camera="Cam", action="hide")
    assert sorted(hid["hidden"]) == ["Panties (covered)", "Shoes"]
    assert (daz_home / "cull-active.json").is_file()
    check = call(server, "render_cull", camera="Cam")
    assert check["active_cull"]["hidden"] == 2

    out = tmp_path / "saved.duf"
    saved = call(server, "scene_save", path=str(out))
    assert "render_cull" in saved
    on_disk = {n["label"]: n for n in json.loads(out.read_text())["nodes"]}
    assert on_disk["Shoes"].get("render_visible", True) is True
    assert off_in_render(bridge) == ["Panties", "Shoes"]   # hidden again for the next render

    # a second hide (another camera) first puts the first one back
    again = call(server, "render_cull", camera="Cam", action="hide", occlusion="none")
    assert again["restored_first"] == 2 and off_in_render(bridge) == ["Shoes"]

    back = call(server, "render_cull", action="restore")
    assert back["restored"] == ["Shoes"] and off_in_render(bridge) == []
    assert not (daz_home / "cull-active.json").exists()


def test_render_shots_culls_each_beat(bridge, server, tmp_path):
    figure_scene(bridge.state).write()
    # camera_shot needs a head and eyes; the beat only needs the camera, so give Mia a head bone
    st = json.loads(bridge.state.read_text())
    mia = next(n for n in st["nodes"] if n["label"] == "Mia")
    st["nodes"].append({"id": st["nextId"], "class": "DzBone", "name": "head", "label": "Head", "parent": mia["id"],
                        "skel": mia["id"], "position": [0, 0, 0], "rotation": [0, 0, 0], "origin": [0, 150, 0],
                        "end": [0, 172, 0], "order": "YZX"})
    st["nextId"] += 1
    bridge.state.write_text(json.dumps(st))
    res = call(server, "render_shots", beats=[{"name": "hello", "subject": "Mia", "shot": "close_up"}],
               out_dir=str(tmp_path / "shots"), max_time=5, cull=True)
    assert res["rendered"] == 1
    # a close-up on the face: skirt, panties and shoes are all out of the picture
    assert set(renders(bridge)[-1]["not_in_render"]) >= {"Shoes", "Panties"}
    assert off_in_render(bridge) == []
    shots = json.loads((tmp_path / "shots" / "shots.json").read_text())
    assert shots["beats"][0]["cull"]["hidden"] >= 2
