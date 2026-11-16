"""wearable_refit: shoes made for another Genesis generation.

The file side (the pose a shoe's own file carries, its authored weights and
the bone names of each generation) is tested directly; the Daz side runs
against the fake Daz, whose Genesis 9 has a tube of "skin" around each bone
and whose clothing is made of boxes."""

from __future__ import annotations

import gzip
import json

import anyio
import pytest

from daz3d_mcp import refit
from daz3d_mcp.client import DazClient
from daz3d_mcp.server import create_server
from daz3d_mcp.settings import Settings

G9 = "People/Genesis 9/Genesis 9.duf"
SHOES = "People/Genesis 8 Female/Clothing/Night Out/Night Out Heels.duf"
DSF = "data/Test/Night Out/Heels/NightOutHeels.dsf"


def heels_duf():
    """What a Genesis 8 heeled shoe's wearable preset looks like."""
    url = "/" + DSF.replace(" ", "%20")
    return {
        "asset_info": {"type": "wearable"},
        "scene": {
            "nodes": [
                {"id": "NightOutHeels", "url": url + "#NightOutHeels", "name": "NightOutHeels",
                 "label": "Night Out Heels", "conform_target": "name://@selection:"},
                {"id": "lFoot", "url": url + "#lFoot", "parent": "#NightOutHeels"},
            ],
            "animations": [
                {"url": "name://@selection/lFoot:?rotation/x/value", "keys": [[0, 30], [1, 30]]},
                {"url": "name://@selection/lMetatarsals:?rotation/z/value", "keys": [[0, 0]]},
                {"url": "name://@selection/lToe:?rotation/x/value", "keys": [[0, -35]]},
                {"url": "name://@selection/lToe:?rotation/z/value", "keys": [[0, 1.2]]},
                {"url": "name://@selection/rFoot:?rotation/x/value", "keys": [[0, 30]]},
                {"url": "name://@selection/rToe:?rotation/x/value", "keys": [[0, -35]]},
                {"url": "NightOutHeels:?rotation/x/value", "keys": [[0, 12]]},
                {"url": "name://@selection/lFoot:?scale/general/value", "keys": [[0, 1]]},
            ],
        },
    }


def heels_dsf():
    return {"modifier_library": [{"id": "SkinBinding", "skin": {"vertex_count": 6, "joints": [
        {"id": "lFoot", "node_weights": {"count": 2, "values": [[0, 1], [1, 0.4]]}},
        {"id": "lMetatarsals", "node_weights": {"count": 2, "values": [[1, 0.6], [2, 0.5]]}},
        {"id": "lToe", "node_weights": {"count": 1, "values": [[2, 0.5]]}},
        {"id": "lSmallToe4", "node_weights": {"count": 0, "values": []}},
        {"id": "rFoot", "node_weights": {"count": 3, "values": [[3, 1], [4, 1], [5, 1]]}},
        {"id": "lShin"},
    ]}}]}


# ------------------------------------------------------------- files ----
def test_bone_names_of_each_generation():
    assert refit.bone_style(["hip", "lFoot", "lToe"]) == "genesis8"
    assert refit.bone_style(["hip", "l_foot"]) == "genesis9"
    assert refit.bone_style(["Bone1"]) is None
    assert refit.map_bone("lToe", "genesis9") == "l_toes"
    assert refit.map_bone("rMetatarsals", "genesis9") == "r_foot"   # a leaf beside the toes on Genesis 9
    assert refit.map_bone("lSmallToe4_2", "genesis9") == "l_pinkytoe2"
    assert refit.map_bone("r_bigtoe1", "genesis8") == "rBigToe"
    assert refit.map_bone("l_foot", "genesis8") == "lFoot"
    assert refit.map_bone("lCollar", "genesis9") is None


def test_pose_in_the_shoes_file_is_translated():
    pose = refit.file_pose(heels_duf())
    assert pose == {"lFoot": [30, 0, 0], "lToe": [-35, 0, 1.2], "rFoot": [30, 0, 0], "rToe": [-35, 0, 0]}
    g9, skipped = refit.translate_pose(pose, "genesis9")
    assert g9 == {"l_foot": [30, 0, 0], "l_toes": [-35, 0, 1.2], "r_foot": [30, 0, 0], "r_toes": [-35, 0, 0]}
    assert skipped == []
    same, _ = refit.translate_pose(pose, "genesis8")
    assert same == pose
    _, skipped = refit.translate_pose({"lCollar": [0, 0, 10], "lFoot": [20, 0, 0]}, "genesis9")
    assert skipped == ["lCollar"]


