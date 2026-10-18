#!/usr/bin/env python3
"""Unit economics calculator for AI features (ai-product-governance skill).

Prices an AI feature per *completed* task: model cost, human review time and the
expected cost of finishing the tasks the AI gets wrong. Reports savings against
today's baseline, payback, the break-even success rate and a sensitivity table.

Standard library only; runs on Python 3.9+.

Usage:
  python unit_economics.py --example > inputs.json
  python unit_economics.py --input inputs.json [--format md]
  python unit_economics.py --input-json '{"price_input_per_mtok": 3, ...}'

Exit codes: 0 success; 2 invalid input.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import sys
from typing import Any, Dict, List, Optional, Tuple

# name: (required, default, minimum, maximum, description)
FIELDS: Dict[str, Tuple[bool, Optional[float], float, Optional[float], str]] = {
    "price_input_per_mtok": (True, None, 0.0, None, "Price per million input tokens"),
    "price_output_per_mtok": (
        True,
        None,
        0.0,
        None,
        "Price per million output tokens (reasoning tokens are usually billed as output)",
    ),
    "input_tokens_per_call": (True, None, 0.0, None, "Average input tokens per model call"),
    "output_tokens_per_call": (
        True,
        None,
        0.0,
        None,
        "Average output tokens per model call, including reasoning tokens",
    ),
    "tasks_per_month": (True, None, 0.0, None, "Expected tasks per month"),
    "success_rate": (True, None, 0.0, 1.0, "Share of tasks the AI path completes acceptably (from evals)"),
    "baseline_cost_per_task": (True, None, 0.0, None, "Cost of today's process per task"),
    "calls_per_task": (False, 1.0, 0.0, None, "Model calls per task (retries, chains, agent turns, judge calls)"),
    "cache_read_price_per_mtok": (False, 0.0, 0.0, None, "Price per million cached input tokens"),
    "cached_input_fraction": (False, 0.0, 0.0, 1.0, "Share of input tokens served from the prompt cache"),
    "other_cost_per_task": (False, 0.0, 0.0, None, "Retrieval, third-party APIs, moderation, per task"),
    "review_minutes_per_task": (False, 0.0, 0.0, None, "Human minutes spent checking each AI output"),
    "fallback_minutes_per_failure": (False, 0.0, 0.0, None, "Human minutes to finish a task the AI failed"),
    "loaded_hourly_cost": (False, 0.0, 0.0, None, "Fully loaded cost of one hour of reviewer time"),
    "fixed_monthly_cost": (False, 0.0, 0.0, None, "Hosting, monitoring, eval runs, on-call share"),
    "one_time_cost": (False, 0.0, 0.0, None, "Build, data preparation, evaluation and launch"),
}
TEXT_FIELDS = ("currency", "label")

EXAMPLE: Dict[str, Any] = {
    "label": "Invoice field extraction",
    "currency": "USD",
    "price_input_per_mtok": 3.0,
    "price_output_per_mtok": 15.0,
    "cache_read_price_per_mtok": 0.3,
    "cached_input_fraction": 0.5,
    "input_tokens_per_call": 4000,
    "output_tokens_per_call": 600,
    "calls_per_task": 2,
    "other_cost_per_task": 0.002,
    "success_rate": 0.85,
    "review_minutes_per_task": 0.5,
    "fallback_minutes_per_failure": 6,
    "loaded_hourly_cost": 35,
    "baseline_cost_per_task": 3.5,
    "tasks_per_month": 20000,
    "fixed_monthly_cost": 2000,
    "one_time_cost": 60000,
}


class InputError(ValueError):
    """The calculator inputs are invalid."""


def validate_inputs(raw: Any) -> Dict[str, Any]:
    """Check types, ranges and unknown keys; fill defaults. Raises InputError."""
    if not isinstance(raw, dict):
        raise InputError("inputs must be a JSON object")
    errors: List[str] = []
    unknown = sorted(set(raw) - set(FIELDS) - set(TEXT_FIELDS))
    if unknown:
        errors.append(f"unknown fields: {', '.join(unknown)} (run --example to see valid fields)")
    values: Dict[str, Any] = {}
    for name, (required, default, minimum, maximum, _) in FIELDS.items():
        if name not in raw or raw[name] is None:
            if required:
                errors.append(f"missing required field '{name}'")
            else:
                values[name] = default
            continue
        value = raw[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            errors.append(f"'{name}' must be a number")
            continue
        if value < minimum or (maximum is not None and value > maximum):
            upper = "" if maximum is None else f" and at most {maximum:g}"
            errors.append(f"'{name}' must be at least {minimum:g}{upper}")
            continue
        values[name] = float(value)
    if not errors and values["calls_per_task"] <= 0:
        errors.append("'calls_per_task' must be greater than 0")
    needs_rate = values.get("review_minutes_per_task", 0) > 0 or values.get("fallback_minutes_per_failure", 0) > 0
    if not errors and needs_rate and values["loaded_hourly_cost"] <= 0:
        errors.append("'loaded_hourly_cost' is required when review or fallback minutes are set")
    if errors:
        raise InputError("; ".join(errors))
    for name in TEXT_FIELDS:
        values[name] = str(raw.get(name, "USD" if name == "currency" else ""))
    return values


def _core(v: Dict[str, Any]) -> Dict[str, Optional[float]]:
    cached = v["input_tokens_per_call"] * v["cached_input_fraction"]
    uncached = v["input_tokens_per_call"] - cached
    model_cost_per_call = (
        uncached * v["price_input_per_mtok"]
        + cached * v["cache_read_price_per_mtok"]
        + v["output_tokens_per_call"] * v["price_output_per_mtok"]
    ) / 1_000_000
    ai_cost_per_attempt = model_cost_per_call * v["calls_per_task"] + v["other_cost_per_task"]
    review_cost = v["review_minutes_per_task"] * v["loaded_hourly_cost"] / 60
    fallback_cost = v["fallback_minutes_per_failure"] * v["loaded_hourly_cost"] / 60
    expected_failure_cost = (1 - v["success_rate"]) * fallback_cost
    cost_per_completed_task = ai_cost_per_attempt + review_cost + expected_failure_cost
    savings_per_task = v["baseline_cost_per_task"] - cost_per_completed_task
    monthly_ai_cost = cost_per_completed_task * v["tasks_per_month"] + v["fixed_monthly_cost"]
    monthly_baseline_cost = v["baseline_cost_per_task"] * v["tasks_per_month"]
    monthly_net_benefit = monthly_baseline_cost - monthly_ai_cost

    payback: Optional[float]
    if monthly_net_benefit <= 0:
        payback = None
    elif v["one_time_cost"] == 0:
        payback = 0.0
    else:
        payback = v["one_time_cost"] / monthly_net_benefit

    headroom = v["baseline_cost_per_task"] - ai_cost_per_attempt - review_cost
    break_even: Optional[float]
    if fallback_cost == 0:
        break_even = 0.0 if headroom >= 0 else None
    else:
        break_even = min(max(1 - headroom / fallback_cost, 0.0), 1.0) if headroom >= 0 else None

    return {
        "model_cost_per_call": model_cost_per_call,
        "model_cost_per_task": model_cost_per_call * v["calls_per_task"],
        "ai_cost_per_attempt": ai_cost_per_attempt,
        "review_cost_per_task": review_cost,
        "fallback_cost_per_failure": fallback_cost,
        "expected_failure_cost_per_task": expected_failure_cost,
        "cost_per_completed_task": cost_per_completed_task,
        "baseline_cost_per_task": v["baseline_cost_per_task"],
        "savings_per_task": savings_per_task,
        "monthly_model_cost": model_cost_per_call * v["calls_per_task"] * v["tasks_per_month"],
        "monthly_ai_path_cost": monthly_ai_cost,
        "monthly_baseline_cost": monthly_baseline_cost,
        "monthly_net_benefit": monthly_net_benefit,
        "annual_net_benefit": monthly_net_benefit * 12,
        "payback_months": payback,
        "break_even_success_rate": break_even,
    }


def _round(value: Optional[float], digits: int) -> Optional[float]:
    return None if value is None else round(value, digits)


def calculate(raw: Any) -> Dict[str, Any]:
    """Validate inputs and return the full unit-economics result as a JSON-serialisable dict."""
    v = validate_inputs(raw)
    base = _core(v)

    scenarios = [
        ("Base case", {}),
        ("Success rate -20 points", {"success_rate": max(v["success_rate"] - 0.2, 0.0)}),
        ("Volume x0.5", {"tasks_per_month": v["tasks_per_month"] * 0.5}),
        ("Volume x2", {"tasks_per_month": v["tasks_per_month"] * 2}),
        (
            "Tokens x1.5",
            {
                "input_tokens_per_call": v["input_tokens_per_call"] * 1.5,
                "output_tokens_per_call": v["output_tokens_per_call"] * 1.5,
            },
        ),
    ]
    sensitivity = []
    for name, overrides in scenarios:
        result = _core({**v, **overrides})
        sensitivity.append(
            {
                "scenario": name,
                "cost_per_completed_task": _round(result["cost_per_completed_task"], 4),
                "monthly_net_benefit": _round(result["monthly_net_benefit"], 2),
            }
        )

    notes: List[str] = []
    break_even = base["break_even_success_rate"]
    if break_even is None:
        notes.append("Even at 100% success the AI path costs more per task than the baseline.")
    elif break_even == 0.0:
        notes.append("The AI path is cheaper than the baseline even if every task fails over to a human.")
    elif v["success_rate"] < break_even:
        notes.append(
            f"Below break-even: at {v['success_rate']:.0%} success the AI path costs more per task than the baseline "
            f"(break-even is {break_even:.0%})."
        )
    elif v["success_rate"] - break_even < 0.1:
        notes.append(
            f"Fragile: the success rate ({v['success_rate']:.0%}) is within 10 points of break-even ({break_even:.0%})."
        )
    human_share = (base["review_cost_per_task"] or 0) + (base["expected_failure_cost_per_task"] or 0)
    if base["cost_per_completed_task"] and human_share / base["cost_per_completed_task"] > 0.5:
        notes.append(
            "Human review and failure handling are more than half the cost per completed task; "
            "raising the success rate or cutting review time is worth more than a cheaper model."
        )

    money4 = (
        "model_cost_per_call",
        "model_cost_per_task",
        "ai_cost_per_attempt",
        "review_cost_per_task",
        "fallback_cost_per_failure",
        "expected_failure_cost_per_task",
        "cost_per_completed_task",
        "baseline_cost_per_task",
        "savings_per_task",
    )
    money2 = (
        "monthly_model_cost",
        "monthly_ai_path_cost",
        "monthly_baseline_cost",
        "monthly_net_benefit",
        "annual_net_benefit",
    )
    results: Dict[str, Optional[float]] = {}
    for key in money4:
        results[key] = _round(base[key], 4)
    for key in money2:
        results[key] = _round(base[key], 2)
    results["payback_months"] = _round(base["payback_months"], 1)
    results["break_even_success_rate"] = _round(break_even, 4)

    return {
        "label": v["label"],
        "currency": v["currency"],
        "inputs": {name: v[name] for name in FIELDS},
        "results": results,
        "sensitivity": sensitivity,
        "notes": notes,
    }


def render_markdown(result: Dict[str, Any]) -> str:
    cur = result["currency"]
    r = result["results"]

    def money(value: Optional[float], digits: int = 4) -> str:
        return "n/a" if value is None else f"{value:,.{digits}f} {cur}"

    title = f"**Unit economics: {result['label']}**" if result["label"] else "**Unit economics**"
    break_even = r["break_even_success_rate"]
    if r["payback_months"] is None:
        payback = "n/a (no positive monthly benefit)"
    elif result["inputs"]["one_time_cost"] == 0:
        payback = "immediate (no one-time cost entered)"
    else:
        payback = f"{r['payback_months']} months"
    lines = [
        title,
        "",
        "| Output | Value |",
        "|---|---|",
        f"| Model cost per call | {money(r['model_cost_per_call'])} |",
        f"| AI cost per attempt | {money(r['ai_cost_per_attempt'])} |",
        f"| Review cost per task | {money(r['review_cost_per_task'])} |",
        f"| Expected failure cost per task | {money(r['expected_failure_cost_per_task'])} |",
        f"| **Cost per completed task** | **{money(r['cost_per_completed_task'])}** |",
        f"| Baseline cost per task | {money(r['baseline_cost_per_task'])} |",
        f"| Savings per task | {money(r['savings_per_task'])} |",
        f"| Monthly model cost | {money(r['monthly_model_cost'], 2)} |",
        f"| Monthly net benefit | {money(r['monthly_net_benefit'], 2)} |",
        f"| Payback | {payback} |",
        f"| Break-even success rate | {'not achievable' if break_even is None else f'{break_even:.1%}'} |",
        "",
        "| Scenario | Cost per completed task | Monthly net benefit |",
        "|---|---|---|",
    ]
    for row in result["sensitivity"]:
        lines.append(
            f"| {row['scenario']} | {money(row['cost_per_completed_task'])} | {money(row['monthly_net_benefit'], 2)} |"
        )
    for note in result["notes"]:
        lines += ["", f"> {note}"]
    return "\n".join(lines) + "\n"


def _never_crash_on_encoding() -> None:
    """Labels may contain characters the console cannot encode (e.g. cp1252 on Windows)."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        with contextlib.suppress(ValueError, OSError):
            reconfigure(errors="replace")


