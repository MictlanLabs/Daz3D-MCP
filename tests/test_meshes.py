"""OBJ and FBX inspection, without Daz."""

from __future__ import annotations

import pytest

from asset_fixture import box_vertices, write_blender_room_fbx, write_cape_fbx, write_fbx, write_obj
from daz3d_mcp import meshes


def test_obj_in_meters_with_textures(tmp_path):
    obj = write_obj(tmp_path / "Table.obj", [-0.9, 0, -0.5], [0.9, 0.78, 0.5], materials=("Wood", "Metal"))
    info = meshes.inspect_mesh(obj)
    assert info["format"] == "obj" and info["vertices"] == 8
    assert info["surfaces"] == ["Metal", "Wood"]
    assert info["bbox_raw"]["size"] == [1.8, 0.78, 1.0]
    assert info["textures"] == ["textures/metal_diffuse.png", "textures/wood_diffuse.png"]
    scale, units, _ = meshes.import_scale(info, "auto")
    assert (scale, units) == (100.0, "m")


def test_obj_units_guess_and_missing_texture(tmp_path):
    cm = write_obj(tmp_path / "a" / "Chair.obj", [-25, 0, -25], [25, 95, 25], missing_texture=True)
    info = meshes.inspect_mesh(cm)
    assert meshes.import_scale(info, "auto")[1] == "cm"
    assert info["missing_textures"] and "missing" in info["warnings"][0]
    mm = write_obj(tmp_path / "b" / "Bracket.obj", [0, 0, 0], [400, 9000, 300], mtl=False)
    assert meshes.import_scale(meshes.inspect_mesh(mm), "auto")[1] == "mm"
    assert meshes.import_scale(meshes.inspect_mesh(mm), "in")[0] == 2.54


def test_binary_fbx(tmp_path):
    cape = write_cape_fbx(tmp_path)
    info = meshes.inspect_mesh(cape)
    assert info["format"] == "fbx-binary"
    assert info["units_in_file"] == {"cm_per_unit": 100.0, "name": "m"}
    assert info["meshes"] == 1 and not info["rigged"]
    assert info["surfaces"] == ["Cape Lining", "Cape Outer"]
    assert info["bbox_raw"]["size"] == [0.64, 0.97, 0.16]


def test_rigged_uncompressed_fbx(tmp_path):
    f = write_fbx(tmp_path / "Robot.fbx", box_vertices([-30, 0, -20], [30, 170, 20]), bones=("Hips", "Spine"),
                  compress=False, up_axis=2)
    info = meshes.inspect_mesh(f)
    assert info["rigged"] and info["up_axis"] == "Z"
    assert any("skeleton" in w for w in info["warnings"])


def test_ascii_fbx(tmp_path):
    f = tmp_path / "Lamp.fbx"
    f.write_text('; FBX 7.4.0 project file\nFBXHeaderExtension:  {\n}\nGlobalSettings:  {\n Properties70:  {\n'
                 '  P: "UnitScaleFactor", "double", "Number", "",2.54\n }\n}\nObjects:  {\n'
                 ' Geometry: 1, "Geometry::", "Mesh" {\n  Vertices: *6 {\n   a: 0,0,0,4,20,4\n  }\n }\n'
                 ' Model: 2, "Model::Lamp", "Mesh" {\n }\n}\n')
    info = meshes.inspect_mesh(f)
    assert info["format"] == "fbx-ascii" and info["units_in_file"]["name"] == "in"
    assert info["bbox_raw"]["size"] == [4, 20, 4] and info["meshes"] == 1


def test_other_formats_are_refused(tmp_path):
    glb = tmp_path / "x.glb"
    glb.write_bytes(b"glTF")
    with pytest.raises(meshes.MeshError, match="Convert"):
        meshes.inspect_mesh(glb)


def test_blender_fbx_size_includes_object_transforms(tmp_path):
    info = meshes.inspect_mesh(write_blender_room_fbx(tmp_path / "Bedroom.fbx"))
    # The vertices alone look like a 4 m room in meters ...
    assert info["bbox_raw"]["size"] == [4.2, 3.6, 2.62]
    assert info["units_in_file"]["name"] == "cm"
    # ... but Daz applies the object's scale and -90 X turn: 114 m wide, Y up.
    box = info["bbox_cm"]
    assert box["size"] == pytest.approx([11429.71, 4753.31, 11429.71], abs=0.1)
    assert box["min"][1] == pytest.approx(-1814.24, abs=0.01) and box["max"][1] == pytest.approx(2939.07, abs=0.01)
    assert info["suggested_scale"] == 0.1
    assert any("10x too big" in w and "scale=0.1" in w for w in info["warnings"])
    assert any("non-uniform object scale" in w for w in info["warnings"])
    assert info["extra_nodes"] == ["Camera", "Light"]
    assert info["transparent_surfaces"] == ["Windows"]
    assert info["objects"][0] == {"name": "Room", "kind": "Mesh", "scale": [2721.36, 3174.92, 1814.24],
                                  "rotation": [-90.0, 0.0, 0.0]}


def test_plain_fbx_has_no_size_advice(tmp_path):
    info = meshes.inspect_mesh(write_cape_fbx(tmp_path))
    assert info["bbox_cm"]["size"] == [64, 97, 16]
    assert "suggested_scale" not in info and info["transparent_surfaces"] == [] and "extra_nodes" not in info


def test_size_advice():
    assert meshes.size_advice([11468, 6553, 8330])[0] == 0.1
    assert meshes.size_advice([540, 370, 630]) == (None, None)
    assert meshes.size_advice([0.42, 0.3, 0.2])[0] == 10
    assert meshes.size_advice([900000, 1, 1])[0] == 0.001
    assert meshes.size_advice([0, 0, 0]) == (None, None)


def test_obj_transparent_surfaces_from_mtl(tmp_path):
    obj = write_obj(tmp_path / "Window.obj", [-50, 0, -2], [50, 120, 2], materials=("Frame", "Glass"))
    mtl = obj.with_suffix(".mtl")
    mtl.write_text(mtl.read_text().replace("newmtl Glass\n", "newmtl Glass\nd 0.2\n"))
    assert meshes.inspect_mesh(obj)["transparent_surfaces"] == ["Glass"]
