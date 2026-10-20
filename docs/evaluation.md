# Evaluation methodology

The skill's claim is behavioural: models give better AI governance advice with it than without it. The eval
harness measures that claim on any model, the way Gate 2 of the skill asks product teams to measure theirs.

## Design

| Element | Choice | Why |
|---|---|---|
| Scenarios | 10 realistic requests across every gate (`evals/scenarios/*.json`) | Each targets a known failure mode: fabricated numbers, AI where rules suffice, launch pressure, autonomous money movement, premature model switching, legal overreach |
| Arms | **with-skill** vs **baseline** | Isolates what the skill contributes |
| Baseline | The same model with a strong expert persona prompt, no skill | A fair control: the skill must beat a good prompt, not an empty one |
| Skill host | Agent CLIs (Claude Code, Codex, Gemini CLI, Copilot CLI, Cursor): the tool's own native skill loading. API models: a provider-neutral emulator (SKILL.md in context, `read_skill_file` and `run_skill_script` tools). Manual kit: your chat tool with the skill switched on | Native hosts show real-world behaviour; the emulator gives API models the same host |
| Grading | Binary rubric criteria graded blind by a model (by default the same tool), plus deterministic regex checks | Binary criteria with quoted evidence are more stable than holistic scores; one tool is enough |
| Critical criteria | Zero tolerance: a single failure fails the trial | Mirrors the launch rule in Gate 2 |
| Trials | 3 per cell by default | Models are non-deterministic; report mean and spread |
| Skill adherence | Did the model read the expected playbook and run the expected calculator? | Separates "the skill was followed" from "the answer was good" |

## Running: one AI tool is enough

You never need more than one AI tool, and it does not matter which one. Pick the path that matches what you use.

### Automatic, with whatever you are signed in to

```bash
pip install -e ".[evals]"
aipg eval --dry-run     # shows what was detected and what would run; no model calls
aipg eval --trials 1    # quick signal
aipg eval               # full run (3 trials)
```

`aipg eval` tries these in order and uses the **first one that is ready**, both to answer and to grade:

| Order | Access | Signs in with | Status |
|---|---|---|---|
| 1 | Claude Code (`claude-code`) | Your Claude subscription (`claude auth login`), or the copy bundled with Claude Desktop | Verified |
| 2 | OpenAI Codex CLI (`codex`) | ChatGPT account (`codex login`) | Unverified profile |
| 3 | Gemini CLI (`gemini-cli`) | Google account | Unverified profile |
| 4 | GitHub Copilot CLI (`copilot-cli`) | Copilot subscription | Unverified profile |
| 5 | Cursor CLI (`cursor-cli`) | Cursor subscription | Unverified profile |
| 6 | Anthropic API (`anthropic-api`) | `ANTHROPIC_API_KEY` | Verified |
| 7 | OpenAI API (`openai-api`) | `OPENAI_API_KEY` | Verified client, any OpenAI-compatible endpoint |
| 8 | Gemini API (`gemini-api`) | `GEMINI_API_KEY` | Via Gemini's OpenAI-compatible endpoint |
| 9 | Local model (`local-ollama`) | Nothing: a model running on your machine with Ollama or LM Studio | No account, no cost |

"Unverified" profiles were built from each tool's documentation and are tested against a fake CLI, but have not
yet been run against the real tool. Run one and open an issue with the result, and it becomes verified.

Useful options: `--subject <id>` picks a specific access, `--model` and `--effort` override the model and effort,
`--judge <id>` grades with a different model, and `--all` runs every ready access for a cross-tool scorecard.

**Grading with the same tool.** By default the tool that answered also grades, so one tool is enough. Grading is
blind (the grader never sees which arm produced an answer), and both arms share the same grader, so the
with-skill vs baseline difference stays comparable even though a model may favour its own style. For an
independent grader, set `judge.use` in `eval.config.json` to another model.

#### Claude Code details

- **Finding the CLI:** `claude` on `PATH`, `$AIPG_CLAUDE_BIN`, or the copy bundled with the Claude desktop app,
  detected automatically. The dry run prints the exact login command for the copy it found.
- **Model and effort:** Claude Opus 5.5 at `max` effort by default, grading at `high`. Set `"inherit"` in
  `eval.config.json` to use Claude Code's own defaults.
- **A real skill host:** the skill is installed into a throwaway workspace at `.claude/skills/`, Claude decides on
  its own whether to activate it, and the report records whether it did, which playbooks it read and which
  calculators it ran.
- **Isolation:** a fresh empty workspace per run; `--setting-sources project` keeps your personal settings, skills,
  plugins, hooks and CLAUDE.md out; `--no-session-persistence` keeps runs out of your history; only Python (for the
  calculators) is allowed in the with-skill arm and no tools at all elsewhere; API keys and variables from a
  surrounding Claude Code session are stripped so the run really uses your login.
