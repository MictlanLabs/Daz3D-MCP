"""Dialogue scenes: camera_shot (film shots framed on a face, 180 degree rule)
and render_shots (a conversation rendered beat by beat), against the fake Daz.
Two Genesis 9 figures stand 100 cm apart on X, turned toward each other and
cheated 20 degrees toward +Z, so the open side of the pair is +Z."""

from __future__ import annotations

import json
import math

import anyio
import pytest

from daz3d_mcp.client import DazClient
from daz3d_mcp.server import create_server
from daz3d_mcp.settings import Settings
from daz3d_mcp.transport import DazError

G9 = "People/Genesis 9/Genesis 9.duf"


def call(server, tool, **args):
    async def go():
        return await server.call_tool(tool, args)
    result = anyio.run(go)
    content = result[0] if isinstance(result, tuple) else result
    texts = [c.text for c in content if getattr(c, "type", "") == "text"]
    return json.loads(texts[-1]), content


def add_eyes(bridge, label):
    state = json.loads(bridge.state.read_text())
    fig = next(n for n in state["nodes"] if n["label"] == label)
    head = next(n for n in state["nodes"] if n.get("name") == "head" and n.get("skel") == fig["id"])
    for side, x in (("l", 3.2), ("r", -3.2)):
        state["nodes"].append({"id": state["nextId"], "class": "DzBone", "name": f"{side}_eye",
                               "label": f"{side} eye", "parent": head["id"], "skel": fig["id"],
                               "position": [0, 0, 0], "rotation": [0, 0, 0], "origin": [x, 168, 8],
                               "end": [x, 168, 10], "order": "ZXY", "limits": [[-30, 30], [-30, 40], None]})
        state["nextId"] += 1
    bridge.state.write_text(json.dumps(state))


@pytest.fixture
def client(bridge, content_library):
    c = DazClient(Settings(transport="http"))
    for label, x, yaw in (("Ana", -50, 70), ("Beto", 50, -70)):
        c.run_tool("content_load", {"path": (content_library / G9).as_posix(), "kind": "figure"})
        c.run_tool("node_set", {"node": "Genesis 9", "label": label, "position": [x, 0, 0],
                                "rotation": [0, yaw, 0]})
        add_eyes(bridge, label)
    c.run_tool("render_settings", {"width": 640, "height": 360})
    return c


def shot(client, **args):
    return client.run_tool("camera_shot", args)


def test_shot_and_reverse_shot_stay_on_one_side_of_the_line(client):
    a = shot(client, subject="Ana", partner="Beto", shot="close_up")
    b = shot(client, subject="Beto", partner="Ana", shot="close_up", camera="Shot B")
    # both cameras on the open (+Z) side; the two look opposite ways on screen
    assert a["position"][2] > 30 and b["position"][2] > 30
    assert (a["looks"], b["looks"]) == ("screen_right", "screen_left")
    assert a["camera"] == "Shot" and b["camera"] == "Shot B" and b["active"] is True
    # eye level, 30 degrees off the eyeline, sized for the head
    assert a["position"][1] == pytest.approx(a["looking_at"][1], abs=0.01)
    assert a["focal_length"] == 85 and 100 < a["distance_cm"] < 220
    assert a["subject_eyes"][1] > 150
    # the camera stands toward the partner: in front of Ana, on Beto's side
    assert a["position"][0] > -50 and b["position"][0] < 50

    tight = shot(client, subject="Ana", partner="Beto", shot="extreme_close_up")
    wide = shot(client, subject="Ana", partner="Beto", shot="medium")
    assert tight["distance_cm"] < a["distance_cm"] < wide["distance_cm"] * 2.5
    assert tight["looks"] == wide["looks"] == "screen_right"

    crossed = shot(client, subject="Ana", partner="Beto", side="screen_left")
    assert crossed["looks"] == "screen_left" and crossed["position"][2] < -30


def test_angle_height_lens_and_room(client):
    base = shot(client, subject="Ana", partner="Beto", lead_room=0)
    profile = shot(client, subject="Ana", partner="Beto", angle=90, lead_room=0)
    # profile: the camera is straight off the line, beside Ana
    assert profile["position"][0] == pytest.approx(profile["looking_at"][0], abs=0.5)
    high = shot(client, subject="Ana", partner="Beto", height=15)
    assert high["position"][1] == pytest.approx(base["position"][1] + 15, abs=0.01)
    assert high["rotation"][0] < -3  # looking down
    near = shot(client, subject="Ana", partner="Beto", max_distance=80, lead_room=0)
    assert near["distance_cm"] == pytest.approx(80, abs=0.5)
    assert near["focal_length"] == pytest.approx(85 * 80 / base["distance_cm"], abs=0.5)
    # lead room moves the aim toward where she looks (+X), so her face sits away from it
    lead = shot(client, subject="Ana", partner="Beto")
    assert lead["looking_at"][0] > base["looking_at"][0] + 3


