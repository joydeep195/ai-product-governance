from __future__ import annotations

import json
import sys
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


def fake_claude_config(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An eval config whose only ready tool is the fake Claude Code CLI."""
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    config = json.loads((repo / "evals" / "eval.config.json").read_text(encoding="utf-8"))
    fake = [sys.executable, str(Path(__file__).with_name("fake_claude.py"))]
    for entry in config["models"]:
        if entry["provider"] == "claude-code":
            entry["params"]["command"] = fake
        elif entry["provider"] == "agent-cli":
            entry["auto"] = False  # keep the test independent of CLIs installed on this machine
        elif entry["params"].get("local"):
            entry["auto"] = False
    path = tmp_path / "eval.config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def test_eval_dry_run_detects_the_one_tool_you_have(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = fake_claude_config(repo, tmp_path, monkeypatch)

    assert main(["eval", "--dry-run", "--trials", "1", "--config", str(path)]) == 0
    out = capsys.readouterr().out
    assert " -> claude-code" in out and "ready" in out
    assert "Plan: 1 model(s) x 10 scenario(s) x 2 arm(s) x 1 trial(s)" in out
    assert "graded by claude-code/claude-opus-5-5, effort high (the same tool)" in out
    assert "usage counts against that plan" in out

    assert main(["eval", "--dry-run", "--config", str(path), "--subject", "claude-code", "--effort", "high"]) == 0
    assert "claude-code: claude-code/claude-opus-5-5, effort high;" in capsys.readouterr().out


def test_eval_without_any_ai_access_explains_the_options(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    config = json.loads((repo / "evals" / "eval.config.json").read_text(encoding="utf-8"))
    for entry in config["models"]:
        entry["auto"] = entry["provider"] in ("anthropic", "openai") and not entry["params"].get("local")
    path = tmp_path / "eval.config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    assert main(["eval", "--config", str(path)]) == 2
    err = capsys.readouterr().err
    assert "Any ONE of these is enough" in err and "aipg eval-kit create" in err


def test_eval_rejects_unknown_scenario(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["eval", "--dry-run", "--scenario", "nope"]) == 2
    assert "unknown scenario" in capsys.readouterr().err


def test_eval_compare_says_which_baseline_each_subject_is_checked_against(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = fake_claude_config(repo, tmp_path, monkeypatch)
    committed = repo / "evals" / "baselines" / "latest.json"
    assert main(["eval", "--dry-run", "--config", str(path), "--compare", str(committed)]) == 0
    out = capsys.readouterr().out
    assert "regression check: against 'Claude Code (Claude Opus 5.5)' (an agent-run result, indicative), which " in out
    assert "stands in for claude-code" in out

    other = tmp_path / "other.json"
    other.write_text(json.dumps({"arms": [{"subject": "codex", "arm": "with-skill", "mean_score": 0.9}]}), "utf-8")
    assert main(["eval", "--dry-run", "--config", str(path), "--compare", str(other)]) == 0
    assert "regression check: SKIPPED, no baseline subject matches" in capsys.readouterr().out

    unreadable = tmp_path / "list.json"
    unreadable.write_text("[]", encoding="utf-8")
    for bad in (tmp_path / "missing.json", unreadable):
        assert main(["eval", "--dry-run", "--config", str(path), "--compare", str(bad)]) == 2
        assert "cannot read baseline" in capsys.readouterr().err, "a bad baseline stops the run before any model call"


def test_eval_compare_applies_or_visibly_skips_the_regression_gate(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = fake_claude_config(repo, tmp_path, monkeypatch)
    run = ["eval", "--config", str(path), "--scenario", "g4-claims-triage-launch", "--trials", "1"]

    committed = repo / "evals" / "baselines" / "latest.json"
    main([*run, "--out", str(tmp_path / "matched"), "--compare", str(committed)])
    assert "skipped" not in capsys.readouterr().err
    gates = json.loads((tmp_path / "matched" / "results.json").read_text(encoding="utf-8"))["gates"]
    (regression,) = [g for g in gates if g["name"] == "max_regression"]
    assert regression["subject"] == "claude-code" and not regression["skipped"]
    assert "from 'Claude Code (Claude Opus 5.5)' (agent-run result, indicative)" in regression["detail"]

    other = tmp_path / "other.json"
    other.write_text(json.dumps({"arms": [{"subject": "codex", "arm": "with-skill", "mean_score": 0.9}]}), "utf-8")
    main([*run, "--out", str(tmp_path / "unmatched"), "--compare", str(other)])
    err = capsys.readouterr().err
    assert "warning: gate max_regression skipped for claude-code: not compared" in err and "'codex'" in err
    report = (tmp_path / "unmatched" / "report.md").read_text(encoding="utf-8")
    assert "| claude-code | max_regression | skipped |" in report and "skipped)**" in report
    junit = (tmp_path / "unmatched" / "junit.xml").read_text(encoding="utf-8")
    assert '<skipped message="not compared: no baseline subject matches' in junit
