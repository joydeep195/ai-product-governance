# Gate 4 — Launch readiness

**Goal:** decide whether to expose users, to how many, and under what conditions.
**Exit artifact:** launch readiness review (`assets/templates/launch-readiness-review.md`).

## 1. Review readiness, area by area

Mark every item **Met**, **Not met** or **N/A**, with a link to the evidence. "We think so" is not evidence.

| Area | Items |
|---|---|
| Quality | Held-out eval at or above the tier thresholds; zero critical failures; baseline comparison done; model judge calibrated (if used) |
| Safety and security | Adversarial and red-team testing done as the tier requires; prompt-injection tests passed; output handling reviewed (nothing rendered or executed unsanitised) |
| Controls | Every required and conditional control from the policy has evidence |
| User experience | AI disclosure where required; error, refusal and low-confidence states designed; feedback mechanism live; undo or appeal path for people affected (high tier) |
| Operations | Dashboards for quality, safety, cost and latency; alerts with thresholds and owners; runbook; kill switch tested; fallback path tested; rate and spend limits; model version pinned |
| Support and communications | Support team briefed; known limitations documented; internal and customer communications ready |
| Approvals | Sign-off from every role the policy requires for the tier |

## 2. Plan a staged rollout

| Stage | Exposure | Purpose | Exit to the next stage |
|---|---|---|---|
| Internal dogfood | Employees only | Catch obvious failures cheaply | No open critical issues; feedback triaged |
| Shadow | AI runs on real traffic; output hidden from users or shown only to reviewers | Compare the AI with today's process on live data | Live sample meets the thresholds |
| Limited beta | Opt-in users or a small percentage | Real usage and real UX | Guardrail metrics within limits for the agreed period |
| Ramp | For example 5% → 25% → 50% | Scale safely | No guardrail breach at each step |
| General availability | All eligible users | — | — |

Shadow mode does not fit every pattern (open conversation, for example). Skip it only with a stated reason.

## 3. Pre-commit rollback triggers

Agree before launch on the thresholds that pause or roll back the rollout. Committing in advance prevents explaining away bad numbers afterwards. For example:

- Any critical incident: data exposure, harmful output reaching a user, or an unauthorised action.
- Override or undo rate above the eval baseline plus an agreed tolerance.
- Complaint rate above an agreed number per 1,000 interactions.
- Cost per completed task above budget for three consecutive days.
- p95 latency above budget for an agreed number of hours.

## 4. Decide

- **Go:** every item is met.
- **Go with conditions:** only non-critical gaps remain. Each condition gets an owner, a due date, and the rollout stage it must close before.
- **No-go:** any critical gap, such as a critical eval failure, a pass rate below the tier threshold, a missing mandatory control, a missing approval, or an untested kill switch. State the shortest path to Go.

Schedule pressure is not a readiness criterion. If the date is fixed, reduce scope or exposure (for example an internal-only launch or shadow mode) rather than lowering the bar.

## Exit criteria

- [ ] Readiness review complete, with evidence for every item.
- [ ] Rollout plan with exit criteria for every stage and pre-committed rollback triggers.
- [ ] Decision recorded, with the approvers who signed it.
