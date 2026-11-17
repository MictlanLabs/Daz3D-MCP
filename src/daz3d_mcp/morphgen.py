"""Builds new shape morphs from a figure's own base mesh. Regions come from its bone weight maps
(named once for every generation: "nostril", "jaw", "belly"...) and from soft spheres placed
around landmarks found on the mesh (nose tip, outer brow, ear); simple operations (scale, move,
inflate) shape them."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Vec = tuple[float, float, float]
OpKind = Literal["scale", "move", "inflate"]
GenKey = Literal["g9", "g8"]

G8_ALL = ("Genesis 8.1 Female", "Genesis 8.1 Male", "Genesis 8 Female", "Genesis 8 Male")
ALL = ("Genesis 9", *G8_ALL)


def _both(left: str, right: str, weight: float = 1.0) -> dict[str, float]:
    return {left: weight, right: weight}


CANON: dict[str, dict[GenKey, dict[str, float]]] = {
    "nostril": {"g9": _both("l_nostril", "r_nostril"), "g8": _both("lNostril", "rNostril")},
    "nose": {"g9": {}, "g8": {"Nose": 1.0, "MidNoseBridge": 0.7}},
    "lips_upper": {"g9": {"l_lipupper": 1.0, "r_lipupper": 1.0, "lipuppermiddle": 1.0},
                   "g8": {"lLipUpperOuter": 1.0, "rLipUpperOuter": 1.0, "lLipUpperInner": 1.0,
                          "rLipUpperInner": 1.0, "LipUpperMiddle": 1.0}},
    "lips_lower": {"g9": {"l_liplower": 1.0, "r_liplower": 1.0, "liplowermiddle": 1.0},
                   "g8": {"lLipLowerOuter": 1.0, "rLipLowerOuter": 1.0, "lLipLowerInner": 1.0,
                          "rLipLowerInner": 1.0, "LipLowerMiddle": 1.0}},
    "lip_corners": {"g9": _both("l_lipcorner", "r_lipcorner"), "g8": _both("lLipCorner", "rLipCorner")},
    "philtrum": {"g9": {}, "g8": _both("lLipBelowNose", "rLipBelowNose")},
    "chin": {"g9": {"chin": 1.0}, "g8": {"Chin": 1.0, "LipBelow": 0.5}},
    "jaw": {"g9": {"lowerjaw": 1.0}, "g8": {"lowerJaw": 1.0, "BelowJaw": 0.7}},
    "cheek_lower": {"g9": _both("l_cheeklower", "r_cheeklower"),
                    "g8": {**_both("lCheekLower", "rCheekLower"), **_both("lJawClench", "rJawClench", 0.5)}},
    "cheek_upper": {"g9": _both("l_cheek", "r_cheek"), "g8": _both("lCheekUpper", "rCheekUpper")},
    "under_eye": {"g9": {**_both("l_infraorbital", "r_infraorbital"), **_both("l_squint", "r_squint", 0.5)},
                  "g8": {**_both("lSquintInner", "rSquintInner"), **_both("lSquintOuter", "rSquintOuter")}},
    "brow": {"g9": {**_both("l_browinner", "r_browinner"), **_both("l_browouter", "r_browouter"),
                    "centerbrow": 1.0},
             "g8": {**_both("lBrowInner", "rBrowInner"), **_both("lBrowMid", "rBrowMid"),
                    **_both("lBrowOuter", "rBrowOuter"), "CenterBrow": 1.0}},
    "brow_outer": {"g9": _both("l_browouter", "r_browouter"), "g8": _both("lBrowOuter", "rBrowOuter")},
    "nasolabial": {"g9": {}, "g8": {**_both("lNasolabialUpper", "rNasolabialUpper"),
                                    **_both("lNasolabialMiddle", "rNasolabialMiddle"),
                                    **_both("lNasolabialLower", "rNasolabialLower"),
                                    **_both("lLipNasolabialCrease", "rLipNasolabialCrease")}},
    "ear": {"g9": _both("l_ear", "r_ear"), "g8": _both("lEar", "rEar")},
    "head": {"g9": {"head": 1.0}, "g8": {"head": 1.0}},
    "neck": {"g9": {"neck1": 1.0, "neck2": 1.0}, "g8": {"neckLower": 1.0, "neckUpper": 1.0}},
    "hip": {"g9": {"hip": 1.0}, "g8": {"hip": 1.0}},
    "pelvis": {"g9": {"pelvis": 1.0}, "g8": {"pelvis": 1.0}},
    "belly": {"g9": {"spine1": 1.0}, "g8": {"abdomenLower": 1.0}},
    "waist": {"g9": {"spine2": 1.0}, "g8": {"abdomenUpper": 1.0}},
    "chest_low": {"g9": {"spine3": 1.0}, "g8": {"chestLower": 1.0}},
    "chest_up": {"g9": {"spine4": 1.0}, "g8": {"chestUpper": 1.0}},
    "pecs": {"g9": _both("l_pectoral", "r_pectoral"), "g8": _both("lPectoral", "rPectoral")},
    "collar": {"g9": _both("l_shoulder", "r_shoulder"), "g8": _both("lCollar", "rCollar")},
    "upperarm": {"g9": {**_both("l_upperarm", "r_upperarm"), **_both("l_upperarmtwist1", "r_upperarmtwist1"),
                        **_both("l_upperarmtwist2", "r_upperarmtwist2")},
                 "g8": {**_both("lShldrBend", "rShldrBend"), **_both("lShldrTwist", "rShldrTwist")}},
    "forearm": {"g9": {**_both("l_forearm", "r_forearm"), **_both("l_forearmtwist1", "r_forearmtwist1"),
                       **_both("l_forearmtwist2", "r_forearmtwist2")},
                "g8": {**_both("lForearmBend", "rForearmBend"), **_both("lForearmTwist", "rForearmTwist")}},
    "thigh": {"g9": {**_both("l_thigh", "r_thigh"), **_both("l_thightwist1", "r_thightwist1"),
                     **_both("l_thightwist2", "r_thightwist2")},
              "g8": {**_both("lThighBend", "rThighBend"), **_both("lThighTwist", "rThighTwist")}},
    "shin": {"g9": _both("l_shin", "r_shin"), "g8": _both("lShin", "rShin")},
}

FACE = ("nostril", "nose", "lips_upper", "lips_lower", "lip_corners", "philtrum", "chin", "jaw", "cheek_lower",
        "cheek_upper", "under_eye", "brow", "nasolabial", "head")


def gen_key(generation: str | None) -> GenKey:
    return "g9" if str(generation or "").startswith("Genesis 9") else "g8"


@dataclass(frozen=True)
class Sphere:
    landmark: str
    offset: Vec
    radii: Vec
    mirror: bool = False


@dataclass(frozen=True)
class Op:
    kind: OpKind
    bones: dict[str, float] = field(default_factory=dict)
    amount: Vec = (0.0, 0.0, 0.0)
    center: Vec | None = None
    center_at: str | None = None
    sphere: Sphere | None = None
    within: tuple[Vec, Vec] | None = None
    smooth: int = 4
    front: float = 0.0
    side_from: float | None = None


@dataclass(frozen=True)
class Recipe:
    name: str
    label: str
    group: str
    trait: str
    plus: str
    ops: tuple[Op, ...]
    smooth: int = 3
    generations: tuple[str, ...] = ALL
    peak: float | None = None


@dataclass
class Mesh:
    vertices: list[Vec]
    facets: list[tuple[int, ...]]
    weights: dict[str, dict[int, float]]
    generation: str = "Genesis 9"
    neighbors: list[set[int]] = field(default_factory=list)
    normals: list[Vec] = field(default_factory=list)
    landmarks: dict[str, Vec] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> Mesh:
        data = json.loads(path.read_text(encoding="utf-8"))
        flat = data["vertices"]
        vertices = [(flat[i], flat[i + 1], flat[i + 2]) for i in range(0, len(flat), 3)]
        fl = data["facets"]
        facets = [tuple(v for v in fl[i:i + 4] if v >= 0) for i in range(0, len(fl), 4)]
        weights = {}
        for bone, pairs in data["weights"].items():
            weights[bone] = {int(pairs[i]): float(pairs[i + 1]) for i in range(0, len(pairs), 2)}
        mesh = cls(vertices, facets, weights, str(data.get("generation") or "Genesis 9"))
        mesh.build()
        return mesh

    @property
    def key(self) -> GenKey:
        return gen_key(self.generation)

    def build(self) -> None:
        n = len(self.vertices)
        self.neighbors = [set() for _ in range(n)]
        acc = [[0.0, 0.0, 0.0] for _ in range(n)]
        for face in self.facets:
            k = len(face)
            for i in range(k):
                a, b = face[i], face[(i + 1) % k]
                self.neighbors[a].add(b)
                self.neighbors[b].add(a)
            p = [self.vertices[i] for i in face]
            nx = ny = nz = 0.0
            for i in range(k):
                x1, y1, z1 = p[i]
                x2, y2, z2 = p[(i + 1) % k]
                nx += (y1 - y2) * (z1 + z2)
                ny += (z1 - z2) * (x1 + x2)
                nz += (x1 - x2) * (y1 + y2)
            for i in face:
                acc[i][0] += nx
                acc[i][1] += ny
                acc[i][2] += nz
        self.normals = []
        for x, y, z in acc:
            length = math.sqrt(x * x + y * y + z * z) or 1.0
            self.normals.append((x / length, y / length, z / length))
        self.landmarks = self.find_landmarks()

    def bones(self, canon: dict[str, float]) -> dict[int, float]:
        out: dict[int, float] = {}
        for name, factor in canon.items():
            for bone, w0 in CANON.get(name, {}).get(self.key, {}).items():
                for idx, w in self.weights.get(bone, {}).items():
                    out[idx] = out.get(idx, 0.0) + w * w0 * factor
        return out

    def left_centroid(self, canon: str) -> Vec | None:
        region = {i: w for i, w in self.bones({canon: 1.0}).items() if self.vertices[i][0] > 0.2}
        return self.centroid(region) if region else None

    def find_landmarks(self) -> dict[str, Vec]:
        marks: dict[str, Vec] = {}
        face = self.bones({k: 1.0 for k in FACE})
        best = None
        for i, w in face.items():
            x, _, z = self.vertices[i]
            if w > 0.5 and abs(x) < 0.6 and (best is None or z > self.vertices[best][2]):
                best = i
        if best is not None:
            marks["nose_tip"] = self.vertices[best]
        for canon in ("brow_outer", "ear", "cheek_upper", "under_eye", "lip_corners"):
            c = self.left_centroid(canon)
            if c:
                marks[canon] = c
        nipple = None
        for i, w in self.bones({"pecs": 1.0}).items():
            x, _, z = self.vertices[i]
            if w > 0.6 and x > 0.5 and (nipple is None or z > self.vertices[nipple][2]):
                nipple = i
        if nipple is not None:
            marks["nipple"] = self.vertices[nipple]
        if "ear" in marks:
            ex, ey, ez = marks["ear"]
            marks["ear_root"] = (ex - 0.9, ey, ez)
        return marks

    def sphere(self, s: Sphere) -> dict[int, float]:
        base = self.landmarks.get(s.landmark)
        if base is None:
            return {}
        centers = [(base[0] + s.offset[0], base[1] + s.offset[1], base[2] + s.offset[2])]
        if s.mirror:
            centers.append((-centers[0][0], centers[0][1], centers[0][2]))
        out: dict[int, float] = {}
        rx, ry, rz = s.radii
        for i, (x, y, z) in enumerate(self.vertices):
            for cx, cy, cz in centers:
                q = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 + ((z - cz) / rz) ** 2
                if q < 1:
                    out[i] = max(out.get(i, 0.0), (1 - q) ** 2)
        return out

    def region(self, op: Op) -> dict[int, float]:
        out = self.bones(op.bones) if op.bones else {}
        if op.sphere:
            mask = self.sphere(op.sphere)
            out = {i: w * out.get(i, 0.0) for i, w in mask.items()} if op.bones else mask
        out = {i: w for i, w in out.items() if w > 0}
        if op.side_from is not None:
            out = {i: w * min(1.0, max(0.0, (abs(self.vertices[i][0]) - op.side_from) / 2.0))
                   for i, w in out.items()}
            out = {i: w for i, w in out.items() if w > 0}
        if op.within:
            lo, hi = op.within
            out = {i: w for i, w in out.items()
                   if all(lo[a] <= self.vertices[i][a] <= hi[a] for a in range(3))}
        return self.smoothed(out, op.smooth)

    def smoothed(self, values: dict[int, float], rounds: int) -> dict[int, float]:
        for _ in range(rounds):
            grown = set(values)
            for i in values:
                grown |= self.neighbors[i]
            nxt = {}
            for i in grown:
                ring = self.neighbors[i]
                total = values.get(i, 0.0) + sum(values.get(j, 0.0) for j in ring)
                v = total / (1 + len(ring))
                if abs(v) > 1e-5:
                    nxt[i] = v
            values = nxt
        return values

    def centroid(self, region: dict[int, float]) -> Vec:
        total = sum(region.values()) or 1.0
        return tuple(sum(self.vertices[i][a] * w for i, w in region.items()) / total for a in range(3))


def _center(mesh: Mesh, op: Op, region: dict[int, float], x: float) -> Vec:
    if op.center is not None:
        return op.center
    if op.center_at and op.center_at in mesh.landmarks:
        cx, cy, cz = mesh.landmarks[op.center_at]
        return (cx if x >= 0 else -cx, cy, cz)
    return mesh.centroid(region)


def build_deltas(mesh: Mesh, recipe: Recipe) -> dict[int, Vec]:
    deltas: dict[int, list[float]] = {}
    for op in recipe.ops:
        region = mesh.region(op)
        if not region:
            continue
        mid = mesh.centroid(region) if op.center is None and not op.center_at else None
        for i, w in region.items():
            x, y, z = mesh.vertices[i]
            if op.kind == "scale":
                c = mid or _center(mesh, op, region, x)
                d = [(x - c[0]) * op.amount[0], (y - c[1]) * op.amount[1], (z - c[2]) * op.amount[2]]
            elif op.kind == "move":
                d = list(op.amount)
            else:
                nx, ny, nz = mesh.normals[i]
                boost = 1 + op.front * max(0.0, nz)
                d = [nx * op.amount[0] * boost, ny * op.amount[0] * boost, nz * op.amount[0] * boost]
            acc = deltas.setdefault(i, [0.0, 0.0, 0.0])
            for a in range(3):
                acc[a] += d[a] * w
    for _ in range(recipe.smooth):
        grown = set(deltas)
        for i in deltas:
            grown |= mesh.neighbors[i]
        nxt: dict[int, list[float]] = {}
        for i in grown:
            ring = [i, *mesh.neighbors[i]]
            nxt[i] = [sum(deltas.get(j, (0.0, 0.0, 0.0))[a] for j in ring) / len(ring) for a in range(3)]
        deltas = nxt
    if recipe.peak:
        top = max((math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2) for d in deltas.values()), default=0.0)
        if top > 0:
            k = recipe.peak / top
            deltas = {i: [d[0] * k, d[1] * k, d[2] * k] for i, d in deltas.items()}
    out: dict[int, Vec] = {}
    for i, d in deltas.items():
        if abs(d[0]) + abs(d[1]) + abs(d[2]) > 1e-4:
            out[i] = (round(d[0], 5), round(d[1], 5), round(d[2], 5))
    return out


def write_deltas(path: Path, deltas: dict[int, Vec]) -> None:
    flat: list[float] = []
    for i in sorted(deltas):
        flat += [i, *deltas[i]]
    path.write_text(json.dumps(flat), encoding="utf-8")


def read_vertices(path: Path) -> list[Vec]:
    flat = json.loads(path.read_text(encoding="utf-8"))["vertices"]
    return [(flat[i], flat[i + 1], flat[i + 2]) for i in range(0, len(flat), 3)]


class Grid:
    def __init__(self, points: list[Vec], cell: float = 1.5):
        self.cell = cell
        self.points = points
        self.cells: dict[tuple[int, int, int], list[int]] = {}
        for i, p in enumerate(points):
            self.cells.setdefault(self.key(p), []).append(i)

    def key(self, p: Vec) -> tuple[int, int, int]:
        return (math.floor(p[0] / self.cell), math.floor(p[1] / self.cell), math.floor(p[2] / self.cell))

    def nearest(self, p: Vec, k: int, reach: int = 4) -> list[tuple[float, int]]:
        cx, cy, cz = self.key(p)
        found: list[tuple[float, int]] = []
        for r in range(reach + 1):
            shell = [(cx + dx, cy + dy, cz + dz) for dx in range(-r, r + 1) for dy in range(-r, r + 1)
                     for dz in range(-r, r + 1) if max(abs(dx), abs(dy), abs(dz)) == r]
            for c in shell:
                for i in self.cells.get(c, ()):
                    q = self.points[i]
                    found.append(((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2, i))
            if len(found) >= k and r >= 1:
                break
        found.sort()
        return found[:k]


def project(body: list[Vec], deltas: dict[int, Vec], item: list[Vec], k: int = 4,
            falloff: float = 6.0) -> dict[int, Vec]:
    moving = sorted(deltas)
    if not moving:
        return {}
    margin = 3 * falloff
    lo = [min(body[i][a] for i in moving) - margin for a in range(3)]
    hi = [max(body[i][a] for i in moving) + margin for a in range(3)]
    grid = Grid(body)
    out: dict[int, Vec] = {}
    for vi, p in enumerate(item):
        if not all(lo[a] <= p[a] <= hi[a] for a in range(3)):
            continue
        near = grid.nearest(p, k)
        if not near:
            continue
        total = 0.0
        acc = [0.0, 0.0, 0.0]
        for d2, bi in near:
            w = 1.0 / (math.sqrt(d2) + 0.05)
            total += w
            d = deltas.get(bi)
            if d:
                acc[0] += d[0] * w
                acc[1] += d[1] * w
                acc[2] += d[2] * w
        fade = math.exp(-math.sqrt(near[0][0]) / falloff)
        v = (acc[0] / total * fade, acc[1] / total * fade, acc[2] / total * fade)
        if abs(v[0]) + abs(v[1]) + abs(v[2]) > 1e-4:
            out[vi] = (round(v[0], 5), round(v[1], 5), round(v[2], 5))
    return out


LIPS = {"lips_upper": -1.5, "lips_lower": -1.5, "lip_corners": -1.5}
MOUTH = {"lips_upper": 1.0, "lips_lower": 1.0, "lip_corners": 1.0}
FACE_FLESH = {"cheek_upper": 1.0, "cheek_lower": 1.0, "chin": 0.8, "jaw": 0.7, "head": 0.25}
BODY_FAT = {"pelvis": 1.6, "hip": 1.2, "belly": 2.2, "waist": 1.6, "chest_low": 1.0, "chest_up": 0.7,
            "thigh": 1.6, "shin": 0.7, "upperarm": 1.0, "forearm": 0.5, "collar": 0.6, "neck": 0.65}
MUSCLE = {"upperarm": 1.0, "forearm": 0.6, "collar": 0.9, "pecs": 1.0, "chest_up": 0.5, "thigh": 0.8,
          "shin": 0.6, "neck": 0.7}
NOSE_GROUP = "/Actor/Head/Face/Nose/Daz3D-MCP"
FACE_GROUP = "/Actor/Head/Face/Daz3D-MCP"
JAW_GROUP = "/Actor/Head/Face/Cheeks and Jaw/Daz3D-MCP"
BODY_GROUP = "/Actor/Full Body/Daz3D-MCP"
CHEST_GROUP = "/Actor/Chest/Daz3D-MCP"


PEAKS = {"nose_width": 0.5, "nose_size": 0.45, "nose_length": 0.45, "nose_bridge": 0.35, "nose_tip_up": 0.3,
         "philtrum": 0.35, "temples": 0.35, "eye_bags": 0.22, "cheekbones": 0.35, "chin_length": 0.45,
         "chin_forward": 0.45, "jaw_width": 0.6, "jaw_definition": 0.4, "lips_fullness": 0.3, "ears_size": 0.55,
         "ears_out": 0.7, "age": 0.45, "weight": 4.0, "muscle": 1.0, "belly": 3.0, "bust": 3.2,
         "breast_shape": 1.8, "areola_size": 0.45, "nipple_projection": 0.4}


def _r(name: str, label: str, group: str, trait: str, plus: str, *ops: Op, smooth: int = 3) -> Recipe:
    return Recipe(name, label, group, trait, plus, ops, smooth, peak=PEAKS.get(trait))


RECIPES: dict[str, Recipe] = {r.trait: r for r in [
    _r("DazMcp_NoseWidth", "MCP Nose Width", NOSE_GROUP, "nose_width", "wider nose",
       Op("scale", {"nostril": 1.0, "nose": 0.4}, (0.35, 0.0, 0.0), center=(0.0, 0.0, 0.0), smooth=3)),
    _r("DazMcp_NoseSize", "MCP Nose Size", NOSE_GROUP, "nose_size", "bigger nose",
       Op("scale", amount=(0.22, 0.22, 0.22), center_at="nose_tip",
          sphere=Sphere("nose_tip", (0.0, 1.2, -1.6), (2.0, 3.0, 2.4)), smooth=2)),
    _r("DazMcp_NoseLength", "MCP Nose Length", NOSE_GROUP, "nose_length", "longer nose, lower tip",
       Op("move", amount=(0.0, -0.45, 0.15), sphere=Sphere("nose_tip", (0.0, 0.0, -0.4), (1.6, 1.6, 2.0)),
          smooth=2)),
    _r("DazMcp_NoseBridge", "MCP Nose Bridge", NOSE_GROUP, "nose_bridge", "higher nose bridge",
       Op("move", amount=(0.0, 0.0, 0.3), sphere=Sphere("nose_tip", (0.0, 2.6, -1.6), (0.9, 2.2, 1.6)),
          smooth=2)),
    _r("DazMcp_NoseTipUp", "MCP Nose Tip Up", NOSE_GROUP, "nose_tip_up", "upturned nose tip",
       Op("move", amount=(0.0, 0.3, -0.12), sphere=Sphere("nose_tip", (0.0, -0.2, -0.3), (1.3, 1.3, 1.7)),
          smooth=2)),
    _r("DazMcp_Philtrum", "MCP Philtrum", FACE_GROUP, "philtrum", "longer space between nose and lip",
       Op("move", {**MOUTH, "philtrum": 0.5, "chin": 0.3}, (0.0, -0.3, 0.0), smooth=3)),
    _r("DazMcp_Temples", "MCP Temples", FACE_GROUP, "temples", "fuller temples",
       Op("inflate", amount=(0.35, 0.0, 0.0),
          sphere=Sphere("brow_outer", (1.6, 1.6, -3.4), (2.0, 2.8, 2.6), mirror=True), smooth=3)),
    _r("DazMcp_EyeBags", "MCP Eye Bags", FACE_GROUP, "eye_bags", "bags under the eyes",
       Op("inflate", {"under_eye": 1.0}, (0.18, 0.0, 0.0), smooth=2),
       Op("move", {"under_eye": 1.0}, (0.0, -0.06, 0.0), smooth=2)),
    _r("DazMcp_Cheekbones", "MCP Cheekbones", FACE_GROUP, "cheekbones", "higher, fuller cheekbones",
       Op("inflate", {"cheek_upper": 1.0}, (0.28, 0.0, 0.0), smooth=3),
       Op("move", {"cheek_upper": 1.0}, (0.0, 0.12, 0.0), smooth=3)),
    _r("DazMcp_ChinLength", "MCP Chin Length", JAW_GROUP, "chin_length", "longer chin",
       Op("move", {"chin": 1.0, "jaw": 0.25, **LIPS}, (0.0, -0.45, 0.0), smooth=3)),
    _r("DazMcp_ChinForward", "MCP Chin Forward", JAW_GROUP, "chin_forward", "chin juts forward",
       Op("move", {"chin": 1.0, **LIPS}, (0.0, 0.0, 0.45), smooth=3)),
    _r("DazMcp_JawWidth", "MCP Jaw Width", JAW_GROUP, "jaw_width", "wider jaw",
       Op("scale", {"jaw": 1.0, "cheek_lower": 0.8, **LIPS}, (0.14, 0.0, 0.0), center=(0.0, 0.0, 0.0),
          smooth=4)),
    _r("DazMcp_JawDefinition", "MCP Jaw Definition", JAW_GROUP, "jaw_definition", "sharper, more angular jawline",
       Op("scale", {"jaw": 1.0, "cheek_lower": 0.2, **LIPS}, (0.06, 0.0, 0.0), center=(0.0, 0.0, 0.0),
          smooth=3, side_from=3.5),
       Op("move", {"jaw": 1.0, **LIPS}, (0.0, -0.35, -0.15), smooth=3, side_from=3.0),
       Op("inflate", {"cheek_lower": 1.0, **LIPS}, (-0.15, 0.0, 0.0), smooth=3)),
    _r("DazMcp_LipsFullness", "MCP Lips Fullness", FACE_GROUP, "lips_fullness", "fuller lips",
       Op("inflate", {"lips_upper": 1.0, "lips_lower": 1.0, "lip_corners": 0.4}, (0.16, 0.0, 0.0), smooth=1),
       smooth=1),
    _r("DazMcp_EarsSize", "MCP Ears Size", FACE_GROUP, "ears_size", "bigger ears",
       Op("scale", {"ear": 1.0}, (0.25, 0.25, 0.25), center_at="ear_root", smooth=2)),
    _r("DazMcp_EarsOut", "MCP Ears Out", FACE_GROUP, "ears_out", "ears stick out",
       Op("scale", {"ear": 1.0}, (0.45, 0.0, 0.0), center_at="ear_root", smooth=2)),
    _r("DazMcp_Age", "MCP Age", FACE_GROUP, "age", "older face",
       Op("inflate", {"under_eye": 1.0}, (0.12, 0.0, 0.0), smooth=2),
       Op("move", {"under_eye": 1.0, "cheek_lower": 1.0, "nasolabial": 0.6}, (0.0, -0.25, 0.0), smooth=3),
       Op("inflate", {"cheek_lower": 1.0}, (0.08, 0.0, 0.0), smooth=3),
       Op("inflate", amount=(-0.22, 0.0, 0.0),
          sphere=Sphere("brow_outer", (1.6, 1.6, -3.4), (2.0, 2.8, 2.6), mirror=True), smooth=3),
       Op("inflate", {"cheek_upper": 1.0}, (-0.12, 0.0, 0.0), smooth=3),
       Op("move", {"lip_corners": 1.0}, (0.0, -0.12, 0.0), smooth=2),
       Op("inflate", {"lips_upper": 1.0, "lips_lower": 1.0}, (-0.06, 0.0, 0.0), smooth=1),
       Op("move", {"brow": 1.0}, (0.0, -0.12, 0.0), smooth=2),
       Op("move", amount=(0.0, -0.15, 0.0), sphere=Sphere("nose_tip", (0.0, 0.0, -0.4), (1.5, 1.5, 1.8)),
          smooth=2)),
    _r("DazMcp_Weight", "MCP Weight", BODY_GROUP, "weight", "heavier body",
       Op("inflate", BODY_FAT, (1.2, 0.0, 0.0), smooth=6, front=0.8),
       Op("inflate", FACE_FLESH, (0.35, 0.0, 0.0), smooth=4), smooth=4),
    _r("DazMcp_Muscle", "MCP Muscle", BODY_GROUP, "muscle", "more muscular (bulk)",
       Op("inflate", MUSCLE, (0.8, 0.0, 0.0), smooth=6),
       Op("inflate", {"belly": 1.0, "waist": 0.6}, (-0.35, 0.0, 0.0), smooth=5), smooth=4),
    _r("DazMcp_Bust", "MCP Bust", CHEST_GROUP, "bust", "larger breasts",
       Op("inflate", amount=(1.0, 0.0, 0.0), sphere=Sphere("nipple", (-0.3, 0.6, -2.5), (6.5, 6.5, 6.0), mirror=True),
          smooth=4, front=1.2),
       Op("move", amount=(0.0, -0.25, 0.0), sphere=Sphere("nipple", (0.0, -1.0, 0.0), (6.0, 5.0, 5.0), mirror=True),
          smooth=4), smooth=4),
    _r("DazMcp_BreastPerk", "MCP Breast Perk", CHEST_GROUP, "breast_shape", "perkier, higher breasts",
       Op("move", amount=(0.0, 1.0, 0.25), sphere=Sphere("nipple", (0.0, -0.8, 0.0), (6.0, 6.0, 6.0), mirror=True),
          smooth=4), smooth=4),
    _r("DazMcp_AreolaSize", "MCP Areola Size", CHEST_GROUP, "areola_size", "larger areolas",
       Op("scale", amount=(0.4, 0.4, 0.0), center_at="nipple",
          sphere=Sphere("nipple", (0.0, 0.0, 0.0), (1.8, 1.8, 1.5), mirror=True), smooth=1), smooth=1),
    _r("DazMcp_NippleProjection", "MCP Nipple Projection", CHEST_GROUP, "nipple_projection", "nipples project more",
       Op("move", amount=(0.0, 0.0, 0.3), sphere=Sphere("nipple", (0.0, 0.0, 0.0), (0.7, 0.7, 1.2), mirror=True),
          smooth=1), smooth=1),
    _r("DazMcp_Belly", "MCP Belly", BODY_GROUP, "belly", "round belly",
       Op("inflate", {"belly": 1.5, "pelvis": 0.5, "waist": 0.8}, (1.0, 0.0, 0.0), smooth=6, front=1.5),
       smooth=4),
]}


UNITS = {"cm": 1.0, "m": 0.01, "mm": 10.0}


def write_obj(path: Path, mesh: Mesh, units: str = "cm") -> None:
    k = UNITS[units]
    lines = [f"# {mesh.generation} base mesh, {len(mesh.vertices)} vertices, {units}, Y up"]
    lines += [f"v {x * k:.5f} {y * k:.5f} {z * k:.5f}" for x, y, z in mesh.vertices]
    lines += ["f " + " ".join(str(i + 1) for i in face) for face in mesh.facets]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_obj_vertices(path: Path) -> list[Vec]:
    out: list[Vec] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("v "):
                parts = line.split()
                out.append((float(parts[1]), float(parts[2]), float(parts[3])))
    return out


def _height(points: list[Vec], axis: int) -> float:
    vals = [p[axis] for p in points]
    return (max(vals) - min(vals)) or 1.0


SNAP = (1.0, 10.0, 100.0, 1000.0, 0.1, 0.01, 2.54, 1 / 2.54)


def sculpt_deltas(base: list[Vec], sculpt: list[Vec], threshold: float = 0.01) -> tuple[dict[int, Vec], dict]:
    if len(base) != len(sculpt):
        raise ValueError(f"The OBJ has {len(sculpt)} vertices; the base mesh has {len(base)}. Export and sculpt the "
                         "base resolution without adding or removing vertices.")
    candidates = {"y_up": lambda p: p, "z_up": lambda p: (p[0], p[2], -p[1])}
    best = None
    for name, turn in candidates.items():
        turned = [turn(p) for p in sculpt]
        scale = _height(base, 1) / _height(turned, 1)
        scale = next((k for k in SNAP if abs(scale / k - 1) < 0.01), scale)
        moved = [(x * scale, y * scale, z * scale) for x, y, z in turned]
        sample = range(0, len(base), max(1, len(base) // 2000))
        err = sorted(math.dist(base[i], moved[i]) for i in sample)
        median = err[len(err) // 2]
        if best is None or median < best[0]:
            best = (median, name, scale, moved)
    median, axis, scale, moved = best
    if median > 1.0:
        raise ValueError(f"The OBJ does not line up with the base mesh (median distance {median:.2f} cm after "
                         "matching size and axes). Keep the vertex order and the base pose and shape.")
    deltas: dict[int, Vec] = {}
    for i, (b, s) in enumerate(zip(base, moved)):
        d = (s[0] - b[0], s[1] - b[1], s[2] - b[2])
        if abs(d[0]) + abs(d[1]) + abs(d[2]) > threshold:
            deltas[i] = (round(d[0], 5), round(d[1], 5), round(d[2], 5))
    return deltas, {"axis": axis, "scale": round(scale, 6), "median_offset_cm": round(median, 4)}
