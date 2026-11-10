"""Where Daz3D-MCP keeps its files."""

from __future__ import annotations

import os
from importlib import resources
from pathlib import Path


def config_dir() -> Path:
    """Folder shared with the bridge plugin (token, bridge.json, settings)."""
    override = os.environ.get("DAZ3D_MCP_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".daz3d-mcp"


def _repo_root() -> Path:
    # src/daz3d_mcp/paths.py -> repo root
    return Path(__file__).resolve().parents[2]


def data_dir(kind: str) -> Path:
    """Folder with packaged data: "scripts" (DazScript) or "skills".

    In a built wheel the data lives in daz3d_mcp/_data; when running from a
    checkout it is read straight from the top of the repository.
    """
    root = _repo_root()
    local = root / kind
    # A checkout (also an editable install, which keeps a stale copy in
    # _data) reads the repository's own files, so edits apply at once.
    if (root / "pyproject.toml").is_file() and local.is_dir():
        return local
    packaged = Path(str(resources.files("daz3d_mcp"))) / "_data" / kind
    if packaged.is_dir():
        return packaged
    if local.is_dir():
        return local
    raise FileNotFoundError(f"Daz3D-MCP data folder '{kind}' is missing from the installation.")


def scripts_dir() -> Path:
    return data_dir("scripts")


def skills_dir() -> Path:
    return data_dir("skills")


def animations_dir() -> Path:
    """Built-in animation presets (.json clips)."""
    return data_dir("animations")
