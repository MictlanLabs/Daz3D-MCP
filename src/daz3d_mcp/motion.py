"""Motion capture files and retargeting, done in Python so Daz Studio never
shows an importer dialog and the bone mapping is fully under our control.

A BVH or FBX animation is read into a source skeleton that can be sampled at
any time. Retargeting compares each source bone with its own rest pose (the
T pose of a Mixamo rig, the zero pose of a BVH) and gives the Genesis bone the
same change in world space, after turning it from its own rest pose (Genesis
starts in an A pose) to the source's. Unmapped Genesis bones stay at zero, so
a source with three spine bones still drives a figure with four.

Conventions (cm, Y up, figures face +Z, the figure's left is +X):

- A Daz bone's dials are Euler angles about the bone's own axes. The bone's
  rotation in figure space is ``parent * Q * E * Q^-1``, where Q is the bone
  orientation and E the dial rotation in the bone's rotation order, first
  letter applied first. These two choices are what real Daz Studio has to
  confirm; ``CONVENTIONS`` lists the alternatives, and anim_import measures
  which one Daz actually uses (see anim_tools.calibrate).
- Matrices are 3x3 tuples of rows acting on column vectors.
"""

from __future__ import annotations

import math
import re
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from daz3d_mcp.meshes import MeshError, _FbxNode, _read_binary

Vec = tuple[float, float, float]
Mat = tuple[Vec, Vec, Vec]

IDENTITY: Mat = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
AXIS = {"X": 0, "Y": 1, "Z": 2}

# How Daz turns dials into a rotation: (euler mode, orientation mode).
#   euler "applied": "XYZ" rotates about X first (matrix Z * Y * X)
#   euler "product": "XYZ" is the product X * Y * Z (Z applied first)
#   orient "qeq": Q * E * Q^-1;  "qiq": Q^-1 * E * Q
CONVENTIONS = ["applied/qeq", "product/qeq", "applied/qiq", "product/qiq"]
DEFAULT_CONVENTION = CONVENTIONS[0]


class MotionError(Exception):
    pass


# ------------------------------------------------------------------ math --
def v_add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def v_sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def v_scale(a: Vec, s: float) -> Vec:
    return (a[0] * s, a[1] * s, a[2] * s)


def v_dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def v_cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def v_len(a: Vec) -> float:
    return math.sqrt(v_dot(a, a))


def v_norm(a: Vec) -> Vec:
    n = v_len(a)
    return (0.0, 0.0, 0.0) if n < 1e-12 else (a[0] / n, a[1] / n, a[2] / n)


def angle_between(a: Vec, b: Vec) -> float:
    """Degrees between two directions (0 when either is zero)."""
    na, nb = v_len(a), v_len(b)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    c = max(-1.0, min(1.0, v_dot(a, b) / (na * nb)))
    return math.degrees(math.acos(c))


def m_mul(a: Mat, b: Mat) -> Mat:
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))  # type: ignore


def m_vec(m: Mat, v: Vec) -> Vec:
    return (m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
            m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
            m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2])


def m_t(m: Mat) -> Mat:
    return ((m[0][0], m[1][0], m[2][0]), (m[0][1], m[1][1], m[2][1]), (m[0][2], m[1][2], m[2][2]))


def m_axis(axis: str, degrees: float) -> Mat:
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    if axis == "X":
        return ((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c))
    if axis == "Y":
        return ((c, 0.0, s), (0.0, 1.0, 0.0), (-s, 0.0, c))
    return ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))


def orthonormal(m: Mat) -> Mat:
    """The rotation part of a matrix that may carry scale (Gram-Schmidt on the columns)."""
    c0 = v_norm((m[0][0], m[1][0], m[2][0]))
    c1 = (m[0][1], m[1][1], m[2][1])
    c1 = v_norm(v_sub(c1, v_scale(c0, v_dot(c0, c1))))
    c2 = v_cross(c0, c1)
    if v_dot(c2, (m[0][2], m[1][2], m[2][2])) < 0:  # mirrored: keep it a rotation
        c2 = v_scale(c2, -1)
    return ((c0[0], c1[0], c2[0]), (c0[1], c1[1], c2[1]), (c0[2], c1[2], c2[2]))


