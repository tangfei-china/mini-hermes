from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"
_SLUG_INVALID_CHARS = re.compile(r"[^a-z0-9-]+")
_SLUG_MULTI_HYPHEN = re.compile(r"-{2,}")


@dataclass(frozen=True)
class Skill:
    name: str
    slug: str
    description: str
    path: Path
    directory: Path
    content: str

    def summary(self) -> dict[str, str]:
        return {
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "path": str(self.path),
            "directory": str(self.directory),
        }


@dataclass(frozen=True)
class SkillLoadResult:
    loaded: list[Skill]
    missing: list[str]
    prompt: str


@dataclass(frozen=True)
class SkillMatch:
    skill: Skill
    reason: str


def slugify(value: str) -> str:
    slug = value.strip().lower().replace("_", "-").replace(" ", "-")
    slug = _SLUG_INVALID_CHARS.sub("", slug)
    return _SLUG_MULTI_HYPHEN.sub("-", slug).strip("-")


def parse_skill_markdown(path: Path, text: str) -> Skill:
    frontmatter, body = _split_frontmatter(text)
    name = str(frontmatter.get("name") or path.parent.name).strip()
    description = str(frontmatter.get("description") or _first_body_line(body)).strip()
    return Skill(
        name=name,
        slug=slugify(name),
        description=description,
        path=path,
        directory=path.parent,
        content=body.strip(),
    )


class SkillLoader:
    def __init__(self, root: Path = DEFAULT_SKILLS_DIR) -> None:
        self.root = root

    def list_skills(self) -> list[Skill]:
        if not self.root.exists():
            return []
        skills = []
        seen: set[str] = set()
        for skill_path in sorted(self.root.rglob("SKILL.md")):
            if any(part.startswith(".") for part in skill_path.parts):
                continue
            try:
                skill = parse_skill_markdown(skill_path, skill_path.read_text(encoding="utf-8"))
            except OSError:
                continue
            if not skill.slug or skill.slug in seen:
                continue
            seen.add(skill.slug)
            skills.append(skill)
        return skills

    def load(self, identifiers: list[str] | tuple[str, ...] | None) -> SkillLoadResult:
        requested = _normalize_identifiers(identifiers)
        if not requested:
            return SkillLoadResult([], [], "")

        available = self.list_skills()
        by_key = self._index_skills(available)
        loaded: list[Skill] = []
        missing: list[str] = []
        seen: set[str] = set()

        for identifier in requested:
            key = slugify(identifier)
            skill = by_key.get(key)
            if skill is None:
                missing.append(identifier)
                continue
            if skill.slug in seen:
                continue
            seen.add(skill.slug)
            loaded.append(skill)

        return SkillLoadResult(loaded, missing, build_skills_prompt(loaded))

    def find(self, identifier: str) -> Skill | None:
        key = slugify(identifier)
        return self._index_skills(self.list_skills()).get(key)

    def read_markdown(self, identifier: str) -> str:
        skill = self.find(identifier)
        if skill is None:
            raise ValueError(f"skill not found: {identifier}")
        self._ensure_under_root(skill.path)
        return skill.path.read_text(encoding="utf-8")

    def save_existing(self, identifier: str, markdown: str) -> Skill:
        skill = self.find(identifier)
        if skill is None:
            raise ValueError(f"skill not found: {identifier}")
        self._ensure_under_root(skill.path)
        parsed = parse_skill_markdown(skill.path, markdown)
        if not parsed.slug:
            raise ValueError("skill markdown must include a name")
        skill.path.write_text(markdown, encoding="utf-8")
        return parse_skill_markdown(skill.path, markdown)

    def import_markdown(self, markdown: str) -> Skill:
        parsed = parse_skill_markdown(self.root / "custom" / "draft" / "SKILL.md", markdown)
        if not parsed.slug:
            raise ValueError("skill markdown must include a name")
        skill_dir = self.root / "custom" / parsed.slug
        skill_path = skill_dir / "SKILL.md"
        self._ensure_under_root(skill_path)
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(markdown, encoding="utf-8")
        return parse_skill_markdown(skill_path, markdown)

    def delete(self, identifier: str) -> Path:
        skill = self.find(identifier)
        if skill is None:
            raise ValueError(f"skill not found: {identifier}")
        self._ensure_under_root(skill.path)
        custom_root = (self.root / "custom").resolve()
        skill_dir = skill.directory.resolve()
        if custom_root != skill_dir and custom_root not in skill_dir.parents:
            raise ValueError("only skills under skills/custom can be deleted")
        deleted_path = skill.path
        shutil.rmtree(skill.directory)
        return deleted_path

    def auto_select(self, text: str, limit: int = 2) -> list[SkillMatch]:
        haystack = slugify(text)
        if not haystack:
            return []

        matches: list[SkillMatch] = []
        for skill in self.list_skills():
            if skill.slug in haystack:
                matches.append(SkillMatch(skill, "matched skill slug"))
                continue
            terms = _skill_terms(skill)
            matched_terms = [term for term in terms if term in haystack]
            if matched_terms:
                matches.append(SkillMatch(skill, f"matched {', '.join(matched_terms[:3])}"))

        deduped: list[SkillMatch] = []
        seen: set[str] = set()
        for match in matches:
            if match.skill.slug in seen:
                continue
            seen.add(match.skill.slug)
            deduped.append(match)
            if len(deduped) >= limit:
                break
        return deduped

    def _index_skills(self, skills: list[Skill]) -> dict[str, Skill]:
        indexed: dict[str, Skill] = {}
        for skill in skills:
            indexed[skill.slug] = skill
            indexed[slugify(skill.name)] = skill
            indexed[slugify(skill.directory.name)] = skill
            try:
                rel_parent = skill.directory.relative_to(self.root)
            except ValueError:
                rel_parent = skill.directory
            indexed[slugify(str(rel_parent))] = skill
        return indexed

    def _ensure_under_root(self, path: Path) -> None:
        root = self.root.resolve()
        target = path.resolve()
        if root != target and root not in target.parents:
            raise ValueError(f"skill path escapes skills root: {path}")


