"""Eval configuration (evals/eval.config.json).

`models` lists every way the harness can reach a model: an agent CLI you are signed in to,
an API key, or a local model server. They are tried in order and the first one that is ready
is used, so one tool is always enough. The judge defaults to that same tool.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ARMS = ("with-skill", "baseline")
PROVIDERS = ("claude-code", "agent-cli", "anthropic", "openai")
JUDGE_SAME_AS_SUBJECT = "subject"

CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["models", "trials", "pass_threshold", "gates"],
    "additionalProperties": False,
    "properties": {
        "$schema": {"type": "string"},
        "models": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id", "provider", "model"],
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9._-]*$"},
                    "provider": {"enum": list(PROVIDERS)},
                    "model": {"type": "string", "minLength": 1},
                    "auto": {"type": "boolean"},
                    "params": {"type": "object"},
                },
            },
        },
        "judge": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "use": {"type": "string", "minLength": 1},
                "params": {"type": "object"},
            },
        },
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
    auto: bool = True  # eligible for automatic detection
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Gates:
    min_with_skill_score: float = 0.8
    max_with_skill_critical_failures: int = 0
    min_delta: float = 0.0
    max_regression: float = 0.05


@dataclass(frozen=True)
class EvalConfig:
    models: tuple[ModelSpec, ...]  # detection order
    judge_use: str  # "subject" (the same tool that answered) or a model id
    judge_params: dict[str, Any]
    arms: tuple[str, ...]
    trials: int
    concurrency: int
    max_turns: int
    pass_threshold: float
    baseline_system_prompt: str
    gates: Gates
    pricing_per_mtok: dict[str, dict[str, float]]
    path: Path

    def model(self, model_id: str) -> ModelSpec:
        for spec in self.models:
            if spec.id == model_id:
                return spec
        raise KeyError(f"Unknown model '{model_id}'. Configured: {', '.join(m.id for m in self.models)}")

    def judge_for(self, subject: ModelSpec, use: str | None = None) -> ModelSpec:
        """The judge for a subject: by default the same tool, with the judge's parameter overrides."""
        choice = use or self.judge_use
        base = subject if choice == JUDGE_SAME_AS_SUBJECT else self.model(choice)
        return replace(base, id=f"{base.id}-judge", params={**base.params, **self.judge_params})

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
    models = tuple(
        ModelSpec(m["id"], m["provider"], m["model"], m.get("auto", True), dict(m.get("params", {})))
        for m in raw["models"]
    )
    if len({m.id for m in models}) != len(models):
        raise ConfigError("model ids must be unique")
    judge = raw.get("judge", {})
    judge_use = judge.get("use", JUDGE_SAME_AS_SUBJECT)
    if judge_use != JUDGE_SAME_AS_SUBJECT and judge_use not in {m.id for m in models}:
        raise ConfigError(f"judge.use must be '{JUDGE_SAME_AS_SUBJECT}' or a configured model id, not '{judge_use}'")
    return EvalConfig(
        models=models,
        judge_use=judge_use,
        judge_params=dict(judge.get("params", {})),
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
