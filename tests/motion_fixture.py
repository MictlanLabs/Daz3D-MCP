"""Animation files for the tests, written the way real exporters write them.

- A Mixamo "FBX Binary" download: a mixamorig: skeleton in T pose whose joints
  have Mixamo-style local axes (Y along the bone, so every joint has a rest
  rotation), a bind pose, and Lcl Rotation / Lcl Translation curves at 30 fps.
- A CMU-style mocap BVH: Hips with 6 channels, ZXY rotation channels, zero
  rest rotations, T pose, inches.

Both carry the same motion, described in world space so the tests know what
the figure must end up doing: arms come down from the T pose to the sides,
the legs swing (the left forward first), the hips go forward 150 cm.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

from daz3d_mcp.motion import (IDENTITY, axis_angle, euler_mat, from_to, m_mul, m_t, m_vec, mat_euler, v_add,
                              v_norm, v_sub)

# Mixamo Y Bot sized, cm, facing +Z, T pose. (name, parent, world position)
MIXAMO_JOINTS = [
    ("Hips", None, (0.0, 104.0, 0.0)),
    ("Spine", "Hips", (0.0, 114.0, -1.0)),
    ("Spine1", "Spine", (0.0, 126.0, -1.0)),
    ("Spine2", "Spine1", (0.0, 139.0, -1.0)),
    ("Neck", "Spine2", (0.0, 153.0, -1.0)),
    ("Head", "Neck", (0.0, 162.0, 1.0)),
    ("HeadTop_End", "Head", (0.0, 181.0, 2.0)),
    ("LeftShoulder", "Spine2", (6.0, 148.0, -1.0)),
    ("LeftArm", "LeftShoulder", (18.0, 148.0, -2.0)),
    ("LeftForeArm", "LeftArm", (45.0, 148.0, -2.0)),
    ("LeftHand", "LeftForeArm", (70.0, 148.0, -2.0)),
    ("LeftHandMiddle1", "LeftHand", (79.0, 148.0, -2.0)),
    ("RightShoulder", "Spine2", (-6.0, 148.0, -1.0)),
    ("RightArm", "RightShoulder", (-18.0, 148.0, -2.0)),
    ("RightForeArm", "RightArm", (-45.0, 148.0, -2.0)),
    ("RightHand", "RightForeArm", (-70.0, 148.0, -2.0)),
    ("RightHandMiddle1", "RightHand", (-79.0, 148.0, -2.0)),
    ("LeftUpLeg", "Hips", (9.0, 97.0, 0.0)),
    ("LeftLeg", "LeftUpLeg", (9.0, 53.0, 0.0)),
    ("LeftFoot", "LeftLeg", (9.0, 9.0, -3.0)),
    ("LeftToeBase", "LeftFoot", (9.0, 2.0, 11.0)),
    ("LeftToe_End", "LeftToeBase", (9.0, 1.0, 18.0)),
    ("RightUpLeg", "Hips", (-9.0, 97.0, 0.0)),
    ("RightLeg", "RightUpLeg", (-9.0, 53.0, 0.0)),
    ("RightFoot", "RightLeg", (-9.0, 9.0, -3.0)),
    ("RightToeBase", "RightFoot", (-9.0, 2.0, 11.0)),
    ("RightToe_End", "RightToeBase", (-9.0, 1.0, 18.0)),
]

FRAMES = 61
FPS = 30
TRAVEL = 150.0
ARM_DOWN = 70.0  # degrees the arms come down from the T pose
SWING = 25.0     # thigh swing


def arm_down(t: float) -> float:
    return ARM_DOWN * min(1.0, t * 2)  # down within the first half second


def thigh_swing(frame: int) -> float:
    """Degrees the left thigh is forward (+) at a frame; the right is opposite."""
    return SWING * math.sin(2 * math.pi * frame / 30)


def world_deltas(frame: int) -> dict[str, tuple]:
    """Each moving joint's rotation from its rest pose, in world space."""
    t = frame / FPS
    a = arm_down(t)
    s = thigh_swing(frame)
    knee_l = max(0.0, -s) * 1.2  # the back leg bends its knee
    knee_r = max(0.0, s) * 1.2
    d = {
        "LeftArm": axis_angle((0, 0, 1), -a),   # the left arm (+X) goes down
        "RightArm": axis_angle((0, 0, 1), a),   # the right arm (-X) goes down
        # Forward swing: about -X (the leg's -Y turns toward +Z).
        "LeftUpLeg": axis_angle((1, 0, 0), -s),
        "RightUpLeg": axis_angle((1, 0, 0), s),
    }
    d["LeftLeg"] = m_mul(d["LeftUpLeg"], axis_angle((1, 0, 0), knee_l))
    d["RightLeg"] = m_mul(d["RightUpLeg"], axis_angle((1, 0, 0), knee_r))
    d["LeftForeArm"] = d["LeftArm"]
    d["RightForeArm"] = d["RightArm"]
    return d


