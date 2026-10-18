from __future__ import annotations

import copy
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from ai_product_governance import engines
from ai_product_governance.skill import Skill, find_repo_root, load_skill


@pytest.fixture(scope="session")
def repo() -> Path:
    return find_repo_root()


@pytest.fixture(scope="session")
def skill(repo: Path) -> Skill:
    return load_skill(repo / "skills" / "ai-product-governance")


@pytest.fixture(scope="session")
def risk_engine() -> ModuleType:
    return engines.risk_tier()


@pytest.fixture(scope="session")
def economics_engine() -> ModuleType:
    return engines.unit_economics()


@pytest.fixture(scope="session")
def _default_policy(skill: Skill) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(skill.default_policy_path.read_text(encoding="utf-8"))
    return data


@pytest.fixture
def policy(_default_policy: dict[str, Any]) -> dict[str, Any]:
    """A fresh, mutable copy of the default policy for each test."""
    return copy.deepcopy(_default_policy)


@pytest.fixture(autouse=True)
def _no_ambient_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIPG_POLICY", raising=False)
