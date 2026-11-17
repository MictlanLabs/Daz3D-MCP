"""Soft-body contact baked into shape morphs. Each frame, the skin of a soft region (a breast, a
belly, a thigh) that the hand or another body part has entered is pushed back to that part's
surface, the push spreads into the flesh around it, the flesh beside the dent bulges out to keep
its volume, and a damped spring gives the flesh inertia: it lags, overshoots when released and
settles. The result is one displacement per vertex per frame, which the bake turns into one morph
per frame keyed on its frame only."""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

from daz3d_mcp.morphgen import Grid, Mesh, Vec

HAND_BONES = ("hand", "indexmetacarpal", "midmetacarpal", "ringmetacarpal", "pinkymetacarpal", "index1", "index2",
              "index3", "mid1", "mid2", "mid3", "ring1", "ring2", "ring3", "pinky1", "pinky2", "pinky3", "thumb1",
              "thumb2", "thumb3")
G8_HAND = {"hand": "Hand", "indexmetacarpal": "Carpal1", "midmetacarpal": "Carpal2", "ringmetacarpal": "Carpal3",
           "pinkymetacarpal": "Carpal4", "index1": "Index1", "index2": "Index2", "index3": "Index3", "mid1": "Mid1",
           "mid2": "Mid2", "mid3": "Mid3", "ring1": "Ring1", "ring2": "Ring2", "ring3": "Ring3", "pinky1": "Pinky1",
           "pinky2": "Pinky2", "pinky3": "Pinky3", "thumb1": "Thumb1", "thumb2": "Thumb2", "thumb3": "Thumb3"}


def hand_bones(mesh: Mesh, side: str) -> list[str]:
    if mesh.key == "g9":
        return [f"{side[0]}_{b}" for b in HAND_BONES]
    return [f"{side[0]}{G8_HAND[b]}" for b in HAND_BONES]


def hand_vertices(mesh: Mesh, side: str, threshold: float = 0.3) -> list[int]:
    total: dict[int, float] = {}
    for bone in hand_bones(mesh, side):
        for i, w in mesh.weights.get(bone, {}).items():
            total[i] = total.get(i, 0.0) + w
    return sorted(i for i, w in total.items() if w >= threshold)


def breast_softness(mesh: Mesh, sides: tuple[str, ...] = ("left", "right"), radius: float = 13.0) -> dict[int, float]:
    """How soft each vertex is (0 firm to 1 fully soft): the pectoral weight map faded by the
    distance from the nipple, so the breast moves and the ribcage and collarbone do not."""
    pecs = mesh.bones({"pecs": 1.0})
    nipple = mesh.landmarks.get("nipple")
    if nipple is None:
        return {}
    out: dict[int, float] = {}
    for side in sides:
        sign = 1.0 if side == "left" else -1.0
        cx, cy, cz = sign * abs(nipple[0]), nipple[1], nipple[2]
        for i, w in pecs.items():
            x, y, z = mesh.vertices[i]
            if x * sign <= 0:
                continue
            d = math.dist((x, y, z), (cx, cy, cz))
            s = min(1.0, w) * min(1.0, max(0.0, 1.4 * (1 - d / radius)))
            if s > 0.01:
                out[i] = max(out.get(i, 0.0), s ** 0.8)
    return out


def posed_normals(mesh: Mesh, pos: dict[int, Vec], verts: list[int]) -> dict[int, Vec]:
    """Vertex normals of the posed surface around the given vertices."""
    want = set(verts)
    acc: dict[int, list[float]] = {i: [0.0, 0.0, 0.0] for i in verts}
    for face in mesh.facets:
        if not any(i in want for i in face) or not all(i in pos for i in face):
            continue
        k = len(face)
        nx = ny = nz = 0.0
        for a in range(k):
            x1, y1, z1 = pos[face[a]]
            x2, y2, z2 = pos[face[(a + 1) % k]]
            nx += (y1 - y2) * (z1 + z2)
            ny += (z1 - z2) * (x1 + x2)
            nz += (x1 - x2) * (y1 + y2)
        for i in face:
            if i in acc:
                acc[i][0] += nx
                acc[i][1] += ny
                acc[i][2] += nz
    out = {}
    for i, (x, y, z) in acc.items():
        n = math.sqrt(x * x + y * y + z * z) or 1.0
        out[i] = (x / n, y / n, z / n)
    return out


@dataclass
class Settings:
    gap: float = 0.08            # cm left between skin and hand
    reach: float = 4.0           # cm; nearest hand point farther than this is no contact
    spread: int = 5              # rounds the dent spreads into the flesh around it
    bulge: float = 0.35          # share of the pushed-in depth that comes back out around the dent
    bulge_radius: float = 4.0    # cm from the dent where the bulge peaks
    stiffness: float = 0.3       # spring pull per frame (higher = snappier flesh)
    damping: float = 0.33        # spring loss per frame (lower = more wobble)
    sag: float = 0.2            # cm the whole breast drops per cm of press depth (then bounces)
    sag_stiffness: float = 0.22
    sag_damping: float = 0.22
    subd_boost: float = 1.15     # SubD smooths cage moves; push the cage a little more


