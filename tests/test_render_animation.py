"""render_animation against the fake Daz: one Iray render per frame, resume,
and joining the frames into a video with ffmpeg."""

from __future__ import annotations

import json
import shutil
import struct
import zlib

import anyio
import pytest

from daz3d_mcp import video
from daz3d_mcp.client import DazClient
from daz3d_mcp.server import create_server
from daz3d_mcp.settings import Settings


def call(server, tool, **args):
    async def go():
        return await server.call_tool(tool, args)
    result = anyio.run(go)
    content = result[0] if isinstance(result, tuple) else result
    texts = [c.text for c in content if getattr(c, "type", "") == "text"]
    return json.loads(texts[-1]), content


@pytest.fixture
def server(bridge, monkeypatch):
    monkeypatch.delenv("DAZ3D_MCP_FFMPEG", raising=False)
    return create_server(DazClient(Settings(transport="http")))


def renders(bridge) -> list:
    return json.loads(bridge.state.read_text())["renders"]


def png(path, w=64, h=36, shade=0):
    raw = b"".join(b"\x00" + bytes([shade, 80, 160]) * w for _ in range(h))
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def test_renders_every_frame_of_the_range(server, bridge, tmp_path):
    call(server, "camera_create", label="Cam", position=[0, 150, 300], look_at=[0, 100, 0])
    call(server, "anim_timeline", end_frame=9, frame=4)
    out = tmp_path / "walk"
    res, content = call(server, "render_animation", camera="Cam", max_time=5, out_dir=out.as_posix(),
                        video_format="none", previews=2)
    assert (res["frames"], res["first_frame"], res["last_frame"], res["rendered"], res["kept"]) == (10, 0, 9, 10, 0)
    assert sorted(p.name for p in out.iterdir()) == [f"frame_{i:04d}.png" for i in range(10)]
    done = renders(bridge)
    assert [r["frame"] for r in done] == list(range(10))
    assert {(r["camera"], r["max_time"]) for r in done} == {("Cam", 5)}
    assert [c.type for c in content] == ["text", "image", "text", "image", "text"]
    # The scene is back on the frame it was on.
    assert call(server, "anim_timeline")[0]["frame"] == 4


def test_step_range_and_resume(server, bridge, tmp_path):
    call(server, "anim_timeline", end_frame=30)
    out = tmp_path / "shots"
    res, _ = call(server, "render_animation", start_frame=10, end_frame=20, step=5, out_dir=out.as_posix(),
                  name="shot", image_format="jpg", video_format="none", previews=0)
    assert res["frames"] == 3 and res["files"] == "shot_####.jpg"
    assert [r["frame"] for r in renders(bridge)] == [10, 15, 20]
    (out / "shot_0015.jpg").unlink()
    res, _ = call(server, "render_animation", start_frame=10, end_frame=20, step=5, out_dir=out.as_posix(),
                  name="shot", image_format="jpg", video_format="none", previews=0)
    assert (res["rendered"], res["kept"]) == (1, 2)
    assert [r["frame"] for r in renders(bridge)][-1] == 15
    with pytest.raises(Exception, match="already exist"):
        call(server, "render_animation", start_frame=10, end_frame=20, step=5, out_dir=out.as_posix(),
             name="shot", image_format="jpg", video_format="none", resume=False)


def test_no_ffmpeg_still_keeps_the_frames(server, bridge, tmp_path, monkeypatch):
    monkeypatch.setattr(video, "find_ffmpeg", lambda configured=None: None)
    call(server, "anim_timeline", end_frame=2)
    res, _ = call(server, "render_animation", out_dir=(tmp_path / "x").as_posix(), previews=0)
    assert res["video"] is None and "ffmpeg" in res["video_error"] and res["frames"] == 3


@pytest.mark.skipif(video.find_ffmpeg() is None, reason="ffmpeg is needed to encode a video")
@pytest.mark.parametrize("fmt", ["mp4", "gif"])
def test_encode_frames_with_gaps(tmp_path, fmt):
    frames = []
    for i in (0, 2, 4, 6, 8, 10):  # numbered with gaps, as with step=2
        p = tmp_path / f"f_{i:04d}.png"
        png(p, w=65, h=37, shade=i * 20)  # odd size: mp4 must pad it
        frames.append(p)
    out = video.encode(video.find_ffmpeg(), frames, tmp_path / f"clip.{fmt}", fps=12, fmt=fmt)
    assert out.is_file() and out.stat().st_size > 100
    assert not (tmp_path / "clip-frames.txt").exists()
    probe = shutil.which("ffprobe")
    if probe and fmt == "mp4":
        import subprocess
        n = subprocess.run([probe, "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_read_frames", "-of", "csv=p=0", str(out)], capture_output=True, text=True)
        assert int(n.stdout.strip()) == 6


def test_render_one_frame(server, bridge, tmp_path):
    call(server, "anim_timeline", end_frame=20, frame=3)
    res, _ = call(server, "render", out_path=(tmp_path / "f12.png").as_posix(), frame=12)
    assert res["frame"] == 12 and renders(bridge)[-1]["frame"] == 12
    assert call(server, "anim_timeline")[0]["frame"] == 3
