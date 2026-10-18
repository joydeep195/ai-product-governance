"""MCP server: the governance skill for any MCP-capable AI client.

Exposes the skill as
  * tools     - instructions, playbooks, templates, the effective policy, and the two
                deterministic engines (risk tier, unit economics);
  * prompts   - one self-contained prompt per governance workflow;
  * resources - SKILL.md, every playbook and template, and the effective policy.

Security model: every tool is read-only and side-effect free. The policy is fixed when
the server starts (--policy, $AIPG_POLICY or the workspace policy) and can never be
chosen or overridden through a tool argument, so a prompt-injected model cannot point
the server at arbitrary files. Reference and template names are checked against an
allow-list built from the bundle's own directory listing.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError, ToolError
from mcp_types import ToolAnnotations

from ai_product_governance import __version__, engines
from ai_product_governance.policy import EffectivePolicy, load_effective_policy
from ai_product_governance.prompts import compose_workflow_prompt
from ai_product_governance.skill import Skill, load_skill
from ai_product_governance.workflows import WORKFLOWS, Workflow

SERVER_NAME = "ai-product-governance"
REPOSITORY_URL = "https://github.com/joydeep195/ai-product-governance"

_READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

_MCP_PREAMBLE = """\
> **Using this skill over MCP.** Wherever the instructions below mention a file, use these tools instead:
> `references/<name>.md` -> `get_reference(name)`, `assets/templates/<name>.md` -> `get_template(name)`,
> the policy file -> `get_policy()`, `scripts/risk_tier.py` -> `get_risk_questionnaire()` then
> `classify_risk_tier(answers)`, `scripts/unit_economics.py` -> `calculate_unit_economics(inputs)`.
> The effective policy for this server is **{policy}**.

