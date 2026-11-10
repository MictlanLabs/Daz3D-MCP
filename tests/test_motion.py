"""The motion math without Daz: rotations, file readers, bone maps, contact."""

from __future__ import annotations

import itertools
import random

import pytest

from daz3d_mcp import clips, motion
from motion_fixture import write_bvh, write_mixamo_fbx


@pytest.mark.parametrize("mode", ["applied", "product"])
@pytest.mark.parametrize("order", ["".join(p) for p in itertools.permutations("XYZ")])
def test_euler_round_trip(order, mode):
    rnd = random.Random(order + mode)
    for _ in range(200):
        a = (rnd.uniform(-170, 170), rnd.uniform(-170, 170), rnd.uniform(-170, 170))
        m = motion.euler_mat(a, order, mode)
        back = motion.mat_euler(m, order, mode)
        assert motion.rot_angle(motion.m_mul(m, motion.m_t(motion.euler_mat(back, order, mode)))) < 1e-4


def test_euler_stays_close_to_the_previous_frame():
    m = motion.euler_mat((170, 10, -175), "XYZ")
    near = motion.mat_euler(m, "XYZ", prev=(185, 10, 180))
    assert near == pytest.approx((170 + 0, 10, 185), abs=1e-6) or abs(near[0] - 170) < 1e-6
    assert all(abs(n - p) < 30 for n, p in zip(near, (185, 10, 180)))


@pytest.mark.parametrize("conv", motion.CONVENTIONS)
def test_dials_round_trip_with_orientation(conv):
    q = motion.axis_angle((0.2, 0.3, 0.9), 40)
    rel = motion.euler_mat((12, -40, 25), "YZX")
    ang = motion.dial_angles(rel, "XYZ", q, conv)
    assert motion.rot_angle(motion.m_mul(rel, motion.m_t(motion.dial_rotation(ang, "XYZ", q, conv)))) < 1e-4


def test_from_to():
    for a, b in [((1, 0, 0), (0, 1, 0)), ((0, -1, 0), (0, -0.7, 0.7)), ((1, 0, 0), (-1, 0, 0))]:
        got = motion.m_vec(motion.from_to(a, b), a)
        assert motion.angle_between(got, b) < 1e-6


def test_readers_and_rig_detection(tmp_path):
    fbx = motion.read_motion(write_mixamo_fbx(tmp_path / "w.fbx", unit_cm=100.0))  # a file in meters
    assert fbx.frames == 61 and fbx.fps == 30 and fbx.take == "mixamo.com"
    hips = [motion.bare(n) for n in fbx.names].index("hips")
    assert fbx.rest[hips].pos == pytest.approx((0, 104, 0))  # converted to cm
    assert motion.detect_rig(fbx.names, motion.SOURCE_RIGS)[0] == "mixamo"
    bvh = motion.read_motion(write_bvh(tmp_path / "w.bvh"))
    assert motion.detect_rig(bvh.names, motion.SOURCE_RIGS)[0] == "cmu"
    assert bvh.names[-1] == "RightToeBase_End"
    (tmp_path / "a.fbx").write_text("; FBX 7.4.0 project file\nFBXHeaderExtension:  {\n}\n")
    with pytest.raises(motion.MotionError, match="ASCII"):
        motion.read_motion(tmp_path / "a.fbx")
    (tmp_path / "b.bvh").write_text("nope")
    with pytest.raises(motion.MotionError, match="HIERARCHY"):
        motion.read_motion(tmp_path / "b.bvh")


def test_contact_report_ranges_and_slide():
    def h(height, x=0.0, z=0.0, bone="l_foot"):
        return {"height": height, "x": x, "z": z, "bone": bone}
    heights = {0: {"l": h(0), "r": h(5, bone="r_foot")}, 1: {"l": h(0, z=2), "r": h(5, bone="r_foot")},
               2: {"l": h(-3, z=4), "r": h(4, bone="r_foot")}, 3: {"l": h(6), "r": h(5, bone="r_foot")},
               4: {"l": h(0, z=50, bone="l_toes"), "r": h(0, bone="r_foot")}}
    r = motion.contact_report(heights, tolerance=1)
    assert r["frames_below_floor"] == [[2, 2]] and r["frames_floating"] == [[3, 3]]
    assert r["slide_cm"] == {"l": 4.0, "r": 0.0} and r["lowest_cm"] == -3


def test_clip_rename_between_generations():
    clip = {"name": "x", "generation": "Genesis 9", "frames": 10, "loop": False,
            "tracks": {"bones": {"l_upperarm": {"rotation": [[0, 0, 0, 0], [10, 0, 0, 30]]}}}}
    tracks, warnings, last = clips.clip_tracks(clip, start=5, speed=0.5, repeat=1, generation="Genesis 8 Female",
                                               in_place=False, root="hip")
    assert tracks["bones"] == {"lShldrBend": {"rotation": [[5, 0, 0, 0], [25, 0, 0, 30]]}}
    assert last == 25 and warnings