def build_skills_prompt(skills: list[Skill]) -> str:
    parts = []
    for skill in skills:
        parts.append(
            "\n".join([
                (
                    f'[IMPORTANT: The user has activated the "{skill.name}" skill '
                    "for this Mini Hermes session. Follow its instructions when "
                    "they are relevant, unless the user overrides them.]"
                ),
                "",
                skill.content,
                "",
                f"[Skill name: {skill.name}]",
                f"[Skill slug: {skill.slug}]",
                f"[Skill directory: {skill.directory}]",
            ])
        )
    return "\n\n".join(parts)


def build_skill_catalog_prompt(skills: list[Skill]) -> str:
    if not skills:
        return ""
    lines = [
        "## Available Skills",
        (
            "You can load specialized instructions with the skill_view tool. "
            "If a skill is relevant to the user's task, call skill_view before "
            "answering or using other tools."
        ),
    ]
    for skill in skills:
        description = f": {skill.description}" if skill.description else ""
        lines.append(f"- {skill.slug}{description}")
    return "\n".join(lines)


def _normalize_identifiers(identifiers: list[str] | tuple[str, ...] | None) -> list[str]:
    if not identifiers:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in identifiers:
        for item in str(raw).split(","):
            value = item.strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
    return normalized


def _skill_terms(skill: Skill) -> list[str]:
    text = " ".join([skill.slug, skill.name, skill.description])
    terms: list[str] = []
    for raw in re.split(r"[^a-zA-Z0-9_\-\u4e00-\u9fff]+", text):
        term = slugify(raw)
        if len(term) >= 4 and term not in terms:
            terms.append(term)
    return terms


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw_frontmatter = text[4:end]
    body = text[end + 5 :]
    return _parse_simple_yaml(raw_frontmatter), body


def _parse_simple_yaml(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip()] = value.strip().strip('"').strip("'")
    return parsed


def _first_body_line(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:120]
    return ""
