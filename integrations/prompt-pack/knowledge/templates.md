# Artifact templates

Each section below is one template. Copy it and fill it in.

<!-- template: ai-prd -->

# AI PRD: <feature name>

| Field | Value |
|---|---|
| Owner (role) | |
| Status | Draft · In review · Approved |
| Risk tier | minimal · limited · high (from the risk tier calculator) |
| Autonomy at launch | L0–L5 |
| Policy | <policy_id> v<version> |
| Gate status | G0 ☐ · G1 ☐ · G2 ☐ · G3 ☐ · G4 ☐ |
| Last updated | YYYY-MM-DD |

**Summary:** one paragraph: the problem, the AI's role, the expected outcome and the current verdict.

## 1. Problem and users (G0)
- **Job to be done and who does it:**
- **Current baseline (time, cost, quality) and its source:**
- **Success metric:** baseline → target, by when

## 2. Why AI (G0)
- **Fit verdict and the deciding dimensions:**
- **What stays deterministic (rules, search, validation):**
- **Interaction pattern and why it is the narrowest that works:**

## 3. Solution
- **User experience walkthrough (happy path):**
- **Autonomy level and the human's role:**
- **Approach (prompted / tools / RAG / workflow / agent) and model; link the model decision record:**

## 4. Task contract (G2)
| Element | Specification |
|---|---|
| Input | |
| Output (format, length, required elements) | |
| Correct means | |
| Must never (critical criteria) | |

## 5. Designing for the wrong answer
| Situation | What the user sees | What the system does |
|---|---|---|
| Output is wrong | | |
| Model is unsure / low confidence | | |
| Model refuses | | |
| Slow (over the latency budget) | | |
| Model or vendor unavailable | | |
| Input outside scope | | |

## 6. Quality bar and evaluation (G2)
- **Golden set:** size (policy minimum), composition, held-out split
- **Thresholds per dimension:**
- **Baseline comparison:**
- **Online metrics and alerts:**
- Link the full eval plan.

## 7. Economics (G1)
- **Cost per completed task, monthly net benefit, payback:** (calculator output)
- **Break-even success rate compared with the eval target:**
- **Latency budget (p50 / p95):**

## 8. Risk and controls (G3)
- **Tier and the rules that triggered it:**
- **Top risks and their controls:**
- **Required approvers:**
- **Regulatory flags routed for review:**
- Link the full risk assessment.

## 9. Rollout and operations (G4–G5)
- **Rollout stages and exit criteria:**
- **Pre-committed rollback triggers:**
- **Kill switch and fallback path:**
- **Monitoring owner and re-certification cadence:**

## 10. Out of scope and non-goals

## Assumptions Ledger
| Assumption | Why it matters | How to verify | Owner |
|---|---|---|---|

## Open decisions
| Decision | Owner (role) | Needed by |
|---|---|---|

## Approvals
| Role (from the policy for this tier) | Decision | Date |
|---|---|---|

---

<!-- template: business-case -->

# Business case: <feature name>

| Field | Value |
|---|---|
| Owner (role) | |
| Status | Draft · In review · Approved |
| Gate | G1 Value and economics |
| Policy | <policy_id> v<version> |
| Last updated | YYYY-MM-DD |

**Verdict:** Invest · Invest with conditions · Do not invest

## 1. Value hypothesis
For **<users>**, **<AI capability>** will move **<metric>** from **<baseline>** to **<target>** within **<time>**, measured by **<method>**.

## 2. Unit economics inputs
| Input | Value | Source (eval / price list / time study / assumption) |
|---|---|---|
| Model and pricing (input, output, cache read per 1M tokens) | | |
| Input and output tokens per call (incl. reasoning) | | |
| Calls per task | | |
| Other cost per task | | |
| Success rate | | |
| Review minutes per task | | |
| Fallback minutes per failure | | |
| Loaded hourly cost | | |
| Baseline cost per task | | |
| Tasks per month | | |
| Fixed monthly cost | | |
| One-time cost | | |

## 3. Results
Paste the calculator output (`scripts/unit_economics.py --format md`).

