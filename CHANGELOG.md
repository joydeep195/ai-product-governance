# Changelog

All notable changes are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/). The package, the skill (`metadata.version`) and the
Claude plugin manifest always share one version; `aipg validate` enforces it.

## [Unreleased]

### Security

- Agent CLI evals no longer pass a prompt as an argument to a Windows `.cmd` or `.bat` shim, where `cmd.exe` could
  run quotes and `&` in the prompt (which includes model output when judging) as commands.

### Added

- The financial-services example policy (2.4.0) adds adverse action reasons (`TRN-03`), a third-party dependency
  and exit plan (`TPR-01`), complaint monitoring (`OPS-06`) and communications record-keeping (`OPS-07`), each
  applied by the questionnaire answers that call for it; an `external_model_dependency` question; and a compliance
  officer approver for the high tier.

### Documentation

- The README opens with the install command; the installation guide covers common `npx` failures.

## [1.0.0] - 2026-10-18

### Added

- `ai-product-governance` Agent Skill following the open Agent Skills specification: eight operating rules, a
  six-gate lifecycle router (intake and fit, value and economics, quality and evals, risk and controls, launch
  readiness, operate and improve), seven playbooks, a glossary and eight artifact templates.
- Policy-as-code: a JSON governance policy with a JSON Schema covering risk tiers, classification rules,
  conditional controls, a 24-control catalogue, approvers, eval minimums, autonomy caps and incident severities.
  Organisations override it with `.ai-governance/policy.json`.
- Deterministic engines bundled in the skill (Python 3.9+, standard library only): `risk_tier.py` and
  `unit_economics.py`.
- MCP server (`aipg serve`, stdio and Streamable HTTP) with seven read-only tools, eight workflow prompts and
  resources; the policy is fixed at start-up.
- Generated integrations for tools without native skill support: a prompt pack (custom GPTs, Projects, Gemini
  Gems, Microsoft 365 Copilot agents, any API), GitHub Copilot prompt files, an `AGENTS.md` section and MCP client
  configurations. `aipg build --check` fails on drift.
- Model-agnostic eval harness (`aipg eval`): ten scenarios across every gate, a provider-neutral skill-host
  emulator, a blind rubric judge, deterministic checks, skill-adherence tracking, cost ceilings, quality gates,
  regression comparison and JSON/Markdown/JUnit reports.
- Tool independence (ADR 0007): every feature works with any single AI tool. `aipg eval` detects the one AI access
  the user has (Claude Code, Codex, Gemini CLI, Copilot CLI or Cursor sign-in; an Anthropic, OpenAI or Gemini API
  key; or a local Ollama/LM Studio model) and uses it both to answer and to grade. `--all` builds an optional
  cross-tool scorecard.
- Declarative agent CLI profiles for Codex, Gemini CLI, Copilot CLI and Cursor CLI (unverified until run against
  the real tools); adding a tool means adding a profile.
- `aipg eval-kit`: a copy-and-paste eval kit for chat-only tools (ChatGPT, Gemini, Microsoft 365 Copilot, Claude
  apps) with blind, shuffled grading prompts and offline scoring into the standard reports.
- `claude-code` eval subject and judge: run the evals on a Claude subscription through Claude Code's headless mode,
  with no API key. The skill is installed as a real project skill, so reports show whether Claude activated it.
  The model and effort default to Claude Opus 5.5 at `max` and can be overridden per run (`--model`, `--effort`).
  By default each tool grades its own answers blind; `judge.use` selects an independent grader.
- Claude Code plugin and marketplace manifests; `aipg package` builds a reproducible skill zip for skill hosts.
- CI across Python 3.11-3.14 on Linux, Windows and macOS, a Python 3.9 job for the bundled scripts, wheel smoke
  tests, scheduled and on-demand evals, and tag-driven releases.
