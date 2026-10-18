# Evaluation methodology

The skill's claim is behavioural: models give better AI governance advice with it than without it. The eval
harness measures that claim on any model, the way Gate 2 of the skill asks product teams to measure theirs.

## Design

| Element | Choice | Why |
|---|---|---|
| Scenarios | 10 realistic requests across every gate (`evals/scenarios/*.json`) | Each targets a known failure mode: fabricated numbers, AI where rules suffice, launch pressure, autonomous money movement, premature model switching, legal overreach |
| Arms | **with-skill** vs **baseline** | Isolates what the skill contributes |
| Baseline | The same model with a strong expert persona prompt, no skill | A fair control: the skill must beat a good prompt, not an empty one |
| Skill host | A provider-neutral emulator: SKILL.md in context, `read_skill_file` and `run_skill_script` tools | Every model gets the same progressive-disclosure host, so differences come from models, not integrations |
| Grading | Binary rubric criteria graded by a judge model, plus deterministic regex checks | Binary criteria with quoted evidence are more stable than holistic scores |
| Critical criteria | Zero tolerance: a single failure fails the trial | Mirrors the launch rule in Gate 2 |
| Trials | 3 per cell by default | Models are non-deterministic; report mean and spread |
| Skill adherence | Did the model read the expected playbook and run the expected calculator? | Separates "the skill was followed" from "the answer was good" |

## Running

```bash
pip install -e ".[evals]"
export ANTHROPIC_API_KEY=...            # judge and Claude subjects
export OPENAI_API_KEY=...               # optional: OpenAI subject
export GEMINI_API_KEY=...               # optional: Gemini via its OpenAI-compatible endpoint

aipg eval --dry-run                     # validate, plan, estimate cost; no API calls
aipg eval --trials 1 --max-cost-usd 5   # quick signal
aipg eval                               # full run (3 trials)
aipg eval --subject openai --subject claude-opus-5-5 --scenario g4-claims-triage-launch
```

Subjects are configured in `evals/eval.config.json`. Any OpenAI-compatible endpoint works through `base_url`, which
covers Gemini, Azure OpenAI and local model servers. Subjects without credentials are skipped with a message.

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
- **Triggering is out of scope.** The harness activates the skill directly. Whether a given tool *chooses* to load
  the skill depends on that tool; test it there (for example with `claude plugin eval` in Claude Code).
