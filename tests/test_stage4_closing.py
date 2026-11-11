"""Closing test of stage 4, without Daz: over MCP (stdio), an agent

1. builds a walk cycle from scratch with key poses, plants its feet, saves it
   as a looping preset, plays it three times, slows it down and walks it
   along another path;
2. adapts a Mixamo FBX animation (T pose rig) to a second Genesis 9 and
   starts it later.

The steps are the ones the animation skill tells an agent to take.
"""

from __future__ import annotations

import json
import math
import os
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from daz3d_mcp import motion
from motion_fixture import FRAMES, TRAVEL, expected_arm_direction, expected_thigh_direction, write_mixamo_fbx

STAGE4_TOOLS = {"anim_timeline", "anim_keys_set", "anim_keys_get", "anim_keys_delete", "anim_key_pose",
                "anim_retime", "anim_offset", "anim_sample", "anim_preview", "anim_foot_contact",
                "anim_preset_list", "anim_preset_save", "anim_preset_apply", "anim_file_inspect", "anim_import"}

FEET = ["l_foot", "r_foot", "l_toes", "r_toes", "hip"]


def _params(daz_home, home) -> StdioServerParameters:
    env = dict(os.environ, DAZ3D_MCP_HOME=str(daz_home), DAZ3D_MCP_TRANSPORT="http", HOME=str(home))
    return StdioServerParameters(command=sys.executable, args=["-m", "daz3d_mcp"], env=env)


def _text(result) -> str:
    return "\n".join(c.text for c in result.content if c.type == "text")


