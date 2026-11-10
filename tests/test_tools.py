"""Runs the real DazScript tools through the client and a fake bridge."""

from __future__ import annotations

import json

import pytest

from daz3d_mcp.client import DazClient
from daz3d_mcp.settings import Settings
from daz3d_mcp.transport import DazError, HttpTransport


@pytest.fixture
def client(bridge):
    return DazClient(Settings(transport="http"))


def test_status(client):
    result = client.run_tool("status")
    assert result["version"].startswith("6.")
    assert result["scene"]["node_count"] == 0


def test_open_describe_save(client, scene_file, tmp_path):
    opened = client.run_tool("scene_open", {"path": scene_file.as_posix()})
    assert opened["node_count"] == 6

    info = client.run_tool("scene_info")
    labels = {n["label"]: n for n in info["nodes"]}
    assert "hip" not in labels  # bones hidden by default
    assert labels["Genesis 9"]["type"] == "figure"
    assert labels["Genesis 9"]["bone_count"] == 140
    assert labels["Genesis 9 Toulouse Shirt"]["type"] == "fitted_figure"
    assert labels["Genesis 9 Toulouse Shirt"]["fitted_to"] == "Genesis 9"
    assert labels["Sofa"]["type"] == "prop"
    assert labels["Sofa"]["rotation"] == [0, 180, 0]
    assert labels["Camera 1"]["type"] == "camera"
    assert labels["Key Light"]["type"] == "light"
    assert info["counts"]["bone"] == 1
    assert info["scene"]["primary_selection"]["label"] == "Genesis 9"

    with_bones = client.run_tool("scene_info", {"include_bones": True})
    assert any(n["label"] == "hip" for n in with_bones["nodes"])

    out = tmp_path / "copy"
    saved = client.run_tool("scene_save", {"path": out.as_posix()})
    assert saved["saved"].endswith("copy.duf")
    assert json.loads((tmp_path / "copy.duf").read_text())["nodes"]


def test_refuses_to_lose_unsaved_work(client, scene_file):
    client.run_tool("scene_open", {"path": scene_file.as_posix()})
    client.run_code("Scene.findNodeByLabel('Sofa').setLabel('Couch'); return true;")
    with pytest.raises(DazError) as err:
        client.run_tool("scene_open", {"path": scene_file.as_posix()})
    assert err.value.code == "unsaved_changes"
    with pytest.raises(DazError):
        client.run_tool("scene_new")
    assert client.run_tool("scene_new", {"discard_changes": True}) == {"cleared": True}


def test_save_does_not_overwrite_other_files(client, scene_file, tmp_path):
    client.run_tool("scene_open", {"path": scene_file.as_posix()})
    other = tmp_path / "other.duf"
    other.write_text("{}")
    with pytest.raises(DazError) as err:
        client.run_tool("scene_save", {"path": other.as_posix()})
    assert err.value.code == "exists"
    client.run_tool("scene_save", {"path": other.as_posix(), "overwrite": True})


def test_open_missing_file(client, tmp_path):
    with pytest.raises(DazError) as err:
        client.run_tool("scene_open", {"path": (tmp_path / "nope.duf").as_posix()})
    assert err.value.code == "not_found"


def test_viewport_capture_scales_and_restores_camera(client, scene_file, daz_home):
    client.run_tool("scene_open", {"path": scene_file.as_posix()})
    out = daz_home / "cap.png"
    result = client.run_tool("viewport_capture", {"out_path": out.as_posix(), "max_size": 512, "camera": "Camera 1"})
    assert result["method"] == "captureImage"
    assert (result["width"], result["height"]) == (512, 288)
    assert result["camera"] == "Camera 1"
    assert out.read_bytes().startswith(b"\x89PNG")
    after = client.run_tool("scene_info")
    assert after["scene"]["viewport_camera"] == "Perspective View"


def test_viewport_capture_fallback(client, daz_home, monkeypatch):
    monkeypatch.setenv("DAZMCP_FAKE_NO_CAPTURE", "1")
    out = daz_home / "cap.png"
    result = client.run_tool("viewport_capture", {"out_path": out.as_posix()})
    assert result["method"] == "saveThumbnailImage"
    assert out.is_file()


def test_black_frame_uses_fallback(client, daz_home, monkeypatch):
    monkeypatch.setenv("DAZMCP_FAKE_BLACK_FRAME", "1")
    result = client.run_tool("viewport_capture", {"out_path": (daz_home / "cap.png").as_posix()})
    assert result["method"] == "saveThumbnailImage"


def test_run_script_returns_value_and_log(client):
    result, log = client.run_code("DazMcp.log('hello ' + args.who); return {n: Scene.getNumNodes()};", {"who": "Ana"})
    assert result == {"n": 0}
    assert log == ["hello Ana"]


def test_run_script_error(client):
    with pytest.raises(DazError) as err:
        client.run_code("throw DazMcp.fail('bad_args', 'Nothing is selected.');")
    assert err.value.code == "bad_args"
    assert "Nothing is selected" in err.value.message


def test_wrong_token_is_rejected(bridge, daz_home):
    (daz_home / "token").write_text("0" * 64)
    with pytest.raises(DazError) as err:
        HttpTransport().status()
    assert err.value.code == "unauthorized"


def test_bridge_not_running(daz_home):
    with pytest.raises(DazError) as err:
        HttpTransport().status()
    assert err.value.code == "bridge_not_found"
    assert "doctor" in (err.value.hint or "")
