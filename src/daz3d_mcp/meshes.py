"""Reads OBJ and FBX files before Daz Studio imports them.

Daz works in centimeters with Y up. An OBJ has no units at all, and FBX files
from Blender, Maya or 3ds Max come in meters, centimeters or inches. Reading
the file here lets import_mesh pick the right scale, and tells the agent what
it is about to import (size, materials, missing textures, rigged or not)
without loading anything into Daz.
"""

from __future__ import annotations

import math
import re
import struct
import zlib
from pathlib import Path

# cm per unit; the OBJ importer's "Scale" option is exactly this number.
UNITS_CM = {"cm": 1.0, "m": 100.0, "mm": 0.1, "in": 2.54, "ft": 30.48, "poser": 243.84}
MAX_OBJ_BYTES = 512 * 1024 * 1024


class MeshError(Exception):
    pass


def guess_units(height: float) -> tuple[str, str]:
    """Units for a model of this raw height, and why.

    Most downloads are people, clothing, furniture or props between 2 cm and
    30 m tall, so a raw height that is implausible in centimeters points at
    meters (Blender, glTF exports) or millimeters (CAD, 3D printing).
    """
    if height <= 0:
        return "cm", "the model is flat or empty; kept as centimeters"
    if height < 4:
        return "m", f"raw height {height:g} would be {height:g} cm, so the file is most likely in meters"
    if height > 5000:
        return "mm", f"raw height {height:g} would be {height / 100:g} m, so the file is most likely in millimeters"
    return "cm", f"raw height {height:g} is a plausible size in centimeters"


# ---------------------------------------------------------------- OBJ --
def _mtl_textures(mtl: Path, opacity: dict[str, float] | None = None) -> tuple[list[str], list[str], list[str]]:
    """Materials, textures found and missing; opacity gets each material's d (or 1 - Tr) when it has one."""
    materials, found, missing = [], [], []
    try:
        lines = mtl.read_text("utf-8", errors="replace").splitlines()
    except OSError:
        return materials, found, missing
    for line in lines:
        parts = line.strip().split()
        if not parts:
            continue
        if parts[0] == "newmtl" and len(parts) > 1:
            materials.append(" ".join(parts[1:]))
        elif parts[0] in ("d", "Tr") and len(parts) > 1 and materials and opacity is not None:
            try:
                v = float(parts[-1])
            except ValueError:
                continue
            opacity[materials[-1]] = v if parts[0] == "d" else 1.0 - v
        elif parts[0].lower().startswith(("map_", "bump", "disp", "norm", "refl")) and len(parts) > 1:
            # The file name is the last token; options such as -bm 1.0 come first.
            name = parts[-1].replace("\\", "/")
            p = Path(name) if Path(name).is_absolute() else mtl.parent / name
            if not p.is_file():
                # Exporters often write an absolute path from the author's machine.
                alt = mtl.parent / Path(name).name
                p = alt if alt.is_file() else p
            (found if p.is_file() else missing).append(name)
    return materials, sorted(set(found)), sorted(set(missing))


