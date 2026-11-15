"""Clothing made for one Genesis generation worn by another.

Daz's Auto-Fit converts such an item (Genesis 8 shoes on Genesis 9) by
projecting the new figure's rigging onto it. Two things get lost on the way:

* the pose the item needs. A heeled shoe's own file poses the feet
  ("lFoot" 26 degrees, "lToe" -35), but with the bone names of the generation
  it was made for; on another generation Daz finds no such bones and skips
  them without a word, so the foot stays flat and goes through the shoe.
* the weights its author painted. The projected ones follow the skin, not the
  shoe: a rigid sole bends with the wrong bones.

This module reads what the item's files say (pose and authored weights) and
translates the bone names; wearable_refit.dsa applies it in Daz Studio.
"""

from __future__ import annotations

import gzip
import json
import re
from pathlib import Path
from urllib.parse import unquote

# Genesis 3 / 8 / 8.1 bone -> Genesis 9 bone, for the left side ("l" + name
# -> "l_" + name). Genesis 8 has foot > metatarsals > toe; on Genesis 9 the
# metatarsal is a leaf beside the toes, so what hung from the metatarsals
# belongs to the foot.
_G8_TO_G9_SIDE = {
    "Foot": "foot", "Metatarsals": "foot", "Toe": "toes",
    "BigToe": "bigtoe1", "BigToe_2": "bigtoe2",
    "SmallToe1": "indextoe1", "SmallToe1_2": "indextoe2",
    "SmallToe2": "midtoe1", "SmallToe2_2": "midtoe2",
    "SmallToe3": "ringtoe1", "SmallToe3_2": "ringtoe2",
    "SmallToe4": "pinkytoe1", "SmallToe4_2": "pinkytoe2",
    "Shin": "shin", "ThighBend": "thigh", "Hand": "hand",
}
_G8_TO_G9_CENTER = {"hip": "hip", "pelvis": "pelvis", "head": "head"}
# Going back, each Genesis 9 bone takes the first Genesis 8 bone that maps to it.
_G9_TO_G8_SIDE: dict[str, str] = {}
for _g8, _g9 in _G8_TO_G9_SIDE.items():
    _G9_TO_G8_SIDE.setdefault(_g9, _g8)
_G9_TO_G8_SIDE["metatarsal"] = "Metatarsals"

FOOT_BONE = re.compile(r"foot|toe|metatars", re.I)


def bone_style(names) -> str | None:
    """"genesis9" (l_foot) or "genesis8" (lFoot, also Genesis 3 and 8.1), from bone names."""
    names = set(names)
    if names & {"l_foot", "r_foot", "l_hand", "l_thigh"}:
        return "genesis9"
    if names & {"lFoot", "rFoot", "lHand", "lThighBend"}:
        return "genesis8"
    return None


def map_bone(name: str, to_style: str) -> str | None:
    """The bone of the other generation that does this bone's job, or None."""
    if to_style == "genesis9":
        if name in _G8_TO_G9_CENTER:
            return _G8_TO_G9_CENTER[name]
        m = re.match(r"^([lr])([A-Z]\w*)$", name)
        if m and m.group(2) in _G8_TO_G9_SIDE:
            return f"{m.group(1)}_{_G8_TO_G9_SIDE[m.group(2)]}"
        return None
    if to_style == "genesis8":
        if name in _G8_TO_G9_CENTER.values():
            return name
        m = re.match(r"^([lr])_(\w+)$", name)
        if m and m.group(2) in _G9_TO_G8_SIDE:
            return f"{m.group(1)}{_G9_TO_G8_SIDE[m.group(2)]}"
        return None
    return None


def read_dson(path: Path) -> dict:
    """A .duf or .dsf file: JSON, often gzip-compressed."""
    data = Path(path).read_bytes()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return json.loads(data.decode("utf-8-sig"))


_ROT_URL = re.compile(r"^(?:name://@selection/)?([^:/?#]+):[^?]*\?rotation/([xyz])/value$")


def file_pose(doc: dict) -> dict[str, list[float]]:
    """Bone rotations a wearable or pose file sets at its first key: {bone: [x, y, z]},
    only bones it turns more than half a degree."""
    own = {n.get("id") for n in (doc.get("scene") or {}).get("nodes", []) if "conform_target" in n}
    pose: dict[str, list[float]] = {}
    for anim in (doc.get("scene") or {}).get("animations", []):
        m = _ROT_URL.match(unquote(str(anim.get("url", ""))))
        keys = anim.get("keys") or []
        if not m or not keys or m.group(1) in own:
            continue
        try:
            value = float(keys[0][1])
        except (TypeError, ValueError, IndexError):
            continue
        pose.setdefault(m.group(1), [0.0, 0.0, 0.0])["xyz".index(m.group(2))] = value
    return {b: v for b, v in pose.items() if max(abs(x) for x in v) > 0.5}


