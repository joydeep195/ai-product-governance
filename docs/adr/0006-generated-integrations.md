# ADR 0006: Integrations are generated, committed and drift-checked

- **Status:** Accepted
- **Date:** 2026-10-18

## Context

Users of tools without native skill support (ChatGPT plans without Skills, Gemini Gems, Microsoft 365 Copilot
agents, generic APIs) need ready-to-paste artifacts in the formats those tools accept: instruction limits of about
8,000 characters, flat knowledge-file uploads, Copilot prompt-file frontmatter, MCP client configs. Hand-maintained
copies would drift from the skill.

## Decision

`aipg build` renders everything under `integrations/` from the skill, deterministically and with LF line endings.
The output is committed so users can browse and copy it from GitHub. `aipg build --check` runs in CI and fails on
missing, changed or stale files. Size budgets (the instruction limit, at most 20 flat knowledge files) are asserted
in tests.

## Consequences

- One edit to the skill updates every integration in the same pull request, and reviewers see both.
- Contributors must run `aipg build` after content changes; CI tells them when they forget.
- The prompt pack reuses SKILL.md sections through `<!-- aipg:begin/end -->` markers, so the markers are part of the
  content contract and are tested.

## Alternatives considered

- **Generate only at release time:** keeps the repository smaller, but users browsing GitHub could not see or copy
  the integrations, and drift would only be found at release.
