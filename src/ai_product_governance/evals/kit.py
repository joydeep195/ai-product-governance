"""Manual eval kit: run the eval suite with any chat-based AI tool, no automation needed.

For tools that cannot be driven from a script (ChatGPT, Gemini, Microsoft 365 Copilot, Claude
apps, ...) the kit turns the suite into copy-and-paste steps:

  1. `aipg eval-kit create` writes a run sheet of prompts and empty answer files. Paste each
     prompt into a new chat (with the skill on for part A, off for part B) and save the answers.
  2. `aipg eval-kit grade <kit>` writes blind grading prompts in shuffled order. Paste each into a
     new chat without the skill and save the JSON replies.
  3. `aipg eval-kit score <kit>` scores everything offline with the same rubric, deterministic
     checks, gates and report formats as automated runs.

One AI tool does everything. No API key, CLI or scripting is involved.

In agent-run mode (`aipg eval-kit create --agent-run`) the user's own agent does the pasting, as
the skill's `references/evaluate-this-skill.md` describes. Every file in `prompts/` and then
`grading/` is a complete task: the arm's access rules, the request, and the file to save the
reply in. The agent sends each fresh sub-agent one line ("Read `<task>` and do exactly what it
says.") and never relays long prompts or replies itself. The report labels such runs as
agent-run, because nothing outside the tool verifies that the baseline sub-agents could not see
the skill.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_product_governance import __version__
from ai_product_governance.evals.agent_cli import extract_json_object
from ai_product_governance.evals.config import EvalConfig
from ai_product_governance.evals.judge import JUDGE_SYSTEM, judge_prompt, parse_verdicts
from ai_product_governance.evals.report import write_reports
from ai_product_governance.evals.runner import tree_hash
from ai_product_governance.evals.scenarios import Scenario
from ai_product_governance.evals.scoring import (
    GateResult,
    TrialResult,
    evaluate_gates,
    score_trial,
    summarise,
    summarise_arms,
)
from ai_product_governance.skill import Skill

PASTE_MARKER = "<!-- Paste the complete reply BELOW this line. Do not edit this line. -->"
ARM_TITLES = {"with-skill": "WITH the skill", "baseline": "WITHOUT the skill"}
JSON_REPLY_FORMAT = (
    "Reply with only a JSON object in exactly this shape, with one entry for every criterion id:\n"
    '{"verdicts": [{"id": "C1", "verdict": "pass", "evidence": "short quote", "rationale": "one sentence"}]}\n'
    'Use "pass" or "fail" for each verdict.'
)


MANUAL, AGENT_RUN = "manual", "agent-run"
MODES = (MANUAL, AGENT_RUN)
REPORT_MODES = {MANUAL: "manual eval kit", AGENT_RUN: "agent-run eval kit"}


# The one line the user's agent sends to each fresh sub-agent. Everything else is in the task file, so the agent
# never relays long prompts or replies by hand.
SUB_AGENT_MESSAGE = "Read `{task}` and do exactly what it says."


def agent_run_preamble(arm: str, skill_root: Path) -> str:
    """The access rules a sub-agent gets, so both arms differ only in access to the skill."""
    if arm == "with-skill":
        return (
            f"You have the AI Product Governance Agent Skill at `{skill_root.as_posix()}`. Read its `SKILL.md` first "
            "and use it as it instructs: its playbooks, templates and scripts. Apart from this file and that skill "
            "folder, do not read any file."
        )
    return (
        "Answer from your own knowledge. Apart from reading this file and writing your answer where it says, do not "
        "read files, run commands, search, or use any skill, plugin or tool."
    )


GRADER_PREAMBLE = (
    "Grade only the text in this file. Apart from reading this file and writing your reply where it says, do not "
    "read files, run commands, search, or use any skill or tool."
)


def _task_file(preamble: str, body: str, reply_path: Path, what: str) -> str:
    return (
        f"{preamble}\n\n{body}\n\n## When you finish\n\n"
        f"Write {what} into `{reply_path.as_posix()}`, replacing everything in that file, exactly as you would reply. "
        "Then reply with just: saved\n"
    )


class KitError(ValueError):
    """The kit is incomplete or malformed."""


@dataclass(frozen=True)
class KitItem:
    id: str
    scenario: str
    arm: str
    trial: int


def create_kit(
    kit_root: Path,
    config: EvalConfig,
    skill: Skill,
    scenarios: list[Scenario],
    trials: int = 1,
    tool: str = "",
    mode: str = MANUAL,
) -> Path:
    if mode not in MODES:
        raise KitError(f"Unknown kit mode '{mode}'. Available: {', '.join(MODES)}")
    kit_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    kit_dir = kit_root / kit_id
    (kit_dir / "answers").mkdir(parents=True)
    items = [
        KitItem(f"A{index:02d}", scenario.id, arm, trial)
        for index, (arm, scenario, trial) in enumerate(
            ((arm, s, t) for arm in config.arms for s in scenarios for t in range(1, trials + 1)), start=1
        )
    ]
    by_id = {s.id: s for s in scenarios}
    manifest = {
        "kit_id": kit_id,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "package_version": __version__,
        "skill_version": skill.version,
        "skill_sha256": tree_hash(skill.root),
        "tool": tool or ("agent-run (unnamed tool)" if mode == AGENT_RUN else "manual (any chat tool)"),
        "mode": mode,
        "trials": trials,
        "arms": list(config.arms),
        "scenarios": [s.id for s in scenarios],
        "answers": [item.__dict__ for item in items],
        "grading": [],
    }
    _write(kit_dir / "kit.json", json.dumps(manifest, indent=2) + "\n")
    for item in items:
        _write(kit_dir / "answers" / f"{item.id}.md", PASTE_MARKER + "\n\n")
    if mode == AGENT_RUN:
        (kit_dir / "prompts").mkdir()
        for item in items:
            request = f"## The request\n\n{config.baseline_system_prompt}\n\n{by_id[item.scenario].prompt}"
            answer = (kit_dir / "answers" / f"{item.id}.md").resolve()
            preamble = agent_run_preamble(item.arm, skill.root.resolve())
            _write(kit_dir / "prompts" / f"{item.id}.md", _task_file(preamble, request, answer, "your complete answer"))
        tasks = [(kit_dir / "prompts" / f"{item.id}.md").resolve() for item in items]
        _write(kit_dir / "1-ANSWERS.md", _agent_run_sheet(kit_id, kit_dir, tasks, "answers", "grade"))
        return kit_dir

    lines = [
        f"# Eval kit {kit_id}, step 1 of 3: collect answers",
        "",
        "You need one AI chat tool; any tool works. For **every** item, start a **new chat**, paste the prompt,",
        "then paste the complete reply into the named file, below the marker line.",
        "",
    ]
    for arm in config.arms:
        arm_items = [item for item in items if item.arm == arm]
        if not arm_items:
            continue
        where = (
            "a chat where the AI Product Governance skill is active (the skill itself, the prompt pack's custom GPT "
            "or project, or the MCP server)"
            if arm == "with-skill"
            else "a plain chat in the same tool with the skill switched off"
        )
        lines += [f"## Part {'A' if arm == 'with-skill' else 'B'}: {ARM_TITLES[arm]}", "", f"Use {where}.", ""]
        for item in arm_items:
            scenario = by_id[item.scenario]
            prompt = f"{config.baseline_system_prompt}\n\n{scenario.prompt}"
            fence = "`" * max(3, _longest_backtick_run(prompt) + 1)
            trial_note = f" (trial {item.trial})" if trials > 1 else ""
            lines += [
                f"### {item.id} | {ARM_TITLES[item.arm]} | {scenario.title}{trial_note}",
                "",
                f"Save the reply in `answers/{item.id}.md`.",
                "",
                f"{fence}text",
                prompt,
                fence,
                "",
            ]
    lines += ["---", "", f"When every answer file is filled in, run `aipg eval-kit grade {kit_dir.as_posix()}`.", ""]
    _write(kit_dir / "1-ANSWERS.md", "\n".join(lines))
    return kit_dir


def prepare_grading(kit_dir: Path, scenarios: list[Scenario]) -> Path:
    manifest = _load(kit_dir)
    items = [KitItem(**entry) for entry in manifest["answers"]]
    missing = [item.id for item in items if not read_reply(kit_dir / "answers" / f"{item.id}.md")]
    if missing:
        raise KitError("These answers are still empty: " + ", ".join(missing))
    by_id = {s.id: s for s in scenarios}
    order = list(items)
    random.Random(manifest["kit_id"]).shuffle(order)  # noqa: S311 - shuffling for blinding, not security
    grading = [{"id": f"G{index:02d}", "answer": item.id} for index, item in enumerate(order, start=1)]
    (kit_dir / "verdicts").mkdir(exist_ok=True)
    agent_run = manifest.get("mode") == AGENT_RUN
    if agent_run:
        (kit_dir / "grading").mkdir(exist_ok=True)
    lines = [
        f"# Eval kit {manifest['kit_id']}, step 2 of 3: grade the answers",
        "",
        "Use the same AI tool. For **every** item, start a **new chat with the skill switched off**, paste the whole",
        "grading prompt, then paste the reply into the named file, below the marker line. The items are shuffled so",
        "the grader cannot tell which answers used the skill.",
        "",
    ]
    for entry in grading:
        item = next(i for i in items if i.id == entry["answer"])
        scenario = by_id[item.scenario]
        response = read_reply(kit_dir / "answers" / f"{item.id}.md")
        prompt = f"{JUDGE_SYSTEM}\n{judge_prompt(scenario, response)}\n\n{JSON_REPLY_FORMAT}"
        _write(kit_dir / "verdicts" / f"{entry['id']}.md", PASTE_MARKER + "\n\n")
        if agent_run:
            verdict = (kit_dir / "verdicts" / f"{entry['id']}.md").resolve()
            task = _task_file(GRADER_PREAMBLE, prompt, verdict, "only the JSON object")
            _write(kit_dir / "grading" / f"{entry['id']}.md", task)
        fence = "`" * max(3, _longest_backtick_run(prompt) + 1)
        lines += [
            f"## {entry['id']}",
            "",
            f"Save the reply in `verdicts/{entry['id']}.md`.",
            "",
            f"{fence}text",
            prompt,
            fence,
            "",
        ]
    lines += ["---", "", f"When every verdict file is filled in, run `aipg eval-kit score {kit_dir.as_posix()}`.", ""]
    if agent_run:
        tasks = [(kit_dir / "grading" / f"{entry['id']}.md").resolve() for entry in grading]
        _write(kit_dir / "2-GRADING.md", _agent_run_sheet(manifest["kit_id"], kit_dir, tasks, "verdicts", "score"))
    else:
        _write(kit_dir / "2-GRADING.md", "\n".join(lines))
    manifest["grading"] = grading
    _write(kit_dir / "kit.json", json.dumps(manifest, indent=2) + "\n")
    return kit_dir / "2-GRADING.md"


def score_kit(
    kit_dir: Path, config: EvalConfig, skill: Skill, scenarios: list[Scenario]
) -> tuple[dict[str, Path], list[GateResult]]:
    manifest = _load(kit_dir)
    if not manifest.get("grading"):
        raise KitError(f"Grading has not been prepared yet: run `aipg eval-kit grade {kit_dir.as_posix()}` first.")
    items = {entry["id"]: KitItem(**entry) for entry in manifest["answers"]}
    by_id = {s.id: s for s in scenarios}
    tool = str(manifest.get("tool", "manual"))
    mode = str(manifest.get("mode", MANUAL))
    trials: list[TrialResult] = []
    problems = []
    for entry in manifest["grading"]:
        item = items[entry["answer"]]
        scenario = by_id[item.scenario]
        reply = read_reply(kit_dir / "verdicts" / f"{entry['id']}.md")
        payload: Any = extract_json_object(reply) if reply else None
        if payload is None:
            problems.append(entry["id"])
            continue
        response = read_reply(kit_dir / "answers" / f"{item.id}.md")
        verdicts = parse_verdicts(scenario, payload)
        score, passed, critical, results = score_trial(scenario, response, verdicts, config.pass_threshold)
        trials.append(
            TrialResult(
                tool, scenario.id, item.arm, item.trial, score, passed, critical, results, response, served_model=tool
            )
        )
    if problems:
        raise KitError("These verdict files are empty or contain no JSON object: " + ", ".join(sorted(problems)))
    trials.sort(key=lambda t: (t.scenario, t.arm, t.trial))
    cells = summarise(trials)
    arms = summarise_arms(cells)
    gates = evaluate_gates(arms, config.gates)
    report_manifest = {
        "run_id": manifest["kit_id"],
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "package_version": __version__,
        "skill_version": manifest.get("skill_version", skill.version),
        "skill_sha256": manifest.get("skill_sha256", ""),
        "scenarios": manifest["scenarios"],
        "subjects": [{"id": tool, "provider": mode, "model": tool, "effort": None}],
        "judge": {"id": f"{tool}-judge", "provider": mode, "model": tool, "effort": None},
        "judges": {tool: {"id": f"{tool}-judge", "provider": mode, "model": tool, "effort": None}},
        "arms": manifest["arms"],
        "trials": manifest["trials"],
        "mode": REPORT_MODES.get(mode, REPORT_MODES[MANUAL]),
    }
    paths = write_reports(kit_dir / "report", report_manifest, trials, cells, arms, gates, [], None)
    return paths, gates


def kit_mode(kit_dir: Path) -> str:
    """The kit's mode: `manual` (copy and paste) or `agent-run` (an agent drives fresh sub-agents)."""
    return str(_load(kit_dir).get("mode", MANUAL))


