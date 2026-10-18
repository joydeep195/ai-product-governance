from __future__ import annotations

import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ALL_NO: dict[str, Any] = {
    "customer_facing": False,
    "external_publication": False,
    "personal_data": False,
    "sensitive_data": False,
    "consequential_decisions": False,
    "regulated_advice": False,
    "vulnerable_users": False,
    "third_party_model_provider": False,
    "uses_retrieval": False,
    "takes_actions": False,
    "irreversible_actions": False,
    "autonomy_level": "L2",
    "max_financial_impact_per_action": 0,
    "prohibited_practices": ["none"],
}


def answers(**overrides: Any) -> dict[str, Any]:
    return {**ALL_NO, **overrides}


def test_default_policy_is_valid(risk_engine: ModuleType, policy: dict[str, Any]) -> None:
    assert risk_engine.validate_policy(policy) == []


def test_internal_assistive_tool_is_minimal(risk_engine: ModuleType, policy: dict[str, Any]) -> None:
    result = risk_engine.classify(policy, answers())
    assert result["tier"]["id"] == "minimal"
    assert result["complete"] is True
    assert result["triggered_rules"] == []
    control_ids = [c["id"] for c in result["required_controls"]]
    assert "HUM-01" in control_ids  # human reviews every output at L2
    assert result["approvers"] == ["Product owner", "Engineering lead"]


def test_customer_facing_is_limited_with_disclosure(risk_engine: ModuleType, policy: dict[str, Any]) -> None:
    result = risk_engine.classify(policy, answers(customer_facing=True))
    assert result["tier"]["id"] == "limited"
    assert [r["id"] for r in result["triggered_rules"]] == ["L-01"]
    assert "TRN-01" in [c["id"] for c in result["required_controls"]]


@pytest.mark.parametrize(
    "overrides",
    [
        {"consequential_decisions": True},
        {"sensitive_data": True},
        {"regulated_advice": True},
        {"vulnerable_users": True},
        {"max_financial_impact_per_action": 1000},
        {"autonomy_level": "L4", "customer_facing": True},
        {"autonomy_level": "L5", "irreversible_actions": True},
    ],
)
def test_high_tier_triggers(risk_engine: ModuleType, policy: dict[str, Any], overrides: dict[str, Any]) -> None:
    assert risk_engine.classify(policy, answers(**overrides))["tier"]["id"] == "high"


def test_internal_autonomy_alone_is_limited(risk_engine: ModuleType, policy: dict[str, Any]) -> None:
    result = risk_engine.classify(policy, answers(autonomy_level="L5"))
    assert result["tier"]["id"] == "limited"


def test_financial_threshold_is_inclusive(risk_engine: ModuleType, policy: dict[str, Any]) -> None:
    assert risk_engine.classify(policy, answers(max_financial_impact_per_action=999.99))["tier"]["id"] == "minimal"
    assert risk_engine.classify(policy, answers(max_financial_impact_per_action=1000))["tier"]["id"] == "high"


def test_refund_agent_exceeds_launch_autonomy_cap(risk_engine: ModuleType, policy: dict[str, Any]) -> None:
    result = risk_engine.classify(
        policy,
        answers(
            customer_facing=True,
            takes_actions=True,
            irreversible_actions=True,
            autonomy_level="L4",
            max_financial_impact_per_action=500,
        ),
    )
    assert result["tier"]["id"] == "high"
    assert result["max_autonomy_at_launch"] == "L3"
    assert result["planned_autonomy_within_cap"] is False
    assert any("exceeds the launch cap" in note for note in result["notes"])
    assert "SEC-02" in [c["id"] for c in result["required_controls"]]


def test_prohibited_practice_stops_the_work(risk_engine: ModuleType, policy: dict[str, Any]) -> None:
    result = risk_engine.classify(policy, answers(prohibited_practices=["social_scoring"]))
    assert result["tier"]["id"] == "prohibited"
    assert result["prohibited"] is True
    assert result["required_controls"] == []
    assert result["approvers"] == []


def test_controls_are_not_duplicated(risk_engine: ModuleType, policy: dict[str, Any]) -> None:
    result = risk_engine.classify(policy, answers(customer_facing=True, personal_data=True))
    ids = [c["id"] for c in result["required_controls"]]
    assert len(ids) == len(set(ids))