def test_authored_weights_are_merged_under_the_new_names():
    weights, count = refit.authored_weights(heels_dsf())
    assert count == 6 and set(weights) == {"lFoot", "lMetatarsals", "lToe", "rFoot"}
    g9, why = refit.translate_weights(weights, "genesis9")
    assert why is None
    assert g9 == {"l_foot": [[0, 1.0], [1, 1.0], [2, 0.5]], "l_toes": [[2, 0.5]],
                  "r_foot": [[3, 1.0], [4, 1.0], [5, 1.0]]}
    total: dict[int, float] = {}
    for values in g9.values():
        for i, w in values:
            total[i] = total.get(i, 0) + w
    assert all(abs(t - 1) < 1e-6 for t in total.values())   # every vertex still adds up to 1


def test_only_footwear_weights_are_translated():
    none, why = refit.translate_weights({"lThighBend": [[0, 1]], "lFoot": [[1, 1]]}, "genesis9")
    assert none is None and "lThighBend" in why
    none, why = refit.translate_weights({"l_foot": [[0, 1]]}, "genesis9")
    assert none is None and "already" in why


def test_finds_the_item_and_its_data_file(tmp_path):
    doc = heels_duf()
    assert refit.matches_item(doc, "Night Out Heels (2)")["dsf"] == DSF
    assert refit.matches_item(doc, "Renamed", "NightOutHeels")["node"] == "NightOutHeels"
    assert refit.matches_item(doc, "Other Shoes") is None
    lib = tmp_path / "lib"
    target = lib / "Data" / "Test" / "Night Out" / "Heels" / "NightOutHeels.dsf"   # "Data", not "data"
    target.parent.mkdir(parents=True)
    target.write_bytes(gzip.compress(json.dumps(heels_dsf()).encode()))
    found = refit.resolve_asset(DSF, [tmp_path / "nothing", lib])
    assert found is not None and refit.authored_weights(refit.read_dson(found))[1] == 6
    assert refit.resolve_asset("data/Test/Missing.dsf", [lib]) is None


# --------------------------------------------------------------- Daz ----
def add_shoes(bridge, label="Night Out Heels", name="NightOutHeels", low=-9.0):
    """Two slabs under the feet, where a heeled shoe's sole is: well below the flat foot."""
    state = json.loads(bridge.state.read_text())
    fig = next(n for n in state["nodes"] if n["label"] == "Genesis 9")
    node_id = state["nextId"]
    state["nextId"] = node_id + 1
    boxes = [[[4, low, -8], [16, low + 2, 22]], [[-16, low, -8], [-4, low + 2, 22]]]
    state["nodes"].append({"id": node_id, "class": "DzFigure", "label": label, "name": name, "parent": fig["id"],
                           "fitted_to": fig["id"], "position": [0, 0, 0], "rotation": [0, 0, 0], "geometry": True,
                           "mesh_boxes": boxes, "bbox_local": [[-16, low, -8], [16, low + 2, 22]]})
    bridge.state.write_text(json.dumps(state))


@pytest.fixture
def client(bridge, content_library):
    c = DazClient(Settings(transport="http"))
    c.run_tool("content_load", {"path": (content_library / G9).as_posix(), "kind": "figure"})
    add_shoes(bridge)
    return c


def test_check_sees_the_feet_floating_over_the_soles(client):
    res = client.run_tool("wearable_refit", {"item": "Night Out Heels"})
    assert res["figure"] == "Genesis 9" and res["bone_style"] == "genesis9" and res["footwear"]
    assert res["verdict"] == "misplaced"
    assert {p["code"] for p in res["problems"]} == {"foot_floating", "below_floor"}
    left = res["feet"]["left"]
    assert left["under_foot"] > 0.8 and left["floating"] > 0.9 and left["median_gap_cm"] > 3
    assert res["lowest_cm"]["item"] == -9 and res["lowest_cm"]["bare_feet"] > -3
    assert res["foot_rotation"]["l_foot"] == [0, 0, 0]