def hips_position(frame: int) -> tuple[float, float, float]:
    return (0.0, 104.0 - 2.0 * abs(math.sin(2 * math.pi * frame / 30)), TRAVEL * frame / (FRAMES - 1))


def _rest_world() -> dict[str, tuple]:
    """Mixamo joint axes: local +Y along the bone (toward the child), X kept level."""
    pos = {n: p for n, _parent, p in MIXAMO_JOINTS}
    kids: dict[str, list[str]] = {}
    for n, parent, _p in MIXAMO_JOINTS:
        if parent:
            kids.setdefault(parent, []).append(n)
    out = {}
    for n, parent, p in MIXAMO_JOINTS:
        if n in kids:
            child = kids[n][0]
            d = v_sub(pos[child], p)
        elif parent:
            d = v_sub(p, pos[parent])
        else:
            d = (0, 1, 0)
        out[n] = from_to((0, 1, 0), d) if n != "Hips" else IDENTITY
    return out


def mixamo_pose(frame: int) -> tuple[dict, dict]:
    """World rotation and position of every joint at a frame."""
    rest = _rest_world()
    deltas = world_deltas(frame)
    parent_of = {n: p for n, p, _ in MIXAMO_JOINTS}
    rest_pos = {n: p for n, _parent, p in MIXAMO_JOINTS}
    rot: dict = {}
    pos: dict = {}
    for n, parent, p in MIXAMO_JOINTS:
        d = deltas.get(n)
        if d is None:
            # Follows its parent rigidly.
            d = m_mul(rot[parent], m_t(rest[parent])) if parent else IDENTITY
        rot[n] = m_mul(d, rest[n])
        if parent is None:
            pos[n] = hips_position(frame)
        else:
            pd = m_mul(rot[parent], m_t(rest[parent]))
            pos[n] = v_add(pos[parent], m_vec(pd, v_sub(p, rest_pos[parent])))
    del parent_of
    return rot, pos


# ----------------------------------------------------------- binary FBX --
def _prop(value) -> bytes:
    if isinstance(value, bool):
        return b"C" + struct.pack("<?", value)
    if isinstance(value, int):
        if -2**31 <= value < 2**31:
            return b"I" + struct.pack("<i", value)
        return b"L" + struct.pack("<q", value)
    if isinstance(value, float):
        return b"D" + struct.pack("<d", value)
    if isinstance(value, str):
        raw = value.encode()
        return b"S" + struct.pack("<I", len(raw)) + raw
    if isinstance(value, tuple) and value[0] == "L":
        return b"L" + struct.pack("<q", value[1])
    if isinstance(value, tuple) and value[0] in ("d", "f", "l"):
        code, items = value[0], value[1]
        fmt = {"d": "d", "f": "f", "l": "q"}[code]
        data = zlib.compress(struct.pack(f"<{len(items)}{fmt}", *items))
        return code.encode() + struct.pack("<III", len(items), 1, len(data)) + data
    raise TypeError(value)


def _node(name: str, props: list, children: list, offset: int) -> bytes:
    pbytes = b"".join(_prop(p) for p in props)
    head_len = 13 + len(name)
    body = b""
    pos = offset + head_len + len(pbytes)
    for c in children:
        cb = _node(*c, offset=pos)
        body += cb
        pos += len(cb)
    if children:
        body += b"\0" * 13
    end = offset + head_len + len(pbytes) + len(body)
    return struct.pack("<III", end, len(props), len(pbytes)) + bytes([len(name)]) + name.encode() + pbytes + body


def _p(name: str, kind: str, *values) -> tuple:
    return ("P", [name, kind, "", "A"] + list(values), [])


