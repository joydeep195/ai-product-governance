# Roadmap

Planned work that v1.1.0 does not include. Nothing here is built yet. Each item keeps the project's design
constraints: the skill runs inside the user's own AI tool, makes no AI API calls, needs no second model, and states
regulatory facts only from sources with a last-verified date ([ADR 0007](adr/0007-one-tool-is-enough.md)).

## Supply-chain and model-provenance risks

Today's risk register and controls centre on the AI feature itself. Add risks and controls for what it is built
from:

- **OWASP Top 10 for LLM Applications 2025** items the default policy does not yet map: LLM03 Supply Chain, LLM04
  Data and Model Poisoning, LLM07 System Prompt Leakage, LLM09 Misinformation and LLM10 Unbounded Consumption.
- **Third-party and open-weight models:** provenance, licence terms, model cards, known evaluations, and how a
  downloaded model or fine-tune is checked before use.
- **MCP servers, plugins and agent tools:** who publishes them, what they can reach, how versions are pinned and
  reviewed, and how a compromised tool is detected and removed. The AI inventory already lists MCP SDKs, which gives
  this work its starting evidence.

## India mappings

The policy maps no Indian law, so the skill flags and routes questions about it (the
`g3-india-lending-flag-not-rule` scenario tests this). An India crosswalk would cover the Digital Personal Data
Protection Act, 2023 and its rules, and RBI guidance relevant to AI in regulated entities. Each entry needs an
official source and a last-verified date in the policy's `frameworks` list before it is added; nothing should be
written from memory.

## Reviewer-effectiveness checks

Several controls rely on human review (`HUM-01`, `HUM-02`, `HUM-03`), but nothing checks that reviewers catch
errors. Add guidance and an eval-plan section for seeding known errors into the review queue, measuring the catch
rate, and acting when it falls (automation bias). This would also give autonomy promotion better evidence than the
override rate alone.

## Agent identity and memory controls

For agents that act with their own credentials or keep memory across sessions:

- **Identity:** a distinct, least-privilege identity per agent, short-lived credentials, and attribution of every
  action to the agent and to the person or process it acted for.
- **Memory:** what an agent may remember, for how long and for whom; isolation between users and tenants; and
  defences against memory poisoning through stored content.

## Open questions found while building v1.1.0

- **Privacy controls with no personal data.** The default limited tier always requires a privacy review (`PRV-01`)
  and a review of vendor data terms (`PRV-03`), even for a use case with no personal data and a model in the
  organisation's own tenancy, such as the `g3-regulated-low-impact` scenario. `applies_when` could rule them out in
  those cases, but some organisations want a privacy screening for every AI use. This is a policy decision for the
  owner, not a code change.
- **Refresh the eval baseline.** The committed baseline predates the four scenarios added in v1.1.0. Run
  `/ai-eval --trials 3` and commit the reviewed result, so the regression gate covers all 14 scenarios.
- **AI inventory coverage.** `scripts/ai_inventory.py` detects SDK imports in Python and JavaScript/TypeScript only,
  and reads manifests but not lockfiles. Extending it to more languages and to transitive dependencies would shrink
  its `not_covered` list.
