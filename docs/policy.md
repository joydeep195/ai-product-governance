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
| `controls` | The control catalogue with the evidence each control requires and, optionally, the framework requirements it maps to |
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

| Policy | Frameworks mapped |
|---|---|
| Default | EU AI Act (Regulation (EU) 2024/1689), NIST AI RMF 1.0 subcategories, ISO/IEC 42001:2023 Annex A controls (and clause 8.2), GDPR for the privacy controls, OWASP Top 10 for LLM Applications 2025 for the security controls |
| Financial services | All of the above, plus the US agencies' model risk guidance SR 26-2 (OCC Bulletin 2026-13), DORA (Regulation (EU) 2022/2554), ECOA and Regulation B (12 CFR 1002), FCRA, SEC Rule 17a-4, FINRA rules, MiFID II, the FCA Consumer Duty (PRIN 2A) and DISP, and the 2023 US interagency third-party guidance |

SR 26-2 replaced SR 11-7 in April 2026 and places generative and agentic AI models outside its formal scope,
expecting a bank's own risk management and governance practices to cover them; the policy cites it for the
model-risk disciplines (inventory, validation, monitoring, vendor models) that `MRM-01` and related controls apply.

References cite an article, clause, rule or subcategory number only where it could be cited with confidence, and
name the section otherwise (the interagency guidance's "Third-party relationship life cycle"). Tests check every
NIST AI RMF reference against the 72 subcategories, every ISO/IEC 42001 reference against the 38 Annex A controls
or a main clause, and every EU AI Act article against the Act's 113 articles.

**The mappings are informative, not legal advice.** They say which requirement a control is designed to address,
not that the requirement applies to a use case, nor that the control alone satisfies it. Applicability depends on
your role (for example provider or deployer under the EU AI Act), jurisdiction, products and dates of application.
Have legal and compliance teams review and own the crosswalk in your organisation's policy, and add your own
frameworks (an internal control library, SOC 2, a sector regulator) in the same shape.

## Distributing a policy

- **Per repository:** commit `.ai-governance/policy.json`; skill-native tools and the bundled scripts pick it up.
- **Organisation-wide:** run the MCP server with `AIPG_POLICY` pointing at the approved policy. The policy is fixed
  when the server starts and no tool can change it, so every connected assistant applies the same rules.

The default policy is a reference informed by the EU AI Act risk categories and the NIST AI RMF. It is not legal
advice; have legal and compliance teams own your organisation's version.
