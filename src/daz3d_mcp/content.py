"""Finds content (figures, clothing, hair, poses, materials...) in the user's
Daz content libraries.

Searching runs here, in the MCP server, not inside Daz Studio: walking a large
library takes a while and Daz would be frozen meanwhile. Daz only tells us
where the libraries are (content_libraries.dsa). The list of files is cached
in ~/.daz3d-mcp/content-index.json.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from daz3d_mcp.paths import config_dir

INDEX_VERSION = 1
CONTENT_EXTENSIONS = (".duf",)
# Folders that hold data the user never loads directly.
SKIP_DIRS = {"data", "runtime", "__macosx", "documentation", "readme's", "readmes", "scripts", "shaders"}
HEADER_BYTES = 16384
MAX_HEADER_READS = 3000

# What a file is, from the "asset_info.type" field of its .duf header.
KIND_BY_TYPE = {
    "figure": "figure",
    "character": "character",
    "wearable": "clothing",
    "follower": "clothing",
    "prop": "prop",
    "scene": "scene",
    "scene_subset": "scene_subset",
    "preset_pose": "pose",
    "preset_hierarchical_pose": "pose",
    "preset_puppeteer": "pose",
    "preset_material": "material",
    "preset_hierarchical_material": "material",
    "preset_shader": "material",
    "preset_shape": "shape",
    "preset_morph": "shape",
    "preset_properties": "properties",
    "preset_render_settings": "render_preset",
    "preset_environment": "environment",
}
KINDS = sorted(set(KIND_BY_TYPE.values()) | {"hair", "light", "preset", "other"})

_HAIR = re.compile(r"(^|[/ _-])(hair|hairs|brows|eyebrows|lashes|beard|mustache|ponytail|braids?|bangs)([/ _.-]|$)",
                   re.I)
_ASSET_TYPE = re.compile(rb'"asset_info"\s*:\s*\{.*?"type"\s*:\s*"([^"]+)"', re.S)

_GENERATIONS = [
    ("Genesis 9", re.compile(r"genesis\s*9|\bg9(?:[fmh]|\b)", re.I)),
    ("Genesis 8.1", re.compile(r"genesis\s*8[._ ]1|\bg8[._]1", re.I)),
    ("Genesis 8", re.compile(r"genesis\s*8|\bg8(?:[fm]|\b)", re.I)),
    ("Genesis 3", re.compile(r"genesis\s*3|\bg3(?:[fm]|\b)", re.I)),
    ("Genesis 2", re.compile(r"genesis\s*2|\bg2(?:[fm]|\b)", re.I)),
]


def read_asset_type(path: Path) -> str | None:
    """The asset_info.type of a .duf file; works on plain and gzip files."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(2)
        if head == b"\x1f\x8b":
            with gzip.open(path, "rb") as fh:
                data = fh.read(HEADER_BYTES)
        else:
            with open(path, "rb") as fh:
                data = fh.read(HEADER_BYTES)
    except (OSError, EOFError, gzip.BadGzipFile):
        return None
    m = _ASSET_TYPE.search(data)
    return m.group(1).decode("utf-8", "replace") if m else None


def kind_of(relative: str, asset_type: str | None) -> str:
    rel = "/" + relative.replace("\\", "/").lower()
    kind = KIND_BY_TYPE.get(asset_type or "")
    if asset_type and asset_type.startswith("preset_") and kind is None:
        kind = "preset"
    if kind is None:
        # No or unknown header: guess from the folder names.
        if "/poses/" in rel or "/pose/" in rel:
            kind = "pose"
        elif "/materials/" in rel or "/shaders/" in rel:
            kind = "material"
        elif "/characters/" in rel:
            kind = "character"
        elif "/clothing/" in rel or "/wardrobe/" in rel:
            kind = "clothing"
        elif "/hair/" in rel:
            kind = "hair"
        elif "/props/" in rel:
            kind = "prop"
        elif "/environments/" in rel or "/scenes/" in rel:
            kind = "scene"
        elif "light" in rel:
            kind = "light"
        else:
            kind = "other"
    if kind in ("clothing", "figure") and (_HAIR.search(Path(relative).stem) or "/hair/" in rel):
        kind = "hair"
    if kind == "clothing" and "/hair/" in rel:
        kind = "hair"
    if kind == "scene_subset" and "light" in rel:
        kind = "light"
    return kind


def generation_of(relative: str) -> str | None:
    for name, pattern in _GENERATIONS:
        if pattern.search(relative):
            return name
    return None


def thumbnail_of(path: Path) -> Path | None:
    for candidate in (path.with_suffix(".png"), Path(str(path) + ".png"), path.with_suffix(".tip.png"),
                      path.with_suffix(".jpg")):
        if candidate.is_file():
            return candidate
    return None


def _normalize(text: str) -> str:
    return re.sub(r"[\s_\-./\\()\[\]!]+", " ", text.lower()).strip()


@dataclass
class Library:
    path: str
    files: list[str]


