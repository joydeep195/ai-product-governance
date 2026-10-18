## AI product governance

This repository vendors the `ai-product-governance` Agent Skill at `.agents/skills/ai-product-governance/`.

When a task involves planning, specifying, evaluating, approving, launching or troubleshooting an AI or
LLM feature:

1. Read `.agents/skills/ai-product-governance/SKILL.md` and follow its operating rules and gate router.
2. Load only the playbook in `references/` for the gate the task concerns.
3. Use the templates in `assets/templates/` and save artifacts under `docs/ai-governance/`.
4. Compute risk tiers and costs with `python .agents/skills/ai-product-governance/scripts/risk_tier.py` and
   `scripts/unit_economics.py`; never estimate them by hand.
5. If `.ai-governance/policy.json` exists, it overrides the bundled default policy.
