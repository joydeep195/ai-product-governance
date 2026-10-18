# Gate 2 — Quality bar and evaluation

**Goal:** agree, before building, what "good enough to launch" means and how it will be measured.
**Exit artifact:** eval plan (`assets/templates/eval-plan.md`).

## 1. Write the task contract

- **Input:** what the model receives, and what it must ignore.
- **Output:** format, length and required elements.
- **Correct means:** a definition for each quality dimension, with two or three worked examples (good, borderline, bad).
- **Must never:** zero-tolerance behaviours, called *critical criteria*. Examples: invents a policy or a price, exposes another customer's data, gives a medication dose, takes an action without approval.

## 2. Pick quality dimensions and thresholds

| Dimension | Typical measure |
|---|---|
| Correctness / faithfulness | % of outputs factually correct, or fully supported by the sources |
| Completeness | % of required elements present (for example every action item captured) |
| Format validity | % of outputs that pass schema validation |
| Instruction and policy compliance | % compliant with tone, scope and content policy |
| Safety | Count of critical failures (target: zero) |
| Retrieval quality (RAG) | Relevant document in the top results; citation accuracy |
| Action correctness (agents) | % correct actions; count of unsafe actions attempted |
| Robustness | Pass rate on the adversarial and edge-case slice |
| Fairness | Largest pass-rate gap across user segments, languages or dialects |
| Latency and cost | p95 latency; cost per completed task (see Gate 1) |

## 3. Build the golden set

- **Sources:** permitted, anonymised real samples first; expert-written cases to fill gaps; synthetic cases for rare edge cases, labelled as synthetic.
- **Coverage matrix:** user segment × difficulty × known edge cases × adversarial inputs. Put several cases in every cell that matters.
- **Size:** at least the policy minimum for the risk tier. The default policy requires 50 (minimal), 150 (limited) and 300 (high).
- **Labels:** domain experts write the expected outcome or grading notes. Have two experts label at least 20% of cases. If experts disagree, the rubric is unclear; fix it before blaming the model.
- **Splits:** keep a held-out test split that is never used while tuning prompts. Launch decisions use the held-out split only.
- **Versioning:** version the eval set like code and record the version behind every reported result.

## 4. Choose grading methods (cheapest reliable method first)

1. **Programmatic checks:** schema validation, regular expressions, exact match, unit tests, assertions on tool calls.
2. **Reference comparison:** label accuracy for classification, field-level match for extraction.
3. **Rubric grading by a model ("LLM-as-judge"):** binary pass/fail per criterion, with quoted evidence. Calibrate it against human labels on at least 50 cases before trusting it; 85% agreement or better is a common bar. Judges tend to favour longer answers, the first option shown, and outputs from their own model family. Counter this with binary criteria, evidence quotes, randomised order, and a judge from a different model family where possible.
4. **Human review panels:** needed for criteria that require expertise, and on a sample for high-tier launches.

## 5. Set thresholds and the baseline

- Set a pass threshold for each dimension and list the critical criteria. **A single critical failure blocks launch, whatever the averages say.**
- Measure today's process (the human team or the existing system) on the same cases. The AI path must match or beat it on the agreed dimensions, or the trade-off must be explicit and approved, for example "3 points less accurate but ten times faster, with human review".

## 6. Be honest about uncertainty

Small eval sets have wide error bars. The approximate 95% margin of error for a pass rate *p* measured on *n* cases is ±1.96 × √(p(1 − p) / n):

| Cases (n) | Pass rate 90% | Pass rate 95% |
|---|---|---|
| 50 | ±8.3 points | ±6.0 points |
| 150 | ±4.8 points | ±3.5 points |
| 300 | ±3.4 points | ±2.5 points |

Generative models are non-deterministic: run each case at least three times and report the mean and spread. Do not call a two-point difference on 50 cases an improvement.

## 7. Plan production (online) measures now

Instrumentation must ship with version 1, so specify it here:

- Acceptance rate (suggestions or drafts used), edit distance (how much users change drafts), override and undo rate, escalation-to-human rate, task completion, explicit feedback, complaint and incident rate, cost per completed task, latency.
- Guardrail metrics with alert thresholds, and the weekly human-review sample size required by the policy for the tier.

## 8. Make evaluation continuous

Run the suite automatically on every change to prompts, models, retrieval or tools, and block releases that fall below threshold. Add every production incident and notable failure to the eval set as a new case.

## Exit criteria

- [ ] Task contract, quality dimensions, thresholds and critical criteria agreed.
- [ ] Golden set plan meets the tier minimum, with a coverage matrix, a labelling plan and a held-out split.
- [ ] Grading method chosen for each dimension, with a calibration plan for any model judge.
- [ ] Baseline measurement planned on the same cases.
- [ ] Online metrics, alert thresholds and the instrumentation plan defined.
