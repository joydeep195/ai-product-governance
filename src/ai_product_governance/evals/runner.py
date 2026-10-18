"""Run the eval matrix: subjects x scenarios x arms x trials."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from ai_product_governance import __version__
from ai_product_governance.evals.config import EvalConfig, ModelSpec
from ai_product_governance.evals.judge import grade
from ai_product_governance.evals.providers import Provider, ProviderError, Usage, create_provider
from ai_product_governance.evals.runtime import TOOLS, SkillRuntime
from ai_product_governance.evals.scenarios import Scenario
from ai_product_governance.evals.scoring import TrialResult, failed_trial, score_trial
from ai_product_governance.skill import Skill

ProviderFactory = Callable[[ModelSpec], Provider]

# Rough planning numbers for dry runs; real costs are measured from API usage.
_EST_OUTPUT_TOKENS = 4000
_EST_SKILL_CONTEXT_TOKENS = 12000
_EST_JUDGE_OUTPUT_TOKENS = 1200


@dataclass(frozen=True)
class Job:
    subject: ModelSpec
    scenario: Scenario
    arm: str
    trial: int


@dataclass
class RunOutcome:
    run_id: str
    trials: list[TrialResult]
    skipped: list[str] = field(default_factory=list)
    total_cost_usd: float | None = 0.0
    manifest: dict[str, Any] = field(default_factory=dict)


def plan_jobs(
    config: EvalConfig, subjects: list[ModelSpec], scenarios: list[Scenario], arms: list[str], trials: int
) -> list[Job]:
    return [
        Job(subject, scenario, arm, trial)
        for subject in subjects
        for scenario in scenarios
        for arm in arms
        for trial in range(1, trials + 1)
    ]


def estimate_cost(config: EvalConfig, skill: Skill, jobs: list[Job]) -> tuple[float | None, dict[str, Any]]:
    """Order-of-magnitude estimate for a dry run (characters / 4 tokens, fixed output assumptions)."""
    skill_tokens = len(skill.clean_body) // 4 + _EST_SKILL_CONTEXT_TOKENS
    judge_price = config.price(config.judge.model)
    total: float | None = 0.0
    for job in jobs:
        prompt_tokens = len(job.scenario.prompt) // 4
        gen = Usage(
            input_tokens=prompt_tokens + (skill_tokens if job.arm == "with-skill" else 300),
            output_tokens=_EST_OUTPUT_TOKENS,
        )
        judge = Usage(input_tokens=prompt_tokens + _EST_OUTPUT_TOKENS + 800, output_tokens=_EST_JUDGE_OUTPUT_TOKENS)
        gen_cost, judge_cost = gen.cost(config.price(job.subject.model)), judge.cost(judge_price)
        if total is None or gen_cost is None or judge_cost is None:
            total = None
        else:
            total += gen_cost + judge_cost
    return total, {"jobs": len(jobs), "assumed_output_tokens": _EST_OUTPUT_TOKENS}


def run_jobs(
    config: EvalConfig,
    skill: Skill,
    jobs: list[Job],
    *,
    max_cost_usd: float | None = None,
    provider_factory: ProviderFactory = create_provider,
    progress: Callable[[str], None] = print,
) -> RunOutcome:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    providers: dict[str, Provider] = {}
    lock = threading.Lock()
    spent: list[float | None] = [0.0]
    skipped: list[str] = []
    judge = provider_factory(config.judge)

    def provider_for(spec: ModelSpec) -> Provider:
        with lock:
            if spec.id not in providers:
                providers[spec.id] = provider_factory(spec)
            return providers[spec.id]

    def execute(job: Job) -> TrialResult | None:
        label = f"{job.subject.id} | {job.scenario.id} | {job.arm} | trial {job.trial}"
        with lock:
            current = spent[0]
            if max_cost_usd is not None and current is not None and current >= max_cost_usd:
                skipped.append(label)
                return None
        result = run_trial(config, skill, job, provider_for(job.subject), judge)
        with lock:
            if spent[0] is not None:
                spent[0] = None if result.cost_usd is None else spent[0] + result.cost_usd
        status = "ERROR " + result.error if result.error else f"score {result.score:.2f}"
        progress(f"{label}: {status}")
        return result

    with ThreadPoolExecutor(max_workers=config.concurrency) as pool:
        results = [r for r in pool.map(execute, jobs) if r is not None]
    order = {(j.subject.id, j.scenario.id, j.arm, j.trial): i for i, j in enumerate(jobs)}
    results.sort(key=lambda r: order[(r.subject, r.scenario, r.arm, r.trial)])
    return RunOutcome(run_id=run_id, trials=results, skipped=skipped, total_cost_usd=spent[0])


def run_trial(config: EvalConfig, skill: Skill, job: Job, subject: Provider, judge: Provider) -> TrialResult:
    runtime = SkillRuntime(skill)
    if job.arm == "with-skill":
        system, tools, executor = runtime.system_prompt(), TOOLS, runtime.execute
    else:
        system, tools = config.baseline_system_prompt, []

        def executor(name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
            return "Error: no tools are available.", True

    try:
        answer = subject.run_agent(system, job.scenario.prompt, tools, executor, config.max_turns)
    except Exception as exc:  # noqa: BLE001 - any provider failure becomes a failed, reported trial
        return failed_trial(job.subject.id, job.scenario, job.arm, job.trial, f"{type(exc).__name__}: {exc}")
    gen_cost = answer.usage.cost(config.price(job.subject.model))
    if answer.error or not answer.text.strip():
        trial = failed_trial(
            job.subject.id, job.scenario, job.arm, job.trial, answer.error or "empty answer", answer.text
        )
        trial.cost_usd, trial.turns = gen_cost, answer.turns
        return trial
    try:
        verdicts, judge_usage = grade(judge, job.scenario, answer.text)
    except (ProviderError, json.JSONDecodeError) as exc:
        trial = failed_trial(job.subject.id, job.scenario, job.arm, job.trial, f"judge failed: {exc}", answer.text)
        trial.cost_usd = gen_cost
        return trial
    except Exception as exc:  # noqa: BLE001
        trial = failed_trial(job.subject.id, job.scenario, job.arm, job.trial, f"judge error: {exc}", answer.text)
        trial.cost_usd = gen_cost
        return trial

    score, passed, critical, items = score_trial(job.scenario, answer.text, verdicts, config.pass_threshold)
    judge_cost = judge_usage.cost(config.price(config.judge.model))
    routing: dict[str, bool] = {}
    if job.arm == "with-skill":
        routing = {f"read {path}": path in runtime.files_read for path in job.scenario.expected_reads}
        routing.update({f"ran {script}": script in runtime.scripts_run for script in job.scenario.expected_scripts})
    return TrialResult(
        subject=job.subject.id,
        scenario=job.scenario.id,
        arm=job.arm,
        trial=job.trial,
        score=score,
        passed=passed,
        critical_failures=critical,
        items=items,
        response=answer.text,
        files_read=list(runtime.files_read),
        scripts_run=list(runtime.scripts_run),
        routing=routing,
        cost_usd=None if gen_cost is None or judge_cost is None else gen_cost + judge_cost,
        input_tokens=answer.usage.input_tokens,
        output_tokens=answer.usage.output_tokens,
        turns=answer.turns,
        served_model=answer.served_model,
    )


def build_manifest(
    config: EvalConfig,
    skill: Skill,
    scenarios: list[Scenario],
    outcome: RunOutcome,
    arms: list[str],
    trials: int,
    subjects: list[ModelSpec],
) -> dict[str, Any]:
    return {
        "run_id": outcome.run_id,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "package_version": __version__,
        "skill_version": skill.version,
        "skill_sha256": _tree_hash(skill.root),
        "config_sha256": hashlib.sha256(config.path.read_bytes()).hexdigest(),
        "scenarios": [s.id for s in scenarios],
        "subjects": [{"id": s.id, "provider": s.provider, "model": s.model} for s in subjects],
        "judge": {"provider": config.judge.provider, "model": config.judge.model},
        "arms": arms,
        "trials": trials,
        "git_commit": _git_commit(skill.root),
        "python": platform.python_version(),
        "sdk_versions": {name: _version(name) for name in ("anthropic", "openai", "mcp")},
    }


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()


def _git_commit(start: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607 - fixed, argument-free git call resolved from PATH
            cwd=start,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None if completed.returncode == 0 else None


def _version(package: str) -> str | None:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None
