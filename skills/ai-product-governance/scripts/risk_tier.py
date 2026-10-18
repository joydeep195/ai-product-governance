#!/usr/bin/env python3
"""Deterministic AI risk-tier classifier for the ai-product-governance skill.

Evaluates questionnaire answers against a governance policy (policy-as-code) and
reports the risk tier, the rules that triggered it, required controls, approvers,
evaluation minimums and the autonomy cap at launch. The same answers and policy
always produce the same result, so the output is suitable for audit trails.

Standard library only; runs on Python 3.9+.

Policy resolution order:
  1. --policy PATH
  2. the AIPG_POLICY environment variable
  3. .ai-governance/policy.json in the current working directory
  4. the bundled default (../assets/policy/default-policy.json, or a
     default-policy.json next to this script in flattened bundles)

Usage:
  python risk_tier.py --questions
  python risk_tier.py --answers answers.json [--policy policy.json] [--format md]
  python risk_tier.py --answers-json '{"customer_facing": true, ...}'
  python risk_tier.py --validate-policy [--policy policy.json]

Exit codes: 0 success; 2 invalid input or answers; 3 invalid or missing policy.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

POLICY_ENV_VAR = "AIPG_POLICY"
WORKSPACE_POLICY = Path(".ai-governance") / "policy.json"
QUESTION_TYPES = ("boolean", "number", "enum", "multiselect")
LEAF_OPERATORS = ("equals", "in", "contains_any", "gte", "lte")


class PolicyError(ValueError):
    """The policy file is missing or invalid."""


class AnswerError(ValueError):
    """The questionnaire answers are invalid for the policy."""


# --------------------------------------------------------------------------- policy


def bundled_policy_candidates() -> List[Path]:
    here = Path(__file__).resolve().parent
    return [
        here.parent / "assets" / "policy" / "default-policy.json",
        here / "default-policy.json",
    ]


def resolve_policy_path(explicit: Optional[str] = None, cwd: Optional[Path] = None) -> Tuple[Path, str]:
    """Return the policy path to use and a human-readable description of its source."""
    if explicit:
        return Path(explicit), "--policy argument"
    from_env = os.environ.get(POLICY_ENV_VAR)
    if from_env:
        return Path(from_env), f"{POLICY_ENV_VAR} environment variable"
    workspace = (cwd or Path.cwd()) / WORKSPACE_POLICY
    if workspace.is_file():
        return workspace, "workspace policy (.ai-governance/policy.json)"
    for candidate in bundled_policy_candidates():
        if candidate.is_file():
            return candidate, "bundled default policy"
    raise PolicyError("No policy file found. Pass --policy or set AIPG_POLICY.")


def load_policy(path: Path) -> Dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as handle:
            policy = json.load(handle)
    except FileNotFoundError as exc:
        raise PolicyError(f"Policy file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PolicyError(f"Policy file is not valid JSON ({path}): {exc}") from exc
    problems = validate_policy(policy)
    if problems:
        raise PolicyError("Invalid policy:\n- " + "\n- ".join(problems))
    return policy


def _check_condition(condition: Any, questions: Dict[str, Dict[str, Any]], where: str, problems: List[str]) -> None:
    if not isinstance(condition, dict) or not condition:
        problems.append(f"{where}: condition must be a non-empty object")
        return
    if "all" in condition or "any" in condition:
        key = "all" if "all" in condition else "any"
        items = condition[key]
        if len(condition) != 1 or not isinstance(items, list) or not items:
            problems.append(f"{where}: '{key}' must be the only key and hold a non-empty list")
            return
        for index, item in enumerate(items):
            _check_condition(item, questions, f"{where}.{key}[{index}]", problems)
        return
    question_id = condition.get("question")
    operators = [op for op in LEAF_OPERATORS if op in condition]
    if question_id not in questions:
        problems.append(f"{where}: unknown question '{question_id}'")
        return
    if len(operators) != 1 or len(condition) != 2:
        problems.append(f"{where}: needs 'question' plus exactly one of {', '.join(LEAF_OPERATORS)}")
        return
    operator = operators[0]
    question = questions[question_id]
    qtype = question.get("type")
    value = condition[operator]
    options = question.get("options") or []
    if operator in ("gte", "lte") and qtype != "number":
        problems.append(f"{where}: '{operator}' only applies to number questions")
    if operator in ("equals", "in") and qtype == "multiselect":
        problems.append(f"{where}: use 'contains_any' for multiselect question '{question_id}'")
    if operator == "contains_any":
        if qtype != "multiselect":
            problems.append(f"{where}: 'contains_any' only applies to multiselect questions")
        elif any(v not in options for v in value):
            problems.append(f"{where}: 'contains_any' lists values that are not options of '{question_id}'")
    if operator == "in" and qtype == "enum" and any(v not in options for v in value):
        problems.append(f"{where}: 'in' lists values that are not options of '{question_id}'")
    if operator == "equals":
        if qtype == "boolean" and not isinstance(value, bool):
            problems.append(f"{where}: '{question_id}' is boolean; 'equals' must be true or false")
        if qtype == "enum" and value not in options:
            problems.append(f"{where}: '{value}' is not an option of '{question_id}'")


def validate_policy(policy: Any) -> List[str]:
    """Structural and referential checks. Returns a list of problems (empty when valid)."""
    problems: List[str] = []
    if not isinstance(policy, dict):
        return ["policy must be a JSON object"]
    for key in (
        "policy_id",
        "version",
        "name",
        "default_tier",
        "autonomy_levels",
        "tiers",
        "questions",
        "rules",
        "controls",
    ):
        if key not in policy:
            problems.append(f"missing required key '{key}'")
    if problems:
        return problems

    levels = [level.get("id") for level in policy["autonomy_levels"]]
    controls = {control.get("id") for control in policy["controls"]}
    if len(controls) != len(policy["controls"]):
        problems.append("control IDs must be unique")

    tiers: Dict[str, Dict[str, Any]] = {}
    ranks = set()
    for tier in policy["tiers"]:
        tier_id = tier.get("id")
        if tier_id in tiers:
            problems.append(f"duplicate tier id '{tier_id}'")
        tiers[tier_id] = tier
        if tier.get("rank") in ranks:
            problems.append(f"duplicate tier rank {tier.get('rank')}")
        ranks.add(tier.get("rank"))
        for control_id in tier.get("required_controls", []):
            if control_id not in controls:
                problems.append(f"tier '{tier_id}' requires unknown control '{control_id}'")
        cap = tier.get("max_autonomy_at_launch")
        if cap is not None and cap not in levels:
            problems.append(f"tier '{tier_id}' has unknown autonomy cap '{cap}'")
    if policy["default_tier"] not in tiers:
        problems.append(f"default_tier '{policy['default_tier']}' is not a defined tier")

    questions: Dict[str, Dict[str, Any]] = {}
    for question in policy["questions"]:
        question_id = question.get("id")
        if question_id in questions:
            problems.append(f"duplicate question id '{question_id}'")
        questions[question_id] = question
        if question.get("type") not in QUESTION_TYPES:
            problems.append(f"question '{question_id}' has unknown type '{question.get('type')}'")
        if question.get("type") in ("enum", "multiselect") and not question.get("options"):
            problems.append(f"question '{question_id}' needs options")

    seen_rules = set()
    for rule in policy["rules"]:
        rule_id = rule.get("id")
        if rule_id in seen_rules:
            problems.append(f"duplicate rule id '{rule_id}'")
        seen_rules.add(rule_id)
        if rule.get("tier") not in tiers:
            problems.append(f"rule '{rule_id}' points to unknown tier '{rule.get('tier')}'")
        _check_condition(rule.get("when"), questions, f"rule '{rule_id}'", problems)

    for index, conditional in enumerate(policy.get("conditional_controls", [])):
        if conditional.get("control") not in controls:
            problems.append(f"conditional control #{index} references unknown control '{conditional.get('control')}'")
        _check_condition(
            conditional.get("when"), questions, f"conditional control '{conditional.get('control')}'", problems
        )
    return problems


# --------------------------------------------------------------------------- answers


def validate_answers(policy: Dict[str, Any], answers: Any) -> Tuple[Dict[str, Any], List[str]]:
    """Return (normalised answers, unanswered question IDs). Raises AnswerError on invalid input."""
    if not isinstance(answers, dict):
        raise AnswerError("answers must be a JSON object mapping question IDs to values")
    questions = {question["id"]: question for question in policy["questions"]}
    errors: List[str] = []
    unknown = sorted(set(answers) - set(questions))
    if unknown:
        errors.append(f"unknown question IDs: {', '.join(unknown)} (run --questions to list valid IDs)")
    normalised: Dict[str, Any] = {}
    for question_id, value in answers.items():
        question = questions.get(question_id)
        if question is None or value is None:
            continue
        qtype = question["type"]
        options = question.get("options") or []
        if qtype == "boolean":
            if not isinstance(value, bool):
                errors.append(f"'{question_id}' must be true or false")
                continue
        elif qtype == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                errors.append(f"'{question_id}' must be a non-negative number")
                continue
        elif qtype == "enum":
            if value not in options:
                errors.append(f"'{question_id}' must be one of: {', '.join(options)}")
                continue
        elif qtype == "multiselect":
            if isinstance(value, str):
                value = [value]
            if not isinstance(value, list) or any(item not in options for item in value):
                errors.append(f"'{question_id}' must be a list drawn from: {', '.join(options)}")
                continue
            if "none" in value and len(value) > 1:
                errors.append(f"'{question_id}' cannot combine 'none' with other options")
                continue
        normalised[question_id] = value
    if errors:
        raise AnswerError("; ".join(errors))
    unanswered = [question_id for question_id in questions if question_id not in normalised]
    return normalised, unanswered


def evaluate_condition(condition: Dict[str, Any], answers: Dict[str, Any]) -> Optional[bool]:
    """Three-valued evaluation: True, False, or None when an unanswered question decides it."""
    if "all" in condition:
        results = [evaluate_condition(item, answers) for item in condition["all"]]
        if any(result is False for result in results):
            return False
        return True if all(result is True for result in results) else None
    if "any" in condition:
        results = [evaluate_condition(item, answers) for item in condition["any"]]
        if any(result is True for result in results):
            return True
        return False if all(result is False for result in results) else None
    question_id = condition["question"]
    if question_id not in answers:
        return None
    value = answers[question_id]
    if "equals" in condition:
        return bool(value == condition["equals"])
    if "in" in condition:
        return value in condition["in"]
    if "contains_any" in condition:
        return bool(set(value) & set(condition["contains_any"]))
    if "gte" in condition:
        return bool(value >= condition["gte"])
    if "lte" in condition:
        return bool(value <= condition["lte"])
    raise PolicyError(f"Unsupported condition: {condition}")


# --------------------------------------------------------------------------- classification


def classify(
    policy: Dict[str, Any],
    answers: Dict[str, Any],
    policy_source: str = "in-memory policy",
    policy_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Classify answers against the policy and return a JSON-serialisable result."""
    normalised, unanswered = validate_answers(policy, answers)
    tiers = {tier["id"]: tier for tier in policy["tiers"]}
    controls = {control["id"]: control for control in policy["controls"]}
    levels = [level["id"] for level in policy["autonomy_levels"]]

    triggered: List[Dict[str, Any]] = []
    undetermined: List[Dict[str, Any]] = []
    for rule in policy["rules"]:
        outcome = evaluate_condition(rule["when"], normalised)
        entry = {"id": rule["id"], "tier": rule["tier"], "reason": rule["reason"]}
        if outcome is True:
            triggered.append(entry)
        elif outcome is None:
            undetermined.append(entry)

    tier = tiers[policy["default_tier"]]
    for entry in triggered:
        if tiers[entry["tier"]]["rank"] > tier["rank"]:
            tier = tiers[entry["tier"]]

    could_rise_to = None
    for entry in undetermined:
        candidate = tiers[entry["tier"]]
        if candidate["rank"] > tier["rank"] and (could_rise_to is None or candidate["rank"] > could_rise_to["rank"]):
            could_rise_to = candidate

    required: List[Dict[str, Any]] = []
    seen = set()

    def add_control(control_id: str, required_by: str) -> None:
        if control_id in seen:
            return
        seen.add(control_id)
        control = controls[control_id]
        required.append(
            {
                "id": control_id,
                "name": control["name"],
                "description": control["description"],
                "evidence": control["evidence"],
                "required_by": required_by,
            }
        )

    prohibited = bool(tier.get("prohibited", False))
    if not prohibited:
        for control_id in tier.get("required_controls", []):
            add_control(control_id, f"tier: {tier['id']}")
        for conditional in policy.get("conditional_controls", []):
            if evaluate_condition(conditional["when"], normalised) is True:
                add_control(conditional["control"], f"condition: {conditional['reason']}")

    cap = tier.get("max_autonomy_at_launch")
    requested = normalised.get("autonomy_level")
    within_cap: Optional[bool] = None
    if cap is not None and isinstance(requested, str) and requested in levels:
        within_cap = levels.index(requested) <= levels.index(cap)

    notes: List[str] = []
    if prohibited:
        notes.append("This use case falls in a prohibited tier. Stop the work; there is no approval path.")
    if unanswered:
        notes.append("Some questions are unanswered. Answering them can only keep or raise the tier.")
    if within_cap is False:
        notes.append(
            f"Planned autonomy {requested} exceeds the launch cap {cap} for the {tier['name']} tier. "
            f"Launch at {cap} or lower and promote with evidence."
        )

    return {
        "policy": {
            "id": policy["policy_id"],
            "version": policy["version"],
            "name": policy["name"],
            "source": policy_source,
            "path": policy_path,
        },
        "tier": {
            "id": tier["id"],
            "name": tier["name"],
            "rank": tier["rank"],
            "description": tier.get("description", ""),
        },
        "prohibited": prohibited,
        "triggered_rules": triggered,
        "complete": not unanswered,
        "unanswered_questions": unanswered,
        "tier_could_rise_to": None if could_rise_to is None else could_rise_to["id"],
        "max_autonomy_at_launch": cap,
        "planned_autonomy": requested,
        "planned_autonomy_within_cap": within_cap,
        "required_controls": required,
        "approvers": list(tier.get("approvers", [])),
        "eval_requirements": tier.get("eval_requirements"),
        "recertification_months": tier.get("recertification_months"),
        "autonomy_promotion": policy.get("autonomy_promotion"),
        "notes": notes,
    }


