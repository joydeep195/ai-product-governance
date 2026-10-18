# Contributing

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

## The single-source rule

`skills/ai-product-governance/` is the only place governance content lives. Everything else is derived from it:

| You change | Then |
|---|---|
| `SKILL.md`, a playbook, a template, the policy or a script | Run `aipg build` and commit the regenerated `integrations/` |
| Gates or workflows (`src/ai_product_governance/workflows.py`) | Keep SKILL.md's lifecycle table in step (`aipg validate` checks it) |
| Anything a model reads | Add or update an eval scenario in `evals/scenarios/` |

Never edit files under `integrations/` by hand; CI rejects drift.

## Checks to run before a pull request

```bash
ruff check . && ruff format --check .
mypy
aipg validate --strict
aipg build --check
python -m pytest
```

Model evals cost money and are not part of the default checks. Run them when you change content a model reads:

```bash
aipg eval --dry-run                      # plan and rough cost, no API calls
aipg eval --trials 1 --max-cost-usd 5    # quick signal
```

See [docs/evaluation.md](docs/evaluation.md) for the methodology.

## Writing governance content

- Write for the model first: imperative, specific, testable. Prefer a decision rule over a principle.
- Keep `SKILL.md` a router: under 500 lines and roughly 5,000 tokens. Put depth in `references/`, one level deep.
- Every number a model must compute belongs in a script, not in prose arithmetic.
- Cite frameworks and regulations by name only where they help a reviewer route the question; never state legal
  conclusions.

## Changing the policy

The default policy is a reference, not legal advice. Higher tiers must stay at least as strict as lower ones
(`aipg validate` warns otherwise), and every example policy in `examples/` must keep validating.

## Releases

1. Bump the version in `src/ai_product_governance/__init__.py`, `SKILL.md` (`metadata.version`) and
   `.claude-plugin/plugin.json`; update `CHANGELOG.md`.
2. Merge to `main`, then tag `vX.Y.Z`. The release workflow verifies the versions, runs the checks and publishes
   the wheel, the sdist and the skill zip to a GitHub release.