def write_mixamo_fbx(path: Path, prefix: str = "mixamorig:", unit_cm: float = 1.0) -> Path:
    rest = _rest_world()
    rest_pos = {n: p for n, _parent, p in MIXAMO_JOINTS}
    parent_of = {n: p for n, p, _ in MIXAMO_JOINTS}
    ids = {n: 1000 + i for i, (n, _p2, _x) in enumerate(MIXAMO_JOINTS)}
    objects = []
    conns = []
    for n, parent, p in MIXAMO_JOINTS:
        prot = rest[parent] if parent else IDENTITY
        local = m_mul(m_t(prot), rest[n])
        euler = mat_euler(local, "XYZ", "applied")
        tr = m_vec(m_t(prot), v_sub(p, rest_pos[parent])) if parent else p
        tr = tuple(v / unit_cm for v in tr)
        objects.append(("Model", [ids[n], f"{prefix}{n}\x00\x01Model", "LimbNode"], [
            ("Version", [232], []),
            ("Properties70", [], [
                _p("RotationOrder", "enum", 0),
                _p("Lcl Translation", "Lcl Translation", *[float(v) for v in tr]),
                _p("Lcl Rotation", "Lcl Rotation", *[float(v) for v in euler]),
                _p("Lcl Scaling", "Lcl Scaling", 1.0, 1.0, 1.0),
            ]),
        ]))
        conns.append(("C", ["OO", ids[n], ids[parent] if parent else 0], []))

    # Bind pose: world matrices, column-major, in file units.
    pose_nodes = []
    for n, _parent, p in MIXAMO_JOINTS:
        r = rest[n]
        m = [r[0][0], r[1][0], r[2][0], 0.0, r[0][1], r[1][1], r[2][1], 0.0,
             r[0][2], r[1][2], r[2][2], 0.0, p[0] / unit_cm, p[1] / unit_cm, p[2] / unit_cm, 1.0]
        pose_nodes.append(("PoseNode", [], [("Node", [("L", ids[n])], []), ("Matrix", [("d", m)], [])]))
    objects.append(("Pose", [5000, "Pose::BIND_POSES\x00\x01Pose", "BindPose"],
                    [("Type", ["BindPose"], []), ("NbPoseNodes", [len(pose_nodes)], [])] + pose_nodes))

    objects.append(("AnimationStack", [6000, "mixamo.com\x00\x01AnimStack", ""], []))
    objects.append(("AnimationLayer", [6001, "BaseLayer\x00\x01AnimLayer", ""], []))
    conns.append(("C", ["OO", 6001, 6000], []))

    poses = [mixamo_pose(f) for f in range(FRAMES)]
    ticks = [int(round(f / FPS * 46186158000)) for f in range(FRAMES)]
    next_id = 10000
    for n, parent, _p2 in MIXAMO_JOINTS:
        rots = []
        prev = None
        for rot, _pos in poses:
            prot = rot[parent] if parent else IDENTITY
            e = mat_euler(m_mul(m_t(prot), rot[n]), "XYZ", "applied", prev)
            prev = e
            rots.append(e)
        channels = [("R", "Lcl Rotation", rots)]
        if parent is None:
            channels.append(("T", "Lcl Translation", [tuple(v / unit_cm for v in pos[n]) for _r, pos in poses]))
        for short, prop, values in channels:
            cn = next_id
            next_id += 1
            objects.append(("AnimationCurveNode", [cn, f"{short}\x00\x01AnimCurveNode", ""], [
                ("Properties70", [], [_p("d|X", "Number", float(values[0][0])), _p("d|Y", "Number", float(values[0][1])),
                                      _p("d|Z", "Number", float(values[0][2]))])]))
            conns.append(("C", ["OO", cn, 6001], []))
            conns.append(("C", ["OP", cn, ids[n], prop], []))
            for a, axis in enumerate("XYZ"):
                cid = next_id
                next_id += 1
                objects.append(("AnimationCurve", [cid, "\x00\x01AnimCurve", ""], [
                    ("Default", [0.0], []),
                    ("KeyVer", [4009], []),
                    ("KeyTime", [("l", ticks)], []),
                    ("KeyValueFloat", [("f", [float(v[a]) for v in values])], []),
                ]))
                conns.append(("C", ["OP", cid, cn, f"d|{axis}"], []))

    top = [
        ("FBXHeaderExtension", [], [("FBXVersion", [7400], [])]),
        ("GlobalSettings", [], [("Properties70", [], [
            _p("UpAxis", "int", 1), _p("UnitScaleFactor", "double", float(unit_cm)), _p("TimeMode", "enum", 6),
        ])]),
        ("Objects", [], objects),
        ("Connections", [], conns),
    ]
    out = b"Kaydara FBX Binary  \x00\x1a\x00" + struct.pack("<I", 7400)
    for n in top:
        out += _node(*n, offset=len(out))
    out += b"\0" * 13 + b"\xfa\xbc\xab\x09\xd0\xc8\xd4\x66\xb1\x76\xfb\x83\x1c\xf7\x26\x7e" + b"\0" * 4
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out)
    return path


