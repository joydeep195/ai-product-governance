# Changelog

All notable changes are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/). The package, the skill (`metadata.version`) and the
Claude plugin manifest always share one version; `aipg validate` enforces it.

## [Unreleased]

## [1.1.0] - 2026-11-10

The default policy moves to 2.0.0 and the financial-services example to 3.0.0: both add questions, so answer files
written for earlier versions come back as incomplete until the new questions are answered (see Changed).

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

- **AI discovery.** Before governing AI, find it. The new playbook `references/ai-discovery.md` and template
  `assets/templates/ai-inventory.md` walk the agent through an inventory with its own file and search tools:
  dependency manifests, SDK imports, model endpoints, API-key variable names, prompts, model files and AI inside
  third-party products. Product AI is listed apart from coding assistants and eval harnesses. When nothing is
  found, the result is an evidenced "No AI found" with what was searched and not covered, and no tier. A new
  `ai-inventory` workflow (MCP prompt and Copilot prompt file) and SKILL.md route start it.
- `scripts/ai_inventory.py` (standard library, Python 3.9+) gives discovery a deterministic starting point. It is
  read-only, makes no network calls, follows no symbolic links, skips dependency and build folders, and prints
  names and locations, never secret values. It is not exposed over MCP, because the server never reads the user's
  files.
- **Incomplete questionnaires lead with "Incomplete".** When questions are unanswered, `risk_tier.py` returns
  `"status": "incomplete"` and a headline such as `Incomplete (provisional Minimal; could rise to Prohibited)`,
  lists the unanswered questions first, and still exits 0. `--strict` (and `aipg tier --strict`) exits 4 instead,
  for CI. A new operating rule tells the agent to ask the questions or log assumptions before presenting a tier.
- **Controls can be ruled out.** A control's optional `applies_when` condition and `not_applicable_reason` let the
  policy say when a control does not apply. Results list such controls under "Not applicable" with the reason,
  rather than dropping them; unanswered questions keep them required. The default and bank policies rule out
  fairness evaluation (`EVAL-03`) and explanation and contestability (`TRN-02`) when no person is the subject of
  the output and it influences no decisions about people, using the new question `outputs_concern_people`.
  `aipg check` does not require records to close controls the answers rule out.
- **Sources and last-verified dates.** A policy's optional `frameworks` list gives each framework cited in control
  mappings its official source URL and the date a maintainer last confirmed it was current. Results list the
  sources behind the required controls, and the skill states regulatory facts "as of" that date and never presents
  its memory of a law as current fact. Every Gate 3 regulatory flag now names its source and last-verified date
  (10 November 2026), including SR 26-2 and OCC Bulletin 2026-13, which replaced SR 11-7 and OCC Bulletin
  2011-12, and Regulation (EU) 2026/1744, which amended the EU AI Act. `aipg validate` warns when controls map to
  frameworks but the policy has no `frameworks` list.
- `aipg validate` warns about conditional controls that can never add anything, because whenever their condition
  holds, a rule sets a tier that already requires the control. The check proves each implication from the
  conditions, so it never warns falsely.
- Four eval scenarios: a product with no AI (`cross-no-ai-product`), over-governance of a minimal internal tool
  (`g3-minimal-internal-tool`), a regulated process with low impact (`g3-regulated-low-impact`), and an Indian
  lending fintech asking what laws the policy does not cover require (`g3-india-lending-flag-not-rule`). The suite
  has 14 scenarios, and the docs recommend three trials (`/ai-eval --trials 3`).
- `docs/roadmap.md` lists planned work that this release does not include.
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
- The financial-services example policy adds adverse action reasons (`TRN-03`), a third-party dependency
  and exit plan (`TPR-01`), complaint monitoring (`OPS-06`) and communications record-keeping (`OPS-07`), each
  applied by the questionnaire answers that call for it; an `external_model_dependency` question; and a compliance
  officer approver for the high tier.
