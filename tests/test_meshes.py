"""OBJ and FBX inspection, without Daz."""

from __future__ import annotations

import pytest

from asset_fixture import box_vertices, write_cape_fbx, write_fbx, write_obj
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
