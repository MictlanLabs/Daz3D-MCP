"""High-level calls into Daz Studio: run a library tool or free code."""

from __future__ import annotations

from daz3d_mcp.scriptlib import build_tool_code, build_user_code
from daz3d_mcp.settings import Settings, load_settings
from daz3d_mcp.transport import DazError, Transport, make_transport

ERROR_HINTS = {
    "unsaved_changes": "Ask the user whether to save first (scene_save) or pass discard_changes=true.",
    "not_found": "Check the path or label; scene_info lists what is in the scene.",
    "script_error": "Read the message and line; DazScript is ES5-style JavaScript.",
}


class DazClient:
    def __init__(self, settings: Settings | None = None, transport: Transport | None = None):
        self.settings = settings or load_settings()
        self.transport = transport or make_transport(self.settings.transport, self.settings.daz_executable)

    def _unwrap(self, response: dict) -> tuple[object, list[str]]:
        log = list(response.get("log") or [])
        if response.get("ok"):
            return response.get("result"), log
        err = response.get("error") or {}
        code = err.get("code", "script_error")
        message = err.get("message", "Unknown error in Daz Studio.")
        if err.get("line"):
            message += f" (line {err['line']})"
        details = err.get("details")
        if log:
            details = {"details": details, "log": log}
        raise DazError(code, message, ERROR_HINTS.get(code), details)

    def run_tool(self, tool: str, args: dict | None = None, timeout: float | None = None) -> object:
        code = build_tool_code(tool)
        response = self.transport.execute(code, args or {}, timeout or self.settings.timeout)
        result, _log = self._unwrap(response)
        return result

    def run_code(self, code: str, args: dict | None = None, timeout: float | None = None) -> tuple[object, list[str]]:
        program = build_user_code(code)
        response = self.transport.execute(program, args or {}, timeout or self.settings.timeout)
        return self._unwrap(response)

    def bridge_status(self) -> dict:
        return self.transport.status()
