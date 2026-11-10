"""Stage 4 tools against the fake Daz: keyframes, timeline, presets, retime,
offset, foot contact and BVH / FBX import."""

from __future__ import annotations

import json
import math

import anyio
import pytest

from daz3d_mcp import motion
from daz3d_mcp.client import DazClient
from daz3d_mcp.server import create_server
from daz3d_mcp.settings import Settings
from motion_fixture import (FRAMES, TRAVEL, expected_arm_direction, expected_thigh_direction, write_bvh,
                            write_mixamo_fbx)

G9 = "People/Genesis 9/Genesis 9.duf"


class Agent:
    """Calls the MCP tools in-process, the way an agent would."""

    def __init__(self, client: DazClient):
        self.server = create_server(client)

    def __call__(self, _tool: str, **args):
        async def go():
            return await self.server.call_tool(_tool, args)
        result = anyio.run(go)
        content = result[0] if isinstance(result, tuple) else result
        texts = [c.text for c in content if getattr(c, "type", "") == "text"]
        return json.loads(texts[-1]) if texts else content


@pytest.fixture
def agent(bridge, content_library):
    a = Agent(DazClient(Settings(transport="http")))
    a.lib = content_library
    return a


def state(bridge) -> dict:
    return json.loads(bridge.state.read_text())


def g9(agent, label="Ana"):
    added = agent("content_load", path=(agent.lib / G9).as_posix())["added"][0]
    agent("node_set", node=added["label"], label=label)
    return label


def direction(sample, frame, a, b):
    row = sample["frames"][str(frame)]["bones"]
    return motion.v_norm(motion.v_sub(tuple(row[b]), tuple(row[a])))


def test_timeline_fps_and_range(agent):
    g9(agent)
    tl = agent("anim_timeline")
    assert tl["fps"] == 30 and tl["start_frame"] == 0 and tl["end_frame"] == 0 and tl["animated"] == []
    agent("anim_keys_set", node="Ana", keys=[{"frame": 0, "bones": {"head": [0, 0, 0]}},
                                              {"frame": 30, "bones": {"head": [0, 40, 0]}}])
    tl = agent("anim_timeline", frame=15)
    assert tl["end_frame"] == 30 and tl["frame"] == 15
    assert tl["animated"] == [{"label": "Ana", "type": "figure", "channels": 3, "bones": 1, "first_frame": 0,
                               "last_frame": 30}]
    # 24 fps keeping the duration: the key at 1 s is now at frame 24.
    tl = agent("anim_timeline", fps=24)
    assert tl["fps"] == 24 and tl["end_frame"] == 24
    keys = agent("anim_keys_get", node="Ana")
    assert keys["tracks"]["bones"]["head"]["rotation"][-1] == [24, 0, 40, 0]
    # Back to 30 keeping the frames: the key stays on frame 24 (plays faster).
    tl = agent("anim_timeline", fps=30, keep="frames")
    assert tl["end_frame"] == 24 and tl["keys_moved"] == 6


