# ADR 0007: Every feature works with any single AI tool

- **Status:** Accepted
- **Date:** 2026-10-18

## Context

People standardise on one AI tool. Some use ChatGPT and nothing else; some use only GitHub Copilot through
their employer; some use Claude, Gemini or Cursor. They will not sign in to a second tool or buy an API key just
to use this project. Earlier designs leaned on Claude Code or on API keys for evaluation, which quietly made one
feature depend on a particular vendor.

## Decision

No feature may require a specific AI tool or more than one. Concretely:

| Feature | How it reaches every tool |
|---|---|
| Governance method (rules, gates, playbooks, templates) | The open Agent Skills package; the prompt pack for tools without skills; the MCP server |
| Policy as code | A plain JSON file read by the skill, the scripts, the CLI and the MCP server |
| Calculators | Python scripts (any tool that runs code or a terminal), MCP tools, the `aipg` CLI, and documented formulas when nothing can execute |
| Evals, automatic | `aipg eval` detects the one AI access the user already has (Claude Code, Codex, Gemini CLI, Copilot CLI or Cursor sign-in; an API key; or a local model) and uses it both to answer and to grade |
| Evals, manual | `aipg eval-kit` turns the suite into copy-and-paste steps for any chat tool, then scores offline |

Agent CLIs are described by declarative profiles (`evals/agent_cli.py`), so supporting another tool means adding
data rather than a new provider.

## Consequences

- A ChatGPT-only, Copilot-only or Gemini-only user gets every feature, including evals.
- By default the tool that answers also grades. This introduces self-preference bias, but both arms share the same
  grader, so the difference between them, which is what the evals measure, stays comparable. Teams that want an
  independent grader set `judge.use` to another model.
- Profiles for tools that have not been run end to end are labelled unverified until someone runs them. Tests
  against a fake CLI cover argument handling and parsing, but not each vendor's real behaviour.
- The manual kit is slow (one chat per answer and per grading), so it defaults to one trial; it is the universal
  fallback, not the fast path.
- A cross-tool scorecard (`aipg eval --all`) remains available for maintainers who do have several tools, but
  nothing depends on it.
