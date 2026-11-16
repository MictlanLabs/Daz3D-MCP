"""Installs content packages bought outside Daz (Renderosity, RuntimeDNA,
CGBytes, Sketchfab, free sites...) into a Daz content library.

Daz's own store installs through Daz Install Manager or Daz Central. Other
stores ship a .zip that the user has to unpack into the right folder by
hand, and the layout inside differs from one vendor to the next:

    Content/data/...  Content/People/...        (Install Manager layout)
    My Library/Props/...                         (wrapped in the library name)
    WesternHat/Runtime/libraries/...             (Poser format)
    data/...  People/...                         (already at the root)
    textures/ + hat.fbx                          (loose meshes, no Daz content)
    parts.zip with more .zip files inside

This module finds the content root inside the archive, installs only that
part, records every file it wrote (so package_uninstall can remove exactly
those) and keeps loose meshes aside for import_mesh.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import shutil
import stat
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

from daz3d_mcp.content import generation_of, kind_of, read_asset_type, thumbnail_of
from daz3d_mcp.paths import config_dir

# Folder names that only appear at the top of a Daz content library.
ROOT_DIRS = {
    "data", "runtime", "people", "props", "environments", "light presets", "lights", "render presets",
    "render settings", "scenes", "scripts", "shader presets", "camera presets", "figures", "animals",
    "architecture", "vehicles", "aniblocks", "animations", "poses", "pose presets", "materials", "presets",
    "documentation", "readme's", "readmes", "scene builder", "wardrobe", "hair", "characters", "clothing",
    "accessories", "general", "my library", "textures",
}
# These are content library roots only when Daz content sits next to them.
WEAK_ROOT_DIRS = {"poses", "materials", "presets", "hair", "characters", "clothing", "accessories",
                  "general", "documentation", "readme's", "readmes", "textures", "scripts", "my library"}
STRONG_ROOT_DIRS = ROOT_DIRS - WEAK_ROOT_DIRS
DAZ_CONTENT_EXT = {".duf", ".dsf", ".dsa", ".dse", ".dsb", ".ds", ".dsx", ".dbz", ".dsd",
                   ".pz2", ".cr2", ".pp2", ".hr2", ".fc2", ".lt2", ".cm2", ".mc6", ".hd2", ".pz3"}
MESH_EXT = {".obj", ".fbx", ".dae", ".abc", ".glb", ".gltf", ".blend", ".stl", ".3ds", ".ply"}
IMPORTABLE_MESH_EXT = {".obj", ".fbx"}  # what Daz Studio imports itself
JUNK = re.compile(r"(^|/)(__macosx|\.ds_store|thumbs\.db|desktop\.ini|\._[^/]*)(/|$)", re.I)
NOT_SUPPORTED = {".rar", ".7z", ".tar", ".gz", ".tgz", ".exe", ".dmg", ".pkg"}

MAX_NESTED_DEPTH = 3


class PackageError(Exception):
    pass


@dataclass
class Entry:
    path: str          # inside the (flattened) archive, posix
    size: int
    open: object       # () -> binary file object
    archive: str       # which archive it came from (for nested zips)


@dataclass
class Plan:
    source: str
    name: str
    root: str | None                     # content root prefix inside the archive ("" = top)
    layout: str                          # daz, poser, meshes, unknown
    content: list[Entry] = field(default_factory=list)   # goes into the library, path relative to root
    meshes: list[Entry] = field(default_factory=list)    # loose meshes (+ their textures)
    extras: list[str] = field(default_factory=list)      # promo images, readmes...
    warnings: list[str] = field(default_factory=list)
    nested: list[str] = field(default_factory=list)


# ------------------------------------------------------------ reading --
def _safe(name: str) -> str | None:
    """Normalizes an archive member name; None when it would escape the folder."""
    name = name.replace("\\", "/")
    if name.startswith("/") or re.match(r"^[a-zA-Z]:", name):
        return None
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return None
    return "/".join(parts)


def _decode_name(info: zipfile.ZipInfo) -> str:
    # Old Windows zips store names in cp437 without the UTF-8 flag; many are really cp1252/utf-8.
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


def _entries(source: Path, tmp: Path, warnings: list[str], nested: list[str], depth: int = 0,
             prefix: str = "", max_bytes: int = 0) -> list[Entry]:
    out: list[Entry] = []
    if source.is_dir():
        for dirpath, dirnames, filenames in os.walk(source):
            dirnames.sort()
            for fname in sorted(filenames):
                full = Path(dirpath) / fname
                rel = full.relative_to(source).as_posix()
                if JUNK.search(rel) or full.is_symlink():
                    continue
                if rel.lower().endswith(".zip") and depth < MAX_NESTED_DEPTH:
                    nested.append(rel)
                    out += _entries(full, tmp, warnings, nested, depth + 1, prefix, max_bytes)
                    continue
                out.append(Entry(rel, full.stat().st_size, (lambda f=full: open(f, "rb")), str(source)))
        return out

    try:
        zf = zipfile.ZipFile(source)
    except zipfile.BadZipFile as exc:
        raise PackageError(f"{source.name} is not a valid .zip file ({exc}).") from exc
    total = sum(i.file_size for i in zf.infolist())
    if max_bytes and total > max_bytes:
        raise PackageError(f"{source.name} unpacks to {total / 1e9:.1f} GB, more than the "
                           f"{max_bytes / 1e9:.0f} GB limit (max_package_gb in settings.json).")
    for info in zf.infolist():
        if info.is_dir():
            continue
        mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(mode):
            warnings.append(f"Skipped symbolic link {info.filename}.")
            continue
        name = _safe(_decode_name(info))
        if name is None:
            warnings.append(f"Skipped unsafe path {info.filename}.")
            continue
        if JUNK.search(name):
            continue
        if info.flag_bits & 0x1:
            raise PackageError(f"{source.name} is password protected; unpack it by hand first.")
        if name.lower().endswith(".zip") and depth < MAX_NESTED_DEPTH:
            nested.append(name)
            inner = tmp / f"nested-{len(nested)}.zip"
            with zf.open(info) as src, open(inner, "wb") as dst:
                shutil.copyfileobj(src, dst)
            out += _entries(inner, tmp, warnings, nested, depth + 1, prefix, max_bytes)
            continue
        out.append(Entry(name, info.file_size, (lambda z=zf, i=info: z.open(i)), str(source)))
    return out


# ------------------------------------------------------------ layout ---
def _root_index(parts: list[str]) -> int | None:
    """Index of the first folder that starts a Daz library, in a file path."""
    for i, part in enumerate(parts[:-1]):
        if part.lower() in STRONG_ROOT_DIRS:
            return i
    return None


def _find_root(entries: list[Entry]) -> str | None:
    """The prefix (folders above the library root) most Daz files share."""
    votes: dict[str, int] = {}
    for e in entries:
        ext = PurePosixPath(e.path).suffix.lower()
        parts = e.path.split("/")
        idx = _root_index(parts)
        if idx is None:
            continue
        weight = 3 if ext in DAZ_CONTENT_EXT else 1
        prefix = "/".join(parts[:idx])
        votes[prefix] = votes.get(prefix, 0) + weight
    if not votes:
        return None
    # The shortest prefix wins a tie: "Content" over "Content/People/Old".
    return sorted(votes.items(), key=lambda kv: (-kv[1], len(kv[0])))[0][0]


def plan_package(source: Path, tmp: Path, max_bytes: int = 0) -> Plan:
    if not source.exists():
        raise PackageError(f"{source} does not exist.")
    ext = source.suffix.lower()
    if source.is_file() and ext != ".zip":
        if ext in NOT_SUPPORTED:
            raise PackageError(f"{source.name}: {ext} archives are not supported yet. Unpack it (double click "
                               "in Finder or Explorer) and pass the folder instead.")
        raise PackageError(f"{source.name} is not a .zip file or a folder.")
    warnings: list[str] = []
    nested: list[str] = []
    entries = _entries(source, tmp, warnings, nested, max_bytes=max_bytes)
    name = re.sub(r"[_\s]+", " ", source.stem if source.is_file() else source.name).strip()
    plan = Plan(source=str(source), name=name, root=None, layout="unknown", warnings=warnings, nested=nested)
    if not entries:
        raise PackageError(f"{source.name} is empty.")

    root = _find_root(entries)
    plan.root = root
    has_mesh = any(PurePosixPath(e.path).suffix.lower() in MESH_EXT for e in entries)
    if root is None:
        # No Daz content: a model download. Keep everything together so the
        # textures that the .mtl or .fbx points to stay where it expects them.
        if has_mesh:
            plan.meshes = entries
            plan.layout = "meshes"
        else:
            plan.extras = [e.path for e in entries]
            plan.warnings.append("No Daz content folders (data, People, Props, Runtime...) and no 3D meshes "
                                 "were found. Look at the files and install by hand if needed.")
        return plan

    mesh_dirs: set[str] = set()
    for e in entries:
        if PurePosixPath(e.path).suffix.lower() in MESH_EXT:
            mesh_dirs.add(str(PurePosixPath(e.path).parent))
    for e in entries:
        p = e.path
        in_root = root is not None and (root == "" or p.startswith(root + "/"))
        rel = p[len(root) + 1:] if in_root and root else p
        if in_root and _root_index(rel.split("/")) == 0:
            plan.content.append(Entry(rel, e.size, e.open, e.archive))
            continue
        suffix = PurePosixPath(p).suffix.lower()
        parent = str(PurePosixPath(p).parent)
        if suffix in MESH_EXT or any(parent == d or parent.startswith(d + "/") for d in mesh_dirs):
            plan.meshes.append(e)
        else:
            plan.extras.append(p)

    rels = [e.path.lower() for e in plan.content]
    if any(r.startswith("runtime/") for r in rels) and not any(r.endswith(".duf") for r in rels):
        plan.layout = "poser"
    elif plan.content:
        plan.layout = "daz"
    elif plan.meshes:
        plan.layout = "meshes"
    if plan.layout in ("daz", "poser") and not any(r.endswith((".duf", ".dsf", ".pz2", ".cr2", ".pp2", ".hr2"))
                                                   for r in rels):
        plan.warnings.append("The package has Daz folders but no loadable files (.duf, .pz2, .cr2...); it may "
                             "be only textures or an add-on for another product.")
    return plan


# -------------------------------------------------------- describing ----
def _user_facing(rel: str) -> bool:
    low = rel.lower()
    if not low.endswith(".duf"):
        return low.endswith((".pz2", ".cr2", ".pp2", ".hr2", ".lt2", ".cm2", ".mc6")) and "runtime/libraries/" in low
    first = low.split("/")[0]
    return first not in ("data", "runtime", "documentation", "readme's", "readmes", "scripts")


def describe_item(library: Path, rel: str) -> dict:
    path = library / rel
    asset_type = read_asset_type(path) if path.suffix.lower() == ".duf" and path.is_file() else None
    kind = kind_of(rel, asset_type) if path.suffix.lower() == ".duf" else "poser"
    thumb = thumbnail_of(path) if path.exists() else None
    return {"name": path.stem, "kind": kind, "generation": generation_of(rel), "path": path.as_posix(),
            "relative": rel, "type": asset_type, "thumbnail": thumb.as_posix() if thumb else None}


def summarize(plan: Plan, max_items: int = 60) -> dict:
    loadable = [e.path for e in plan.content if _user_facing(e.path)]
    importable = [e.path for e in plan.meshes if PurePosixPath(e.path).suffix.lower() in IMPORTABLE_MESH_EXT]
    other_meshes = [e.path for e in plan.meshes
                    if PurePosixPath(e.path).suffix.lower() in MESH_EXT - IMPORTABLE_MESH_EXT]
    folders = sorted({e.path.split("/")[0] for e in plan.content})
    out = {
        "name": plan.name,
        "source": plan.source,
        "layout": plan.layout,
        "content_root": plan.root if plan.root is not None else None,
        "library_folders": folders,
        "files": len(plan.content),
        "bytes": sum(e.size for e in plan.content) + sum(e.size for e in plan.meshes),
        "loadable": loadable[:max_items],
        "loadable_total": len(loadable),
        "meshes": importable,
        "other_meshes": other_meshes,
        "extras": plan.extras[:20],
        "nested_archives": plan.nested,
        "warnings": list(plan.warnings),
    }
    if other_meshes:
        out["warnings"].append("Daz Studio imports only .obj and .fbx; convert " +
                               ", ".join(PurePosixPath(m).suffix for m in sorted(set(other_meshes))) +
                               " files first (for example with Blender).")
    return out


# ------------------------------------------------------- requirements --
# Add-ons (morph packs, presets, characters) only work on top of another
# product: a base figure, a body morph pack, an outfit. Their .duf/.dsf files
# name the files of that product by library path; when none of the user's
# libraries has them, Daz loads the add-on with "missing files" and it does
# nothing. These are the base products every Genesis add-on points to.
BASE_PRODUCTS = {
    "data/daz 3d/genesis 9/base": "Genesis 9",
    "data/daz 3d/genesis 8/female 8_1": "Genesis 8.1 Female",
    "data/daz 3d/genesis 8/male 8_1": "Genesis 8.1 Male",
    "data/daz 3d/genesis 8/female": "Genesis 8 Female",
    "data/daz 3d/genesis 8/male": "Genesis 8 Male",
    "data/daz 3d/genesis 3/female": "Genesis 3 Female",
    "data/daz 3d/genesis 3/male": "Genesis 3 Male",
    "data/daz 3d/genesis 2/female": "Genesis 2 Female",
    "data/daz 3d/genesis 2/male": "Genesis 2 Male",
}
_REF = re.compile(rb'"(/(?:data|people|props|environments|runtime)/[^"#?]+?\.(?:dsf|duf))[#?"]', re.I)
# Presets dial morphs by property name ("name://@selection#BL_Pointy:?value"),
# not by file: the morph is a .dsf of that name in some library's data folder.
# Only dials set away from zero count: presets and animations saved with every
# dial the author had keep the ones they do not use at 0, and Daz skips those.
_DIAL = re.compile(rb'"name://@selection#([^":/?]+):\?value/value"\s*,\s*"keys"\s*:\s*\[(.{0,400}?)\]\s*\}',
                   re.I | re.S)
# the value of each [time, value, (interpolation)] key
_KEY_VALUE = re.compile(rb"\[\s*-?[\d.eE+-]+\s*,\s*(-?[\d.]+(?:[eE][+-]?\d+)?)")
_ID = re.compile(rb'"id"\s*:\s*"([^"]+)"')
MIN_DIAL_FAMILY = 3            # unknown morphs sharing a prefix before they are reported
MAX_DIAL_FAMILIES = 5
REF_SCAN_BYTES = 8 << 20      # read at most this much of one file
REF_SCAN_FILES = 4000         # and at most this many files of a package


def _read_text(entry: Entry) -> bytes:
    with entry.open() as fh:  # type: ignore[operator]
        data = fh.read(REF_SCAN_BYTES)
    if data[:2] == b"\x1f\x8b":
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:
                data = gz.read(REF_SCAN_BYTES)
        except (OSError, EOFError):
            return b""
    return data


def _product_of(rel: str) -> tuple[str, str]:
    """(folder, name) of the product a library file belongs to."""
    parts = rel.split("/")
    low = [p.lower() for p in parts]
    for key, name in BASE_PRODUCTS.items():
        k = key.split("/")
        if low[:len(k)] == k and (len(low) == len(k) + 1 or low[len(k)] != "morphs"):
            return "/".join(parts[:len(k)]), name
    if "morphs" in low:
        # .../Morphs/<Vendor>/<Product>/file.dsf
        i = low.index("morphs")
        folder = parts[:min(i + 3, len(parts) - 1)]
    else:
        folder = parts[:min(4, len(parts) - 1)]
    return "/".join(folder), folder[-1] if folder else rel


def references(plan: Plan, dials: dict[str, dict] | None = None, ids: set[str] | None = None) -> dict[str, dict]:
    """Library files the package's .duf/.dsf files point to: {lower path: {path, by}}.
    dials collects the morph properties its presets set by name; ids the ids its files define."""
    refs: dict[str, dict] = {}
    scanned = 0
    for e in plan.content:
        if not e.path.lower().endswith((".duf", ".dsf")):
            continue
        if scanned >= REF_SCAN_FILES:
            break
        scanned += 1
        try:
            data = _read_text(e)
        except OSError:
            continue
        for m in _REF.finditer(data):
            rel = unquote(m.group(1).decode("utf-8", "replace")).lstrip("/")
            key = rel.lower()
            ref = refs.setdefault(key, {"path": rel, "by": []})
            if len(ref["by"]) < 3 and e.path not in ref["by"]:
                ref["by"].append(e.path)
        if dials is not None:
            for m in _DIAL.finditer(data):
                # keys: [[time, value], ...]; every second number is a value
                values = [float(v) for v in _KEY_VALUE.findall(m.group(2))]
                if not any(abs(v) > 1e-4 for v in values):
                    continue
                name = unquote(m.group(1).decode("utf-8", "replace"))
                dial = dials.setdefault(name.lower(), {"name": name, "by": []})
                if len(dial["by"]) < 3 and e.path not in dial["by"]:
                    dial["by"].append(e.path)
        if ids is not None and e.path.lower().endswith(".dsf"):
            ids.update(unquote(m.group(1).decode("utf-8", "replace")).lower() for m in _ID.finditer(data))
    return refs


def _morph_names(libraries: list[Path]) -> set[str]:
    """Lower-case names of every .dsf in the libraries' data folders."""
    names: set[str] = set()
    for lib in libraries:
        for dirpath, _dirs, files in os.walk(lib / "data"):
            names.update(f[:-4].lower() for f in files if f.lower().endswith(".dsf"))
    return names


