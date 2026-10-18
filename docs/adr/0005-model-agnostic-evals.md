# ADR 0005: A model-agnostic eval harness with a provider-neutral skill host

- **Status:** Accepted
- **Date:** 2026-10-18

## Context

The skill claims to improve governance advice on any model. Tool-specific eval frameworks test one runtime, and
the skill's value has to be shown across vendors and caught when a model update changes behaviour.

## Decision

Build `aipg eval`:

- Providers behind one interface: the official Anthropic SDK, and the official OpenAI SDK, which also reaches
  OpenAI-compatible endpoints such as Gemini, Azure OpenAI and local servers.
- A provider-neutral skill host: SKILL.md in the system prompt plus `read_skill_file` and `run_skill_script`
  tools, sandboxed to the skill directory and two allow-listed scripts.
- Two arms per scenario (with the skill, and an expert-persona baseline without it), several trials each.
- A blind rubric judge with binary criteria and quoted evidence, plus deterministic regex checks; critical
  criteria fail a trial outright.
- Quality gates and regression comparison against a committed baseline, with JSON, Markdown and JUnit reports and
  a reproducibility manifest.

### Addendum: subscription-based runs through Claude Code

Many users have a Claude subscription but no API key. A `claude-code` provider runs subjects and the judge through
Claude Code's headless mode with the user's login. It acts as a native skill host (the skill is installed at
`.claude/skills/` in a throwaway workspace), so it also measures whether the model chooses to activate the skill.
Bare mode cannot use a subscription login, so isolation comes from an empty workspace, project-only setting
sources, no session persistence, deny-by-default permissions and a scrubbed environment.

## Consequences

- The same scenarios compare models and quantify the skill's uplift on each.
- Evals cost money, so they run on a schedule, on demand, or by pull-request label, with a cost ceiling; unit tests
  use fake providers and cost nothing.
- Activation (whether a tool chooses to load the skill) is not measured here and is tested per tool.
- Judge bias is mitigated, not eliminated; see docs/evaluation.md.

## Alternatives considered

- **Only tool-native evals (for example `claude plugin eval`):** they test real triggering but only in one tool.
  They remain a useful complement.
- **Human review only:** the gold standard for calibration, but too slow to run on every change.
