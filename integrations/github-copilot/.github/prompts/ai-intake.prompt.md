---
name: ai-intake
description: "Decide whether a use case needs AI at all (Gate 0) and produce a use-case brief with a fit verdict."
argument-hint: "Describe the idea, problem or request"
agent: agent
---

Use the **ai-product-governance** Agent Skill (in `.github/skills/` or `.agents/skills/`). Read its `SKILL.md` first and follow its operating rules.

Run Gate 0 (intake and AI fit) for this idea and produce the use-case brief with a fit verdict:

${input:idea:Describe the idea, problem or request}

1. Read only these playbooks from the skill: `references/gate-0-intake-and-fit.md`.
2. Use the template `assets/templates/use-case-brief.md` and keep every section.
3. Run the skill's `scripts/risk_tier.py` and `scripts/unit_economics.py` for risk tiers and costs; never estimate them by hand.
4. If `.ai-governance/policy.json` exists in this repository, it overrides the default policy.
5. Save the result as `docs/ai-governance/<feature>-use-case-brief.md` unless asked otherwise.