def _exists_in(libraries: list[Path], rel: str) -> bool:
    for lib in libraries:
        try:
            if (lib / rel).is_file():
                return True
        except OSError:
            continue
    return False


def missing_requirements(plan: Plan, libraries: list[Path]) -> list[dict]:
    """Products the package needs that neither the package nor the libraries have."""
    shipped = {e.path.lower() for e in plan.content}
    shipped_dirs = {str(PurePosixPath(p).parent) for p in shipped}
    shipped_tops = {"/".join(p.split("/")[:4]) for p in shipped if not p.startswith("data/")}
    products: dict[str, dict] = {}
    dials: dict[str, dict] = {}
    ids: set[str] = set()
    for key, ref in references(plan, dials, ids).items():
        if key in shipped:
            continue
        parent = PurePosixPath(key).parent
        # A file of the package's own folder that it forgot, or a name with a
        # slash in it ("Glans R/L.dsf"): not another product.
        if str(parent) in shipped_dirs or str(parent.parent) in shipped_dirs:
            continue
        # A user-facing file (People/..., Props/...) in the package's own vendor folder.
        if not key.startswith("data/") and "/".join(key.split("/")[:4]) in shipped_tops:
            continue
        if _exists_in(libraries, ref["path"]):
            continue
        folder, name = _product_of(ref["path"])
        p = products.setdefault(folder.lower(), {"product": name, "folder": folder, "base_figure":
                                                 folder.lower() in BASE_PRODUCTS, "missing_files": 0,
                                                 "examples": [], "needed_by": []})
        p["missing_files"] += 1
        if len(p["examples"]) < 3:
            p["examples"].append(ref["path"])
        for by in ref["by"]:
            if len(p["needed_by"]) < 3 and by not in p["needed_by"]:
                p["needed_by"].append(by)
    shipped_names = {PurePosixPath(p).stem for p in shipped if p.endswith(".dsf")}
    unknown = [d for k, d in dials.items() if k not in shipped_names and k not in ids]
    if unknown:
        known = _morph_names(libraries)
        groups: dict[str, dict] = {}
        for d in unknown:
            if d["name"].lower() in known:
                continue
            # The morphs of one product share a prefix ("BL_" for Breastacular).
            prefix = re.split(r"[_\s-]", d["name"], maxsplit=1)[0]
            p = groups.setdefault(prefix.lower(), {
                "product": f"morphs named {prefix}...", "folder": None, "base_figure": False,
                "missing_files": 0, "examples": [], "needed_by": [], "morphs": True})
            p["missing_files"] += 1
            if len(p["examples"]) < 3:
                p["examples"].append(d["name"])
            for by in d["by"]:
                if len(p["needed_by"]) < 3 and by not in p["needed_by"]:
                    p["needed_by"].append(by)
        # A property name is not always its file name: a lone unknown dial is
        # more likely that than a missing product, so only families count.
        families = sorted((g for g in groups.values() if g["missing_files"] >= MIN_DIAL_FAMILY),
                          key=lambda g: -g["missing_files"])
        for g in families[:MAX_DIAL_FAMILIES]:
            products["dials:" + g["product"].lower()] = g
    return sorted(products.values(), key=lambda p: (not p["base_figure"], -p["missing_files"], p["folder"] or ""))


