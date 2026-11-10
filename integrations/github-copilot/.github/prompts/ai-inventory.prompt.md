---
name: ai-inventory
description: "Find every AI use in a product or repository, apart from development tools, and route each to its gate, or record a clean 'No AI found' with what was searched."
argument-hint: "Name the product, repository or paths to search, and the third-party tools it relies on"
agent: agent
---

Use the **ai-product-governance** Agent Skill (in `.github/skills/` or `.agents/skills/`). Read its `SKILL.md` first and follow its operating rules.

Run AI discovery on this scope and produce the AI inventory. Route each AI use you find to its next gate; if you find none, record 'No AI found' with what was searched and what was not covered:

${input:scope:Name the product, repository or paths to search, and the third-party tools it relies on}

1. Read only these playbooks from the skill: `references/ai-discovery.md`.
2. Use the template `assets/templates/ai-inventory.md` and keep every section.
3. Run the skill's `scripts/risk_tier.py` and `scripts/unit_economics.py` for risk tiers and costs (and `scripts/ai_inventory.py` to scan for AI); never estimate tiers or costs by hand.
4. If `.ai-governance/policy.json` exists in this repository, it overrides the default policy.
5. Save the result as `docs/ai-governance/<feature>-ai-inventory.md` unless asked otherwise.
