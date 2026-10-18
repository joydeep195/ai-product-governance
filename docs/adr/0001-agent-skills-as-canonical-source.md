# ADR 0001: The Agent Skills package is the single source of truth

- **Status:** Accepted
- **Date:** 2026-10-18

## Context

The method must work in many AI tools: ChatGPT, GitHub Copilot, Claude, Cursor, Gemini, Codex and custom apps.
Maintaining a separate prompt per tool would let the copies drift apart, and every drift is a governance
inconsistency: two teams getting different answers to the same question.

The open Agent Skills specification (agentskills.io) is now implemented by about 40 tools, including Claude, ChatGPT
(plans with Skills), OpenAI Codex, GitHub Copilot, Cursor and Gemini CLI. Most of them read skills from a shared
`.agents/skills/` location.

## Decision

`skills/ai-product-governance/` is written to the Agent Skills specification and is the only place governance
content is authored. Every other artifact (the prompt pack, Copilot prompt files, the `AGENTS.md` section, MCP
prompts and resources, eval prompts) is derived from it by code.

## Consequences

- Tools that implement the standard need no adapter at all.
- Content changes happen once, and CI proves the derived artifacts follow them (see ADR 0006).
- The skill must respect the specification's constraints (name format, a description of at most 1,024 characters,
  a short SKILL.md with depth in one-level-deep references). `aipg validate` enforces them.
- Tool-specific frontmatter extensions are avoided so the package stays portable.

## Alternatives considered

- **A prompt per tool:** simple at first, but it drifts and cannot be validated as a whole.
- **An MCP server only:** universal, but needs a running process and is not how most users install skills.
  It is kept as a complementary channel (ADR 0004).
