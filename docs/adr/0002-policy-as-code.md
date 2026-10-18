# ADR 0002: Governance policy as validated data

- **Status:** Accepted
- **Date:** 2026-10-18

## Context

Risk tiers, required controls, approvers and launch thresholds differ between organisations: a bank, a retailer
and a hospital will not accept the same rules. If the rules lived in prose, every organisation would have to fork
and re-word the skill, and models would apply the rules inconsistently.

## Decision

Rules live in a JSON policy file with a published JSON Schema: tiers, a questionnaire, classification rules with
composable conditions, conditional controls, a control catalogue with required evidence, approvers, eval minimums,
autonomy caps and incident severities. A workspace file (`.ai-governance/policy.json`) or a server setting overrides
the bundled default. Every result names the policy ID and version it applied.

## Consequences

- Organisations customise by editing data, reviewed through their normal pull-request process, without touching
  prompts or code.
- Policies are checked by schema and by referential validation (unknown tiers, controls, questions or operator
  misuse), and `aipg validate` warns when a higher tier is weaker than a lower one.
- Classification is deterministic and auditable: the same answers and policy always produce the same tier.
- The condition language is deliberately small (`equals`, `in`, `contains_any`, `gte`, `lte`, `all`, `any`).
  Richer logic would need a new schema version.

## Alternatives considered

- **Rules in SKILL.md prose:** not enforceable, not auditable, and inconsistent across models.
- **A general policy engine (for example OPA/Rego):** powerful but adds a runtime dependency that code-interpreter
  sandboxes and many agents do not have. Plain JSON runs everywhere Python does.
