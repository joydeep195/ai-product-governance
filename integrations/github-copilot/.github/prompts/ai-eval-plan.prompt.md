---
name: ai-eval-plan
description: "Define the quality bar, golden set, grading methods and thresholds for an AI feature (Gate 2)."
argument-hint: "Describe the feature and what good output looks like"
agent: agent
---

Use the **ai-product-governance** Agent Skill (in `.github/skills/` or `.agents/skills/`). Read its `SKILL.md` first and follow its operating rules.

Run Gate 2 (quality and evals) for this feature and produce the eval plan:

${input:feature:Describe the feature and what good output looks like}

1. Read only these playbooks from the skill: `references/gate-2-quality-and-evals.md`.
2. Use the template `assets/templates/eval-plan.md` and keep every section.
3. Run the skill's `scripts/risk_tier.py` and `scripts/unit_economics.py` for risk tiers and costs; never estimate them by hand.
4. If `.ai-governance/policy.json` exists in this repository, it overrides the default policy.
5. Save the result as `docs/ai-governance/<feature>-eval-plan.md` unless asked otherwise.
