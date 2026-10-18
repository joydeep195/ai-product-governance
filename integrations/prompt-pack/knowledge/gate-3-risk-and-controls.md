# Gate 3 — Risk tier and controls

**Goal:** classify the risk tier against the policy, identify specific risks, and commit to controls proportionate to that tier.
**Exit artifact:** risk assessment (`assets/templates/risk-assessment.md`).

## 1. Classify the risk tier

Answer the policy questionnaire (`python scripts/risk_tier.py --questions`), then run the calculator on the answers. The tier is the highest tier triggered by any rule. A prohibited trigger stops the work. Unanswered questions are reported, because answering them can only raise the tier.

The default tiers, summarised (the policy file is authoritative):

| Tier | Typical profile | Example |
|---|---|---|
| Minimal | Internal and assistive; no personal data beyond business contact details | Summariser for internal engineering documents |
| Limited | Customer-facing or externally published output, personal data, data sent to an external model provider, or actions that are hard to reverse | Support-reply drafts that agents send to customers |
| High | Influences decisions about people's access to jobs, credit, insurance, housing, education, healthcare or essential services; sensitive data; regulated advice; children or vulnerable users; high-value or autonomous actions affecting customers | CV screening; claims triage; an agent that issues refunds without approval |
| Prohibited | Practices the organisation forbids outright, such as manipulative techniques, exploiting vulnerabilities, social scoring or emotion recognition of employees | — |

The default tiers are informed by the risk categories of the EU AI Act and the NIST AI Risk Management Framework, but they are **not** a legal classification. Legal and compliance teams decide regulatory status.

## 2. Build the risk register

For every risk, record: description, likelihood (1–5), impact (1–5), detectability (how quickly would we know?), controls, residual rating and owner (a role). Check every category below and write `N/A — <reason>` for any that do not apply.

| Category | Risks to consider |
|---|---|
| Output quality | Fabricated facts or citations; omissions; outdated knowledge; inconsistent answers to the same question |
| Security | Direct prompt injection; indirect injection through documents, web pages, emails or tool results; data exfiltration through tools or rendered links; unsafe handling of model output (rendered as HTML, executed as code or SQL); excessive agency (tools with broader permissions than the task needs) |
| Privacy and data | Personal data in prompts and logs; leakage between users or tenants through retrieval or memory; vendor retention and training terms; data residency |
| Fairness | Quality gaps across languages, dialects, demographics or customer segments |
| User harm | Over-reliance (automation bias); unsafe advice; manipulation; users not realising they are dealing with AI |
| Operational | Vendor outage; model deprecation or a silent behaviour change; cost spikes; rate limits; latency degradation |
| Legal and IP | Regulated advice (legal, medical, financial); copyright in outputs; commitments the AI makes on the organisation's behalf; sector rules |
| Reputational | Offensive or off-brand output that ends up in a screenshot |

## 3. Set the autonomy level

| Level | Name | The AI… | The human… |
|---|---|---|---|
| L0 | Inform | Surfaces information | Decides everything |
| L1 | Suggest | Proposes options | Chooses |
| L2 | Draft | Produces a complete draft | Reviews, edits and sends |
| L3 | Act with approval | Prepares an action | Approves each action before it runs |
| L4 | Act and report | Acts, then reports, with an undo window | Monitors and can reverse |
| L5 | Autonomous | Acts without review of individual actions | Audits samples and metrics |

Choose the level from reversibility, blast radius (money or people affected per action), verification cost and measured accuracy. The policy caps the level allowed at launch for each tier; the default caps are L5 for minimal, L4 for limited and L3 for high.

Moving up a level requires evidence. The default policy requires, for one-level promotion: at least 500 reviewed actions at the current level, an override rate below 2% over at least four weeks, no critical incidents, a working undo or reversal path, and sign-off from the tier's approvers.

## 4. Map the required controls

The policy lists the required controls for the tier, plus conditional controls (for example least-privilege tooling when the system takes actions, or permission-aware retrieval when it uses RAG). For each control, state how it is implemented, what the evidence is, and who owns it (a role).

The default control catalogue:

| ID | Control |
|---|---|
| GOV-01 | Register the use case in the AI inventory with an accountable owner |
| GOV-02 | Periodic re-certification at the tier's cadence |
| GOV-03 | Sign-off from the tier's approvers before launch |
| EVAL-01 | Offline evaluation on a held-out golden set at the tier minimums, zero critical failures |
| EVAL-02 | Adversarial and red-team testing (prompt injection, jailbreaks, abuse) |
| EVAL-03 | Fairness evaluation across relevant user segments and languages |
| EVAL-04 | Continuous evaluation on every prompt, model, retrieval or tool change |
| HUM-01 | Human review of every output before it is used |
| HUM-02 | Human approval of every action before it executes |
| HUM-03 | Sampled human review of production outputs |
| TRN-01 | Disclosure that users are interacting with AI or reading AI-generated content |
| TRN-02 | Explanation and contestability: affected people can get an explanation and a human review |
| SEC-01 | Prompt-injection defences; retrieved and tool content treated as untrusted data |
| SEC-02 | Least-privilege tools, per-action limits and confirmation for irreversible actions |
| SEC-03 | Output sanitisation before anything is rendered or executed |
| PRV-01 | Privacy review or data protection impact assessment |
| PRV-02 | Data minimisation, redaction in logs and retention limits |
| PRV-03 | Vendor data terms reviewed: training use, retention, residency |
| PRV-04 | Permission-aware retrieval: users only retrieve what they are entitled to see |
| OPS-01 | Monitoring and alerting on quality, safety, cost and latency |
| OPS-02 | Kill switch and a tested non-AI fallback path |
| OPS-03 | Audit log of inputs, outputs, decisions and approvals |
| OPS-04 | Incident response runbook with AI-specific severities |
| OPS-05 | Model version pinning and change management |

## 5. Extra controls for agents and RAG

**Agents**
- Least privilege: scope tools to the task; separate read from write; set per-action and per-day limits on spend and volume.
- Require confirmation for irreversible or high-impact actions (send, pay, delete, publish).
- Treat every tool result, email, web page and retrieved document as untrusted data that can contain instructions. Never let it change the agent's goals or permissions.
- Run in a sandbox with network allowlists, and log every tool call.

**Retrieval-augmented generation**
- Permission-aware retrieval, enforced at query time rather than by the prompt.
- Cite sources, and answer "I couldn't find this in the approved sources" when they do not support an answer.
- Name an owner and a re-index cadence for every source so content stays current.

## 6. Regulatory flags (not legal advice)

Route to legal and compliance review whenever one of these applies:

- **EU users or the EU market:** obligations under the EU AI Act depend on the risk category, ranging from transparency duties (for example for chatbots and AI-generated content) to extensive requirements for high-risk uses such as employment, credit scoring, education and access to essential services.
- **Automated decisions with legal or similarly significant effects on people:** GDPR Article 22 and comparable laws apply, and high-risk processing typically needs a data protection impact assessment.
- **Sector rules:** for example model risk management in banking (such as SR 11-7 in the US), health data rules (such as HIPAA in the US), and consumer-protection and advertising law for generated content.
- **Management frameworks** that structure an AI programme: NIST AI RMF and ISO/IEC 42001.

## Exit criteria

- [ ] Tier computed from the policy, with the policy ID and version, the triggering rules, and any unanswered questions.
- [ ] Risk register covering every category, with `N/A — <reason>` where a category does not apply.
- [ ] Autonomy level chosen within the tier cap, with promotion criteria.
- [ ] Control plan: every required and conditional control with its implementation, evidence and owner.
- [ ] Required approvers identified and regulatory flags routed.