def translate_pose(pose: dict[str, list[float]], to_style: str) -> tuple[dict[str, list[float]], list[str]]:
    """The pose with the other generation's bone names; also the bones with no counterpart.
    Two bones that land on one (metatarsals and foot) add up."""
    out: dict[str, list[float]] = {}
    skipped: list[str] = []
    for bone, rot in pose.items():
        own = r"^[lr]_[a-z]" if to_style == "genesis9" else r"^[lr][A-Z]"
        if re.match(own, bone):
            target = bone
        else:
            target = map_bone(bone, to_style)
        if not target:
            skipped.append(bone)
            continue
        cur = out.setdefault(target, [0.0, 0.0, 0.0])
        for i in range(3):
            cur[i] = round(cur[i] + rot[i], 3)
    return out, skipped


def figure_assets(doc: dict) -> list[dict]:
    """The fitted figures a wearable file loads: [{label, name, dsf, node}], dsf relative to
    a content library ("data/.../Shoes.dsf")."""
    out = []
    for node in (doc.get("scene") or {}).get("nodes", []):
        url = unquote(str(node.get("url", "")))
        if "conform_target" not in node or ".dsf#" not in url:
            continue
        path, _, frag = url.partition("#")
        out.append({"label": node.get("label") or node.get("name"), "name": node.get("name") or node.get("id"),
                    "dsf": path.lstrip("/"), "node": frag})
    return out


def resolve_asset(relative: str, libraries) -> Path | None:
    """Finds data/... in the content libraries, whatever the letter case of the folders."""
    for lib in libraries:
        cur = Path(lib)
        for part in Path(relative).parts:
            nxt = cur / part
            if not nxt.exists():
                try:
                    nxt = next((c for c in cur.iterdir() if c.name.lower() == part.lower()), None)
                except OSError:
                    nxt = None
                if nxt is None:
                    break
            cur = nxt
        else:
            if cur.is_file():
                return cur
    return None


def authored_weights(dsf: dict) -> tuple[dict[str, list[list[float]]], int]:
    """The skin weights an item's .dsf holds: ({bone: [[vertex, weight], ...]}, vertex count)."""
    for mod in dsf.get("modifier_library", []):
        skin = mod.get("skin")
        if not skin:
            continue
        weights = {}
        for joint in skin.get("joints", []):
            values = (joint.get("node_weights") or {}).get("values") or []
            if values:
                weights[joint.get("id") or unquote(str(joint.get("node", ""))).lstrip("#")] = values
        return weights, int(skin.get("vertex_count") or 0)
    return {}, 0


def translate_weights(weights: dict[str, list[list[float]]], to_style: str
                      ) -> tuple[dict[str, list[list[float]]] | None, str | None]:
    """Authored weights under the other generation's bone names, merged where two bones
    become one. None (and why) when the item is not just footwear: legs and bodies have
    twist bones that do not translate one to one, and there Auto-Fit's weights are fine."""
    if not weights:
        return None, "The item's file holds no skin weights."
    if bone_style(weights) == to_style:
        return None, "The item already uses this figure's bone names."
    not_feet = [b for b in weights if not FOOT_BONE.search(b)]
    if not_feet:
        return None, ("It is also weighted to " + ", ".join(sorted(not_feet)[:4]) +
                      ": only footwear weights are translated.")
    merged: dict[str, dict[int, float]] = {}
    for bone, values in weights.items():
        target = map_bone(bone, to_style)
        if not target:
            return None, f"No bone on this figure does the job of {bone}."
        acc = merged.setdefault(target, {})
        for index, weight in values:
            acc[int(index)] = acc.get(int(index), 0.0) + float(weight)
    return {b: [[i, round(w, 5)] for i, w in sorted(acc.items())] for b, acc in merged.items()}, None


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def matches_item(doc: dict, item_label: str, item_name: str | None = None) -> dict | None:
    """The fitted figure of a wearable file that is this scene item (Daz numbers duplicate
    labels: "Canvas Sneakers (2)")."""
    label = _norm(re.sub(r"\s*\(\d+\)$", "", item_label))
    name = _norm(item_name or "")
    for asset in figure_assets(doc):
        if (name and _norm(asset["name"]) == name) or _norm(asset["label"]) == label:
            return asset
    return None
