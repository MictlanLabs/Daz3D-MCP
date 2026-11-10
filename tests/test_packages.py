"""Package inspection and installation, without Daz."""

from __future__ import annotations

import zipfile

import pytest

from asset_fixture import JACKET, build_mesh_zip, build_store_zip
from daz3d_mcp import packages
from daz3d_mcp.packages import PackageError


def _plan(path, tmp_path):
    return packages.summarize(packages.plan_package(path, tmp_path / "t"))


@pytest.fixture
def store_zip(tmp_path):
    return build_store_zip(tmp_path / "downloads" / "LeatherJacket_G9.zip")


def test_finds_the_content_root_inside_wrappers(store_zip, tmp_path):
    (tmp_path / "t").mkdir()
    s = _plan(store_zip, tmp_path)
    assert s["layout"] == "daz"
    assert s["content_root"] == "LeatherJacket_G9/Content"
    assert s["library_folders"] == ["People", "Runtime", "data"]
    assert JACKET in s["loadable"]
    assert s["loadable_total"] == 2  # the jacket and its material preset; data/ files are not loadable
    assert set(s["extras"]) == {"LeatherJacket_G9/Promo/promo_01.jpg", "LeatherJacket_G9/ReadMe.txt"}
    assert s["meshes"] == []


@pytest.mark.parametrize("prefix", ["", "My Library/", "Products/Vendor/Thing/DAZ Studio/"])
def test_root_at_any_depth(tmp_path, prefix):
    z = tmp_path / "p.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr(prefix + "Props/Vendor/Lamp/Lamp.duf", '{"asset_info": {"type": "prop"}}')
        zf.writestr(prefix + "data/Vendor/Lamp/lamp.dsf", "{}")
        zf.writestr("Read me.pdf", "x")
    (tmp_path / "t").mkdir()
    s = _plan(z, tmp_path)
    assert s["content_root"] == prefix.rstrip("/")
    assert s["loadable"] == ["Props/Vendor/Lamp/Lamp.duf"]


def test_poser_runtime_package(tmp_path):
    z = tmp_path / "poser.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("Runtime/libraries/Pose/Vendor/Wave.pz2", "{}")
        zf.writestr("Runtime/Textures/Vendor/skin.jpg", "x")
    (tmp_path / "t").mkdir()
    s = _plan(z, tmp_path)
    assert s["layout"] == "poser"
    assert s["loadable"] == ["Runtime/libraries/Pose/Vendor/Wave.pz2"]


def test_nested_zips_and_unsafe_paths(tmp_path, store_zip):
    outer = tmp_path / "bundle.zip"
    with zipfile.ZipFile(outer, "w") as zf:
        zf.write(store_zip, "parts/LeatherJacket_G9.zip")
        zf.writestr("../../evil.duf", "x")
        zf.writestr("/abs/evil.duf", "x")
    (tmp_path / "t").mkdir()
    s = _plan(outer, tmp_path)
    assert s["nested_archives"] == ["parts/LeatherJacket_G9.zip"]
    assert JACKET in s["loadable"]
    assert sum("unsafe path" in w for w in s["warnings"]) == 2


def test_model_download_is_kept_for_import(tmp_path):
    z = build_mesh_zip(tmp_path / "table.zip", tmp_path / "work")
    (tmp_path / "t").mkdir()
    s = _plan(z, tmp_path)
    assert s["layout"] == "meshes"
    assert s["meshes"] == ["tavern_table/source/Table.obj"]


def test_rejects_other_archives(tmp_path):
    rar = tmp_path / "x.rar"
    rar.write_bytes(b"Rar!")
    with pytest.raises(PackageError, match="not supported"):
        packages.plan_package(rar, tmp_path)
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"nope")
    with pytest.raises(PackageError, match="not a valid"):
        packages.plan_package(bad, tmp_path)


def test_size_limit(store_zip, tmp_path):
    with pytest.raises(PackageError, match="limit"):
        packages.plan_package(store_zip, tmp_path, max_bytes=10)


def test_install_conflicts_reinstall_and_uninstall(store_zip, tmp_path, daz_home):
    lib = tmp_path / "Third Party Library"
    res = packages.install(store_zip, lib)
    assert res["installed_files"] == 5 and res["layout"] == "daz"
    jacket = next(i for i in res["items"] if i["name"] == "Leather Jacket")
    assert jacket["kind"] == "clothing" and jacket["generation"] == "Genesis 9"
    assert jacket["thumbnail"].endswith("Leather Jacket.duf.png")
    assert (lib / JACKET).is_file() and not (lib / "Promo").exists() and not (lib / "__MACOSX").exists()

    again = packages.install(store_zip, lib)  # same files: nothing to do
    assert again["installed_files"] == 0 and again["already_there"] == 5

    # Another package wrote a different file at the same path.
    other = tmp_path / "other.zip"
    with zipfile.ZipFile(other, "w") as zf:
        zf.writestr("Content/" + JACKET, "different")
    with pytest.raises(PackageError, match="overwrite=true"):
        packages.install(other, lib)
    packages.install(other, lib, overwrite=True)

    assert {p["package"] for p in packages.list_packages()} == {"leatherjacket-g9", "other"}
    out = packages.uninstall("leatherjacket-g9")
    assert out["kept_shared"] == 1  # the jacket .duf belongs to "other" too
    assert (lib / JACKET).is_file()
    assert not (lib / "data").exists()  # emptied folders are removed
    packages.uninstall("other")
    assert not (lib / "People").exists()
    with pytest.raises(PackageError, match="No installed package"):
        packages.uninstall("other")


def test_mesh_package_goes_to_imports(tmp_path, daz_home):
    z = build_mesh_zip(tmp_path / "table.zip", tmp_path / "work")
    res = packages.install(z, tmp_path / "lib")
    assert res["layout"] == "meshes" and res["installed_files"] == 0
    (mesh,) = res["meshes"]
    assert mesh.endswith("imports/table/Table.obj")
    assert (daz_home / "imports" / "table" / "Table.mtl").is_file()
    assert (daz_home / "imports" / "table" / "textures" / "wood_diffuse.png").is_file()
