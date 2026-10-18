# Evaluation methodology

The skill's claim is behavioural: models give better AI governance advice with it than without it. The eval
harness measures that claim on any model, the way Gate 2 of the skill asks product teams to measure theirs.

## Design

| Element | Choice | Why |
|---|---|---|
| Scenarios | 10 realistic requests across every gate (`evals/scenarios/*.json`) | Each targets a known failure mode: fabricated numbers, AI where rules suffice, launch pressure, autonomous money movement, premature model switching, legal overreach |
| Arms | **with-skill** vs **baseline** | Isolates what the skill contributes |
| Baseline | The same model with a strong expert persona prompt, no skill | A fair control: the skill must beat a good prompt, not an empty one |
| Skill host | API models: a provider-neutral emulator (SKILL.md in context, `read_skill_file` and `run_skill_script` tools). Claude Code: the real, native skill host | The emulator gives every model the same host; the native host measures real-world activation |
| Grading | Binary rubric criteria graded by a judge model, plus deterministic regex checks | Binary criteria with quoted evidence are more stable than holistic scores |
| Critical criteria | Zero tolerance: a single failure fails the trial | Mirrors the launch rule in Gate 2 |
| Trials | 3 per cell by default | Models are non-deterministic; report mean and spread |
| Skill adherence | Did the model read the expected playbook and run the expected calculator? | Separates "the skill was followed" from "the answer was good" |

## Running without an API key (your Claude subscription)

The `claude-code` subject and judge run [Claude Code](https://code.claude.com) in headless mode (`claude -p`) with the
Claude login you already have. No API key is needed, and usage counts against your plan's limits instead of being
billed per token.

```bash
claude auth login                        # once: sign in with your Claude account in the browser
aipg eval --dry-run --subject claude-code
aipg eval --subject claude-code --trials 1
```

- **Finding the CLI:** `claude` on `PATH`, `$AIPG_CLAUDE_BIN`, or the copy bundled with the Claude desktop app, which is
  detected automatically. The dry run prints the exact login command for the copy it found.
- **Model and effort:** the default is Claude Opus 5.5 at `max` effort for the subject and `high` for the judge.
  Override them per run with `--model` and `--effort`, or set `"inherit"` in `eval.config.json` to use Claude
  Code's own defaults. Lower effort finishes faster and uses less of your plan.
- **A real skill host:** in the with-skill arm the skill is installed into a throwaway workspace at `.claude/skills/`,
  and Claude decides on its own whether to activate it. The report records whether it did ("activated the skill"),
  which playbooks it read and which calculators it ran, which the API harness cannot measure.
- **Isolation:** every run uses a fresh empty workspace; `--setting-sources project` keeps your personal settings,
  skills, plugins, hooks and CLAUDE.md out; `--no-session-persistence` keeps eval runs out of your history; anything
  not explicitly allowed is denied (the with-skill arm may run Python for the calculators, while the baseline arm
  and the judge have no tools); and API keys and variables from a surrounding Claude Code session are removed from
  the child process so the run really uses your login.
- **CI:** run `claude setup-token` (Pro, Max, Team or Enterprise plans) and store the token as the
  `CLAUDE_CODE_OAUTH_TOKEN` secret of the `evals` environment; the Evals workflow installs Claude Code and uses it.

## Running with API keys (any model)

```bash
pip install -e ".[evals]"
export ANTHROPIC_API_KEY=...            # judge and Claude subjects
export OPENAI_API_KEY=...               # optional: OpenAI subject
export GEMINI_API_KEY=...               # optional: Gemini via its OpenAI-compatible endpoint

aipg eval --dry-run                     # validate, plan, estimate cost; no model calls
aipg eval --trials 1 --max-cost-usd 5   # quick signal
aipg eval                               # full run (3 trials)
aipg eval --subject openai --subject claude-opus-5-5 --scenario g4-claims-triage-launch
```

Subjects are configured in `evals/eval.config.json`. Any OpenAI-compatible endpoint works through `base_url`, which
covers Gemini, Azure OpenAI and local model servers. Subjects without credentials are skipped with a message, and the
judge is the first entry in the `judge` list that is ready (or the one you name with `--judge`).

Each run writes `evals/results/<run id>/`:

| File | Contents |
|---|---|
| `report.md` | Summary by subject and arm, gates, per-scenario scores, skill adherence, every failed criterion with the judge's rationale |
| `results.json` | Every trial: response, verdicts, evidence, files read, scripts run, tokens, cost |
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
| Drop against `evals/baselines/latest.json` | ≤ 0.05 |

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
