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
    if os.environ.get("DAZ3D_MCP_TIMEOUT"):
        settings.timeout = float(os.environ["DAZ3D_MCP_TIMEOUT"])
    return settings
