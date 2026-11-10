"""The installer writes each agent's MCP config and copies the skills."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from daz3d_mcp import cli, installer


@pytest.fixture
def fake_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))  # no `claude` CLI: use the JSON fallback
    monkeypatch.setattr(installer, "server_command", lambda: ("uvx", ["daz3d-mcp"]))
    monkeypatch.setattr(cli, "_SERVING", False, raising=False)
    return home


def test_install_all_detected_agents(fake_home, capsys):
    (fake_home / ".claude").mkdir()
    (fake_home / ".cursor").mkdir()
    (fake_home / ".codex").mkdir()
    (fake_home / ".codex" / "config.toml").write_text('model = "gpt-5"\n\n[mcp_servers.other]\ncommand = "x"\n')
    (fake_home / ".cursor" / "mcp.json").write_text(json.dumps({"mcpServers": {"other": {"command": "y"}}}))

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["install", "--all"])
    assert exit_info.value.code == 0

    claude = json.loads((fake_home / ".claude.json").read_text())
    assert claude["mcpServers"]["daz3d"]["command"] == "uvx"

    cursor = json.loads((fake_home / ".cursor" / "mcp.json").read_text())
    assert cursor["mcpServers"]["daz3d"] == {"command": "uvx", "args": ["daz3d-mcp"]}
    assert "other" in cursor["mcpServers"]  # other servers untouched
    assert (fake_home / ".cursor" / "mcp.json.daz3d-mcp.bak").is_file()

    toml = (fake_home / ".codex" / "config.toml").read_text()
    assert '[mcp_servers.daz3d]\ncommand = "uvx"\nargs = ["daz3d-mcp"]' in toml
    assert "[mcp_servers.other]" in toml and 'model = "gpt-5"' in toml

    # Skills: Claude Code folder (Cursor reads it too) and the shared .agents folder for Codex.
    assert (fake_home / ".claude" / "skills" / "daz-basics" / "SKILL.md").is_file()
    assert (fake_home / ".agents" / "skills" / "daz-basics" / "SKILL.md").is_file()
    assert not (fake_home / ".cursor" / "skills").exists()  # no duplicate for Cursor

    # Running it again changes nothing and keeps a single codex table.
    with pytest.raises(SystemExit):
        cli.main(["install", "--all"])
    assert (fake_home / ".codex" / "config.toml").read_text().count("[mcp_servers.daz3d]") == 1


def test_install_single_client_and_uninstall(fake_home):
    with pytest.raises(SystemExit):
        cli.main(["install", "--client", "cursor"])
    assert (fake_home / ".cursor" / "skills" / "daz-basics" / ".daz3d-mcp").is_file()
    with pytest.raises(SystemExit):
        cli.main(["uninstall", "--client", "cursor"])
    cursor = json.loads((fake_home / ".cursor" / "mcp.json").read_text())
    assert "daz3d" not in cursor["mcpServers"]
    assert not (fake_home / ".cursor" / "skills" / "daz-basics").exists()


def test_does_not_overwrite_foreign_skill(fake_home):
    foreign = fake_home / ".cursor" / "skills" / "daz-basics"
    foreign.mkdir(parents=True)
    (foreign / "SKILL.md").write_text("mine")
    with pytest.raises(SystemExit):
        cli.main(["install", "--client", "cursor"])
    assert (foreign / "SKILL.md").read_text() == "mine"


def test_jsonc_config_is_left_alone(fake_home):
    vscode = installer.get_client("vscode").config_path
    vscode.parent.mkdir(parents=True)
    vscode.write_text('{ // comment\n "servers": {} }')
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["install", "--client", "vscode"])
    assert exit_info.value.code == 1
    assert "// comment" in vscode.read_text()


def test_unknown_client(fake_home):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["install", "--client", "notepad"])
    assert exit_info.value.code == 2


def test_server_command_from_git(monkeypatch):
    class Dist:
        def read_text(self, name):
            return json.dumps({"url": "https://github.com/MictlanLabs/Daz3D-MCP",
                               "vcs_info": {"vcs": "git", "commit_id": "abc", "requested_revision": "main"}})

    monkeypatch.setattr(installer.metadata, "distribution", lambda name: Dist())
    monkeypatch.delenv("DAZ3D_MCP_SOURCE", raising=False)
    assert installer.server_command() == (
        "uvx", ["--from", "git+https://github.com/MictlanLabs/Daz3D-MCP@main", "daz3d-mcp"])
