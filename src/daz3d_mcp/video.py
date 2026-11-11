"""Turns a folder of rendered frames into a video with ffmpeg.

Daz Studio ships its own ffmpeg (on Windows in <install>/bin/ffmpeg.exe), so
most users need nothing extra. A ffmpeg on PATH, the "ffmpeg" setting or the
DAZ3D_MCP_FFMPEG environment variable win over it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from daz3d_mcp.daz_locate import find_daz_installs

FORMATS = ("mp4", "gif")


class VideoError(Exception):
    pass


def _exe_name() -> str:
    return "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"


def find_ffmpeg(configured: str | None = None) -> str | None:
    """Path of an ffmpeg to use, or None."""
    for candidate in (configured, os.environ.get("DAZ3D_MCP_FFMPEG")):
        if candidate and Path(candidate).expanduser().is_file():
            return str(Path(candidate).expanduser())
    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path
    name = _exe_name()
    for install in find_daz_installs():
        for folder in (install.root / "bin", install.root, install.executable.parent,
                       install.executable.parent.parent / "Resources"):
            exe = folder / name
            if exe.is_file():
                return str(exe)
    return None


def _concat_list(frames: list[Path], fps: float, list_path: Path) -> None:
    # The concat demuxer takes any file names (frames need not be numbered
    # 0, 1, 2...), each shown for 1/fps seconds. The last file is listed twice
    # so ffmpeg keeps its duration.
    step = 1.0 / fps
    lines = []
    for f in frames:
        lines.append("file '" + f.as_posix().replace("'", "'\\''") + "'")
        lines.append(f"duration {step:.6f}")
    lines.append("file '" + frames[-1].as_posix().replace("'", "'\\''") + "'")
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def encode(ffmpeg: str, frames: list[Path], out: Path, fps: float, fmt: str = "mp4",
           gif_width: int = 640, timeout: float = 1800.0) -> Path:
    """Encodes the frames (in order) into out. Returns out."""
    if fmt not in FORMATS:
        raise VideoError(f"Unknown video format {fmt!r}; use one of {', '.join(FORMATS)}.")
    if not frames:
        raise VideoError("No frames to encode.")
    list_path = out.with_name(out.stem + "-frames.txt")
    _concat_list(frames, fps, list_path)
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path)]
    if fmt == "mp4":
        # yuv420p plays everywhere (Windows, macOS, browsers); it needs even sizes.
        cmd += ["-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-r", f"{fps:g}", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", str(out)]
    else:
        cmd += ["-vf", f"fps={fps:g},scale='min({gif_width},iw)':-2:flags=lanczos,split[a][b];"
                       "[a]palettegen[p];[b][p]paletteuse", "-loop", "0", str(out)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VideoError(f"ffmpeg did not run: {exc}") from exc
    finally:
        try:
            list_path.unlink()
        except OSError:
            pass
    if proc.returncode != 0 or not out.is_file():
        raise VideoError("ffmpeg failed: " + (proc.stderr or proc.stdout or "").strip()[-800:])
    return out
