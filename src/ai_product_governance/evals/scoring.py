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
    skipped: bool = False  # the gate could not be checked; a skipped gate never fails the run


@dataclass(frozen=True)
class BaselineScore:
    """One subject's with-skill mean score in a baseline results.json."""

    subject: str
    mean_score: float
    provider: str = ""  # how the baseline was produced: a provider such as "claude-code", or a kit mode
    stands_in_for: str = ""  # the automated subject id a kit result is compared as, if it names one
    indicative: bool = False  # an agent-run result: indicative evidence, not audited


def parse_baseline(data: dict[str, Any]) -> list[BaselineScore]:
    """The with-skill scores in a results.json, with what its `subjects` list says about how they were produced."""
    subjects = {str(s.get("id")): s for s in data.get("subjects", []) if isinstance(s, dict)}
    scores = []
    for arm in data.get("arms", []):
        if arm.get("arm") != "with-skill":
            continue
        described = subjects.get(str(arm["subject"]), {})
        scores.append(
            BaselineScore(
                subject=str(arm["subject"]),
                mean_score=float(arm["mean_score"]),
                provider=str(described.get("provider") or ""),
                stands_in_for=str(described.get("stands_in_for") or ""),
                indicative=bool(described.get("indicative")),
            )
        )
    return scores


def match_baseline(subject: str, baseline: list[BaselineScore]) -> BaselineScore | None:
    """The baseline score to compare `subject` with: the same subject id, else a kit result that stands in for it."""
    exact = next((b for b in baseline if b.subject == subject), None)
    return exact or next((b for b in baseline if b.stands_in_for == subject), None)


def evaluate_gates(
    arms: list[ArmSummary], gates: Gates, baseline: list[BaselineScore] | None = None
) -> list[GateResult]:
    """Apply the quality gates per subject.

    With a `baseline` (from `--compare`), every subject gets a `max_regression` gate: checked against its match
    (see `match_baseline`), or reported as skipped when nothing in the baseline matches it.
    """
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
        if baseline is not None:
            results.append(_regression_gate(subject, skill.mean_score, baseline, gates.max_regression))
    return results


def _regression_gate(subject: str, score: float, baseline: list[BaselineScore], max_drop: float) -> GateResult:
    match = match_baseline(subject, baseline)
    if match is None:
        found = ", ".join(repr(b.subject) for b in baseline) or "no with-skill results"
        return GateResult(
            subject,
            "max_regression",
            True,
            f"not compared: no baseline subject matches {subject!r} (the baseline has {found})",
            skipped=True,
        )
    origin = f" from {match.subject!r}" if match.subject != subject else ""
    if match.indicative:
        origin += f" ({match.provider} result, indicative)"
    return GateResult(
        subject,
        "max_regression",
        match.mean_score - score <= max_drop,
        f"{score:.3f} vs baseline {match.mean_score:.3f}{origin} (maximum drop {max_drop:.3f})",
    )
