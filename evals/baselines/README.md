# Eval baselines

`latest.json` is the reviewed `results.json` of the last accepted eval run. CI compares new runs against it and
fails when the with-skill score drops by more than `gates.max_regression` (see `../eval.config.json`).

Create or refresh it after a run you have reviewed:

```bash
aipg eval --update-baseline
```

Commit the change in the same pull request as the content change that justified it, so reviewers can see both.
