"""Locate and read the canonical skill bundle (skills/ai-product-governance).

The skill folder is the single source of truth. Everything in this package (the MCP
server, the generated integrations, the eval harness) reads it through this module.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

import yaml

SKILL_NAME = "ai-product-governance"
SKILL_DIR_ENV = "AIPG_SKILL_DIR"

_FRONTMATTER = re.compile(r"\A---\r?\n(?P<yaml>.*?)\r?\n---\r?\n(?P<body>.*)\Z", re.DOTALL)
_SECTION = re.compile(
    r"<!-- aipg:begin (?P<name>[\w-]+) -->\r?\n(?P<body>.*?)\r?\n<!-- aipg:end (?P=name) -->",
    re.DOTALL,
)
_MARKER_LINE = re.compile(r"^<!-- aipg:(?:begin|end) [\w-]+ -->\r?\n?", re.MULTILINE)


class SkillError(RuntimeError):
    """The skill bundle is missing or malformed."""


def find_skill_dir() -> Path:
    """Resolve the skill directory: $AIPG_SKILL_DIR, the installed bundle, or the source tree."""
    override = os.environ.get(SKILL_DIR_ENV)
    if override:
        path = Path(override)
        if (path / "SKILL.md").is_file():
            return path
        raise SkillError(f"{SKILL_DIR_ENV}={override} does not contain SKILL.md")
    package_dir = Path(__file__).resolve().parent
    bundled = package_dir / "_bundle" / SKILL_NAME
    if (bundled / "SKILL.md").is_file():
        return bundled
    for parent in package_dir.parents:
        candidate = parent / "skills" / SKILL_NAME
        if (candidate / "SKILL.md").is_file():
            return candidate
    raise SkillError(f"Could not find the {SKILL_NAME} skill. Set {SKILL_DIR_ENV} to its directory.")


def find_repo_root(start: Path | None = None) -> Path:
    """Find the source repository root (only meaningful in a development checkout)."""
    origin = (start or Path(__file__)).resolve()
    for parent in [origin, *origin.parents]:
        if (parent / "pyproject.toml").is_file() and (parent / "skills" / SKILL_NAME).is_dir():
            return parent
    raise SkillError("Not running from a source checkout: no pyproject.toml next to skills/.")


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER.match(text)
    if not match:
        raise SkillError("SKILL.md must start with YAML frontmatter delimited by '---' lines")
    data = yaml.safe_load(match.group("yaml"))
    if not isinstance(data, dict):
        raise SkillError("SKILL.md frontmatter must be a YAML mapping")
    return data, match.group("body")


@dataclass(frozen=True)
class Skill:
    root: Path
    frontmatter: dict[str, Any] = field(repr=False)
    body: str = field(repr=False)

    @property
    def name(self) -> str:
        return str(self.frontmatter.get("name", ""))

    @property
    def description(self) -> str:
        return str(self.frontmatter.get("description", ""))

    @property
    def version(self) -> str:
        metadata = self.frontmatter.get("metadata") or {}
        return str(metadata.get("version", ""))

    @property
    def references_dir(self) -> Path:
        return self.root / "references"

    @property
    def templates_dir(self) -> Path:
        return self.root / "assets" / "templates"

    @property
    def policy_dir(self) -> Path:
        return self.root / "assets" / "policy"

    @property
    def default_policy_path(self) -> Path:
        return self.policy_dir / "default-policy.json"

    @property
    def policy_schema_path(self) -> Path:
        return self.policy_dir / "policy.schema.json"

    @property
    def scripts_dir(self) -> Path:
        return self.root / "scripts"

    @cached_property
    def reference_names(self) -> tuple[str, ...]:
        return tuple(sorted(p.stem for p in self.references_dir.glob("*.md")))

    @cached_property
    def template_names(self) -> tuple[str, ...]:
        return tuple(sorted(p.stem for p in self.templates_dir.glob("*.md")))

    def read_reference(self, name: str) -> str:
        return self._read_named(name, self.reference_names, self.references_dir, "reference")

    def read_template(self, name: str) -> str:
        return self._read_named(name, self.template_names, self.templates_dir, "template")

    def section(self, name: str) -> str:
        """Return the body of an `<!-- aipg:begin name -->` section of SKILL.md."""
        for match in _SECTION.finditer(self.body):
            if match.group("name") == name:
                return match.group("body").strip()
        raise SkillError(f"SKILL.md has no '{name}' section")

    def section_names(self) -> list[str]:
        return [match.group("name") for match in _SECTION.finditer(self.body)]

    @property
    def clean_body(self) -> str:
        """SKILL.md body with the build markers removed, as a model should read it."""
        return _MARKER_LINE.sub("", self.body).strip() + "\n"

    @staticmethod
    def _read_named(name: str, allowed: tuple[str, ...], directory: Path, kind: str) -> str:
        stem = name.removesuffix(".md")
        if stem not in allowed:
            raise KeyError(f"Unknown {kind} '{name}'. Available: {', '.join(allowed)}")
        return (directory / f"{stem}.md").read_text(encoding="utf-8")


def load_skill(root: Path | None = None) -> Skill:
    directory = root or find_skill_dir()
    skill_md = directory / "SKILL.md"
    if not skill_md.is_file():
        raise SkillError(f"{skill_md} not found")
    frontmatter, body = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    return Skill(root=directory, frontmatter=frontmatter, body=body)
