"""How the MCP server reaches Daz Studio.

HttpTransport   talks to the bridge plugin over 127.0.0.1 with a token.
FileTransport   no-plugin mode: writes a .dsa file and asks the running Daz
                Studio to execute it, then waits for the answer file. Slower,
                experimental, but needs nothing compiled.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

from daz3d_mcp import PROTOCOL_VERSION
from daz3d_mcp.paths import config_dir
from daz3d_mcp.scriptlib import ENTRY_FUNCTION


class DazError(Exception):
    """An error with a short code and a hint the agent can act on."""

    def __init__(self, code: str, message: str, hint: str | None = None, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.details = details

    def __str__(self) -> str:
        text = f"[{self.code}] {self.message}"
        if self.hint:
            text += f"\nHint: {self.hint}"
        return text


NOT_RUNNING_HINT = (
    "Open Daz Studio (with the Daz3D-MCP bridge plugin installed) and try again. "
    "Run `uvx daz3d-mcp doctor` to diagnose."
)


@dataclass
class BridgeInfo:
    port: int
    token: str
    bridge_version: str | None = None
    daz_version: str | None = None
    protocol: int | None = None
    pid: int | None = None


def read_bridge_info() -> BridgeInfo | None:
    """Reads ~/.daz3d-mcp/bridge.json and token, written by the plugin."""
    base = config_dir()
    info_path = base / "bridge.json"
    token_path = base / "token"
    if not info_path.is_file() or not token_path.is_file():
        return None
    try:
        data = json.loads(info_path.read_text(encoding="utf-8"))
        token = token_path.read_text(encoding="utf-8").strip()
    except (OSError, json.JSONDecodeError):
        return None
    if not token or "port" not in data:
        return None
    return BridgeInfo(
        port=int(data["port"]),
        token=token,
        bridge_version=data.get("bridge_version"),
        daz_version=data.get("daz_version"),
        protocol=data.get("protocol"),
        pid=data.get("pid"),
    )


def _decode_response(raw: bytes) -> dict:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DazError("bad_response", f"Daz Studio returned something that is not JSON: {raw[:200]!r}") from exc
    if not isinstance(data, dict):
        raise DazError("bad_response", "Daz Studio returned an unexpected value.")
    return data


class Transport:
    name = "base"

    def execute(self, code: str, args: dict, timeout: float) -> dict:
        raise NotImplementedError

    def status(self) -> dict:
        raise NotImplementedError


class HttpTransport(Transport):
    name = "http"

    def __init__(self, info: BridgeInfo | None = None):
        self._info = info

    def _bridge(self) -> BridgeInfo:
        info = self._info or read_bridge_info()
        if info is None:
            raise DazError(
                "bridge_not_found",
                "The Daz3D-MCP bridge is not running (no ~/.daz3d-mcp/bridge.json).",
                NOT_RUNNING_HINT,
            )
        return info

    def _request(self, path: str, payload: dict | None, timeout: float) -> dict:
        info = self._bridge()
        url = f"http://127.0.0.1:{info.port}{path}"
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST" if body is not None else "GET")
        req.add_header("Authorization", f"Bearer {info.token}")
        req.add_header("Content-Type", "application/json")
        # Do not let a system proxy capture traffic meant for localhost.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=timeout) as resp:
                return _decode_response(resp.read())
        except urllib.error.HTTPError as exc:
            data = {}
            try:
                data = _decode_response(exc.read())
            except DazError:
                pass
            err = data.get("error") or {}
            if exc.code == 401:
                raise DazError("unauthorized", "The bridge rejected the token.",
                               "Restart Daz Studio so the plugin and the MCP share the same token.") from exc
            if exc.code == 409:
                raise DazError("busy", "Daz Studio is still busy with the previous request.",
                               "Wait for it to finish and try again.") from exc
            raise DazError(err.get("code", f"http_{exc.code}"), err.get("message", str(exc))) from exc
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, TimeoutError) or "timed out" in str(reason):
                raise DazError("timeout", f"Daz Studio did not answer within {timeout:.0f} s.",
                               "Long loads can take minutes; check Daz Studio for an open dialog.") from exc
            raise DazError("bridge_unreachable", f"Could not reach the bridge on port {info.port}: {reason}",
                           NOT_RUNNING_HINT) from exc

    def status(self) -> dict:
        data = self._request("/v1/status", None, timeout=5)
        proto = data.get("protocol")
        if proto is not None and proto != PROTOCOL_VERSION:
            data["warning"] = (
                f"Bridge protocol {proto} differs from MCP protocol {PROTOCOL_VERSION}; "
                "update the plugin with `uvx daz3d-mcp setup`."
            )
        return data

    def execute(self, code: str, args: dict, timeout: float) -> dict:
        payload = {"code": code, "entry": ENTRY_FUNCTION, "args": json.dumps(args)}
        return self._request("/v1/execute", payload, timeout=timeout)


class FileTransport(Transport):
    """No-plugin mode. Daz Studio forwards a script given on its command line
    to the instance that is already running, so each request launches the Daz
    executable with a generated .dsa file and waits for the answer file."""

    name = "file"

    def __init__(self, daz_executable: str | None):
        self.daz_executable = daz_executable

    def _queue(self) -> Path:
        path = config_dir() / "queue"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _executable(self) -> str:
        exe = self.daz_executable
        if not exe:
            from daz3d_mcp.daz_locate import find_daz_installs

            installs = find_daz_installs()
            if installs:
                exe = str(installs[0].executable)
        if not exe or not Path(exe).exists():
            raise DazError(
                "daz_not_found",
                "No-plugin mode needs the Daz Studio executable and none was found.",
                "Set daz_executable in ~/.daz3d-mcp/settings.json or the DAZ3D_MCP_DAZ_EXECUTABLE variable.",
            )
        return exe

    def status(self) -> dict:
        return {"ok": True, "transport": "file", "executable": self._executable()}

    def execute(self, code: str, args: dict, timeout: float) -> dict:
        exe = self._executable()
        queue = self._queue()
        req_id = uuid.uuid4().hex
        script_path = queue / f"{req_id}.dsa"
        out_path = queue / f"{req_id}.json"
        tmp_path = queue / f"{req_id}.json.tmp"
        epilogue = (
            "\n(function () {\n"
            f"  var out = {ENTRY_FUNCTION}({json.dumps(json.dumps(args))});\n"
            f"  var f = new DzFile({json.dumps(tmp_path.as_posix())});\n"
            "  f.open(DzFile.WriteOnly);\n"
            "  f.write(out);\n"
            "  f.close();\n"
            f"  f.rename({json.dumps(out_path.as_posix())});\n"
            "})();\n"
        )
        script_path.write_text(code + epilogue, encoding="utf-8")
        try:
            kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
            if sys.platform == "win32":
                kwargs["creationflags"] = 0x00000008  # DETACHED_PROCESS
            else:
                kwargs["start_new_session"] = True
            subprocess.Popen([exe, str(script_path)], **kwargs)  # noqa: S603
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if out_path.is_file():
                    raw = out_path.read_bytes()
                    return _decode_response(raw)
                time.sleep(0.2)
            raise DazError("timeout", f"Daz Studio did not answer within {timeout:.0f} s (no-plugin mode).",
                           "Make sure Daz Studio is open; the first request can also open a new window.")
        finally:
            for p in (script_path, out_path, tmp_path):
                try:
                    p.unlink()
                except OSError:
                    pass


def make_transport(mode: str = "auto", daz_executable: str | None = None) -> Transport:
    mode = (mode or "auto").lower()
    if mode == "http":
        return HttpTransport()
    if mode == "file":
        return FileTransport(daz_executable)
    if mode != "auto":
        raise DazError("bad_settings", f"Unknown transport {mode!r}; use auto, http or file.")
    return AutoTransport(daz_executable)


class AutoTransport(Transport):
    """Uses the plugin when its bridge.json exists, otherwise no-plugin mode."""

    name = "auto"

    def __init__(self, daz_executable: str | None):
        self._file = FileTransport(daz_executable)

    def _pick(self) -> Transport:
        info = read_bridge_info()
        if info is not None:
            return HttpTransport(info)
        if os.environ.get("DAZ3D_MCP_NO_FILE_FALLBACK"):
            return HttpTransport()
        return self._file

    def status(self) -> dict:
        t = self._pick()
        data = t.status()
        data.setdefault("transport", t.name)
        return data

    def execute(self, code: str, args: dict, timeout: float) -> dict:
        return self._pick().execute(code, args, timeout)
