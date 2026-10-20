# Changelog

All notable changes are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/). The package, the skill (`metadata.version`) and the
Claude plugin manifest always share one version; `aipg validate` enforces it.

## [Unreleased]

### Security

- The MCP server's Streamable HTTP transport can require a bearer token, read from `AIPG_SERVER_TOKEN` or
  `--token-file` and checked in constant time by the MCP SDK's auth middleware. Without a token, `aipg serve`
  refuses to listen on any host other than `127.0.0.1`, `localhost` or `::1`. The stdio transport is unchanged.
- `aipg serve --audit-log PATH` appends one JSON line per tool call: UTC timestamp, tool, outcome, policy id and
  version, a SHA-256 hash of the arguments, the tier from `classify_risk_tier`, and the caller as the transport
  reports it. Tokens and arguments are never written, and a call whose line cannot be written fails.
- Agent CLI evals no longer pass a prompt as an argument to a Windows `.cmd` or `.bat` shim, where `cmd.exe` could
  run quotes and `&` in the prompt (which includes model output when judging) as commands.
- Every release file gets a signed SLSA build provenance attestation and a signed CycloneDX SBOM attestation, and
  the SBOM is attached to the release; `gh attestation verify` checks them (see SECURITY.md).
- The release workflow builds with a read-only token in one job and signs and publishes in another.
- Every GitHub Action is pinned to a full commit SHA, checkouts no longer keep the GitHub token, and the Claude Code
  CLI installed by the evals workflow is pinned to a version.

### Added

- `/ai-eval` evaluates the skill inside the AI tool the user already works in, with no sign-in, CLI or API key.
  The agent follows the skill's new `references/evaluate-this-skill.md`: it runs
  `aipg eval-kit create --agent-run`, starts a fresh sub-agent for every answer and blind grading, and scores the
  kit. Agent-run kits write one self-contained task file per sub-agent (`prompts/`, `grading/`) that says what it
  may use and where to save its reply, so the agent only sends one line per sub-agent. Their reports are labelled
  as agent-run, indicative rather than audited evidence. Available as an MCP prompt, a Copilot prompt file and a
  SKILL.md route.
- Use-case records make the controls enforceable. `.ai-governance/use-cases/<id>.json` (schema:
  `assets/policy/use-case.schema.json`) records a use case's answers, tier, policy version, each control's status
  and evidence, approver sign-offs and re-certification dates. `aipg record new` classifies answers against the
  effective policy and writes a record with every required control open. `aipg check` re-classifies each record and
  exits 1 when the tier is stale, a required control is not done with evidence or waived with an approver, an
  approver has not signed, re-certification has lapsed or the policy version changed; `--format md` renders a
  pull-request comment. `aipg validate` checks example records, and the financial-services example includes a
  complete one. The policy guide shows how to run the check in CI.
- The financial-services example policy (2.4.0) adds adverse action reasons (`TRN-03`), a third-party dependency
  and exit plan (`TPR-01`), complaint monitoring (`OPS-06`) and communications record-keeping (`OPS-07`), each
  applied by the questionnaire answers that call for it; an `external_model_dependency` question; and a compliance
  officer approver for the high tier.
- Regulatory crosswalk: a control can list the framework requirements it addresses in an optional `mappings`
  array (`framework`, `reference`, optional `note`). The default policy (1.1.0) maps every control to the EU AI
  Act, NIST AI RMF 1.0 subcategories and ISO/IEC 42001 Annex A, plus GDPR and the OWASP Top 10 for LLM
  Applications where relevant. The financial-services example (2.5.0) adds SR 26-2 (which replaced SR 11-7),
  DORA, ECOA and Regulation B, FCRA, SEC Rule 17a-4, FINRA rules, MiFID II and the FCA Consumer Duty.
  `risk_tier.py` returns the mappings with each required control and adds a "Maps to" column to its Markdown
  output. The mappings are informative, not legal advice.
- First published eval baseline, `evals/baselines/latest.json`: an agent-run `/ai-eval` on Claude Code (Claude
  Opus 5.5), 10 scenarios × 2 arms × 1 trial. With the skill it scored 1.00 (100% pass, 0 critical failures);
  without it, 0.92 (90% pass, 1 critical failure), a delta of +0.08. All gates pass. The README's new Results section
  gives per-scenario scores and caveats. CI's regression gate does not use this baseline yet, because the gate
  matches by subject id and agent-run results are labelled with the tool name.

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
