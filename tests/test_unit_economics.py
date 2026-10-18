from __future__ import annotations

import json
from types import ModuleType
from typing import Any

import pytest

SUPPORT_CASE: dict[str, Any] = {
    "price_input_per_mtok": 3,
    "price_output_per_mtok": 15,
    "input_tokens_per_call": 6000,
    "output_tokens_per_call": 800,
    "calls_per_task": 3,
    "success_rate": 0.7,
    "review_minutes_per_task": 1,
    "fallback_minutes_per_failure": 9,
    "loaded_hourly_cost": 40,
    "baseline_cost_per_task": 8 * 40 / 60,
    "tasks_per_month": 40000,
}


def test_support_case_matches_hand_calculation(economics_engine: ModuleType) -> None:
    r = economics_engine.calculate(SUPPORT_CASE)["results"]
    assert r["model_cost_per_call"] == pytest.approx(0.03)
    assert r["ai_cost_per_attempt"] == pytest.approx(0.09)
    assert r["review_cost_per_task"] == pytest.approx(0.6667, abs=1e-4)
    assert r["expected_failure_cost_per_task"] == pytest.approx(1.8)
    assert r["cost_per_completed_task"] == pytest.approx(2.5567, abs=1e-4)
    assert r["savings_per_task"] == pytest.approx(2.7767, abs=1e-4)
    assert r["monthly_net_benefit"] == pytest.approx(111066.67, abs=0.01)
    assert r["break_even_success_rate"] == pytest.approx(0.2372, abs=1e-4)
    assert r["payback_months"] == 0.0


def test_human_cost_dominates_note(economics_engine: ModuleType) -> None:
    notes = economics_engine.calculate(SUPPORT_CASE)["notes"]
    assert any("more than half the cost" in note for note in notes)


def test_prompt_caching_reduces_model_cost(economics_engine: ModuleType) -> None:
    cached = {**SUPPORT_CASE, "cached_input_fraction": 0.5, "cache_read_price_per_mtok": 0.3}
    base = economics_engine.calculate(SUPPORT_CASE)["results"]["model_cost_per_call"]
    assert economics_engine.calculate(cached)["results"]["model_cost_per_call"] == pytest.approx(
        (3000 * 3 + 3000 * 0.3 + 800 * 15) / 1e6
    )
    assert economics_engine.calculate(cached)["results"]["model_cost_per_call"] < base


def test_sensitivity_table(economics_engine: ModuleType) -> None:
    rows = {row["scenario"]: row for row in economics_engine.calculate(SUPPORT_CASE)["sensitivity"]}
    assert set(rows) == {"Base case", "Success rate -20 points", "Volume x0.5", "Volume x2", "Tokens x1.5"}
    assert rows["Success rate -20 points"]["cost_per_completed_task"] == pytest.approx(3.7567, abs=1e-4)
    assert rows["Volume x2"]["monthly_net_benefit"] == pytest.approx(2 * rows["Base case"]["monthly_net_benefit"])


def test_never_breaks_even(economics_engine: ModuleType) -> None:
    result = economics_engine.calculate({**SUPPORT_CASE, "baseline_cost_per_task": 0.5})
    assert result["results"]["break_even_success_rate"] is None
    assert result["results"]["payback_months"] is None
    assert any("Even at 100% success" in note for note in result["notes"])


def test_cheaper_even_if_everything_fails(economics_engine: ModuleType) -> None:
    result = economics_engine.calculate({**SUPPORT_CASE, "fallback_minutes_per_failure": 2})
    assert result["results"]["break_even_success_rate"] == 0.0


def test_below_break_even_note(economics_engine: ModuleType) -> None:
    result = economics_engine.calculate({**SUPPORT_CASE, "success_rate": 0.2})
    assert any(note.startswith("Below break-even") for note in result["notes"])


def test_payback_with_one_time_cost(economics_engine: ModuleType) -> None:
    result = economics_engine.calculate({**SUPPORT_CASE, "one_time_cost": 222133.34, "fixed_monthly_cost": 0})
    assert result["results"]["payback_months"] == pytest.approx(2.0, abs=0.01)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"success_rate": 1.5}, "at most 1"),
        ({"price_input_per_mtok": -1}, "at least 0"),
        ({"tasks_per_month": "lots"}, "must be a number"),
        ({"calls_per_task": 0}, "greater than 0"),
        ({"surprise_field": 1}, "unknown fields"),
        ({"loaded_hourly_cost": 0}, "loaded_hourly_cost"),
    ],
)
def test_invalid_inputs(economics_engine: ModuleType, change: dict[str, Any], message: str) -> None:
    with pytest.raises(economics_engine.InputError, match=message):
        economics_engine.calculate({**SUPPORT_CASE, **change})


def test_missing_required_field(economics_engine: ModuleType) -> None:
    incomplete = {k: v for k, v in SUPPORT_CASE.items() if k != "success_rate"}
    with pytest.raises(economics_engine.InputError, match="missing required field 'success_rate'"):
        economics_engine.calculate(incomplete)


def test_example_is_valid_and_round_trips(economics_engine: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    assert economics_engine.main(["--example"]) == 0
    example = json.loads(capsys.readouterr().out)
    assert economics_engine.main(["--input-json", json.dumps(example), "--format", "md"]) == 0
    out = capsys.readouterr().out
    assert "Cost per completed task" in out and out.isascii()
