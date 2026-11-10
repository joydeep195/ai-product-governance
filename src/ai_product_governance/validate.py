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
from typing import Any, Literal

from ai_product_governance import __version__
from ai_product_governance.adapters import PROMPT_PACK_CHAR_LIMIT, prompt_pack_instructions
from ai_product_governance.policy import load_effective_policy, policy_problems
from ai_product_governance.records import check_record, record_workspace
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
    findings += check_example_records(repo)
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


def check_example_records(repo: Path) -> list[Finding]:
    """Example use-case records must keep passing `aipg check` against their workspace policy as both evolve.

    Re-certification is not judged against today's date, so the examples never expire.
    """
    findings: list[Finding] = []
    default_policy = load_skill(repo / "skills" / SKILL_NAME).default_policy_path
    for path in sorted((repo / "examples").rglob("*.json")):
        workspace = record_workspace(path)
        if workspace is None:
            continue
        label = path.relative_to(repo).as_posix()
        workspace_policy = workspace / ".ai-governance" / "policy.json"
        try:
            policy = load_effective_policy(str(workspace_policy if workspace_policy.is_file() else default_policy))
        except ValueError as exc:  # the engine's PolicyError; check_example_policies reports the details
            findings.append(Finding("error", label, f"cannot load the policy: {exc}"))
            continue
        findings += [Finding("error", label, problem) for problem in check_record(path, policy, as_of=None).problems]
    return findings


def check_policy_file(path: Path, label: str) -> list[Finding]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [Finding("error", label, f"invalid JSON: {exc}")]
    findings = [Finding("error", label, problem) for problem in policy_problems(document)]
    if findings:
        return findings
    mapped = any(control.get("mappings") for control in document["controls"])
    if mapped and "frameworks" not in document:
        findings.append(
            Finding(
                "warning",
                label,
                "controls map to frameworks but the policy has no 'frameworks' list: add each framework's official "
                "source and last_verified date so regulatory facts can be stated as of a date",
            )
        )
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
    findings += [Finding("warning", label, message) for message in shadowed_conditionals(document)]
    return findings


def shadowed_conditionals(policy: dict[str, Any]) -> list[str]:
    """Conditional controls that can never add anything, because the tiers already require them.

    A conditional is shadowed when its condition implies a rule whose tier, and every higher non-prohibited tier,
    already requires the control. The check is conservative: it reports only implications it can prove from the
    conditions' structure, so a conditional it does not report may still be shadowed.
    """
    tiers = [t for t in policy["tiers"] if not t.get("prohibited")]
    rank = {t["id"]: t["rank"] for t in tiers}  # rules that set a prohibited tier never shadow anything

    def covered(control: str, tier_id: str) -> bool:
        return all(control in t["required_controls"] for t in tiers if t["rank"] >= rank[tier_id])

    def shadowing_rules(control: str, when: dict[str, Any]) -> list[str] | None:
        if "any" in when:
            found: list[str] = []
            for branch in when["any"]:
                rules = shadowing_rules(control, branch)
                if rules is None:
                    return None
                found += [r for r in rules if r not in found]
            return found
        for rule in policy["rules"]:
            if rank.get(rule["tier"]) is not None and covered(control, rule["tier"]) and _implies(when, rule["when"]):
                return [f"{rule['id']} ({rule['tier']})"]
        return None

    messages = []
    for item in policy.get("conditional_controls", []):
        rules = shadowing_rules(item["control"], item["when"])
        if rules:
            messages.append(
                f"conditional control {item['control']} never adds anything: whenever its condition holds, "
                f"{' or '.join(rules)} sets a tier that already requires it. Remove the conditional, or drop the "
                "control from the tier if it should depend on the condition"
            )
    return messages


def _same(a: Any, b: Any) -> bool:
    # True == 1 in Python, but a boolean answer never satisfies a numeric condition or the reverse.
    return isinstance(a, bool) == isinstance(b, bool) and a == b


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _implies(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """True only if condition `a` holding provably means condition `b` holds."""
    if "any" in a:
        return all(_implies(branch, b) for branch in a["any"])
    if "all" in a and any(_implies(part, b) for part in a["all"]):
        return True
    if "any" in b:
        return any(_implies(a, branch) for branch in b["any"])
    if "all" in b:
        return all(_implies(a, part) for part in b["all"])
    if "all" in a or a.get("question") != b.get("question"):
        return False
    if "equals" in a:
        value = a["equals"]
        if "equals" in b:
            return _same(value, b["equals"])
        if "in" in b:
            return any(_same(value, option) for option in b["in"])
        if "gte" in b:
            return _number(value) and value >= b["gte"]
        if "lte" in b:
            return _number(value) and value <= b["lte"]
        return False
    if "in" in a:
        if "in" in b:
            return all(any(_same(x, y) for y in b["in"]) for x in a["in"])
        if "equals" in b:
            return all(_same(x, b["equals"]) for x in a["in"])
        return False
    if "gte" in a:
        return "gte" in b and a["gte"] >= b["gte"]
    if "lte" in a:
        return "lte" in b and a["lte"] <= b["lte"]
    if "contains_any" in a:
        return "contains_any" in b and set(a["contains_any"]) <= set(b["contains_any"])
    return False


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
