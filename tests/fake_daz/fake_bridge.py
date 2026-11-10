"""A fake Daz3D-MCP bridge for tests.

It speaks the same HTTP protocol as the C++ plugin (bridge/src/bridgeserver.cpp),
including the token and Host/Origin checks, but runs the DazScript programs with
Node.js against fake_daz.js instead of inside Daz Studio.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent


class FakeBridge:
    def __init__(self, home: Path, state: Path):
        self.home = home
        self.state = state
        self.token = secrets.token_hex(32)
        self.lock = threading.Lock()
        self.requests: list[dict] = []
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence
                pass

            def _send(self, status: int, body: bytes) -> None:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _check(self) -> bool:
                host = (self.headers.get("Host") or "").split(":")[0].lower()
                if host not in ("127.0.0.1", "localhost") or self.headers.get("Origin"):
                    self._send(403, b'{"ok":false,"error":{"code":"forbidden","message":"no"}}')
                    return False
                auth = self.headers.get("Authorization") or ""
                if not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:].strip(), bridge.token):
                    self._send(401, b'{"ok":false,"error":{"code":"unauthorized","message":"no"}}')
                    return False
                return True

            def do_GET(self):  # noqa: N802
                if not self._check():
                    return
                if self.path == "/v1/status":
                    body = {"ok": True, "protocol": 1, "bridge_version": "fake", "daz_version": "6.25.2026.14722",
                            "busy": False}
                    self._send(200, json.dumps(body).encode())
                else:
                    self._send(404, b'{"ok":false,"error":{"code":"not_found","message":"?"}}')

            def do_POST(self):  # noqa: N802
                if not self._check():
                    return
                length = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(length))
                bridge.requests.append(req)
                with bridge.lock:
                    self._send(200, bridge.run(req["code"], req.get("entry", "dazmcp_entry"), req.get("args", "{}")))

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def run(self, code: str, entry: str, args: str) -> bytes:
        with tempfile.TemporaryDirectory() as tmp:
            code_file = Path(tmp) / "program.dsa"
            args_file = Path(tmp) / "args.json"
            code_file.write_text(code, encoding="utf-8")
            args_file.write_text(args, encoding="utf-8")
            env = dict(os.environ, DAZMCP_FAKE_STATE=str(self.state))
            proc = subprocess.run(
                ["node", str(HERE / "run.js"), str(code_file), entry, str(args_file)],
                capture_output=True, text=True, env=env, timeout=60,
            )
        if proc.returncode != 0:
            # Same shape the plugin uses when DzScript reports an error.
            err = {"ok": False, "error": {"code": "script_error", "message": proc.stderr.strip()[-500:]}}
            return json.dumps(err).encode()
        return proc.stdout.encode()

    def start(self) -> "FakeBridge":
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "token").write_text(self.token)
        (self.home / "bridge.json").write_text(json.dumps(
            {"port": self.port, "protocol": 1, "bridge_version": "fake", "daz_version": "6.25.2026.14722",
             "pid": os.getpid()}))
        self.thread.start()
        return self

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
