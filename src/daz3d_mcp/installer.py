"""Registers the MCP server and copies the skills into each AI agent."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Callable

from daz3d_mcp.skills import list_skills

SERVER_NAME = "daz3d"
MARKER = ".daz3d-mcp"  # file placed in every skill folder we install


# ----------------------------------------------------------- server spec ---
def server_command() -> tuple[str, list[str]]:
    """The command each agent runs to start this server.

    When the package was installed from git or a local folder (for example with
    `uvx --from git+https://... daz3d-mcp install`), the agents get the same
    source so they run exactly this version.
    """
    source = None
    try:
        raw = metadata.distribution("daz3d-mcp").read_text("direct_url.json")
        if raw:
            info = json.loads(raw)
            url = info.get("url", "")
            vcs = info.get("vcs_info")
            if vcs:
                ref = vcs.get("requested_revision")
                source = f"{vcs.get('vcs', 'git')}+{url}" + (f"@{ref}" if ref else "")
            elif url.startswith("file://"):
                source = url
    except (metadata.PackageNotFoundError, json.JSONDecodeError, OSError):
        pass
    if os.environ.get("DAZ3D_MCP_SOURCE"):
        source = os.environ["DAZ3D_MCP_SOURCE"]
    if source:
        return "uvx", ["--from", source, "daz3d-mcp"]
    return "uvx", ["daz3d-mcp"]


# ------------------------------------------------------------ json utils ---
class ConfigError(Exception):
    pass


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not plain JSON (comments?); add the entry by hand.") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} does not contain a JSON object.")
    return data


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name(path.name + ".daz3d-mcp.bak")
    if path.is_file() and not backup.exists():
        shutil.copy2(path, backup)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _json_set(path: Path, key: str, entry: dict | None) -> bool:
    """Sets (or removes when entry is None) data[key][SERVER_NAME]. Returns True if changed."""
    data = _load_json(path)
    servers = data.setdefault(key, {})
    if entry is None:
        if SERVER_NAME not in servers:
            return False
        servers.pop(SERVER_NAME)
    else:
        if servers.get(SERVER_NAME) == entry:
            return False
        servers[SERVER_NAME] = entry
    _write_json(path, data)
    return True


# ------------------------------------------------------------ toml utils ---
_TOML_HEADER = re.compile(r"^\s*\[mcp_servers\.(?:\"daz3d\"|daz3d)\]\s*$")
_ANY_HEADER = re.compile(r"^\s*\[")


def _toml_set(path: Path, command: str | None, args: list[str] | None) -> bool:
    """Adds, replaces or removes the [mcp_servers.daz3d] table in a TOML file."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    out: list[str] = []
    skipping = False
    for line in lines:
        if _TOML_HEADER.match(line):
            skipping = True
            continue
        if skipping and _ANY_HEADER.match(line) and not line.strip().startswith("[mcp_servers.daz3d."):
            skipping = False
        if not skipping:
            out.append(line)
    if command is not None:
        while out and not out[-1].strip():
            out.pop()
        if out:
            out.append("")
        out.append(f"[mcp_servers.{SERVER_NAME}]")
        out.append(f"command = {json.dumps(command)}")
        out.append("args = [" + ", ".join(json.dumps(a) for a in (args or [])) + "]")
        out.append("startup_timeout_sec = 60")
        out.append("tool_timeout_sec = 600")
    new_text = "\n".join(out) + "\n" if out else ""
    old_text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if new_text == old_text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name(path.name + ".daz3d-mcp.bak")
    if path.is_file() and not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(new_text, encoding="utf-8")
    return True


# --------------------------------------------------------------- clients ---
def _home() -> Path:
    return Path.home()


def _app_support() -> Path:
    if sys.platform == "darwin":
        return _home() / "Library" / "Application Support"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", _home() / "AppData" / "Roaming"))
    return Path(os.environ.get("XDG_CONFIG_HOME", _home() / ".config"))


@dataclass
class Client:
    id: str
    name: str
    detect: Callable[[], bool]
    configure: Callable[[str, list[str]], str]      # returns a short description of what was done
    unconfigure: Callable[[], str]
    is_configured: Callable[[], bool]
    # Skill folders the agent reads, best first. Empty: the agent has no skills,
    # it gets the same guides through MCP prompts and the daz_guide tool.
    skill_dirs: list[Path] = field(default_factory=list)
    config_path: Path | None = None


def _json_client(cid: str, name: str, path: Path, key: str, detect_paths: list[Path],
                 skill_dirs: list[Path] | None = None, entry_extra: dict | None = None) -> Client:
    def entry(command: str, args: list[str]) -> dict:
        e = dict(entry_extra or {})
        e.update({"command": command, "args": args})
        return e

    def configure(command: str, args: list[str]) -> str:
        changed = _json_set(path, key, entry(command, args))
        return f"{'updated' if changed else 'already set'}: {path}"

    def unconfigure() -> str:
        changed = _json_set(path, key, None) if path.is_file() else False
        return f"{'removed from' if changed else 'not in'} {path}"

    def is_configured() -> bool:
        try:
            return SERVER_NAME in _load_json(path).get(key, {})
        except ConfigError:
            return False

    return Client(cid, name, lambda: any(p.exists() for p in detect_paths), configure, unconfigure,
                  is_configured, skill_dirs or [], path)


