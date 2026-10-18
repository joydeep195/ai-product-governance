# Glossary

| Term | Meaning in this skill |
|---|---|
| Acceptance rate | Share of AI suggestions or drafts that users keep (with or without edits). |
| Assumptions Ledger | The closing table of every artifact listing what was assumed, why it matters, how it will be verified and who owns that. |
| Autonomy level | L0 Inform → L5 Autonomous; how much the AI does without a human approving each output or action. |
| Baseline | Performance and cost of today's process on the same cases; what the AI must match or beat. |
| Break-even success rate | The success rate below which the AI path costs more per task than today's process. |
| Control | A required safeguard from the policy catalogue (for example OPS-02, kill switch and fallback). |
| Cost per completed task | Model cost plus review time plus the expected cost of handling failures; the honest unit for comparing AI with alternatives. |
| Critical criterion | A zero-tolerance eval criterion. One failure blocks launch regardless of averages. |
| Drift | Change over time in inputs, retrieved content or model behaviour that degrades quality. |
| Edit distance | How much users change an AI draft before using it; a proxy for draft quality. |
| Fallback path | The non-AI way a task gets done when the AI fails, is switched off or is unavailable. |
| Gate | One of six lifecycle checkpoints (G0–G5), each with exit criteria and an artifact. |
| Golden set | A versioned set of representative test cases with expected outcomes or grading notes. |
| Held-out split | Part of the golden set never used while tuning, reserved for launch decisions. |
| Indirect prompt injection | Instructions hidden in content the AI reads (documents, emails, web pages, tool results) that try to change its behaviour. |
| Kill switch | A tested mechanism that turns the AI path off quickly and routes work to the fallback path. |
| LLM-as-judge | Using a model to grade outputs against a rubric; must be calibrated against human labels. |
| Override rate | Share of AI outputs or actions that humans reverse or replace. |
| Policy | The machine-readable governance policy (`policy.json`) that defines tiers, rules, controls, approvers and eval minimums. |
| RAG | Retrieval-augmented generation: the model answers using documents retrieved at query time. |
| Re-certification | Repeating the gate review on a cadence or after a material change. |
| Risk tier | Minimal, limited, high or prohibited; computed from the policy questionnaire. |
| Shadow mode | Running the AI on live traffic without exposing its output, to compare it with the current process. |
| Success rate | Share of tasks the AI completes acceptably without human rework, measured by evals. |
