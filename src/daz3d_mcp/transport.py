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
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
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

    def execute(self, code: str, args: dict, timeout: float, dialogs: list[dict] | None = None) -> dict:
        raise NotImplementedError

    def status(self) -> dict:
        raise NotImplementedError

    def dialogs(self) -> dict:
        raise DazError("not_supported", "Seeing Daz Studio dialogs needs the bridge plugin (0.2 or later).",
                       "No-plugin mode cannot see dialogs; ask the user to click it.")

    def answer_dialog(self, button: str | None = None, dialog_id: str | None = None,
                      check: list[str] | None = None, uncheck: list[str] | None = None,
                      wait: float = 600.0) -> dict:
        return self.dialogs()

    def wait_pending(self, wait: float) -> dict | None:
        return None


# Modal dialogs. A Daz call that asks the user something (overwrite? replace?)
# stops the script until a button is pressed. Bridge 0.2+ lists open dialogs
# and presses buttons, and keeps answering HTTP while a dialog is open.
DIALOG_POLL = 0.5  # seconds between dialog checks while a request runs
DIALOG_GRACE = 1.0  # a dialog must stay open this long before it is reported
# The socket waits this much longer than the caller's timeout, so a request
# stuck on a dialog can still deliver its result once the dialog is answered.
SOCKET_SLACK = 3600.0


def describe_dialogs(dialogs: list[dict]) -> str:
    parts = []
    for d in dialogs:
        text = " ".join(str(d.get("text") or "").split())
        line = f'"{d.get("title") or "(no title)"}"'
        if text:
            line += f": {text[:400]}"
        if d.get("buttons"):
            line += " Buttons: " + ", ".join(d["buttons"]) + "."
        opts = d.get("options") or []
        if opts:
            line += " Options: " + ", ".join(
                f'{o.get("label")} [{"x" if o.get("checked") else " "}]' for o in opts) + "."
        parts.append(line)
    return " | ".join(parts)


def dialog_open_error(dialogs: list[dict]) -> DazError:
    return DazError(
        "dialog_open",
        "Daz Studio stopped on a dialog and is waiting for an answer: " + describe_dialogs(dialogs),
        "Answer it with daz_dialog(button=...) (or button='escape' to cancel); the waiting call's result "
        "comes back then. Ask the user first when the answer would discard or overwrite their work.",
        {"dialogs": dialogs},
    )


