---
name: ai-regression-review
description: "Diagnose why an AI feature got worse, or review an AI incident, using the Gate 5 protocol."
argument-hint: "Describe what changed, when, and the metrics"
agent: agent
---

Use the **ai-product-governance** Agent Skill (in `.github/skills/` or `.agents/skills/`). Read its `SKILL.md` first and follow its operating rules.

Apply the Gate 5 regression diagnosis protocol (or incident process) to this situation:

${input:symptom:Describe what changed, when, and the metrics}

1. Read only these playbooks from the skill: `references/gate-5-operate-and-improve.md`.
2. Use the template `assets/templates/incident-review.md` and keep every section.
3. Run the skill's `scripts/risk_tier.py` and `scripts/unit_economics.py` for risk tiers and costs; never estimate them by hand.
4. If `.ai-governance/policy.json` exists in this repository, it overrides the default policy.
5. Save the result as `docs/ai-governance/<feature>-incident-review.md` unless asked otherwise.