| Output | Value |
|---|---|
| Model cost per call | |
| AI cost per attempt | |
| Cost per completed task | |
| Savings per task vs baseline | |
| Monthly net benefit | |
| Payback (months) | |
| Break-even success rate | |

## 4. Sensitivity
| Scenario | Cost per completed task | Monthly net benefit |
|---|---|---|
| Base case | | |
| Success rate −20 points | | |
| Volume ×0.5 | | |
| Volume ×2 | | |
| Tokens ×1.5 | | |

## 5. Latency budget
| Measure | Target |
|---|---|
| p50 | |
| p95 | |

## 6. Interpretation
- **Break-even success rate compared with the eval target:**
- **Largest cost driver, and the lever that addresses it:**
- **What would change the verdict:**

## Assumptions Ledger
| Assumption | Why it matters | How to verify | Owner |
|---|---|---|---|

## Open decisions
| Decision | Owner (role) | Needed by |
|---|---|---|

**Next gate:** G2 Quality and evals

---

<!-- template: eval-plan -->

# Eval plan: <feature name>

| Field | Value |
|---|---|
| Owner (role) | |
| Status | Draft · In review · Approved |
| Gate | G2 Quality and evals |
| Risk tier | (from the risk tier calculator) |
| Policy | <policy_id> v<version> |
| Eval set version | v0.1 |
| Last updated | YYYY-MM-DD |

## 1. Task contract
- **Input:**
- **Output (format, length, required elements):**
- **Correct means:**
- **Worked examples:** good · borderline · bad

## 2. Critical criteria (zero tolerance; any failure blocks launch)
| ID | The system must never… | How it is detected |
|---|---|---|
| C1 | | |

## 3. Quality dimensions and thresholds
| Dimension | Measure | Launch threshold | Grading method |
|---|---|---|---|
| Correctness / faithfulness | | | |
| Completeness | | | |
| Format validity | | | |
| Policy compliance | | | |
| Robustness (adversarial slice) | | | |
| Fairness (largest segment gap) | | | |
| Latency p95 | | | |
| Cost per completed task | | | |

## 4. Golden set
| Item | Plan |
|---|---|
| Size (policy minimum for the tier) | |
| Sources (real / expert-written / synthetic) | |
| Coverage matrix (segments × difficulty × edge cases × adversarial) | |
| Labelling (who; double-labelled share; agreement target) | |
| Held-out split | |
| Repeated runs per case | |

## 5. Model judge (if used)
- **Judge model and why (different family from the system under test where possible):**
- **Calibration:** number of human-labelled cases; agreement target
- **Bias controls:** binary criteria · evidence quotes · randomised order

## 6. Baseline comparison
- **Today's process measured on the same cases by:**
- **Required result:** match or beat on <dimensions>, or the approved trade-off

## 7. Statistical confidence
- **Expected margin of error at this size and pass rate:**
- **Minimum difference we will treat as real:**

## 8. Online metrics and alerts
| Metric | Baseline | Alert threshold | Owner |
|---|---|---|---|
| Acceptance rate | | | |
| Edit distance | | | |
| Override / undo rate | | | |
| Escalation rate | | | |
| Complaint rate per 1,000 | | | |
| Weekly human-review sample | | | |

## 9. Continuous evaluation
- **Runs on:** every prompt · model · retrieval · tool change
- **Blocks release when:**

## Assumptions Ledger
| Assumption | Why it matters | How to verify | Owner |
|---|---|---|---|

## Open decisions
| Decision | Owner (role) | Needed by |
|---|---|---|

**Next gate:** G3 Risk and controls

---

<!-- template: incident-review -->

# Incident or regression review: <title>

| Field | Value |
|---|---|
| Feature | |
| Type | Incident · Quality regression |
| Severity | SEV1 · SEV2 · SEV3 · N/A |
| Owner (role) | |
| Detected | YYYY-MM-DD hh:mm |
| Contained | YYYY-MM-DD hh:mm |
| Policy | <policy_id> v<version> |

The review is blameless: focus on systems and signals, not individuals.

## 1. Summary
What happened, who was affected, and the current status, in three sentences.

## 2. Impact
| Measure | Value |
|---|---|
| Users or records affected | |
| Duration | |
| Harm (data exposure, wrong actions, financial, reputational) | |
| Notifications made (privacy, legal, security, customers) | |

