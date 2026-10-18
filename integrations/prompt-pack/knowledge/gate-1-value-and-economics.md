# Gate 1 — Value and economics

**Goal:** show that the feature is worth building and running at the expected volume, including the cost of being wrong.
**Exit artifact:** business case (`assets/templates/business-case.md`).

## 1. State the value hypothesis

Write it as one sentence:

> For **<users>**, **<AI capability>** will move **<metric>** from **<baseline>** to **<target>** within **<time>**, measured by **<method>**.

Value usually comes from one of: time saved (hours × loaded rate), throughput, conversion or revenue, cost avoided (for example contact deflection), quality (fewer errors) or risk reduction. Never count one benefit twice. "Hours saved" and "headcount avoided" are usually the same money.

## 2. Model the cost of a completed task

Every task ends up completed, either by the AI path or by the fallback path when the AI fails. Model both.

| Input | Meaning |
|---|---|
| `price_input_per_mtok`, `price_output_per_mtok` | Price per million tokens for the chosen model |
| `cache_read_price_per_mtok`, `cached_input_fraction` | Optional prompt caching: the share of input tokens served from cache, and its price |
| `input_tokens_per_call` | System prompt, instructions, retrieved context and user input |
| `output_tokens_per_call` | Visible output **plus reasoning tokens**, which most providers bill as output |
| `calls_per_task` | Model calls needed to finish one task: retries, chains, agent turns, guardrail or judge calls |
| `other_cost_per_task` | Retrieval, vector search, third-party APIs, moderation |
| `success_rate` | Share of tasks the AI path completes acceptably. Take it from evals, not from hope |
| `review_minutes_per_task` | Human time spent checking each AI output |
| `fallback_minutes_per_failure` | Human time to finish a task the AI got wrong. Usually the full manual task, plus the review already spent |
| `loaded_hourly_cost` | Fully loaded cost of one hour of the reviewer's time |
| `baseline_cost_per_task` | Cost of today's process per task |
| `tasks_per_month` | Expected volume |
| `fixed_monthly_cost` | Hosting, monitoring, eval runs, share of on-call |
| `one_time_cost` | Build, data preparation, evaluation, launch |

### Formulas

```
model_cost_per_call      = (uncached_input × input_price + cached_input × cache_read_price
                            + output_tokens × output_price) / 1,000,000
ai_cost_per_attempt      = model_cost_per_call × calls_per_task + other_cost_per_task
review_cost_per_task     = review_minutes × hourly_cost / 60
fallback_cost_per_failure= fallback_minutes × hourly_cost / 60
cost_per_completed_task  = ai_cost_per_attempt + review_cost_per_task
                           + (1 − success_rate) × fallback_cost_per_failure
savings_per_task         = baseline_cost_per_task − cost_per_completed_task
monthly_net_benefit      = savings_per_task × tasks_per_month − fixed_monthly_cost
payback_months           = one_time_cost / monthly_net_benefit      (only when the benefit is positive)
break_even_success_rate  = 1 − (baseline_cost_per_task − ai_cost_per_attempt − review_cost_per_task)
                               / fallback_cost_per_failure
```

The break-even success rate is the success rate below which the AI path costs more than today's process. Compare it with what the evals show the system can actually reach.

Run `python scripts/unit_economics.py --input <file>`. It computes all of the above and a sensitivity table (success rate −20 points, volume ×0.5 and ×2, tokens ×1.5). Use `--example` for a starting input file.

## 3. Read the numbers like an owner

- **Human time usually dominates.** For most enterprise workflows, review and failure handling cost more than tokens. Raising the success rate and cutting review time are usually worth more than a cheaper model. Check this against the numbers rather than assuming it.
- **A break-even close to the eval target is a warning.** If break-even is 80% and evals reach 85% ± 6 points, the business case is fragile.
- **Measure tokens on real traffic.** Reasoning tokens, retrieved context and retries make estimates from visible text wrong, sometimes by several times.
- **Prices per token change.** Cost per completed task is the stable way to compare models and vendors.

## 4. Cost levers, in order

1. **Raise the success rate** with better instructions, retrieval or a narrower scope. This cuts the fallback cost.
2. **Cut review time** with verification-friendly UX: highlighted changes, citations, confidence signals.
3. **Cache stable prompt prefixes**, such as system prompts, policies and shared documents.
4. **Trim context:** retrieve less, summarise long histories.
5. **Batch** non-interactive workloads. Providers typically discount asynchronous batch processing.
6. **Lower reasoning effort or use a smaller model for easy cases,** but only after evals show quality holds. Measure a routing cascade end to end against one strong model at lower effort before adopting it.

## 5. Set a latency budget

Set p50 and p95 targets for the interaction pattern and record them in the PRD. Typical tolerances:

| Pattern | Typical tolerance |
|---|---|
| Inline suggestion or autocomplete | Users ignore it unless it appears almost instantly (well under a second) |
| Interactive chat or drafting | First visible output within about two seconds, streamed; complete answers in seconds |
| Background or batch | Minutes to hours; optimise for cost |
| Agentic tasks | Show progress, cap wall-clock time, keep state resumable |

## Exit criteria

- [ ] Value hypothesis with baseline, target and measurement method.
- [ ] Unit economics with a source for every input: eval result, vendor price list, time study, or a labelled assumption.
- [ ] Sensitivity analysis, with the break-even success rate compared against the eval target.
- [ ] Latency budget (p50 and p95).
