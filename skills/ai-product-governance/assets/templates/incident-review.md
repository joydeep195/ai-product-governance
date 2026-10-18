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
