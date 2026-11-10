"""Builds a small fake Daz content library for the tests.

Each file is a .duf with a real-looking "asset_info" header (what the MCP
server reads) and a "dazmcp_fake" block (what fake_daz.js does on load).
"""

from __future__ import annotations

import base64
import gzip
import json
from pathlib import Path

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")


def _cloth(color):
    return {
        "Base Color": {"type": "color", "value": color, "mappable": True, "map": None},
        "Glossy Roughness": {"type": "float", "value": 0.7, "min": 0, "max": 1, "mappable": True},
        "Cutout Opacity": {"type": "float", "value": 1, "min": 0, "max": 1, "mappable": True},
    }


def _wearable(label, name, bbox, surface, color, generation="Genesis 9"):
    return {"add": [{"label": label, "name": name, "follows": True, "generation": generation, "geometry": True,
                     "bbox_local": bbox,
                     "materials": [{"name": surface, "label": surface, "shader": "Iray Uber", "props": _cloth(color)}]}]}


def _light(label, position, rotation):
    return {"label": label, "name": label, "class": "DzSpotLight", "position": position, "rotation": rotation,
            "props": {"Luminous Flux (Lumen)": {"type": "float", "value": 3000, "min": 0, "max": 1e7},
                      "Color": {"type": "color", "value": [1, 1, 1]}}}


LIBRARY: dict[str, tuple[str, dict]] = {
    "People/Genesis 9/Genesis 9.duf": ("figure", {"add": [{"template": "genesis9"}]}),
    "People/Genesis 9/Characters/Ana 9.duf": (
        "character", {"morphs": {"Ana 9 Body": 1, "Ana 9 Head": 1}, "materials": {"*": {"Base Color": [0.86, 0.68, 0.58]}}}),
    "People/Genesis 9/Characters/Leo 9.duf": (
        "character", {"morphs": {"Leo 9 Body": 1, "Leo 9 Head": 1}, "materials": {"*": {"Base Color": [0.55, 0.38, 0.28]}}}),
    "People/Genesis 9/Clothing/Basic Wear/Basic Wear Shirt.duf": (
        "wearable", _wearable("Basic Wear Shirt", "BasicWearShirt", [[-25, 100, -14], [25, 152, 16]], "Shirt", [0.9, 0.9, 0.9])),
    "People/Genesis 9/Clothing/Basic Wear/Basic Wear Pants.duf": (
        "wearable", _wearable("Basic Wear Pants", "BasicWearPants", [[-22, 5, -13], [22, 106, 14]], "Pants", [0.1, 0.15, 0.3])),
    "People/Genesis 9/Clothing/Summer Dress/Summer Dress.duf": (
        "wearable", _wearable("Summer Dress", "SummerDress", [[-30, 60, -16], [30, 150, 18]], "Dress", [0.9, 0.7, 0.2])),
    "People/Genesis 9/Clothing/Shoes/Canvas Sneakers.duf": (
        "wearable", _wearable("Canvas Sneakers", "CanvasSneakers", [[-14, 0, -12], [14, 12, 16]], "Sneakers", [1, 1, 1])),
    "People/Genesis 9/Hair/Short Bob Hair.duf": (
        "wearable", _wearable("Short Bob Hair", "ShortBobHair", [[-12, 150, -14], [12, 182, 14]], "Hair", [0.2, 0.1, 0.05])),
    "People/Genesis 9/Hair/Buzz Cut Hair.duf": (
        "wearable", _wearable("Buzz Cut Hair", "BuzzCutHair", [[-10, 160, -12], [10, 180, 12]], "Hair", [0.05, 0.05, 0.05])),
    "People/Genesis 9/Poses/Standing Casual.duf": (
        "preset_pose", {"pose": {"l_upperarm": [0, 0, -65], "r_upperarm": [0, 0, 65], "head": [-5, 10, 0],
                                 "l_thigh": [-4, 0, 3]}}),
    "People/Genesis 9/Poses/Arms Crossed.duf": (
        "preset_pose", {"pose": {"l_upperarm": [30, -40, -50], "r_upperarm": [30, 40, 50], "l_forearm": [0, -110, 0],
                                 "r_forearm": [0, 110, 0]}}),
    "People/Genesis 9/Poses/Waving.duf": (
        "preset_pose", {"pose": {"r_upperarm": [0, 0, -40], "r_forearm": [0, 0, -100], "head": [0, -8, 0]}}),
    "People/Genesis 9/Materials/Basic Wear Shirt Red.duf": (
        "preset_material", {"materials": {"Shirt": {"Base Color": [0.7, 0.1, 0.1]}}}),
    "People/Genesis 8 Female/Clothing/Old Jacket.duf": (
        "wearable", _wearable("Old Jacket", "OldJacket", [[-26, 100, -15], [26, 152, 17]], "Jacket", [0.3, 0.2, 0.1],
                              generation="Genesis 8")),
    "Props/Furniture/Wooden Chair.duf": (
        "prop", {"add": [{"label": "Wooden Chair", "name": "WoodenChair", "class": "DzNode", "geometry": True,
                          "bbox_local": [[-25, 0, -25], [25, 95, 25]],
                          "materials": [{"name": "Wood", "label": "Wood", "props": _cloth([0.5, 0.3, 0.1])}]}]}),
    "Light Presets/Studio/Three Point Lights.duf": (
        "scene_subset", {"add": [_light("Key", [150, 220, 250], [-25, 30, 0]),
                                 _light("Fill", [-200, 160, 200], [-15, -45, 0]),
                                 _light("Rim", [0, 250, -250], [-30, 180, 0])]}),
    # Things the index must skip.
    "data/DAZ 3D/Genesis 9/Base/Morphs/ignored.duf": ("modifier", {}),
    "People/Genesis 9/Genesis 9.duf.png": ("", {}),
}

GZIPPED = {"People/Genesis 9/Clothing/Summer Dress/Summer Dress.duf"}
THUMBNAILS = ["People/Genesis 9/Hair/Short Bob Hair.png", "People/Genesis 9/Genesis 9.png"]


def build_library(root: Path) -> Path:
    for rel, (asset_type, fake) in LIBRARY.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if rel.endswith(".png"):
            path.write_bytes(PNG)
            continue
        doc = {
            "file_version": "0.6.0.0",
            "asset_info": {"id": "/" + rel.replace(" ", "%20"), "type": asset_type,
                           "contributor": {"author": "Test", "email": "", "website": ""}, "revision": "1.0"},
            "dazmcp_fake": fake,
        }
        data = json.dumps(doc, indent=1).encode()
        path.write_bytes(gzip.compress(data) if rel in GZIPPED else data)
    for rel in THUMBNAILS:
        (root / rel).write_bytes(PNG)
    return root
