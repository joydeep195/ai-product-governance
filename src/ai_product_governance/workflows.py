"""The governance lifecycle and workflows, shared by every integration target.

Gates and workflows are declared once here and rendered into MCP prompts, GitHub
Copilot prompt files and the universal prompt pack. A test checks that SKILL.md's
lifecycle table stays consistent with these declarations.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Gate:
    id: str
    title: str
    question: str
    reference: str
    template: str


@dataclass(frozen=True)
class Workflow:
    id: str
    title: str
    description: str
    argument: str
    argument_hint: str
    references: tuple[str, ...]
    template: str
    task: str  # contains the "{argument}" placeholder

    def render_task(self, value: str) -> str:
        return self.task.replace("{argument}", value)


GATES: tuple[Gate, ...] = (
    Gate("G0", "Intake and fit", "Should this use AI at all?", "gate-0-intake-and-fit", "use-case-brief"),
    Gate("G1", "Value and economics", "Is it worth it at our volume?", "gate-1-value-and-economics", "business-case"),
    Gate("G2", "Quality and evals", "How will we know it is good enough?", "gate-2-quality-and-evals", "eval-plan"),
    Gate(
        "G3",
        "Risk and controls",
        "What can go wrong, and which controls are mandatory?",
        "gate-3-risk-and-controls",
        "risk-assessment",
    ),
    Gate(
        "G4",
        "Launch readiness",
        "Is it safe to expose to users, and how much?",
        "gate-4-launch-readiness",
        "launch-readiness-review",
    ),
    Gate("G5", "Operate and improve", "Is it still working?", "gate-5-operate-and-improve", "incident-review"),
)

WORKFLOWS: tuple[Workflow, ...] = (
    Workflow(
        id="ai-intake",
        title="AI use-case intake and fit check",
        description="Decide whether a use case needs AI at all (Gate 0) and produce a use-case brief with a fit verdict.",
        argument="idea",
        argument_hint="Describe the idea, problem or request",
        references=("gate-0-intake-and-fit",),
        template="use-case-brief",
        task="Run Gate 0 (intake and AI fit) for this idea and produce the use-case brief with a fit verdict:\n\n{argument}",
    ),
    Workflow(
        id="ai-business-case",
        title="AI business case and unit economics",
        description="Price an AI feature per completed task and decide whether it is worth building (Gate 1).",
        argument="feature",
        argument_hint="Describe the feature, volumes, model prices and today's cost",
        references=("gate-1-value-and-economics",),
        template="business-case",
        task="Run Gate 1 (value and economics) for this feature and produce the business case:\n\n{argument}",
    ),
    Workflow(
        id="ai-prd",
        title="AI PRD",
        description="Write an AI PRD with a fit verdict, quality bar, failure design, economics, risk tier, controls and rollout.",
        argument="feature",
        argument_hint="Describe the feature and its users",
        references=("gate-0-intake-and-fit", "gate-2-quality-and-evals", "gate-3-risk-and-controls"),
        template="ai-prd",
        task="Write an AI PRD for this feature. If Gate 0 has not been passed, run the fit check first:\n\n{argument}",
    ),
    Workflow(
        id="ai-eval-plan",
        title="AI eval plan",
        description="Define the quality bar, golden set, grading methods and thresholds for an AI feature (Gate 2).",
        argument="feature",
        argument_hint="Describe the feature and what good output looks like",
        references=("gate-2-quality-and-evals",),
        template="eval-plan",
        task="Run Gate 2 (quality and evals) for this feature and produce the eval plan:\n\n{argument}",
    ),
    Workflow(
        id="ai-risk-review",
        title="AI risk review",
        description="Classify the risk tier against the policy, build the risk register and map required controls (Gate 3).",
        argument="feature",
        argument_hint="Describe the feature, its users, data and actions",
        references=("gate-3-risk-and-controls",),
        template="risk-assessment",
        task="Run Gate 3 (risk and controls) for this feature and produce the risk assessment:\n\n{argument}",
    ),
    Workflow(
        id="ai-launch-review",
        title="AI launch readiness review",
        description="Decide Go, Go with conditions or No-go for an AI launch and plan a staged rollout (Gate 4).",
        argument="status",
        argument_hint="Paste the feature's current status, eval results and open items",
        references=("gate-4-launch-readiness",),
        template="launch-readiness-review",
        task="Run Gate 4 (launch readiness) on this status and give a Go, Go with conditions or No-go decision:\n\n{argument}",
    ),
    Workflow(
        id="ai-regression-review",
        title="AI quality regression or incident review",
        description="Diagnose why an AI feature got worse, or review an AI incident, using the Gate 5 protocol.",
        argument="symptom",
        argument_hint="Describe what changed, when, and the metrics",
        references=("gate-5-operate-and-improve",),
        template="incident-review",
        task="Apply the Gate 5 regression diagnosis protocol (or incident process) to this situation:\n\n{argument}",
    ),
    Workflow(
        id="ai-model-decision",
        title="AI approach and model decision",
        description="Choose the approach (prompting, RAG, agent, fine-tuning) and model on evidence, and record the decision.",
        argument="context",
        argument_hint="Describe the task, data, volume, latency and constraints",
        references=("approach-and-model-selection", "gate-1-value-and-economics"),
        template="model-decision-record",
        task="Recommend the approach and model for this situation and produce a model decision record:\n\n{argument}",
    ),
)


def workflow(workflow_id: str) -> Workflow:
    for item in WORKFLOWS:
        if item.id == workflow_id:
            return item
    raise KeyError(f"Unknown workflow '{workflow_id}'")
