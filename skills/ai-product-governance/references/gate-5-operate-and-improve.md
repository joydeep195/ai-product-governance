# Gate 5 — Operate and improve

**Goal:** keep the feature good, safe and affordable after launch, and know quickly when it isn't.
**Exit artifacts:** monitoring plan; incident or regression review (`assets/templates/incident-review.md`).

## 1. Monitoring plan

| Area | Signals | Typical alert |
|---|---|---|
| Quality | Sampled human review scores; acceptance; edit distance; override and undo rates; escalations | Drop against the four-week baseline beyond tolerance |
| Safety | Flagged outputs; incident reports; policy-violation detections | Any critical event pages the on-call owner |
| Cost | Cost per completed task; tokens per task; spend against budget | 20% above baseline |
| Latency and reliability | p50 and p95 latency; timeouts; error rates; fallback activation rate | p95 above budget |
| Usage | Active users; tasks; repeat usage | Sudden drop |
| Drift | Input mix (languages, topics, lengths, new segments); changes to the retrieval corpus | Distribution shift |
| Vendor | Model version, deprecation notices, changes to terms | Any change |

The policy sets the weekly human-review sample size for each tier.

## 2. Regression diagnosis protocol

When a quality metric drops, work through these steps **in order**. Most reports that "the model got worse" turn out to be something else, and switching models before diagnosing usually hides the real cause.

1. **Measurement.** Did the metric's definition, logging, sampling or dashboard change? Did instrumentation break? If so, re-baseline, then diagnose only the real change that remains.
2. **Change log.** What shipped in the window: prompt, model version or alias, provider routing, retrieval index or corpus, tools, guardrails, UI, configuration? Line up the start of the drop with deployment times.
3. **Input mix.** Did the traffic change: a new customer segment, language, entry point, season or campaign? Compare the metric within stable segments. If every segment is flat but the mix shifted, the cause is the mix, not quality.
4. **Dependencies.** Retrieval failures or stale content, timeouts that truncate context, rate limiting, the fallback path activating, upstream data quality.
5. **Model behaviour.** Replay a fixed sample of recent inputs through the current system and through the last-known-good configuration (pinned model, prompt and index). Compare the outputs and run the golden set on both.

Then quantify how much of the drop each cause explains, fix the cause, and add the failing cases to the eval set so the regression cannot return unnoticed.

## 3. AI incident management

Severities in the default policy:

- **SEV1:** harmful, unlawful or data-exposing output reached users, or an unauthorised action executed. Contain immediately with the kill switch or the fallback path, and notify the privacy, legal and security owners named in the runbook.
- **SEV2:** a systematic quality failure affecting many users, with no confirmed harm.
- **SEV3:** an isolated failure or a near miss.

Response sequence: **contain → scope** (who, how many, since when; use the audit log) **→ notify → fix → verify with evals → blameless review → add the cases to the eval set.**

## 4. Re-certification

Repeat the gate review on the policy's cadence (default: every 3 months for high tier, 6 for limited, 12 for minimal) and after any material change: a new model or provider, a new use or user group, a new data source, an autonomy promotion, or a SEV1 incident.

## 5. Retirement

Retire or roll back when the value no longer covers the cost and risk, quality cannot be held at the threshold, the vendor deprecates the model with no validated replacement, or a policy change raises the tier beyond what the controls support. Plan data deletion and user communications.

## Exit criteria (ongoing)

- [ ] Monitoring live, with an owner for every alert.
- [ ] Regression protocol and incident runbook documented and rehearsed.
- [ ] Next re-certification date set.
