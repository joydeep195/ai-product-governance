from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from mcp import Client

from ai_product_governance.mcp_server import build_server
from ai_product_governance.workflows import EVAL_WORKFLOW, WORKFLOWS

EXPECTED_TOOLS = {
    "get_governance_instructions",
    "get_reference",
    "get_template",
    "get_policy",
    "get_risk_questionnaire",
    "classify_risk_tier",
    "calculate_unit_economics",
}


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_tools_are_registered_and_read_only() -> None:
    async def scenario() -> None:
        async with Client(build_server()) as client:
            tools = (await client.list_tools()).tools
            assert {t.name for t in tools} == EXPECTED_TOOLS
            for tool in tools:
                assert tool.annotations is not None
                assert tool.annotations.read_only_hint is True
                assert tool.annotations.destructive_hint is False

    run(scenario())


def test_classify_risk_tier_returns_structured_result() -> None:
    async def scenario() -> None:
        async with Client(build_server()) as client:
            result = await client.call_tool("classify_risk_tier", {"answers": {"consequential_decisions": True}})
            assert not result.is_error
            assert result.structured_content is not None
            assert result.structured_content["tier"]["id"] == "high"

    run(scenario())


def test_invalid_answers_return_actionable_tool_error() -> None:
    async def scenario() -> None:
        async with Client(build_server()) as client:
            result = await client.call_tool("classify_risk_tier", {"answers": {"bogus": True}})
            assert result.is_error
            text = result.content[0].text  # type: ignore[union-attr]
            assert "unknown question IDs: bogus" in text
            assert "get_risk_questionnaire" in text

    run(scenario())


def test_unit_economics_tool() -> None:
    inputs = {
        "price_input_per_mtok": 3,
        "price_output_per_mtok": 15,
        "input_tokens_per_call": 6000,
        "output_tokens_per_call": 800,
        "calls_per_task": 3,
        "success_rate": 0.7,
        "review_minutes_per_task": 1,
        "fallback_minutes_per_failure": 9,
        "loaded_hourly_cost": 40,
        "baseline_cost_per_task": 5.3333,
        "tasks_per_month": 40000,
    }

    async def scenario() -> None:
        async with Client(build_server()) as client:
            result = await client.call_tool("calculate_unit_economics", {"inputs": inputs})
            assert not result.is_error
            assert result.structured_content is not None
            assert result.structured_content["results"]["cost_per_completed_task"] == pytest.approx(2.5567, 1e-3)

    run(scenario())


def test_path_traversal_is_refused_with_a_helpful_message() -> None:
    async def scenario() -> None:
        async with Client(build_server()) as client:
            result = await client.call_tool("get_reference", {"name": "../../pyproject"})
            assert result.is_error
            assert "Available:" in result.content[0].text  # type: ignore[union-attr]

    run(scenario())


def test_prompts_cover_every_workflow() -> None:
    async def scenario() -> None:
        async with Client(build_server()) as client:
            prompts = {p.name: p for p in (await client.list_prompts()).prompts}
            assert set(prompts) == {flow.id for flow in WORKFLOWS} | {EVAL_WORKFLOW.id}
            for flow in WORKFLOWS:
                assert [a.name for a in prompts[flow.id].arguments or []] == [flow.argument]
            rendered = await client.get_prompt("ai-launch-review", {"status": "Kill switch untested"})
            text = rendered.messages[0].content.text  # type: ignore[union-attr]
            assert "Kill switch untested" in text
            assert "Gate 4" in text and "aipg-default v1.1.0" in text

    run(scenario())


def test_eval_prompt_carries_the_procedure_and_the_options() -> None:
    async def scenario() -> None:
        async with Client(build_server()) as client:
            prompt = next(p for p in (await client.list_prompts()).prompts if p.name == EVAL_WORKFLOW.id)
            [argument] = prompt.arguments or []
            assert argument.name == "options" and not argument.required
            plain = await client.get_prompt(EVAL_WORKFLOW.id)
            text = plain.messages[0].content.text  # type: ignore[union-attr]
            assert "aipg eval-kit create --agent-run" in text and "fresh sub-agent" in text
            assert "None given: run the full suite with one trial." in text
            chosen = await client.get_prompt(EVAL_WORKFLOW.id, {"options": "only g0-deterministic-first"})
            assert "only g0-deterministic-first" in chosen.messages[0].content.text  # type: ignore[union-attr]

    run(scenario())


def test_resources() -> None:
    async def scenario() -> None:
        async with Client(build_server()) as client:
            uris = {str(r.uri) for r in (await client.list_resources()).resources}
            assert {"aipg://skill", "aipg://policy"} <= uris
            templates = {t.uri_template for t in (await client.list_resource_templates()).resource_templates}
            assert {"aipg://references/{name}", "aipg://templates/{name}"} <= templates
            policy = await client.read_resource("aipg://policy")
            assert json.loads(policy.contents[0].text)["policy_id"] == "aipg-default"  # type: ignore[union-attr]

    run(scenario())


def test_policy_is_fixed_at_start_up(tmp_path: Path, policy: dict[str, Any]) -> None:
    policy["policy_id"] = "acme-ai-policy"
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")

    async def scenario() -> None:
        async with Client(build_server(str(path))) as client:
            result = await client.call_tool("get_policy", {})
            assert result.structured_content is not None
            assert result.structured_content["label"] == "acme-ai-policy v1.1.0"
            # The tools expose no parameter for choosing another policy file.
            tools = {t.name: t for t in (await client.list_tools()).tools}
            assert set(tools["classify_risk_tier"].input_schema["properties"]) == {"answers"}

    run(scenario())


def test_invalid_policy_prevents_start_up(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_text('{"policy_id": "broken"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid policy"):
        build_server(str(path))


def test_stdio_transport_end_to_end() -> None:
    """Launch `python -m ai_product_governance serve` as a subprocess, exactly as an MCP client would."""
    import sys

    from mcp import StdioServerParameters

    async def scenario() -> None:
        params = StdioServerParameters(command=sys.executable, args=["-m", "ai_product_governance", "serve"])
        async with Client(params) as client:
            assert client.server_info is not None and client.server_info.name == "ai-product-governance"
            result = await client.call_tool("classify_risk_tier", {"answers": {"vulnerable_users": True}})
            assert result.structured_content is not None
            assert result.structured_content["tier"]["id"] == "high"

    run(scenario())
