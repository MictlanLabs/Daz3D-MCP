"""`daz3d-mcp setup`: copying the bridge plugin into Daz Studio on Windows."""

import sys

import pytest

import daz3d_mcp.cli as cli

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows setup paths")


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    monkeypatch.setenv("DAZ3D_MCP_HOME", str(tmp_path / "cfg"))
    monkeypatch.setattr(cli, "find_daz_installs", lambda: [])
    source = tmp_path / "bridge.dll"
    source.write_bytes(b"plugin")
    plugins = tmp_path / "plugins"
    return source, plugins


def _setup(source, plugins, *extra):
    with pytest.raises(SystemExit) as exc:
        cli.main(["setup", "--plugin-file", str(source), "--plugins-dir", str(plugins), *extra])
    return exc.value.code


def _deny_copy(monkeypatch):
    def deny(*_a, **_k):
        raise PermissionError("protected")

    monkeypatch.setattr(cli.shutil, "copy2", deny)


def test_protected_folder_asks_for_admin_rights(plugin, monkeypatch):
    source, plugins = plugin
    _deny_copy(monkeypatch)
    calls = []
    monkeypatch.setattr(cli, "_copy_elevated", lambda s, t: calls.append((s, t)) or True)
    assert _setup(source, plugins) == 0
    assert calls == [(source, plugins / "dsp_dazmcp_bridge.dll")]


def test_refused_admin_rights_fail(plugin, monkeypatch):
    source, plugins = plugin
    _deny_copy(monkeypatch)
    monkeypatch.setattr(cli, "_copy_elevated", lambda s, t: False)
    assert _setup(source, plugins) == 1


def test_no_elevate_does_not_ask(plugin, monkeypatch):
    source, plugins = plugin
    _deny_copy(monkeypatch)
    monkeypatch.setattr(cli, "_copy_elevated", lambda s, t: pytest.fail("asked for admin rights"))
    assert _setup(source, plugins, "--no-elevate") == 1


def test_open_daz_with_plugin_installed_stops(plugin, monkeypatch):
    source, plugins = plugin
    plugins.mkdir()
    (plugins / "dsp_dazmcp_bridge.dll").write_bytes(b"old")
    monkeypatch.setattr(cli, "_daz_running", lambda: True)
    assert _setup(source, plugins) == 1
    assert (plugins / "dsp_dazmcp_bridge.dll").read_bytes() == b"old"


@pytest.mark.parametrize("existing", [True, False])
def test_elevated_copy_command_copies(tmp_path, existing):
    # "open" runs the same cmd line as "runas" without the UAC prompt.
    source = tmp_path / "bridge.dll"
    source.write_bytes(b"plugin")
    folder = tmp_path / "plugins dir"
    if existing:
        folder.mkdir()
    assert cli._copy_elevated(source, folder / "dsp_dazmcp_bridge.dll", verb="open")