class ContentIndex:
    def __init__(self, libraries: list[str], cache_path: Path | None = None, max_age_hours: float = 24.0):
        self.libraries = [str(Path(p)) for p in libraries]
        self.cache_path = cache_path or (config_dir() / "content-index.json")
        self.max_age = max_age_hours * 3600
        self.built_at = 0.0
        self.libs: list[Library] = []
        self.types: dict[str, list] = {}  # abs path -> [mtime, asset_type]
        self._types_dirty = False

    # ------------------------------------------------------------ build --
    def load(self, refresh: bool = False) -> "ContentIndex":
        if not refresh and self._load_cache():
            return self
        self.build()
        return self

    def _load_cache(self) -> bool:
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if data.get("version") != INDEX_VERSION or data.get("libraries") != self.libraries:
            return False
        if time.time() - float(data.get("built_at", 0)) > self.max_age:
            return False
        self.built_at = float(data["built_at"])
        self.libs = [Library(lib["path"], lib["files"]) for lib in data.get("libs", [])]
        self.types = data.get("types", {})
        return True

    def build(self) -> None:
        libs = []
        for root in self.libraries:
            files: list[str] = []
            base = Path(root)
            if base.is_dir():
                for dirpath, dirnames, filenames in os.walk(base):
                    dirnames[:] = sorted(d for d in dirnames
                                         if not d.startswith(".") and d.lower() not in SKIP_DIRS)
                    rel_dir = Path(dirpath).relative_to(base)
                    for name in sorted(filenames):
                        if name.lower().endswith(CONTENT_EXTENSIONS) and not name.startswith("."):
                            files.append((rel_dir / name).as_posix())
            libs.append(Library(root, files))
        self.libs = libs
        self.built_at = time.time()
        self._types_dirty = True
        self.save()

    def save(self) -> None:
        data = {
            "version": INDEX_VERSION,
            "libraries": self.libraries,
            "built_at": self.built_at,
            "libs": [{"path": lib.path, "files": lib.files} for lib in self.libs],
            "types": self.types,
        }
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(self.cache_path)
            self._types_dirty = False
        except OSError:
            pass

    @property
    def file_count(self) -> int:
        return sum(len(lib.files) for lib in self.libs)

    # ------------------------------------------------------------- read --
    def asset_type(self, path: Path) -> str | None:
        key = path.as_posix()
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return None
        cached = self.types.get(key)
        if cached and cached[0] == mtime:
            return cached[1]
        value = read_asset_type(path)
        self.types[key] = [mtime, value]
        self._types_dirty = True
        return value

    def describe(self, library: str, relative: str) -> dict:
        path = Path(library) / relative
        asset_type = self.asset_type(path)
        thumb = thumbnail_of(path)
        return {
            "name": path.stem,
            "kind": kind_of(relative, asset_type),
            "generation": generation_of(relative),
            "path": path.as_posix(),
            "relative": relative,
            "library": Path(library).as_posix(),
            "type": asset_type,
            "thumbnail": thumb.as_posix() if thumb else None,
        }

    def resolve(self, path: str) -> Path | None:
        """An absolute path, or a path relative to one of the libraries."""
        p = Path(path).expanduser()
        if p.is_absolute():
            return p if p.is_file() else None
        for lib in self.libraries:
            candidate = Path(lib) / path
            if candidate.is_file():
                return candidate
        return None

    def kind_for(self, path: Path) -> str:
        relative = path.as_posix()
        for lib in self.libraries:
            try:
                relative = path.relative_to(lib).as_posix()
                break
            except ValueError:
                continue
        return kind_of(relative, self.asset_type(path))

    # ----------------------------------------------------------- search --
    def search(self, query: str = "", kind: str | None = None, generation: str | None = None,
               folder: str | None = None, limit: int = 20, offset: int = 0) -> dict:
        words = _normalize(query).split()
        folder_norm = folder.strip("/").lower() + "/" if folder else None
        gen_want = _normalize(generation) if generation else None

        scored: list[tuple[int, int, int, str, str]] = []
        for lib in self.libs:
            for rel in lib.files:
                if folder_norm and not rel.lower().startswith(folder_norm):
                    continue
                norm = _normalize(rel)
                if words and not all(w in norm for w in words):
                    continue
                stem = _normalize(Path(rel).stem)
                score = sum(3 for w in words if w in stem) + (5 if words and stem == " ".join(words) else 0)
                scored.append((-score, len(stem), len(rel), lib.path, rel))
        scored.sort()

        results = []
        matched = 0
        reads = 0
        more = False
        for *_, lib, rel in scored:
            if gen_want:
                gen = generation_of(rel)
                if not gen or _normalize(gen) != gen_want:
                    continue
            if kind:
                reads += 1
                if reads > MAX_HEADER_READS:
                    more = True
                    break
                item = self.describe(lib, rel)
                if item["kind"] != kind:
                    continue
            else:
                item = None
            matched += 1
            if matched <= offset:
                continue
            if len(results) >= limit:
                more = True
                break
            results.append(item or self.describe(lib, rel))
        if self._types_dirty:
            self.save()
        return {
            "results": results,
            "more": more,
            "next_offset": offset + len(results) if more else None,
            "index": {"files": self.file_count, "libraries": self.libraries,
                      "built": time.strftime("%Y-%m-%d %H:%M", time.localtime(self.built_at))},
        }
