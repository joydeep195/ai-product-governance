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
- requires 500 golden-set cases for high-risk launches.

Validate before you publish:

```bash
python skills/ai-product-governance/scripts/risk_tier.py --validate-policy --policy path/to/policy.json
aipg validate          # also checks every policy under examples/ and warns if a higher tier is weaker than a lower one
```

## Distributing a policy

- **Per repository:** commit `.ai-governance/policy.json`; skill-native tools and the bundled scripts pick it up.
- **Organisation-wide:** run the MCP server with `AIPG_POLICY` pointing at the approved policy. The policy is fixed
  when the server starts and no tool can change it, so every connected assistant applies the same rules.

The default policy is a reference informed by the EU AI Act risk categories and the NIST AI RMF. It is not legal
advice; have legal and compliance teams own your organisation's version.