def main(argv: Optional[List[str]] = None) -> int:
    _never_crash_on_encoding()
    parser = argparse.ArgumentParser(description="Price an AI feature per completed task.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", metavar="FILE", help="JSON file with inputs ('-' for stdin)")
    source.add_argument("--input-json", metavar="JSON", help="inputs as an inline JSON object")
    source.add_argument("--example", action="store_true", help="print an example input file")
    source.add_argument("--fields", action="store_true", help="describe every input field")
    parser.add_argument("--format", choices=("json", "md"), default="json", help="output format")
    args = parser.parse_args(argv)

    if args.example:
        sys.stdout.write(json.dumps(EXAMPLE, indent=2) + "\n")
        return 0
    if args.fields:
        for name, (required, default, _minimum, _maximum, description) in FIELDS.items():
            flag = "required" if required else f"optional, default {default:g}"
            sys.stdout.write(f"{name} ({flag}): {description}\n")
        return 0

    try:
        if args.input_json is not None:
            raw = json.loads(args.input_json)
        elif args.input == "-":
            raw = json.load(sys.stdin)
        else:
            with open(args.input, encoding="utf-8") as handle:
                raw = json.load(handle)
        result = calculate(raw)
    except (OSError, json.JSONDecodeError, InputError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.format == "md":
        sys.stdout.write(render_markdown(result))
    else:
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