class HttpTransport(Transport):
    name = "http"

    def __init__(self, info: BridgeInfo | None = None):
        self._info = info
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="daz-bridge")
        self._pending: Future | None = None  # an execute still waiting on a dialog
        self._features: set[str] | None = None

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
        self._features = set(data.get("features") or [])
        return data

    # ------------------------------------------------------------ dialogs --
    def supports_dialogs(self) -> bool:
        if self._features is None:
            try:
                self.status()
            except DazError:
                return False
        return "dialogs" in (self._features or set())

    def dialogs(self) -> dict:
        """Open dialogs, and whether a tool call is waiting on one."""
        if not self.supports_dialogs():
            raise DazError("not_supported", "Seeing Daz Studio dialogs needs the bridge plugin 0.2 or later.",
                           "Update the plugin (`uvx daz3d-mcp setup`) and restart Daz Studio.")
        data = self._request("/v1/dialogs", None, timeout=10).get("result") or {}
        pending = self._pending is not None and not self._pending.done()
        return {"dialogs": data.get("dialogs") or [], "busy": bool(data.get("busy")), "waiting_call": pending}

    def _blocking_dialogs(self) -> list[dict]:
        data = self._request("/v1/dialogs", None, timeout=5).get("result") or {}
        return [d for d in data.get("dialogs") or [] if not d.get("progress")]

    def answer_dialog(self, button: str | None = None, dialog_id: str | None = None,
                      check: list[str] | None = None, uncheck: list[str] | None = None,
                      wait: float = 600.0) -> dict:
        """Presses a button (after setting check boxes). When a tool call was
        waiting on the dialog, waits for it and returns its raw response."""
        if not self.supports_dialogs():
            raise DazError("not_supported", "Answering Daz Studio dialogs needs the bridge plugin 0.2 or later.",
                           "Update the plugin (`uvx daz3d-mcp setup`) and restart Daz Studio, or ask the "
                           "user to click the dialog.")
        body: dict = {}
        if button:
            body["button"] = button
        if dialog_id:
            body["id"] = dialog_id
        if check:
            body["check"] = list(check)
        if uncheck:
            body["uncheck"] = list(uncheck)
        answered = self._request("/v1/dialogs/answer", body, timeout=10).get("result")
        out: dict = {"answered": answered}
        fut = self._pending
        if fut is not None and button:
            out["response"] = self._wait(fut, wait)
        return out

    def wait_pending(self, wait: float) -> dict | None:
        """Waits for a tool call that was left waiting; None when there is none."""
        fut = self._pending
        if fut is None:
            return None
        return self._wait(fut, wait)

    def _wait(self, fut: Future, timeout: float) -> dict:
        """Waits for an execute request, watching for dialogs that block it."""
        self._pending = None
        watch = self.supports_dialogs()
        deadline = time.monotonic() + timeout
        first_seen: dict[str, float] = {}
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._pending = fut
                raise DazError("timeout", f"Daz Studio did not answer within {timeout:.0f} s.",
                               "It is still working (or waiting on a dialog nobody can see). Call daz_dialog "
                               "to look; it also collects the result once the call ends.")
            try:
                return fut.result(timeout=min(DIALOG_POLL, remaining) if watch else remaining)
            except FutureTimeout:
                pass
            if not watch:
                continue
            try:
                dialogs = self._blocking_dialogs()
            except DazError:
                continue
            now = time.monotonic()
            first_seen = {d["id"]: first_seen.get(d["id"], now) for d in dialogs if d.get("id")}
            blocking = [d for d in dialogs if now - first_seen.get(d.get("id"), now) >= DIALOG_GRACE]
            if blocking and not fut.done():
                self._pending = fut
                raise dialog_open_error(blocking)

    def execute(self, code: str, args: dict, timeout: float, dialogs: list[dict] | None = None) -> dict:
        fut = self._pending
        if fut is not None:
            if not fut.done():
                try:
                    blocking = self._blocking_dialogs() if self.supports_dialogs() else []
                except DazError:
                    blocking = []
                if blocking:
                    raise dialog_open_error(blocking)
                raise DazError("busy", "Daz Studio is still running an earlier call.",
                               "Call daz_dialog to wait for it (and see any dialog it stopped on).")
            self._pending = None
        payload: dict = {"code": code, "entry": ENTRY_FUNCTION, "args": json.dumps(args)}
        if dialogs:
            payload["dialogs"] = dialogs
        fut = self._pool.submit(self._request, "/v1/execute", payload, timeout + SOCKET_SLACK)
        return self._wait(fut, timeout)


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

    def execute(self, code: str, args: dict, timeout: float, dialogs: list[dict] | None = None) -> dict:
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
        self._http: HttpTransport | None = None

    def _pick(self) -> Transport:
        info = read_bridge_info()
        if info is not None:
            # Keep one HttpTransport per running bridge: it remembers a call
            # that is waiting on a dialog.
            if self._http is None or self._http._info != info:
                self._http = HttpTransport(info)
            return self._http
        if os.environ.get("DAZ3D_MCP_NO_FILE_FALLBACK"):
            return HttpTransport()
        return self._file

    def status(self) -> dict:
        t = self._pick()
        data = t.status()
        data.setdefault("transport", t.name)
        return data

    def execute(self, code: str, args: dict, timeout: float, dialogs: list[dict] | None = None) -> dict:
        return self._pick().execute(code, args, timeout, dialogs)

    def dialogs(self) -> dict:
        return self._pick().dialogs()

    def answer_dialog(self, button: str | None = None, dialog_id: str | None = None,
                      check: list[str] | None = None, uncheck: list[str] | None = None,
                      wait: float = 600.0) -> dict:
        return self._pick().answer_dialog(button, dialog_id, check, uncheck, wait)

    def wait_pending(self, wait: float) -> dict | None:
        return self._pick().wait_pending(wait)
