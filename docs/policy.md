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
| `questions` | The questionnaire (boolean, number, enum, multiselect); `split_from` marks a question split out of an older one |
| `rules` | Conditions that raise the tier; the highest triggered tier wins |
| `conditional_controls` | Controls added by specific answers regardless of tier (for example permission-aware retrieval when RAG is used) |
| `controls` | The control catalogue with the evidence each control requires and, optionally, the framework requirements it maps to and an `applies_when` condition that rules the control out |
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
so a partially completed questionnaire never under-classifies silently. It also leads with that fact: the result
carries `"status": "incomplete"` and a headline such as `Incomplete (provisional Minimal; could rise to Prohibited)`
instead of a bare tier, and the skill tells the agent to ask the missing questions, or log them in the Assumptions
Ledger, before it presents any tier. The calculator still exits 0, so an agent reads the explanation instead of
falling back to classifying by hand; add `--strict` (to `risk_tier.py` or `aipg tier`) to exit 4 in CI instead.

## Splitting a question: `split_from`

A question that does two jobs over-classifies. The default policy's `regulated_advice` used to cover both regulated
advice and running inside a regulated process, so almost every banking or fintech use came out high risk. Since
policy 2.0.0 it asks only about regulated advice (rule `H-03`, high), and `inside_regulated_process` (rule `L-07`,
limited) covers KYC checks, AML or fraud monitoring, complaints or dispute handling, claims handling and regulatory
reporting. Whether such work is high risk is then decided by the rules that measure harm: decisions about people,
sensitive data, financial impact and autonomy.

The new question carries `"split_from": "regulated_advice"`. Answer files written before the split keep working:
the key is unchanged, so an old `true` still produces the high tier until a person re-checks it, and an answer set
without the new question is reported as incomplete with a note that explains the split and asks for both answers.
Use `split_from` the same way when you split a question in your own policy.

## Ruling controls out: `applies_when`

Tiers and conditional controls can only add controls. A control whose purpose depends on the facts, such as
fairness evaluation, which needs people whose results could differ, can carry an `applies_when` condition and a
`not_applicable_reason`:

```json
{ "id": "TRN-02", "name": "Explanation and contestability", "...": "...",
  "applies_when": { "any": [
    { "question": "outputs_concern_people", "equals": true },
    { "question": "consequential_decisions", "equals": true }
  ] },
  "not_applicable_reason": "No person is the subject of the output and it influences no decisions about people, so nobody is affected by an outcome they could ask to have explained or reviewed." }
```

Whenever a tier or a conditional requires the control and the answers make the condition false, the result lists it
under `not_applicable_controls` (and a "Not applicable" table in Markdown) with the reason, instead of requiring it.
An unanswered question keeps the control required. `aipg record new` and `aipg check` require only the applicable
controls. The default policy uses this for `EVAL-03` (fairness evaluation) and `TRN-02` (explanation and
contestability), based on the `outputs_concern_people` question: an internal AI that drafts an infrastructure
report can be high risk because a wrong report is costly, yet have nobody to evaluate for fairness or to explain an
outcome to. To make a control unconditional again, delete its `applies_when` and `not_applicable_reason`.

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
aipg validate          # also checks every policy under examples/ and warns about weak or redundant structure
```

`aipg validate` warns when a higher tier drops a control that a lower tier requires, and when a conditional control
can never add anything. A conditional is redundant when its condition already triggers a rule whose tier, and every
tier above it, requires the control: for example, privacy review conditional on personal data, when personal data
already makes the use case limited risk and the limited tier requires privacy review. Remove the conditional, or
take the control out of the tier if it should depend on the condition. The check reports only what it can prove from
the conditions, so it never warns falsely, but it can miss a redundancy.

## Regulatory crosswalk

Each control can list the external requirements it addresses, so an auditor can trace a control to the regulation
they are asking about:

```json
{ "id": "EVAL-03", "name": "Fairness evaluation", "...": "...",
  "mappings": [
    { "framework": "EU AI Act", "reference": "Art. 10", "note": "Data governance, including examination for possible biases" },
    { "framework": "NIST AI RMF 1.0", "reference": "MEASURE 2.11", "note": "Fairness and bias evaluated and documented" },
    { "framework": "ISO/IEC 42001:2023", "reference": "A.5.4", "note": "Assessing impact on individuals or groups of individuals" }
  ] }