# ------------------------------------------------------------------ BVH --
CMU_RENAME = {"Spine": "LowerBack", "Spine1": "Spine", "Spine2": "Spine1"}


def write_bvh(path: Path, inches: bool = True) -> Path:
    """The same motion as a CMU-style BVH (zero rest rotations, ZXY channels)."""
    unit = 1 / 2.54 if inches else 1.0
    rest_pos = {n: p for n, _parent, p in MIXAMO_JOINTS}
    kids: dict[str, list[str]] = {}
    for n, parent, _p2 in MIXAMO_JOINTS:
        if parent:
            kids.setdefault(parent, []).append(n)
    ends = {n for n in rest_pos if n not in kids}
    lines = ["HIERARCHY"]
    order: list[str] = []

    def name(n: str) -> str:
        return CMU_RENAME.get(n, n)

    def emit(n: str, depth: int) -> None:
        pad = "  " * depth
        parent = next(p for j, p, _x in MIXAMO_JOINTS if j == n)
        off = v_sub(rest_pos[n], rest_pos[parent]) if parent else (0.0, 0.0, 0.0)
        off = tuple(v * unit for v in off)
        if n in ends:
            lines.append(f"{pad}End Site")
            lines.append(f"{pad}{{")
            lines.append(f"{pad}  OFFSET {off[0]:.4f} {off[1]:.4f} {off[2]:.4f}")
            lines.append(f"{pad}}}")
            return
        lines.append(f"{pad}{'ROOT' if parent is None else 'JOINT'} {name(n)}")
        lines.append(f"{pad}{{")
        lines.append(f"{pad}  OFFSET {off[0]:.4f} {off[1]:.4f} {off[2]:.4f}")
        if parent is None:
            lines.append(f"{pad}  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation")
        else:
            lines.append(f"{pad}  CHANNELS 3 Zrotation Xrotation Yrotation")
        order.append(n)
        for k in kids.get(n, []):
            emit(k, depth + 1)
        lines.append(f"{pad}}}")

    emit("Hips", 0)
    lines += ["MOTION", f"Frames: {FRAMES}", f"Frame Time: {1 / FPS:.6f}"]
    parent_of = {n: p for n, p, _x in MIXAMO_JOINTS}
    rest = _rest_world()
    for f in range(FRAMES):
        rot, pos = mixamo_pose(f)
        row = [v * unit for v in pos["Hips"]]
        prevs: dict = {}
        for n in order:
            # BVH rest rotations are zero: world = delta from the Mixamo rest.
            d = m_mul(rot[n], m_t(rest[n]))
            p = parent_of[n]
            dp = m_mul(rot[p], m_t(rest[p])) if p else IDENTITY
            local = m_mul(m_t(dp), d)
            e = mat_euler(local, "YXZ", "applied", prevs.get(n))  # channels Z X Y: Y applied first
            prevs[n] = e
            row += [e[2], e[0], e[1]]
        lines.append(" ".join(f"{v:.5f}" for v in row))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path


def expected_arm_direction(frame: int, side: str = "l") -> tuple:
    """Where the upper arm must point at a frame (world, unit vector)."""
    a = math.radians(arm_down(frame / FPS))
    x = math.cos(a)
    return (x if side == "l" else -x, -math.sin(a), 0.0)


def expected_thigh_direction(frame: int, side: str = "l") -> tuple:
    s = math.radians(thigh_swing(frame) * (1 if side == "l" else -1))
    return v_norm((0.0, -math.cos(s), math.sin(s)))


__all__ = ["write_mixamo_fbx", "write_bvh", "expected_arm_direction", "expected_thigh_direction", "FRAMES", "FPS",
           "TRAVEL", "euler_mat"]