# --------------------------------------------------------------------------- rendering


def render_markdown(result: Dict[str, Any]) -> str:
    policy = result["policy"]
    tier = result["tier"]
    lines = [
        f"**Risk tier: {tier['name']}** | Policy: {policy['id']} v{policy['version']} ({policy['source']})",
        "",
    ]
    if result["triggered_rules"]:
        lines += ["| Rule | Tier | Reason |", "|---|---|---|"]
        lines += [f"| {r['id']} | {r['tier']} | {r['reason']} |" for r in result["triggered_rules"]]
    else:
        lines.append(f"No rule triggered; default tier `{tier['id']}` applies.")
    lines.append("")
    if result["unanswered_questions"]:
        lines.append("**Unanswered questions:** " + ", ".join(f"`{q}`" for q in result["unanswered_questions"]))
        if result["tier_could_rise_to"]:
            lines.append(f"Depending on those answers the tier could rise to **{result['tier_could_rise_to']}**.")
        lines.append("")
    if not result["prohibited"]:
        cap = result["max_autonomy_at_launch"]
        planned = result["planned_autonomy"] or "not stated"
        lines.append(f"**Autonomy:** planned {planned}; maximum at launch {cap}.")
        lines += ["", "| Control | Name | Required by | Evidence |", "|---|---|---|---|"]
        lines += [
            f"| {c['id']} | {c['name']} | {c['required_by']} | {c['evidence']} |" for c in result["required_controls"]
        ]
        lines += ["", "**Approvers:** " + ", ".join(result["approvers"])]
        evals = result["eval_requirements"] or {}
        if evals:
            lines.append(
                "**Eval minimums:** golden set >= {golden_set_min}, pass rate >= {rate:.0%}, critical failures <= {critical_failures_max}".format(
                    rate=evals["pass_rate_min"], **evals
                )
            )
        lines.append(f"**Re-certification:** every {result['recertification_months']} months")
    for note in result["notes"]:
        lines += ["", f"> {note}"]
    return "\n".join(lines) + "\n"


