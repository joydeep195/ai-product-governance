# Installing AI Product Governance

Install it in the AI tool you already use; one tool is enough. The skill follows the open
[Agent Skills](https://agentskills.io) standard, so the same folder works in every tool below.

## Option 1: one command, any coding tool (needs Node.js)

```bash
npx skills add joydeep195/ai-product-governance
```

The [skills CLI](https://github.com/vercel-labs/skills) asks which tools to install into and whether to install
for this project only or for all your projects. To skip the questions:

```bash
# For all your projects, in Codex:
npx skills add joydeep195/ai-product-governance -g -a codex -y

# For this project only, in GitHub Copilot:
npx skills add joydeep195/ai-product-governance -a github-copilot -y
```

Agent names: `claude-code`, `codex`, `cursor`, `github-copilot`, `gemini-cli`, `windsurf` (and many more).
Keep it current with `npx skills update`; remove it with `npx skills remove ai-product-governance`.

### If `npx` fails

- **The command is `npx skills add …`.** This project is not an npm package, so `npx ai-product-governance`
  fails with a 404. `skills` is the installer; the repository name is its argument.
- **Install Node.js and Git first.** The installer needs Node.js 18 or later (`node --version`) and clones the
  repository with Git (`git --version`).
- **Windows PowerShell says "running scripts is disabled".** Run `npx.cmd skills add joydeep195/ai-product-governance`
  instead, or allow local scripts once with `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
- **Windows reports a symlink or permission error.** Add `--copy` to copy files instead of linking them, or turn on
  Developer Mode in Windows settings.
- **A corporate proxy or firewall blocks the download.** Set `HTTPS_PROXY` (and `npm config set proxy`), or use
  Option 2 below, which needs no network tooling.

## Option 2: copy one folder (no tooling needed)

Download the repository (**Code → Download ZIP** on GitHub, or `git clone`), then copy the folder
`skills/ai-product-governance` into the location your tool reads:

| Tool | This project only | All your projects |
|---|---|---|
| Claude Code (terminal, desktop app, IDE extensions) | `.claude/skills/` | `~/.claude/skills/` |
| OpenAI Codex (CLI, IDE extension, app) | `.agents/skills/` | `~/.agents/skills/` |
| GitHub Copilot (VS Code, Copilot CLI, cloud agent) | `.github/skills/` or `.agents/skills/` | `~/.copilot/skills/` |
| Cursor | `.cursor/skills/` or `.agents/skills/` | `~/.cursor/skills/` |
| Gemini CLI | `.gemini/skills/` or `.agents/skills/` | `~/.gemini/skills/` |
| Windsurf | `.windsurf/skills/` | `~/.codeium/windsurf/skills/` |

- "This project only" paths are relative to your repository's root. `~` is your home folder (on Windows,
  `C:\Users\<you>`).
- Keep the folder name `ai-product-governance`: the standard requires it to match the skill's name.
- Restart the tool (or open a new session) so it picks up the new skill.

## Option 3: Claude Code plugin (with updates)

Inside Claude Code:

```text
/plugin marketplace add joydeep195/ai-product-governance
/plugin install ai-product-governance@aipg
```

Plugin skills are namespaced, so the slash command is `/ai-product-governance:ai-product-governance`.

## Tool-specific extras

- **GitHub Copilot:** the skill appears as `/ai-product-governance` in VS Code chat. For one slash command per
  workflow (`/ai-intake`, `/ai-prd`, `/ai-eval-plan`, `/ai-risk-review`, `/ai-launch-review`,
  `/ai-regression-review`, `/ai-model-decision`, `/ai-business-case`), also copy
  [`integrations/github-copilot/.github/prompts/`](../integrations/github-copilot/) into your repository's
  `.github/prompts/`.
- **Gemini CLI:** run `gemini skills list` to confirm it loaded.
- **Agents that read `AGENTS.md` but not skills:** copy the skill to `.agents/skills/` and paste
  [the AGENTS.md section](../integrations/agents-md/AGENTS.md) into your `AGENTS.md`.

## Check that it works

You don't need to call the skill by name; ask the kind of question it is for. For example:

> *"We want to use an LLM to validate phone numbers and postcodes on our signup form. Can you spec it?"*

With the skill active, the answer starts with a verdict (here: deterministic validation first, not an LLM) and
follows the gate structure. Another good test:

> *"Product wants an agent that issues refunds up to $500 with no human in the loop. Can you approve it?"*

Expect a high risk tier, autonomy capped at "act with approval" for launch, and a list of required controls.

## Optional add-ons

| Add-on | What it gives you | How |
|---|---|---|
| Python 3.9+ | Exact numbers from the risk-tier and unit-economics calculators (no packages needed). Without Python, the assistant applies the documented formulas and shows its working | Usually already installed; the skill runs `python scripts/...` |
| Your organisation's policy | Your own risk tiers, controls and approvers | Put `.ai-governance/policy.json` in the repository ([policy guide](policy.md)) |
| MCP server | The calculators and playbooks as tools in any MCP client, with one policy enforced centrally | Configs for each tool in [`integrations/mcp/`](../integrations/mcp/) (needs [uv](https://docs.astral.sh/uv/)) |

## Chat apps (not coding tools)

- **ChatGPT Business, Enterprise or Edu, and Claude apps:** upload the skill as a zip (zip the
  `skills/ai-product-governance` folder, or use the zip attached to a release; each release file is signed, and
  [SECURITY.md](../SECURITY.md#verifying-a-release) shows how to verify it).
- **Custom GPTs, ChatGPT or Claude Projects, Gemini Gems, Microsoft 365 Copilot agents:** use the
  [prompt pack](../integrations/prompt-pack/): instructions plus knowledge files.
