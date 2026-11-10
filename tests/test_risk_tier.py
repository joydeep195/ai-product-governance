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
    "outputs_concern_people": False,
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


def test_complete_answers_lead_with_the_tier(risk_engine: ModuleType, policy: dict[str, Any]) -> None:
    result = risk_engine.classify(policy, answers(customer_facing=True))
    assert result["status"] == "complete"
    assert result["headline"] == "Limited"


def test_empty_questionnaire_leads_with_incomplete_not_a_tier(
    risk_engine: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """An agent reading the output must not see a bare tier first when nothing has been answered."""
    assert risk_engine.main(["--answers-json", "{}", "--format", "md"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("**Risk tier: Incomplete (provisional Minimal; could rise to Prohibited)**")
    assert "**Risk tier: Minimal**" not in out

    assert risk_engine.main(["--answers-json", "{}"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "incomplete"
    assert result["headline"] == "Incomplete (provisional Minimal; could rise to Prohibited)"
    assert result["tier"]["id"] == "minimal"  # the provisional tier stays available to existing readers
    assert "ask the user the unanswered questions" in result["notes"][0]
    assert "Assumptions Ledger" in result["notes"][0]


def test_strict_exits_4_on_an_incomplete_questionnaire_but_still_prints(
    risk_engine: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert risk_engine.main(["--answers-json", "{}", "--strict"]) == 4
    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == "incomplete"
    assert "unanswered questions" in captured.err
    assert risk_engine.main(["--answers-json", json.dumps(answers()), "--strict"]) == 0


def test_incomplete_headline_when_the_tier_cannot_rise(risk_engine: ModuleType, policy: dict[str, Any]) -> None:
    partial = answers(sensitive_data=True)
    del partial["uses_retrieval"]  # no rule reads it, but it can still add a control
    result = risk_engine.classify(policy, partial)
    assert result["status"] == "incomplete"
    assert result["tier_could_rise_to"] is None
    assert result["headline"] == "Incomplete (provisional High; the tier cannot rise, but controls can change)"


def test_prohibited_is_final_even_when_incomplete(risk_engine: ModuleType, policy: dict[str, Any]) -> None:
    result = risk_engine.classify(policy, {"prohibited_practices": ["social_scoring"]})
    assert result["status"] == "incomplete"
    assert result["headline"] == "Prohibited"
    assert any("final" in note for note in result["notes"])


# An internal AI that drafts an infrastructure resilience report: high risk because one wrong report can be costly,
# but nobody is the subject of the output, so fairness and contestability have nothing to act on.
RESILIENCE_REPORT = answers(max_financial_impact_per_action=5000)


def test_controls_with_nobody_affected_are_shown_as_not_applicable(
    risk_engine: ModuleType, policy: dict[str, Any]
) -> None:
    result = risk_engine.classify(policy, RESILIENCE_REPORT)
    assert result["tier"]["id"] == "high"
    required = [c["id"] for c in result["required_controls"]]
    ruled_out = {c["id"]: c for c in result["not_applicable_controls"]}
    assert "EVAL-03" not in required and "TRN-02" not in required
    assert set(ruled_out) == {"EVAL-03", "TRN-02"}
    assert ruled_out["TRN-02"]["required_by"] == "tier: high"
    assert ruled_out["TRN-02"]["reason"].startswith("No person is the subject of the output")
    assert any("do not drop them silently" in note for note in result["notes"])


def test_not_applicable_controls_are_listed_in_markdown(
    risk_engine: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert risk_engine.main(["--answers-json", json.dumps(RESILIENCE_REPORT), "--format", "md"]) == 0
    out = capsys.readouterr().out
    assert "**Not applicable:**" in out
    assert "| EVAL-03 | Fairness evaluation | tier: high | not applicable: No person is the subject" in out
    assert out.isascii()


@pytest.mark.parametrize(
    ("overrides", "required", "ruled_out"),
    [
        ({"outputs_concern_people": True}, {"EVAL-03", "TRN-02"}, set()),
        ({"consequential_decisions": True}, {"EVAL-03", "TRN-02"}, set()),
        ({"customer_facing": True}, {"EVAL-03"}, {"TRN-02"}),  # users outside the org, but nobody is assessed
        ({"vulnerable_users": True}, {"EVAL-03"}, {"TRN-02"}),
    ],
)
def test_answers_that_bring_people_into_scope_keep_the_controls(
    risk_engine: ModuleType,
    policy: dict[str, Any],
    overrides: dict[str, Any],
    required: set[str],
    ruled_out: set[str],
) -> None:
    result = risk_engine.classify(policy, {**RESILIENCE_REPORT, **overrides})
    assert required <= {c["id"] for c in result["required_controls"]}
    assert {c["id"] for c in result["not_applicable_controls"]} == ruled_out


def test_unanswered_applicability_keeps_the_control_required(risk_engine: ModuleType, policy: dict[str, Any]) -> None:
    partial = dict(RESILIENCE_REPORT)
    del partial["outputs_concern_people"]
    result = risk_engine.classify(policy, partial)
    assert {"EVAL-03", "TRN-02"} <= {c["id"] for c in result["required_controls"]}
    assert result["not_applicable_controls"] == []
    assert any("EVAL-03, TRN-02 stay required until `outputs_concern_people`" in note for note in result["notes"])


def test_policy_validation_checks_applicability(risk_engine: ModuleType, policy: dict[str, Any]) -> None:
    fairness = next(c for c in policy["controls"] if c["id"] == "EVAL-03")
    del fairness["not_applicable_reason"]
    fairness["applies_when"] = {"question": "nobody_asked_this", "equals": True}
    problems = risk_engine.validate_policy(policy)
    assert any("must be given together" in p for p in problems)
    assert any("applies_when: unknown question 'nobody_asked_this'" in p for p in problems)


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
