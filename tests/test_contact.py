"""Soft contact: skin pushed out of a pressing hand, the bulge around it, the spring that makes
the flesh lag and wobble, and the contact_bake tool against a stand-in for Daz."""

from __future__ import annotations

import json
import math
from pathlib import Path

import anyio
import pytest
from mcp.server.fastmcp import FastMCP

from daz3d_mcp import contact as ct
from daz3d_mcp import contact_tools, morph_tools
from daz3d_mcp import morphgen as mg

N = 15


def sheet_with_hand() -> dict:
    """A soft sheet facing +z (the 'breast', weighted to l_pectoral) and a small flat 'palm' above
    it facing -z (weighted to r_hand), as one mesh."""
    verts, facets, pecs, hand = [], [], [], []
    for j in range(N):
        for i in range(N):
            verts += [i - 7.0 + 5.0, j - 7.0, 0.0]
            pecs += [j * N + i, 1.0]
    for j in range(N - 1):
        for i in range(N - 1):
            a = j * N + i
            facets += [a, a + 1, a + N + 1, a + N]
    base = N * N
    m = 5
    for j in range(m):
        for i in range(m):
            verts += [i - 2.0 + 5.0, j - 2.0, 0.0]
            hand += [base + j * m + i, 1.0]
    for j in range(m - 1):
        for i in range(m - 1):
            a = base + j * m + i
            facets += [a, a + m, a + m + 1, a + 1]
    return {"generation": "Genesis 9", "vertices": verts, "facets": facets,
            "weights": {"l_pectoral": pecs, "r_hand": hand}}


@pytest.fixture
def mesh(tmp_path) -> mg.Mesh:
    path = tmp_path / "m.json"
    path.write_text(json.dumps(sheet_with_hand()))
    return mg.Mesh.load(path)


def posed(mesh: mg.Mesh, depth: float) -> dict[int, mg.Vec]:
    hand = set(ct.hand_vertices(mesh, "right"))
    return {i: (x, y, z - depth if i in hand else z) for i, (x, y, z) in enumerate(mesh.vertices)}


def test_hand_and_softness(mesh):
    hand = ct.hand_vertices(mesh, "right")
    assert len(hand) == 25
    soft = ct.breast_softness(mesh, ("left",))
    assert soft and all(0 < s <= 1 for s in soft.values())


def test_skin_is_pushed_out_of_the_hand_and_bulges_around(mesh):
    soft = {i: 1.0 for i in range(N * N)}
    hand = ct.hand_vertices(mesh, "right")
    target, touching, deepest = ct.contact_targets(mesh, soft, hand, posed(mesh, 1.0), ct.Settings())
    assert deepest == pytest.approx(1.0, abs=1e-6)
    assert touching
    for i in touching:
        assert target[i][2] <= -1.0 + 1e-6
    outside = [i for i in target if i not in touching and target[i][2] > 0.01]
    assert outside, "flesh beside the dent bulges out"
    no = ct.contact_targets(mesh, soft, hand, posed(mesh, -0.5), ct.Settings())
    assert not no[1]


def test_flesh_lags_overshoots_and_settles(mesh):
    soft = {i: 1.0 for i in range(N * N)}
    hand = ct.hand_vertices(mesh, "right")
    seq = [posed(mesh, 1.0)] * 10 + [posed(mesh, -3.0)] * 40
    out = ct.simulate(mesh, soft, hand, seq, ct.Settings(sag=0.0, subd_boost=1.0))
    center = min(range(N * N), key=lambda i: math.dist(mesh.vertices[i], (5.0, 0.0, 0.0)))
    z = [f.get(center, (0.0, 0.0, 0.0))[2] for f in out]
    assert z[9] == pytest.approx(-1.0 - ct.Settings().gap, abs=0.05)
    assert max(z[10:25]) > 0.05, "released flesh springs past its rest shape"
    assert abs(z[-1]) < 0.02, "and settles"


