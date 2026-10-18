# Approach and model selection

**Goal:** choose the simplest approach and the right model on evidence, and record why.
**Artifact:** model decision record (`assets/templates/model-decision-record.md`).

## 1. Climb the approach ladder only when you must

Start on the lowest rung. Move up only when evals show the current rung cannot meet the quality bar, because every rung adds cost, latency and operational surface.

1. **Prompted model:** clear instructions, a few examples, the input. Start here.
2. **Structured outputs and tools:** schema-constrained output; deterministic tools for lookups, arithmetic and actions.
3. **Retrieval (RAG):** when answers depend on private, large or fast-changing knowledge. Adds a new failure mode: the wrong or stale document.
4. **Fixed multi-step workflow:** a predictable chain of calls, such as extract → validate → draft.
5. **Agent:** the model decides the steps and tool calls. Use only when the path cannot be specified in advance and errors are recoverable.
6. **Fine-tuning or a custom model:** for consistent style or format at very high volume, tight latency or cost constraints, or behaviour prompting cannot reach. It brings training-data governance and must be re-validated whenever the base model changes. Fine-tuning is a poor way to keep a model up to date with knowledge that changes; use retrieval for that.

## 2. Choose the model on your own evidence

Decide with your golden set, not public leaderboards.

| Criterion | Question |
|---|---|
| Quality | Pass rate on our golden set, especially the critical criteria |
| Cost | Cost per completed task from the Gate 1 model, not price per token |
| Latency | p95 at the expected concurrency |
| Context and modality | Handles our input types and lengths |
| Data terms | Retention, use of our data for training, data residency, zero-retention options |
| Deployment route | Vendor API directly, or through our cloud provider (procurement, residency, private networking) |
| Reliability | SLA, rate limits, regional availability, deprecation policy |
| Portability | Effort to switch: provider-specific features used, how well prompts transfer |

## 3. Proven patterns

- **Tiering or routing:** a capable model for hard or high-stakes cases and a cheaper one for routine cases. Measure the whole cascade, including routing mistakes, against the single strongest model at lower effort. The simpler option often wins.
- **Provider-neutral layer:** keep prompts, tool definitions and evals portable so a switch is a configuration change plus an eval run. Still test each model on its own terms, because prompts rarely transfer unchanged.
- **Version pinning:** pin exact model versions in production. Treat any model upgrade as a release: run the eval suite, shadow test, then roll out in stages.

## 4. Build or buy

First check whether a product the organisation already uses (CRM, help desk, IDE, office suite) offers the capability with acceptable controls. Build when the workflow differentiates the business, the data is proprietary, or vendor controls fail the policy.

## Exit criteria

- [ ] Candidate models evaluated on the same golden set version.
- [ ] Decision record with the rationale, the rejected options, and a re-evaluation trigger (for example a new model release, a cost change above 20%, or a quality regression).