def test_fix_poses_the_feet_and_stands_the_figure_on_the_soles(bridge, client):
    bare = client.run_tool("wearable_refit", {"item": "Night Out Heels"})["lowest_cm"]["bare_feet"]
    res = client.run_tool("wearable_refit", {"item": "Night Out Heels", "action": "fix",
                                              "pose": {"l_foot": [30, 0, 0], "r_foot": [30, 0, 0]}})
    assert res["done"] == ["pose", "ground"]
    assert res["keep_shape"]["pose"]["l_foot"] == [30, 0, 0]
    assert res["keep_shape"]["state"] == "not_needed"       # the fake's boxes do not bend with the bones
    assert res["ground"]["moved_up_cm"] == pytest.approx(bare + 9, abs=0.2)
    assert res["after"]["foot_rotation"]["r_foot"] == [30, 0, 0]
    assert res["after"]["lowest_cm"]["item"] == pytest.approx(bare, abs=0.2)
    fig = next(n for n in json.loads(bridge.state.read_text())["nodes"] if n["label"] == "Genesis 9")
    assert fig["position"][1] == pytest.approx(bare + 9, abs=0.2)


def test_fix_keeps_the_rest_of_the_pose_and_can_leave_the_figure_where_it_is(client):
    client.run_tool("pose_bones", {"figure": "Genesis 9", "bones": {"l_thigh": [-40, 0, 0], "l_foot": [10, 0, 0]}})
    res = client.run_tool("wearable_refit", {"item": "Night Out Heels", "action": "fix", "ground": False,
                                              "pose": {"l_foot": [30, 0, 0]}})
    assert "ground" not in res and res["done"] == ["pose"]
    posed = client.run_tool("figure_info", {"figure": "Genesis 9"})["posed_bones"]
    assert {b["bone"]: b["rotation"] for b in posed} == {"l_thigh": [-40, 0, 0], "l_foot": [30, 0, 0]}


def test_errors(client):
    from daz3d_mcp.transport import DazError
    with pytest.raises(DazError, match="no bone lFoot"):
        client.run_tool("wearable_refit", {"item": "Night Out Heels", "action": "fix", "pose": {"lFoot": [30, 0, 0]}})
    with pytest.raises(DazError, match="No node"):
        client.run_tool("wearable_refit", {"item": "Nothing"})


# ------------------------------------------------------- the MCP tool ----
def call(server, name, **args):
    async def run():
        res = await server.call_tool(name, args)
        parts = res[0] if isinstance(res, tuple) else res
        return json.loads(parts[0].text)
    return anyio.run(run)


@pytest.fixture
def server(bridge, content_library):
    (content_library / SHOES).parent.mkdir(parents=True)
    (content_library / SHOES).write_text(json.dumps(heels_duf()))
    (content_library / DSF).parent.mkdir(parents=True)
    (content_library / DSF).write_bytes(gzip.compress(json.dumps(heels_dsf()).encode()))
    s = create_server(DazClient(Settings(transport="http")))
    call(s, "content_load", path=G9)
    add_shoes(bridge)
    return s


def test_tool_reads_the_pose_from_the_shoes_own_file(server):
    res = call(server, "wearable_refit", item="Night Out Heels")
    assert res["source"]["file"].endswith("Night Out Heels.duf")
    assert res["source"]["made_for"] == "genesis8" and res["source"]["other_generation"] is True
    assert res["source"]["pose"]["l_toes"] == [-35, 0, 1.2]
    assert "pose_not_applied" in {p["code"] for p in res["problems"]}
    assert res["verdict"] == "misplaced" and "fix=true" in res["hint"]
    assert not any(k.startswith("_") for k in res["source"])     # the weights stay out of the answer

    fixed = call(server, "wearable_refit", item="Night Out Heels", fix=True)
    assert fixed["after"]["foot_rotation"]["l_foot"] == [30, 0, 0]
    assert fixed["after"]["foot_rotation"]["l_toes"] == [-35, 0, 1.2]
    assert "pose" in fixed["done"] and "ground" in fixed["done"]
    again = call(server, "wearable_refit", item="Night Out Heels")
    assert "pose_not_applied" not in {p["code"] for p in again["problems"]}


def test_tool_takes_a_pose_by_hand(server):
    res = call(server, "wearable_refit", item="Night Out Heels", fix=True,
               foot_pose={"l_foot": [20, 0, 0], "r_foot": [20, 0, 0]}, ground=False)
    assert res["after"]["foot_rotation"]["l_foot"] == [20, 0, 0] and "ground" not in res
    none = call(server, "wearable_refit", item="Night Out Heels", fix=True, foot_pose="none", ground=False)
    assert "pose" not in none["done"] and "No foot pose" in none["notes"][-1]


