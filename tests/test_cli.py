from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from ai_product_governance.cli import main


def test_validate_and_build_check(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", "--strict"]) == 0
    assert main(["build", "--check"]) == 0
    assert "up to date" in capsys.readouterr().out


def test_tier_and_economics_commands(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["tier", "--answers-json", json.dumps({"sensitive_data": True})]) == 0
    assert "**Risk tier: High**" in capsys.readouterr().out
    assert main(["economics", "--example", "--format", "json"]) == 0
    assert "price_input_per_mtok" in capsys.readouterr().out


def test_package_creates_a_reproducible_skill_zip(tmp_path: Path) -> None:
    assert main(["package", "--out", str(tmp_path / "a")]) == 0
    assert main(["package", "--out", str(tmp_path / "b")]) == 0
    first = next((tmp_path / "a").glob("*.zip"))
    second = next((tmp_path / "b").glob("*.zip"))
    assert first.read_bytes() == second.read_bytes(), "the skill zip must be byte-for-byte reproducible"
    with zipfile.ZipFile(first) as archive:
        names = archive.namelist()
    assert "ai-product-governance/SKILL.md" in names
    assert not any("__pycache__" in name for name in names)


def test_eval_dry_run_needs_no_credentials(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert main(["eval", "--dry-run", "--trials", "1"]) == 0
    out = capsys.readouterr().out
    assert "Plan: 1 subject(s) x 10 scenario(s) x 2 arm(s) x 1 trial(s)" in out


def test_eval_rejects_unknown_scenario(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["eval", "--dry-run", "--scenario", "nope"]) == 2
    assert "unknown scenario" in capsys.readouterr().err
