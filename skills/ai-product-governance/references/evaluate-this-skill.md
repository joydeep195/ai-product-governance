# Evaluate this skill with your own AI tool (/ai-eval)

**Goal:** measure whether this skill improves answers on the AI tool and model the user already works in, using
that tool's own session: no API key, no extra sign-in. You, the agent, run the eval suite by giving every prompt to
a fresh sub-agent.

## Before you start

Check all three. If any fails, stop and tell the user which one and what to do instead.

| Requirement | If it is missing |
|---|---|
| A checkout of the `ai-product-governance` repository, with `aipg` installed in it (`python -m pip install -e .`). The eval scenarios live in its `evals/` folder | Ask the user to clone the repository, or run there |
| You can run shell commands | Tell the user to use the copy-and-paste kit: `aipg eval-kit create` |
| You can start **fresh sub-agents**: separate contexts that see only what you give them, and can read and write files | Same: the copy-and-paste kit. Never answer the prompts in this conversation instead; that contaminates the result |

Then tell the user what it costs before running anything: one sub-agent per answer and one per grading, so the
full suite is 20 answers and 20 gradings (fewer with `--scenario`), all counted against their plan's usage. Start
only after they agree.

## Rules

The result means something only if you follow these exactly.

1. **Never answer or grade a task yourself.** Every answer and every grading comes from a new sub-agent.
2. **Send each sub-agent its one line from the run sheet, exactly, and nothing else:** no summary, hints or
   context of your own. The line points to a task file that says what the sub-agent may use, and where it saves
   its reply.
3. **Never write, edit or repair a reply.** If a sub-agent errors or leaves its file empty, start a new one with
   the same line.
4. **Do not open the scenario files, the task files or their criteria yourself.** The sub-agents read them.
5. Sub-agents may run one at a time or in parallel.

## Steps

1. Create an agent-run kit, naming the tool and model you are:

   ```bash
   aipg eval-kit create --agent-run --tool "<tool> (<model>)"
   ```

   Add `--scenario <id>` (repeatable) to run part of the suite, or `--trials <n>` for repeat runs. Note the kit
   folder it prints.
2. `<kit>/1-ANSWERS.md` lists one line per answer, such as ``Read `<kit>/prompts/A01.md` and do exactly what it
   says.`` Start one fresh sub-agent per line and send it that line. Each sub-agent writes its answer into
   `<kit>/answers/`.
3. Prepare the blind grading: `aipg eval-kit grade <kit>`. It stops with a list if any answer file is still empty.
4. `<kit>/2-GRADING.md` lists one line per grading. Do the same: one fresh sub-agent per line, which writes its
   verdicts into `<kit>/verdicts/`.
5. Score it: `aipg eval-kit score <kit>`. It exits 1 when a quality gate fails; that is a result, not an error.

## Report back

Read `<kit>/report/report.md` and give the user:

- the gate result, and the mean score, pass rate and critical failures for each arm (with and without the skill);
- the scenarios where the skill did not help, with the failed criteria;
- that this was an **agent-run** result: one tool answered and graded through sub-agents, and nothing outside the
  tool verified that the baseline sub-agents could not see the skill. It is indicative evidence for this tool and
  model only. For audit-grade evidence, run `aipg eval` with an automated subject.
