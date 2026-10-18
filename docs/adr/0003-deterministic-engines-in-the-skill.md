# ADR 0003: Deterministic engines live inside the skill, written for Python 3.9 standard library

- **Status:** Accepted
- **Date:** 2026-10-18

## Context

Two tasks must give the same answer every time: classifying risk tiers against a policy, and pricing a feature per
completed task. Language models do multi-step arithmetic and rule evaluation unreliably, and an auditor cannot
reproduce a model's mental arithmetic.

The engines must run wherever the skill runs: developer machines, CI, Claude's and ChatGPT's code-execution
sandboxes, and agents with no way to install packages.

## Decision

`scripts/risk_tier.py` and `scripts/unit_economics.py` ship inside the skill. They use only the Python standard
library, stay compatible with Python 3.9, produce ASCII-safe Markdown or JSON, and fail with clear messages and exit
codes. The Python package imports these exact files (`engines.py`) for the CLI, the MCP server and the tests, so
there is one implementation.

## Consequences

- Results are reproducible and testable; the unit economics are checked against hand calculations in the tests.
- The skill tells models to run the scripts and never estimate; where code execution is unavailable, the documented
  formulas are the fallback.
- A CI job runs the scripts on Python 3.9 so modern syntax cannot slip in.
- Bundled scripts carry no third-party dependencies, so features such as YAML policies are out of reach for them.

## Alternatives considered

- **Engines in the Python package only:** the skill would then depend on an installed package, which most skill
  hosts cannot provide.
- **Duplicated engines (script plus package):** two implementations would eventually disagree.
