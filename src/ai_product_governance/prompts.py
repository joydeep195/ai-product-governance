"""Compose self-contained workflow prompts from the skill.

Used by the MCP server's prompts and the eval harness. A composed prompt carries the
operating rules, the relevant gate playbooks and the template, so it works in clients
that cannot read files or call tools.
"""

from __future__ import annotations

from ai_product_governance.skill import Skill
from ai_product_governance.workflows import EVAL_WORKFLOW, Workflow


def compose_eval_prompt(skill: Skill, options: str) -> str:
    """The /ai-eval procedure from the skill, plus whatever the user asked for (scenarios, trials)."""
    return "\n".join(
        [
            skill.read_reference(EVAL_WORKFLOW.reference).strip(),
            "",
            "## The user's options",
            "",
            options.strip() or "None given: run the full suite with one trial.",
            "",
        ]
    )


def compose_workflow_prompt(skill: Skill, flow: Workflow, value: str, policy_label: str) -> str:
    parts = [
        f"# {flow.title}",
        "",
        "You are applying the **AI Product Governance** method.",
        "",
        skill.section("role"),
        "",
        "## Operating rules",
        "",
        skill.section("rules"),
        "",
        "## Policy",
        "",
        f"Apply the governance policy **{policy_label}**. Use the `classify_risk_tier` and "
        "`calculate_unit_economics` tools for tiers and costs when they are available; otherwise apply "
        "the formulas in the playbooks and show your working.",
        "",
        "## Task",
        "",
        flow.render_task(value.strip() or "(no details given: ask up to three targeted questions)"),
        "",
    ]
    for name in flow.references:
        parts += [f"## Playbook: {name}", "", skill.read_reference(name).strip(), ""]
    parts += [
        f"## Template: {flow.template}",
        "",
        skill.read_template(flow.template).strip(),
        "",
        "## Output standards",
        "",
        skill.section("output"),
        "",
    ]
    return "\n".join(parts)