def requirement_warnings(missing: list[dict]) -> list[str]:
    out = []
    for p in missing:
        if p.get("morphs"):
            out.append(f"Its presets set {p['missing_files']} morph(s) that are not installed, e.g. "
                       f"{', '.join(p['examples'])}: they belong to another product (a body morph pack; the "
                       "package name or readme usually says which). Install it first, or the presets do nothing.")
            continue
        what = "the base figure" if p["base_figure"] else "the product"
        out.append(f"Needs {what} {p['product']!r} ({p['folder']}), which is not installed: "
                   f"{p['missing_files']} file(s) it uses are missing, e.g. {p['examples'][0]}. "
                   f"Install {p['product']} first, or its items load without effect or with a "
                   "'missing files' dialog.")
    return out


# ------------------------------------------------------------ install --
def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "package"


def packages_dir() -> Path:
    return config_dir() / "packages"


def imports_dir() -> Path:
    return config_dir() / "imports"


def _same_file(path: Path, entry: Entry) -> bool:
    try:
        if path.stat().st_size != entry.size:
            return False
    except OSError:
        return False
    h1, h2 = hashlib.sha1(), hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h1.update(chunk)
    with entry.open() as fh:  # type: ignore[operator]
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h2.update(chunk)
    return h1.digest() == h2.digest()