def test_keys_set_get_and_in_between(agent, bridge):
    g9(agent)
    res = agent("anim_keys_set", node="Ana", keys=[
        {"frame": 0, "bones": {"l_shin": [0, 0, 0]}, "bone_positions": {"hip": [0, 0, 0]}, "morphs": {"Jaw Open": 0}},
        {"frame": 10, "bones": {"l_shin": [60, None, None]}, "bone_positions": {"hip": [0, -5, 20]},
         "morphs": {"Jaw Open": 0.8}, "position": [100, 0, 0]},
        {"frame": 20, "bones": {"nope": [1, 2, 3]}},
    ])
    assert res["keys_set"] == 7 + 8  # at frame 10 the shin keys only X
    assert res["not_found"] == {"bones": ["nope"]} and res["range"] == [0, 10]
    got = agent("anim_keys_get", node="Ana")
    assert got["tracks"]["bones"]["l_shin"]["rotation"] == [[0, 0, 0, 0], [10, 60, 0, 0]]
    assert got["tracks"]["bones"]["hip"]["position"][-1] == [10, 0, -5, 20]
    assert got["tracks"]["morphs"]["Jaw Open"] == [[0, 0], [10, 0.8]]
    assert got["tracks"]["node"]["position"] == [[10, 100, 0, 0]]
    summary = agent("anim_keys_get", node="Ana", summary=True)
    assert "tracks" not in summary and set(summary["summary"]["bones"]) == {"l_shin", "hip"}
    # Daz fills in the frames between keys: at frame 5 the knee is half bent.
    s = agent("anim_sample", figure="Ana", frames=[0, 5, 10], bones=["l_shin", "l_foot"])
    knee = [math.degrees(math.atan2(-direction(s, f, "l_shin", "l_foot")[2], -direction(s, f, "l_shin", "l_foot")[1]))
            for f in (0, 5, 10)]
    assert knee[0] == pytest.approx(2.6, abs=0.5) and knee[1] == pytest.approx(32.6, abs=1) and \
        knee[2] == pytest.approx(62.6, abs=1)
    # replace clears the old keys in the range before setting new ones.
    res = agent("anim_keys_set", node="Ana", keys=[{"frame": 5, "bones": {"l_shin": [10, 0, 0]}}], replace=[0, 30])
    assert res["keys_replaced"] == 4
    assert agent("anim_keys_get", node="Ana", bones=["l_shin"])["tracks"]["bones"]["l_shin"]["rotation"] == \
        [[5, 10, 0, 0]]
    deleted = agent("anim_keys_delete", node="Ana", what=["morphs"])
    assert deleted["keys_deleted"] == 2
    assert agent("anim_keys_delete", node="Ana")["keys_left"] == 0


def test_key_pose_after_a_pose_preset(agent):
    g9(agent)
    pose = agent("content_search", query="waving", kind="pose")["results"][0]
    agent("content_load", path=pose["path"], target="Ana")
    res = agent("anim_key_pose", figure="Ana", frames=[0, 24])
    assert set(res["bones"]) == {"hip", "r_upperarm", "r_forearm", "head"}
    got = agent("anim_keys_get", node="Ana", bones=["r_forearm"])
    assert got["tracks"]["bones"]["r_forearm"]["rotation"] == [[0, 0, 0, -100], [24, 0, 0, -100]]


def test_retime_and_offset(agent, bridge):
    g9(agent)
    agent("anim_keys_set", node="Ana", keys=[{"frame": 0, "bones": {"head": [0, 0, 0]}},
                                              {"frame": 20, "bones": {"head": [0, 30, 0]}},
                                              {"frame": 40, "bones": {"head": [0, 0, 0]}}])
    res = agent("anim_retime", node="Ana", speed=2)
    assert res["new_part"] == [0, 20] and res["last_frame"] == 20 and res["range_updated"] is True
    assert agent("anim_timeline")["end_frame"] == 20
    res = agent("anim_retime", node="Ana", length=60, start_frame=10, end_frame=20)
    assert [r[0] for r in agent("anim_keys_get", node="Ana")["tracks"]["bones"]["head"]["rotation"]] == [0, 10, 70]
    res = agent("anim_offset", node="Ana", frames=15)
    assert res["first_frame"] == 15 and res["last_frame"] == 85
    with pytest.raises(Exception):
        agent("anim_offset", node="Ana", frames=-50)
    assert agent("anim_timeline")["end_frame"] == 85


def test_offset_moves_and_turns_root_motion(agent):
    g9(agent)
    agent("anim_keys_set", node="Ana", keys=[{"frame": 0, "bone_positions": {"hip": [0, 0, 0]}},
                                              {"frame": 30, "bone_positions": {"hip": [0, 0, 100]}}])
    s = agent("anim_sample", figure="Ana", frames=[0, 30], bones=["hip"])
    assert s["frames"]["30"]["bones"]["hip"] == [0, 100, 100]
    agent("anim_offset", node="Ana", turn=90, start_at=[200, -50])
    s = agent("anim_sample", figure="Ana", frames=[0, 30], bones=["hip"])
    # Starts at the spot and now walks toward +X instead of +Z.
    assert s["frames"]["0"]["bones"]["hip"] == [200, 100, -50]
    assert s["frames"]["30"]["bones"]["hip"] == [300, 100, -50]


