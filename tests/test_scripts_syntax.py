"""Every DazScript file must be plain ES5 so it runs on Daz Studio 4.x and 6."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from daz3d_mcp.scriptlib import available_tools, build_tool_code

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tests" / "fake_daz" / "check_es5.js"


def _check(tmp_path: Path, code: str) -> subprocess.CompletedProcess:
    f = tmp_path / "program.js"
    f.write_text(code, encoding="utf-8")
    return subprocess.run(["node", str(CHECKER), str(f)], capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")
@pytest.mark.parametrize("tool", available_tools())
def test_tool_is_es5(tool, tmp_path):
    res = _check(tmp_path, build_tool_code(tool))
    if "acorn not installed" in res.stderr:
        pytest.skip("acorn is not installed (npm install --prefix tests/fake_daz acorn)")
    assert res.returncode == 0, res.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")
def test_checker_rejects_es6(tmp_path):
    res = _check(tmp_path, "let x = () => 1;")
    if "acorn not installed" in res.stderr:
        pytest.skip("acorn is not installed")
    assert res.returncode != 0


def test_every_tool_defines_entry():
    for tool in available_tools():
        assert "function dazmcpTool(args)" in (ROOT / "scripts" / "tools" / f"{tool}.dsa").read_text()