def inspect_obj(path: Path) -> dict:
    if path.stat().st_size > MAX_OBJ_BYTES:
        raise MeshError(f"{path.name} is larger than {MAX_OBJ_BYTES >> 20} MB; import it without inspection "
                        "by giving units explicitly.")
    mn = [float("inf")] * 3
    mx = [float("-inf")] * 3
    verts = faces = 0
    groups: set[str] = set()
    usemtl: set[str] = set()
    mtllibs: list[str] = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("v "):
                parts = line.split()
                try:
                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                except (IndexError, ValueError):
                    continue
                verts += 1
                if x < mn[0]: mn[0] = x  # noqa: E701
                if x > mx[0]: mx[0] = x  # noqa: E701
                if y < mn[1]: mn[1] = y  # noqa: E701
                if y > mx[1]: mx[1] = y  # noqa: E701
                if z < mn[2]: mn[2] = z  # noqa: E701
                if z > mx[2]: mx[2] = z  # noqa: E701
            elif line.startswith("f "):
                faces += 1
            elif line.startswith(("g ", "o ")):
                groups.add(line[2:].strip())
            elif line.startswith("usemtl "):
                usemtl.add(line[7:].strip())
            elif line.startswith("mtllib "):
                mtllibs.append(line[7:].strip())
    if not verts:
        raise MeshError(f"{path.name} has no vertices; it is not a valid OBJ mesh.")
    materials, found, missing = [], [], []
    opacity: dict[str, float] = {}
    missing_mtl = []
    for lib in mtllibs:
        mtl = path.parent / lib
        if not mtl.is_file():
            missing_mtl.append(lib)
            continue
        m, f, x = _mtl_textures(mtl, opacity)
        materials += m
        found += f
        missing += x
    size = [mx[i] - mn[i] for i in range(3)]
    out = {
        "format": "obj",
        "path": path.as_posix(),
        "vertices": verts,
        "faces": faces,
        "groups": sorted(groups)[:50],
        "surfaces": sorted(usemtl)[:100],
        "bbox_raw": {"min": _r(mn), "max": _r(mx), "size": _r(size)},
        "units_in_file": None,
        "up_axis": "Y",
        "rigged": False,
        "animated": False,
        "textures": found,
        "missing_textures": missing,
        "transparent_surfaces": sorted(n for n, v in opacity.items() if v < 0.95),
        "warnings": [],
    }
    if missing_mtl:
        out["warnings"].append(f"Material library {', '.join(missing_mtl)} is missing: the mesh imports grey.")
    if missing:
        out["warnings"].append(f"{len(missing)} textures named in the .mtl are missing, e.g. {missing[0]}.")
    if size[2] > 0 and size[1] > 0 and size[2] > 3 * size[1] and size[2] > size[0]:
        out["warnings"].append("The model is much deeper (Z) than tall (Y): it may be Z-up (from Blender or 3ds Max "
                               "without 'Y up'). Use up_axis='Z' if it imports lying down.")
    return out


def _r(v: list[float]) -> list[float]:
    return [round(x, 4) for x in v]


# ---------------------------------------------------------------- FBX --
class _FbxNode:
    __slots__ = ("name", "props", "children")

    def __init__(self, name: str, props: list, children: list):
        self.name = name
        self.props = props
        self.children = children

    def find(self, name: str) -> "_FbxNode | None":
        for c in self.children:
            if c.name == name:
                return c
        return None

    def find_all(self, name: str) -> list["_FbxNode"]:
        return [c for c in self.children if c.name == name]


_ARRAY = {b"f": ("f", 4), b"d": ("d", 8), b"l": ("q", 8), b"i": ("i", 4), b"b": ("?", 1)}
_SCALAR = {b"Y": ("<h", 2), b"C": ("<?", 1), b"I": ("<i", 4), b"F": ("<f", 4), b"D": ("<d", 8), b"L": ("<q", 8)}
_WANTED_ARRAYS = {"Vertices"}


def _read_props(data: bytes, pos: int, count: int, want_arrays: bool) -> tuple[list, int]:
    props = []
    for _ in range(count):
        code = data[pos:pos + 1]
        pos += 1
        if code in _SCALAR:
            fmt, n = _SCALAR[code]
            props.append(struct.unpack_from(fmt, data, pos)[0])
            pos += n
        elif code in _ARRAY:
            length, encoding, clen = struct.unpack_from("<III", data, pos)
            pos += 12
            raw = data[pos:pos + clen]
            pos += clen
            if want_arrays:
                if encoding == 1:
                    raw = zlib.decompress(raw)
                fmt, _n = _ARRAY[code]
                props.append(list(struct.unpack(f"<{length}{fmt}", raw[:length * _n])))
            else:
                props.append(None)
        elif code in (b"S", b"R"):
            (length,) = struct.unpack_from("<I", data, pos)
            pos += 4
            raw = data[pos:pos + length]
            pos += length
            props.append(raw.decode("utf-8", "replace") if code == b"S" else raw)
        else:
            raise MeshError(f"Unknown FBX property type {code!r}.")
    return props, pos


