"""Command line: `daz3d-mcp` (serve), setup, install, uninstall, doctor."""

from __future__ import annotations

import argparse
import shutil
import sys
import urllib.request
from pathlib import Path

from daz3d_mcp import PROTOCOL_VERSION, __version__
from daz3d_mcp.daz_locate import DazInstall, find_daz_installs, plugin_filename
from daz3d_mcp.paths import config_dir

RELEASES = "https://github.com/MictlanLabs/Daz3D-MCP/releases/download"


def _print(msg: str = "") -> None:
    print(msg, file=sys.stderr if _SERVING else sys.stdout)


_SERVING = False


# ------------------------------------------------------------------ setup --
def _release_asset_name(install: DazInstall) -> str:
    arch = "arm64" if _is_arm() else "x64"
    osname = "macos" if sys.platform == "darwin" else "windows"
    ext = "dylib" if sys.platform == "darwin" else "dll"
    return f"dazmcp_bridge-ds{install.major}-{osname}-{arch}.{ext}"


def _is_arm() -> bool:
    import platform

    return platform.machine().lower() in {"arm64", "aarch64"}


def cmd_setup(args: argparse.Namespace) -> int:
    from daz3d_mcp.settings import load_settings

    cfg = config_dir()
    cfg.mkdir(parents=True, exist_ok=True)
    settings = load_settings()
    if not settings.path.is_file():
        settings.save()
        _print(f"Created {settings.path}")

    installs = find_daz_installs()
    if args.plugins_dir:
        target_dir = Path(args.plugins_dir).expanduser()
        install = installs[0] if installs else None
    else:
        if not installs:
            _print("Daz Studio was not found. Install Daz Studio 6 (or 4.24) first, or pass --plugins-dir.")
            return 1
        install = installs[0]
        if len(installs) > 1:
            _print("Found several Daz Studio installs; using the newest:")
            for i in installs:
                _print(f"  - {i.label}")
        target_dir = install.plugins_dir
    _print(f"Daz Studio: {install.label if install else 'unknown'}")
    if install and install.executable and not settings.daz_executable:
        settings.daz_executable = str(install.executable)
        settings.save()

    if args.no_plugin:
        _print("Skipping the plugin: the MCP will use no-plugin mode (experimental).")
        return 0

    target = target_dir / plugin_filename()
    if args.plugin_file:
        source = Path(args.plugin_file).expanduser()
        if not source.is_file():
            _print(f"Plugin file not found: {source}")
            return 1
    else:
        if install is None:
            _print("Pass --plugin-file with a compiled bridge when Daz Studio is not detected.")
            return 1
        asset = _release_asset_name(install)
        url = f"{RELEASES}/v{__version__}/{asset}"
        source = cfg / "downloads" / asset
        source.parent.mkdir(parents=True, exist_ok=True)
        _print(f"Downloading {url}")
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 (fixed https URL)
                source.write_bytes(resp.read())
        except Exception as exc:  # noqa: BLE001
            _print(f"Could not download the prebuilt bridge ({exc}).")
            _print("Build it yourself (see bridge/README.md) and run: daz3d-mcp setup --plugin-file <file>")
            _print("Or use no-plugin mode for now: daz3d-mcp setup --no-plugin")
            return 1

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    except PermissionError:
        _print(f"No permission to write {target}.")
        if sys.platform == "darwin":
            _print(f'Run: sudo cp "{source}" "{target}"')
        else:
            _print("Run the command again from a terminal opened as Administrator.")
        return 1
    _print(f"Installed the bridge plugin: {target}")
    _print("Restart Daz Studio, then run: daz3d-mcp doctor")
    return 0


# ---------------------------------------------------------------- install --
def _select_clients(args: argparse.Namespace):
    from daz3d_mcp.installer import all_clients, get_client

    if args.client:
        return [get_client(c) for c in args.client]
    clients = all_clients()
    if args.all:
        return [c for c in clients if c.detect()]
    return []


def cmd_install(args: argparse.Namespace) -> int:
    from daz3d_mcp.installer import ConfigError, install_skills, manual_snippet, plan_skill_dirs, server_command

    try:
        clients = _select_clients(args)
    except KeyError as exc:
        _print(str(exc.args[0]))
        return 2
    if not clients:
        if args.all:
            _print("No supported agent was detected. Add this to your agent's MCP settings:")
        else:
            _print("Choose agents with --all or --client NAME. Manual configuration:")
        _print(manual_snippet())
        return 1 if args.all else 2

    command, cmd_args = server_command()
    _print(f"MCP command: {command} {' '.join(cmd_args)}")
    failures = 0
    for c in clients:
        try:
            _print(f"- {c.name}: {c.configure(command, cmd_args)}")
        except (ConfigError, OSError) as exc:
            failures += 1
            _print(f"- {c.name}: FAILED ({exc})")

    if not args.no_skills:
        for folder in plan_skill_dirs(clients):
            names = install_skills(folder)
            _print(f"- skills {', '.join(names) or '(none new)'} -> {folder}")
        without = [c.name for c in clients if not c.skill_dirs]
        if without:
            _print(f"- {', '.join(without)}: no skills folder; guides come through the MCP (daz_guide).")
    _print("Restart the agents so they load the new MCP server.")
    return 1 if failures else 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    from daz3d_mcp.installer import all_clients, get_client, remove_skills

    clients = [get_client(c) for c in args.client] if args.client else all_clients()
    for c in clients:
        try:
            if c.is_configured() or args.client:
                _print(f"- {c.name}: {c.unconfigure()}")
        except Exception as exc:  # noqa: BLE001
            _print(f"- {c.name}: FAILED ({exc})")
        for folder in c.skill_dirs:
            removed = remove_skills(folder)
            if removed:
                _print(f"- removed skills {', '.join(removed)} from {folder}")
    return 0