def _claude_code() -> Client:
    path = _home() / ".claude.json"

    def has_cli() -> bool:
        return shutil.which("claude") is not None

    def configure(command: str, args: list[str]) -> str:
        if has_cli():
            subprocess.run(["claude", "mcp", "remove", "--scope", "user", SERVER_NAME],
                           capture_output=True, text=True, check=False)
            res = subprocess.run(["claude", "mcp", "add", "--scope", "user", SERVER_NAME, "--", command, *args],
                                 capture_output=True, text=True, check=False)
            if res.returncode == 0:
                return "registered with `claude mcp add --scope user`"
        changed = _json_set(path, "mcpServers", {"type": "stdio", "command": command, "args": args, "env": {}})
        return f"{'updated' if changed else 'already set'}: {path}"

    def unconfigure() -> str:
        if has_cli():
            subprocess.run(["claude", "mcp", "remove", "--scope", "user", SERVER_NAME],
                           capture_output=True, text=True, check=False)
        if path.is_file():
            _json_set(path, "mcpServers", None)
        return "removed"

    def is_configured() -> bool:
        try:
            return SERVER_NAME in _load_json(path).get("mcpServers", {})
        except ConfigError:
            return False

    return Client("claude-code", "Claude Code",
                  lambda: has_cli() or (_home() / ".claude").is_dir(),
                  configure, unconfigure, is_configured,
                  [_home() / ".claude" / "skills"], path)


def all_clients() -> list[Client]:
    home = _home()
    support = _app_support()
    vscode_user = support / "Code" / "User"
    gemini = home / ".gemini"
    codex_home = Path(os.environ.get("CODEX_HOME", home / ".codex"))
    codex_cfg = codex_home / "config.toml"

    def codex_configure(command: str, args: list[str]) -> str:
        changed = _toml_set(codex_cfg, command, args)
        return f"{'updated' if changed else 'already set'}: {codex_cfg}"

    def codex_unconfigure() -> str:
        changed = _toml_set(codex_cfg, None, None) if codex_cfg.is_file() else False
        return f"{'removed from' if changed else 'not in'} {codex_cfg}"

    def codex_is_configured() -> bool:
        if not codex_cfg.is_file():
            return False
        return any(_TOML_HEADER.match(l) for l in codex_cfg.read_text(encoding="utf-8").splitlines())

    codex = Client("codex", "Codex",
                   lambda: codex_home.is_dir() or shutil.which("codex") is not None,
                   codex_configure, codex_unconfigure, codex_is_configured,
                   [home / ".agents" / "skills", codex_home / "skills"], codex_cfg)

    claude_desktop_cfg = support / "Claude" / "claude_desktop_config.json"

    return [
        _claude_code(),
        codex,
        _json_client("cursor", "Cursor", home / ".cursor" / "mcp.json", "mcpServers",
                     [home / ".cursor"],
                     # Cursor also reads ~/.claude/skills and ~/.agents/skills.
                     [home / ".cursor" / "skills", home / ".claude" / "skills", home / ".agents" / "skills"]),
        _json_client("antigravity", "Antigravity", gemini / "antigravity" / "mcp_config.json", "mcpServers",
                     [gemini / "antigravity"],
                     [gemini / "antigravity" / "skills", gemini / "skills"]),
        _json_client("gemini-cli", "Gemini CLI", gemini / "settings.json", "mcpServers",
                     [gemini / "settings.json"],
                     [gemini / "skills", home / ".agents" / "skills"]),
        _json_client("claude-desktop", "Claude Desktop", claude_desktop_cfg, "mcpServers",
                     [claude_desktop_cfg.parent]),
        _json_client("windsurf", "Windsurf", home / ".codeium" / "windsurf" / "mcp_config.json", "mcpServers",
                     [home / ".codeium" / "windsurf"]),
        _json_client("vscode", "VS Code (Copilot)", vscode_user / "mcp.json", "servers",
                     [vscode_user], entry_extra={"type": "stdio"}),
    ]


def get_client(client_id: str) -> Client:
    for c in all_clients():
        if c.id == client_id:
            return c
    ids = ", ".join(c.id for c in all_clients())
    raise KeyError(f"Unknown client {client_id!r}. Known clients: {ids}")


# ---------------------------------------------------------------- skills ---
def plan_skill_dirs(clients: list[Client]) -> list[Path]:
    """Smallest set of folders so every client sees the skills exactly once."""
    chosen: list[Path] = []
    for c in clients:
        if not c.skill_dirs:
            continue
        if any(d in chosen for d in c.skill_dirs):
            continue
        chosen.append(c.skill_dirs[0])
    return chosen


def install_skills(target: Path) -> list[str]:
    installed = []
    target.mkdir(parents=True, exist_ok=True)
    for skill in list_skills():
        dest = target / skill.path.name
        if dest.exists():
            if not (dest / MARKER).exists():
                # Someone else's skill with the same name: leave it alone.
                continue
            shutil.rmtree(dest)
        shutil.copytree(skill.path, dest)
        (dest / MARKER).write_text("Installed by daz3d-mcp; safe to delete.\n", encoding="utf-8")
        installed.append(skill.name)
    return installed


def remove_skills(target: Path) -> list[str]:
    removed = []
    for skill in list_skills():
        dest = target / skill.path.name
        if (dest / MARKER).exists():
            shutil.rmtree(dest)
            removed.append(skill.name)
    return removed


def manual_snippet() -> str:
    command, args = server_command()
    return json.dumps({"mcpServers": {SERVER_NAME: {"command": command, "args": args}}}, indent=2)
