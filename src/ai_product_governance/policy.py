"""Effective-policy resolution and schema validation.

Classification logic lives in the skill's risk_tier engine; this module adds JSON Schema
validation (used by `aipg validate`, the MCP server and CI) on top of the engine's own
referential checks.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from ai_product_governance import engines
from ai_product_governance.skill import load_skill


@dataclass(frozen=True)
class EffectivePolicy:
    document: dict[str, Any]
    path: Path
    source: str

    @property
    def id(self) -> str:
        return str(self.document["policy_id"])

    @property
    def version(self) -> str:
        return str(self.document["version"])

    @property
    def label(self) -> str:
        return f"{self.id} v{self.version}"


def schema_errors(policy: Any, schema_path: Path | None = None) -> list[str]:
    """Validate a policy document against policy.schema.json; return readable errors."""
    path = schema_path or load_skill().policy_schema_path
    schema = json.loads(path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = []
    for error in sorted(validator.iter_errors(policy), key=lambda e: list(e.absolute_path)):
        location = "/".join(str(part) for part in error.absolute_path) or "(root)"
        errors.append(f"{location}: {error.message}")
    return errors


def policy_problems(policy: Any) -> list[str]:
    """Schema errors plus the engine's referential checks (unknown tiers, controls, questions)."""
    problems = schema_errors(policy)
    if not problems:
        problems.extend(engines.risk_tier().validate_policy(policy))
    return problems


def load_effective_policy(explicit_path: str | None = None, cwd: Path | None = None) -> EffectivePolicy:
    """Resolve the policy exactly as the bundled script does, then validate it fully."""
    engine = engines.risk_tier()
    path, source = engine.resolve_policy_path(explicit_path, cwd)
    document = engine.load_policy(path)
    problems = schema_errors(document)
    if problems:
        raise engine.PolicyError("Policy fails schema validation:\n- " + "\n- ".join(problems))
    return EffectivePolicy(document=document, path=Path(path), source=source)
