"""Finds Daz Studio installations and their plugin folders."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DazInstall:
    root: Path          # install folder, e.g. /Applications/DAZ 3D/DAZStudio6 64-bit
    executable: Path    # binary to launch
    plugins_dir: Path   # where plugin .dll/.dylib files go
    major: int          # 4 or 6 (best guess from the folder name)

    @property
    def label(self) -> str:
        return f"Daz Studio {self.major} ({self.root})"


def _major_from(name: str) -> int:
    m = re.search(r"(?:studio|DAZStudio)\s*(\d)", name, re.IGNORECASE)
    return int(m.group(1)) if m else 4


def _mac_installs(base: Path) -> list[DazInstall]:
    found: list[DazInstall] = []
    if not base.is_dir():
        return found
    for root in sorted(base.iterdir()):
        if not root.is_dir():
            continue
        for app in sorted(root.glob("*.app")):
            if "studio" not in app.name.lower():
                continue
            exe_dir = app / "Contents" / "MacOS"
            exes = [p for p in exe_dir.glob("*") if p.is_file() and os.access(p, os.X_OK)] if exe_dir.is_dir() else []
            if not exes:
                continue
            exe = next((p for p in exes if "studio" in p.name.lower()), exes[0])
            candidates = [root / "plugins", app / "Contents" / "PlugIns", app / "Contents" / "plugins"]
            plugins = next((c for c in candidates if c.is_dir()), candidates[0])
            found.append(DazInstall(root, exe, plugins, _major_from(root.name + " " + app.name)))
    return found


def _windows_installs() -> list[DazInstall]:
    found: list[DazInstall] = []
    bases = {os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramW6432", r"C:\Program Files")}
    for base in bases:
        daz = Path(base) / "DAZ 3D"
        if not daz.is_dir():
            continue
        for root in sorted(daz.iterdir()):
            exe = root / "DAZStudio.exe"
            if exe.is_file():
                found.append(DazInstall(root, exe, root / "plugins", _major_from(root.name)))
    return found


def find_daz_installs() -> list[DazInstall]:
    """All installs found, newest major version first."""
    override = os.environ.get("DAZ3D_MCP_DAZ_ROOT")
    if sys.platform == "darwin":
        installs = _mac_installs(Path(override) if override else Path("/Applications/DAZ 3D"))
    elif sys.platform == "win32":
        installs = _windows_installs()
    else:
        installs = _mac_installs(Path(override)) if override else []
    return sorted(installs, key=lambda i: -i.major)


def plugin_filename() -> str:
    return "dazmcp_bridge.dll" if sys.platform == "win32" else "dazmcp_bridge.dylib"
