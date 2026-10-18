# ADR 0004: An MCP server for organisation-wide enforcement

- **Status:** Accepted
- **Date:** 2026-10-18

## Context

Skills are installed per user or per repository, so an organisation cannot easily guarantee that every assistant
applies the approved policy version. Some tools, and some plans, also cannot load skills but can connect to Model
Context Protocol (MCP) servers.

## Decision

Ship an MCP server (`aipg serve`, stdio and Streamable HTTP) that exposes:

- **Tools:** the instructions, playbooks, templates, the effective policy, the risk questionnaire, and the two
  deterministic engines.
- **Prompts:** one self-contained prompt per governance workflow.
- **Resources:** SKILL.md, every playbook and template, and the effective policy.

The policy is fixed when the server starts (`--policy`, `AIPG_POLICY` or the workspace) and is never selectable
through a tool argument. Every tool is annotated read-only and idempotent.

## Consequences

- One server deployment applies one approved policy to every connected assistant: Claude Desktop, VS Code and
  Copilot, Cursor, Gemini CLI, Codex, and ChatGPT connectors when hosted remotely.
- A prompt-injected model cannot redirect the server to arbitrary files or swap the policy.
- Remote deployment needs an authenticating gateway; the server does not implement authentication itself.
  *Update (2026-10-18):* the Streamable HTTP transport now requires a bearer token beyond loopback and can
  write an audit log of tool calls. TLS termination, per-user identity and rate limiting still belong to the
  gateway; see [`SECURITY.md`](../../SECURITY.md#running-the-mcp-server-as-a-shared-service).

## Alternatives considered

- **A REST API:** reachable by apps but not natively usable by AI assistants.
- **Policy as a tool argument:** convenient, but it lets the model choose its own rules.