def test_unanswered_questions_are_reported(risk_engine: ModuleType, policy: dict[str, Any]) -> None:
    result = risk_engine.classify(policy, {"customer_facing": True})
    assert result["complete"] is False
    assert "sensitive_data" in result["unanswered_questions"]
    assert result["tier"]["id"] == "limited"
    assert result["tier_could_rise_to"] == "prohibited"


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        ({"not_a_question": True}, "unknown question"),
        ({"customer_facing": "yes"}, "true or false"),
        ({"autonomy_level": "L9"}, "must be one of"),
        ({"max_financial_impact_per_action": -1}, "non-negative"),
        ({"prohibited_practices": ["none", "social_scoring"]}, "cannot combine"),
    ],
)
def test_invalid_answers_are_rejected(
    risk_engine: ModuleType, policy: dict[str, Any], bad: dict[str, Any], message: str
) -> None:
    with pytest.raises(risk_engine.AnswerError, match=message):
        risk_engine.classify(policy, bad)


def test_policy_validation_catches_broken_references(risk_engine: ModuleType, policy: dict[str, Any]) -> None:
    policy["rules"][1]["tier"] = "catastrophic"
    policy["tiers"][0]["required_controls"].append("NOPE-01")
    policy["rules"][2]["when"] = {"question": "missing_question", "equals": True}
    problems = risk_engine.validate_policy(policy)
    assert any("unknown tier 'catastrophic'" in p for p in problems)
    assert any("unknown control 'NOPE-01'" in p for p in problems)
    assert any("unknown question 'missing_question'" in p for p in problems)


def test_policy_validation_checks_operator_types(risk_engine: ModuleType, policy: dict[str, Any]) -> None:
    policy["rules"][0]["when"] = {"question": "prohibited_practices", "equals": "none"}
    assert any("contains_any" in p for p in risk_engine.validate_policy(policy))


def test_policy_resolution_order(
    risk_engine: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, policy: dict[str, Any]
) -> None:
    workspace = tmp_path / ".ai-governance"
    workspace.mkdir()
    (workspace / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
    path, source = risk_engine.resolve_policy_path(None, cwd=tmp_path)
    assert path == workspace / "policy.json" and "workspace" in source

    env_policy = tmp_path / "env.json"
    env_policy.write_text(json.dumps(policy), encoding="utf-8")
    monkeypatch.setenv("AIPG_POLICY", str(env_policy))
    assert risk_engine.resolve_policy_path(None, cwd=tmp_path)[0] == env_policy
    assert risk_engine.resolve_policy_path("explicit.json", cwd=tmp_path)[0] == Path("explicit.json")


def test_bundled_default_used_without_overrides(risk_engine: ModuleType, tmp_path: Path) -> None:
    path, source = risk_engine.resolve_policy_path(None, cwd=tmp_path)
    assert path.name == "default-policy.json" and source == "bundled default policy"


def test_organisation_policy_changes_the_outcome(risk_engine: ModuleType, policy: dict[str, Any]) -> None:
    """Policy-as-code: an organisation can make customer-facing AI high risk without touching code."""
    for rule in policy["rules"]:
        if rule["id"] == "L-01":
            rule["tier"] = "high"
    assert risk_engine.classify(policy, answers(customer_facing=True))["tier"]["id"] == "high"


def test_cli_markdown_output(risk_engine: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    code = risk_engine.main(["--answers-json", json.dumps(answers(customer_facing=True)), "--format", "md"])
    out = capsys.readouterr().out
    assert code == 0
    assert "**Risk tier: Limited**" in out
    assert out.isascii(), "markdown output must be ASCII-safe for legacy consoles"


def test_cli_rejects_bad_answers(risk_engine: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    assert risk_engine.main(["--answers-json", '{"bogus": 1}']) == 2
    assert "unknown question" in capsys.readouterr().err


def test_cli_rejects_invalid_policy(risk_engine: ModuleType, tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"policy_id": "x"}', encoding="utf-8")
    assert risk_engine.main(["--validate-policy", "--policy", str(bad)]) == 3
