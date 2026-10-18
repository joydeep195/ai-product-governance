# Gate 0 — Intake and AI fit

**Goal:** decide whether AI is the right tool before anyone writes a spec.
**Exit artifact:** use-case brief with a fit verdict (`assets/templates/use-case-brief.md`).

## 1. Capture the use case

Collect the following, or assume it and label the assumption.

| Field | Question |
|---|---|
| Problem | What job is the user trying to get done, and what goes wrong today? |
| Users and volume | Who does it, how often (tasks per month), and how long does each task take now? |
| Current baseline | How is it done today, what does it cost, and how good is it (error rate, cycle time, satisfaction)? |
| Proposed AI role | What exactly would the model produce: a suggestion, a draft, a label, extracted fields, an answer, or an action? |
| Decision owner | Who acts on the output, and can they check it? |
| Cost of error | What happens if the output is wrong and nobody notices? Who is harmed, and how badly? |
| Data | What inputs does the model need? Are they available, permitted for this purpose, and of usable quality? |
| Success metric | Which business or user metric must move, from what baseline, to what target? |
| Driver | Why now: customer demand, cost pressure, competition, or an executive mandate? |

An executive mandate is a valid driver but not evidence of value. Record it as a driver and keep looking for the user problem.

## 2. Run the AI fit test

Score each dimension 0, 1 or 2 and justify each score in one sentence.

| # | Dimension | 2: strong fit | 0: weak fit |
|---|---|---|---|
| F1 | Input variability | Unstructured, varied language, documents or images | Structured fields with known formats |
| F2 | Rule coverage | Rules, search or lookup would handle under half of the cases | Rules or lookup would handle 80% or more |
| F3 | Verification cost | Checking an output is much cheaper than producing it | Checking takes as long as doing the task |
| F4 | Error tolerance | Errors are cheap, visible and reversible | Errors are costly, silent or irreversible |
| F5 | Context availability | The information needed is in the input or can be retrieved | The answer depends on knowledge nobody can give the model |
| F6 | Value at volume | Enough volume or value per task to pay for evals and operations | A rare, low-value task |

F3 is the most useful single test: generative AI pays off where producing is expensive but checking is cheap.

### Verdict

Read the pattern, not just the total. Apply the first rule that matches.

1. The policy prohibits the use case (see Gate 3) → **Prohibited by policy**, whatever the score.
2. F2 = 0 → **Deterministic first**: build rules, search, validation or a better form. Use AI only for the residual cases, and only if they are valuable.
3. F5 = 0 → **Not ready**: fix data access or quality before any modelling.
4. F3 = 0 and F4 = 0 → **AI-assisted only**: AI may suggest or draft, never decide. Cap autonomy at L2.
5. Total ≥ 9 with no zeroes → **AI-appropriate**.
6. Total 6–8 → **AI-assisted**: viable with human verification and a narrow scope.
7. Total ≤ 5 → **Do not pursue now**. Record what would change the verdict.

## 3. Choose the narrowest interaction pattern

Narrower patterns are cheaper, safer and much easier to evaluate. Pick the least open-ended pattern that delivers the value.

| Pattern | Example | Evaluation difficulty |
|---|---|---|
| Classification or routing | Triage tickets to the right queue | Low: compare against correct labels |
| Extraction to structured fields | Pull totals and dates from invoices | Low: field-level accuracy |
| Inline suggestion | Suggested reply an agent can accept | Medium |
| Draft for review | First draft of a contract summary | Medium: rubric-based grading |
| Grounded Q&A (RAG) | Answer policy questions from documents | Medium to high: retrieval plus faithfulness |
| Open conversation | General assistant | High |
| Agentic action | Issue refunds, update records | High: action correctness plus safety |

Default away from chat. A chat box is rarely the narrowest pattern for a well-defined job.

## 4. Anti-patterns to name

- **Solution looking for a problem** ("we need an AI strategy"): go back to a user job and a metric.
- **LLM as calculator, database or validator:** exact arithmetic, lookups, format validation and deterministic business rules belong in code.
- **Boil-the-ocean assistant:** a general chatbot instead of one well-defined job.
- **Demo-driven commitment:** a great demo on five hand-picked examples says nothing about the long tail. Ask for the eval plan.
- **Automating a broken process:** if today's process produces the wrong outcome, AI produces it faster.

## Exit criteria

- [ ] Use-case brief complete, with every assumption labelled.
- [ ] Fit verdict with a reason for each dimension's score.
- [ ] Interaction pattern chosen and justified.
- [ ] Decision owner (a role) and a success metric with a baseline, or a plan to measure the baseline.