def render_questions(policy: Dict[str, Any], fmt: str) -> str:
    if fmt == "json":
        return json.dumps(policy["questions"], indent=2) + "\n"
    lines = ["| ID | Type | Question | Options |", "|---|---|---|---|"]
    for question in policy["questions"]:
        options = ", ".join(question.get("options", [])) or "-"
        lines.append(f"| `{question['id']}` | {question['type']} | {question['text']} | {options} |")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- CLI


def _read_json_argument(path: Optional[str], inline: Optional[str]) -> Any:
    if inline is not None:
        return json.loads(inline)
    if path == "-":
        return json.load(sys.stdin)
    with open(str(path), encoding="utf-8") as handle:
        return json.load(handle)


def _never_crash_on_encoding() -> None:
    """Policies may contain characters the console cannot encode (e.g. cp1252 on Windows)."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        with contextlib.suppress(ValueError, OSError):
            reconfigure(errors="replace")


def main(argv: Optional[List[str]] = None) -> int:
    _never_crash_on_encoding()
    parser = argparse.ArgumentParser(description="Classify an AI use case into a governance risk tier.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--answers", metavar="FILE", help="JSON file with questionnaire answers ('-' for stdin)")
    source.add_argument("--answers-json", metavar="JSON", help="questionnaire answers as an inline JSON object")
    source.add_argument("--questions", action="store_true", help="print the policy questionnaire")
    source.add_argument("--validate-policy", action="store_true", help="validate the policy and exit")
    parser.add_argument("--policy", metavar="FILE", help="policy file (default: see module docstring)")
    parser.add_argument("--format", choices=("json", "md"), default="json", help="output format")
    args = parser.parse_args(argv)

    try:
        path, source_label = resolve_policy_path(args.policy)
        policy = load_policy(path)
    except PolicyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    if args.validate_policy:
        print(f"Policy {policy['policy_id']} v{policy['version']} is valid ({source_label}: {path}).")
        return 0
    if args.questions:
        sys.stdout.write(render_questions(policy, args.format))
        return 0
    if args.answers is None and args.answers_json is None:
        parser.error("provide --answers, --answers-json, --questions or --validate-policy")

    try:
        answers = _read_json_argument(args.answers, args.answers_json)
        result = classify(policy, answers, policy_source=source_label, policy_path=str(path))
    except (OSError, json.JSONDecodeError, AnswerError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.format == "md":
        sys.stdout.write(render_markdown(result))
    else:
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
