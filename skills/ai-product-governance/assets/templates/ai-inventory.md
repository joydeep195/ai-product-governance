# AI inventory: <product, repository or portfolio>

**Verdict:** <N AI uses found | No AI found> · Policy: <policy ID and version> · Date: <YYYY-MM-DD> · Prepared by: <role>

## Scope searched

| Item | Value |
|---|---|
| Paths and repositories | <what was searched> |
| Method | <`scripts/ai_inventory.py` scan, and/or a manual search with the AI tool's own file and search tools> |
| Files scanned | <count, and whether the scan stopped early> |
| Evidence checked | Dependency manifests · SDK imports · model endpoints · API-key variable names · prompts · model files · AI inside third-party products (asked) |

## Product AI uses

| # | AI use | What it does | Users and people affected | Model or provider | Data it touches | Evidence (file:line) | Owner (role) | Status | Next gate |
|---|---|---|---|---|---|---|---|---|---|
| 1 | | | | | | | | <idea / pilot / production> | <G0–G5> |

## Development and test use (not product AI)

Coding assistants, eval harnesses and test fixtures that call models. They do not go through the gates unless the product ships them to users.

| Tool or harness | Evidence | Note |
|---|---|---|
| | | |

## Evidence not yet tied to a use

| Evidence | Why it is unresolved | How it will be resolved | Owner (role) |
|---|---|---|---|
| | | | |

## Not covered

| Gap | How it will be checked | Owner (role) | By |
|---|---|---|---|
| AI inside third-party products | <questions asked of the user, and their answers> | | |
| | | | |

## No AI found

Complete this section only when the verdict is "No AI found"; otherwise write `N/A — <N> AI uses found`.

- **What was searched:** <paths, file counts, every evidence type above>
- **What was not covered, and how it was checked:** <or why it could not be>
- **What would change this answer:** <for example adding an AI SDK, or switching on an AI feature in a third-party product; the work would then start at Gate 0>

No risk tier, controls or gate review apply while no AI is in use.

## Assumptions Ledger

| Assumption | Why it matters | How to verify | Owner (role) |
|---|---|---|---|
| | | | |

## Open decisions

| Decision | Owner (role) | Needed by |
|---|---|---|
| | | |

## Next gate

<For each AI use: the gate it goes to next and why. For "No AI found": none.>