def test_presets_builtin_save_and_apply(agent, daz_home):
    g9(agent)
    g9(agent, "Leo")
    listed = {p["name"]: p for p in agent("anim_preset_list")["presets"]}
    assert {"idle-breathing", "head-nod", "head-shake"} <= set(listed)
    res = agent("anim_preset_apply", figure="Ana", preset="head-nod", start_frame=10, speed=2)
    assert res["last_frame"] == 25 and res["keys_set"] > 0
    # A small walk cycle with travel, saved as a looping preset.
    agent("anim_keys_set", node="Leo", keys=[
        {"frame": 0, "bones": {"l_thigh": [-20, 0, 0]}, "bone_positions": {"hip": [0, 0, 0]}},
        {"frame": 16, "bones": {"l_thigh": [20, 0, 0]}, "bone_positions": {"hip": [0, 0, 70]}},
        {"frame": 32, "bones": {"l_thigh": [-20, 0, 0]}, "bone_positions": {"hip": [0, 0, 140]}}])
    saved = agent("anim_preset_save", figure="Leo", name="Tiny Walk", loop=True, description="test walk")
    assert saved["name"] == "tiny-walk" and saved["frames"] == 32 and (daz_home / "animations" / "tiny-walk.json").is_file()
    assert "tiny-walk" in {p["name"] for p in agent("anim_preset_list", query="walk")["presets"]}
    res = agent("anim_preset_apply", figure="Ana", preset="tiny-walk", start_frame=0, repeat=3)
    assert res["last_frame"] == 96
    hip = agent("anim_keys_get", node="Ana", bones=["hip"])["tracks"]["bones"]["hip"]["position"]
    assert hip[-1] == [96, 0, 0, 420]  # three cycles carry on walking
    res = agent("anim_preset_apply", figure="Ana", preset="tiny-walk", repeat=2, in_place=True)
    hip = agent("anim_keys_get", node="Ana", bones=["hip"])["tracks"]["bones"]["hip"]["position"]
    assert {r[3] for r in hip if r[0] <= 64} == {0}


def test_library_animation_preset(agent):
    g9(agent)
    found = agent("content_search", kind="animation")["results"]
    assert [f["name"] for f in found] == ["Little Hop"]
    res = agent("anim_preset_apply", figure="Ana", preset=found[0]["path"], start_frame=30)
    assert res["first_frame"] == 30 and res["last_frame"] == 50


def _check_walk(agent, frames=(0, 7, 15, 30, 45)):
    s = agent("anim_sample", figure="Ana", frames=list(frames),
              bones=["l_upperarm", "l_forearm", "r_upperarm", "r_forearm", "l_thigh", "l_shin", "r_thigh", "r_shin",
                     "hip"])
    for f in frames:
        for side in "lr":
            want = expected_arm_direction(f, side)
            got = direction(s, f, f"{side}_upperarm", f"{side}_forearm")
            assert motion.angle_between(want, got) < 6, (f, side, "arm", want, got)
            want = expected_thigh_direction(f, side)
            got = direction(s, f, f"{side}_thigh", f"{side}_shin")
            assert motion.angle_between(want, got) < 4, (f, side, "thigh", want, got)
    return s


