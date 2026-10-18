"""The manual eval kit: a full create -> answer -> grade -> score cycle with no model access."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_product_governance.cli import main
from ai_product_governance.evals.config import EvalConfig, load_config
from ai_product_governance.evals.kit import PASTE_MARKER, KitError, create_kit, prepare_grading, read_reply, score_kit
from ai_product_governance.evals.scenarios import Scenario, load_scenarios
from ai_product_governance.skill import Skill


@pytest.fixture
def config(repo: Path) -> EvalConfig:
    return load_config(repo / "evals" / "eval.config.json")


@pytest.fixture
def scenarios(repo: Path) -> list[Scenario]:
    chosen = {"g4-claims-triage-launch", "g5-acceptance-regression"}
    return [s for s in load_scenarios(repo / "evals" / "scenarios") if s.id in chosen]


def paste(path: Path, text: str) -> None:
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def test_full_manual_cycle(tmp_path: Path, config: EvalConfig, skill: Skill, scenarios: list[Scenario]) -> None:
    kit = create_kit(tmp_path, config, skill, scenarios, trials=1, tool="ChatGPT (GPT-5)")
    manifest = json.loads((kit / "kit.json").read_text(encoding="utf-8"))
    answers = manifest["answers"]
    assert [a["arm"] for a in answers] == ["with-skill", "with-skill", "baseline", "baseline"]
    sheet = (kit / "1-ANSWERS.md").read_text(encoding="utf-8")
    assert "Part A: WITH the skill" in sheet and "Part B: WITHOUT the skill" in sheet
    assert all(f"answers/{a['id']}.md" in sheet for a in answers)

    with pytest.raises(KitError, match="still empty"):
        prepare_grading(kit, scenarios)
    with pytest.raises(KitError, match="Grading has not been prepared"):
        score_kit(kit, config, skill, scenarios)

    for entry in answers:
        reply = "Verdict: No-go. Blocking gaps listed." if entry["arm"] == "with-skill" else "Go ahead, ship it."
        paste(kit / "answers" / f"{entry['id']}.md", reply)
    grading_sheet = prepare_grading(kit, scenarios).read_text(encoding="utf-8")
    grading = json.loads((kit / "kit.json").read_text(encoding="utf-8"))["grading"]
    assert len(grading) == 4 and "WITH the skill" not in grading_sheet, "grading prompts must be blind"

    with pytest.raises(KitError, match="contain no JSON"):
        score_kit(kit, config, skill, scenarios)

    by_answer = {a["id"]: a for a in answers}
    for entry in grading:
        answer = by_answer[entry["answer"]]
        scenario = next(s for s in scenarios if s.id == answer["scenario"])
        good = answer["arm"] == "with-skill"
        verdicts = [
            {"id": c.id, "verdict": "pass" if good else "fail", "evidence": "", "rationale": ""}
            for c in scenario.criteria
        ]
        paste(kit / "verdicts" / f"{entry['id']}.md", "```json\n" + json.dumps({"verdicts": verdicts}) + "\n```")

    paths, gates = score_kit(kit, config, skill, scenarios)
    results = json.loads(paths["results"].read_text(encoding="utf-8"))
    arms = {a["arm"]: a for a in results["arms"]}
    assert arms["baseline"]["mean_score"] < arms["with-skill"]["mean_score"]
    assert arms["with-skill"]["critical_failures"] == 0
    assert {g.name for g in gates} >= {"min_with_skill_score", "min_delta"}
    report = paths["report"].read_text(encoding="utf-8")
    assert "ChatGPT (GPT-5)" in report


def test_read_reply_ignores_the_marker_and_tolerates_its_removal(tmp_path: Path) -> None:
    path = tmp_path / "a.md"
    path.write_text(f"{PASTE_MARKER}\n\n  The answer.  \n", encoding="utf-8")
    assert read_reply(path) == "The answer."
    path.write_text("Marker deleted, answer only.", encoding="utf-8")
    assert read_reply(path) == "Marker deleted, answer only."
    assert read_reply(tmp_path / "missing.md") == ""


def test_kit_commands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "kits"
    assert (
        main(["eval-kit", "create", "--out", str(out), "--scenario", "g0-deterministic-first", "--tool", "Gemini"]) == 0
    )
    kit = next(out.iterdir())
    assert "collect 2 answers" in capsys.readouterr().out
    assert main(["eval-kit", "grade", str(kit)]) == 2
    assert "still empty" in capsys.readouterr().err
