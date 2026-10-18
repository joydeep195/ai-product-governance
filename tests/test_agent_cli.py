"""Agent CLI profiles (Codex, Gemini CLI, Copilot CLI, Cursor CLI) against a fake CLI: offline and free."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from ai_product_governance.evals import agent_cli
from ai_product_governance.evals.agent_cli import PROFILES, AgentCliProvider, extract_answer, extract_json_object
from ai_product_governance.evals.config import ModelSpec
from ai_product_governance.evals.judge import VERDICT_SCHEMA
from ai_product_governance.evals.providers import ProviderError, create_provider, readiness
from ai_product_governance.skill import Skill

FAKE = [sys.executable, str(Path(__file__).with_name("fake_agent.py"))]


@pytest.fixture
def log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "fake-agent.log"
    monkeypatch.setenv("FAKE_AGENT_LOG", str(path))
    return path


def calls(log: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def provider(profile: str, model: str = "inherit", **params: Any) -> AgentCliProvider:
    return AgentCliProvider(
        ModelSpec(profile, "agent-cli", model, True, {"profile": profile, "command": FAKE, **params})
    )


@pytest.mark.parametrize("profile", sorted(PROFILES))
def test_every_profile_answers_judges_and_installs_the_skill_natively(profile: str, skill: Skill, log: Path) -> None:
    cli = provider(profile)
    with_skill = cli.run_native("Can we launch?", skill.root, "You are an expert.", 12)
    baseline = cli.run_native("Can we launch?", None, "You are an expert.", 12)
    assert with_skill.error is None and "No-go" in with_skill.text
    assert baseline.error is None and baseline.text == "Sounds fine, go ahead."
    assert "(progress output" not in with_skill.text, "only the final message may be used"

    prompt = "<criteria>\n- [C1] a\n</criteria>\n<response>\nVerdict: No-go\n</response>"
    payload, usage = cli.complete_json("Grade strictly.", prompt, VERDICT_SCHEMA, "verdicts")
    assert payload == {"verdicts": [{"id": "C1", "verdict": "pass", "evidence": "", "rationale": ""}]}
    assert usage.reported_cost_usd is None, "subscription CLIs report no per-token cost"

    first = calls(log)[0]
    assert "You are an expert." in (first["stdin"] + " ".join(first["args"])), "the shared persona reaches the tool"


def test_codex_profile_is_isolated_and_read_only(skill: Skill, log: Path) -> None:
    provider("codex", model="gpt-5", effort="high").run_native("Q", skill.root, "P", 12)
    args = calls(log)[0]["args"]
    for flag in ("exec", "--ephemeral", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules"):
        assert flag in args
    assert args[args.index("--sandbox") + 1] == "read-only"
    assert args[args.index("-m") + 1] == "gpt-5"
    assert args[args.index("-c") + 1] == "model_reasoning_effort=high"
    assert args[-1] == "-", "Codex reads the prompt from stdin"


def test_codex_judge_requests_structured_output(log: Path) -> None:
    provider("codex").complete_json("S", "<criteria>\n- [C1] a\n</criteria>", VERDICT_SCHEMA, "verdicts")
    args = calls(log)[0]["args"]
    schema_file = args[args.index("--output-schema") + 1]
    assert schema_file.endswith("schema.json")


def test_prompt_delivery_per_profile(log: Path) -> None:
    provider("copilot").run_native("Copilot prompt", None, "", 3)
    provider("gemini").run_native("Gemini prompt", None, "", 3)
    copilot, gemini = calls(log)
    assert copilot["args"][copilot["args"].index("-p") + 1] == "Copilot prompt" and copilot["stdin"] == ""
    assert "Gemini prompt" in gemini["stdin"]
    assert gemini["args"][gemini["args"].index("--output-format") + 1] == "json"


def test_inherit_omits_model_and_effort(log: Path) -> None:
    provider("codex", model="inherit", effort="inherit").run_native("Q", None, "", 3)
    args = calls(log)[0]["args"]
    assert "-m" not in args and "-c" not in args


def test_host_session_variables_are_stripped(log: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    provider("copilot").run_native("Q", None, "", 3)
    assert calls(log)[0]["has_claudecode"] is False


def test_failures_are_reported_not_raised(tmp_path: Path) -> None:
    failing = tmp_path / "fail.py"
    failing.write_text("import sys\nsys.stderr.write('not signed in')\nsys.exit(3)\n", encoding="utf-8")
    cli = AgentCliProvider(
        ModelSpec("x", "agent-cli", "inherit", True, {"profile": "copilot", "command": [sys.executable, str(failing)]})
    )
    result = cli.run_native("Q", None, "", 3)
    assert result.text == "" and "exited with 3: not signed in" in (result.error or "")
    with pytest.raises(ProviderError):
        cli.complete_json("S", "U", VERDICT_SCHEMA, "verdicts")


@pytest.mark.parametrize("profile", ["copilot", "cursor"])
def test_prompt_is_never_passed_to_a_windows_batch_file(
    profile: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agent_cli, "_WINDOWS", True)  # patching os.name would break pathlib off Windows
    shim = tmp_path / f"{profile}.CMD"
    shim.write_text("@echo off\r\n", encoding="utf-8")
    cli = AgentCliProvider(ModelSpec("x", "agent-cli", "inherit", True, {"profile": profile, "command": str(shim)}))
    result = cli.run_native('hi" & calc & "', None, "", 3)
    assert result.text == "" and "batch file" in (result.error or "")


def test_readiness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(agent_cli.shutil, "which", lambda name: None)
    missing = AgentCliProvider(ModelSpec("g", "agent-cli", "inherit", True, {"profile": "gemini"}))
    ok, detail = missing.check_ready()
    assert not ok and "not installed" in detail

    assert provider("codex").check_ready() == (True, "signed in")  # `codex login status` exits 0

    monkeypatch.setattr(agent_cli.Path, "home", staticmethod(lambda: tmp_path))
    for var in PROFILES["gemini"].ready_env:
        monkeypatch.delenv(var, raising=False)
    assert provider("gemini").check_ready()[0] is False
    (tmp_path / ".gemini").mkdir()
    (tmp_path / ".gemini" / "oauth_creds.json").write_text("{}", encoding="utf-8")
    assert provider("gemini").check_ready() == (True, "signed in (saved login found)")
    monkeypatch.setenv("COPILOT_GITHUB_TOKEN", "x")
    assert provider("copilot").check_ready() == (True, "credentials found in the environment")


def test_provider_factory_and_unknown_profile() -> None:
    spec = ModelSpec("c", "agent-cli", "inherit", True, {"profile": "codex", "command": FAKE})
    assert isinstance(create_provider(spec), AgentCliProvider)
    assert readiness(spec)[0] is True
    with pytest.raises(ValueError, match="Unknown agent CLI profile"):
        AgentCliProvider(ModelSpec("z", "agent-cli", "inherit", True, {"profile": "nope"}))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"verdicts": []}', {"verdicts": []}),
        ('Sure! ```json\n{"verdicts": [{"id": "C1"}]}\n``` Hope that helps.', {"verdicts": [{"id": "C1"}]}),
        ('{"a": 1} then {"b": {"c": 2}}', {"b": {"c": 2}}),
        ("no json here", None),
    ],
)
def test_extract_json_object(text: str, expected: dict[str, Any] | None) -> None:
    assert extract_json_object(text) == expected


def test_extract_answer_errors() -> None:
    with pytest.raises(ProviderError, match="no 'response' text"):
        extract_answer('{"other": 1}', "json:response")
    with pytest.raises(ProviderError, match="reported an error"):
        extract_answer('{"error": {"message": "quota"}}', "json:response")
