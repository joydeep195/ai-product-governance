"""Blind rubric judge: grades one response against a scenario's criteria."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_product_governance.evals.providers import Provider, Usage
from ai_product_governance.evals.scenarios import Scenario

JUDGE_SYSTEM = """\
You are a meticulous evaluator of AI product governance advice. Grade the RESPONSE against each \
CRITERION independently.

Rules:
- PASS only if the response clearly and explicitly satisfies the criterion. Partial, vague or implied \
satisfaction is a FAIL.
- Quote the shortest exact excerpt (at most 40 words) from the response that supports your verdict. Use \
an empty string if nothing relevant exists.
- Judge substance, not length, tone or formatting. Do not reward content the criterion does not ask for.
- You do not know how the response was produced, and that must not influence you.
- Return exactly one verdict for every criterion id.
"""

VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["pass", "fail"]},
                    "evidence": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["id", "verdict", "evidence", "rationale"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Verdict:
    id: str
    passed: bool
    evidence: str
    rationale: str


def judge_prompt(scenario: Scenario, response: str) -> str:
    criteria = "\n".join(f"- [{c.id}] {c.text}" for c in scenario.criteria)
    return (
        f"<task_given_to_the_assistant>\n{scenario.prompt}\n</task_given_to_the_assistant>\n\n"
        f"<criteria>\n{criteria}\n</criteria>\n\n"
        f"<response>\n{response}\n</response>\n\n"
        "Return a verdict for every criterion id."
    )


def parse_verdicts(scenario: Scenario, payload: Any) -> list[Verdict]:
    """Map the judge's JSON to verdicts; a criterion the judge skipped counts as a failure."""
    by_id: dict[str, dict[str, Any]] = {}
    if isinstance(payload, dict):
        for item in payload.get("verdicts", []):
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                by_id.setdefault(item["id"].strip("[] "), item)
    verdicts = []
    for criterion in scenario.criteria:
        item = by_id.get(criterion.id)
        if item is None:
            verdicts.append(Verdict(criterion.id, False, "", "The judge returned no verdict for this criterion."))
        else:
            verdicts.append(
                Verdict(
                    criterion.id,
                    item.get("verdict") == "pass",
                    str(item.get("evidence", "")),
                    str(item.get("rationale", "")),
                )
            )
    return verdicts


def grade(judge: Provider, scenario: Scenario, response: str) -> tuple[list[Verdict], Usage]:
    payload, usage = judge.complete_json(JUDGE_SYSTEM, judge_prompt(scenario, response), VERDICT_SCHEMA, "verdicts")
    return parse_verdicts(scenario, payload), usage
