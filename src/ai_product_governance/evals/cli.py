"""`aipg eval` command."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ai_product_governance.evals.config import ARMS, ConfigError, ModelSpec, load_config
from ai_product_governance.evals.providers import credentials_available
from ai_product_governance.evals.report import write_reports
from ai_product_governance.evals.runner import build_manifest, estimate_cost, plan_jobs, run_jobs
from ai_product_governance.evals.scenarios import ScenarioError, load_scenarios
from ai_product_governance.evals.scoring import evaluate_gates, summarise, summarise_arms
from ai_product_governance.skill import find_repo_root, load_skill


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="eval config (default: evals/eval.config.json)")
    parser.add_argument("--scenarios", help="scenario directory (default: evals/scenarios)")
    parser.add_argument("--subject", action="append", default=[], help="subject id to run (repeatable)")
    parser.add_argument("--scenario", action="append", default=[], help="scenario id to run (repeatable)")
    parser.add_argument("--arms", help=f"comma-separated arms ({', '.join(ARMS)})")
    parser.add_argument("--trials", type=int, help="trials per subject x scenario x arm")
    parser.add_argument("--max-cost-usd", type=float, help="stop starting new trials once spend reaches this")
    parser.add_argument("--out", help="results directory (default: evals/results/<run id>)")
    parser.add_argument("--compare", help="baseline results.json to check for regressions")
    parser.add_argument("--update-baseline", action="store_true", help="save this run as evals/baselines/latest.json")
    parser.add_argument(
        "--dry-run", action="store_true", help="validate and print the plan and an estimate; no API calls"
    )


def run_from_args(args: argparse.Namespace) -> int:
    repo = find_repo_root()
    try:
        config = load_config(Path(args.config) if args.config else repo / "evals" / "eval.config.json")
        scenarios = load_scenarios(Path(args.scenarios) if args.scenarios else repo / "evals" / "scenarios")
    except (ConfigError, ScenarioError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.scenario:
        unknown = sorted(set(args.scenario) - {s.id for s in scenarios})
        if unknown:
            print(f"error: unknown scenario(s): {', '.join(unknown)}", file=sys.stderr)
            return 2
        scenarios = [s for s in scenarios if s.id in args.scenario]

    subjects = _select_subjects(config.subjects, args.subject, args.dry_run)
    if subjects is None:
        return 2
    arms = [a.strip() for a in args.arms.split(",")] if args.arms else list(config.arms)
    if any(a not in ARMS for a in arms):
        print(f"error: arms must be drawn from {', '.join(ARMS)}", file=sys.stderr)
        return 2
    trials = args.trials or config.trials
    skill = load_skill()
    jobs = plan_jobs(config, subjects, scenarios, arms, trials)

    estimate, _ = estimate_cost(config, skill, jobs)
    print(
        f"Plan: {len(subjects)} subject(s) x {len(scenarios)} scenario(s) x {len(arms)} arm(s) x {trials} "
        f"trial(s) = {len(jobs)} generations + {len(jobs)} judge calls."
    )
    print("Rough cost estimate: " + ("n/a (missing pricing)" if estimate is None else f"${estimate:,.2f}"))
    if args.dry_run:
        for subject in subjects:
            ready = "credentials found" if credentials_available(subject) else "no credentials"
            print(f"  subject {subject.id}: {subject.provider}/{subject.model} ({ready})")
        print(f"  judge: {config.judge.provider}/{config.judge.model}")
        return 0
    if not jobs:
        print("Nothing to run.")
        return 0
    if not credentials_available(config.judge):
        print("error: no credentials for the judge model; see docs/evaluation.md", file=sys.stderr)
        return 2

    outcome = run_jobs(config, skill, jobs, max_cost_usd=args.max_cost_usd)
    outcome.manifest = build_manifest(config, skill, scenarios, outcome, arms, trials, subjects)
    cells = summarise(outcome.trials)
    arm_summaries = summarise_arms(cells)
    baseline = _load_baseline(Path(args.compare)) if args.compare else None
    gates = evaluate_gates(arm_summaries, config.gates, baseline)

    out_dir = Path(args.out) if args.out else repo / "evals" / "results" / outcome.run_id
    paths = write_reports(
        out_dir, outcome.manifest, outcome.trials, cells, arm_summaries, gates, outcome.skipped, outcome.total_cost_usd
    )
    if args.update_baseline:
        target = repo / "evals" / "baselines" / "latest.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(paths["results"].read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Baseline updated: {target}")

    print(f"Report: {paths['report']}")
    failed = [g for g in gates if not g.passed]
    for gate in failed:
        print(f"GATE FAILED {gate.subject} {gate.name}: {gate.detail}")
    if outcome.skipped:
        print(f"{len(outcome.skipped)} trial(s) skipped at the cost ceiling; results are partial.")
        return 3
    return 1 if failed else 0


def _select_subjects(subjects: tuple[ModelSpec, ...], requested: list[str], dry_run: bool) -> list[ModelSpec] | None:
    by_id = {s.id: s for s in subjects}
    if requested:
        unknown = sorted(set(requested) - set(by_id))
        if unknown:
            print(f"error: unknown subject(s): {', '.join(unknown)}", file=sys.stderr)
            return None
        chosen = [by_id[i] for i in requested]
    else:
        chosen = [s for s in subjects if s.enabled]
    if dry_run:
        return chosen
    ready = [s for s in chosen if credentials_available(s)]
    for subject in chosen:
        if subject not in ready:
            print(f"skipping subject {subject.id}: no API credentials in the environment")
    return ready


def _load_baseline(path: Path) -> dict[str, float]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {a["subject"]: a["mean_score"] for a in data.get("arms", []) if a.get("arm") == "with-skill"}
