---
name: ai-model-decision
description: "Choose the approach (prompting, RAG, agent, fine-tuning) and model on evidence, and record the decision."
argument-hint: "Describe the task, data, volume, latency and constraints"
agent: agent
---

Use the **ai-product-governance** Agent Skill (in `.github/skills/` or `.agents/skills/`). Read its `SKILL.md` first and follow its operating rules.

Recommend the approach and model for this situation and produce a model decision record:

${input:context:Describe the task, data, volume, latency and constraints}

1. Read only these playbooks from the skill: `references/approach-and-model-selection.md`, `references/gate-1-value-and-economics.md`.
2. Use the template `assets/templates/model-decision-record.md` and keep every section.
3. Run the skill's `scripts/risk_tier.py` and `scripts/unit_economics.py` for risk tiers and costs; never estimate them by hand.
4. If `.ai-governance/policy.json` exists in this repository, it overrides the default policy.
5. Save the result as `docs/ai-governance/<feature>-model-decision-record.md` unless asked otherwise.
