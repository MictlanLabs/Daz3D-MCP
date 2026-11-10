"""Exercises the compiled C++ bridge (Qt side) against the Python transport.

Runs only when CI (or you) built the bridge against the SDK stub:
  DAZMCP_BRIDGE_HOST=<bridge_host binary>  DAZMCP_BRIDGE_MODULE=<built module>
See .github/workflows/ci.yml.
"""

from __future__ import annotations

import http.client
import os
import subprocess
import time

import pytest

from daz3d_mcp.transport import DazError, HttpTransport, read_bridge_info

HOST = os.environ.get("DAZMCP_BRIDGE_HOST")
MODULE = os.environ.get("DAZMCP_BRIDGE_MODULE")

pytestmark = pytest.mark.skipif(not (HOST and MODULE), reason="bridge not built (see CI)")


@pytest.fixture
def plugin(daz_home):
    env = dict(os.environ, DAZ3D_MCP_HOME=str(daz_home), DAZ3D_MCP_PORT="18741", QT_QPA_PLATFORM="offscreen")
    proc = subprocess.Popen([HOST, MODULE, "30"], env=env, stderr=subprocess.PIPE, text=True)
    for _ in range(100):
        if (daz_home / "bridge.json").is_file():
            break
        time.sleep(0.1)
    else:
        proc.kill()
        pytest.fail("bridge did not start: " + (proc.stderr.read() if proc.stderr else ""))
    yield proc
    proc.terminate()
    proc.wait(10)


def _raw(port: int, headers: dict, path: str = "/v1/status") -> int:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path, headers=headers)
    return conn.getresponse().status


def test_status_and_execute(plugin, daz_home):
    t = HttpTransport()
    status = t.status()
    assert status["ok"] and status["protocol"] == 1
    out = t.execute("function f(){}", {"a": 1}, 10)
    assert out == {"ok": True, "result": {"func": "dazmcp_entry", "args": {"a": 1}}}
    assert (daz_home / "token").stat().st_mode & 0o077 == 0


def test_script_error_shape(plugin):
    out = HttpTransport().execute("SYNTAX_ERROR", {}, 10)
    assert out["ok"] is False and out["error"]["code"] == "script_error"


def test_security_checks(plugin):
    info = read_bridge_info()
    good = {"Authorization": f"Bearer {info.token}"}
    assert _raw(info.port, {}) == 401
    assert _raw(info.port, {"Authorization": "Bearer " + "0" * 64}) == 401
    assert _raw(info.port, {**good, "Origin": "http://example.com"}) == 403
    assert _raw(info.port, {**good, "Host": "example.com"}) == 403
    assert _raw(info.port, good) == 200


def test_large_request(plugin):
    out = HttpTransport().execute("function f(){}", {"big": "x" * 5_000_000}, 20)
    assert len(out["result"]["args"]["big"]) == 5_000_000


def test_discovery_file_removed_on_quit(plugin, daz_home):
    plugin.terminate()
    plugin.wait(10)
    # SIGTERM skips aboutToQuit; the MCP must then report a clear error.
    if (daz_home / "bridge.json").is_file():
        with pytest.raises(DazError) as err:
            HttpTransport().status()
        assert err.value.code == "bridge_unreachable"
