"""`aipg eval` command.

With no options it detects the AI access you already have (an agent CLI you are signed in to,
an API key, or a local model server) and uses that one tool both to answer and to grade, so a
single tool is always enough. Chat-only tools use the manual kit instead (`aipg eval-kit`).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from ai_product_governance.evals.config import (
    ARMS,
    JUDGE_SAME_AS_SUBJECT,
    ConfigError,
    EvalConfig,
    ModelSpec,
    load_config,
)
from ai_product_governance.evals.providers import readiness
from ai_product_governance.evals.report import write_reports
from ai_product_governance.evals.runner import build_manifest, estimate_cost, plan_jobs, run_jobs
from ai_product_governance.evals.scenarios import ScenarioError, load_scenarios
from ai_product_governance.evals.scoring import evaluate_gates, summarise, summarise_arms
from ai_product_governance.skill import find_repo_root, load_skill

NO_TOOL_HELP = """\
No AI access was found to run the evals automatically. Any ONE of these is enough:
  - sign in to an agent CLI you use: Claude Code (`claude auth login`), Codex (`codex login`),
    Gemini CLI, GitHub Copilot CLI or Cursor CLI;
  - set an API key (ANTHROPIC_API_KEY, OPENAI_API_KEY or GEMINI_API_KEY);
  - run a free local model with Ollama (`ollama pull llama3.1`).
