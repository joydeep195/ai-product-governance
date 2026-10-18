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
