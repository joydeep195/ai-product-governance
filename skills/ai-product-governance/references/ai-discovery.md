# AI discovery: find the AI before you govern it

**Goal:** list every AI use in a product, repository or portfolio, so the gates assess the AI that actually exists, and give an evidenced "No AI found" when there is none.
**Exit artifact:** AI inventory (`assets/templates/ai-inventory.md`).

Run discovery first when the user asks you to review a product or repository for AI governance, asks where the product uses AI, or wants the AI register (control GOV-01) filled in, and whenever nobody can say which AI uses exist.

"AI" here means any system that produces predictions, content, recommendations or decisions from a model, whether a foundation model behind an API or a model trained on data (for example a credit-scoring model built with XGBoost). Fixed rules written by people are not AI. List them only if the user asks, as "not AI".

## 1. Search with your own tools

Search with the file and search tools of the AI tool you are running in. If you can run Python, start with the bundled scan: `python scripts/ai_inventory.py <path> --format md`. It is read-only, makes no network calls, and prints names and locations, never secret values. It also lists what it does not cover. With or without the scan, check every row:

| Evidence | Where to look | Examples |
|---|---|---|
| AI packages in dependency manifests | `requirements*.txt`, `pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`, `pom.xml`, `build.gradle`, `*.csproj`, `Gemfile`, `composer.json` | `openai`, `anthropic`, `google-genai`, `langchain`, `llama-index`, `transformers`, `torch`, `scikit-learn`, `@ai-sdk/*`, Bedrock runtime clients |
| SDK imports | Source files, notebooks, scripts | `import openai`, `from langchain_openai import …`, `require("@anthropic-ai/sdk")` |
| Model endpoints | Configuration and source | `api.openai.com`, `*.openai.azure.com`, `bedrock-runtime`, `generativelanguage.googleapis.com`, `localhost:11434`, `/v1/chat/completions` behind an internal gateway |
| API-key variable names | `.env.example`, CI workflow secrets, deployment and infrastructure configuration | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `HF_TOKEN` |
| Prompts | `prompts/` folders, `*.prompt.md`, `*.prompty`, long instruction strings in code | A system prompt for a support assistant |
| Model files | Repositories, artifact stores | `*.onnx`, `*.safetensors`, `*.gguf`, `*.pt`, `*.joblib` |
| AI inside third-party products | Not in the code: ask the user | Auto-replies in the support desk, lead scoring in the CRM, meeting transcription, document processing |

Record variable names only. Never print, copy or quote a secret value, even when a file contains one.

## 2. Separate product AI from development tools

Coding-assistant configuration (`CLAUDE.md`, `AGENTS.md`, `.cursor/`, `.claude/`, GitHub Copilot instructions and prompt files) shapes how the product is built, not what it does. So do eval harnesses and test fixtures that call models. List them in the inventory's "Development and test use" table. They matter for code provenance and supply-chain review, but they are not a product AI use and do not go through the gates, unless the product ships them to its users.

## 3. Group the evidence into AI uses

An AI use is one capability that users or the business rely on (for example "support reply drafting"), not one SDK. Several packages and endpoints can serve one use, and one SDK can serve several. For each use, record:

- what it does;
- who uses it and who is affected by it;
- the model or provider, as the evidence shows it;
- the data it touches;
- where the evidence is (file and line);
- the owner (a role);
- its status (idea, pilot or production);
- its next gate.

Evidence you cannot tie to a use goes in "Evidence not yet tied to a use", with how it will be resolved. Anything you were not told goes in the Assumptions Ledger.

If the repository keeps use-case records in `.ai-governance/use-cases/`, compare them with what you found. A use with no record is unregistered. A record with no evidence has either been retired or lives elsewhere: ask which.

## 4. Record a clean "No AI found"

When the scan and your own search find nothing, say **No AI found**, and record:

- what you searched: paths, file counts and every row of the table in section 1;
- what you could not cover: the scan's `not_covered` list, plus anything else, such as repositories you were not given;
- the user's answers about AI inside third-party products.

A scan result of `"ai_found": false` alone is not "No AI found": the third-party question must be answered first. Do not choose a gate, classify a risk tier or recommend controls when there is no AI: there is nothing to govern. Say what would change the answer, such as adding an AI SDK or switching on an AI feature in a third-party product, and that the work then starts at Gate 0.

## 5. Route each AI use

- Give each AI use its own risk tier. Never classify a whole product with a single tier.
- A use that is only an idea starts at Gate 0.
- A use already live without governance artifacts starts at Gate 3: classify the tier and confirm the mandatory controls first, because the exposure already exists. Then gather Gate 2 eval evidence and set up Gate 5 monitoring.
- Register every use in the AI inventory with an accountable owner (GOV-01).

## Exit criteria

- [ ] Every row of the evidence table searched, with the scan or your own tools, and the paths covered stated.
- [ ] Product AI uses listed apart from development and test tools.
- [ ] Each AI use recorded with its evidence, owner role, status and next gate; unknowns in the Assumptions Ledger.
- [ ] What the search did not cover listed, with the questions asked of the user.
- [ ] If nothing was found: an explicit "No AI found" with what was searched and its limits, and no tier or controls.