Using a chat app such as ChatGPT, Gemini or Microsoft 365 Copilot? Use the manual kit:
  aipg eval-kit create"""


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="eval config (default: evals/eval.config.json)")
    parser.add_argument("--scenarios", help="scenario directory (default: evals/scenarios)")
    parser.add_argument("--subject", action="append", default=[], help="model id to evaluate (repeatable)")
    parser.add_argument("--all", action="store_true", help="evaluate every ready model (a cross-tool scorecard)")
    parser.add_argument("--scenario", action="append", default=[], help="scenario id to run (repeatable)")
    parser.add_argument("--arms", help=f"comma-separated arms ({', '.join(ARMS)})")
    parser.add_argument("--trials", type=int, help="trials per model x scenario x arm")
    parser.add_argument("--model", help="override the model name of every selected subject")
    parser.add_argument("--effort", help="override the effort level of every selected subject (e.g. high, max)")
    parser.add_argument("--judge", help=f"'{JUDGE_SAME_AS_SUBJECT}' (the same tool, default) or a model id")
    parser.add_argument("--max-cost-usd", type=float, help="stop starting new trials once known spend reaches this")
    parser.add_argument("--out", help="results directory (default: evals/results/<run id>)")
    parser.add_argument("--compare", help="baseline results.json to check for regressions")
    parser.add_argument("--update-baseline", action="store_true", help="save this run as evals/baselines/latest.json")
    parser.add_argument(
        "--dry-run", action="store_true", help="show what would run and what is detected; no model calls"
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
    arms = [a.strip() for a in args.arms.split(",")] if args.arms else list(config.arms)
    if any(a not in ARMS for a in arms):
        print(f"error: arms must be drawn from {', '.join(ARMS)}", file=sys.stderr)
        return 2
    judge_use = args.judge or config.judge_use
    if judge_use != JUDGE_SAME_AS_SUBJECT and judge_use not in {m.id for m in config.models}:
        print(f"error: unknown judge '{judge_use}'", file=sys.stderr)
        return 2

    statuses = {spec.id: readiness(spec) for spec in config.models}
    subjects = _choose_subjects(config, args, statuses)
    if subjects is None:
        return 2
    subjects = _override(subjects, args.model, args.effort)

    def judge_for(subject: ModelSpec) -> ModelSpec:
        return config.judge_for(subject, judge_use)

    trials = args.trials or config.trials
    skill = load_skill()
    jobs = plan_jobs(config, subjects, scenarios, arms, trials)

    if args.dry_run:
        _print_detection(config, statuses, subjects)
    if not subjects:
        print(NO_TOOL_HELP, file=sys.stdout if args.dry_run else sys.stderr)
        return 0 if args.dry_run else 2

    estimate, _ = estimate_cost(config, skill, jobs, judge_for)
    print(
        f"Plan: {len(subjects)} model(s) x {len(scenarios)} scenario(s) x {len(arms)} arm(s) x {trials} "
        f"trial(s) = {len(jobs)} answers + {len(jobs)} gradings."
    )
    for subject in subjects:
        judge = judge_for(subject)
        same = " (the same tool)" if judge_use == JUDGE_SAME_AS_SUBJECT else ""
        print(f"  {subject.id}: {_label(subject)}; graded by {_label(judge)}{same}")
    print(
        "Rough cost estimate: " + ("n/a (subscription or unpriced model)" if estimate is None else f"${estimate:,.2f}")
    )
    if any(s.provider in ("claude-code", "agent-cli") for s in subjects):
        print("Agent CLIs use your existing sign-in: usage counts against that plan, not an API bill.")
    if args.dry_run:
        return 0

    for judge in {judge_for(s).id: judge_for(s) for s in subjects}.values():
        ok, detail = readiness(judge)
        if not ok:
            print(f"error: judge {judge.id} is not ready: {detail}", file=sys.stderr)
            return 2

    outcome = run_jobs(config, skill, jobs, judge_for=judge_for, max_cost_usd=args.max_cost_usd)
    outcome.manifest = build_manifest(config, skill, scenarios, outcome, arms, trials, subjects, judge_for=judge_for)
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


def add_kit_arguments(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="kit_command", required=True)
    create = sub.add_parser("create", help="write the run sheet and empty answer files")
    create.add_argument("--trials", type=int, default=1, help="trials per scenario and arm (default 1)")
    create.add_argument("--scenario", action="append", default=[], help="scenario id to include (repeatable)")
    create.add_argument("--tool", default="", help="label for the AI tool you will use, e.g. 'ChatGPT (GPT-5)'")
    create.add_argument("--out", help="folder for kits (default: evals/kits)")
    for name, text in (("grade", "write the blind grading prompts"), ("score", "score the kit and write the report")):
        command = sub.add_parser(name, help=text)
        command.add_argument("kit", help="the kit folder created by `aipg eval-kit create`")


def run_kit_from_args(args: argparse.Namespace) -> int:
    from ai_product_governance.evals.kit import KitError, create_kit, prepare_grading, score_kit

    repo = find_repo_root()
    config = load_config(repo / "evals" / "eval.config.json")
    scenarios = load_scenarios(repo / "evals" / "scenarios")
    skill = load_skill()
    try:
        if args.kit_command == "create":
            if args.scenario:
                scenarios = [s for s in scenarios if s.id in args.scenario]
                if not scenarios:
                    print("error: no matching scenarios", file=sys.stderr)
                    return 2
            kit_root = Path(args.out) if args.out else repo / "evals" / "kits"
            kit_dir = create_kit(kit_root, config, skill, scenarios, trials=args.trials, tool=args.tool)
            answers = len(scenarios) * len(config.arms) * args.trials
            print(f"Created {kit_dir}")
            print(f"Step 1: open {kit_dir / '1-ANSWERS.md'} and collect {answers} answers with your AI tool.")
            return 0
        kit_dir = Path(args.kit)
        if args.kit_command == "grade":
            sheet = prepare_grading(kit_dir, scenarios)
            print(f"Step 2: open {sheet} and grade each answer in a new chat without the skill.")
            return 0
        paths, gates = score_kit(kit_dir, config, skill, scenarios)
        print(f"Report: {paths['report']}")
        failed = [g for g in gates if not g.passed]
        for gate in failed:
            print(f"GATE FAILED {gate.subject} {gate.name}: {gate.detail}")
        return 1 if failed else 0
    except KitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _choose_subjects(
    config: EvalConfig, args: argparse.Namespace, statuses: dict[str, tuple[bool, str]]
) -> list[ModelSpec] | None:
    if args.subject:
        unknown = sorted(set(args.subject) - {m.id for m in config.models})
        if unknown:
            print(f"error: unknown model(s): {', '.join(unknown)}", file=sys.stderr)
            return None
        chosen = [config.model(model_id) for model_id in args.subject]
        if args.dry_run:
            return chosen
        not_ready = [m for m in chosen if not statuses[m.id][0]]
        for model in not_ready:
            print(f"error: {model.id} is not ready: {statuses[model.id][1]}", file=sys.stderr)
        return None if not_ready else chosen
    ready = [m for m in config.models if m.auto and statuses[m.id][0]]
    if args.all:
        return ready
    return ready[:1]  # one tool is enough: the first ready one, in configured order


def _override(subjects: list[ModelSpec], model: str | None, effort: str | None) -> list[ModelSpec]:
    if not (model or effort):
        return subjects
    return [
        replace(s, model=model or s.model, params={**s.params, **({"effort": effort} if effort else {})})
        for s in subjects
    ]


def _print_detection(config: EvalConfig, statuses: dict[str, tuple[bool, str]], chosen: list[ModelSpec]) -> None:
    chosen_ids = {s.id for s in chosen}
    print("Detected AI access (tried in this order):")
    for spec in config.models:
        ok, detail = statuses[spec.id]
        marker = "->" if spec.id in chosen_ids else "  "
        state = "ready" if ok else "not available"
        print(f" {marker} {spec.id:<18} {state:<14} {detail}")


def _label(spec: ModelSpec) -> str:
    if spec.provider == "agent-cli":
        base = f"{spec.params.get('profile', 'agent-cli')} CLI"
        model = "" if spec.model in ("", "inherit") else f" {spec.model}"
        text = base + model
    else:
        text = f"{spec.provider}/{spec.model}"
    effort = spec.params.get("effort")
    return text + (f", effort {effort}" if effort else "")


def _load_baseline(path: Path) -> dict[str, float]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {a["subject"]: a["mean_score"] for a in data.get("arms", []) if a.get("arm") == "with-skill"}
