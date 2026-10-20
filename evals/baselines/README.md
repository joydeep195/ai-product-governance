# Eval baselines

`latest.json` is the reviewed `results.json` of the last accepted eval run. CI compares new runs against it and
fails when the with-skill score drops by more than `gates.max_regression` (see `../eval.config.json`).

Create or refresh it after a run you have reviewed:

```bash
aipg eval --update-baseline
```

Commit the change in the same pull request as the content change that justified it, so reviewers can see both.

The current `latest.json` is an agent-run `/ai-eval` kit (`20261018T191202Z`, Claude Code with Claude Opus 5.5).
`aipg eval-kit` has no `--update-baseline`, so the kit's `report/results.json` was copied here unchanged. Its
subject id is the tool name, which CI's automated subjects do not match, so the regression gate skips it for now.
