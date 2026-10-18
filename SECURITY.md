# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's **Report a vulnerability** button on the repository's
Security tab. Do not open a public issue. You will get an acknowledgement within five working days.

## Threat model

| Component | Exposure | Design controls |
|---|---|---|
| Bundled scripts (`risk_tier.py`, `unit_economics.py`) | Run by AI agents inside users' environments | Standard library only; no network access, no file writes, no shell; inputs validated strictly; unknown fields rejected |
| MCP server | Called by models that may be prompt-injected | Every tool is read-only and idempotent; the policy is fixed at start-up and cannot be chosen through a tool argument; playbook and template names are checked against an allow-list built from the bundle; anticipated errors return messages without stack traces |
| MCP server over Streamable HTTP | Network-reachable when deployed remotely | A bearer token (`AIPG_SERVER_TOKEN` or `--token-file`, at least 32 characters) checked by the MCP SDK's auth middleware with a constant-time comparison; the server refuses to start on any host other than `127.0.0.1`, `localhost` or `::1` without one; plain HTTP only, so TLS must be terminated in front of it |
| MCP audit log (`--audit-log`) | Read by auditors and SIEM pipelines | One JSON line per tool call with a hash of the arguments, never the arguments or the token; appended under a lock; fails closed, so a call whose line cannot be written returns an error, not a result |
| Eval harness (API subjects) | Executes model-chosen tool calls | File reads are confined to the skill directory; only two allow-listed scripts can run, with an argument list (no shell), a timeout and an empty working directory |
| Eval harness (`claude-code` subject) | Claude Code acts in a workspace with your login | A throwaway workspace per run; personal settings, plugins and hooks excluded; `dontAsk` permissions deny everything except Python (for the calculators) in the with-skill arm, and no tools at all in the baseline arm or the judge; API keys and host-session variables are stripped from the child environment |
| Eval harness (other agent CLIs) | Codex, Gemini CLI, Copilot CLI or Cursor act with your sign-in | A throwaway workspace per run with only the skill in it; Codex runs read-only with user config ignored; the other tools' own permission defaults apply, so review a profile before enabling it in CI |
| Manual eval kit | Text you paste from your AI tool | Parsed as data only (JSON extraction); nothing pasted is executed |
| Generated integrations | Copied into other repositories | Plain Markdown, JSON and TOML; contain no secrets |

## Running the MCP server as a shared service

The server authenticates callers and keeps an audit trail; the rest of a safe deployment comes from the
environment around it. Before it serves an organisation:

- **Generate a strong token** with `python -c "import secrets; print(secrets.token_urlsafe(32))"`, keep it in
  your secret store, and pass it through `AIPG_SERVER_TOKEN` or a `--token-file` that only the service account
  can read. The server never logs it, and error messages do not echo it.
- **Terminate TLS in front of the server.** It speaks plain HTTP, so a token sent across a network without TLS
  can be read in transit. Bind the server to `127.0.0.1` behind a reverse proxy on the same machine, or to a
  private interface reachable only from your gateway. On loopback the SDK's DNS-rebinding protection accepts
  only a `Host` header of `127.0.0.1`, `localhost` or `[::1]`, so the proxy must send one of those.
- **Know what a shared token proves.** Every holder of the token is the same principal (`shared-token` in the
  audit log). `client.name` and `client.version` are self-reported by the client. For per-user identity, put an
  authenticating gateway (SSO) in front and correlate its logs with the audit log by time and address.
- **Rotate by restarting.** The server reads the token at start-up and accepts exactly one, so rotation means
  distributing the new token and restarting the server; plan a short window in which clients reconnect.
- **Protect the audit log.** Write it to a location the service account can append to and other users cannot
  modify, ship it to your SIEM or immutable storage, and give each server process its own file. The log
  reopens the file for every line, so external rotation by renaming works. A call fails if its line cannot be
  written, so monitor free disk space.
- **Mind what the server does not do.** It has no rate limiting, and it audits tool calls only, not prompt and
  resource reads, which return the same playbooks, templates and policy the tools do. Requests rejected for a
  missing or wrong token never reach a tool, so they appear in the server's access log on stderr (status
  `401`, with the peer address) rather than in the audit log; collect both. Apply rate limits at the gateway.

## Supply chain

- Runtime dependencies are minimal (`mcp`, `jsonschema`, `pyyaml`); Dependabot keeps them and the GitHub Actions
  current.
- Eval API keys live in a protected GitHub environment and are never available to pull requests from forks.
- Releases are built in CI from a tagged commit after all checks pass.