def contact_targets(mesh: Mesh, soft: dict[int, float], hand: list[int], pos: dict[int, Vec],
                    settings: Settings) -> tuple[dict[int, list[float]], set[int], float]:
    """Where each soft vertex has to be this frame (world-space offsets), which ones touch the hand,
    and how deep the press is."""
    hand_n = posed_normals(mesh, pos, hand)
    body_n = posed_normals(mesh, pos, list(soft))
    # Only the side of the hand that faces the flesh counts: with a deep press the nearest hand
    # point to a buried vertex can be on the back of the hand, which would read as outside.
    facing = [0.0, 0.0, 0.0]
    for i, s in soft.items():
        for a in range(3):
            facing[a] += body_n[i][a] * s
    ln = math.sqrt(sum(v * v for v in facing)) or 1.0
    facing = [v / ln for v in facing]
    hand = [i for i in hand if sum(hand_n[i][a] * facing[a] for a in range(3)) < -0.15]
    if not hand:
        return {}, set(), 0.0
    hand_pts = [pos[i] for i in hand]
    grid = Grid(hand_pts, cell=1.0)
    push: dict[int, list[float]] = {}
    deepest = 0.0
    for i, s in soft.items():
        p = pos[i]
        near = grid.nearest(p, 3, reach=3)
        if not near or math.sqrt(near[0][0]) > settings.reach:
            continue
        total = 0.0
        h = [0.0, 0.0, 0.0]
        n = [0.0, 0.0, 0.0]
        for d2, k in near:
            w = 1.0 / (math.sqrt(d2) + 0.05)
            total += w
            q = hand_pts[k]
            m = hand_n[hand[k]]
            for a in range(3):
                h[a] += q[a] * w
                n[a] += m[a] * w
        h = [v / total for v in h]
        ln = math.sqrt(sum(v * v for v in n)) or 1.0
        n = [v / ln for v in n]
        depth = -sum((p[a] - h[a]) * n[a] for a in range(3))
        if depth <= -settings.gap:
            continue
        move = (depth + settings.gap) * (0.35 + 0.65 * s)
        push[i] = [n[a] * move for a in range(3)]
        deepest = max(deepest, depth)
    touching = set(push)
    field = {i: list(v) for i, v in push.items()}
    for _ in range(settings.spread):
        nxt = dict(field)
        for i, s in soft.items():
            if i in touching:
                continue
            ring = [j for j in mesh.neighbors[i] if j in field]
            if not ring:
                continue
            avg = [sum(field[j][a] for j in ring) / len(mesh.neighbors[i]) for a in range(3)]
            nxt[i] = [v * s * 0.92 for v in avg]
        field = nxt
    if touching and settings.bulge > 0:
        dist = geodesic(mesh, pos, touching, limit=settings.bulge_radius * 2.5)
        volume = sum(math.sqrt(sum(v * v for v in push[i])) for i in touching)
        ring = {i: d for i, d in dist.items() if i in soft and i not in touching and d > 0}
        shape = {i: soft[i] * (d / settings.bulge_radius) * math.exp(1 - d / settings.bulge_radius)
                 for i, d in ring.items()}
        norm = sum(shape.values()) or 1.0
        for i, w in shape.items():
            amount = settings.bulge * volume * w / norm
            n = body_n.get(i, (0.0, 0.0, 1.0))
            cur = field.setdefault(i, [0.0, 0.0, 0.0])
            for a in range(3):
                cur[a] += n[a] * amount
    return field, touching, deepest


def geodesic(mesh: Mesh, pos: dict[int, Vec], start: set[int], limit: float) -> dict[int, float]:
    dist = {i: 0.0 for i in start}
    heap = [(0.0, i) for i in start]
    while heap:
        d, i = heapq.heappop(heap)
        if d > dist.get(i, math.inf) or d > limit:
            continue
        for j in mesh.neighbors[i]:
            if j not in pos:
                continue
            nd = d + math.dist(pos[i], pos[j])
            if nd < dist.get(j, math.inf) and nd <= limit:
                dist[j] = nd
                heapq.heappush(heap, (nd, j))
    return dist


def simulate(mesh: Mesh, soft: dict[int, float], hand: list[int], frames: list[dict[int, Vec]],
             settings: Settings | None = None, scale: float = 1.0) -> list[dict[int, Vec]]:
    """Per-frame offsets (object space, cm) for the soft vertices: contact as a hard constraint,
    everything else following it through a damped spring, plus a whole-breast sag spring driven by
    how deep the press is."""
    settings = settings or Settings()
    x: dict[int, list[float]] = {}
    v: dict[int, list[float]] = {}
    sag = sag_v = 0.0
    out: list[dict[int, Vec]] = []
    for pos in frames:
        # The breast's sag (from the previous frame's press) moves it before the hand is tested,
        # so the contact push is measured on the flesh where it really is.
        if sag:
            pos = dict(pos)
            for i, s in soft.items():
                x0, y0, z0 = pos[i]
                pos[i] = (x0, y0 + sag * s, z0)
        target, touching, deepest = contact_targets(mesh, soft, hand, pos, settings)
        for i in set(x) | set(target):
            t = target.get(i, [0.0, 0.0, 0.0])
            cur = x.setdefault(i, [0.0, 0.0, 0.0])
            vel = v.setdefault(i, [0.0, 0.0, 0.0])
            if i in touching:
                for a in range(3):
                    vel[a] = t[a] - cur[a]
                    cur[a] = t[a]
                continue
            for a in range(3):
                vel[a] += settings.stiffness * (t[a] - cur[a]) - settings.damping * vel[a]
                cur[a] += vel[a]
        frame_sag = sag
        sag_v += settings.sag_stiffness * (-settings.sag * deepest - sag) - settings.sag_damping * sag_v
        sag += sag_v
        frame: dict[int, Vec] = {}
        k = settings.subd_boost / scale
        for i, s in soft.items():
            d = x.get(i, [0.0, 0.0, 0.0])
            vec = (d[0] * k, (d[1] + frame_sag * s) * k, d[2] * k)
            if abs(vec[0]) + abs(vec[1]) + abs(vec[2]) > 0.003:
                frame[i] = (round(vec[0], 5), round(vec[1], 5), round(vec[2], 5))
        out.append(frame)
    return out
