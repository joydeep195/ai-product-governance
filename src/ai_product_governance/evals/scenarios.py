"""Eval scenarios (evals/scenarios/*.json): a prompt, rubric criteria and deterministic checks."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCENARIO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "title", "gate", "prompt", "criteria"],
    "additionalProperties": False,
    "properties": {
        "$schema": {"type": "string"},
        "id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
        "title": {"type": "string", "minLength": 1},
        "gate": {"enum": ["G0", "G1", "G2", "G3", "G4", "G5", "cross-cutting"]},
        "tags": {"type": "array", "items": {"type": "string"}},
        "prompt": {"type": "string", "minLength": 20},
        "criteria": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id", "text"],
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string", "pattern": "^C\\d+$"},
                    "text": {"type": "string", "minLength": 10},
                    "weight": {"type": "number", "exclusiveMinimum": 0},
                    "critical": {"type": "boolean"},
                },
            },
        },
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "pattern", "description"],
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string", "pattern": "^K\\d+$"},
                    "pattern": {"type": "string", "minLength": 1},
                    "flags": {"type": "string", "pattern": "^[ims]*$"},
                    "expect": {"enum": ["match", "no_match"]},
                    "description": {"type": "string"},
                    "weight": {"type": "number", "exclusiveMinimum": 0},
                    "critical": {"type": "boolean"},
                },
            },
        },
        "expected_reads": {"type": "array", "items": {"type": "string"}},
        "expected_scripts": {"type": "array", "items": {"enum": ["risk_tier.py", "unit_economics.py"]}},
    },
}


@dataclass(frozen=True)
class Criterion:
    id: str
    text: str
    weight: float = 1.0
    critical: bool = False


@dataclass(frozen=True)
class Check:
    id: str
    pattern: str
    description: str
    flags: str = ""
    expect: str = "match"
    weight: float = 1.0
    critical: bool = False

    def evaluate(self, text: str) -> bool:
        flags = 0
        for letter, value in (("i", re.IGNORECASE), ("m", re.MULTILINE), ("s", re.DOTALL)):
            if letter in self.flags:
                flags |= value
        found = re.search(self.pattern, text, flags) is not None
        return found if self.expect == "match" else not found


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    gate: str
    prompt: str
    criteria: tuple[Criterion, ...]
    checks: tuple[Check, ...] = ()
    tags: tuple[str, ...] = ()
    expected_reads: tuple[str, ...] = ()
    expected_scripts: tuple[str, ...] = ()


class ScenarioError(ValueError):
    """A scenario file is invalid."""


def parse_scenario(raw: dict[str, Any], where: str = "scenario") -> Scenario:
    errors = [
        f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}"
        for e in Draft202012Validator(SCENARIO_SCHEMA).iter_errors(raw)
    ]
    ids = [c["id"] for c in raw.get("criteria", [])] + [k["id"] for k in raw.get("checks", [])]
    if len(ids) != len(set(ids)):
        errors.append("criterion and check ids must be unique")
    for check in raw.get("checks", []):
        try:
            re.compile(check.get("pattern", ""))
        except re.error as exc:
            errors.append(f"check {check.get('id')}: invalid regex: {exc}")
    if errors:
        raise ScenarioError(f"{where}:\n- " + "\n- ".join(errors))
    return Scenario(
        id=raw["id"],
        title=raw["title"],
        gate=raw["gate"],
        prompt=raw["prompt"],
        criteria=tuple(
            Criterion(c["id"], c["text"], c.get("weight", 1.0), c.get("critical", False)) for c in raw["criteria"]
        ),
        checks=tuple(
            Check(
                k["id"],
                k["pattern"],
                k["description"],
                k.get("flags", ""),
                k.get("expect", "match"),
                k.get("weight", 1.0),
                k.get("critical", False),
            )
            for k in raw.get("checks", [])
        ),
        tags=tuple(raw.get("tags", [])),
        expected_reads=tuple(raw.get("expected_reads", [])),
        expected_scripts=tuple(raw.get("expected_scripts", [])),
    )


def load_scenarios(directory: Path) -> list[Scenario]:
    scenarios = []
    for path in sorted(directory.glob("*.json")):
        scenarios.append(parse_scenario(json.loads(path.read_text(encoding="utf-8")), where=path.name))
    ids = [s.id for s in scenarios]
    if len(ids) != len(set(ids)):
        raise ScenarioError("scenario ids must be unique")
    return scenarios
