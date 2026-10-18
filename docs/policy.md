# Governance policy guide

The policy is the part of the method an organisation owns. It turns "it depends" into rules everyone applies the
same way, in every AI tool, and it is versioned, reviewed and validated like code.

## Where the policy comes from

The engines and the MCP server resolve the policy in this order:

1. An explicit path (`--policy` on the CLI or server)
2. The `AIPG_POLICY` environment variable
3. `.ai-governance/policy.json` in the current workspace
4. The bundled default, `skills/ai-product-governance/assets/policy/default-policy.json`

Every result names the policy ID, version and source, so artifacts are traceable to the rules that produced them.

## Structure

| Section | Purpose |
|---|---|
| `tiers` | Ranked risk tiers with required controls, approvers, the maximum autonomy at launch, re-certification cadence and eval minimums. A tier with `"prohibited": true` stops the work |
| `questions` | The questionnaire (boolean, number, enum, multiselect) |
| `rules` | Conditions that raise the tier; the highest triggered tier wins |
| `conditional_controls` | Controls added by specific answers regardless of tier (for example permission-aware retrieval when RAG is used) |
| `controls` | The control catalogue with the evidence each control requires |
| `autonomy_levels`, `autonomy_promotion` | The L0-L5 ladder and the evidence needed to move up |
| `incident_severities` | SEV definitions used by Gate 5 |

Conditions support `equals`, `in`, `contains_any`, `gte`, `lte`, and nesting with `all` and `any`:

```json
{
  "id": "H-06",
  "tier": "high",
  "when": {
    "all": [
      { "question": "autonomy_level", "in": ["L4", "L5"] },
      { "any": [
        { "question": "customer_facing", "equals": true },
        { "question": "irreversible_actions", "equals": true }
      ] }
    ]
  },
  "reason": "Acts without per-action approval in a way that affects customers or cannot easily be reversed."
}
```

Unanswered questions evaluate to "unknown". The result lists them and the highest tier they could still trigger,
so a partially completed questionnaire never under-classifies silently.

## Customising

Start from the default, then change data, not code. [`examples/financial-services/.ai-governance/policy.json`](../examples/financial-services/.ai-governance/policy.json)
shows a regulated bank that:

- makes every customer-facing AI use case high risk;
- lowers the financial-impact threshold from 1,000 to 250;
- adds an independent model validation control (`MRM-01`) and the model risk approver;
- requires 500 golden-set cases and a compliance officer's sign-off for high-risk launches;
- adds four controls that apply only when the questionnaire answers call for them.

| Control | Applies when | Covers |
|---|---|---|
| `TRN-03` Adverse action reasons | the output influences decisions about people's access to services | specific principal reasons for a decline, reduction or repricing |
| `TPR-01` Third-party dependency and exit plan | the system depends on an external model or AI platform (a question this policy adds) | third-party risk onboarding, contract rights and a tested exit plan |
| `OPS-06` Complaint monitoring | the AI is customer-facing or influences decisions about people | tagging, trending and root-causing complaints that involve the AI |
| `OPS-07` Communications record-keeping | the AI is customer-facing or its content is published externally | books-and-records retention and supervisory review of AI communications |

Validate before you publish:

```bash
python skills/ai-product-governance/scripts/risk_tier.py --validate-policy --policy path/to/policy.json
aipg validate          # also checks every policy under examples/ and warns if a higher tier is weaker than a lower one
```

## Use-case records and `aipg check`

The policy says which controls and approvers a use case needs; a use-case record says whether it has them. Each
record is a JSON file at `.ai-governance/use-cases/<id>.json`, validated by
[`use-case.schema.json`](../skills/ai-product-governance/assets/policy/use-case.schema.json), holding:

- `id`, `title` and the accountable `owner`;
- `policy_id` and `policy_version` it was certified against, and the `tier` the answers produced;
- the `questionnaire`: `answers`, `answered_by` and `answered_on`;
- `controls`: for each, the `id`, a `status` (`open`, `done` or `waived`), an `evidence_url` and an `owner`, plus the
  `approver` and `reason` for a waiver;
- `approvals`: the `role`, `name` and `date` of each sign-off;
- `last_certified` and `recertify_by`.

