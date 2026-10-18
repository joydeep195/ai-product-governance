---
name: ai-business-case
description: "Price an AI feature per completed task and decide whether it is worth building (Gate 1)."
argument-hint: "Describe the feature, volumes, model prices and today's cost"
agent: agent
---

Use the **ai-product-governance** Agent Skill (in `.github/skills/` or `.agents/skills/`). Read its `SKILL.md` first and follow its operating rules.

Run Gate 1 (value and economics) for this feature and produce the business case:

${input:feature:Describe the feature, volumes, model prices and today's cost}

1. Read only these playbooks from the skill: `references/gate-1-value-and-economics.md`.
2. Use the template `assets/templates/business-case.md` and keep every section.
3. Run the skill's `scripts/risk_tier.py` and `scripts/unit_economics.py` for risk tiers and costs; never estimate them by hand.
4. If `.ai-governance/policy.json` exists in this repository, it overrides the default policy.
5. Save the result as `docs/ai-governance/<feature>-business-case.md` unless asked otherwise.
