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