## 3. Timeline
| Time | Event |
|---|---|

## 4. Diagnosis (regression protocol, in order)
| Step | Finding | Share of the drop explained |
|---|---|---|
| 1. Measurement and instrumentation | | |
| 2. Change log (prompt, model, retrieval, tools, configuration) | | |
| 3. Input mix | | |
| 4. Dependencies | | |
| 5. Model behaviour (replay against last-known-good) | | |

## 5. Root cause and contributing factors

## 6. Actions
| Action | Type (fix / detect / prevent) | Owner (role) | Due | Status |
|---|---|---|---|---|
| Add the failing cases to the eval set | Prevent | | | |

## 7. Detection gap
How could this have been caught earlier (an alert, an eval case, a review sample)?

## Assumptions Ledger
| Assumption | Why it matters | How to verify | Owner |
|---|---|---|---|

**Re-certification required:** Yes (SEV1 or material change) · No

---

<!-- template: launch-readiness-review -->

# Launch readiness review: <feature name>

| Field | Value |
|---|---|
| Owner (role) | |
| Review date | YYYY-MM-DD |
| Gate | G4 Launch readiness |
| Risk tier | |
| Policy | <policy_id> v<version> |

**Decision:** Go · Go with conditions · No-go

## 1. Readiness checklist
| Area | Item | Status (Met / Not met / N/A) | Evidence |
|---|---|---|---|
| Quality | Held-out eval at or above the tier thresholds | | |
| Quality | Zero critical failures | | |
| Quality | Baseline comparison complete | | |
| Quality | Model judge calibrated (if used) | | |
| Safety and security | Adversarial / red-team testing as the tier requires | | |
| Safety and security | Prompt-injection tests passed | | |
| Safety and security | Output handling reviewed | | |
| Controls | Every required and conditional control evidenced | | |
| User experience | AI disclosure (where required) | | |
| User experience | Error, refusal and low-confidence states | | |
| User experience | Feedback mechanism | | |
| User experience | Undo or appeal path (high tier) | | |
| Operations | Dashboards and alerts with owners | | |
| Operations | Runbook | | |
| Operations | Kill switch tested | | |
| Operations | Fallback path tested | | |
| Operations | Rate and spend limits | | |
| Operations | Model version pinned | | |
| Support and communications | Support briefed; limitations documented; communications ready | | |
| Approvals | All roles required by the policy have signed | | |

## 2. Blocking gaps (No-go items)
| Gap | Why it blocks | Shortest path to closing it | Owner (role) |
|---|---|---|---|

## 3. Conditions (Go with conditions only)
| Condition | Owner (role) | Due | Must close before stage |
|---|---|---|---|

## 4. Rollout plan
| Stage | Exposure | Entry date | Exit criteria |
|---|---|---|---|
| Internal dogfood | | | |
| Shadow | | | |
| Limited beta | | | |
| Ramp | | | |
| General availability | | | |

## 5. Pre-committed rollback triggers
| Trigger | Threshold | Action | Owner (role) |
|---|---|---|---|

## 6. Sign-off
| Role | Decision | Date |
|---|---|---|

## Assumptions Ledger
| Assumption | Why it matters | How to verify | Owner |
|---|---|---|---|

**Next gate:** G5 Operate and improve

---

<!-- template: model-decision-record -->

# Model decision record: <feature name>

| Field | Value |
|---|---|
| Decision ID | MDR-### |
| Owner (role) | |
| Status | Proposed · Accepted · Superseded |
| Date | YYYY-MM-DD |
| Eval set version | |

## 1. Context
What the feature needs from a model: task, interaction pattern, volume, latency budget, data constraints.

## 2. Approach
- **Rung on the approach ladder:** prompted · structured outputs and tools · RAG · workflow · agent · fine-tuned
- **Why lower rungs were not enough (eval evidence):**

## 3. Candidates compared (same golden set)
| Model / configuration | Pass rate | Critical failures | Cost per completed task | p95 latency | Data terms OK? | Notes |
|---|---|---|---|---|---|---|

## 4. Decision
- **Chosen:** model, exact pinned version, deployment route, key settings
- **Rationale:**
- **Rejected options and why:**