"""


def build_server(policy_path: str | None = None) -> MCPServer[Any]:
    """Create the MCP server. The policy is resolved once, at start-up."""
    skill = load_skill()
    policy = load_effective_policy(policy_path)
    risk_engine = engines.risk_tier()
    economics_engine = engines.unit_economics()

    server: MCPServer[Any] = MCPServer(
        name=SERVER_NAME,
        title="AI Product Governance",
        description="Enterprise AI product governance: fit, economics, evals, risk tiers, controls, launch and operations.",
        version=__version__,
        website_url=REPOSITORY_URL,
        instructions=(
            "Governs AI and LLM features from idea to production. Call get_governance_instructions first, "
            "then load only the playbook for the relevant gate. Use classify_risk_tier and "
            "calculate_unit_economics for tiers and costs instead of estimating them. "
            f"Effective policy: {policy.label}."
        ),
    )

    _register_tools(server, skill, policy, risk_engine, economics_engine)
    _register_resources(server, skill, policy)
    _register_prompts(server, skill, policy)
    return server


def _register_tools(
    server: MCPServer[Any], skill: Skill, policy: EffectivePolicy, risk_engine: Any, economics_engine: Any
) -> None:
    @server.tool(
        title="Get governance instructions",
        description="Return the operating rules, the six-gate lifecycle router and the output standards. Call this first.",
        annotations=_READ_ONLY,
    )
    def get_governance_instructions() -> str:
        return _MCP_PREAMBLE.format(policy=policy.label) + skill.clean_body

    @server.tool(
        title="Get gate playbook",
        description="Return a playbook (reference) by name. Available: " + ", ".join(skill.reference_names),
        annotations=_READ_ONLY,
    )
    def get_reference(name: str) -> str:
        try:
            return skill.read_reference(name)
        except KeyError as exc:
            raise ToolError(_message(exc)) from exc

    @server.tool(
        title="Get artifact template",
        description="Return an artifact template by name. Available: " + ", ".join(skill.template_names),
        annotations=_READ_ONLY,
    )
    def get_template(name: str) -> str:
        try:
            return skill.read_template(name)
        except KeyError as exc:
            raise ToolError(_message(exc)) from exc

    @server.tool(
        title="Get effective policy",
        description="Return the governance policy this server enforces: tiers, rules, controls, approvers, eval minimums.",
        annotations=_READ_ONLY,
    )
    def get_policy() -> dict[str, Any]:
        return {"policy": policy.document, "source": policy.source, "label": policy.label}

    @server.tool(
        title="Get risk questionnaire",
        description="Return the questions classify_risk_tier expects, with their types and allowed options.",
        annotations=_READ_ONLY,
    )
    def get_risk_questionnaire() -> list[dict[str, Any]]:
        return list(policy.document["questions"])

    @server.tool(
        title="Classify risk tier",
        description=(
            "Deterministically classify an AI use case against the effective policy. `answers` maps question IDs "
            "from get_risk_questionnaire to values. Returns the tier, triggered rules, unanswered questions, required "
            "controls, approvers, eval minimums and the autonomy cap at launch."
        ),
        annotations=_READ_ONLY,
    )
    def classify_risk_tier(answers: dict[str, Any]) -> dict[str, Any]:
        try:
            result: dict[str, Any] = risk_engine.classify(
                policy.document, answers, policy_source=policy.source, policy_path=None
            )
        except risk_engine.AnswerError as exc:
            raise ToolError(f"{exc}. Call get_risk_questionnaire for valid IDs and values.") from exc
        return result

    @server.tool(
        title="Calculate unit economics",
        description=(
            "Price an AI feature per completed task (model cost + review time + expected failure handling). "
            "Required inputs: price_input_per_mtok, price_output_per_mtok, input_tokens_per_call, "
            "output_tokens_per_call, tasks_per_month, success_rate (0-1), baseline_cost_per_task. Optional: "
            "calls_per_task, cache_read_price_per_mtok, cached_input_fraction, other_cost_per_task, "
            "review_minutes_per_task, fallback_minutes_per_failure, loaded_hourly_cost, fixed_monthly_cost, "
            "one_time_cost, currency, label."
        ),
        annotations=_READ_ONLY,
    )
    def calculate_unit_economics(inputs: dict[str, Any]) -> dict[str, Any]:
        try:
            result: dict[str, Any] = economics_engine.calculate(inputs)
        except economics_engine.InputError as exc:
            raise ToolError(str(exc)) from exc
        return result


def _register_resources(server: MCPServer[Any], skill: Skill, policy: EffectivePolicy) -> None:
    @server.resource("aipg://skill", name="SKILL.md", mime_type="text/markdown", description="The skill instructions")
    def skill_document() -> str:
        return skill.clean_body

    @server.resource(
        "aipg://references/{name}", name="Gate playbook", mime_type="text/markdown", description="A gate playbook"
    )
    def reference(name: str) -> str:
        try:
            return skill.read_reference(name)
        except KeyError as exc:
            raise ResourceNotFoundError(_message(exc)) from exc

    @server.resource(
        "aipg://templates/{name}",
        name="Artifact template",
        mime_type="text/markdown",
        description="An artifact template",
    )
    def template(name: str) -> str:
        try:
            return skill.read_template(name)
        except KeyError as exc:
            raise ResourceNotFoundError(_message(exc)) from exc

    @server.resource(
        "aipg://policy", name="Effective policy", mime_type="application/json", description="The enforced policy"
    )
    def policy_document() -> str:
        return json.dumps(policy.document, indent=2)


def _register_prompts(server: MCPServer[Any], skill: Skill, policy: EffectivePolicy) -> None:
    for flow in WORKFLOWS:
        _register_prompt(server, skill, policy, flow)


def _register_prompt(server: MCPServer[Any], skill: Skill, policy: EffectivePolicy, flow: Workflow) -> None:
    # The prompt function's parameter name becomes the MCP prompt argument name, so each
    # workflow gets a small adapter with the right signature.
    def render(value: str) -> str:
        return compose_workflow_prompt(skill, flow, value, policy.label)

    adapters = {
        "idea": lambda idea: render(idea),
        "feature": lambda feature: render(feature),
        "status": lambda status: render(status),
        "symptom": lambda symptom: render(symptom),
        "context": lambda context: render(context),
    }
    function = adapters[flow.argument]
    server.prompt(name=flow.id, title=flow.title, description=flow.description)(function)


def _message(exc: KeyError) -> str:
    return str(exc.args[0]) if exc.args else str(exc)


def serve(transport: str = "stdio", host: str = "127.0.0.1", port: int = 8000, policy_path: str | None = None) -> None:
    server = build_server(policy_path)
    if transport == "stdio":
        server.run("stdio")
    elif transport == "streamable-http":
        server.run("streamable-http", host=host, port=port)
    else:
        raise ValueError(f"Unsupported transport: {transport}")
