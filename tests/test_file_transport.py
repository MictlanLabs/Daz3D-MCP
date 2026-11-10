"""No-plugin mode: the MCP launches the Daz executable with a script file."""

from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path

import pytest

from daz3d_mcp.client import DazClient
from daz3d_mcp.settings import Settings

HERE = Path(__file__).resolve().parent


@pytest.mark.skipif(shutil.which("node") is None or sys.platform == "win32", reason="needs Node.js on POSIX")
def test_file_transport_round_trip(daz_home, tmp_path, scene_file, monkeypatch):
    exe = tmp_path / "DAZStudio"
    exe.write_text(f'#!/bin/sh\nexec node "{HERE / "fake_daz" / "fake_daz_exe.js"}" "$1"\n')
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("DAZMCP_FAKE_STATE", str(tmp_path / "state.json"))

    client = DazClient(Settings(transport="file", daz_executable=str(exe), timeout=30))
    assert client.run_tool("scene_open", {"path": scene_file.as_posix()})["node_count"] == 6
    info = client.run_tool("scene_info")
    assert any(n["label"] == "Sofa" for n in info["nodes"])
    # The queue folder is cleaned after each request.
    assert not any((daz_home / "queue").iterdir())
