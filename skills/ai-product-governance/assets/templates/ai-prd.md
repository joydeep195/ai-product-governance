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
