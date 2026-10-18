"""Load the skill's deterministic engines (scripts/*.py) as Python modules.

The scripts are the single implementation of tiering and unit economics. They live
inside the skill so that any agent can run them; this module imports the very same
files so the MCP server, CLI and tests can never drift from what agents execute.
"""

from __future__ import annotations

import importlib.util
import sys
from functools import cache
from types import ModuleType

from ai_product_governance.skill import find_skill_dir


@cache
def load_engine(name: str) -> ModuleType:
    path = find_skill_dir() / "scripts" / f"{name}.py"
    module_name = f"ai_product_governance._engine_{name}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load engine '{name}' from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def risk_tier() -> ModuleType:
    return load_engine("risk_tier")


def unit_economics() -> ModuleType:
    return load_engine("unit_economics")
