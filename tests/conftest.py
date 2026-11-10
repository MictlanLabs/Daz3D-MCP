from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from fake_daz.fake_bridge import FakeBridge  # noqa: E402

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is needed to run DazScript in tests")


@pytest.fixture
def daz_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "daz3d-mcp-home"
    monkeypatch.setenv("DAZ3D_MCP_HOME", str(home))
    monkeypatch.delenv("DAZ3D_MCP_TRANSPORT", raising=False)
    monkeypatch.delenv("DAZ3D_MCP_ALLOW_SCRIPTS", raising=False)
    return home


@pytest.fixture
def scene_file(tmp_path) -> Path:
    path = tmp_path / "living room.duf"
    shutil.copy(HERE / "fixtures_scene.json", path)
    return path


@pytest.fixture
def bridge(daz_home, tmp_path):
    if shutil.which("node") is None:
        pytest.skip("Node.js is needed to run DazScript in tests")
    b = FakeBridge(daz_home, tmp_path / "fake-state.json").start()
    yield b
    b.stop()