def _copy(entry: Entry, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".dazmcp-part")
    with entry.open() as src, open(tmp, "wb") as dst:  # type: ignore[operator]
        shutil.copyfileobj(src, dst, 1 << 20)
    tmp.replace(dest)


def install(source: Path, library: Path, overwrite: bool = False, max_bytes: int = 0,
            name: str | None = None, libraries: list[Path] | None = None) -> dict:
    """Installs a package. Returns the summary, what was written and the new items."""
    library = library.expanduser()
    # ignore_cleanup_errors: on Windows a nested .zip can still be open when it is removed
    with tempfile.TemporaryDirectory(prefix="dazmcp-pkg-", ignore_cleanup_errors=True) as tmpdir:
        plan = plan_package(source, Path(tmpdir), max_bytes)
        summary = summarize(plan)
        requires = missing_requirements(plan, list(libraries or []) + [library])
        if plan.layout == "unknown":
            raise PackageError("Nothing to install: " + " ".join(plan.warnings))
        slug = _slug(name or plan.name)
        manifest_path = packages_dir() / f"{slug}.json"
        previous = json.loads(manifest_path.read_text("utf-8")) if manifest_path.is_file() else None

        conflicts, same, todo = [], [], []
        for e in plan.content:
            dest = library / e.path
            if dest.exists():
                if _same_file(dest, e):
                    same.append(e.path)
                    continue
                owned = previous and e.path in previous.get("files", []) and previous.get("library") == str(library)
                if not overwrite and not owned:
                    conflicts.append(e.path)
                    continue
            todo.append(e)
        if conflicts:
            raise PackageError(
                f"{len(conflicts)} files already exist in {library} with different contents (another package or "
                f"version installed them), e.g. {', '.join(conflicts[:5])}. Pass overwrite=true to replace them.")

        written = []
        for e in todo:
            _copy(e, library / e.path)
            written.append(e.path)

        mesh_root = imports_dir() / slug
        mesh_files = []
        if plan.meshes:
            # Keep the folder structure, so .mtl files and textures next to a mesh still resolve.
            common = os.path.commonpath([str(PurePosixPath(e.path).parent) for e in plan.meshes]) if len(
                plan.meshes) > 1 else str(PurePosixPath(plan.meshes[0].path).parent)
            common = "" if common in (".", "") else common
            for e in plan.meshes:
                rel = e.path[len(common) + 1:] if common else e.path
                _copy(e, mesh_root / rel)
                mesh_files.append(rel)

        files = sorted(set((previous or {}).get("files", []) if previous and previous.get("library") == str(library)
                           else []) | set(written) | set(same))
        manifest = {
            "name": plan.name,
            "slug": slug,
            "source": str(source),
            "library": str(library),
            "installed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "layout": plan.layout,
            "files": files,
            "written": written,
            "meshes_dir": str(mesh_root) if mesh_files else None,
            "meshes": mesh_files,
        }
        packages_dir().mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    items = [describe_item(library, rel) for rel in files if _user_facing(rel)]
    meshes = [(mesh_root / m).as_posix() for m in mesh_files
              if PurePosixPath(m).suffix.lower() in IMPORTABLE_MESH_EXT]
    return {
        "package": slug,
        "name": plan.name,
        "library": library.as_posix(),
        "layout": plan.layout,
        "installed_files": len(written),
        "already_there": len(same),
        "items": items[:80],
        "items_total": len(items),
        "meshes": meshes,
        "requires": requires,
        "warnings": requirement_warnings(requires) + summary["warnings"],
    }