def _read_binary(data: bytes, wanted: set[str] | frozenset[str] = frozenset(_WANTED_ARRAYS)) -> list[_FbxNode]:
    """The node tree of a binary FBX; arrays are decoded only for nodes named in wanted."""
    version = struct.unpack_from("<I", data, 23)[0]
    wide = version >= 7500
    head = 25 if wide else 13

    def node(pos: int) -> tuple[_FbxNode | None, int]:
        if wide:
            end, nprops, _plen = struct.unpack_from("<QQQ", data, pos)
        else:
            end, nprops, _plen = struct.unpack_from("<III", data, pos)
        name_len = data[pos + head - 1]
        if end == 0:
            return None, pos + head
        name = data[pos + head:pos + head + name_len].decode("ascii", "replace")
        p = pos + head + name_len
        props, p = _read_props(data, p, nprops, name in wanted)
        children = []
        while p < end:
            child, p = node(p)
            if child is None:
                break
            children.append(child)
        return _FbxNode(name, props, children), end

    nodes = []
    pos = 27
    while pos < len(data) - head:
        n, pos = node(pos)
        if n is None:
            break
        nodes.append(n)
    return nodes


_ASCII_P = re.compile(r'P:\s*"([^"]+)"\s*,\s*"[^"]*"\s*,\s*"[^"]*"\s*,\s*"[^"]*"\s*,\s*([-\d.eE+]+)')


def _ascii_summary(text: str) -> dict:
    props = {m.group(1): float(m.group(2)) for m in _ASCII_P.finditer(text)}
    meshes = len(re.findall(r'Model:\s*[^\n]*"Mesh"', text))
    rigged = bool(re.search(r'Deformer:\s*[^\n]*"Skin"', text))
    animated = bool(re.search(r"AnimationCurve:", text))
    materials = re.findall(r'Material:\s*\d*,?\s*"Material::([^"]*)"', text)
    verts: list[float] = []
    for m in re.finditer(r"Vertices:\s*\*\d+\s*\{\s*a:\s*([^}]*)\}", text):
        verts += [float(x) for x in m.group(1).replace("\n", "").split(",") if x.strip()]
    textures = re.findall(r'(?:Relative)?FileName:\s*"([^"]+)"', text)
    return {"props": props, "meshes": meshes, "rigged": rigged, "animated": animated,
            "materials": materials, "verts": verts, "textures": textures}


def _binary_summary(data: bytes) -> dict:
    nodes = _read_binary(data)
    top = {n.name: n for n in nodes}
    props: dict[str, float] = {}
    gs = top.get("GlobalSettings")
    p70 = gs.find("Properties70") if gs else None
    for p in (p70.find_all("P") if p70 else []):
        if len(p.props) >= 5 and isinstance(p.props[0], str) and isinstance(p.props[4], (int, float)):
            props[p.props[0]] = float(p.props[4])
    objects = top.get("Objects")
    meshes = rigged = animated = 0
    materials: list[str] = []
    opacity: dict[str, float] = {}
    verts: list[float] = []
    textures: list[str] = []
    models: dict[int, dict] = {}
    geometries: dict[int, list[float]] = {}
    for o in (objects.children if objects else []):
        kind = o.props[2] if len(o.props) > 2 else ""
        name = o.props[1].split("\x00")[0] if len(o.props) > 1 and isinstance(o.props[1], str) else ""
        oid = o.props[0] if o.props and isinstance(o.props[0], int) else None
        if o.name == "Model":
            if kind == "Mesh":
                meshes += 1
            if oid is not None:
                models[oid] = {"name": name, "kind": kind or "Null", **_model_transform(o)}
        elif o.name == "Deformer" and kind == "Skin":
            rigged += 1
        elif o.name in ("AnimationCurve", "AnimationCurveNode"):
            animated += 1
        elif o.name == "Material":
            materials.append(name)
            op = _material_opacity(_p70(o))
            if op is not None:
                opacity[name] = op
        elif o.name == "Geometry":
            v = o.find("Vertices")
            if v and v.props and v.props[0]:
                verts += v.props[0]
                if oid is not None:
                    geometries[oid] = v.props[0]
        elif o.name in ("Texture", "Video"):
            for key in ("RelativeFilename", "FileName"):
                f = o.find(key)
                if f and f.props and isinstance(f.props[0], str) and f.props[0]:
                    textures.append(f.props[0])
                    break
    parents: dict[int, int] = {}
    conns = top.get("Connections")
    for c in (conns.find_all("C") if conns else []):
        if len(c.props) >= 3 and c.props[0] == "OO" and isinstance(c.props[1], int) and isinstance(c.props[2], int):
            parents.setdefault(c.props[1], c.props[2])
    return {"props": props, "meshes": meshes, "rigged": bool(rigged), "animated": bool(animated),
            "materials": materials, "verts": verts, "textures": textures, "opacity": opacity,
            "models": models, "geometries": geometries, "parents": parents}


