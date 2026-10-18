"""Write eval results as JSON, Markdown and JUnit XML."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from ai_product_governance.evals.scoring import ArmSummary, CellSummary, GateResult, TrialResult


def write_reports(
    out_dir: Path,
    manifest: dict[str, Any],
    trials: list[TrialResult],
    cells: list[CellSummary],
    arms: list[ArmSummary],
    gates: list[GateResult],
    skipped: list[str],
    total_cost: float | None,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "manifest": out_dir / "manifest.json",
        "results": out_dir / "results.json",
        "report": out_dir / "report.md",
        "junit": out_dir / "junit.xml",
    }
    _write(paths["manifest"], json.dumps(manifest, indent=2) + "\n")
    _write(
        paths["results"],
        json.dumps(
            {
                "run_id": manifest["run_id"],
                "total_cost_usd": total_cost,
                "skipped": skipped,
                "arms": [asdict(a) for a in arms],
                "cells": [asdict(c) for c in cells],
                "gates": [asdict(g) for g in gates],
                "trials": [t.to_dict() for t in trials],
            },
            indent=2,
        )
        + "\n",
    )
    _write(paths["report"], render_markdown(manifest, trials, cells, arms, gates, skipped, total_cost))
    _write(paths["junit"], render_junit(manifest, cells, gates))
    return paths


def render_markdown(
    manifest: dict[str, Any],
    trials: list[TrialResult],
    cells: list[CellSummary],
    arms: list[ArmSummary],
    gates: list[GateResult],
    skipped: list[str],
    total_cost: float | None,
) -> str:
    cost = "n/a" if total_cost is None else f"${total_cost:,.2f}"
    verdict = "PASS" if gates and all(g.passed for g in gates) else ("FAIL" if gates else "NO GATES EVALUATED")
    subjects = manifest.get("subjects", [])
    judges = list(manifest.get("judges", {}).values()) or [manifest.get("judge", {})]
    judge_models = sorted({str(j.get("model", "n/a")) for j in judges if j})
    lines = [
        f"# Eval report {manifest['run_id']}",
        "",
        f"**Gates: {verdict}** | skill v{manifest['skill_version']} | judged by {', '.join(judge_models) or 'n/a'} | "
        f"{manifest['trials']} trial(s) per cell | cost {cost}",
        "",
    ]
    models = [*subjects, *judges]
    if any(m.get("provider") in ("claude-code", "agent-cli") for m in models):
        lines += [
            "> Agent CLI runs used the tool's own sign-in. Costs shown for Claude Code are its API-equivalent "
            "estimates and other agent CLIs report none; on a subscription these runs count against plan usage "
            "limits instead of being billed per token.",
            "",
        ]
    if manifest.get("mode") == "agent-run eval kit":
        lines += [
            "> **Agent-run results.** An AI agent ran this kit inside the user's own tool, giving each prompt to a "
            "fresh sub-agent. Nothing outside that tool checked that the baseline sub-agents could not see the skill "
            "or that replies were saved unedited, so treat the with-skill vs baseline difference as indicative "
            "evidence for this tool and model, not an audited result. Use `aipg eval` for audit-grade runs.",
            "",
        ]
    if any(s.get("id") and judges and s.get("model") == j.get("model") for s, j in zip(subjects, judges, strict=False)):
        lines += [
            "> Each model graded its own answers (blind to which arm produced them), so one AI tool is enough. "
            "Both arms share the same judge, so the with-skill vs baseline difference stays comparable.",
            "",
        ]
    lines += [
        "## Summary by subject and arm",
        "",
        "| Subject | Arm | Mean score | Pass rate | Critical failures | Errors |",
        "|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {a.subject} | {a.arm} | {a.mean_score:.2f} | {a.pass_rate:.0%} | {a.critical_failures} | {a.errors} |"
        for a in arms
    ]
    if gates:
        lines += ["", "## Quality gates", "", "| Subject | Gate | Result | Detail |", "|---|---|---|---|"]
        lines += [f"| {g.subject} | {g.name} | {'pass' if g.passed else 'FAIL'} | {g.detail} |" for g in gates]

    lines += [
        "",
        "## Scenarios",
        "",
        "| Subject | Scenario | Arm | Mean | Std dev | Pass rate | Critical |",
        "|---|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {c.subject} | {c.scenario} | {c.arm} | {c.mean_score:.2f} | {c.stdev:.2f} | {c.pass_rate:.0%} | "
        f"{c.critical_failures} |"
        for c in cells
    ]

    routing = [t for t in trials if t.routing]
    if routing:
        lines += [
            "",
            "## Skill adherence (with-skill arm)",
            "",
            "Whether the model loaded the expected playbooks and ran the expected calculators.",
            "",
            "| Subject | Scenario | Trial | Expected step | Done |",
            "|---|---|---|---|---|",
        ]
        for t in routing:
            lines += [
                f"| {t.subject} | {t.scenario} | {t.trial} | {step} | {'yes' if done else 'no'} |"
                for step, done in t.routing.items()
            ]

    failures = [t for t in trials if t.error or any(not i.passed for i in t.items)]
    if failures:
        lines += ["", "## Failures", ""]
        for t in failures:
            lines.append(f"### {t.subject} / {t.scenario} / {t.arm} / trial {t.trial} (score {t.score:.2f})")
            if t.error:
                lines.append(f"- **Error:** {t.error}")
            for item in t.items:
                if not item.passed:
                    flag = " **(critical)**" if item.critical else ""
                    detail = f" — {item.rationale}" if item.rationale else ""
                    lines.append(f"- {item.id}{flag}: {item.text}{detail}")
            lines.append("")
    if skipped:
        lines += ["", "## Skipped (cost ceiling reached)", "", *[f"- {s}" for s in skipped]]
    return "\n".join(lines).rstrip() + "\n"


def render_junit(manifest: dict[str, Any], cells: list[CellSummary], gates: list[GateResult]) -> str:
    suites = ET.Element("testsuites", name=f"aipg-evals-{manifest['run_id']}")
    scenario_suite = ET.SubElement(suites, "testsuite", name="scenarios")
    for cell in cells:
        case = ET.SubElement(scenario_suite, "testcase", classname=f"{cell.subject}.{cell.arm}", name=cell.scenario)
        if cell.arm == "with-skill" and (cell.critical_failures or cell.errors):
            failure = ET.SubElement(case, "failure", message="critical failures or errors")
            failure.text = f"critical={cell.critical_failures} errors={cell.errors} mean={cell.mean_score:.3f}"
    gate_suite = ET.SubElement(suites, "testsuite", name="gates")
    for gate in gates:
        case = ET.SubElement(gate_suite, "testcase", classname=gate.subject, name=gate.name)
        if not gate.passed:
            ET.SubElement(case, "failure", message=gate.detail)
    for suite in (scenario_suite, gate_suite):
        suite.set("tests", str(len(suite)))
        suite.set("failures", str(sum(1 for case in suite if case.find("failure") is not None)))
    ET.indent(suites)
    return ET.tostring(suites, encoding="unicode", xml_declaration=True) + "\n"


def _write(path: Path, content: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
