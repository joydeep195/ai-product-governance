# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's **Report a vulnerability** button on the repository's
Security tab. Do not open a public issue. You will get an acknowledgement within five working days.

## Threat model

| Component | Exposure | Design controls |
|---|---|---|
| Bundled scripts (`risk_tier.py`, `unit_economics.py`) | Run by AI agents inside users' environments | Standard library only; no network access, no file writes, no shell; inputs validated strictly; unknown fields rejected |
| MCP server | Called by models that may be prompt-injected | Every tool is read-only and idempotent; the policy is fixed at start-up and cannot be chosen through a tool argument; playbook and template names are checked against an allow-list built from the bundle; anticipated errors return messages without stack traces |
| MCP server over Streamable HTTP | Network-reachable when deployed remotely | No built-in authentication: deploy behind a gateway that terminates TLS and authenticates users, and do not expose it to the internet directly |
| Eval harness (API subjects) | Executes model-chosen tool calls | File reads are confined to the skill directory; only two allow-listed scripts can run, with an argument list (no shell), a timeout and an empty working directory |
| Eval harness (`claude-code` subject) | Claude Code acts in a workspace with your login | A throwaway workspace per run; personal settings, plugins and hooks excluded; `dontAsk` permissions deny everything except Python (for the calculators) in the with-skill arm, and no tools at all in the baseline arm or the judge; API keys and host-session variables are stripped from the child environment |
| Eval harness (other agent CLIs) | Codex, Gemini CLI, Copilot CLI or Cursor act with your sign-in | A throwaway workspace per run with only the skill in it; Codex runs read-only with user config ignored; the other tools' own permission defaults apply, so review a profile before enabling it in CI |
| Manual eval kit | Text you paste from your AI tool | Parsed as data only (JSON extraction); nothing pasted is executed |
| Generated integrations | Copied into other repositories | Plain Markdown, JSON and TOML; contain no secrets |

## Supply chain

- Runtime dependencies are minimal (`mcp`, `jsonschema`, `pyyaml`); Dependabot keeps them and the GitHub Actions
  current.
- Eval API keys live in a protected GitHub environment and are never available to pull requests from forks.
- Releases are built in CI from a tagged commit after all checks pass. The build job has a read-only token; only
  the separate publish job can sign attestations and create the release.
- Every GitHub Action is pinned to a full commit SHA (with its version in a comment, which Dependabot updates), and
  checkouts do not keep the GitHub token in the local git config.
- Each release ships with a CycloneDX SBOM of the package and its runtime dependencies.

## Verifying a release

Every file attached to a GitHub release (wheel, sdist, skill zip) has a signed
[SLSA build provenance](https://slsa.dev/spec/v1.0/provenance) attestation and a signed SBOM attestation, created
by the release workflow through GitHub artifact attestations (Sigstore). With the [GitHub CLI](https://cli.github.com/):

```bash
gh attestation verify ai_product_governance-1.0.0-py3-none-any.whl --repo joydeep195/ai-product-governance
```

This proves the file was built by this repository's release workflow from the tagged commit and has not been
changed since. Add `--predicate-type https://cyclonedx.org/bom` to check the SBOM attestation instead of the
provenance. If verification fails, do not install the file, and report it as described above.
