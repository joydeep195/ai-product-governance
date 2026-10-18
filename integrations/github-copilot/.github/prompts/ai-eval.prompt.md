---
name: ai-eval
description: "Run the skill's eval suite inside this AI tool with fresh sub-agents, using its own session: no API key or extra sign-in."
argument-hint: "Optional: scenario ids to run, or a number of trials"
agent: agent
---

Use the **ai-product-governance** Agent Skill (in `.github/skills/` or `.agents/skills/`). Read `references/evaluate-this-skill.md` from it and follow that procedure exactly: it runs the skill's eval suite here, giving every prompt to a fresh sub-agent, and needs a checkout of the ai-product-governance repository.

Options from the user: ${input:options:Optional: scenario ids to run, or a number of trials}