# ------------------------------------------------- FBX object transforms --
# Blender keeps an object's unapplied scale and rotation (and its meters to
# centimeters factor) on the FBX Model, not in the vertices. Daz Studio keeps
# them as the node's transform, so the size it shows is vertices * transform.
def _p70(o: _FbxNode) -> dict[str, list]:
    p70 = o.find("Properties70")
    out: dict[str, list] = {}
    for p in (p70.find_all("P") if p70 else []):
        if p.props and isinstance(p.props[0], str):
            out[p.props[0]] = p.props[4:]
    return out


def _vec(values: list | None, default: float) -> list[float]:
    if not values or len(values) < 3 or not all(isinstance(v, (int, float)) for v in values[:3]):
        return [default] * 3
    return [float(v) for v in values[:3]]


def _model_transform(o: _FbxNode) -> dict:
    p = _p70(o)
    order = p.get("RotationOrder")
    return {"t": _vec(p.get("Lcl Translation"), 0.0), "r": _vec(p.get("Lcl Rotation"), 0.0),
            "s": _vec(p.get("Lcl Scaling"), 1.0), "pre": _vec(p.get("PreRotation"), 0.0),
            "order": int(order[0]) if order and isinstance(order[0], int) else 0}


def _material_opacity(p: dict[str, list]) -> float | None:
    """0 (clear) to 1 (solid) from an FBX material, or None when it does not say."""
    if p.get("Opacity") and isinstance(p["Opacity"][0], (int, float)):
        return float(p["Opacity"][0])
    if p.get("TransparencyFactor") and isinstance(p["TransparencyFactor"][0], (int, float)):
        return 1.0 - float(p["TransparencyFactor"][0])
    return None


_ORDERS = ["XYZ", "XZY", "YZX", "YXZ", "ZXY", "ZYX"]  # FBX EFbxRotationOrder


def _rot(deg: list[float], order: int = 0) -> list[list[float]]:
    """Rotation matrix of FBX Euler angles; the first letter of the order turns first."""
    out = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    for axis in _ORDERS[order if 0 <= order < 6 else 0]:
        a = math.radians(deg["XYZ".index(axis)])
        c, s = math.cos(a), math.sin(a)
        if axis == "X":
            m = [[1, 0, 0], [0, c, -s], [0, s, c]]
        elif axis == "Y":
            m = [[c, 0, s], [0, 1, 0], [-s, 0, c]]
        else:
            m = [[c, -s, 0], [s, c, 0], [0, 0, 1]]
        out = _mm(m, out)
    return out


