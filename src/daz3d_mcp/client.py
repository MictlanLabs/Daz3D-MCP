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
        # Dialogs the bridge saw while the script ran (answered by a rule, by
        # the agent, or closed by Daz itself).
        for d in response.get("dialogs") or []:
            answer = d.get("answered")
            how = f'answered "{answer}"' if answer else "closed without an answer from the MCP"
            log.append(f'Daz Studio showed the dialog "{d.get("title") or ""}" '
                       f'({" ".join(str(d.get("text") or "").split())[:200]}); {how}.')
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

    def _execute(self, code: str, args: dict, timeout: float | None) -> dict:
        rules = self.settings.dialog_rules
        if rules:
            return self.transport.execute(code, args, timeout or self.settings.timeout, rules)
        return self.transport.execute(code, args, timeout or self.settings.timeout)

    def run_tool(self, tool: str, args: dict | None = None, timeout: float | None = None) -> object:
        response = self._execute(build_tool_code(tool), args or {}, timeout)
        result, log = self._unwrap(response)
        if response.get("dialogs") and isinstance(result, dict):
            result = {**result, "dialogs": log}
        return result

    def run_code(self, code: str, args: dict | None = None, timeout: float | None = None) -> tuple[object, list[str]]:
        return self._unwrap(self._execute(build_user_code(code), args or {}, timeout))

    def bridge_status(self) -> dict:
        return self.transport.status()

    def dialogs(self) -> dict:
        return self.transport.dialogs()

    def answer_dialog(self, button: str | None = None, dialog_id: str | None = None,
                      check: list[str] | None = None, uncheck: list[str] | None = None,
                      wait: float | None = None) -> dict:
        """Answers a dialog; when a tool call was waiting on it, adds that call's
        result (or raises its error)."""
        out = self.transport.answer_dialog(button, dialog_id, check, uncheck, wait or self.settings.timeout)
        return self._finish(out)

    def wait_pending(self, wait: float | None = None) -> dict | None:
        response = self.transport.wait_pending(wait or self.settings.timeout)
        if response is None:
            return None
        return self._finish({"response": response})

    def _finish(self, out: dict) -> dict:
        response = out.pop("response", None)
        if response is not None:
            result, log = self._unwrap(response)
            out["call_result"] = result
            if log:
                out["log"] = log
        return out
