---
name: ai-prd
description: "Write an AI PRD with a fit verdict, quality bar, failure design, economics, risk tier, controls and rollout."
argument-hint: "Describe the feature and its users"
agent: agent
---

Use the **ai-product-governance** Agent Skill (in `.github/skills/` or `.agents/skills/`). Read its `SKILL.md` first and follow its operating rules.

Write an AI PRD for this feature. If Gate 0 has not been passed, run the fit check first:

${input:feature:Describe the feature and its users}

1. Read only these playbooks from the skill: `references/gate-0-intake-and-fit.md`, `references/gate-2-quality-and-evals.md`, `references/gate-3-risk-and-controls.md`.
2. Use the template `assets/templates/ai-prd.md` and keep every section.
3. Run the skill's `scripts/risk_tier.py` and `scripts/unit_economics.py` for risk tiers and costs; never estimate them by hand.
4. If `.ai-governance/policy.json` exists in this repository, it overrides the default policy.
5. Save the result as `docs/ai-governance/<feature>-ai-prd.md` unless asked otherwise.
