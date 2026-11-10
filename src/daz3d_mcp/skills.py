"""Reads the SKILL.md files shipped with the package."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from daz3d_mcp.paths import skills_dir


@dataclass
class Skill:
    name: str
    description: str
    path: Path  # folder that holds SKILL.md

    @property
    def text(self) -> str:
        return (self.path / "SKILL.md").read_text(encoding="utf-8")

    @property
    def body(self) -> str:
        """SKILL.md without its frontmatter."""
        return split_frontmatter(self.text)[1]


def split_frontmatter(text: str) -> tuple[dict, str]:
    meta: dict[str, str] = {}
    if not text.startswith("---"):
        return meta, text
    end = text.find("\n---", 3)
    if end < 0:
        return meta, text
    for line in text[3:end].strip().splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta, text[end + 4 :].lstrip("\n")


def list_skills() -> list[Skill]:
    skills = []
    for folder in sorted(p for p in skills_dir().iterdir() if (p / "SKILL.md").is_file()):
        meta, _ = split_frontmatter((folder / "SKILL.md").read_text(encoding="utf-8"))
        skills.append(Skill(meta.get("name", folder.name), meta.get("description", ""), folder))
    return skills


def get_skill(name: str) -> Skill | None:
    for skill in list_skills():
        if skill.name == name or skill.path.name == name:
            return skill
    return None
