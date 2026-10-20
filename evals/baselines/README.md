# Eval baselines

`latest.json` is the reviewed `results.json` of the last accepted eval run. CI runs `aipg eval --compare` against it
and fails when a subject's with-skill score drops by more than `gates.max_regression` (see `../eval.config.json`).

A subject is compared with the baseline's results for the same subject id, or with a kit result that stands in for
that id. When nothing in the baseline matches, the gate is reported as skipped in the console, `report.md` and
`junit.xml`; it never passes silently. The details are in
[`docs/evaluation.md`](../../docs/evaluation.md#baselines-and-regressions).

Create or refresh it after a run you have reviewed:

```bash
aipg eval --update-baseline                                                            # an automated run
aipg eval-kit score evals/kits/<kit id> --stands-in-for claude-code --update-baseline  # a kit
```

Pass `--stands-in-for` only when the kit ran in that subject's tool and model. Commit the change in the same pull
request as the content change that justified it, so reviewers can see both.

The current `latest.json` is an agent-run `/ai-eval` kit (`20261018T191202Z`, Claude Code with Claude Opus 5.5),
scored with `--stands-in-for claude-code`. CI's `claude-code` runs are compared with it; the gate's detail labels the
comparison indicative, because agent-run and automated runs measure differently. Other subjects are reported as not
compared. A reviewed automated `claude-code` run committed with `aipg eval --update-baseline` would replace it as a
like-for-like baseline.
