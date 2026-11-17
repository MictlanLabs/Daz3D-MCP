"""Photographic postwork for finished renders, done with ffmpeg.

A raw Iray render looks "3D": perfectly clean, evenly sharp, saturated, with
straight-line tones. Photographers and most realistic Daz artists finish their
images: a film-like tone curve, a little split toning, local contrast, lens
sharpening, grain and a vignette. These are ffmpeg filters, so the ffmpeg that
ships with Daz Studio is enough (see video.find_ffmpeg).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from daz3d_mcp.video import VideoError


@dataclass(frozen=True)
class Look:
    curve: str          # ffmpeg curves points (master channel)
    shadows: tuple      # colorbalance shadows (r, g, b), -1..1
    highlights: tuple   # colorbalance highlights (r, g, b)
    saturation: float
    clarity: float      # large-radius unsharp amount (local contrast)
    sharpen: float      # small-radius unsharp amount
    grain: float        # ffmpeg noise strength 0..100
    vignette: float     # vignette angle in radians (smaller = softer); 0 = none


LOOKS: dict[str, Look] = {
    # lifted blacks, soft highlight roll-off, cool shadows, warm highlights
    "film": Look("0/0.02 0.25/0.215 0.5/0.5 0.75/0.79 1/0.97", (-0.02, 0.0, 0.04), (0.04, 0.015, -0.03),
                 0.9, 0.35, 0.6, 6.0, 0.55),
    # gentler: portraits and bright scenes
    "soft": Look("0/0.03 0.25/0.24 0.5/0.51 0.75/0.77 1/0.96", (-0.01, 0.0, 0.02), (0.025, 0.01, -0.015),
                 0.93, 0.2, 0.45, 4.0, 0.4),
    # more contrast and bite: night, action, neon
    "punchy": Look("0/0.0 0.25/0.19 0.5/0.5 0.75/0.82 1/0.99", (-0.03, 0.0, 0.05), (0.04, 0.01, -0.04),
                   1.0, 0.5, 0.75, 7.0, 0.65),
    # only the background, sharpening and a touch of grain: keeps the render's own colors
    "neutral": Look("0/0 1/1", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 1.0, 0.0, 0.4, 3.0, 0.0),
}


def _hex(color: str | list[float] | tuple) -> str:
    if isinstance(color, str):
        c = color.strip().lstrip("#")
        if len(c) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in c):
            raise ValueError(f"Colors are [r, g, b] from 0 to 1 or \"#rrggbb\" (got {color!r}).")
        return "0x" + c.lower()
    if len(color) < 3:
        raise ValueError("Colors are [r, g, b] from 0 to 1 or \"#rrggbb\".")
    vals = [max(0, min(255, round(float(v) * 255))) for v in color[:3]]
    return "0x" + "".join(f"{v:02x}" for v in vals)


def build_filter(look: str = "film", strength: float = 1.0, background: str | list | None = "#000000",
                 grain: float | None = None, vignette: float | None = None,
                 sharpen: float | None = None) -> str:
    """ffmpeg -filter_complex graph from input [0:v] to output [out]."""
    if look not in LOOKS:
        raise ValueError(f"look must be one of {', '.join(LOOKS)}.")
    lk = LOOKS[look]
    s = max(0.0, min(2.0, float(strength)))
    steps: list[str] = []
    graph = ""
    src = "[0:v]"
    if background is not None:
        # transparent pixels (nothing behind the subject) become the background color
        graph += (f"[0:v]format=rgba,split[fg][tmp];[tmp]drawbox=x=0:y=0:w=iw:h=ih:color={_hex(background)}@1:t=fill"
                  f"[bg];[bg][fg]overlay=format=auto,format=rgb24[base];")
        src = "[base]"
    else:
        steps.append("format=rgb24")
    clarity = lk.clarity * s
    if clarity > 0:
        steps.append(f"unsharp=lx=13:ly=13:la={clarity:.3f}:cx=3:cy=3:ca=0")
    if look != "neutral" and s > 0:
        # blend the curve toward identity as strength goes down
        pts = []
        for pair in lk.curve.split():
            x, y = (float(v) for v in pair.split("/"))
            pts.append(f"{x:g}/{x + (y - x) * min(s, 1.0):.4f}")
        steps.append("curves=master='" + " ".join(pts) + "'")
        sh, hi = lk.shadows, lk.highlights
        steps.append(f"colorbalance=rs={sh[0] * s:.3f}:gs={sh[1] * s:.3f}:bs={sh[2] * s:.3f}"
                     f":rh={hi[0] * s:.3f}:gh={hi[1] * s:.3f}:bh={hi[2] * s:.3f}")
        sat = 1 + (lk.saturation - 1) * s
        if abs(sat - 1) > 1e-3:
            steps.append(f"eq=saturation={sat:.3f}")
    vig = lk.vignette if vignette is None else vignette
    if vig and vig > 0:
        steps.append(f"vignette=angle={min(vig, 1.2):.3f}")
    sharp = (lk.sharpen * s) if sharpen is None else sharpen
    if sharp and sharp > 0:
        steps.append(f"unsharp=lx=5:ly=5:la={sharp:.3f}:cx=5:cy=5:ca=0")
    gr = (lk.grain * s) if grain is None else grain
    if gr and gr > 0:
        steps.append(f"noise=alls={gr:.1f}:allf=u")
    graph += src + ",".join(steps or ["null"]) + "[out]"
    return graph


def apply(ffmpeg: str, src: Path, dst: Path, look: str = "film", strength: float = 1.0,
          background: str | list | None = "#000000", grain: float | None = None,
          vignette: float | None = None, sharpen: float | None = None) -> Path:
    graph = build_filter(look, strength, background, grain, vignette, sharpen)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
           "-filter_complex", graph, "-map", "[out]", "-frames:v", "1"]
    if dst.suffix.lower() in (".jpg", ".jpeg"):
        cmd += ["-q:v", "2"]
    cmd.append(str(dst))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as exc:
        raise VideoError(f"ffmpeg did not run: {exc}") from exc
    if proc.returncode != 0 or not dst.is_file():
        raise VideoError("ffmpeg failed: " + (proc.stderr or proc.stdout or "").strip()[-800:])
    return dst


def default_output(src: Path) -> Path:
    return src.with_name(f"{src.stem}-post{src.suffix if src.suffix.lower() in ('.png', '.jpg', '.jpeg') else '.png'}")
