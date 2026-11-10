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
    shadowed_conditionals,
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
    original = (root / "SKILL.md").read_text(encoding="utf-8")
    text = original.replace(f'version: "{skill.version}"', "version: 1.0")
    assert text != original, "the test must turn the version into a number"
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


def _conditional(control: str, when: dict[str, Any]) -> dict[str, Any]:
    return {"control": control, "when": when, "reason": "test"}


def _yes(question: str) -> dict[str, Any]:
    return {"question": question, "equals": True}


def test_conditionals_that_a_tier_already_covers_are_flagged(policy: dict[str, Any], tmp_path: Path) -> None:
    assert shadowed_conditionals(policy) == [], "the default policy has no redundant conditionals"
    policy["conditional_controls"] += [
        _conditional("PRV-01", _yes("personal_data")),
        _conditional("TRN-01", {"any": [_yes("customer_facing"), _yes("external_publication")]}),
        _conditional("PRV-03", {"all": [_yes("third_party_model_provider"), _yes("uses_retrieval")]}),
    ]
    messages = shadowed_conditionals(policy)
    assert len(messages) == 3
    assert messages[0].startswith("conditional control PRV-01 never adds anything: whenever its condition holds, L-03")
    assert "L-01 (limited) or L-02 (limited)" in messages[1], "each branch of an 'any' can be covered by its own rule"
    assert "L-04 (limited)" in messages[2], "one conjunct of an 'all' is enough"
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    assert sum("never adds anything" in f.message for f in check_policy_file(path, "p") if f.level == "warning") == 3


@pytest.mark.parametrize(
    ("control", "when"),
    [
        ("TRN-01", {"any": [_yes("customer_facing"), _yes("takes_actions")]}),  # no rule for takes_actions
        ("EVAL-03", _yes("personal_data")),  # limited, the tier personal data sets, lacks EVAL-03
        ("PRV-01", {"question": "max_financial_impact_per_action", "gte": 500}),  # below H-05's 1000
        ("PRV-01", {"question": "max_financial_impact_per_action", "equals": True}),  # a boolean is not a number
    ],
)
def test_conditionals_that_can_add_a_control_are_not_flagged(
    policy: dict[str, Any], control: str, when: dict[str, Any]
) -> None:
    policy["conditional_controls"].append(_conditional(control, when))
    assert shadowed_conditionals(policy) == []


def test_conditionals_are_not_flagged_when_a_higher_tier_drops_the_control(policy: dict[str, Any]) -> None:
    policy["conditional_controls"].append(_conditional("PRV-01", _yes("personal_data")))
    high = next(t for t in policy["tiers"] if t["id"] == "high")
    high["required_controls"].remove("PRV-01")
    assert shadowed_conditionals(policy) == []


def test_conditionals_implied_through_ranges_and_option_sets_are_flagged(policy: dict[str, Any]) -> None:
    policy["conditional_controls"] += [
        _conditional("EVAL-03", {"question": "max_financial_impact_per_action", "gte": 5000}),
        _conditional("EVAL-03", {"question": "autonomy_level", "equals": "L5"}),
        _conditional("OPS-04", {"question": "prohibited_practices", "contains_any": ["social_scoring"]}),
    ]
    messages = shadowed_conditionals(policy)
    assert [m.split(" never")[0] for m in messages] == ["conditional control EVAL-03"]
    assert "H-05 (high)" in messages[0]
    # L5 alone triggers only L-06 (limited), which lacks EVAL-03. A rule that prohibits the use is not reported.


def test_workspace_policy_overrides_default(risk_engine: Any, repo: Path) -> None:
    example = repo / "examples" / "financial-services"
    path, source = risk_engine.resolve_policy_path(None, cwd=example)
    policy = risk_engine.load_policy(path)
    answers = json.loads((repo / "examples" / "inputs" / "refund-agent.answers.json").read_text(encoding="utf-8"))
    result = risk_engine.classify(policy, answers, policy_source=source)
    assert result["policy"]["id"] == "fs-bank-ai-policy"
    assert "MRM-01" in [c["id"] for c in result["required_controls"]]
    assert "Model risk management" in result["approvers"]


FS_CONTROLS = {"TRN-03", "TPR-01", "OPS-06", "OPS-07"}


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        # A vendor-hosted model that drafts credit decisions for customers needs every financial-services control.
        (
            {"customer_facing": True, "consequential_decisions": True, "external_model_dependency": True},
            FS_CONTROLS,
        ),
        # Back-office decision support with a self-hosted model: reasons and complaints, but no customer comms.
        ({"consequential_decisions": True}, {"TRN-03", "OPS-06"}),
        # Marketing copy from a vendor API: archived like any other external communication.
        ({"external_publication": True, "external_model_dependency": True}, {"TPR-01", "OPS-07"}),
        # An internal summariser on a self-hosted model needs none of them.
        ({"customer_facing": False, "consequential_decisions": False, "external_model_dependency": False}, set()),
    ],
)
def test_financial_services_controls_follow_the_answers(
    risk_engine: Any, repo: Path, answers: dict[str, Any], expected: set[str]
) -> None:
    policy = risk_engine.load_policy(repo / "examples" / "financial-services" / ".ai-governance" / "policy.json")
    result = risk_engine.classify(policy, answers)
    assert FS_CONTROLS & {c["id"] for c in result["required_controls"]} == expected