```

`risk_tier.py` copies the mappings onto every required control in its JSON output and adds a "Maps to" column to
the Markdown table. `framework` and `reference` are required; `note` is optional.

### Sources and "last verified" dates

The skill runs inside the user's own AI tool and never looks anything up, and a model can fill a gap from its
training data with a fact that has since changed. So every framework a policy cites is listed once in a
`frameworks` array with its official source and the date someone last confirmed that source was current:

```json
"frameworks": [
  { "id": "EU AI Act", "title": "Regulation (EU) 2024/1689 (Artificial Intelligence Act)",
    "url": "https://eur-lex.europa.eu/eli/reg/2024/1689/oj", "last_verified": "2026-11-10",
    "note": "In force. Amended by Regulation (EU) 2026/1744 (Digital Omnibus on AI), published 24 July 2026, ..." }
]
```

`id` must equal the `framework` value used in mappings; when the list is present, a mapping to an unlisted framework
is an error, and `aipg validate` warns about a policy that has mappings but no list. `risk_tier.py` returns the
sources behind the required controls (`sources` in JSON, a Sources list in Markdown), and the skill tells the agent
to state regulatory facts "as of" those dates and never to present its own memory of a law as current. The Gate 3
playbook's regulatory flags carry the same links and dates.

`last_verified` means the source was opened and checked as current (not superseded, withdrawn or replaced) on that
date; it does not re-certify every mapping. Re-check the sources at least yearly, and whenever a regulator
announces a change, then update the dates.

| Policy | Frameworks mapped |
|---|---|
| Default | EU AI Act (Regulation (EU) 2024/1689), NIST AI RMF 1.0 subcategories, ISO/IEC 42001:2023 Annex A controls (and clause 8.2), GDPR for the privacy controls, OWASP Top 10 for LLM Applications 2025 for the security controls |
| Financial services | All of the above, plus the US agencies' model risk guidance SR 26-2 (OCC Bulletin 2026-13), DORA (Regulation (EU) 2022/2554), ECOA and Regulation B (12 CFR 1002), FCRA, SEC Rule 17a-4, FINRA rules, MiFID II, the FCA Consumer Duty (PRIN 2A) and DISP, and the 2023 US interagency third-party guidance |

SR 26-2 (with OCC Bulletin 2026-13, both 17 April 2026) replaced SR 11-7 and OCC Bulletin 2011-12. Footnote 3 of
the guidance places generative and agentic AI models outside its scope and says a bank's own risk management and
governance practices should guide the controls for them; the policy cites it for the model-risk disciplines
(inventory, validation, monitoring, vendor models) that `MRM-01` and related controls apply. Source:
[SR 26-2](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm), last verified 10 November 2026.

References cite an article, clause, rule or subcategory number only where it could be cited with confidence, and
name the section otherwise (the interagency guidance's "Third-party relationship life cycle"). Tests check every
NIST AI RMF reference against the 72 subcategories, every ISO/IEC 42001 reference against the 38 Annex A controls
or a main clause, and every EU AI Act article against the Act's 113 articles.

**The mappings are informative, not legal advice.** They say which requirement a control is designed to address,
not that the requirement applies to a use case, nor that the control alone satisfies it. Applicability depends on
your role (for example provider or deployer under the EU AI Act), jurisdiction, products and dates of application.
Have legal and compliance teams review and own the crosswalk in your organisation's policy, and add your own
frameworks (an internal control library, SOC 2, a sector regulator) in the same shape.

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