def list_packages() -> list[dict]:
    out = []
    folder = packages_dir()
    if not folder.is_dir():
        return out
    for f in sorted(folder.glob("*.json")):
        try:
            m = json.loads(f.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append({"package": m.get("slug", f.stem), "name": m.get("name"), "library": m.get("library"),
                    "installed_at": m.get("installed_at"), "files": len(m.get("files", [])),
                    "meshes_dir": m.get("meshes_dir"), "source": m.get("source")})
    return out


def uninstall(slug: str) -> dict:
    path = packages_dir() / f"{_slug(slug)}.json"
    if not path.is_file():
        names = [p["package"] for p in list_packages()]
        raise PackageError(f"No installed package {slug!r}. Installed: {', '.join(names) or 'none'}.")
    m = json.loads(path.read_text("utf-8"))
    library = Path(m["library"])
    # Files other packages also list stay: they share them.
    shared: set[str] = set()
    for other in packages_dir().glob("*.json"):
        if other == path:
            continue
        try:
            o = json.loads(other.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if o.get("library") == m["library"]:
            shared |= set(o.get("files", []))
    removed, kept = 0, []
    dirs: set[Path] = set()
    for rel in m.get("files", []):
        if rel in shared:
            kept.append(rel)
            continue
        f = library / rel
        try:
            f.unlink()
            removed += 1
        except FileNotFoundError:
            pass
        d = f.parent
        while d != library and library in d.parents:
            dirs.add(d)
            d = d.parent
    for d in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
        try:
            d.rmdir()
        except OSError:
            pass
    if m.get("meshes_dir"):
        shutil.rmtree(m["meshes_dir"], ignore_errors=True)
    path.unlink()
    return {"package": m.get("slug"), "removed_files": removed, "kept_shared": len(kept), "library": m["library"]}
