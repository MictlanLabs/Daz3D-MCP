"""render_postwork: the ffmpeg filter graph, and a real run when ffmpeg is there."""

from __future__ import annotations

import subprocess

import pytest

from daz3d_mcp import postwork, video


def test_every_look_builds_a_graph_to_out():
    for look in postwork.LOOKS:
        graph = postwork.build_filter(look)
        assert graph.endswith("[out]")
        assert "drawbox" in graph and "overlay" in graph  # black behind transparent pixels by default


def test_film_look_has_the_photographic_steps():
    graph = postwork.build_filter("film")
    for step in ("curves=master=", "colorbalance=", "eq=saturation=", "vignette=", "unsharp=", "noise="):
        assert step in graph
    # ffmpeg refuses unsharp matrices over 25 (lx/2 + ly/2) * 2
    assert "lx=17" not in graph


def test_strength_zero_keeps_the_tones():
    graph = postwork.build_filter("film", strength=0, grain=0, vignette=0, sharpen=0)
    assert "curves" not in graph and "colorbalance" not in graph and "noise" not in graph


def test_background_none_keeps_transparency_and_colors_are_checked():
    assert "drawbox" not in postwork.build_filter("film", background=None)
    assert "color=0xff0000@1" in postwork.build_filter("neutral", background=[1, 0, 0])
    assert "color=0x102030@1" in postwork.build_filter("neutral", background="#102030")
    with pytest.raises(ValueError):
        postwork.build_filter("film", background="red")
    with pytest.raises(ValueError):
        postwork.build_filter("sepia")


def test_default_output_sits_next_to_the_image(tmp_path):
    assert postwork.default_output(tmp_path / "shot.png") == tmp_path / "shot-post.png"
    assert postwork.default_output(tmp_path / "shot.tif") == tmp_path / "shot-post.png"


@pytest.mark.skipif(video.find_ffmpeg() is None, reason="needs ffmpeg")
@pytest.mark.parametrize("look", list(postwork.LOOKS))
def test_ffmpeg_runs_every_look(tmp_path, look):
    ffmpeg = video.find_ffmpeg()
    src = tmp_path / "in.png"
    subprocess.run([ffmpeg, "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=0x806040@0.5:s=64x48,format=rgba", "-frames:v", "1", str(src)], check=True)
    out = postwork.apply(ffmpeg, src, tmp_path / f"out-{look}.png", look=look)
    assert out.is_file() and out.stat().st_size > 0