- **CI:** run `claude setup-token` (Pro, Max, Team or Enterprise plans) and store the token as the
  `CLAUDE_CODE_OAUTH_TOKEN` secret of the `evals` environment.

#### Other agent CLIs

Codex, Gemini CLI, Copilot CLI and Cursor CLI are driven through declarative profiles in
`src/ai_product_governance/evals/agent_cli.py`: how the prompt is passed, where the tool discovers project skills
(`.agents/skills/`), how the final answer is read, and how sign-in is detected. Each run uses a throwaway
workspace, and Codex additionally runs with `--ephemeral --ignore-user-config --sandbox read-only`. These tools do
not expose their tool calls in a stable format, so skill adherence is reported only for Claude Code. To add a tool,
add a profile.

### Agent-run kit, inside the AI tool you are already using (`/ai-eval`)

No sign-in, CLI or API key: your own agent runs the suite in its current session. In Claude Code, Codex, GitHub
Copilot (agent mode), Cursor, Gemini CLI or any agent that can run commands and start sub-agents, open a checkout of
this repository and ask it to evaluate the skill: say "evaluate the skill", or use `/ai-eval` (a Copilot prompt
file and an MCP prompt). The agent follows the skill's
[`references/evaluate-this-skill.md`](../skills/ai-product-governance/references/evaluate-this-skill.md):

1. It tells you the cost (20 answers and 20 gradings for the full suite, against your plan's usage) and waits for
   your go-ahead.
2. It runs `aipg eval-kit create --agent-run --tool "<tool> (<model>)"`. Each file in the kit's `prompts/` folder is
   a complete task: whether its sub-agent may use the skill, the request, and the file to save the answer in.
3. It starts a **fresh sub-agent** per task and sends it one line, ``Read `<task file>` and do exactly what it
   says.``, so it never relays long prompts or replies itself. Each sub-agent saves its own answer. Then it runs
   `aipg eval-kit grade`, does the same for the blind grading tasks in `grading/`, and runs `aipg eval-kit score`.
4. It reports the gates and the with-skill vs baseline scores.

The report labels these runs **agent-run**. Nothing outside the tool checks that the baseline sub-agents could not
see the skill, or that replies were saved unedited, so agent-run results are indicative evidence for that tool and
model, not an audited result. Use `aipg eval` with an automated subject when you need audit-grade evidence.

### Manual kit, with any chat tool

For ChatGPT, Gemini, Microsoft 365 Copilot, Claude apps or any tool that cannot be scripted:

```bash
aipg eval-kit create --tool "ChatGPT (GPT-5)"   # 1. writes a run sheet and empty answer files
aipg eval-kit grade evals/kits/<kit id>         # 2. after you paste the answers: blind grading prompts
aipg eval-kit score evals/kits/<kit id>         # 3. after you paste the gradings: the report
```

1. **Answers:** for each prompt in `1-ANSWERS.md`, open a new chat (part A with the skill switched on, part B with it
   off), paste the prompt and save the reply into the named file.
2. **Grading:** for each prompt in `2-GRADING.md`, open a new chat without the skill, paste it and save the JSON reply.
   The order is shuffled so the grader cannot tell which answers used the skill.
3. **Score:** the toolkit scores everything offline and writes the same report, gates and JUnit output as an
   automatic run.

A one-trial kit is 20 answers plus 20 gradings: slow, but it works with any tool and needs no setup.

Each run writes `evals/results/<run id>/`:

| File | Contents |
|---|---|
| `report.md` | Summary by subject and arm, gates, per-scenario scores, skill adherence, every failed criterion with the judge's rationale |
| `results.json` | How each subject was produced, then every trial: response, verdicts, evidence, files read, scripts run, tokens, cost |
| `junit.xml` | Gates and per-scenario results for CI dashboards |
| `manifest.json` | Reproducibility: git commit, skill content hash, config hash, models, SDK versions |

## Gates

Configured in `eval.config.json` and enforced per subject (the command exits 1 on failure, 3 when the cost ceiling
cut the run short):

| Gate | Default |
|---|---|
| Mean with-skill score | ≥ 0.80 |
| Critical failures with the skill | 0 |
| Uplift over the baseline arm | ≥ 0.00 |
| Drop against `evals/baselines/latest.json` (with `--compare`; see below) | ≤ 0.05 |

## Baselines and regressions

`aipg eval --compare <results.json>` adds a `max_regression` gate for every subject: it fails when the subject's
with-skill mean score is more than `gates.max_regression` below the baseline's. CI passes
`--compare evals/baselines/latest.json`.

**Which baseline score a subject is compared with.** First, the baseline's results for the same subject id (an
automated run of `claude-code` against an earlier automated run of `claude-code`). Failing that, a kit result that
declares it stands in for that subject id (see below). A same-id match always wins.