def read_reply(path: Path) -> str:
    """The text pasted below the marker line (or the whole file if the marker was removed)."""
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")
    if PASTE_MARKER in text:
        text = text.split(PASTE_MARKER, 1)[1]
    return text.strip()


def _load(kit_dir: Path) -> dict[str, Any]:
    path = kit_dir / "kit.json"
    if not path.is_file():
        raise KitError(f"{kit_dir} is not an eval kit (no kit.json)")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _agent_run_sheet(kit_id: str, kit_dir: Path, tasks: list[Path], replies: str, next_step: str) -> str:
    step, title = ("1", "collect answers") if replies == "answers" else ("2", "grade the answers")
    lines = [
        f"# Eval kit {kit_id}, step {step} of 3: {title} (agent-run)",
        "",
        "Start one **fresh sub-agent** per line below and send it that line, exactly, and nothing else. Each task file",
        f"says what the sub-agent may use and where it saves its reply (in `{replies}/`). Never do a task yourself and",
        "never edit a reply; if a sub-agent fails or leaves its file empty, start a new one with the same line.",
        "",
        "The full procedure is in the skill's `references/evaluate-this-skill.md`.",
        "",
        *(f"- {SUB_AGENT_MESSAGE.format(task=task.as_posix())}" for task in tasks),
        "",
        "---",
        "",
        f"When every file in `{replies}/` is filled in, run `aipg eval-kit {next_step} {kit_dir.as_posix()}`.",
        "",
    ]
    return "\n".join(lines)


def _longest_backtick_run(text: str) -> int:
    longest = current = 0
    for char in text:
        current = current + 1 if char == "`" else 0
        longest = max(longest, current)
    return longest


def _write(path: Path, content: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