def quat_mat(x: float, y: float, z: float, w: float) -> Mat:
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    return ((1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
            (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
            (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)))


def from_to(a: Vec, b: Vec) -> Mat:
    """The smallest rotation that turns direction a into direction b."""
    a, b = v_norm(a), v_norm(b)
    if v_len(a) < 1e-9 or v_len(b) < 1e-9:
        return IDENTITY
    c = v_dot(a, b)
    axis = v_cross(a, b)
    s = v_len(axis)
    if s < 1e-9:
        if c > 0:
            return IDENTITY
        # Opposite: half a turn about any perpendicular axis.
        perp = v_norm(v_cross(a, (1.0, 0.0, 0.0) if abs(a[0]) < 0.9 else (0.0, 1.0, 0.0)))
        return axis_angle(perp, 180.0)
    return axis_angle(v_scale(axis, 1 / s), math.degrees(math.atan2(s, c)))


def axis_angle(axis: Vec, degrees: float) -> Mat:
    x, y, z = v_norm(axis)
    a = math.radians(degrees)
    c, s, t = math.cos(a), math.sin(a), 1 - math.cos(a)
    return ((t * x * x + c, t * x * y - s * z, t * x * z + s * y),
            (t * x * y + s * z, t * y * y + c, t * y * z - s * x),
            (t * x * z - s * y, t * y * z + s * x, t * z * z + c))


def rot_angle(m: Mat) -> float:
    """Degrees a rotation turns by."""
    c = max(-1.0, min(1.0, (m[0][0] + m[1][1] + m[2][2] - 1) / 2))
    return math.degrees(math.acos(c))


def _product_letters(order: str, mode: str) -> str:
    order = order.upper()
    if sorted(order) != ["X", "Y", "Z"]:
        raise MotionError(f"Bad rotation order {order!r}.")
    return order[::-1] if mode == "applied" else order


def euler_mat(angles: Vec, order: str, mode: str = "applied") -> Mat:
    """Rotation from [x, y, z] degrees in a rotation order."""
    m = IDENTITY
    for letter in _product_letters(order, mode):
        m = m_mul(m, m_axis(letter, angles[AXIS[letter]]))
    return m


def _unwrap(a: float, ref: float) -> float:
    while a - ref > 180:
        a -= 360
    while a - ref < -180:
        a += 360
    return a


def mat_euler(m: Mat, order: str, mode: str = "applied", prev: Vec | None = None) -> Vec:
    """[x, y, z] degrees that give rotation m in the order; with prev, the
    solution closest to the previous frame, so curves do not jump."""
    i, j, k = (AXIS[c] for c in _product_letters(order, mode))
    s = 1.0 if (j - i) % 3 == 1 else -1.0
    sb = max(-1.0, min(1.0, s * m[i][k]))
    b = math.asin(sb)
    if math.cos(b) > 1e-6:
        a = math.atan2(-s * m[j][k], m[k][k])
        c = math.atan2(-s * m[i][j], m[i][i])
    else:  # gimbal lock: put it all on the first angle
        a = math.atan2(s * m[k][j], m[j][j])
        c = 0.0
    sols = [(a, b, c), (a + math.pi, math.pi - b, c + math.pi)]
    best = None
    for sa, sb2, sc in sols:
        out = [0.0, 0.0, 0.0]
        out[i], out[j], out[k] = math.degrees(sa), math.degrees(sb2), math.degrees(sc)
        if prev is not None:
            out = [_unwrap(out[n], prev[n]) for n in range(3)]
            cost = sum(abs(out[n] - prev[n]) for n in range(3))
        else:
            out = [_unwrap(v, 0.0) for v in out]
            cost = sum(abs(v) for v in out)
        if best is None or cost < best[0] - 1e-9:
            best = (cost, out)
    assert best is not None
    return (best[1][0], best[1][1], best[1][2])


def split_convention(convention: str) -> tuple[str, str]:
    if convention not in CONVENTIONS:
        raise MotionError(f"Unknown rotation convention {convention!r}; use one of {', '.join(CONVENTIONS)}.")
    mode, orient = convention.split("/")
    return mode, orient


def dial_rotation(angles: Vec, order: str, orient: Mat, convention: str = DEFAULT_CONVENTION) -> Mat:
    """A bone's rotation relative to its parent from its dial values."""
    mode, how = split_convention(convention)
    e = euler_mat(angles, order, mode)
    return m_mul(m_mul(orient, e), m_t(orient)) if how == "qeq" else m_mul(m_mul(m_t(orient), e), orient)


def dial_angles(relative: Mat, order: str, orient: Mat, convention: str = DEFAULT_CONVENTION,
                prev: Vec | None = None) -> Vec:
    mode, how = split_convention(convention)
    e = m_mul(m_mul(m_t(orient), relative), orient) if how == "qeq" else m_mul(m_mul(orient, relative), m_t(orient))
    return mat_euler(e, order, mode, prev)


def dial_translation(delta: Vec, orient: Mat, convention: str = DEFAULT_CONVENTION) -> Vec:
    """Translate dials that move a bone by delta (in its parent's space)."""
    _mode, how = split_convention(convention)
    return m_vec(m_t(orient), delta) if how == "qeq" else m_vec(orient, delta)


# -------------------------------------------------------- target figure --
@dataclass
class TargetBone:
    name: str
    parent: str | None
    origin: Vec
    end: Vec
    orient: Mat
    order: str


@dataclass
class TargetSkeleton:
    figure: str
    bones: dict[str, TargetBone]
    order: list[str]  # parents before children
    generation: str | None = None

    @classmethod
    def from_daz(cls, data: dict) -> "TargetSkeleton":
        bones: dict[str, TargetBone] = {}
        for b in data["bones"]:
            q = b.get("orientation") or [0, 0, 0, 1]
            bones[b["name"]] = TargetBone(b["name"], b.get("parent"), tuple(b["origin"]), tuple(b.get("end") or b["origin"]),
                                          quat_mat(*q), str(b.get("rotation_order") or "XYZ").upper())
        for b in bones.values():
            if b.parent not in bones:
                b.parent = None
        order: list[str] = []
        seen: set[str] = set()

        def visit(name: str) -> None:
            if name in seen:
                return
            p = bones[name].parent
            if p:
                visit(p)
            seen.add(name)
            order.append(name)

        for name in bones:
            visit(name)
        return cls(data.get("figure", ""), bones, order, data.get("generation"))

    def children(self, name: str) -> list[str]:
        return [b.name for b in self.bones.values() if b.parent == name]

    def root(self) -> str:
        for name in ("hip", "Hip", "hips", "Hips"):
            if name in self.bones:
                return name
        roots = [n for n in self.order if self.bones[n].parent is None]
        if not roots:
            raise MotionError(f"{self.figure} has no bones.")
        return max(roots, key=lambda r: len(self.descendants(r)))

    def descendants(self, name: str) -> list[str]:
        out = []
        for c in self.children(name):
            out += [c] + self.descendants(c)
        return out

    def fk(self, rotations: dict[str, Vec], root_translation: Vec | None = None,
           convention: str = DEFAULT_CONVENTION) -> tuple[dict[str, Vec], dict[str, Mat]]:
        """Bone origins and rotations in figure space for dial values."""
        world: dict[str, Mat] = {}
        pos: dict[str, Vec] = {}
        root = self.root()
        for name in self.order:
            b = self.bones[name]
            local = dial_rotation(rotations.get(name, (0.0, 0.0, 0.0)), b.order, b.orient, convention)
            if b.parent is None:
                world[name] = local
                pos[name] = b.origin
                if name == root and root_translation:
                    t = m_vec(b.orient, root_translation) if convention.endswith("qeq") else m_vec(m_t(b.orient), root_translation)
                    pos[name] = v_add(b.origin, t)
            else:
                pw = world[b.parent]
                world[name] = m_mul(pw, local)
                pos[name] = v_add(pos[b.parent], m_vec(pw, v_sub(b.origin, self.bones[b.parent].origin)))
        return pos, world


# ------------------------------------------------------------ source rig --
@dataclass
class Xform:
    """A transform with scale: x' = lin * x + pos."""
    lin: Mat
    pos: Vec

    def then(self, child: "Xform") -> "Xform":
        return Xform(m_mul(self.lin, child.lin), v_add(m_vec(self.lin, child.pos), self.pos))


@dataclass
class SourceMotion:
    """A skeleton with animation, read from a BVH or FBX file."""
    format: str
    names: list[str]
    parents: list[int]
    fps: float
    frames: int
    start: float  # seconds
    rest: list[Xform]  # world rest transforms
    sampler: object = None  # callable(t seconds) -> list[Xform] local transforms
    unit_cm: float = 1.0
    take: str | None = None
    rest_source: str = "zero pose"
    takes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(self.frames - 1, 0) / self.fps if self.fps else 0.0

    def world_at(self, t: float) -> list[Xform]:
        local = self.sampler(t)  # type: ignore[misc]
        out: list[Xform] = []
        for i, lx in enumerate(local):
            p = self.parents[i]
            out.append(out[p].then(lx) if p >= 0 else lx)
        return out

    def children(self, i: int) -> list[int]:
        return [c for c, p in enumerate(self.parents) if p == i]


def _lerp(a: list[float], b: list[float], f: float) -> list[float]:
    return [x + (y - x) * f for x, y in zip(a, b)]


# ------------------------------------------------------------------- BVH --
def read_bvh(path: Path) -> SourceMotion:
    try:
        text = path.read_text("utf-8", errors="replace")
    except OSError as exc:
        raise MotionError(f"Cannot read {path}: {exc}") from exc
    tokens = text.split()
    if not tokens or tokens[0].upper() != "HIERARCHY":
        raise MotionError(f"{path.name} is not a BVH file (it does not start with HIERARCHY).")
    names: list[str] = []
    parents: list[int] = []
    offsets: list[Vec] = []
    channels: list[list[str]] = []
    pos = 1
    stack: list[int] = []
    try:
        while pos < len(tokens) and tokens[pos].upper() != "MOTION":
            tok = tokens[pos].upper()
            if tok in ("ROOT", "JOINT"):
                names.append(tokens[pos + 1])
                parents.append(stack[-1] if stack else -1)
                offsets.append((0.0, 0.0, 0.0))
                channels.append([])
                pos += 2
            elif tok == "END":  # End Site
                parent = stack[-1] if stack else -1
                names.append(f"{names[parent]}_End" if parent >= 0 else "End")
                parents.append(parent)
                offsets.append((0.0, 0.0, 0.0))
                channels.append([])
                pos += 2
            elif tok == "{":
                stack.append(len(names) - 1)
                pos += 1
            elif tok == "}":
                stack.pop()
                pos += 1
            elif tok == "OFFSET":
                offsets[stack[-1]] = (float(tokens[pos + 1]), float(tokens[pos + 2]), float(tokens[pos + 3]))
                pos += 4
            elif tok == "CHANNELS":
                n = int(tokens[pos + 1])
                channels[stack[-1]] = [c.lower() for c in tokens[pos + 2:pos + 2 + n]]
                pos += 2 + n
            else:
                pos += 1
        if pos >= len(tokens):
            raise MotionError(f"{path.name} has no MOTION section.")
        pos += 1
        frames = int(tokens[pos + 1])  # Frames: N
        pos += 2
        frame_time = float(tokens[pos + 2])  # Frame Time: dt
        pos += 3
    except (IndexError, ValueError) as exc:
        raise MotionError(f"{path.name} is not a valid BVH file ({exc}).") from exc
    width = sum(len(c) for c in channels)
    values = tokens[pos:pos + frames * width]
    if len(values) < frames * width:
        frames = len(values) // width
    if frames < 1:
        raise MotionError(f"{path.name} has no frames.")
    data = [[float(v) for v in values[f * width:(f + 1) * width]] for f in range(frames)]
    fps = 1.0 / frame_time if frame_time > 0 else 30.0

    def local_from(row: list[float]) -> list[Xform]:
        out = []
        col = 0
        for i in range(len(names)):
            rot = IDENTITY
            p = offsets[i]
            moved = [None, None, None]
            for ch in channels[i]:
                v = row[col]
                col += 1
                if ch.endswith("rotation"):
                    rot = m_mul(rot, m_axis(ch[0].upper(), v))
                elif ch.endswith("position"):
                    moved[AXIS[ch[0].upper()]] = v
            if any(m is not None for m in moved):
                p = tuple(moved[a] if moved[a] is not None else offsets[i][a] for a in range(3))  # type: ignore
            out.append(Xform(rot, p))
        return out

    def sampler(t: float) -> list[Xform]:
        f = max(0.0, min(frames - 1, t * fps))
        a = int(math.floor(f))
        b = min(a + 1, frames - 1)
        return local_from(_lerp(data[a], data[b], f - a) if b != a else data[a])

    rest_local = [Xform(IDENTITY, offsets[i]) for i in range(len(names))]
    rest: list[Xform] = []
    for i, lx in enumerate(rest_local):
        rest.append(rest[parents[i]].then(lx) if parents[i] >= 0 else lx)
    return SourceMotion("bvh", names, parents, fps, frames, 0.0, rest, sampler)


# ------------------------------------------------------------------- FBX --
FBX_TICKS = 46186158000.0
_FBX_ORDERS = {0: "XYZ", 1: "XZY", 2: "YZX", 3: "YXZ", 4: "ZXY", 5: "ZYX"}
_FBX_FPS = {1: 120.0, 2: 100.0, 3: 60.0, 4: 50.0, 5: 48.0, 6: 30.0, 7: 30.0, 8: 30.0, 9: 29.97, 10: 25.0,
            11: 24.0, 12: 1000.0, 13: 23.976, 15: 96.0, 16: 72.0, 17: 59.94}
_FBX_ARRAYS = frozenset({"Vertices", "KeyTime", "KeyValueFloat", "Matrix"})


def _p70(node: _FbxNode | None) -> dict[str, list]:
    out: dict[str, list] = {}
    p70 = node.find("Properties70") if node else None
    for p in (p70.find_all("P") if p70 else []):
        if p.props and isinstance(p.props[0], str):
            out[p.props[0]] = p.props[4:]
    return out


def _vec3(values: list | None, default: Vec) -> Vec:
    if not values or len(values) < 3:
        return default
    return (float(values[0]), float(values[1]), float(values[2]))


def _fbx_name(prop) -> str:
    name = prop.split("\x00")[0] if isinstance(prop, str) else ""
    return name.split("::", 1)[1] if "::" in name else name


class _Curve:
    def __init__(self, times: list[float], values: list[float]):
        self.t = times
        self.v = values

    def at(self, t: float) -> float:
        ts, vs = self.t, self.v
        if not ts:
            return 0.0
        if t <= ts[0]:
            return vs[0]
        if t >= ts[-1]:
            return vs[-1]
        lo, hi = 0, len(ts) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if ts[mid] <= t:
                lo = mid
            else:
                hi = mid
        f = (t - ts[lo]) / (ts[hi] - ts[lo]) if ts[hi] > ts[lo] else 0.0
        return vs[lo] + (vs[hi] - vs[lo]) * f


def _mat16(values: list[float]) -> Xform:
    m = values  # column-major: translation in 12, 13, 14
    lin = ((m[0], m[4], m[8]), (m[1], m[5], m[9]), (m[2], m[6], m[10]))
    return Xform(lin, (m[12], m[13], m[14]))


def read_fbx(path: Path, take: str | None = None) -> SourceMotion:
    data = path.read_bytes()
    if not data.startswith(b"Kaydara FBX Binary"):
        if b"FBXHeaderExtension" in data[:4096]:
            raise MotionError(f"{path.name} is an ASCII FBX. Export it again as binary FBX (Mixamo, Blender and Maya "
                              "do by default) and import that.")
        raise MotionError(f"{path.name} is not an FBX file.")
    try:
        nodes = _read_binary(data, _FBX_ARRAYS)
    except (struct.error, zlib.error, IndexError, MeshError) as exc:
        raise MotionError(f"{path.name} could not be read as binary FBX ({exc}).") from exc
    top = {n.name: n for n in nodes}
    gs = _p70(top.get("GlobalSettings"))
    unit = float((gs.get("UnitScaleFactor") or [1.0])[0] or 1.0)
    fps = _FBX_FPS.get(int((gs.get("TimeMode") or [0])[0] or 0))
    if not fps:
        fps = float((gs.get("CustomFrameRate") or [30.0])[0] or 30.0)
    if fps <= 0:
        fps = 30.0

    objects = top.get("Objects")
    models: dict[int, dict] = {}
    curve_nodes: dict[int, dict] = {}
    curves: dict[int, _Curve] = {}
    stacks: dict[int, str] = {}
    layers: set[int] = set()
    bind: dict[int, Xform] = {}
    for o in (objects.children if objects else []):
        oid = o.props[0] if o.props else None
        if o.name == "Model":
            p = _p70(o)
            models[oid] = {
                "name": _fbx_name(o.props[1]), "type": o.props[2] if len(o.props) > 2 else "",
                "t": _vec3(p.get("Lcl Translation"), (0.0, 0.0, 0.0)),
                "r": _vec3(p.get("Lcl Rotation"), (0.0, 0.0, 0.0)),
                "s": _vec3(p.get("Lcl Scaling"), (1.0, 1.0, 1.0)),
                "pre": _vec3(p.get("PreRotation"), (0.0, 0.0, 0.0)),
                "post": _vec3(p.get("PostRotation"), (0.0, 0.0, 0.0)),
                # Daz Studio exports each bone's place as a RotationOffset (and
                # keeps Lcl Translation for the dials); others use pivots.
                "roff": _vec3(p.get("RotationOffset"), (0.0, 0.0, 0.0)),
                "rpiv": _vec3(p.get("RotationPivot"), (0.0, 0.0, 0.0)),
                "soff": _vec3(p.get("ScalingOffset"), (0.0, 0.0, 0.0)),
                "spiv": _vec3(p.get("ScalingPivot"), (0.0, 0.0, 0.0)),
                "order": _FBX_ORDERS.get(int((p.get("RotationOrder") or [0])[0] or 0), "XYZ"),
                "parent": None, "anim": {},
            }
        elif o.name == "AnimationCurveNode":
            p = _p70(o)
            curve_nodes[oid] = {"kind": _fbx_name(o.props[1]),
                                "default": {k[2]: float(v[0]) for k, v in p.items() if k.startswith("d|") and v},
                                "curves": {}, "model": None, "prop": None, "layer": None}
        elif o.name == "AnimationCurve":
            kt = o.find("KeyTime")
            kv = o.find("KeyValueFloat")
            times = [t / FBX_TICKS for t in (kt.props[0] if kt and kt.props and kt.props[0] else [])]
            vals = [float(v) for v in (kv.props[0] if kv and kv.props and kv.props[0] else [])]
            curves[oid] = _Curve(times, vals)
        elif o.name == "AnimationStack":
            stacks[oid] = _fbx_name(o.props[1])
        elif o.name == "AnimationLayer":
            layers.add(oid)
        elif o.name == "Pose" and len(o.props) > 2 and o.props[2] == "BindPose":
            for pn in o.find_all("PoseNode"):
                node_id = pn.find("Node")
                mat = pn.find("Matrix")
                if node_id and mat and mat.props and mat.props[0] and len(mat.props[0]) == 16:
                    bind[node_id.props[0]] = _mat16(mat.props[0])

    layer_stack: dict[int, int] = {}
    conns = top.get("Connections")
    for c in (conns.find_all("C") if conns else []):
        kind, child, parent = c.props[0], c.props[1], c.props[2]
        prop = c.props[3] if len(c.props) > 3 else None
        if kind == "OO" and child in models and parent in models:
            models[child]["parent"] = parent
        elif kind == "OP" and child in curve_nodes and parent in models:
            curve_nodes[child]["model"] = parent
            curve_nodes[child]["prop"] = prop
        elif kind == "OP" and child in curves and parent in curve_nodes:
            curve_nodes[parent]["curves"][str(prop)[-1:]] = curves[child]
        elif kind == "OO" and child in curve_nodes and parent in layers:
            curve_nodes[child]["layer"] = parent
        elif kind == "OO" and child in layers and parent in stacks:
            layer_stack[child] = parent

    take_names = [stacks[s] for s in stacks]
    chosen = None
    if stacks:
        if take:
            for sid, name in stacks.items():
                if name.lower() == take.lower():
                    chosen = sid
            if chosen is None:
                raise MotionError(f"{path.name} has no take {take!r}; it has {', '.join(take_names)}.")
        else:
            # Real Mixamo files can carry an empty "Take 001" before "mixamo.com":
            # take the stack that animates the most channels.
            used: dict[int, int] = {sid: 0 for sid in stacks}
            for cn in curve_nodes.values():
                sid = layer_stack.get(cn["layer"]) if cn["layer"] is not None else None
                if sid in used and cn["model"] is not None and cn["curves"]:
                    used[sid] += 1
            chosen = max(stacks, key=lambda sid: used[sid])
    for cn in curve_nodes.values():
        if cn["model"] is None:
            continue
        if chosen is not None and cn["layer"] is not None and layer_stack.get(cn["layer"]) != chosen:
            continue
        key = {"Lcl Translation": "t", "Lcl Rotation": "r", "Lcl Scaling": "s"}.get(cn["prop"])
        if key:
            models[cn["model"]]["anim"][key] = cn

    # Keep the skeleton: limb nodes and their ancestors (an "Armature" null may scale everything).
    def is_bone(m: dict) -> bool:
        return m["type"] in ("LimbNode", "Root", "Limb")

    keep: set[int] = set()
    for mid, m in models.items():
        if is_bone(m):
            cur = mid
            while cur is not None and cur not in keep:
                keep.add(cur)
                cur = models[cur]["parent"]
    if not keep:
        raise MotionError(f"{path.name} has no skeleton (no LimbNode bones), so it has no character animation.")
    ids: list[int] = []

    def add(mid: int) -> None:
        if mid in ids:
            return
        p = models[mid]["parent"]
        if p is not None and p in keep:
            add(p)
        ids.append(mid)

    for mid in models:
        if mid in keep:
            add(mid)
    index = {mid: i for i, mid in enumerate(ids)}
    names = [models[m]["name"] for m in ids]
    parents = [index.get(models[m]["parent"], -1) if models[m]["parent"] in keep else -1 for m in ids]

    times: list[float] = []
    for m in ids:
        for cn in models[m]["anim"].values():
            for cv in cn["curves"].values():
                times += cv.t[:1] + cv.t[-1:]
    start = min(times) if times else 0.0
    end = max(times) if times else 0.0
    frames = int(round((end - start) * fps)) + 1 if times else 1
    if not times:
        raise MotionError(f"{path.name} has a skeleton but no animation curves.")

    def channel(m: dict, key: str, t: float | None) -> Vec:
        base = m[key]
        cn = m["anim"].get(key)
        if cn is None or t is None:
            return base
        out = []
        for a, axis in enumerate("XYZ"):
            cv = cn["curves"].get(axis)
            if cv is not None:
                out.append(cv.at(t))
            elif axis in cn["default"]:
                out.append(cn["default"][axis])
            else:
                out.append(base[a])
        return (out[0], out[1], out[2])

    def local(m: dict, t: float | None) -> Xform:
        # FBX: T * Roff * Rp * Rpre * R * Rpost^-1 * Rp^-1 * Soff * Sp * S * Sp^-1
        tr = channel(m, "t", t)
        r = euler_mat(channel(m, "r", t), m["order"], "applied")
        pre = euler_mat(m["pre"], "XYZ", "applied")
        post = euler_mat(m["post"], "XYZ", "applied")
        s = channel(m, "s", t)
        rot = m_mul(m_mul(pre, r), m_t(post))
        sm = ((s[0], 0.0, 0.0), (0.0, s[1], 0.0), (0.0, 0.0, s[2]))
        lin = m_mul(rot, sm)
        rp, sp = m["rpiv"], m["spiv"]
        inner = v_sub(v_add(m["soff"], sp), v_add(m_vec(sm, sp), rp))
        pos = v_add(v_add(v_add(tr, m["roff"]), rp), m_vec(rot, inner))
        return Xform(lin, pos)

    unit_x = Xform(((unit, 0.0, 0.0), (0.0, unit, 0.0), (0.0, 0.0, unit)), (0.0, 0.0, 0.0))

    def sampler(t: float) -> list[Xform]:
        out = [local(models[m], start + t) for m in ids]
        for i, p in enumerate(parents):
            if p < 0:
                out[i] = unit_x.then(out[i])
        return out

    rest_default: list[Xform] = []
    for i, m in enumerate(ids):
        lx = local(models[m], None)
        rest_default.append(rest_default[parents[i]].then(lx) if parents[i] >= 0 else unit_x.then(lx))
    rest = rest_default
    rest_source = "the skeleton's default pose in the file"
    bound = [m for m in ids if m in bind]
    if len(bound) >= max(3, len([m for m in ids if is_bone(models[m])]) // 2):
        rest = []
        for i, m in enumerate(ids):
            if m in bind:
                rest.append(unit_x.then(bind[m]))
            else:  # not skinned: follow its parent's bind pose
                lx = local(models[m], None)
                rest.append(rest[parents[i]].then(lx) if parents[i] >= 0 else unit_x.then(lx))
        rest_source = "the bind pose stored in the file"
    motion = SourceMotion("fbx", names, parents, fps, frames, 0.0, rest, sampler, unit_cm=unit,
                          take=stacks.get(chosen) if chosen is not None else None, rest_source=rest_source,
                          takes=take_names)
    up = int((gs.get("UpAxis") or [1])[0] or 1)
    if up != 1:
        motion.warnings.append("The file says it is Z-up; the up axis is detected from the skeleton itself.")
    return motion


def read_motion(path: Path, take: str | None = None) -> SourceMotion:
    if not path.is_file():
        raise MotionError(f"{path} does not exist.")
    ext = path.suffix.lower()
    if ext == ".bvh":
        return read_bvh(path)
    if ext == ".fbx":
        return read_fbx(path, take)
    raise MotionError(f"Animations import from .bvh and .fbx files; {path.name} is {ext or 'unknown'}. "
                      "Export it as FBX or BVH first (Blender: File > Export).")


# ------------------------------------------------------------- bone maps --
SIDES = ("l", "r")
FINGERS = ("thumb", "index", "middle", "ring", "pinky")

# Roles: what each bone does, so any source rig maps to any Genesis rig.
ROLES = (["hips", "pelvis", "spine1", "spine2", "chest", "upper_chest", "neck", "neck2", "head"] +
         [f"{s}_{p}" for s in SIDES for p in ("collar", "upperarm", "forearm", "hand", "thigh", "shin", "foot", "toes")] +
         [f"{s}_{f}{n}" for s in SIDES for f in FINGERS for n in (1, 2, 3)])


def _sided(fmt: dict[str, str], left: str, right: str) -> dict[str, str]:
    """Expands {'collar': 'LeftShoulder'}-style names written for the left side."""
    out: dict[str, str] = {}
    for part, name in fmt.items():
        out[f"l_{part}"] = name.replace("{S}", left).replace("{s}", left.lower())
        out[f"r_{part}"] = name.replace("{S}", right).replace("{s}", right.lower())
    return out


def _fingers(fmt: str, names: dict[str, str]) -> dict[str, str]:
    out = {}
    for f in FINGERS:
        for n in (1, 2, 3):
            out[f"{f}{n}"] = fmt.replace("{F}", names[f]).replace("{n}", str(n))
    return out


_MIXAMO_FINGERS = {"thumb": "Thumb", "index": "Index", "middle": "Middle", "ring": "Ring", "pinky": "Pinky"}

# Source rigs: role -> bone name (names are compared without a "prefix:" and case).
SOURCE_RIGS: dict[str, dict[str, str]] = {
    "mixamo": {
        "hips": "Hips", "spine1": "Spine", "chest": "Spine1", "upper_chest": "Spine2", "neck": "Neck", "head": "Head",
        **_sided({"collar": "{S}Shoulder", "upperarm": "{S}Arm", "forearm": "{S}ForeArm", "hand": "{S}Hand",
                  "thigh": "{S}UpLeg", "shin": "{S}Leg", "foot": "{S}Foot", "toes": "{S}ToeBase",
                  **_fingers("{S}Hand{F}{n}", _MIXAMO_FINGERS)}, "Left", "Right"),
    },
    "cmu": {
        "hips": "Hips", "spine1": "LowerBack", "chest": "Spine", "upper_chest": "Spine1", "neck": "Neck",
        "neck2": "Neck1", "head": "Head",
        **_sided({"collar": "{S}Shoulder", "upperarm": "{S}Arm", "forearm": "{S}ForeArm", "hand": "{S}Hand",
                  "thigh": "{S}UpLeg", "shin": "{S}Leg", "foot": "{S}Foot", "toes": "{S}ToeBase"}, "Left", "Right"),
    },
    "unreal": {
        "hips": "pelvis", "spine1": "spine_01", "spine2": "spine_02", "chest": "spine_03", "upper_chest": "spine_04",
        "neck": "neck_01", "neck2": "neck_02", "head": "head",
        **_sided({"collar": "clavicle_{s}", "upperarm": "upperarm_{s}", "forearm": "lowerarm_{s}", "hand": "hand_{s}",
                  "thigh": "thigh_{s}", "shin": "calf_{s}", "foot": "foot_{s}", "toes": "ball_{s}",
                  **{f"{f}{n}": f"{f}_0{n}_{{s}}" for f in FINGERS for n in (1, 2, 3)}}, "L", "R"),
    },
    "biped": {  # 3ds Max Biped, also many game rips
        "hips": "Bip01 Pelvis", "spine1": "Bip01 Spine", "chest": "Bip01 Spine1", "upper_chest": "Bip01 Spine2",
        "neck": "Bip01 Neck", "head": "Bip01 Head",
        **_sided({"collar": "Bip01 {S} Clavicle", "upperarm": "Bip01 {S} UpperArm", "forearm": "Bip01 {S} Forearm",
                  "hand": "Bip01 {S} Hand", "thigh": "Bip01 {S} Thigh", "shin": "Bip01 {S} Calf",
                  "foot": "Bip01 {S} Foot", "toes": "Bip01 {S} Toe0"}, "L", "R"),
    },
}

# Genesis rigs: role -> bone name.
TARGET_RIGS: dict[str, dict[str, str]] = {
    "genesis9": {
        "hips": "hip", "pelvis": "pelvis", "spine1": "spine1", "spine2": "spine2", "chest": "spine3",
        "upper_chest": "spine4", "neck": "neck1", "neck2": "neck2", "head": "head",
        **_sided({"collar": "{s}_shoulder", "upperarm": "{s}_upperarm", "forearm": "{s}_forearm", "hand": "{s}_hand",
                  "thigh": "{s}_thigh", "shin": "{s}_shin", "foot": "{s}_foot", "toes": "{s}_toes",
                  **{f"{f}{n}": f"{{s}}_{f}{n}" for f in FINGERS for n in (1, 2, 3)}}, "L", "R"),
    },
    "genesis8": {  # also Genesis 3
        "hips": "hip", "pelvis": "pelvis", "spine1": "abdomenLower", "spine2": "abdomenUpper", "chest": "chestLower",
        "upper_chest": "chestUpper", "neck": "neckLower", "neck2": "neckUpper", "head": "head",
        **_sided({"collar": "{s}Collar", "upperarm": "{s}ShldrBend", "forearm": "{s}ForearmBend", "hand": "{s}Hand",
                  "thigh": "{s}ThighBend", "shin": "{s}Shin", "foot": "{s}Foot", "toes": "{s}Toe",
                  **_fingers("{s}{F}{n}", {"thumb": "Thumb", "index": "Index", "middle": "Mid", "ring": "Ring",
                                           "pinky": "Pinky"})}, "L", "R"),
    },
}
SOURCE_RIGS["genesis9"] = TARGET_RIGS["genesis9"]
SOURCE_RIGS["genesis8"] = TARGET_RIGS["genesis8"]


def bare(name: str) -> str:
    """Bone name without a namespace prefix ("mixamorig:Hips" -> "hips")."""
    return name.split(":")[-1].split("|")[-1].strip().lower()


def detect_rig(names: list[str], rigs: dict[str, dict[str, str]]) -> tuple[str | None, int]:
    have = {bare(n) for n in names}
    best, score = None, 0
    for rig, roles in rigs.items():
        n = sum(1 for v in roles.values() if v.lower() in have)
        if n > score:
            best, score = rig, n
    return best, score


@dataclass
class BoneMap:
    pairs: dict[str, int]  # target bone -> source joint index
    source_rig: str | None
    target_rig: str | None
    unmapped_source: list[str]
    missing_target: list[str]


def build_map(src: SourceMotion, tgt: TargetSkeleton, rig: str = "auto",
              custom: dict[str, str | None] | None = None) -> BoneMap:
    by_bare = {}
    for i, n in enumerate(src.names):
        by_bare.setdefault(bare(n), i)
    target_rig, _ = detect_rig(list(tgt.bones), TARGET_RIGS)
    if rig == "auto":
        source_rig, score = detect_rig(src.names, SOURCE_RIGS)
        if score < 4:
            source_rig = None
    else:
        if rig not in SOURCE_RIGS:
            raise MotionError(f"Unknown rig {rig!r}; use auto or one of {', '.join(SOURCE_RIGS)}.")
        source_rig = rig
    pairs: dict[str, int] = {}
    if source_rig and target_rig:
        for role, sname in SOURCE_RIGS[source_rig].items():
            tname = TARGET_RIGS[target_rig].get(role)
            i = by_bare.get(sname.lower())
            if tname in tgt.bones and i is not None:
                pairs[tname] = i
    if not pairs:  # same names on both sides (e.g. a BVH exported from Daz)
        lower = {b.lower(): b for b in tgt.bones}
        for i, n in enumerate(src.names):
            t = lower.get(bare(n))
            if t:
                pairs[t] = i
    for s_name, t_name in (custom or {}).items():
        i = by_bare.get(bare(s_name))
        if i is None:
            raise MotionError(f"bone_map names {s_name!r}, which is not a bone in the file.")
        if t_name in (None, ""):
            for t in [t for t, j in pairs.items() if j == i]:
                del pairs[t]
            continue
        if t_name not in tgt.bones:
            raise MotionError(f"bone_map sends {s_name!r} to {t_name!r}, which {tgt.figure} does not have.")
        for t in [t for t, j in pairs.items() if j == i]:
            del pairs[t]
        pairs[t_name] = i
    if not pairs:
        raise MotionError("No bone of the file matches a bone of the figure. Pass bone_map {file bone: figure bone} "
                          "(anim_file_inspect lists the file's bones, figure_info(all_bones=true) the figure's).")
    used = set(pairs.values())
    unmapped = [src.names[i] for i in range(len(src.names))
                if i not in used and not src.names[i].endswith("_End") and not bare(src.names[i]).endswith("_end")]
    key_roles = ["hips", "head", "l_upperarm", "l_forearm", "l_thigh", "l_shin", "l_foot",
                 "r_upperarm", "r_forearm", "r_thigh", "r_shin", "r_foot"]
    missing = []
    if target_rig:
        for role in key_roles:
            t = TARGET_RIGS[target_rig][role]
            if t in tgt.bones and t not in pairs:
                missing.append(t)
    return BoneMap(pairs, source_rig, target_rig, unmapped, missing)


# ------------------------------------------------------------ retarget --
@dataclass
class RetargetResult:
    rotations: dict[str, list[list[float]]]  # bone -> [[frame, x, y, z], ...]
    root: str
    root_positions: list[list[float]]  # [[frame, x, y, z], ...] dial values
    frames: int
    source_frames: tuple[int, int]
    fps: float
    scale: float
    facing_fix: float
    up_fix: str
    floor: str
    root_travel: float
    predicted: dict[int, dict[str, Vec]]  # frame -> bone origins in figure space
    placement_turn: float = 0.0  # degrees of the file's own placement taken out (see _unplaced)


def _role_dir(src: SourceMotion, j: int, rest_pos: list[Vec]) -> Vec | None:
    kids = src.children(j)
    if not kids:
        return None
    if len(kids) == 1:
        return v_sub(rest_pos[kids[0]], rest_pos[j])
    return None


def _fix_axes(src: SourceMotion, bmap: BoneMap, tgt: TargetSkeleton) -> tuple[Mat, str, float]:
    """Rotation that makes the source Y up and facing +Z, from its rest pose."""
    rest_pos = [x.pos for x in src.rest]
    inv = {t: j for t, j in bmap.pairs.items()}
    rig = TARGET_RIGS.get(bmap.target_rig or "", {})

    def src_of(role: str) -> int | None:
        t = rig.get(role)
        return inv.get(t) if t else None

    hips = src_of("hips")
    head = src_of("head") or src_of("neck") or src_of("upper_chest")
    fix = IDENTITY
    up = "Y"
    if hips is not None and head is not None:
        d = v_sub(rest_pos[head], rest_pos[hips])
        axis = max(range(3), key=lambda a: abs(d[a]))
        if axis == 2:
            fix = m_axis("X", -90.0 if d[2] > 0 else 90.0)
            up = "Z" if d[2] > 0 else "-Z"
        elif axis == 0:
            fix = m_axis("Z", 90.0 if d[0] > 0 else -90.0)
            up = "X" if d[0] > 0 else "-X"
        elif d[1] < 0:
            fix = m_axis("X", 180.0)
            up = "-Y"
    yaw = 0.0
    lt = src_of("l_thigh") or src_of("l_upperarm") or src_of("l_collar")
    rt = src_of("r_thigh") or src_of("r_upperarm") or src_of("r_collar")
    if lt is not None and rt is not None:
        left = m_vec(fix, v_sub(rest_pos[lt], rest_pos[rt]))
        if abs(left[0]) + abs(left[2]) > 1e-6:
            yaw = math.degrees(math.atan2(left[2], left[0]))  # turn about Y so left goes to +X
            fix = m_mul(m_axis("Y", yaw), fix)
    return fix, up, round(yaw, 1)


def retarget(src: SourceMotion, tgt: TargetSkeleton, bmap: BoneMap, fps: float, *, start_frame: int = 0,
             source_start: float = 0.0, source_end: float | None = None, speed: float = 1.0,
             in_place: bool = False, root_motion: bool = True, convention: str = DEFAULT_CONVENTION,
             frames_only: list[int] | None = None) -> RetargetResult:
    if speed <= 0:
        raise MotionError("speed must be above 0.")
    fix, up, yaw = _fix_axes(src, bmap, tgt)
    rest = [Xform(m_mul(fix, orthonormal(x.lin)), m_vec(fix, x.pos)) for x in src.rest]
    rest_pos = [x.pos for x in rest]
    root = tgt.root()
    src_root = bmap.pairs.get(root)
    if src_root is None:
        # The highest mapped source joint drives the root.
        src_root = min(bmap.pairs.values(), key=lambda j: _depth(src, j))

    # Rest corrections: turn each Genesis bone from its rest direction to the source's.
    corr: dict[str, Mat] = {}
    for name in tgt.order:
        b = tgt.bones[name]
        j = bmap.pairs.get(name)
        if j is None:
            continue
        c = None
        kids = _mapped_below(tgt, name, bmap.pairs)
        central = not re.match(r"^(l_|r_|l[A-Z]|r[A-Z])", name)
        if central:
            kids = [k for k in kids if not re.match(r"^(l_|r_|l[A-Z]|r[A-Z])", k)] or kids
        if len(kids) == 1 or (kids and central):
            k = kids[0]
            dt = v_sub(tgt.bones[k].origin, b.origin)
            ds = v_sub(rest_pos[bmap.pairs[k]], rest_pos[j])
            if v_len(dt) > 1e-6 and v_len(ds) > 1e-6:
                c = from_to(dt, ds)
        if c is None:
            ds = _role_dir(src, j, rest_pos)
            dt = v_sub(b.end, b.origin)
            if ds is not None and v_len(dt) > 1e-6 and v_len(ds) > 1e-6 and not kids:
                c = from_to(dt, ds)
        if c is None:
            p = b.parent
            while p and p not in corr:
                p = tgt.bones[p].parent
            c = corr.get(p, IDENTITY) if p else IDENTITY
        corr[name] = c

    # Height: the root's height above the lowest joint of each rest pose.
    t_heights = [tgt.bones[n].origin[1] for n in tgt.order]
    t_floor = min(min(t_heights), 0.0)
    t_root_h = tgt.bones[root].origin[1] - t_floor
    s_low = min(p[1] for p in rest_pos)
    s_root_h = rest_pos[src_root][1] - s_low
    scale = t_root_h / s_root_h if s_root_h > 1e-6 else 1.0

    end = src.duration if source_end is None else min(source_end, src.duration)
    begin = max(0.0, source_start)
    if end < begin:
        raise MotionError("The source range is empty.")
    count = int(math.floor((end - begin) / speed * fps + 1e-6)) + 1

    world_at, placed = _unplaced(src, src_root, begin)
    first = world_at(begin)
    first_root = m_vec(fix, first[src_root].pos)
    floor_note = "the file's floor is at height 0"
    floor_y = 0.0
    if abs(first_root[1] - s_root_h) > 0.5 * s_root_h:
        floor_y = first_root[1] - s_root_h  # the file is not standing on y = 0
        floor_note = "the file's floor is not at 0; the first frame is taken as standing on the floor"

    rest_inv = {j: m_t(rest[j].lin) for j in set(bmap.pairs.values())}
    rotations: dict[str, list[list[float]]] = {n: [] for n in tgt.order if n in bmap.pairs}
    root_positions: list[list[float]] = []
    predicted: dict[int, dict[str, Vec]] = {}
    prev: dict[str, Vec] = {}
    travel = 0.0
    last_xz = None
    wanted = set(frames_only) if frames_only is not None else None
    for f in range(count):
        frame = start_frame + f
        if wanted is not None and frame not in wanted:
            continue
        t = begin + f * speed / fps
        world = world_at(t)
        world_g: dict[str, Mat] = {}
        dials: dict[str, Vec] = {}
        for name in tgt.order:
            b = tgt.bones[name]
            parent_g = world_g.get(b.parent, IDENTITY) if b.parent else IDENTITY
            j = bmap.pairs.get(name)
            if j is None:
                world_g[name] = parent_g
                continue
            # The bone's change from its rest pose, in (fixed) world space.
            d = m_mul(m_mul(fix, orthonormal(world[j].lin)), rest_inv[j])
            g = m_mul(d, corr[name])
            rel = m_mul(m_t(parent_g), g)
            ang = dial_angles(rel, b.order, b.orient, convention, prev.get(name))
            prev[name] = ang
            dials[name] = ang
            world_g[name] = m_mul(parent_g, dial_rotation(ang, b.order, b.orient, convention))
            rotations[name].append([frame, round(ang[0], 3), round(ang[1], 3), round(ang[2], 3)])
        rp = m_vec(fix, world[src_root].pos)
        delta = (0.0, 0.0, 0.0)
        if root_motion:
            x = (rp[0] - first_root[0]) * scale
            z = (rp[2] - first_root[2]) * scale
            y = (rp[1] - floor_y) * scale + t_floor
            if in_place:
                x = z = 0.0
            if last_xz is not None:
                travel += math.hypot(x - last_xz[0], z - last_xz[1])
            last_xz = (x, z)
            target = (x, y, z)
            delta = v_sub(target, (0.0, tgt.bones[root].origin[1], 0.0))
            tr = dial_translation(delta, tgt.bones[root].orient, convention)
            root_positions.append([frame, round(tr[0], 3), round(tr[1], 3), round(tr[2], 3)])
        if wanted is not None or f in (0, count // 2, count - 1):
            tr = root_positions[-1][1:] if root_motion else None
            pos, _ = tgt.fk(dials, tuple(tr) if tr else None, convention)
            predicted[frame] = pos
    return RetargetResult(rotations, root, root_positions, count, (int(round(begin * src.fps)),
                          int(round(end * src.fps))), fps, round(scale, 4), yaw, up, floor_note,
                          round(travel, 1), predicted, placed)


def _unplaced(src: SourceMotion, root: int, begin: float):
    """A world_at that takes out where the file placed its character.

    The joints above the mapped root are not mapped (the figure node of an FBX
    exported from Daz, an Armature object), but they hold how the character
    was placed: Ana turned 90 degrees to walk along +X keeps that turn there,
    and her bind pose does not. Their change from the rest pose at the first
    frame is that placement; it is taken out of every frame, so the motion is
    told in the character's own space (facing +Z) and the target figure walks
    its own way forward. Their motion after the first frame stays.
    Returns (world_at, degrees turned)."""
    anc = src.parents[root] if 0 <= root < len(src.parents) else -1
    if anc < 0:
        return src.world_at, 0.0
    now = src.world_at(begin)[anc]
    rest = src.rest[anc]
    turn = m_mul(orthonormal(now.lin), m_t(orthonormal(rest.lin)))
    angle = rot_angle(turn)
    shift = v_len(v_sub(now.pos, rest.pos))
    if angle < 0.01 and shift < 1e-6:
        return src.world_at, 0.0
    back = m_t(turn)

    def world_at(t: float) -> list[Xform]:
        out = []
        for x in src.world_at(t):
            out.append(Xform(m_mul(back, x.lin), v_add(m_vec(back, v_sub(x.pos, now.pos)), rest.pos)))
        return out

    return world_at, round(angle, 1)


def _mapped_below(tgt: TargetSkeleton, name: str, pairs: dict[str, int]) -> list[str]:
    """The nearest mapped bones below one, looking through unmapped bones."""
    out: list[str] = []
    for c in tgt.children(name):
        out += [c] if c in pairs else _mapped_below(tgt, c, pairs)
    return out


def _depth(src: SourceMotion, j: int) -> int:
    d = 0
    while src.parents[j] >= 0:
        j = src.parents[j]
        d += 1
    return d


# ------------------------------------------------- checking against Daz --
def pose_error(tgt: TargetSkeleton, predicted: dict[str, Vec], measured: dict[str, list[float]]) -> float | None:
    """Mean difference in degrees between the joint angles we expect and the ones
    Daz shows. Joint angles do not change with where the figure stands, how it
    is turned or its size, so they compare well across both."""
    diffs = []
    for name in tgt.order:
        b = tgt.bones[name]
        p = b.parent
        g = tgt.bones[p].parent if p else None
        if not p or not g:
            continue
        if not all(n in predicted and n in measured for n in (name, p, g)):
            continue
        m = {n: tuple(measured[n]) for n in (name, p, g)}
        if v_len(v_sub(m[name], m[p])) < 0.5 or v_len(v_sub(m[p], m[g])) < 0.5:
            continue
        a = angle_between(v_sub(predicted[name], predicted[p]), v_sub(predicted[p], predicted[g]))
        bm = angle_between(v_sub(m[name], m[p]), v_sub(m[p], m[g]))
        diffs.append(abs(a - bm))
    root = tgt.root()
    for end in [n for n in tgt.order if not tgt.children(n)]:
        for other in [n for n in tgt.order if not tgt.children(n)]:
            if end >= other:
                continue
            if not all(n in predicted and n in measured for n in (root, end, other)):
                continue
            a = angle_between(v_sub(predicted[end], predicted[root]), v_sub(predicted[other], predicted[root]))
            bm = angle_between(v_sub(tuple(measured[end]), tuple(measured[root])),
                               v_sub(tuple(measured[other]), tuple(measured[root])))
            diffs.append(abs(a - bm))
    return sum(diffs) / len(diffs) if diffs else None


# ---------------------------------------------------------- foot contact --
FOOT_BONES = {
    "genesis9": {"l": ["l_foot", "l_toes"], "r": ["r_foot", "r_toes"]},
    "genesis8": {"l": ["lFoot", "lToe"], "r": ["rFoot", "rToe"]},
}


def foot_bones(tgt: TargetSkeleton) -> dict[str, list[str]]:
    rig, _ = detect_rig(list(tgt.bones), TARGET_RIGS)
    if rig in FOOT_BONES:
        return {s: [b for b in names if b in tgt.bones] for s, names in FOOT_BONES[rig].items()}
    out: dict[str, list[str]] = {"l": [], "r": []}
    for n in tgt.bones:
        low = n.lower()
        if "foot" in low or "toe" in low:
            side = "l" if low.startswith(("l_", "l", "left")) else "r" if low.startswith(("r_", "r", "right")) else None
            if side:
                out[side].append(n)
    return out


def contact_heights(tgt: TargetSkeleton, feet: dict[str, list[str]], samples: dict[int, dict[str, list[float]]],
                    floor: float, scale: float) -> dict[int, dict[str, dict]]:
    """Per frame and foot: the lowest point (sole) height above the floor and its x, z."""
    out: dict[int, dict[str, dict]] = {}
    for frame, pos in samples.items():
        row = {}
        for side, bones in feet.items():
            best = None
            for b in bones:
                if b not in pos:
                    continue
                rest_h = tgt.bones[b].origin[1] * scale  # how high the joint is when standing
                h = pos[b][1] - rest_h - floor
                if best is None or h < best["height"]:
                    best = {"height": h, "x": pos[b][0], "z": pos[b][2], "bone": b}
            if best:
                row[side] = best
        out[frame] = row
    return out


def contact_report(heights: dict[int, dict[str, dict]], tolerance: float = 1.0) -> dict:
    """Frames below the floor or floating, and how far each foot slides while it
    is planted (the longest slide of one planted phase). Slides are measured on
    the point touching the floor (heel or toes) and only while that point stays
    the same, so rolling from heel to toes is not counted."""
    frames = sorted(heights)
    below, floating = [], []
    contact = {"l": 0, "r": 0}
    phase = {"l": 0.0, "r": 0.0}
    worst = {"l": 0.0, "r": 0.0}
    last: dict[str, dict | None] = {"l": None, "r": None}
    lowest = None
    for f in frames:
        row = heights[f]
        if not row:
            continue
        low = min(v["height"] for v in row.values())
        lowest = low if lowest is None else min(lowest, low)
        if low < -tolerance:
            below.append(f)
        if low > tolerance:
            floating.append(f)
        for side, v in row.items():
            if v["height"] <= tolerance:
                contact[side] = contact.get(side, 0) + 1
                prev = last.get(side)
                if prev is not None and prev["bone"] == v["bone"]:
                    phase[side] += math.hypot(v["x"] - prev["x"], v["z"] - prev["z"])
                    worst[side] = max(worst[side], phase[side])
                last[side] = v
            else:
                last[side] = None
                phase[side] = 0.0
    return {
        "frames_checked": len(frames),
        "lowest_cm": round(lowest, 2) if lowest is not None else None,
        "frames_below_floor": _ranges(below),
        "frames_floating": _ranges(floating),
        "contact_frames": contact,
        "slide_cm": {k: round(v, 1) for k, v in worst.items()},
    }


def _ranges(frames: list[int]) -> list[list[int]]:
    out: list[list[int]] = []
    for f in frames:
        if out and f == out[-1][1] + 1:
            out[-1][1] = f
        else:
            out.append([f, f])
    return out


# ------------------------------------------------------------- summary --
def describe(src: SourceMotion, path: Path) -> dict:
    rig, score = detect_rig(src.names, SOURCE_RIGS)
    rest_pos = [x.pos for x in src.rest]
    low = min(p[1] for p in rest_pos) if rest_pos else 0
    high = max(p[1] for p in rest_pos) if rest_pos else 0
    out = {
        "path": path.as_posix(), "format": src.format, "fps": round(src.fps, 3), "frames": src.frames,
        "seconds": round(src.duration, 3), "bones": len(src.names),
        "bone_names": src.names[:200], "rig": rig if score >= 4 else None,
        "rest_pose": src.rest_source, "rest_height_raw": round(high - low, 2), "warnings": list(src.warnings),
    }
    if src.format == "fbx":
        out["units_cm_per_unit"] = src.unit_cm
        out["takes"] = src.takes
        out["take"] = src.take
    if rig and score >= 4:
        roles = SOURCE_RIGS[rig]
        by = {bare(n): i for i, n in enumerate(src.names)}
        lu, ru = by.get(roles["l_upperarm"].lower()), by.get(roles["l_forearm"].lower())
        if lu is not None and ru is not None:
            d = v_norm(v_sub(rest_pos[ru], rest_pos[lu]))
            out["arms_at_rest"] = "T pose" if abs(d[1]) < 0.35 else "A pose" if abs(d[1]) < 0.85 else "arms down"
        hips = by.get(roles["hips"].lower())
        if hips is not None:
            first = src.world_at(0.0)[hips].pos
            last = src.world_at(src.duration)[hips].pos
            out["root_travel_raw"] = round(math.hypot(last[0] - first[0], last[2] - first[2]), 2)
    else:
        out["warnings"].append("The rig was not recognized; pass bone_map to anim_import.")
    return out
