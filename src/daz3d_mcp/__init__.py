"""Daz3D-MCP: let AI agents control Daz Studio."""

from importlib.metadata import PackageNotFoundError, version as _dist_version


def _read_version() -> str:
    # The version lives only in pyproject.toml (bump it with `uv version --bump minor`).
    # Installed copies read it from the package metadata.
    try:
        return _dist_version("daz3d-mcp")
    except PackageNotFoundError:
        pass
    # Running from a source checkout that was never installed: read pyproject.toml.
    import re
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"), re.M)
    except OSError:
        match = None
    return match.group(1) if match else "0+unknown"


__version__ = _read_version()

# Version of the HTTP protocol spoken with the bridge plugin.
PROTOCOL_VERSION = 1