# ----------------------------------------------------------------- doctor --
def cmd_doctor(args: argparse.Namespace) -> int:
    from daz3d_mcp.client import DazClient
    from daz3d_mcp.installer import all_clients, server_command
    from daz3d_mcp.settings import load_settings
    from daz3d_mcp.transport import DazError, read_bridge_info

    problems = 0

    def ok(msg: str) -> None:
        _print(f"[ok]   {msg}")

    def bad(msg: str, fix: str) -> None:
        nonlocal problems
        problems += 1
        _print(f"[fail] {msg}\n       -> {fix}")

    def info(msg: str) -> None:
        _print(f"[info] {msg}")

    info(f"daz3d-mcp {__version__} (protocol {PROTOCOL_VERSION}), Python {sys.version.split()[0]}")
    settings = load_settings()
    info(f"settings: transport={settings.transport}, run_script={'on' if settings.allow_run_script else 'off'}")

    installs = find_daz_installs()
    if installs:
        for i in installs:
            plugin = i.plugins_dir / plugin_filename()
            ok(f"{i.label}; bridge plugin {'installed' if plugin.is_file() else 'NOT installed'}")
    else:
        bad("Daz Studio not found in the default location", "Install Daz Studio, or ignore if it lives elsewhere.")

    bridge = read_bridge_info()
    if bridge:
        ok(f"bridge.json found (port {bridge.port}, bridge {bridge.bridge_version}, Daz {bridge.daz_version})")
    elif settings.transport == "http":
        bad("bridge.json not found", "Open Daz Studio with the bridge plugin installed (daz3d-mcp setup).")
    else:
        info("bridge plugin not running; the MCP will try no-plugin mode")

    client = DazClient(settings)
    try:
        st = client.bridge_status()
        ok(f"transport answers: {st}")
        result = client.run_tool("status", timeout=30)
        ok(f"Daz Studio answers: version {result.get('version')}, scene {result.get('scene', {}).get('filename')}")
    except DazError as exc:
        bad(f"cannot talk to Daz Studio: {exc.message}", exc.hint or "Open Daz Studio and retry.")

    command, cmd_args = server_command()
    info(f"agents run: {command} {' '.join(cmd_args)}")
    if shutil.which(command) is None:
        bad(f"`{command}` is not on PATH", "Install uv: https://docs.astral.sh/uv/getting-started/installation/")
    for c in all_clients():
        if not c.detect():
            continue
        if c.is_configured():
            ok(f"{c.name}: MCP registered")
        else:
            bad(f"{c.name}: MCP not registered", f"daz3d-mcp install --client {c.id}")
    _print("")
    _print("All good." if not problems else f"{problems} problem(s) found.")
    return 1 if problems else 0


# ------------------------------------------------------------------ serve --
def cmd_serve(args: argparse.Namespace) -> int:
    global _SERVING
    _SERVING = True
    from daz3d_mcp.server import run

    run()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="daz3d-mcp", description="MCP server and installer for Daz Studio agents.")
    p.add_argument("--version", action="version", version=f"daz3d-mcp {__version__}")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("serve", help="Run the MCP server on stdio (default when no command is given).")

    s = sub.add_parser("setup", help="Install the bridge plugin into Daz Studio.")
    s.add_argument("--plugin-file", help="Use this compiled bridge (.dylib/.dll) instead of downloading it.")
    s.add_argument("--plugins-dir", help="Daz Studio plugins folder, if it is not detected.")
    s.add_argument("--no-plugin", action="store_true", help="Skip the plugin and use no-plugin mode.")

    i = sub.add_parser("install", help="Register the MCP server and skills in your AI agents.")
    i.add_argument("--all", action="store_true", help="Every supported agent found on this computer.")
    i.add_argument("--client", action="append", metavar="NAME",
                   help="claude-code, codex, cursor, antigravity, gemini-cli, claude-desktop, windsurf, vscode")
    i.add_argument("--no-skills", action="store_true", help="Only register the MCP server.")

    u = sub.add_parser("uninstall", help="Remove the MCP server and skills from agents.")
    u.add_argument("--client", action="append", metavar="NAME")

    sub.add_parser("doctor", help="Check Daz Studio, the bridge and the agents.")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    handlers = {
        None: cmd_serve,
        "serve": cmd_serve,
        "setup": cmd_setup,
        "install": cmd_install,
        "uninstall": cmd_uninstall,
        "doctor": cmd_doctor,
    }
    sys.exit(handlers[args.command](args))