def test_import_mixamo_fbx(agent, daz_home, tmp_path):
    fbx = write_mixamo_fbx(tmp_path / "Walking.fbx")
    g9(agent)
    info = agent("anim_file_inspect", path=str(fbx), figure="Ana")
    assert info["rig"] == "mixamo" and info["arms_at_rest"] == "T pose" and info["frames"] == FRAMES
    assert info["rest_pose"] == "the bind pose stored in the file"
    assert info["bone_map"]["pairs"]["mixamorig:LeftArm"] == "l_upperarm"
    res = agent("anim_import", path=str(fbx), figure="Ana")
    assert res["source_rig"] == "mixamo" and res["figure_rig"] == "genesis9"
    assert res["frames"] == [0, FRAMES - 1] and res["bones_mapped"] == 22
    assert res["calibration"]["convention"] == "applied/qeq" and res["calibration"]["mean_error_deg"] < 1
    assert res["check_joint_angle_error_deg"] < 1
    assert res["root_travel_cm"] == pytest.approx(TRAVEL * 100 / 104, rel=0.02)
    assert (daz_home / "animation.json").is_file()
    s = _check_walk(agent)
    hip0, hip60 = s["frames"]["0"]["bones"]["hip"], agent("anim_sample", figure="Ana", frames=[60],
                                                          bones=["hip"])["frames"]["60"]["bones"]["hip"]
    assert hip0[2] == pytest.approx(0, abs=0.5) and hip60[2] == pytest.approx(TRAVEL * 100 / 104, rel=0.02)
    # Second import: the convention is already known, no calibration.
    res = agent("anim_import", path=str(fbx), figure="Ana", in_place=True, start_frame=100)
    assert "calibration" not in res and res["frames"] == [100, 160] and res["root_travel_cm"] == 0


def test_import_finds_another_rotation_convention(agent, monkeypatch, tmp_path):
    monkeypatch.setenv("DAZMCP_FAKE_CONVENTION", "product/qiq")
    bvh = write_bvh(tmp_path / "walk.bvh")
    g9(agent)
    res = agent("anim_import", path=str(bvh), figure="Ana")
    assert res["source_rig"] == "cmu" and res["calibration"]["convention"] == "product/qiq"
    assert res["check_joint_angle_error_deg"] < 1
    _check_walk(agent)


def test_import_bone_map_and_errors(agent, tmp_path):
    bvh = write_bvh(tmp_path / "walk.bvh")
    g9(agent)
    res = agent("anim_import", path=str(bvh), figure="Ana", bone_map={"LeftArm": None, "Head": "neck2"})
    assert "LeftArm" not in res["pairs"] and res["pairs"]["Head"] == "neck2"
    assert any("l_upperarm" in w for w in res["warnings"])
    with pytest.raises(Exception) as err:
        agent("anim_import", path=str(bvh), figure="Ana", bone_map={"Tail": "head"})
    assert "Tail" in str(err.value)
    (tmp_path / "x.glb").write_bytes(b"glTF")
    with pytest.raises(Exception) as err:
        agent("anim_file_inspect", path=str(tmp_path / "x.glb"))
    assert ".bvh and .fbx" in str(err.value)


def test_foot_contact_lift_and_plant(agent):
    g9(agent)
    # Knees bend but the hip stays up: the feet float. Then the hip sinks too far.
    agent("anim_keys_set", node="Ana", keys=[
        {"frame": 0, "bones": {"l_thigh": [-30, 0, 0], "r_thigh": [-30, 0, 0], "l_shin": [60, 0, 0],
                               "r_shin": [60, 0, 0]}, "bone_positions": {"hip": [0, 0, 0]}},
        {"frame": 10, "bone_positions": {"hip": [0, -20, 0]}, "bones": {"l_thigh": [0, 0, 0], "r_thigh": [0, 0, 0],
                                                                         "l_shin": [0, 0, 0], "r_shin": [0, 0, 0]}}])
    res = agent("anim_foot_contact", figure="Ana")
    assert res["before"]["frames_below_floor"] and res["before"]["frames_floating"]
    res = agent("anim_foot_contact", figure="Ana", fix="lift")
    assert res["after"]["frames_below_floor"] == [] and res["after"]["frames_floating"]
    res = agent("anim_foot_contact", figure="Ana", fix="plant")
    assert res["after"]["frames_below_floor"] == [] and res["after"]["frames_floating"] == []
    assert abs(res["after"]["lowest_cm"]) <= 1
