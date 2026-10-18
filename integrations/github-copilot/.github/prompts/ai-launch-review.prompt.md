---
name: ai-launch-review
description: "Decide Go, Go with conditions or No-go for an AI launch and plan a staged rollout (Gate 4)."
argument-hint: "Paste the feature's current status, eval results and open items"
agent: agent
---

Use the **ai-product-governance** Agent Skill (in `.github/skills/` or `.agents/skills/`). Read its `SKILL.md` first and follow its operating rules.

Run Gate 4 (launch readiness) on this status and give a Go, Go with conditions or No-go decision:

${input:status:Paste the feature's current status, eval results and open items}

1. Read only these playbooks from the skill: `references/gate-4-launch-readiness.md`.
2. Use the template `assets/templates/launch-readiness-review.md` and keep every section.
3. Run the skill's `scripts/risk_tier.py` and `scripts/unit_economics.py` for risk tiers and costs; never estimate them by hand.
4. If `.ai-governance/policy.json` exists in this repository, it overrides the default policy.
5. Save the result as `docs/ai-governance/<feature>-launch-readiness-review.md` unless asked otherwise.