Create one from questionnaire answers. The command classifies them with the same engine as `aipg tier`, against the
effective policy, and writes every required control as `open`, a blank sign-off for each approver role, and
`recertify_by` set by the tier's `recertification_months`:

```bash
aipg record new --answers refund-agent.answers.json --id refund-agent --owner "Payments product team" --answered-by "Alex Morgan"
```

Then fill it in as the work lands. Mark a control `done` with a link to the evidence the policy names, or `waived`
with the approver and the reason, and record each approver's name and date when they sign.
[`card-dispute-replies.json`](../examples/financial-services/.ai-governance/use-cases/card-dispute-replies.json) is
a complete record for a high-risk use case under the example bank policy, including one waiver.

`aipg check` re-classifies every record's answers against the effective policy and lists everything that stops it
passing:

| Fails when | To fix it |
|---|---|
| The stored `tier` differs from what the answers now produce, or a question is unanswered | Repeat the risk review and update the record |
| A required control is missing, `open`, `done` without an `evidence_url`, or `waived` without an approver and a reason | Finish the control, link the evidence or get the waiver approved |
| An approver role the tier requires has no name and date in `approvals` | Collect the sign-off |
| Today is after `recertify_by`, or `recertify_by` is further from `last_certified` than the tier's cadence | Re-certify, then update `last_certified` and `recertify_by` |
| `policy_id` or `policy_version` differs from the effective policy | Repeat the gate review under the new policy, then update the version and dates |
| The answers fall in a prohibited tier, `owner` or `answered_by` is empty, the `id` does not match the file name, or the file breaks the schema | Stop the work, or correct the record |

```bash
aipg check                                   # every record in .ai-governance/use-cases/
aipg check path/to/workspace other/record.json
aipg check --format md > governance.md       # a summary for a pull-request comment
aipg check --as-of 2027-01-31                # will we still pass on launch day?
```

It exits 0 when every record passes, 1 when any fails and 2 when it finds no records. Each record is checked against
the policy for its own workspace: `--policy`, then `AIPG_POLICY`, then the `.ai-governance/policy.json` beside its
`use-cases` folder, then the bundled default. `aipg validate` also checks every record under `examples/`, but not
against today's date, so the examples do not expire.

### Adding `aipg check` to CI

Run it on every pull request so a change cannot merge while a record is incomplete, and on a schedule so a lapsed
re-certification fails even when nothing changes. For GitHub Actions, save this as
`.github/workflows/ai-governance.yml`:

```yaml
name: AI governance

on:
  pull_request:
  schedule:
    - cron: "0 6 * * 1"  # Mondays: catches re-certifications that lapse between changes

permissions:
  contents: read
  pull-requests: write  # for the comment step only

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.13"
      - name: Install aipg  # pin a release tag or commit so a new version cannot change the gate unannounced
        run: pip install "git+https://github.com/joydeep195/ai-product-governance"
      - name: Check every use-case record against the policy
        run: aipg check --format md > governance-check.md
      - name: Add the result to the job summary
        if: always()
        run: cat governance-check.md >> "$GITHUB_STEP_SUMMARY"
      - name: Comment on the pull request
        if: failure() && github.event_name == 'pull_request'
        env:
          GH_TOKEN: ${{ github.token }}
        run: gh pr comment "${{ github.event.pull_request.number }}" --body-file governance-check.md
```

Make the job a required status check in the branch protection rules so a failing record blocks the merge. Pull
requests from forks get a read-only token, so the comment step fails there; the job summary still shows the result.
To enforce one organisation-wide policy instead of each repository's own, set `AIPG_POLICY` on the check step. In
other CI systems, run `aipg check` and treat a non-zero exit code as a failed build.

## Distributing a policy

- **Per repository:** commit `.ai-governance/policy.json`; skill-native tools and the bundled scripts pick it up.
- **Organisation-wide:** run the MCP server with `AIPG_POLICY` pointing at the approved policy. The policy is fixed
  when the server starts and no tool can change it, so every connected assistant applies the same rules.

The default policy is a reference informed by the EU AI Act risk categories and the NIST AI RMF. It is not legal
advice; have legal and compliance teams own your organisation's version.
