# Architecture

## Design goals

1. **One governance method, every AI tool, and one tool is enough.** The same rules, gates, policy and
   calculations whether someone works in ChatGPT, GitHub Copilot, Claude, Cursor, Gemini or a custom app, with no
   feature requiring a second tool, a second sign-in or an API key.
2. **Standards first.** Build on open standards (Agent Skills, MCP, JSON Schema) rather than any one vendor's
   format, so portability is the default and adapters are the exception.
3. **Judgement in prose, arithmetic in code.** Models handle reasoning and writing; deterministic engines handle
   anything that must be repeatable or auditable.
4. **Configurable without forking.** Organisations change tiers, rules, controls and approvers in a policy file,
   not in code or prompts.
5. **Measured, not asserted.** Behavioural quality is evaluated across models and gated in CI.

## Components

```mermaid
flowchart LR
    subgraph source["Single source of truth: skills/ai-product-governance/"]
        skill["SKILL.md<br/>rules and gate router"]
        refs["references/<br/>gate playbooks"]
        tmpl["assets/templates/<br/>artifact templates"]
        policy["assets/policy/<br/>policy + JSON Schema"]
        engines["scripts/<br/>risk_tier.py, unit_economics.py"]
    end

    subgraph toolkit["Python package: ai_product_governance"]
        build["aipg build<br/>adapter generator"]
        server["aipg serve<br/>MCP server"]
        evals["aipg eval<br/>model-agnostic evals"]
        validate["aipg validate<br/>spec, schema, links, versions"]
    end

    org[".ai-governance/policy.json<br/>organisation override"]

    source --> native["Agent Skills hosts:<br/>Claude, ChatGPT, Codex, Copilot,<br/>Cursor, Gemini CLI and others"]
    source --> build --> generated["integrations/:<br/>prompt pack, Copilot prompts,<br/>AGENTS.md, MCP configs"]
    source --> server --> mcpclients["MCP clients:<br/>Claude Desktop, VS Code, Cursor,<br/>Gemini CLI, Codex, ChatGPT connectors"]
    source --> evals
    source --> validate
    org -. overrides .-> engines
    org -. overrides .-> server
```

| Component | Responsibility | Key decisions |
|---|---|---|
| Skill (`skills/ai-product-governance/`) | The governance method: rules, routing, playbooks, templates, policy, engines | [ADR 0001](adr/0001-agent-skills-as-canonical-source.md), [ADR 0003](adr/0003-deterministic-engines-in-the-skill.md) |
| Policy (`assets/policy/`) | Tiers, rules, controls, approvers, eval minimums as validated data | [ADR 0002](adr/0002-policy-as-code.md) |
| Adapter generator (`adapters.py`) | Renders tool-specific integrations; CI rejects drift | [ADR 0006](adr/0006-generated-integrations.md) |
| MCP server (`mcp_server.py`, `audit.py`) | Read-only tools, prompts and resources; central policy enforcement; bearer-token auth and an audit log for shared use | [ADR 0004](adr/0004-mcp-for-central-enforcement.md) |
| Eval harness (`evals/`) | Same scenarios with and without the skill, on whichever single AI tool the user has | [ADR 0005](adr/0005-model-agnostic-evals.md), [ADR 0007](adr/0007-one-tool-is-enough.md) |
| Validator (`validate.py`) | Agent Skills spec, schema, links, version consistency, size budgets | — |

## How a request flows (skill-native tools)

```mermaid
sequenceDiagram
    actor User
    participant Host as AI tool (skill host)
    participant Skill as SKILL.md
    participant Ref as references/gate-N
    participant Engine as scripts/*.py
    participant Policy as policy.json

    User->>Host: "Can we launch our claims-triage assistant on Monday?"
    Host->>Skill: description matches, so load SKILL.md (about 2k tokens)
    Skill-->>Host: rules + router: this is Gate 4
    Host->>Ref: read gate-4-launch-readiness.md only
    Host->>Engine: risk_tier.py --answers-json {...}
    Engine->>Policy: workspace override, else bundled default
    Engine-->>Host: tier high, required controls, approvers, eval minimums
    Host-->>User: Verdict No-go, blocking gaps, shortest path to Go, Assumptions Ledger
```

