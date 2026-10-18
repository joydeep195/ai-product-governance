## What and why

<!-- What does this change, and what problem does it solve? -->

## Type of change

- [ ] Governance content (SKILL.md, playbooks, templates)
- [ ] Policy (tiers, rules, controls, approvers, eval minimums)
- [ ] Engines (risk tier, unit economics)
- [ ] MCP server, CLI or integrations
- [ ] Evals (scenarios, harness)
- [ ] Docs or CI

## Checklist

- [ ] `aipg validate --strict` passes
- [ ] `aipg build` run and generated `integrations/` committed (`aipg build --check` passes)
- [ ] `python -m pytest` passes; new behaviour has tests
- [ ] Policy changes keep higher tiers at least as strict as lower ones, and existing example policies still validate
- [ ] Governance content changes: an eval scenario covers the new or changed behaviour
- [ ] `CHANGELOG.md` updated; version bumped in all four places if releasing