**When nothing matches, the gate is skipped, visibly.** The plan printed before any model call shows a
`regression check:` line per subject, saying what it will be compared with or that it will be skipped. After the
run, a skipped gate is printed as a warning, shown as `skipped` in `report.md` (whose verdict line then reads, for
example, `PASS (1 skipped)`) and written as `<skipped>` in `junit.xml`. A skipped gate never fails the run. A
baseline file that cannot be read stops the run with exit code 2 before any model call.

**Saving a baseline.** After reviewing a run, `aipg eval --update-baseline` or
`aipg eval-kit score <kit> --update-baseline` copies that run's `results.json` to `evals/baselines/latest.json`,
byte for byte. `results.json` records how each subject was produced (`subjects`: id, provider, model and effort;
for kits also `indicative` and `stands_in_for`), so the baseline describes itself.

**Using a kit as the baseline for an automated subject.** A kit's subject id is the tool label you gave it, such as
`Claude Code (Claude Opus 5.5)`, which no automated subject matches. To compare an automated subject with it, name
that subject when you score the kit:

```bash
aipg eval-kit score evals/kits/<kit id> --stands-in-for claude-code --update-baseline
```

Only do this when the kit ran in that subject's tool and model, such as an `/ai-eval` in Claude Code with Claude
Opus 5.5 standing in for `claude-code`. The kit keeps its tool label as its subject id, and the gate names it and
keeps the agent-run label: `1.000 vs baseline 1.000 from 'Claude Code (Claude Opus 5.5)' (agent-run result,
indicative)`. An unknown subject id is refused.

**Is comparing an agent-run kit with an automated run meaningful?** Partly. Both use the same scenarios, rubric,
deterministic checks and gates, and by default both are graded blind by the model that answered. They still measure
different things:

- **Skill activation.** Agent-run with-skill sub-agents are told to read `SKILL.md`. The `claude-code` subject
  decides on its own whether to load the skill, and that choice is part of what it measures. Agent-run with-skill
  scores are therefore closer to an upper bound.
- **Environment and effort.** Agent-run sub-agents inherit the session's effort level and environment (settings,
  plugins, `CLAUDE.md`). Automated runs are isolated and use the configured effort (`max` answering, `high`
  grading, for `claude-code`).
- **Verification.** Nothing outside the tool checks that agent-run baseline sub-agents could not see the skill, or
  that replies were saved unedited.

So a drop against an agent-run baseline is a tripwire, not proof of a regression. CI enforces it like any other
gate, so it gets noticed. When it fires, read the report. If a content change lowered the scores, that is a
regression. If the drop comes from the host (the skill was not activated, or effort differs), it is a measurement
difference. In that case, review the automated run and commit it with `aipg eval --update-baseline`: it becomes a
like-for-like baseline that matches by subject id. Only a like-for-like automated comparison is audit-grade.

**Why not match on the model, or map subjects on the command line?** A kit records a tool label, not a model id.
Also, one model behind different hosts measures different things: `claude-code` (native skill loading, `max`
effort) and `anthropic-api` (the emulator, `medium` effort) both serve Claude Opus 5.5. A command-line mapping would
have to live in the CI workflow and be edited whenever the baseline changes. Recording the claim in the baseline
keeps it next to the scores that reviewers approve.

**In CI.** The committed baseline is an agent-run kit that stands in for `claude-code`, so the gate applies when CI
runs the `claude-code` subject (the `CLAUDE_CODE_OAUTH_TOKEN` secret is set). Without that secret, CI uses the next
ready subject, such as `anthropic-api`, and the report shows the gate as skipped.

## Cost

`aipg eval --dry-run` prints an order-of-magnitude estimate from configured prices. A full default run (one
subject, 10 scenarios, 2 arms, 3 trials, plus judging) is roughly $10 at the listed Claude Opus 5.5 prices; one
trial is about a third of that. `--max-cost-usd` stops starting new trials once measured spend reaches the ceiling.

## Known limitations

- **Judge bias.** Model judges can favour longer answers and their own model family. Criteria are binary with
  quoted evidence, the judge never sees which arm produced a response, and you can set a judge from a different
  family than the subject. Calibrate against human labels before relying on small differences.
- **Arm leakage.** With-skill responses often follow the skill's templates, which a judge might recognise. Criteria
  test substance rather than format to limit the effect.
- **Small samples.** Ten scenarios × three trials gives directional evidence, not precise estimates. Treat
  differences of a few points as noise.
- **Triggering is measured only for native hosts.** API subjects get the skill activated directly. The `claude-code`
  subject measures whether Claude Code chooses to load it; other tools need their own native runs.
- **Subscription costs are estimates.** For `claude-code` runs, the reported cost is Claude Code's API-equivalent
  estimate; on a subscription the real effect is plan usage.