def test_scale_turns_world_offsets_into_object_space(mesh):
    soft = {i: 1.0 for i in range(N * N)}
    hand = ct.hand_vertices(mesh, "right")
    a = ct.simulate(mesh, soft, hand, [posed(mesh, 1.0)], ct.Settings(sag=0.0, subd_boost=1.0), scale=1.0)[0]
    b = ct.simulate(mesh, soft, hand, [posed(mesh, 1.0)], ct.Settings(sag=0.0, subd_boost=1.0), scale=2.0)[0]
    i = next(iter(a))
    assert b[i][2] == pytest.approx(a[i][2] / 2, abs=1e-4)


class FakeDaz:
    def __init__(self, mesh_data: dict):
        self.data = mesh_data
        self.calls: list[tuple[str, dict]] = []

    async def call(self, tool: str, args: dict | None = None, timeout: float | None = None) -> dict:
        args = dict(args or {})
        self.calls.append((tool, args))
        if tool == "figure_info":
            return {"generation": "Genesis 9"}
        if tool == "morph_mesh":
            Path(args["path"]).write_text(json.dumps(self.data))
            return {}
        if tool == "anim_timeline":
            return {"start_frame": 0, "end_frame": 3}
        if tool == "contact_sample":
            flat = self.data["vertices"]
            verts = [flat[i:i + 3] for i in range(0, len(flat), 3)]
            rows = []
            for f in args["frames"]:
                depth = 1.0 if f < 2 else -3.0
                row = []
                for i in args["vertices"]:
                    x, y, z = verts[i]
                    row += [x, y, z - depth if i >= N * N else z]
                rows.append(row)
            Path(args["path"]).write_text(json.dumps({"frames": args["frames"], "positions": rows}))
            return {"scale": 1.0, "removed": 0}
        if tool == "contact_bake":
            if args.get("remove_only"):
                return {"removed": 4}
            data = json.loads(Path(args["path"]).read_text())
            return {"morphs": sum(1 for o in data["offsets"] if o)}
        raise AssertionError(tool)


def test_contact_bake_tool(tmp_path, monkeypatch):
    monkeypatch.setenv("DAZ3D_MCP_HOME", str(tmp_path / "home"))
    data = sheet_with_hand()
    daz = FakeDaz(data)
    mcp = FastMCP("test")
    gen = morph_tools.register(mcp, daz.call)
    contact_tools.register(mcp, daz.call, gen)

    def run(**args):
        async def go():
            return await mcp.call_tool("contact_bake", args)
        res = anyio.run(go)
        parts = res[0] if isinstance(res, tuple) else res
        return json.loads(parts[0].text)

    monkeypatch.setattr(ct, "breast_softness", lambda mesh, sides: {i: 1.0 for i in range(N * N)})
    out = run(figure="Amala", region="breast_left")
    assert out["frames"] == [0, 3] and out["morphs"] >= 2
    sample = next(a for t, a in daz.calls if t == "contact_sample")
    assert sample["remove_prefix"] == contact_tools.PREFIX and sample["frames"] == [0, 1, 2, 3]
    assert run(figure="Amala", region="breast_left", remove=True)["removed"] == 4


def test_flesh_springing_back_never_ends_inside_the_hand(mesh):
    soft = {i: 1.0 for i in range(N * N)}
    hand = ct.hand_vertices(mesh, "right")
    seq = [posed(mesh, d) for d in (0.0, 0.5, 1.0, 1.5, 1.5, 1.2, 0.8, 0.4, 0.0)]
    out = ct.simulate(mesh, soft, hand, seq, ct.Settings(sag=0.0, subd_boost=1.0))
    for pos, frame in zip(seq, out):
        offsets = {i: list(frame.get(i, (0.0, 0.0, 0.0))) for i in soft}
        assert not ct.resolve(mesh, soft, hand, pos, offsets, ct.Settings(gap=0.0), rounds=1)