Progressive disclosure keeps context small: about 100 tokens of metadata always, the SKILL.md body only when the
skill activates, and one playbook per gate on demand.

## The MCP server as a shared service

ADR 0004 makes the MCP server the central enforcement point: one deployment, one fixed policy, every assistant
connected to it. Over Streamable HTTP, each request passes three layers before a result leaves the server.

```mermaid
flowchart LR
    clients["Assistants:<br/>Claude, VS Code, Cursor,<br/>Gemini CLI, Codex"] -->|HTTPS| gateway["Gateway or reverse proxy<br/>TLS, optional SSO, rate limits"]
    gateway -->|"HTTP with Authorization: Bearer"| auth
    subgraph serve["aipg serve --transport streamable-http"]
        auth["SDK bearer-auth middleware<br/>StaticTokenVerifier"] --> audit["AuditMiddleware<br/>one line per tools/call"] --> tools["Read-only tools<br/>policy fixed at start-up"]
    end
    audit --> log[("audit.jsonl")]
```

| Layer | Behaviour |
|---|---|
| Start-up checks (`serve`) | Reads the token from `--token-file` or `AIPG_SERVER_TOKEN` and rejects one shorter than 32 characters. Without a token the server listens only on `127.0.0.1`, `localhost` or `::1`, the hosts on which the SDK enables DNS-rebinding protection; any other `--host` stops start-up with an error |
| Authentication | The MCP SDK's own bearer-auth middleware, given a `TokenVerifier` that compares SHA-256 digests with `hmac.compare_digest`. Requests without the token get `401` and never reach a session |
| Audit | An SDK server middleware around every `tools/call`. It hashes the arguments, records the outcome, the tier for `classify_risk_tier`, the policy id and version, and the caller as the transport reports it, then appends one JSON line under a lock. If the line cannot be written, the client gets an error instead of the result |
| Tools | Unchanged: read-only, idempotent, with the policy fixed at start-up |

The stdio transport is unchanged: it serves only the process that launched it, so it takes no token, though
`--audit-log` works there too. The record format is documented in
[`integrations/mcp/README.md`](../integrations/mcp/README.md#audit-log) and the deployment checklist in
[`SECURITY.md`](../SECURITY.md#running-the-mcp-server-as-a-shared-service).

## Repository layout

```text
skills/ai-product-governance/   canonical skill (the product)
  SKILL.md                      rules, lifecycle router, output standards
  references/                   gate playbooks, approach and model selection, glossary
  assets/templates/             eight artifact templates
  assets/policy/                default policy and JSON Schema
  scripts/                      deterministic engines (Python 3.9+, stdlib only)
src/ai_product_governance/      toolkit: CLI, MCP server, adapters, validator, evals
integrations/                   generated adapters (do not edit)
evals/                          eval config, scenarios, baselines
examples/                       example organisation policy and inputs
docs/                           architecture, evaluation, policy guide, ADRs
.claude-plugin/                 Claude Code plugin and marketplace manifests
.github/                        CI, evals, release, Dependabot, templates
```

## Quality gates

| Gate | Where | Catches |
|---|---|---|
| `ruff check`, `ruff format --check`, `mypy --strict` | CI | Code defects, style drift, type errors |
| `aipg validate --strict` | CI | Spec violations, broken links, invalid policies, version mismatch, oversize prompt pack |
| `aipg build --check` | CI | Generated integrations out of step with the skill |
| `pytest` on 3 OSes and Python 3.11-3.14 | CI | Engine, server, adapter and harness regressions |
| Bundled scripts on Python 3.9 | CI | Code-interpreter compatibility |
| Wheel smoke test | CI | Packaging mistakes (for example a skill missing from the wheel) |
| `aipg eval` with gates and baseline comparison | Scheduled, manual, or `run-evals` label | Behavioural regressions across models |
