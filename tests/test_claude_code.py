"""Claude Code provider tests, driven by a fake CLI (tests/fake_claude.py): offline and free."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from ai_product_governance.evals import claude_code
from ai_product_governance.evals.claude_code import (
    SCRIPT_RULES,
    SKILL_TOOLS,
    ClaudeCodeProvider,
    find_claude_cli,
    native_adherence,
    parse_stream,
)
from ai_product_governance.evals.config import EvalConfig, ModelSpec, load_config
from ai_product_governance.evals.judge import VERDICT_SCHEMA
from ai_product_governance.evals.providers import ProviderError, ToolCall
from ai_product_governance.evals.report import render_markdown
from ai_product_governance.evals.runner import build_manifest, plan_jobs, run_jobs
from ai_product_governance.evals.scenarios import Scenario, parse_scenario
from ai_product_governance.evals.scoring import evaluate_gates, summarise, summarise_arms
from ai_product_governance.skill import Skill

FAKE = [sys.executable, str(Path(__file__).with_name("fake_claude.py"))]


@pytest.fixture
def log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "fake-claude.log"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(path))
    return path


def calls(log: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def provider(model: str = "claude-opus-5-5", **params: Any) -> ClaudeCodeProvider:
    return ClaudeCodeProvider(ModelSpec("cc", "claude-code", model, True, {"command": FAKE, **params}))


def scenario() -> Scenario:
    return parse_scenario(
        {
            "id": "launch",
            "title": "Launch",
            "gate": "G4",
            "prompt": "Can we launch the claims assistant on Monday?",
            "criteria": [
                {"id": "C1", "text": "Says No-go clearly", "critical": True},
                {"id": "C2", "text": "Lists the blocking gaps"},
            ],
            "expected_reads": ["references/gate-4-launch-readiness.md"],
        }
    )


def test_with_skill_run_installs_the_skill_natively_and_isolates_the_run(
    skill: Skill, log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Variables a surrounding Claude Code session would set, plus credentials.
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "claude-desktop")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "subscription-token")

    result = provider(effort="max").run_native("Can we launch?", skill.root, "You are an expert.", 12)

    assert result.error is None and "No-go" in result.text
    assert [c.name for c in result.tool_calls] == ["Skill", "Read"]
    assert result.served_model == "claude-opus-5-5"
    assert result.usage.reported_cost_usd == pytest.approx(0.05)
    assert result.usage.input_tokens == 1200 and result.usage.cache_read_tokens == 200

    (run,) = calls(log)
    args = run["args"]
    for flag in ("-p", "--no-session-persistence", "--verbose"):
        assert flag in args
    assert args[args.index("--setting-sources") + 1] == "project"
    assert args[args.index("--permission-mode") + 1] == "dontAsk"
    assert args[args.index("--permission-prompts") + 1] == "none"
    assert args[args.index("--output-format") + 1] == "stream-json"
    assert args[args.index("--model") + 1] == "claude-opus-5-5"
    assert args[args.index("--effort") + 1] == "max"
    assert args[args.index("--tools") + 1] == SKILL_TOOLS
    assert args[args.index("--allowedTools") + 1 :] == list(SCRIPT_RULES)
    assert not run["has_claudecode"] and not run["has_host_var"], "host-session variables must not leak"
    assert not run["has_api_key"], "the subscription login must be used, not an API key"
    assert run["has_oauth_token"]
    workspace = Path(run["cwd"])
    assert workspace != Path.cwd() and not workspace.exists(), "each run uses a throwaway workspace"


def test_baseline_run_has_no_skill_and_no_tools(log: Path) -> None:
    result = provider().run_native("Can we launch?", None, "You are an expert.", 12)
    assert result.text == "Sounds fine, go ahead." and result.tool_calls == []
    args = calls(log)[0]["args"]
    assert args[args.index("--tools") + 1] == ""
    assert "--allowedTools" not in args


def test_inherit_leaves_model_and_effort_to_claude_code(log: Path, skill: Skill) -> None:
    provider(model="inherit", effort="inherit").run_native("q", None, "p", 3)
    args = calls(log)[0]["args"]
    assert "--model" not in args and "--effort" not in args


def test_api_key_kept_when_subscription_is_not_required(log: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-console")
    provider(use_subscription=False).run_native("q", None, "p", 3)
    assert calls(log)[0]["has_api_key"]


def test_judge_uses_structured_output_without_tools(log: Path) -> None:
    prompt = "<criteria>\n- [C1] a\n- [C2] b\n</criteria>\n<response>\nVerdict: No-go\n</response>"
    payload, usage = provider(effort="high").complete_json("Grade strictly.", prompt, VERDICT_SCHEMA, "verdicts")
    assert [v["verdict"] for v in payload["verdicts"]] == ["pass", "pass"]
    assert usage.reported_cost_usd == pytest.approx(0.01)
    args = calls(log)[0]["args"]
    assert json.loads(args[args.index("--json-schema") + 1]) == VERDICT_SCHEMA
    assert "--system-prompt-file" in args
    assert args[args.index("--tools") + 1] == ""


def test_readiness() -> None:
    assert provider().check_ready() == (True, "signed in to Claude Code")
    missing = ClaudeCodeProvider(
        ModelSpec("cc", "claude-code", "m", True, {"command": [str(Path("does") / "not" / "exist")]})
    )
    ok, detail = missing.check_ready()
    assert not ok and "cannot start the Claude Code CLI" in detail


def test_parse_stream_reports_errors_and_missing_results() -> None:
    failed = json.dumps({"type": "result", "subtype": "error_max_turns", "is_error": True, "result": "stopped"})
    assert parse_stream(failed).error == "error_max_turns: stopped"
    assert "no result" in (parse_stream("not json\n", "boom").error or "")


def test_native_adherence_from_tool_calls() -> None:
    root = "C:\\tmp\\run\\.claude\\skills\\ai-product-governance\\"
    tool_calls = [
        ToolCall("Skill", {"skill": "ai-product-governance"}, "", False),
        ToolCall("Read", {"file_path": root + "references\\gate-1-value-and-economics.md"}, "", False),
        ToolCall("Bash", {"command": "python scripts/unit_economics.py --input-json '{}'"}, "", False),
        ToolCall("Read", {"file_path": "/etc/hosts"}, "", False),
    ]
    activated, files, scripts = native_adherence(tool_calls, "ai-product-governance")
    assert activated
    assert files == ["references/gate-1-value-and-economics.md"]
    assert scripts == ["unit_economics.py"]


def test_cli_discovery_prefers_env_then_path_then_desktop_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIPG_CLAUDE_BIN", "/opt/claude")
    assert find_claude_cli() == ["/opt/claude"]
    monkeypatch.delenv("AIPG_CLAUDE_BIN")

    monkeypatch.setattr(claude_code.shutil, "which", lambda name: "/usr/bin/claude")
    assert find_claude_cli() == ["/usr/bin/claude"]

    monkeypatch.setattr(claude_code.shutil, "which", lambda name: None)
    monkeypatch.setattr(claude_code.Path, "home", staticmethod(lambda: tmp_path / "home"))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    for version in ("2.1.9", "2.1.10"):
        exe = tmp_path / "Claude" / "claude-code" / version / "abc123" / "claude.exe"
        exe.parent.mkdir(parents=True)
        exe.write_text("", encoding="utf-8")
    found = find_claude_cli()
    assert found is not None and "2.1.10" in found[0], "versions must compare numerically, not as text"


def test_end_to_end_eval_with_claude_code_subject_and_judge(skill: Skill, repo: Path, log: Path) -> None:
    base: EvalConfig = load_config(repo / "evals" / "eval.config.json")
    subject = ModelSpec("claude-code", "claude-code", "claude-opus-5-5", True, {"command": FAKE, "effort": "max"})
    judge = ModelSpec("claude-code-judge", "claude-code", "claude-opus-5-5", True, {"command": FAKE, "effort": "high"})
    config = replace(base, concurrency=2)
    jobs = plan_jobs(config, [subject], [scenario()], ["with-skill", "baseline"], trials=2)

    outcome = run_jobs(config, skill, jobs, judge_spec=judge, progress=lambda _: None)

    with_skill = [t for t in outcome.trials if t.arm == "with-skill"]
    baseline = [t for t in outcome.trials if t.arm == "baseline"]
    assert all(t.passed and t.score == 1.0 for t in with_skill)
    assert all(
        t.routing == {"activated the skill": True, "read references/gate-4-launch-readiness.md": True}
        for t in with_skill
    )
    assert all(not t.passed and t.critical_failures == ["C1"] for t in baseline)
    assert outcome.total_cost_usd == pytest.approx(4 * (0.05 + 0.01)), "reported costs are used, not a price table"

    cells = summarise(outcome.trials)
    arms = summarise_arms(cells)
    manifest = build_manifest(config, skill, [scenario()], outcome, ["with-skill", "baseline"], 2, [subject], judge)
    assert manifest["judge"] == {
        "id": "claude-code-judge",
        "provider": "claude-code",
        "model": "claude-opus-5-5",
        "effort": "high",
    }
    report = render_markdown(manifest, outcome.trials, cells, arms, evaluate_gates(arms, config.gates), [], 0.24)
    assert "own sign-in" in report and "activated the skill" in report


def test_judge_errors_surface_as_provider_errors(tmp_path: Path) -> None:
    failing = tmp_path / "fail.py"
    failing.write_text(
        "import json, sys\nsys.stdin.read()\n"
        "print(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': True, 'result': 'Not logged in'}))\n",
        encoding="utf-8",
    )
    judge = ClaudeCodeProvider(ModelSpec("j", "claude-code", "m", True, {"command": [sys.executable, str(failing)]}))
    with pytest.raises(ProviderError, match="Not logged in"):
        judge.complete_json("s", "u", VERDICT_SCHEMA, "verdicts")