def walk_cycle_keys() -> list[dict]:
    """A walk cycle the way an animator blocks it: contact, down, passing, up
    for each step; 32 frames (about 1.1 s) for two steps. Thighs swing on X
    (negative = forward), knees bend on X, the feet roll, the arms swing
    opposite to the legs, the hip dips after contact and rises at passing, and
    travels one step per half cycle."""
    step = 2 * 87 * math.sin(math.radians(25))  # leg length 87 cm, thighs 25 degrees each way
    # (thigh, shin, foot) of the planted leg and of the swinging leg, and the hip height.
    poses = {
        "contact": ((-25, 5, -10), (25, 10, 15), -3),
        "down": ((-18, 15, 0), (15, 45, 25), -4),
        "passing": ((-5, 5, 0), (-20, 55, 5), 1),
        "up": ((10, 5, 10), (-30, 30, -5), 2),
    }
    arms = {"contact": 20, "down": 12, "passing": 0, "up": -12}
    keys = []
    for i, name in enumerate(["contact", "down", "passing", "up"] * 2 + ["contact"]):
        frame = i * 4
        plant, swing = ("l", "r") if (i // 4) % 2 == 0 else ("r", "l")
        (pt, ps, pf), (st, ss, sf), hip_y = poses[name]
        bones = {f"{plant}_thigh": [pt, 0, 0], f"{plant}_shin": [ps, 0, 0], f"{plant}_foot": [pf, 0, 0],
                 f"{swing}_thigh": [st, 0, 0], f"{swing}_shin": [ss, 0, 0], f"{swing}_foot": [sf, 0, 0]}
        # The arm on the planted leg's side swings back while that leg is forward.
        a = arms[name]
        bones[f"{plant}_upperarm"] = [0, -a if plant == "l" else a, 0]
        bones[f"{swing}_upperarm"] = [0, a if swing == "l" else -a, 0]
        bones["l_forearm"], bones["r_forearm"] = [0, -15, 0], [0, 15, 0]
        keys.append({"frame": frame, "bones": bones,
                     "bone_positions": {"hip": [0, hip_y, round(step * frame / 16, 2)]}})
    return keys


def test_walk_cycle_from_scratch_and_mixamo_on_genesis9(bridge, daz_home, content_library, tmp_path):
    home = tmp_path / "home"
    mixamo = write_mixamo_fbx(home / "Downloads" / "Walking.fbx")
    log: dict = {}

    async def scenario():
        async with stdio_client(_params(daz_home, home)) as (read, write):
            async with ClientSession(read, write) as s:
                await s.initialize()

                async def tool(_tool, **args):
                    res = await s.call_tool(_tool, args)
                    assert not res.isError, f"{_tool}: {_text(res)}"
                    texts = [c.text for c in res.content if c.type == "text"]
                    return json.loads(texts[-1]) if texts else res

                assert STAGE4_TOOLS <= {t.name for t in (await s.list_tools()).tools}
                assert "animation" in {p.name for p in (await s.list_prompts()).prompts}

                await tool("scene_new")
                g9 = (await tool("content_search", query="genesis 9", kind="figure"))["results"][0]["path"]
                for name in ("Ana", "Leo"):
                    added = (await tool("content_load", path=g9))["added"][0]
                    await tool("node_set", node=added["label"], label=name)
                await tool("node_set", node="Leo", position=[150, 0, 0])

                # ---------------------------------------- 1. walk cycle --
                tl = await tool("anim_timeline", fps=30, frame=0)
                assert tl["fps"] == 30
                keyed = await tool("anim_keys_set", node="Ana", keys=walk_cycle_keys())
                assert keyed["range"] == [0, 32] and "not_found" not in keyed
                # Feet: the hip height was a guess; plant the feet on the floor.
                contact = await tool("anim_foot_contact", figure="Ana", fix="plant")
                assert contact["after"]["frames_below_floor"] == [] and contact["after"]["frames_floating"] == []
                log["walk_contact"] = contact
                # Left foot ahead at frame 0, right foot ahead at 16.
                feet = await tool("anim_sample", figure="Ana", frames=[0, 16], bones=FEET)
                f0, f16 = feet["frames"]["0"]["bones"], feet["frames"]["16"]["bones"]
                assert f0["l_foot"][2] - f0["r_foot"][2] > 50 and f16["r_foot"][2] - f16["l_foot"][2] > 50

                saved = await tool("anim_preset_save", figure="Ana", name="Walk Cycle", loop=True,
                                   description="Relaxed walk, two steps, 32 frames at 30 fps.")
                assert saved["frames"] == 32 and saved["loop"] is True
                await tool("anim_keys_delete", node="Ana")
                applied = await tool("anim_preset_apply", figure="Ana", preset="walk-cycle", repeat=3)
                assert applied["last_frame"] == 96
                slower = await tool("anim_retime", node="Ana", speed=0.8)
                assert slower["last_frame"] == 120
                placed = await tool("anim_offset", node="Ana", start_at=[-200, 100], turn=90)
                assert placed["rotation"][1] == 90
                after = await tool("anim_foot_contact", figure="Ana")
                assert after["before"]["frames_below_floor"] == [] and after["before"]["frames_floating"] == []
                log["walk_after_retime"] = after
                path = await tool("anim_sample", figure="Ana", frames=[0, 120], bones=["hip"])
                h0, h120 = path["frames"]["0"]["bones"]["hip"], path["frames"]["120"]["bones"]["hip"]
                assert h0[0] == -200 and h0[2] == 100
                # Three cycles of about 147 cm, now along +X.
                assert 400 < h120[0] - h0[0] < 480 and abs(h120[2] - h0[2]) < 1

                preview = await s.call_tool("anim_preview", {"frames": [0, 30, 60, 90]})
                assert not preview.isError and len([c for c in preview.content if c.type == "image"]) == 4

                # ------------------------------------ 2. Mixamo on Leo --
                info = await tool("anim_file_inspect", path=str(mixamo), figure="Leo")
                assert info["rig"] == "mixamo" and info["arms_at_rest"] == "T pose"
                assert info["bone_map"]["figure_bones_missing"] == []
                imported = await tool("anim_import", path=str(mixamo), figure="Leo")
                assert imported["frames"] == [0, FRAMES - 1] and imported["check_joint_angle_error_deg"] < 1
                assert imported["calibration"]["convention"] == "applied/qiq"
                log["mixamo_import"] = imported
                fix = await tool("anim_foot_contact", figure="Leo", fix="lift")
                assert fix["after"]["frames_below_floor"] == []
                later = await tool("anim_offset", node="Leo", frames=10)
                assert later["first_frame"] == 10 and later["last_frame"] == FRAMES + 9

                check = await tool("anim_sample", figure="Leo", frames=[10, 25, 40, 55],
                                   bones=["l_upperarm", "l_forearm", "r_upperarm", "r_forearm", "l_thigh", "l_shin",
                                          "r_thigh", "r_shin", "hip"])
                for f in (10, 25, 40, 55):
                    row = check["frames"][str(f)]["bones"]
                    for side in "lr":
                        arm = motion.v_norm(motion.v_sub(tuple(row[f"{side}_forearm"]), tuple(row[f"{side}_upperarm"])))
                        assert motion.angle_between(arm, expected_arm_direction(f - 10, side)) < 6
                        leg = motion.v_norm(motion.v_sub(tuple(row[f"{side}_shin"]), tuple(row[f"{side}_thigh"])))
                        assert motion.angle_between(leg, expected_thigh_direction(f - 10, side)) < 4
                hips = check["frames"]
                travel = hips["55"]["bones"]["hip"][2] - hips["10"]["bones"]["hip"][2]
                assert travel == __import__("pytest").approx(TRAVEL * 45 / 60 * 100 / 104, rel=0.03)

                tl = await tool("anim_timeline")
                assert tl["end_frame"] == 120
                assert {a["label"] for a in tl["animated"]} == {"Ana", "Leo"}
                await tool("scene_save", path=str(tmp_path / "walk and mixamo.duf"))

    anyio.run(scenario)
    walk = log["walk_contact"]["after"]
    # A walk blocked by hand slides a little; it must stay small.
    assert max(walk["slide_cm"].values()) < 30
    saved = json.loads((tmp_path / "walk and mixamo.duf").read_text())
    labels = {n["label"] for n in saved["nodes"]}
    assert {"Ana", "Leo"} <= labels
