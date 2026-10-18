from __future__ import annotations

import json
import shutil
import tomllib
from pathlib import Path

from ai_product_governance.adapters import (
    PROMPT_PACK_CHAR_LIMIT,
    build_outputs,
    check_outputs,
    prompt_pack_instructions,
    write_outputs,
)
from ai_product_governance.skill import Skill
from ai_product_governance.workflows import WORKFLOWS


def test_committed_integrations_are_up_to_date(repo: Path) -> None:
    assert check_outputs(repo, build_outputs(repo)) == [], "run `aipg build` and commit the result"


def test_build_is_deterministic(repo: Path) -> None:
    assert build_outputs(repo) == build_outputs(repo)


def test_prompt_pack_fits_instruction_limits(skill: Skill) -> None:
    instructions = prompt_pack_instructions(skill)
    assert len(instructions) <= PROMPT_PACK_CHAR_LIMIT
    for name in skill.reference_names:
        assert f"`{name}.md`" in instructions, f"instructions never point the assistant at {name}.md"


def test_prompt_pack_knowledge_is_flat_and_complete(repo: Path, skill: Skill) -> None:
    outputs = build_outputs(repo)
    knowledge = [p for p in outputs if p.startswith("integrations/prompt-pack/knowledge/")]
    assert all(p.count("/") == 3 for p in knowledge), "knowledge files must be flat for upload"
    assert len(knowledge) <= 20, "ChatGPT custom GPTs accept at most 20 knowledge files"
    names = {p.rsplit("/", 1)[1] for p in knowledge}
    assert {"default-policy.json", "risk_tier.py", "unit_economics.py", "templates.md"} <= names


def test_flattened_risk_script_finds_its_policy(repo: Path, tmp_path: Path) -> None:
    """In a flat knowledge folder (e.g. ChatGPT's sandbox) the script must find default-policy.json beside it."""
    import subprocess
    import sys

    knowledge = repo / "integrations" / "prompt-pack" / "knowledge"
    flat = tmp_path / "data"
    flat.mkdir()
    for name in ("risk_tier.py", "default-policy.json"):
        shutil.copy(knowledge / name, flat / name)
    completed = subprocess.run(
        [sys.executable, str(flat / "risk_tier.py"), "--validate-policy"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_one_copilot_prompt_per_workflow(repo: Path) -> None:
    outputs = build_outputs(repo)
    for flow in WORKFLOWS:
        content = outputs[f"integrations/github-copilot/.github/prompts/{flow.id}.prompt.md"]
        assert content.startswith("---\n")
        assert f"name: {flow.id}\n" in content
        assert "${input:" in content
        assert f"assets/templates/{flow.template}.md" in content


def test_mcp_configs_are_valid(repo: Path) -> None:
    outputs = build_outputs(repo)
    for path, content in outputs.items():
        if path.startswith("integrations/mcp/") and path.endswith(".json"):
            json.loads(content)
    tomllib.loads(outputs["integrations/mcp/codex.config.toml"])


def test_write_and_check_detect_drift_and_stale_files(repo: Path, tmp_path: Path) -> None:
    outputs = build_outputs(repo)
    assert write_outputs(tmp_path, outputs)
    assert check_outputs(tmp_path, outputs) == []
    first = next(iter(outputs))
    (tmp_path / first).write_text("tampered", encoding="utf-8")
    stale = tmp_path / "integrations" / "old.md"
    stale.write_text("left over", encoding="utf-8")
    problems = check_outputs(tmp_path, outputs)
    assert f"out of date: {first}" in problems
    assert "stale: integrations/old.md" in problems
    write_outputs(tmp_path, outputs)
    assert check_outputs(tmp_path, outputs) == []