- Regulatory crosswalk: a control can list the framework requirements it addresses in an optional `mappings`
  array (`framework`, `reference`, optional `note`). The default policy maps every control to the EU AI
  Act, NIST AI RMF 1.0 subcategories and ISO/IEC 42001 Annex A, plus GDPR and the OWASP Top 10 for LLM
  Applications where relevant. The financial-services example adds SR 26-2 (which replaced SR 11-7),
  DORA, ECOA and Regulation B, FCRA, SEC Rule 17a-4, FINRA rules, MiFID II and the FCA Consumer Duty.
  `risk_tier.py` returns the mappings with each required control and adds a "Maps to" column to its Markdown
  output. The mappings are informative, not legal advice. The Gate 3 playbook and the risk-assessment template's
  control plan now cite each control's mappings, and the playbook names SR 26-2 in place of SR 11-7.
- First published eval baseline, `evals/baselines/latest.json`: an agent-run `/ai-eval` on Claude Code (Claude
  Opus 5.5), 10 scenarios × 2 arms × 1 trial. With the skill it scored 1.00 (100% pass, 0 critical failures);
  without it, 0.92 (90% pass, 1 critical failure), a delta of +0.08. All gates pass. The README's new Results section
  gives per-scenario scores and caveats. It stands in for the `claude-code` subject, so CI's regression gate
  compares `claude-code` runs against it, labelled indicative.
- `aipg eval-kit score --update-baseline` saves a scored kit as `evals/baselines/latest.json`, as
  `aipg eval --update-baseline` does for automated runs; both now copy `results.json` byte for byte.
- `aipg eval-kit score --stands-in-for <subject id>` lets a kit's results serve as the baseline for a configured
  automated subject, such as an `/ai-eval` in Claude Code standing in for `claude-code`. The kit keeps its tool
  label as its subject id, and the regression gate's detail names it and keeps the agent-run "indicative" label.
  `docs/evaluation.md` explains why agent-run and automated runs measure differently and how to read a drop.
- `results.json` records how each subject was produced (`subjects`: id, provider, model, effort, and for kits
  `indicative` and `stands_in_for`), so a baseline copied from it describes itself.

### Changed

- `regulated_advice` is split. It now asks only about regulated advice to people (medical, legal, financial or tax;
  high risk). The new question `inside_regulated_process` asks whether the system runs inside a regulated process,
  such as KYC, anti-money-laundering or fraud monitoring, complaints, claims or regulatory reporting, and rule `L-07`
  makes that limited risk; other rules decide whether it is high. A question's new `split_from` field makes the
  result explain the split when an answer file has the old question but not the new one, so old answers are
  re-checked rather than silently reused.
- Default policy 2.0.0 and financial-services example 3.0.0: the new questions `outputs_concern_people` and
  `inside_regulated_process`, rule `L-07`, `applies_when` on `EVAL-03` and `TRN-02`, and a `frameworks` list. The
  conditional controls `PRV-01`, `PRV-03` and `TRN-01` are removed because the tiers already require them; results
  are unchanged. The example use-case record is re-certified against 3.0.0.
- The eval regression gate compares the mean over the scenarios both runs share, using the baseline's
  per-scenario scores. New scenarios are listed as not compared and missing ones as not run, so adding a hard
  scenario cannot fail the gate and dropping one cannot pass it. Baselines without per-scenario scores fall back to
  the overall means, and the gate says so.
- Gate 1 and the business case template count the set-up and running cost of the risk tier's mandatory controls in
  `one_time_cost` and `fixed_monthly_cost`.

### Fixed

- `aipg eval --compare` no longer skips the regression gate silently when no baseline subject matches. The plan
  shows a `regression check:` line per subject before any model call. After the run, the console prints a warning,
  `report.md` marks the gate `skipped` (with the verdict `PASS (n skipped)`) and `junit.xml` writes a `<skipped>`
  test case. A skipped gate never fails the run. An unreadable baseline now stops the run with exit code 2 before
  any model call, instead of failing after the run has been paid for.
- CI's Python 3.9 compatibility job runs on `ubuntu-24.04`: `ubuntu-latest` moved to Ubuntu 26.04, which has no
  Python 3.9 build, so the job failed to set up Python.

### Documentation

- The README opens with the install command; the installation guide covers common `npx` failures.
- The README no longer hard-codes the number of tests, and its sample risk-tier output matches policy 2.0.0.

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
