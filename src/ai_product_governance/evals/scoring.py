"""Scoring, aggregation, quality gates and regression comparison."""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from typing import Any

from ai_product_governance.evals.config import Gates
from ai_product_governance.evals.judge import Verdict
from ai_product_governance.evals.scenarios import Scenario


@dataclass
class ItemResult:
    id: str
    kind: str  # "criterion" or "check"
    text: str
    passed: bool
    weight: float
    critical: bool
    evidence: str = ""
    rationale: str = ""


@dataclass
class TrialResult:
    subject: str
    scenario: str
    arm: str
    trial: int
    score: float
    passed: bool
    critical_failures: list[str]
    items: list[ItemResult]
    response: str
    files_read: list[str] = field(default_factory=list)
    scripts_run: list[str] = field(default_factory=list)
    routing: dict[str, bool] = field(default_factory=dict)
    error: str | None = None
    cost_usd: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    turns: int = 0
    served_model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def score_trial(
    scenario: Scenario,
    response: str,
    verdicts: list[Verdict],
    pass_threshold: float,
) -> tuple[float, bool, list[str], list[ItemResult]]:
    items: list[ItemResult] = []
    by_id = {v.id: v for v in verdicts}
    for criterion in scenario.criteria:
        verdict = by_id.get(criterion.id)
        items.append(
            ItemResult(
                criterion.id,
                "criterion",
                criterion.text,
                bool(verdict and verdict.passed),
                criterion.weight,
                criterion.critical,
                verdict.evidence if verdict else "",
                verdict.rationale if verdict else "missing",
            )
        )
    for check in scenario.checks:
        items.append(
            ItemResult(check.id, "check", check.description, check.evaluate(response), check.weight, check.critical)
        )
    total = sum(item.weight for item in items)
    score = sum(item.weight for item in items if item.passed) / total if total else 0.0
    critical_failures = [item.id for item in items if item.critical and not item.passed]
    return score, (score >= pass_threshold and not critical_failures), critical_failures, items


def failed_trial(subject: str, scenario: Scenario, arm: str, trial: int, error: str, response: str = "") -> TrialResult:
    """A trial that produced no gradeable answer scores zero and fails every critical criterion."""
    critical = [c.id for c in scenario.criteria if c.critical] + [k.id for k in scenario.checks if k.critical]
    return TrialResult(subject, scenario.id, arm, trial, 0.0, False, critical, [], response, error=error)


@dataclass
class CellSummary:
    """One subject x scenario x arm."""

    subject: str
    scenario: str
    arm: str
    trials: int
    mean_score: float
    stdev: float
    pass_rate: float
    critical_failures: int
    errors: int
    cost_usd: float | None


def summarise(trials: list[TrialResult]) -> list[CellSummary]:
    cells: dict[tuple[str, str, str], list[TrialResult]] = {}
    for trial in trials:
        cells.setdefault((trial.subject, trial.scenario, trial.arm), []).append(trial)
    summaries = []
    for (subject, scenario, arm), group in sorted(cells.items()):
        scores = [t.score for t in group]
        costs = [t.cost_usd for t in group]
        summaries.append(
            CellSummary(
                subject=subject,
                scenario=scenario,
                arm=arm,
                trials=len(group),
                mean_score=statistics.fmean(scores),
                stdev=statistics.stdev(scores) if len(scores) > 1 else 0.0,
                pass_rate=sum(t.passed for t in group) / len(group),
                critical_failures=sum(len(t.critical_failures) for t in group),
                errors=sum(1 for t in group if t.error),
                cost_usd=None if any(c is None for c in costs) else sum(c for c in costs if c is not None),
            )
        )
    return summaries


@dataclass
class ArmSummary:
    subject: str
    arm: str
    scenarios: int
    mean_score: float
    pass_rate: float
    critical_failures: int
    errors: int


def summarise_arms(cells: list[CellSummary]) -> list[ArmSummary]:
    groups: dict[tuple[str, str], list[CellSummary]] = {}
    for cell in cells:
        groups.setdefault((cell.subject, cell.arm), []).append(cell)
    return [
        ArmSummary(
            subject=subject,
            arm=arm,
            scenarios=len(group),
            mean_score=statistics.fmean(c.mean_score for c in group),
            pass_rate=statistics.fmean(c.pass_rate for c in group),
            critical_failures=sum(c.critical_failures for c in group),
            errors=sum(c.errors for c in group),
        )
        for (subject, arm), group in sorted(groups.items())
    ]


@dataclass
class GateResult:
    subject: str
    name: str
    passed: bool
    detail: str


def evaluate_gates(arms: list[ArmSummary], gates: Gates, baseline: dict[str, float] | None = None) -> list[GateResult]:
    """Apply the quality gates per subject. `baseline` maps subject id -> previous with-skill mean score."""
    results: list[GateResult] = []
    by_key = {(a.subject, a.arm): a for a in arms}
    for subject in sorted({a.subject for a in arms}):
        skill = by_key.get((subject, "with-skill"))
        if skill is None:
            continue
        results.append(
            GateResult(
                subject,
                "min_with_skill_score",
                skill.mean_score >= gates.min_with_skill_score,
                f"{skill.mean_score:.3f} (minimum {gates.min_with_skill_score:.3f})",
            )
        )
        results.append(
            GateResult(
                subject,
                "max_with_skill_critical_failures",
                skill.critical_failures <= gates.max_with_skill_critical_failures,
                f"{skill.critical_failures} (maximum {gates.max_with_skill_critical_failures})",
            )
        )
        control = by_key.get((subject, "baseline"))
        if control is not None:
            delta = skill.mean_score - control.mean_score
            results.append(
                GateResult(
                    subject, "min_delta", delta >= gates.min_delta, f"{delta:+.3f} (minimum {gates.min_delta:+.3f})"
                )
            )
        if baseline and subject in baseline:
            drop = baseline[subject] - skill.mean_score
            results.append(
                GateResult(
                    subject,
                    "max_regression",
                    drop <= gates.max_regression,
                    f"{skill.mean_score:.3f} vs baseline {baseline[subject]:.3f} (maximum drop {gates.max_regression:.3f})",
                )
            )
    return results
