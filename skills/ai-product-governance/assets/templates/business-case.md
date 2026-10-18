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
