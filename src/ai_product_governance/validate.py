"""Repository validation: Agent Skills spec compliance, links, policy, versions, budgets.

Run with `aipg validate`. CI runs it with --strict so warnings also fail the build.
"""

from __future__ import annotations

import itertools
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ai_product_governance import __version__
from ai_product_governance.adapters import PROMPT_PACK_CHAR_LIMIT, prompt_pack_instructions
from ai_product_governance.policy import policy_problems
from ai_product_governance.skill import SKILL_NAME, Skill, SkillError, load_skill
from ai_product_governance.workflows import GATES, WORKFLOWS

# https://agentskills.io/specification
SPEC_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_SKILL_LINES = 500
MAX_SKILL_TOKENS = 5000  # spec recommendation for the SKILL.md body
_LINK = re.compile(r"\]\((?!https?://|#|mailto:)([^)\s]+)\)")
_CODE_PATH = re.compile(r"`((?:references|assets|scripts)/[^`\s]+)`")


@dataclass(frozen=True)
class Finding:
    level: Literal["error", "warning"]
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():7} {self.where}: {self.message}"


def validate_repository(repo: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        skill = load_skill(repo / "skills" / SKILL_NAME)
    except SkillError as exc:
        return [Finding("error", "SKILL.md", str(exc))]
    findings += check_frontmatter(skill)
    findings += check_budget(skill)
    findings += check_links(skill)
    findings += check_policy(skill)
    findings += check_example_policies(repo)
    findings += check_lifecycle_consistency(skill)
    findings += check_versions(repo, skill)
    findings += check_prompt_pack(skill)
    return findings


def check_frontmatter(skill: Skill) -> list[Finding]:
    findings = []
    fm = skill.frontmatter
    where = "SKILL.md frontmatter"
    name = fm.get("name")
    if not isinstance(name, str) or not 1 <= len(name) <= 64 or not NAME_PATTERN.match(name):
        findings.append(Finding("error", where, "name must be 1-64 lowercase letters, digits and single hyphens"))
    elif name != skill.root.name:
        findings.append(Finding("error", where, f"name '{name}' must match the directory name '{skill.root.name}'"))
    description = fm.get("description")
    if not isinstance(description, str) or not 1 <= len(description) <= 1024:
        findings.append(Finding("error", where, "description must be 1-1024 characters"))
    compatibility = fm.get("compatibility")
    if compatibility is not None and (not isinstance(compatibility, str) or not 1 <= len(compatibility) <= 500):
        findings.append(Finding("error", where, "compatibility must be 1-500 characters"))
    metadata = fm.get("metadata")
    if metadata is not None and (
        not isinstance(metadata, dict)
        or not all(isinstance(k, str) and isinstance(v, str) for k, v in metadata.items())
    ):
        findings.append(Finding("error", where, "metadata must map strings to strings (quote numbers)"))
    for key in sorted(set(fm) - SPEC_FIELDS):
        findings.append(
            Finding("warning", where, f"'{key}' is not an Agent Skills spec field; some tools may reject it")
        )
    return findings


def check_budget(skill: Skill) -> list[Finding]:
    findings = []
    lines = skill.body.count("\n") + 1
    if lines > MAX_SKILL_LINES:
        findings.append(Finding("error", "SKILL.md", f"body has {lines} lines; the spec recommends at most 500"))
    approx_tokens = len(skill.clean_body) // 4
    if approx_tokens > MAX_SKILL_TOKENS:
        findings.append(Finding("warning", "SKILL.md", f"body is ~{approx_tokens} tokens; keep it under 5,000"))
    return findings


def check_links(skill: Skill) -> list[Finding]:
    """Every relative link or path mentioned in SKILL.md and the references must exist."""
    findings = []
    documents = [skill.root / "SKILL.md", *sorted(skill.references_dir.glob("*.md"))]
    for document in documents:
        text = document.read_text(encoding="utf-8")
        targets = set(_LINK.findall(text)) | set(_CODE_PATH.findall(text))
        for target in sorted(targets):
            clean = target.split("#", 1)[0]
            if "<" in clean or "*" in clean:
                continue  # placeholders such as references/<name>.md
            base = skill.root if clean.startswith(("references/", "assets/", "scripts/")) else document.parent
            if not (base / clean).exists():
                where = document.relative_to(skill.root).as_posix()
                findings.append(Finding("error", where, f"broken reference: {target}"))
    return findings


def check_policy(skill: Skill) -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(skill.policy_dir.glob("*-policy.json")):
        findings += check_policy_file(path, path.name)
    return findings


def check_example_policies(repo: Path) -> list[Finding]:
    """Example organisation policies in examples/ must stay valid as the schema evolves."""
    findings: list[Finding] = []
    for path in sorted((repo / "examples").rglob("policy.json")):
        findings += check_policy_file(path, path.relative_to(repo).as_posix())
    return findings


def check_policy_file(path: Path, label: str) -> list[Finding]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [Finding("error", label, f"invalid JSON: {exc}")]
    findings = [Finding("error", label, problem) for problem in policy_problems(document)]
    if findings:
        return findings
    tiers = sorted((t for t in document["tiers"] if not t.get("prohibited")), key=lambda t: t["rank"])
    for lower, higher in itertools.pairwise(tiers):
        missing = set(lower["required_controls"]) - set(higher["required_controls"])
        if missing:
            findings.append(
                Finding(
                    "warning",
                    label,
                    f"tier '{higher['id']}' drops controls required by lower tier '{lower['id']}': "
                    + ", ".join(sorted(missing)),
                )
            )
    return findings


def check_lifecycle_consistency(skill: Skill) -> list[Finding]:
    """SKILL.md's lifecycle table must reference every gate playbook and template declared in workflows.py."""
    findings = []
    for gate in GATES:
        for path in (f"references/{gate.reference}.md", f"assets/templates/{gate.template}.md"):
            if path not in skill.body:
                findings.append(Finding("error", "SKILL.md", f"lifecycle table does not reference {path} ({gate.id})"))
    for flow in WORKFLOWS:
        for name in flow.references:
            if name not in skill.reference_names:
                findings.append(Finding("error", "workflows.py", f"{flow.id} uses unknown reference '{name}'"))
        if flow.template not in skill.template_names:
            findings.append(Finding("error", "workflows.py", f"{flow.id} uses unknown template '{flow.template}'"))
    return findings


def check_versions(repo: Path, skill: Skill) -> list[Finding]:
    """The package, skill, plugin manifest and marketplace entry must carry the same version."""
    versions = {"src/ai_product_governance/__init__.py": __version__, "SKILL.md metadata.version": skill.version}
    plugin = repo / ".claude-plugin" / "plugin.json"
    if plugin.is_file():
        versions[".claude-plugin/plugin.json"] = json.loads(plugin.read_text(encoding="utf-8")).get("version", "")
    pyproject = repo / "pyproject.toml"
    if pyproject.is_file():
        project = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {})
        if "version" in project:
            versions["pyproject.toml"] = project["version"]
    if len(set(versions.values())) > 1:
        detail = ", ".join(f"{where}={version or '(missing)'}" for where, version in versions.items())
        return [Finding("error", "versions", f"versions disagree: {detail}")]
    return []


def check_prompt_pack(skill: Skill) -> list[Finding]:
    size = len(prompt_pack_instructions(skill))
    if size > PROMPT_PACK_CHAR_LIMIT:
        return [
            Finding(
                "error",
                "prompt-pack/instructions.md",
                f"{size} characters; custom GPT and Copilot Studio instructions allow {PROMPT_PACK_CHAR_LIMIT}",
            )
        ]
    return []
