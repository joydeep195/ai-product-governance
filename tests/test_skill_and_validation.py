from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from ai_product_governance.policy import policy_problems, schema_errors
from ai_product_governance.skill import Skill, load_skill, parse_frontmatter
from ai_product_governance.validate import (
    check_example_policies,
    check_frontmatter,
    check_links,
    check_policy_file,
    validate_repository,
)
from ai_product_governance.workflows import GATES, WORKFLOWS


def test_repository_validates_cleanly(repo: Path) -> None:
    assert [str(f) for f in validate_repository(repo)] == []


def test_skill_follows_agent_skills_spec(skill: Skill) -> None:
    assert skill.name == skill.root.name == "ai-product-governance"
    assert 1 <= len(skill.description) <= 1024
    assert skill.body.count("\n") < 500


def test_sections_used_by_adapters_exist(skill: Skill) -> None:
    assert {"role", "rules", "policy", "scripts", "output", "scope"} <= set(skill.section_names())
    assert "<!-- aipg:" not in skill.clean_body


def test_every_gate_and_workflow_resolves(skill: Skill) -> None:
    for gate in GATES:
        assert gate.reference in skill.reference_names
        assert gate.template in skill.template_names
    for flow in WORKFLOWS:
        assert flow.template in skill.template_names
        assert all(name in skill.reference_names for name in flow.references)
        assert "{argument}" in flow.task


def test_reading_unknown_or_escaping_names_is_refused(skill: Skill) -> None:
    with pytest.raises(KeyError):
        skill.read_reference("../SKILL")
    with pytest.raises(KeyError):
        skill.read_template("does-not-exist")


def test_default_policy_passes_schema_and_semantics(policy: dict[str, Any]) -> None:
    assert schema_errors(policy) == []
    assert policy_problems(policy) == []


def test_schema_rejects_unknown_keys(policy: dict[str, Any]) -> None:
    policy["tiers"][0]["surprise"] = True
    assert any("surprise" in e for e in schema_errors(policy))


def _copy_skill(skill: Skill, tmp_path: Path) -> Path:
    target = tmp_path / "ai-product-governance"
    shutil.copytree(skill.root, target)
    return target


def test_frontmatter_rules_are_enforced(skill: Skill, tmp_path: Path) -> None:
    root = _copy_skill(skill, tmp_path)
    text = (root / "SKILL.md").read_text(encoding="utf-8").replace("name: ai-product-governance", "name: Wrong_Name")
    (root / "SKILL.md").write_text(text, encoding="utf-8")
    messages = [f.message for f in check_frontmatter(load_skill(root))]
    assert any("lowercase" in m for m in messages)


def test_non_string_metadata_is_flagged(skill: Skill, tmp_path: Path) -> None:
    root = _copy_skill(skill, tmp_path)
    text = (root / "SKILL.md").read_text(encoding="utf-8").replace('version: "1.0.0"', "version: 1.0")
    (root / "SKILL.md").write_text(text, encoding="utf-8")
    assert any("metadata" in f.message for f in check_frontmatter(load_skill(root)))


def test_broken_links_are_detected(skill: Skill, tmp_path: Path) -> None:
    root = _copy_skill(skill, tmp_path)
    with open(root / "SKILL.md", "a", encoding="utf-8") as handle:
        handle.write("\nSee [missing](references/not-here.md) and `assets/templates/ghost.md`.\n")
    findings = [f.message for f in check_links(load_skill(root))]
    assert "broken reference: references/not-here.md" in findings
    assert "broken reference: assets/templates/ghost.md" in findings


def test_parse_frontmatter_requires_delimiters() -> None:
    with pytest.raises(Exception, match="frontmatter"):
        parse_frontmatter("# no frontmatter")


def test_versions_are_consistent(repo: Path, skill: Skill) -> None:
    plugin = json.loads((repo / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    from ai_product_governance import __version__

    assert plugin["version"] == skill.version == __version__


def test_example_organisation_policies_are_valid(repo: Path) -> None:
    assert list((repo / "examples").rglob("policy.json")), "expected at least one example policy"
    assert check_example_policies(repo) == []


def test_policy_that_weakens_a_higher_tier_is_flagged(policy: dict[str, Any], tmp_path: Path) -> None:
    high = next(t for t in policy["tiers"] if t["id"] == "high")
    high["required_controls"].remove("PRV-01")
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    findings = check_policy_file(path, "policy.json")
    assert [f.level for f in findings] == ["warning"]
    assert "drops controls required by lower tier 'limited': PRV-01" in findings[0].message


def test_workspace_policy_overrides_default(risk_engine: Any, repo: Path) -> None:
    example = repo / "examples" / "financial-services"
    path, source = risk_engine.resolve_policy_path(None, cwd=example)
    policy = risk_engine.load_policy(path)
    answers = json.loads((repo / "examples" / "inputs" / "refund-agent.answers.json").read_text(encoding="utf-8"))
    result = risk_engine.classify(policy, answers, policy_source=source)
    assert result["policy"]["id"] == "fs-bank-ai-policy"
    assert "MRM-01" in [c["id"] for c in result["required_controls"]]
    assert "Model risk management" in result["approvers"]
