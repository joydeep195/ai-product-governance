"""Eval configuration (evals/eval.config.json)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ARMS = ("with-skill", "baseline")

_PROVIDER = {
    "type": "object",
    "required": ["provider", "model"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9._-]*$"},
        "provider": {"enum": ["anthropic", "openai", "claude-code"]},
        "model": {"type": "string", "minLength": 1},
        "enabled": {"type": "boolean"},
        "params": {"type": "object"},
    },
}

CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["subjects", "judge", "trials", "pass_threshold", "gates"],
    "additionalProperties": False,
    "properties": {
        "$schema": {"type": "string"},
        "subjects": {"type": "array", "minItems": 1, "items": {**_PROVIDER, "required": ["id", "provider", "model"]}},
        # One judge, or a preference-ordered list: the first one with working credentials is used.
        "judge": {"oneOf": [_PROVIDER, {"type": "array", "minItems": 1, "items": _PROVIDER}]},
        "arms": {"type": "array", "items": {"enum": list(ARMS)}, "minItems": 1, "uniqueItems": True},
        "trials": {"type": "integer", "minimum": 1, "maximum": 20},
        "concurrency": {"type": "integer", "minimum": 1, "maximum": 32},
        "max_turns": {"type": "integer", "minimum": 1, "maximum": 50},
        "pass_threshold": {"type": "number", "minimum": 0, "maximum": 1},
        "baseline_system_prompt": {"type": "string", "minLength": 1},
        "gates": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "min_with_skill_score": {"type": "number", "minimum": 0, "maximum": 1},
                "max_with_skill_critical_failures": {"type": "integer", "minimum": 0},
                "min_delta": {"type": "number", "minimum": -1, "maximum": 1},
                "max_regression": {"type": "number", "minimum": 0, "maximum": 1},
            },
        },
        "pricing_per_mtok": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "required": ["input", "output"],
                "additionalProperties": False,
                "properties": {
                    "input": {"type": "number", "minimum": 0},
                    "output": {"type": "number", "minimum": 0},
                    "cache_read": {"type": "number", "minimum": 0},
                },
            },
        },
    },
}

DEFAULT_BASELINE_PROMPT = (
    "You are an expert AI product manager at a large enterprise. Give rigorous, practical, decision-ready guidance."
)


@dataclass(frozen=True)
class ModelSpec:
    id: str
    provider: str
    model: str
    enabled: bool = True
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Gates:
    min_with_skill_score: float = 0.8
    max_with_skill_critical_failures: int = 0
    min_delta: float = 0.0
    max_regression: float = 0.05


@dataclass(frozen=True)
class EvalConfig:
    subjects: tuple[ModelSpec, ...]
    judges: tuple[ModelSpec, ...]  # preference order
    arms: tuple[str, ...]
    trials: int
    concurrency: int
    max_turns: int
    pass_threshold: float
    baseline_system_prompt: str
    gates: Gates
    pricing_per_mtok: dict[str, dict[str, float]]
    path: Path

    @property
    def judge(self) -> ModelSpec:
        """The preferred judge (the CLI falls back to later ones that have credentials)."""
        return self.judges[0]

    def price(self, model: str) -> dict[str, float] | None:
        return self.pricing_per_mtok.get(model)


class ConfigError(ValueError):
    """The eval configuration is invalid."""


def load_config(path: Path) -> EvalConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    errors = [
        f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}"
        for e in Draft202012Validator(CONFIG_SCHEMA).iter_errors(raw)
    ]
    if errors:
        raise ConfigError("Invalid eval config:\n- " + "\n- ".join(errors))
    subjects = tuple(
        ModelSpec(s["id"], s["provider"], s["model"], s.get("enabled", True), dict(s.get("params", {})))
        for s in raw["subjects"]
    )
    if len({s.id for s in subjects}) != len(subjects):
        raise ConfigError("subject ids must be unique")
    judge_entries = raw["judge"] if isinstance(raw["judge"], list) else [raw["judge"]]
    judges = tuple(
        ModelSpec(j.get("id", f"judge-{i + 1}"), j["provider"], j["model"], True, dict(j.get("params", {})))
        for i, j in enumerate(judge_entries)
    )
    return EvalConfig(
        subjects=subjects,
        judges=judges,
        arms=tuple(raw.get("arms", ARMS)),
        trials=raw["trials"],
        concurrency=raw.get("concurrency", 4),
        max_turns=raw.get("max_turns", 12),
        pass_threshold=raw["pass_threshold"],
        baseline_system_prompt=raw.get("baseline_system_prompt", DEFAULT_BASELINE_PROMPT),
        gates=Gates(**raw["gates"]),
        pricing_per_mtok={k: dict(v) for k, v in raw.get("pricing_per_mtok", {}).items()},
        path=path,
    )