def _mm(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _local(m: dict) -> tuple[list[list[float]], list[float]]:
    """(3x3, translation) of one Model: T * PreRotation * Rotation * Scale."""
    r = _mm(_rot(m["pre"]), _rot(m["r"], m["order"]))
    s = m["s"]
    return [[r[i][j] * s[j] for j in range(3)] for i in range(3)], list(m["t"])


def _world(mid: int, models: dict, parents: dict) -> tuple[list[list[float]], list[float]]:
    lin, t = _local(models[mid])
    seen = {mid}
    p = parents.get(mid)
    while p in models and p not in seen:
        seen.add(p)
        plin, pt = _local(models[p])
        t = [sum(plin[i][k] * t[k] for k in range(3)) + pt[i] for i in range(3)]
        lin = _mm(plin, lin)
        p = parents.get(p)
    return lin, t


def _placed_box(s: dict) -> tuple[list[float], list[float]] | None:
    """Bounding box of every mesh with its object transforms, in file units."""
    models, parents = s.get("models") or {}, s.get("parents") or {}
    mn = [float("inf")] * 3
    mx = [float("-inf")] * 3
    found = False
    for gid, v in (s.get("geometries") or {}).items():
        mid = parents.get(gid)
        if mid not in models:
            continue
        lin, t = _world(mid, models, parents)
        for i in range(3):
            a, b, c = lin[i]
            vals = [a * v[k] + b * v[k + 1] + c * v[k + 2] for k in range(0, len(v) - 2, 3)]
            if vals:
                mn[i] = min(mn[i], min(vals) + t[i])
                mx[i] = max(mx[i], max(vals) + t[i])
                found = True
    return (mn, mx) if found else None


def size_advice(size_cm: list[float]) -> tuple[float | None, str | None]:
    """A power-of-ten scale that brings an implausible size back to a room, prop or person, and why.

    Rooms, furniture, people and props are between about 1 cm and 50 m. A
    model 10x or 100x outside that range nearly always has a stray object
    scale or unit, not a real size.
    """
    longest = max(size_cm) if size_cm else 0
    if longest <= 0:
        return None, None
    exp = 0
    while longest * 10 ** exp > 5000:
        exp -= 1
    while longest * 10 ** exp < 1:
        exp += 1
    if exp == 0:
        return None, None
    scale = 10.0 ** exp
    return scale, (f"It comes in {_length(longest)} across, which is not a believable size for a room, prop or "
                   f"person. The model is most likely {_times(scale)} (an unapplied object scale or a wrong unit in "
                   f"the program it came from). Import it with scale={scale:g} ({_length(longest * scale)} "
                   "across), or give height= for an exact size.")


def _length(cm: float) -> str:
    if cm >= 100000:
        return f"{cm / 100000:.3g} km"
    if cm >= 100:
        return f"{cm / 100:.3g} m"
    if cm >= 1:
        return f"{cm:.3g} cm"
    return f"{cm * 10:.3g} mm"


def _times(scale: float) -> str:
    return f"{1 / scale:g}x too big" if scale < 1 else f"{scale:g}x too small"


def inspect_fbx(path: Path) -> dict:
    data = path.read_bytes()
    if data.startswith(b"Kaydara FBX Binary"):
        try:
            s = _binary_summary(data)
        except (struct.error, zlib.error, IndexError) as exc:
            raise MeshError(f"{path.name} could not be read as binary FBX ({exc}).") from exc
        fmt = "fbx-binary"
    else:
        text = data.decode("utf-8", "replace")
        if "FBXHeaderExtension" not in text:
            raise MeshError(f"{path.name} is not an FBX file.")
        s = _ascii_summary(text)
        fmt = "fbx-ascii"
    v = s["verts"]
    out: dict = {"format": fmt, "path": path.as_posix(), "meshes": s["meshes"], "rigged": s["rigged"],
                 "animated": s["animated"], "surfaces": sorted(set(s["materials"]))[:100], "warnings": []}
    unit = s["props"].get("UnitScaleFactor")
    out["units_in_file"] = {"cm_per_unit": unit, "name": _unit_name(unit)} if unit else None
    up = s["props"].get("UpAxis")
    out["up_axis"] = {0: "X", 1: "Y", 2: "Z"}.get(int(up), "Y") if up is not None else "Y"
    if len(v) >= 3:
        xs, ys, zs = v[0::3], v[1::3], v[2::3]
        mn, mx = [min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]
        out["vertices"] = len(v) // 3
        out["bbox_raw"] = {"min": _r(mn), "max": _r(mx), "size": _r([mx[i] - mn[i] for i in range(3)])}
    else:
        out["vertices"] = 0
        out["bbox_raw"] = None
    unit_cm = unit or 1.0
    placed = _placed_box(s) if s.get("models") else None
    if placed:
        mn, mx = [v * unit_cm for v in placed[0]], [v * unit_cm for v in placed[1]]
        if out["up_axis"] == "Z":  # the importer turns Z-up into Daz's Y-up
            mn, mx = [mn[0], mn[2], -mx[1]], [mx[0], mx[2], -mn[1]]
        out["bbox_cm"] = {"min": _r(mn), "max": _r(mx), "size": _r([mx[i] - mn[i] for i in range(3)])}
    elif out["bbox_raw"]:
        b = out["bbox_raw"]
        out["bbox_cm"] = {k: _r([x * unit_cm for x in b[k]]) for k in ("min", "max", "size")}
    else:
        out["bbox_cm"] = None
    objects = []
    for m in (s.get("models") or {}).values():
        if m["kind"] == "LimbNode":
            continue
        o = {"name": m["name"], "kind": m["kind"]}
        if m["kind"] == "Mesh":
            o["scale"] = _r(m["s"])
            o["rotation"] = _r(m["r"])
        objects.append(o)
    out["objects"] = objects[:50]
    extras = [o["name"] for o in objects if o["kind"] in ("Camera", "Light", "Null")]
    if extras:
        out["extra_nodes"] = extras
        out["warnings"].append(f"It also holds {', '.join(extras)} (camera, light or empty object from the program "
                               "it came from); import_mesh leaves them out unless keep_empties=true.")
    clear = sorted(n for n, v in (s.get("opacity") or {}).items() if v < 0.95)
    out["transparent_surfaces"] = clear
    if clear:
        out["warnings"].append(f"Surfaces {', '.join(clear)} are see-through in the file; import_mesh makes them "
                               "Iray glass unless glass=false.")
    odd = [o for o in objects if o.get("scale") and max(map(abs, o["scale"])) > 1.02 * min(map(abs, o["scale"]))]
    if odd:
        out["warnings"].append(f"{odd[0]['name']} has an unapplied non-uniform object scale {odd[0]['scale']}: Daz "
                               "keeps it as the node's X/Y/Z scale. In Blender, Object > Apply > All Transforms "
                               "before exporting gives a clean node.")
    if out["bbox_cm"]:
        scale, why = size_advice(out["bbox_cm"]["size"])
        if scale:
            out["suggested_scale"] = scale
            out["warnings"].append(why)
    found, missing = [], []
    for t in sorted(set(s["textures"])):
        name = t.replace("\\", "/")
        p = Path(name) if Path(name).is_absolute() else path.parent / name
        if not p.is_file() and (path.parent / Path(name).name).is_file():
            p = path.parent / Path(name).name
        (found if p.is_file() else missing).append(name)
    out["textures"] = found
    out["missing_textures"] = missing
    if missing:
        out["warnings"].append(f"{len(missing)} textures the FBX points to are missing, e.g. {missing[0]}. "
                               "Embedded textures are fine; otherwise put them next to the .fbx.")
    if out["up_axis"] == "Z":
        out["warnings"].append("The file is Z-up; the Daz FBX importer converts the axes itself.")
    if s["rigged"]:
        out["warnings"].append("The FBX has a skeleton: it imports as a figure with its own bones, not a Daz "
                               "Genesis rig. To wear it on a Genesis figure use wearable_from_mesh.")
    return out


def _unit_name(cm_per_unit: float | None) -> str | None:
    if not cm_per_unit:
        return None
    for name, value in UNITS_CM.items():
        if abs(value - cm_per_unit) < 1e-6 * max(1.0, value):
            return name
    return f"{cm_per_unit:g} cm"


def inspect_mesh(path: Path) -> dict:
    if not path.is_file():
        raise MeshError(f"{path} does not exist.")
    ext = path.suffix.lower()
    if ext == ".obj":
        info = inspect_obj(path)
    elif ext == ".fbx":
        info = inspect_fbx(path)
    else:
        raise MeshError(f"Daz Studio imports .obj and .fbx; {path.name} is {ext or 'unknown'}. Convert it first "
                        "(Blender: File > Export > FBX).")
    info["size_bytes"] = path.stat().st_size
    return info


def import_scale(info: dict, units: str) -> tuple[float, str, str]:
    """(cm per file unit for the OBJ importer, units used, why)."""
    if units != "auto":
        if units not in UNITS_CM:
            raise MeshError(f"Unknown units {units!r}; use one of auto, {', '.join(UNITS_CM)}.")
        return UNITS_CM[units], units, "given"
    if info["format"].startswith("fbx"):
        # The Daz FBX importer reads the file's own unit and converts to cm.
        unit = info.get("units_in_file") or {}
        return 1.0, unit.get("name") or "cm", "the FBX file states its units; the importer converts them"
    box = info.get("bbox_raw") or {}
    size = box.get("size") or [0, 0, 0]
    up = 2 if info.get("up_axis") == "Z" else 1
    name, why = guess_units(max(size[up], max(size) * 0.25))
    return UNITS_CM[name], name, why
