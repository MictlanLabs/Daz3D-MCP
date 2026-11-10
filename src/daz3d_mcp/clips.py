"""Animation presets ("clips"): keyframes saved as JSON, independent of a scene.

A clip holds the tracks anim_keys_get returns, with frames counted from 0. It
can be applied to any figure of the same generation, at any frame, faster or
slower and repeated. Built-in clips ship with the package; the user's own
live in ~/.daz3d-mcp/animations.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from daz3d_mcp.motion import TARGET_RIGS
from daz3d_mcp.paths import animations_dir, config_dir

FORMAT = "daz3d-mcp-clip"


class ClipError(Exception):
    pass


def user_dir() -> Path:
    return config_dir() / "animations"


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not s:
        raise ClipError("The preset needs a name with letters or digits.")
    return s[:80]


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClipError(f"{path.name} is not a readable animation preset ({exc}).") from exc
    if data.get("format") != FORMAT or not isinstance(data.get("tracks"), dict):
        raise ClipError(f"{path.name} is not a Daz3D-MCP animation preset.")
    data["path"] = path.as_posix()
    return data


def _all() -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    try:
        out += [("built-in", p) for p in sorted(animations_dir().glob("*.json"))]
    except FileNotFoundError:
        pass
    if user_dir().is_dir():
        out += [("saved", p) for p in sorted(user_dir().glob("*.json"))]
    return out


def list_clips(query: str | None = None) -> list[dict]:
    words = (query or "").lower().split()
    out = []
    for origin, path in _all():
        try:
            c = _read(path)
        except ClipError:
            continue
        text = f"{c.get('name', '')} {c.get('description', '')}".lower()
        if words and not all(w in text for w in words):
            continue
        out.append({"name": c.get("name", path.stem), "origin": origin, "description": c.get("description", ""),
                    "generation": c.get("generation"), "frames": c.get("frames"), "fps": c.get("fps"),
                    "loop": bool(c.get("loop")), "bones": sorted((c["tracks"].get("bones") or {}).keys())[:40],
                    "path": path.as_posix()})
    return out


def find_clip(ref: str) -> dict:
    p = Path(ref).expanduser()
    if p.suffix.lower() == ".json" and p.is_absolute():
        if not p.is_file():
            raise ClipError(f"{p} does not exist.")
        return _read(p)
    want = slug(ref)
    found = None
    for _origin, path in _all():  # saved ones come last and win
        if path.stem == want:
            found = path
    if found is None:
        names = ", ".join(sorted({p.stem for _o, p in _all()})) or "none"
        raise ClipError(f"No animation preset named {ref!r}. Presets: {names}.")
    return _read(found)


def save_clip(name: str, keys: dict, *, start: float, end: float | None, description: str, loop: bool,
              overwrite: bool, fps: float) -> dict:
    tracks = keys.get("tracks") or {}
    shifted: dict = {}
    last = 0.0
    for group in ("bones", "morphs", "node"):
        items = tracks.get(group) or {}
        if not items:
            continue
        out_g: dict = {}
        for item, value in items.items():
            if group == "bones":
                out_g[item] = {}
                for kind, rows in value.items():
                    rows2 = [[round(r[0] - start, 3)] + r[1:] for r in rows if r[0] >= start and (end is None or r[0] <= end)]
                    if rows2:
                        out_g[item][kind] = rows2
                        last = max(last, rows2[-1][0])
                if not out_g[item]:
                    del out_g[item]
            else:
                rows2 = [[round(r[0] - start, 3)] + r[1:] for r in value if r[0] >= start and (end is None or r[0] <= end)]
                if rows2:
                    out_g[item] = rows2
                    last = max(last, rows2[-1][0])
        if out_g:
            shifted[group] = out_g
    if not shifted:
        raise ClipError(f"{keys.get('node')} has no keys in that range, so there is nothing to save.")
    folder = user_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{slug(name)}.json"
    if path.exists() and not overwrite:
        raise ClipError(f"A preset named {slug(name)!r} exists. Pass overwrite=true or another name.")
    length = (end - start) if end is not None else last
    data = {"format": FORMAT, "version": 1, "name": slug(name), "description": description,
            "generation": keys.get("generation"), "fps": fps, "frames": round(length, 3), "loop": loop,
            "tracks": shifted}
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    data["path"] = path.as_posix()
    return data


def _rename_map(src_gen: str | None, dst_gen: str | None) -> dict[str, str]:
    def rig(gen: str | None) -> str | None:
        g = (gen or "").lower()
        if "genesis 9" in g:
            return "genesis9"
        if "genesis 8" in g or "genesis 3" in g:
            return "genesis8"
        return None

    a, b = rig(src_gen), rig(dst_gen)
    if not a or not b or a == b:
        return {}
    return {TARGET_RIGS[a][role]: TARGET_RIGS[b][role] for role in TARGET_RIGS[a] if role in TARGET_RIGS[b]}


def clip_tracks(clip: dict, *, start: float, speed: float, repeat: int, generation: str | None,
                in_place: bool, root: str | None) -> tuple[dict, list[str], float]:
    """The tracks to give anim_keys_set, and warnings, and the last frame."""
    if speed <= 0:
        raise ClipError("speed must be above 0.")
    if repeat < 1:
        raise ClipError("repeat must be 1 or more.")
    warnings: list[str] = []
    if clip.get("generation") and generation and clip["generation"] != generation:
        warnings.append(f"The preset was made on {clip['generation']} and the figure is {generation}; bone names "
                        "were translated, but axes can differ. Check it with anim_preview.")
    rename = _rename_map(clip.get("generation"), generation)
    length = float(clip.get("frames") or 0)
    if length <= 0:
        length = max((r[0] for b in (clip["tracks"].get("bones") or {}).values() for rows in b.values() for r in rows),
                     default=0)
    tracks = clip["tracks"]
    # A looping clip with root motion (a walk) carries on from where the last cycle ended.
    travel = [0.0, 0.0, 0.0]
    root_rows = ((tracks.get("bones") or {}).get(root or "") or {}).get("position") if root else None
    if root_rows and clip.get("loop") and not in_place and len(root_rows) > 1:
        a, b = root_rows[0], root_rows[-1]
        travel = [(b[i] or 0) - (a[i] or 0) if i != 1 else 0.0 for i in range(1, 4)]
    out: dict = {}
    last = start

    def frame(f: float, r: int) -> float:
        return round(start + (r * length + f) / speed, 3)

    for r in range(repeat):
        for bone, kinds in (tracks.get("bones") or {}).items():
            name = rename.get(bone, bone)
            for kind, rows in kinds.items():
                dest = out.setdefault("bones", {}).setdefault(name, {}).setdefault(kind, [])
                for row in rows:
                    if r > 0 and row[0] == 0 and clip.get("loop"):
                        continue  # the first key of a loop is the last of the previous cycle
                    vals = list(row[1:])
                    if kind == "position" and name == root:
                        if in_place:
                            vals = [0.0 if i != 1 else v for i, v in enumerate(vals)]
                        else:
                            vals = [(v + travel[i] * r) if v is not None else None for i, v in enumerate(vals)]
                    f = frame(row[0], r)
                    dest.append([f] + vals)
                    last = max(last, f)
        for group in ("morphs", "node"):
            for item, rows in (tracks.get(group) or {}).items():
                dest = out.setdefault(group, {}).setdefault(item, [])
                for row in rows:
                    if r > 0 and row[0] == 0 and clip.get("loop"):
                        continue
                    f = frame(row[0], r)
                    dest.append([f] + list(row[1:]))
                    last = max(last, f)
    return out, warnings, last
