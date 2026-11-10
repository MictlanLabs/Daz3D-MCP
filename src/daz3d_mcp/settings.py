"""User settings stored in ~/.daz3d-mcp/settings.json."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from daz3d_mcp.paths import config_dir

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


@dataclass
class Settings:
    # Allow the free-form run_script tool. Turn off to only allow the named tools.
    allow_run_script: bool = True
    # "auto" (plugin, else no-plugin mode), "http" (plugin only) or "file" (no-plugin mode).
    transport: str = "auto"
    # Full path of the Daz Studio executable, used by the no-plugin mode.
    daz_executable: str | None = None
    # Seconds to wait for Daz Studio to answer one request.
    timeout: float = 600.0
    # How many viewport captures to keep in ~/.daz3d-mcp/captures.
    keep_captures: int = 20
    # Seconds to wait for one render (renders can be much longer than other calls).
    render_timeout: float = 3600.0
    # Folder for renders when the agent gives no path (default ~/.daz3d-mcp/renders).
    render_dir: str | None = None
    # Content libraries to search when Daz Studio cannot list them.
    content_libraries: list = field(default_factory=list)
    # Hours before the content library index is rebuilt.
    content_index_max_age_hours: float = 24.0
    # Content library that package_install uses when the agent names none
    # (default ~/Documents/DAZ 3D/Third Party Library).
    install_library: str | None = None
    # Largest package (unpacked) that package_install accepts, in GB.
    max_package_gb: float = 20.0
    extra: dict = field(default_factory=dict)

    @property
    def path(self) -> Path:
        return config_dir() / "settings.json"

    def save(self) -> Path:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        extra = data.pop("extra", {})
        data.update(extra)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return path


def load_settings() -> Settings:
    settings = Settings()
    path = config_dir() / "settings.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            data = {}
        known = set(Settings.__dataclass_fields__) - {"extra"}
        for key, value in data.items():
            if key in known:
                setattr(settings, key, value)
            else:
                settings.extra[key] = value

    env = os.environ.get("DAZ3D_MCP_ALLOW_SCRIPTS", "").strip().lower()
    if env in _TRUE:
        settings.allow_run_script = True
    elif env in _FALSE:
        settings.allow_run_script = False
    if os.environ.get("DAZ3D_MCP_TRANSPORT"):
        settings.transport = os.environ["DAZ3D_MCP_TRANSPORT"].strip().lower()
    if os.environ.get("DAZ3D_MCP_DAZ_EXECUTABLE"):
        settings.daz_executable = os.environ["DAZ3D_MCP_DAZ_EXECUTABLE"]
    if os.environ.get("DAZ3D_MCP_RENDER_TIMEOUT"):
        settings.render_timeout = float(os.environ["DAZ3D_MCP_RENDER_TIMEOUT"])
    if os.environ.get("DAZ3D_MCP_TIMEOUT"):
        settings.timeout = float(os.environ["DAZ3D_MCP_TIMEOUT"])
    return settings
