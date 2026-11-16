"""Builds new shape morphs from a figure's own base mesh: regions come from its bone weight maps
(nose, jaw, cheeks, belly...), and simple operations (scale, move, inflate) shape them."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Vec = tuple[float, float, float]
OpKind = Literal["scale", "move", "inflate"]


@dataclass(frozen=True)
class Op:
    kind: OpKind
    bones: dict[str, float]
    amount: Vec = (0.0, 0.0, 0.0)
    center: Vec | None = None
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
    generations: tuple[str, ...] = ("Genesis 9",)


@dataclass
class Mesh:
    vertices: list[Vec]
    facets: list[tuple[int, ...]]
    weights: dict[str, dict[int, float]]
    neighbors: list[set[int]] = field(default_factory=list)
    normals: list[Vec] = field(default_factory=list)

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
        mesh = cls(vertices, facets, weights)
        mesh.build()
        return mesh

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

    def region(self, bones: dict[str, float], within: tuple[Vec, Vec] | None, smooth: int,
               side_from: float | None = None) -> dict[int, float]:
        out: dict[int, float] = {}
        for bone, factor in bones.items():
            for idx, w in self.weights.get(bone, {}).items():
                out[idx] = out.get(idx, 0.0) + w * factor
        out = {i: w for i, w in out.items() if w > 0}
        if side_from is not None:
            out = {i: w * min(1.0, max(0.0, (abs(self.vertices[i][0]) - side_from) / 2.0)) for i, w in out.items()}
            out = {i: w for i, w in out.items() if w > 0}
        if within:
            lo, hi = within
            out = {i: w for i, w in out.items()
                   if all(lo[a] <= self.vertices[i][a] <= hi[a] for a in range(3))}
        return self.smoothed(out, smooth)

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


def build_deltas(mesh: Mesh, recipe: Recipe) -> dict[int, Vec]:
    deltas: dict[int, list[float]] = {}
    for op in recipe.ops:
        region = mesh.region(op.bones, op.within, op.smooth, op.side_from)
        center = op.center or mesh.centroid(region)
        for i, w in region.items():
            x, y, z = mesh.vertices[i]
            if op.kind == "scale":
                d = [(x - center[0]) * op.amount[0], (y - center[1]) * op.amount[1], (z - center[2]) * op.amount[2]]
            elif op.kind == "move":
                d = list(op.amount)
            else:
                nx, ny, nz = mesh.normals[i]
                boost = 1 + op.front * max(0.0, nz)
                d = [nx * op.amount[0] * boost, ny * op.amount[0] * boost, nz * op.amount[0] * boost]
            acc = deltas.setdefault(i, [0.0, 0.0, 0.0])
            for a in range(3):
                acc[a] += d[a] * w
    out: dict[int, Vec] = {}
    for _ in range(recipe.smooth):
        grown = set(deltas)
        for i in deltas:
            grown |= mesh.neighbors[i]
        nxt: dict[int, list[float]] = {}
        for i in grown:
            ring = [i, *mesh.neighbors[i]]
            nxt[i] = [sum(deltas.get(j, (0.0, 0.0, 0.0))[a] for j in ring) / len(ring) for a in range(3)]
        deltas = nxt
    for i, d in deltas.items():
        if abs(d[0]) + abs(d[1]) + abs(d[2]) > 1e-4:
            out[i] = (round(d[0], 5), round(d[1], 5), round(d[2], 5))
    return out


def write_deltas(path: Path, deltas: dict[int, Vec]) -> None:
    flat: list[float] = []
    for i in sorted(deltas):
        flat += [i, *deltas[i]]
    path.write_text(json.dumps(flat), encoding="utf-8")


LIPS = {"l_lipcorner": -1.5, "r_lipcorner": -1.5, "l_liplower": -1.5, "r_liplower": -1.5, "liplowermiddle": -1.5,
        "l_lipupper": -1.5, "r_lipupper": -1.5, "lipuppermiddle": -1.5}
FACE_FLESH = {"l_cheek": 1.0, "r_cheek": 1.0, "l_cheeklower": 1.0, "r_cheeklower": 1.0, "chin": 0.8,
              "lowerjaw": 0.7, "head": 0.25}
BODY_FAT = {"pelvis": 1.6, "hip": 1.2, "spine1": 2.2, "spine2": 1.6, "spine3": 1.0, "spine4": 0.7,
            "l_thigh": 1.6, "r_thigh": 1.6, "l_shin": 0.7, "r_shin": 0.7, "l_upperarm": 1.0, "r_upperarm": 1.0,
            "l_forearm": 0.5, "r_forearm": 0.5, "l_shoulder": 0.6, "r_shoulder": 0.6, "neck1": 0.8, "neck2": 0.5}

RECIPES: dict[str, Recipe] = {r.trait: r for r in [
    Recipe("DazMcp_NoseWidth", "MCP Nose Width", "/Actor/Head/Face/Nose/Daz3D-MCP", "nose_width", "wider nose",
           (Op("scale", {"l_nostril": 1.0, "r_nostril": 1.0}, (0.35, 0.0, 0.0), center=(0.0, 0.0, 0.0),
               smooth=3),)),
    Recipe("DazMcp_JawWidth", "MCP Jaw Width", "/Actor/Head/Face/Cheeks and Jaw/Daz3D-MCP",
           "jaw_width", "wider jaw",
           (Op("scale", {"lowerjaw": 1.0, "l_cheeklower": 0.8, "r_cheeklower": 0.8, **LIPS}, (0.14, 0.0, 0.0),
               center=(0.0, 0.0, 0.0), smooth=4),)),
    Recipe("DazMcp_JawDefinition", "MCP Jaw Definition", "/Actor/Head/Face/Cheeks and Jaw/Daz3D-MCP",
           "jaw_definition", "sharper, more angular jawline",
           (Op("scale", {"lowerjaw": 1.0, "l_cheeklower": 0.2, "r_cheeklower": 0.2, **LIPS}, (0.06, 0.0, 0.0),
               center=(0.0, 0.0, 0.0), smooth=3, side_from=3.5),
            Op("move", {"lowerjaw": 1.0, **LIPS}, (0.0, -0.35, -0.15), smooth=3, side_from=3.0),
            Op("inflate", {"l_cheeklower": 1.0, "r_cheeklower": 1.0, **LIPS}, (-0.15, 0.0, 0.0), smooth=3))),
    Recipe("DazMcp_Weight", "MCP Weight", "/Actor/Full Body/Daz3D-MCP", "weight", "heavier body",
           (Op("inflate", BODY_FAT, (1.2, 0.0, 0.0), smooth=6, front=0.8),
            Op("inflate", FACE_FLESH, (0.35, 0.0, 0.0), smooth=4)), smooth=4),
]}


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