## 5. Portability and exit plan
- **Provider-specific features relied on:**
- **Effort to switch:**

## 6. Re-evaluation triggers
- New model release from a shortlisted vendor
- Cost per completed task changes by more than 20%
- Quality regression or vendor deprecation notice

## Assumptions Ledger
| Assumption | Why it matters | How to verify | Owner |
|---|---|---|---|

---

<!-- template: risk-assessment -->

# Risk assessment: <feature name>

| Field | Value |
|---|---|
| Owner (role) | |
| Status | Draft · In review · Approved |
| Gate | G3 Risk and controls |
| Policy | <policy_id> v<version> |
| Last updated | YYYY-MM-DD |

**Risk tier:** minimal · limited · high · prohibited  **Maximum autonomy at launch:** L_

## 1. Tier classification
Paste the calculator output (`scripts/risk_tier.py --format md`).

| Rule triggered | Tier | Reason |
|---|---|---|

**Unanswered questions (answering them can only raise the tier):**

## 2. Risk register
Likelihood and impact on a 1–5 scale. Write `N/A — <reason>` for categories that do not apply.

| ID | Category | Risk | Likelihood | Impact | Detectability | Controls | Residual | Owner (role) |
|---|---|---|---|---|---|---|---|---|
| R1 | Output quality | | | | | | | |
| R2 | Security | | | | | | | |
| R3 | Privacy and data | | | | | | | |
| R4 | Fairness | | | | | | | |
| R5 | User harm | | | | | | | |
| R6 | Operational | | | | | | | |
| R7 | Legal and IP | | | | | | | |
| R8 | Reputational | | | | | | | |

## 3. Autonomy
- **Level at launch and why:**
- **Promotion criteria to the next level:**

## 4. Control plan
| Control ID | Control | Required by (tier / conditional rule) | Implementation | Evidence | Owner (role) | Status |
|---|---|---|---|---|---|---|

## 5. Approvers required
| Role | Status |
|---|---|

## 6. Regulatory flags (routed for review; not legal advice)
| Flag | Why it may apply | Routed to | Status |
|---|---|---|---|

## Assumptions Ledger
| Assumption | Why it matters | How to verify | Owner |
|---|---|---|---|

## Open decisions
| Decision | Owner (role) | Needed by |
|---|---|---|

**Next gate:** G4 Launch readiness

---

<!-- template: use-case-brief -->

# Use-case brief: <feature name>

| Field | Value |
|---|---|
| Owner (role) | |
| Status | Draft · In review · Approved |
| Gate | G0 Intake and fit |
| Policy | <policy_id> v<version> |
| Last updated | YYYY-MM-DD |

**Verdict:** AI-appropriate · AI-assisted · Deterministic first · Not ready · Do not pursue · Prohibited by policy

## 1. Problem and users
- **Job to be done:**
- **Who does it today, and how often (tasks per month):**
- **What goes wrong today:**

## 2. Current baseline
| Measure | Value | Source (measured / estimated / assumed) |
|---|---|---|
| Time per task | | |
| Cost per task | | |
| Quality (error rate, satisfaction) | | |

## 3. Proposed AI role
- **The model produces:** suggestion · draft · label · extracted fields · answer · action
- **Who acts on the output, and how they check it:**
- **Interaction pattern and why it is the narrowest that works:**

## 4. AI fit test
| # | Dimension | Score (0–2) | Reason |
|---|---|---|---|
| F1 | Input variability | | |
| F2 | Rule coverage | | |
| F3 | Verification cost | | |
| F4 | Error tolerance | | |
| F5 | Context availability | | |
| F6 | Value at volume | | |
| | **Total** | **/12** | |

## 5. Cost of error
- **Worst realistic failure:**
- **Who is harmed, and how badly:**
- **How quickly would we notice:**

## 6. Data
- **Inputs required:**
- **Availability, permissions and quality:**

## 7. Success metric
- **Metric:** baseline → target, by when, measured how

## Assumptions Ledger
| Assumption | Why it matters | How to verify | Owner |
|---|---|---|---|

## Open decisions
| Decision | Owner (role) | Needed by |
|---|---|---|

**Next gate:** G1 Value and economics

---