# ------------------------------------------- clothing of another generation ----
def add_top(bridge, label="Bardot Top", skin=None, fitted_to="Genesis 9"):
    """A top Auto-Fit put on Genesis 9 without converting it: still rigged to Genesis 8 bones."""
    state = json.loads(bridge.state.read_text())
    target = next(n for n in state["nodes"] if n["label"] == fitted_to)
    node_id = state["nextId"]
    state["nextId"] = node_id + 1
    boxes = [[[-14, 120, -10], [14, 150, 12]]]
    state["nodes"].append({"id": node_id, "class": "DzFigure", "label": label, "name": label.replace(" ", ""),
                           "parent": target["id"], "fitted_to": target["id"], "position": [0, 0, 0],
                           "rotation": [0, 0, 0], "geometry": True, "mesh_boxes": boxes,
                           "bbox_local": boxes[0],
                           "skin": skin or {"chestUpper": 300, "lCollar": 80, "rCollar": 80, "hip": 10}})
    bridge.state.write_text(json.dumps(state))


def test_clone_for_reads_the_generation_from_the_items_folder():
    assert refit.clone_for("C:/Lib/People/Genesis 8 Female/Clothing/Bardot/Bardot Top.duf") == "CloneGenesis8Female"
    assert refit.clone_for("People/Genesis 8.1 Male/Clothing/Jacket.duf") == "CloneGenesis8Male"
    assert refit.clone_for(r"People\Genesis 9\Clothing\Worker Uniform\Boots.duf") == "CloneGenesis9"
    assert refit.clone_for("Props/Chair.duf") is None and refit.clone_for(None) is None


def test_check_sees_a_top_still_rigged_to_the_other_generation(bridge, client):
    add_top(bridge)
    res = client.run_tool("wearable_refit", {"item": "Bardot Top"})
    assert res["footwear"] is False and res["feet"] is None
    assert res["rig"]["converted"] is False and res["rig"]["item_bones"] == "genesis8"
    assert res["rig"]["matched_share"] < 0.1 and "chestUpper" in res["rig"]["unmatched"]
    assert [p["code"] for p in res["problems"]] == ["not_converted"]


def test_convert_rebuilds_the_top_with_the_clone_and_keeps_what_hangs_from_it(bridge, client):
    add_top(bridge)
    add_top(bridge, label="Bardot Belt", skin={"abdomenUpper": 40}, fitted_to="Bardot Top")
    res = client.run_tool("wearable_refit", {"item": "Bardot Top", "action": "convert",
                                              "clone": "CloneGenesis8Female"})
    assert res["converted"] is True and res["clone"] == "CloneGenesis8Female"
    assert res["item"] == "Bardot Top" and res["after"]["converted"] is True
    assert res["fitted_items"] == ["Bardot Belt"]
    state = json.loads(bridge.state.read_text())
    transfer = state["transfers"][-1]
    assert transfer["base"] == "CloneGenesis8Female" and transfer["adjust_base"] and transfer["smooth"]
    top = [n for n in state["nodes"] if n["label"] == "Bardot Top"]
    assert len(top) == 1                                       # the old one is gone
    belt = next(n for n in state["nodes"] if n["label"] == "Bardot Belt")
    assert belt["fitted_to"] == top[0]["id"]
    again = client.run_tool("wearable_refit", {"item": "Bardot Top", "action": "convert"})
    assert again["converted"] is False and again["already"] is True
    # the belt is still Genesis 8: converting it fits it to the figure
    belt_res = client.run_tool("wearable_refit", {"item": "Bardot Belt", "action": "convert"})
    assert belt_res["converted"] is True and belt_res["clone"] == "CloneGenesis8Female"


def test_tool_rebuilds_everything_a_figure_wears(bridge, server):
    add_top(bridge)
    res = call(server, "wearable_refit", item="Genesis 9")
    assert res["figure"] == "Genesis 9" and res["verdict"] == "misplaced"
    by = {r["item"]: r for r in res["items"]}
    assert by["Bardot Top"]["problems"] == ["not_converted"]
    assert "Night Out Heels" in by
    fixed = call(server, "wearable_refit", item="Genesis 9", fix=True)
    top = next(r for r in fixed["items"] if r["item"] == "Bardot Top")
    assert top["converted"][0]["clone"] == "CloneGenesis8Female" and top["verdict"] == "ok"
    one = call(server, "wearable_refit", item="Bardot Top")
    assert one["verdict"] == "ok" and one["rig"]["converted"] is True
