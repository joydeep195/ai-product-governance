---
name: ai-risk-review
description: "Classify the risk tier against the policy, build the risk register and map required controls (Gate 3)."
argument-hint: "Describe the feature, its users, data and actions"
agent: agent
---

Use the **ai-product-governance** Agent Skill (in `.github/skills/` or `.agents/skills/`). Read its `SKILL.md` first and follow its operating rules.

Run Gate 3 (risk and controls) for this feature and produce the risk assessment:

${input:feature:Describe the feature, its users, data and actions}

1. Read only these playbooks from the skill: `references/gate-3-risk-and-controls.md`.
2. Use the template `assets/templates/risk-assessment.md` and keep every section.
3. Run the skill's `scripts/risk_tier.py` and `scripts/unit_economics.py` for risk tiers and costs; never estimate them by hand.
4. If `.ai-governance/policy.json` exists in this repository, it overrides the default policy.
5. Save the result as `docs/ai-governance/<feature>-risk-assessment.md` unless asked otherwise.
