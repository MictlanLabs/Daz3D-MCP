"""Third-party assets for the tests: store packages (.zip) and loose OBJ / FBX
meshes, written the way real exporters write them."""

from __future__ import annotations

import json
import struct
import zipfile
import zlib
from pathlib import Path

from content_fixture import PNG, _wearable

# --------------------------------------------------------------- FBX ---
# Binary FBX 7.4: node records of (end offset, property count, property bytes,
# name), properties tagged with a one-letter type, nested nodes, a null record.


def _prop(value) -> bytes:
    if isinstance(value, bool):
        return b"C" + struct.pack("<?", value)
    if isinstance(value, int):
        return b"I" + struct.pack("<i", value)
    if isinstance(value, float):
        return b"D" + struct.pack("<d", value)
    if isinstance(value, str):
        raw = value.encode()
        return b"S" + struct.pack("<I", len(raw)) + raw
    if isinstance(value, tuple) and value[0] == "d":  # ("d", [floats], compress)
        data = struct.pack(f"<{len(value[1])}d", *value[1])
        if value[2]:
            comp = zlib.compress(data)
            return b"d" + struct.pack("<III", len(value[1]), 1, len(comp)) + comp
        return b"d" + struct.pack("<III", len(value[1]), 0, len(data)) + data
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


def write_fbx(path: Path, vertices: list[float], unit_cm: float = 1.0, materials=("Default",), bones=(),
              compress: bool = True, up_axis: int = 1) -> Path:
    header = b"Kaydara FBX Binary  \x00\x1a\x00" + struct.pack("<I", 7400)
    objects = [("Geometry", [1, "Geometry::Mesh\x00\x01Geometry", "Mesh"], [("Vertices", [("d", vertices, compress)], [])]),
               ("Model", [2, "Model::Mesh\x00\x01Model", "Mesh"], [])]
    for i, m in enumerate(materials):
        objects.append(("Material", [10 + i, f"{m}\x00\x01Material", ""], []))
    for i, b in enumerate(bones):
        objects.append(("Model", [100 + i, f"{b}\x00\x01Model", "LimbNode"], []))
    if bones:
        objects.append(("Deformer", [200, "Skin\x00\x01Deformer", "Skin"], []))
    top = [
        ("FBXHeaderExtension", [], [("FBXVersion", [7400], [])]),
        ("GlobalSettings", [], [("Properties70", [], [
            ("P", ["UpAxis", "int", "Integer", "", up_axis], []),
            ("P", ["UnitScaleFactor", "double", "Number", "", float(unit_cm)], []),
        ])]),
        ("Objects", [], objects),
    ]
    out = header
    for n in top:
        out += _node(*n, offset=len(out))
    out += b"\0" * 13 + b"\xfa\xbc\xab\x09\xd0\xc8\xd4\x66\xb1\x76\xfb\x83\x1c\xf7\x26\x7e" + b"\0" * 4
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out)
    return path


def box_vertices(mn, mx) -> list[float]:
    out: list[float] = []
    for x in (mn[0], mx[0]):
        for y in (mn[1], mx[1]):
            for z in (mn[2], mx[2]):
                out += [float(x), float(y), float(z)]
    return out


def write_cape_fbx(folder: Path) -> Path:
    """A cape modeled in Blender around a Genesis 9 in its default pose, saved in meters."""
    verts = box_vertices([-0.32, 0.55, -0.24], [0.32, 1.52, -0.08])
    return write_fbx(folder / "Hero Cape.fbx", verts, unit_cm=100.0, materials=("Cape Outer", "Cape Lining"))


# --------------------------------------------------------------- OBJ ---
def write_obj(path: Path, mn, mx, materials=("Wood",), mtl: bool = True, missing_texture: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if mtl:
        lines.append(f"mtllib {path.stem}.mtl")
    for x in (mn[0], mx[0]):
        for y in (mn[1], mx[1]):
            for z in (mn[2], mx[2]):
                lines.append(f"v {x} {y} {z}")
    lines.append("g body")
    for m in materials:
        lines.append(f"usemtl {m}")
        lines.append("f 1 2 3 4")
    path.write_text("\n".join(lines) + "\n")
    if mtl:
        mtl_lines = []
        for m in materials:
            mtl_lines += [f"newmtl {m}", "Kd 0.8 0.8 0.8", f"map_Kd textures/{m.lower()}_diffuse.png"]
            if not missing_texture:
                (path.parent / "textures").mkdir(exist_ok=True)
                (path.parent / "textures" / f"{m.lower()}_diffuse.png").write_bytes(PNG)
        (path.parent / f"{path.stem}.mtl").write_text("\n".join(mtl_lines) + "\n")
    return path


# ---------------------------------------------------------- packages ---
def _duf(rel: str, asset_type: str, fake: dict) -> bytes:
    doc = {"file_version": "0.6.0.0",
           "asset_info": {"id": "/" + rel.replace(" ", "%20"), "type": asset_type,
                          "contributor": {"author": "Vendor", "email": "", "website": ""}, "revision": "1.0"},
           "dazmcp_fake": fake}
    return json.dumps(doc, indent=1).encode()


JACKET = "People/Genesis 9/Clothing/StudioVendor/Leather Jacket/Leather Jacket.duf"


def build_store_zip(path: Path) -> Path:
    """A Renderosity-style package: a wrapper folder, an Install Manager style
    Content folder inside it, promo images and a readme beside it, and
    macOS junk."""
    top = "LeatherJacket_G9"
    jacket = _wearable("Leather Jacket", "LeatherJacket", [[-27, 98, -16], [27, 154, 18]], "Leather", [0.25, 0.15, 0.1])
    files = {
        f"{top}/Content/{JACKET}": _duf(JACKET, "wearable", jacket),
        f"{top}/Content/People/Genesis 9/Clothing/StudioVendor/Leather Jacket/Leather Jacket.duf.png": PNG,
        f"{top}/Content/People/Genesis 9/Clothing/StudioVendor/Leather Jacket/Materials/Leather Jacket Black.duf":
            _duf("People/Genesis 9/Clothing/StudioVendor/Leather Jacket/Materials/Leather Jacket Black.duf",
                 "preset_material", {"materials": {"Leather": {"Base Color": [0.03, 0.03, 0.03]}}}),
        f"{top}/Content/data/StudioVendor/LeatherJacket/LeatherJacket.dsf": b'{"file_version": "0.6.0.0"}',
        f"{top}/Content/Runtime/Textures/StudioVendor/LeatherJacket/leather_d.jpg": b"\xff\xd8fakejpeg",
        f"{top}/Promo/promo_01.jpg": b"\xff\xd8promo",
        f"{top}/ReadMe.txt": b"Install the Content folder into your library.",
        f"__MACOSX/{top}/._ReadMe.txt": b"junk",
        f"{top}/.DS_Store": b"junk",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return path


def build_mesh_zip(path: Path, work: Path) -> Path:
    """A model download (Sketchfab / CGTrader style): an OBJ, its .mtl and textures, no Daz content."""
    obj = write_obj(work / "tavern_table" / "source" / "Table.obj", [-0.9, 0, -0.5], [0.9, 0.78, 0.5])
    with zipfile.ZipFile(path, "w") as zf:
        for f in sorted(obj.parent.parent.rglob("*")):
            if f.is_file():
                zf.write(f, f.relative_to(work).as_posix())
    return path
