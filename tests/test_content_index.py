"""The content library index and search run in Python, without Daz."""

from __future__ import annotations

import json

from content_fixture import build_library

from daz3d_mcp.content import ContentIndex, generation_of, kind_of, read_asset_type


def _index(tmp_path, **kw):
    lib = build_library(tmp_path / "My Library")
    return lib, ContentIndex([str(lib)], cache_path=tmp_path / "index.json", **kw).load()


def test_reads_plain_and_gzip_headers(tmp_path):
    lib = build_library(tmp_path / "lib")
    assert read_asset_type(lib / "People/Genesis 9/Genesis 9.duf") == "figure"
    assert read_asset_type(lib / "People/Genesis 9/Clothing/Summer Dress/Summer Dress.duf") == "wearable"
    (tmp_path / "broken.duf").write_bytes(b"\x1f\x8bnot gzip")
    assert read_asset_type(tmp_path / "broken.duf") is None


def test_kinds_and_generations():
    assert kind_of("People/Genesis 9/Hair/Short Bob Hair.duf", "wearable") == "hair"
    assert kind_of("People/Genesis 9/Clothing/Basic Wear/Shirt.duf", "wearable") == "clothing"
    assert kind_of("People/Genesis 9/Poses/Walk.duf", "preset_pose") == "pose"
    assert kind_of("People/Genesis 9/Poses/Walk.duf", None) == "pose"
    assert kind_of("Light Presets/Studio/Three Point.duf", "scene_subset") == "light"
    assert kind_of("Something/Odd.duf", "preset_dforce") == "preset"
    assert generation_of("People/Genesis 8 Female/Clothing/x.duf") == "Genesis 8"
    assert generation_of("People/Genesis 8.1 Male/x.duf") == "Genesis 8.1"
    assert generation_of("Runtime/G9 Outfit/x.duf") == "Genesis 9"
    assert generation_of("Props/Chair.duf") is None


def test_search(tmp_path):
    lib, idx = _index(tmp_path)
    assert idx.file_count == 17  # data/ and .png files are skipped

    hair = idx.search(kind="hair")["results"]
    assert {r["name"] for r in hair} == {"Short Bob Hair", "Buzz Cut Hair"}
    bob = [r for r in hair if r["name"] == "Short Bob Hair"][0]
    assert bob["thumbnail"].endswith("Short Bob Hair.png")
    assert bob["generation"] == "Genesis 9"
    assert bob["path"] == (lib / "People/Genesis 9/Hair/Short Bob Hair.duf").as_posix()

    shirts = idx.search("shirt")["results"]
    assert shirts[0]["name"] == "Basic Wear Shirt"  # name matches rank above folder matches
    assert idx.search("basic wear", kind="material")["results"][0]["kind"] == "material"

    g9_clothes = {r["name"] for r in idx.search(kind="clothing", generation="Genesis 9", limit=50)["results"]}
    assert "Old Jacket" not in g9_clothes and "Summer Dress" in g9_clothes
    poses = idx.search(folder="People/Genesis 9/Poses")["results"]
    assert {r["kind"] for r in poses} == {"pose"} and len(poses) == 3


def test_paging(tmp_path):
    _, idx = _index(tmp_path)
    first = idx.search(kind="clothing", limit=2)
    assert first["more"] and first["next_offset"] == 2
    rest = idx.search(kind="clothing", limit=50, offset=2)
    names = [r["name"] for r in first["results"] + rest["results"]]
    assert len(names) == len(set(names)) == 5


def test_cache_is_reused_and_refreshed(tmp_path):
    lib, idx = _index(tmp_path)
    idx.search(kind="pose")
    cached = json.loads((tmp_path / "index.json").read_text())
    assert any(v[1] == "preset_pose" for v in cached["types"].values())

    (lib / "Props/New Lamp.duf").write_text('{"asset_info": {"type": "prop"}}')
    again = ContentIndex([str(lib)], cache_path=tmp_path / "index.json").load()
    assert again.file_count == 17  # still the cached list
    fresh = ContentIndex([str(lib)], cache_path=tmp_path / "index.json").load(refresh=True)
    assert fresh.file_count == 18
    expired = ContentIndex([str(lib)], cache_path=tmp_path / "index.json", max_age_hours=0).load()
    assert expired.file_count == 18


def test_resolve_relative_paths(tmp_path):
    lib, idx = _index(tmp_path)
    assert idx.resolve("People/Genesis 9/Genesis 9.duf") == lib / "People/Genesis 9/Genesis 9.duf"
    assert idx.resolve("nope.duf") is None
    assert idx.kind_for(lib / "People/Genesis 9/Poses/Waving.duf") == "pose"
