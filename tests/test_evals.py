"""Eval harness tests. Fake providers keep these offline, deterministic and free."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import pytest

from ai_product_governance.evals.config import EvalConfig, Gates, ModelSpec, load_config
from ai_product_governance.evals.judge import Verdict, parse_verdicts
from ai_product_governance.evals.providers import AgentResult, ToolCall, ToolSpec, Usage
from ai_product_governance.evals.report import write_reports
from ai_product_governance.evals.runner import build_manifest, estimate_cost, plan_jobs, run_jobs
from ai_product_governance.evals.runtime import SkillRuntime
from ai_product_governance.evals.scenarios import Scenario, ScenarioError, load_scenarios, parse_scenario
from ai_product_governance.evals.scoring import (
    ArmSummary,
    BaselineScore,
    GateResult,
    evaluate_gates,
    match_baseline,
    parse_baseline,
    score_trial,
    summarise,
    summarise_arms,
)
from ai_product_governance.skill import Skill


@pytest.fixture(scope="module")
def config(repo: Path) -> EvalConfig:
    return load_config(repo / "evals" / "eval.config.json")


@pytest.fixture(scope="module")
def scenarios(repo: Path) -> list[Scenario]:
    return load_scenarios(repo / "evals" / "scenarios")


# --------------------------------------------------------------------------- data files


def test_config_and_scenarios_load(config: EvalConfig, scenarios: list[Scenario]) -> None:
    assert config.judge_use == "subject", "one tool must be enough: the subject grades itself by default"
    assert config.models[0].id == "claude-code"
    assert len(scenarios) >= 10
    gates = {s.gate for s in scenarios}
    assert {"G0", "G1", "G2", "G3", "G4", "G5"} <= gates, "every lifecycle gate needs at least one scenario"
    assert any(c.critical for s in scenarios for c in s.criteria)


def test_scenario_expectations_point_at_real_files(skill: Skill, scenarios: list[Scenario]) -> None:
    for scenario in scenarios:
        for path in scenario.expected_reads:
            assert (skill.root / path).is_file(), f"{scenario.id}: {path}"


def test_scenario_validation_rejects_bad_files() -> None:
    with pytest.raises(ScenarioError, match="criterion and check ids must be unique"):
        parse_scenario(
            {
                "id": "dup",
                "title": "t",
                "gate": "G0",
                "prompt": "a sufficiently long prompt here",
                "criteria": [{"id": "C1", "text": "criterion one text"}, {"id": "C1", "text": "criterion two text"}],
            }
        )
    with pytest.raises(ScenarioError, match="invalid regex"):
        parse_scenario(
            {
                "id": "re",
                "title": "t",
                "gate": "G0",
                "prompt": "a sufficiently long prompt here",
                "criteria": [{"id": "C1", "text": "criterion one text"}],
                "checks": [{"id": "K1", "pattern": "([", "description": "broken"}],
            }
        )


# --------------------------------------------------------------------------- scoring


def _scenario() -> Scenario:
    return parse_scenario(
        {
            "id": "unit",
            "title": "Unit",
            "gate": "G4",
            "prompt": "Can we launch the assistant on Monday?",
            "criteria": [
                {"id": "C1", "text": "Says No-go clearly", "critical": True, "weight": 2},
                {"id": "C2", "text": "Lists the blocking gaps"},
            ],
            "checks": [{"id": "K1", "pattern": "no[- ]go", "flags": "i", "description": "States No-go"}],
        }
    )


def test_score_trial_weights_and_criticals() -> None:
    scenario = _scenario()
    verdicts = [Verdict("C1", True, "No-go", ""), Verdict("C2", False, "", "missing")]
    score, passed, critical, items = score_trial(scenario, "Decision: No-go.", verdicts, pass_threshold=0.7)
    assert score == pytest.approx(3 / 4)
    assert passed is True and critical == []
    assert [i.passed for i in items] == [True, False, True]

    verdicts = [Verdict("C1", False, "", ""), Verdict("C2", True, "", "")]
    score, passed, critical, _ = score_trial(scenario, "Go!", verdicts, pass_threshold=0.0)
    assert critical == ["C1"] and passed is False, "a critical failure fails the trial whatever the score"


def test_judge_parsing_treats_missing_verdicts_as_failures() -> None:
    verdicts = parse_verdicts(
        _scenario(), {"verdicts": [{"id": "[C2]", "verdict": "pass", "evidence": "x", "rationale": "y"}]}
    )
    assert [(v.id, v.passed) for v in verdicts] == [("C1", False), ("C2", True)]
    assert parse_verdicts(_scenario(), "garbage")[0].passed is False


def test_gates_and_regression() -> None:
    arms = [
        ArmSummary("m", "with-skill", 10, 0.86, 0.9, 0, 0),
        ArmSummary("m", "baseline", 10, 0.62, 0.4, 3, 0),
    ]
    gates = {g.name: g for g in evaluate_gates(arms, Gates(), baseline=[BaselineScore("m", 0.95)])}
    assert gates["min_with_skill_score"].passed
    assert gates["max_with_skill_critical_failures"].passed
    assert gates["min_delta"].passed and "+0.240" in gates["min_delta"].detail
    assert not gates["max_regression"].passed and not gates["max_regression"].skipped
    assert gates["max_regression"].detail == "0.860 vs baseline 0.950 (maximum drop 0.050)"
    assert "max_regression" not in {g.name for g in evaluate_gates(arms, Gates())}, "no --compare, no gate"


AGENT_RUN_BASELINE = BaselineScore("Claude Code (Opus)", 1.0, "agent-run", stands_in_for="claude-code", indicative=True)


def _with_skill(subject: str, score: float) -> list[ArmSummary]:
    return [ArmSummary(subject, "with-skill", 10, score, 1.0, 0, 0)]


def _regression(subject: str, score: float, baseline: list[BaselineScore]) -> GateResult:
    (gate,) = [g for g in evaluate_gates(_with_skill(subject, score), Gates(), baseline) if g.name == "max_regression"]
    return gate


def test_regression_gate_compares_a_subject_with_the_kit_that_stands_in_for_it() -> None:
    gate = _regression("claude-code", 0.97, [AGENT_RUN_BASELINE])
    assert gate.passed and not gate.skipped
    assert "vs baseline 1.000 from 'Claude Code (Opus)' (agent-run result, indicative)" in gate.detail
    gate = _regression("claude-code", 0.90, [AGENT_RUN_BASELINE])
    assert not gate.passed, "a stand-in baseline is enforced like any other"


def test_regression_gate_prefers_the_same_subject_id() -> None:
    baseline = [AGENT_RUN_BASELINE, BaselineScore("claude-code", 0.80, "claude-code")]
    assert match_baseline("claude-code", baseline) == baseline[1]
    assert match_baseline("Claude Code (Opus)", baseline) == baseline[0]
    gate = _regression("claude-code", 0.78, baseline)
    assert gate.passed and gate.detail == "0.780 vs baseline 0.800 (maximum drop 0.050)"


@pytest.mark.parametrize(
    ("baseline", "listed"), [([AGENT_RUN_BASELINE], "'Claude Code (Opus)'"), ([], "no with-skill results")]
)
def test_regression_gate_without_a_matching_subject_is_skipped_not_silent(
    baseline: list[BaselineScore], listed: str
) -> None:
    gate = _regression("anthropic-api", 0.5, baseline)
    assert gate.skipped and gate.passed, "skipped, and never a failure"
    assert "no baseline subject matches 'anthropic-api'" in gate.detail and listed in gate.detail


def test_parse_baseline_reads_how_each_subject_was_produced() -> None:
    arms = [
        {"subject": "Claude Code (Opus)", "arm": "with-skill", "mean_score": 1.0},
        {"subject": "Claude Code (Opus)", "arm": "baseline", "mean_score": 0.9},
        {"subject": "codex", "arm": "with-skill", "mean_score": 0.85},
    ]
    subjects = [
        {"id": "Claude Code (Opus)", "provider": "agent-run", "stands_in_for": "claude-code", "indicative": True},
        {"id": "codex", "provider": "agent-cli", "model": "inherit", "effort": None},
    ]
    assert parse_baseline({"arms": arms, "subjects": subjects}) == [
        AGENT_RUN_BASELINE,
        BaselineScore("codex", 0.85, "agent-cli"),
    ]
    # Results written before `subjects` was recorded still match by subject id.
    assert parse_baseline({"arms": arms}) == [BaselineScore("Claude Code (Opus)", 1.0), BaselineScore("codex", 0.85)]


def test_committed_baseline_is_compared_with_the_claude_code_subject(repo: Path) -> None:
    data = json.loads((repo / "evals" / "baselines" / "latest.json").read_text(encoding="utf-8"))
    (score,) = parse_baseline(data)
    assert score.stands_in_for == "claude-code" and score.indicative and score.provider == "agent-run"
    assert score.subject.startswith("Claude Code"), "the kit keeps its tool label as its subject id"
    gates = evaluate_gates(_with_skill("claude-code", 1.0) + _with_skill("anthropic-api", 1.0), Gates(), [score])
    regression = {g.subject: g for g in gates if g.name == "max_regression"}
    assert not regression["claude-code"].skipped and regression["claude-code"].passed
    assert regression["anthropic-api"].skipped, "other subjects are reported as not compared"


def test_skipped_gates_are_visible_in_markdown_and_junit() -> None:
    from ai_product_governance.evals.report import render_junit, render_markdown

    arms = _with_skill("anthropic-api", 0.9)
    gates = evaluate_gates(arms, Gates(), [AGENT_RUN_BASELINE])
    manifest = {"run_id": "r1", "skill_version": "1.0.0", "trials": 1, "subjects": [], "judges": {}}
    report = render_markdown(manifest, [], [], arms, gates, [], None)
    assert "**Gates: PASS (1 skipped)**" in report
    assert "| anthropic-api | max_regression | skipped | not compared: no baseline subject matches" in report
    suite = ET.fromstring(render_junit(manifest, [], gates)).find("testsuite[@name='gates']")
    assert suite is not None and suite.get("skipped") == "1" and suite.get("failures") == "0"
    case = suite.find("testcase[@name='max_regression']")
    assert case is not None and case.find("skipped") is not None and case.find("failure") is None


# --------------------------------------------------------------------------- skill-host runtime


def test_runtime_reads_files_inside_the_skill_only(skill: Skill) -> None:
    runtime = SkillRuntime(skill)
    text, error = runtime.execute("read_skill_file", {"path": "references/gate-0-intake-and-fit.md"})
    assert not error and text.startswith("# Gate 0")
    _, error = runtime.execute("read_skill_file", {"path": "../../pyproject.toml"})
    assert error
    _, error = runtime.execute("read_skill_file", {"path": "references/nope.md"})
    assert error
    assert runtime.files_read == ["references/gate-0-intake-and-fit.md"]
    assert "<skill_instructions>" in runtime.system_prompt()


def test_runtime_runs_only_allow_listed_scripts(skill: Skill) -> None:
    runtime = SkillRuntime(skill)
    output, error = runtime.execute(
        "run_skill_script", {"script": "risk_tier.py", "args": ["--answers-json", '{"customer_facing": true}']}
    )
    assert not error and '"id": "limited"' in output
    _, error = runtime.execute("run_skill_script", {"script": "../../evil.py", "args": []})
    assert error
    _, error = runtime.execute("run_skill_script", {"script": "unit_economics.py", "args": "--example"})
    assert error
    assert runtime.scripts_run == ["risk_tier.py"]


# --------------------------------------------------------------------------- end-to-end with fakes


class FakeSubject:
    """With the skill it reads the playbook and answers well; without tools it answers poorly."""

    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec

    def run_agent(self, system: str, user: str, tools: list[ToolSpec], execute: Any, max_turns: int) -> AgentResult:
        calls = []
        if tools:
            output, is_error = execute("read_skill_file", {"path": "references/gate-4-launch-readiness.md"})
            calls.append(ToolCall("read_skill_file", {}, output, is_error))
            text = "Verdict: No-go. Blocking gaps: kill switch untested, no red team."
        else:
            text = "Sounds fine, go ahead."
        return AgentResult(text=text, tool_calls=calls, usage=Usage(1000, 500), turns=2, stop_reason="end_turn")

    def complete_json(self, system: str, user: str, schema: dict[str, Any], schema_name: str) -> tuple[Any, Usage]:
        raise AssertionError("subjects are never used as judges")


class FakeJudge:
    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec

    def run_agent(self, *args: Any, **kwargs: Any) -> AgentResult:
        raise AssertionError("the judge never runs agent loops")

    def complete_json(self, system: str, user: str, schema: dict[str, Any], schema_name: str) -> tuple[Any, Usage]:
        response = user.split("<response>", 1)[1]
        good = "No-go" in response
        verdicts = [
            {"id": cid, "verdict": "pass" if good else "fail", "evidence": "", "rationale": ""} for cid in ("C1", "C2")
        ]
        return {"verdicts": verdicts}, Usage(800, 200)


def _factory(spec: ModelSpec) -> Any:
    return FakeJudge(spec) if "judge" in spec.id else FakeSubject(spec)


def test_end_to_end_run_with_fake_models(config: EvalConfig, skill: Skill, tmp_path: Path) -> None:
    scenario = replace(_scenario(), expected_reads=("references/gate-4-launch-readiness.md",))
    subject = ModelSpec("fake", "anthropic", "claude-opus-5-5")
    cfg = replace(config, concurrency=2)
    jobs = plan_jobs(cfg, [subject], [scenario], ["with-skill", "baseline"], trials=2)
    outcome = run_jobs(cfg, skill, jobs, provider_factory=_factory, progress=lambda _: None)

    assert len(outcome.trials) == 4
    with_skill = [t for t in outcome.trials if t.arm == "with-skill"]
    baseline = [t for t in outcome.trials if t.arm == "baseline"]
    assert all(t.passed and t.score == 1.0 for t in with_skill)
    assert all(not t.passed and t.critical_failures == ["C1"] for t in baseline)
    assert all(t.routing == {"read references/gate-4-launch-readiness.md": True} for t in with_skill)
    assert outcome.total_cost_usd is not None and outcome.total_cost_usd > 0

    cells = summarise(outcome.trials)
    arms = summarise_arms(cells)
    gates = evaluate_gates(arms, cfg.gates)
    assert all(g.passed for g in gates)

    manifest = build_manifest(cfg, skill, [scenario], outcome, ["with-skill", "baseline"], 2, [subject])
    paths = write_reports(
        tmp_path, manifest, outcome.trials, cells, arms, gates, outcome.skipped, outcome.total_cost_usd
    )
    report = paths["report"].read_text(encoding="utf-8")
    assert "**Gates: PASS**" in report and "Skill adherence" in report
    results = json.loads(paths["results"].read_text(encoding="utf-8"))
    assert {a["arm"] for a in results["arms"]} == {"with-skill", "baseline"}
    suites = ET.parse(paths["junit"]).getroot()
    assert suites.find("testsuite[@name='gates']") is not None
    assert len(manifest["skill_sha256"]) == 64


def test_cost_ceiling_skips_remaining_trials(config: EvalConfig, skill: Skill) -> None:
    cfg = replace(config, concurrency=1)
    subject = ModelSpec("fake", "anthropic", "claude-opus-5-5")
    jobs = plan_jobs(cfg, [subject], [_scenario()], ["with-skill"], trials=3)
    outcome = run_jobs(cfg, skill, jobs, max_cost_usd=0.000001, provider_factory=_factory, progress=lambda _: None)
    assert len(outcome.trials) == 1 and len(outcome.skipped) == 2


def test_provider_errors_become_failed_trials(config: EvalConfig, skill: Skill) -> None:
    class Exploding(FakeSubject):
        def run_agent(self, *args: Any, **kwargs: Any) -> AgentResult:
            raise RuntimeError("rate limited")

    def factory(spec: ModelSpec) -> Any:
        return FakeJudge(spec) if "judge" in spec.id else Exploding(spec)

    jobs = plan_jobs(config, [ModelSpec("x", "anthropic", "m")], [_scenario()], ["baseline"], trials=1)
    outcome = run_jobs(config, skill, jobs, provider_factory=factory, progress=lambda _: None)
    trial = outcome.trials[0]
    assert trial.error == "RuntimeError: rate limited" and trial.score == 0.0 and trial.critical_failures == ["C1"]


def test_dry_run_estimate_is_positive(config: EvalConfig, skill: Skill, scenarios: list[Scenario]) -> None:
    jobs = plan_jobs(config, [config.models[0]], scenarios, ["with-skill", "baseline"], trials=1)
    estimate, detail = estimate_cost(config, skill, jobs)
    assert estimate is not None and estimate > 0 and detail["jobs"] == len(jobs)
    unpriced = plan_jobs(config, [ModelSpec("u", "openai", "unknown-model")], scenarios[:1], ["baseline"], 1)
    assert estimate_cost(config, skill, unpriced)[0] is None
