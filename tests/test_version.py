"""The package version is written once, in pyproject.toml."""

import re
from pathlib import Path

import daz3d_mcp

ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version\s*=\s*"([^"]+)"', text, re.M).group(1)


def test_version_comes_from_pyproject():
    assert daz3d_mcp.__version__ == _pyproject_version()


def test_changelogs_have_current_version():
    for name in ("CHANGELOG.md", "CHANGELOG.es.md"):
        changelog = (ROOT / name).read_text(encoding="utf-8")
        assert f"## [{_pyproject_version()}]" in changelog, name