def test_over_the_shoulder_two_shot_and_blocked_heads(client):
    ots = shot(client, subject="Ana", partner="Beto", shot="over_the_shoulder")
    beto_eyes = shot(client, subject="Beto", partner="Ana")["subject_eyes"]
    behind = math.dist(ots["position"], beto_eyes)
    assert 25 < behind < 60 and ots["position"][0] > beto_eyes[0]  # behind Beto's head
    assert ots["position"][2] > beto_eyes[2]                      # on the open side
    assert "blocked_by" not in ots and 24 <= ots["focal_length"] <= 200

    two = shot(client, subject="Ana", partner="Beto", shot="two_shot")
    assert -20 < two["looking_at"][0] < 20 and two["position"][2] > 100

    on_line = shot(client, subject="Ana", partner="Beto", angle=0)
    assert on_line["blocked_by"] == ["Beto"] and "angle" in on_line["hint"]

    with pytest.raises(DazError, match="needs a partner"):
        shot(client, subject="Ana", shot="over_the_shoulder")
    with pytest.raises(DazError, match="another figure"):
        shot(client, subject="Ana", partner="Ana")


def test_shot_without_partner_follows_the_face(client):
    res = shot(client, subject="Ana", angle=0, lead_room=0)
    # Ana faces yaw 70: mostly +X, a bit +Z
    d = [res["position"][0] - res["looking_at"][0], res["position"][2] - res["looking_at"][2]]
    assert math.degrees(math.atan2(d[0], d[1])) == pytest.approx(70, abs=1)


def test_render_shots(client, bridge, tmp_path):
    server = create_server(client)
    out = tmp_path / "escena"
    beats = [
        {"name": "establecer", "subject": "Ana", "partner": "Beto", "shot": "two_shot",
         "gaze": {"Ana": "Beto", "Beto": "Ana"}, "line": "(Entran.)"},
        {"name": "ana_hola", "subject": "Ana", "partner": "Beto", "faces": {"Ana": "neutral"},
         "line": "Ana: Hola."},
        {"name": "beto_mira", "subject": "Beto", "partner": "Ana", "shot": "over_the_shoulder",
         "gaze": {"Beto": {"target": "camera", "head": 0}}},
    ]
    res, content = call(server, "render_shots", beats=beats, max_time=3, out_dir=out.as_posix(), previews=2)
    assert res["rendered"] == 3 and res["kept"] == 0
    assert res["looks"] == ["1 Ana: screen_right", "2 Ana: screen_right", "3 Beto: screen_left"]
    names = sorted(p.name for p in out.iterdir())
    assert names == ["01_establecer.png", "02_ana_hola.png", "03_beto_mira.png", "shots.json"]
    manifest = json.loads((out / "shots.json").read_text(encoding="utf-8"))
    assert [b["line"] for b in manifest["beats"]] == ["(Entran.)", "Ana: Hola.", None]
    assert manifest["beats"][2]["shot"] == "over_the_shoulder" and manifest["camera"] == "Shot"
    done = json.loads(bridge.state.read_text())["renders"]
    assert [r["camera"] for r in done] == ["Shot"] * 3 and {r["max_time"] for r in done} == {3}
    assert [c.type for c in content] == ["text", "image", "text", "image", "text"]

    # again: everything is there, nothing renders; `only` redoes a beat after deleting it
    again, _ = call(server, "render_shots", beats=beats, out_dir=out.as_posix())
    assert again["rendered"] == 0 and again["kept"] == 3
    (out / "02_ana_hola.png").unlink()
    redo, _ = call(server, "render_shots", beats=beats, out_dir=out.as_posix(), only=[2], previews=0)
    assert redo["rendered"] == 1 and (out / "02_ana_hola.png").exists()

    with pytest.raises(Exception, match="own name"):
        call(server, "render_shots", beats=beats + [beats[0]], out_dir=out.as_posix())
