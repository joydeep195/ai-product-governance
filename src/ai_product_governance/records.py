"""Use-case records: per-use-case evidence that makes the policy's controls enforceable.

A record lives at `.ai-governance/use-cases/<id>.json` (schema: assets/policy/use-case.schema.json). It stores the
questionnaire answers, the tier they produced under a specific policy version, the status and evidence of every
required control, approver sign-offs and the re-certification dates. `aipg record new` writes one with every
control open; `aipg check` re-classifies each record against the effective policy with the skill's risk_tier
engine and fails until the record is complete and current, so CI can block what the policy does not allow.
"""

from __future__ import annotations

import calendar
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ai_product_governance import engines
from ai_product_governance.policy import EffectivePolicy, load_effective_policy, schema_errors
from ai_product_governance.skill import load_skill

RECORDS_DIR = Path(".ai-governance") / "use-cases"
RECORD_ID = re.compile(r"[a-z0-9][a-z0-9-]*")


class RecordError(ValueError):
    """A record cannot be created, or the paths given to check are unusable."""


class ProhibitedUseCaseError(RecordError):
    """The answers classify into a prohibited tier, which has no approval path and therefore no record."""


def add_months(start: date, months: int) -> date:
    """The same day `months` calendar months later, clamped to the end of a shorter month (31 Jan + 1 = 28 Feb)."""
    index = start.month - 1 + months
    year, month = start.year + index // 12, index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def record_workspace(path: Path) -> Path | None:
    """The workspace that owns a record stored at <workspace>/.ai-governance/use-cases/<id>.json, if any."""
    folder = path.resolve().parent
    if folder.name == RECORDS_DIR.name and folder.parent.name == RECORDS_DIR.parent.name:
        return folder.parent.parent
    return None


def policy_for_record(path: Path, explicit: str | None = None) -> EffectivePolicy:
    """The effective policy for a record: --policy, $AIPG_POLICY, its workspace's policy, then the bundled default."""
    return load_effective_policy(explicit, cwd=record_workspace(path) or Path.cwd())


# --------------------------------------------------------------------------- creating records


def new_record(
    answers: Any,
    record_id: str,
    policy: EffectivePolicy,
    *,
    on: date,
    title: str = "",
    owner: str = "",
    answered_by: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Classify the answers and return (record, classification), with every required control open.

    Raises the engine's AnswerError for invalid answers, RecordError for an invalid ID and ProhibitedUseCaseError
    when the use case falls in a prohibited tier.
    """
    if not RECORD_ID.fullmatch(record_id):
        raise RecordError(f"invalid record ID '{record_id}': use lowercase letters, digits and hyphens")
    engine = engines.risk_tier()
    normalised, _ = engine.validate_answers(policy.document, answers)
    result: dict[str, Any] = engine.classify(
        policy.document, normalised, policy_source=policy.source, policy_path=str(policy.path)
    )
    if result["prohibited"]:
        rules = "; ".join(f"{rule['id']}: {rule['reason']}" for rule in result["triggered_rules"])
        raise ProhibitedUseCaseError(
            f"the answers classify as {result['tier']['name']} under {policy.label} ({rules}). "
            "Stop the work: there is no approval path, so no record was written."
        )
    months = result["recertification_months"]
    record = {
        "id": record_id,
        "title": title or record_id.replace("-", " ").capitalize(),
        "owner": owner,
        "policy_id": policy.id,
        "policy_version": policy.version,
        "tier": result["tier"]["id"],
        "last_certified": on.isoformat(),
        "recertify_by": add_months(on, months).isoformat() if months else None,
        "questionnaire": {"answers": normalised, "answered_by": answered_by, "answered_on": on.isoformat()},
        "approvals": [{"role": role, "name": "", "date": ""} for role in result["approvers"]],
        "controls": [
            {"id": control["id"], "name": control["name"], "status": "open", "owner": "", "evidence_url": ""}
            for control in result["required_controls"]
        ],
    }
    return record, result


def write_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, indent=2, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- checking records


@dataclass(frozen=True)
class RecordCheck:
    path: Path
    record_id: str
    title: str
    tier: str
    policy: str
    problems: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.problems


def find_records(paths: Sequence[Path]) -> list[Path]:
    """Expand files, use-cases folders and workspaces (folders holding .ai-governance/use-cases) into record files."""
    found: dict[Path, Path] = {}
    for path in paths:
        if path.is_file():
            candidates = [path]
        elif path.is_dir():
            folder = path / RECORDS_DIR if (path / RECORDS_DIR).is_dir() else path
            candidates = sorted(folder.glob("*.json"))
        else:
            raise RecordError(f"{path} does not exist")
        for candidate in candidates:
            found.setdefault(candidate.resolve(), candidate)
    return list(found.values())


def check_records(
    paths: Iterable[Path], explicit_policy: str | None = None, as_of: date | None = None
) -> list[RecordCheck]:
    """Check each record against the effective policy for its workspace (resolved once per workspace)."""
    engine = engines.risk_tier()
    policies: dict[Path | None, EffectivePolicy | str] = {}
    results = []
    for path in paths:
        workspace = record_workspace(path)
        if workspace not in policies:
            try:
                policies[workspace] = load_effective_policy(explicit_policy, cwd=workspace or Path.cwd())
            except engine.PolicyError as exc:
                policies[workspace] = str(exc)
        policy = policies[workspace]
        if isinstance(policy, str):
            results.append(RecordCheck(path, path.stem, "", "", "", (f"cannot load the effective policy: {policy}",)))
        else:
            results.append(check_record(path, policy, as_of))
    return results


def check_record(path: Path, policy: EffectivePolicy, as_of: date | None) -> RecordCheck:
    """Re-classify a record's answers against `policy` and list everything that stops it from passing.

    `as_of` is the date re-certification is judged on; None skips the dates that depend on today, which keeps
    example records valid forever while still checking everything else.
    """
    engine = engines.risk_tier()
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return RecordCheck(path, path.stem, "", "", policy.label, (f"cannot read the record: {exc}",))
    errors = schema_errors(record, load_skill().use_case_schema_path)
    if errors:
        title = record.get("title", "") if isinstance(record, dict) else ""
        invalid = tuple(f"does not match use-case.schema.json at {error}" for error in errors)
        return RecordCheck(path, path.stem, str(title), "", policy.label, invalid)

    problems: list[str] = []
    if record["id"] != path.stem:
        problems.append(f"id '{record['id']}' does not match the file name {path.name}: rename the file or the id")
    if not record["owner"].strip():
        problems.append("owner is not set: name the accountable owner of the use case")
    if not record["questionnaire"]["answered_by"].strip():
        problems.append("questionnaire.answered_by is not set: name who answered the questionnaire")
    if record["policy_id"] != policy.id:
        problems.append(f"the record was certified against policy '{record['policy_id']}', not {policy.label}")
    elif record["policy_version"] != policy.version:
        problems.append(
            f"the policy changed since certification (v{record['policy_version']} -> v{policy.version}): "
            "repeat the gate review, then update policy_version, last_certified and recertify_by"
        )

    def finish(tier: str) -> RecordCheck:
        return RecordCheck(path, record["id"], record["title"], tier, policy.label, tuple(problems))

    try:
        result = engine.classify(
            policy.document,
            record["questionnaire"]["answers"],
            policy_source=policy.source,
            policy_path=str(policy.path),
        )
    except engine.AnswerError as exc:
        problems.append(f"the answers are not valid for {policy.label}: {exc}")
        return finish(record["tier"])
    tier = result["tier"]
    if result["unanswered_questions"]:
        problems.append(
            "unanswered questions: "
            + ", ".join(result["unanswered_questions"])
            + " (answers can raise the tier or add controls, so every question must be answered)"
        )
    if record["tier"] != tier["id"]:
        problems.append(
            f"the stored tier '{record['tier']}' is stale: the answers classify as '{tier['id']}' under {policy.label}"
        )
    if result["prohibited"]:
        problems.append(f"the answers classify as {tier['name']}: stop the work; there is no approval path")
        return finish(tier["name"])
    problems += _control_problems(record["controls"], result["required_controls"])
    problems += _approval_problems(record["approvals"], result["approvers"])
    problems += _recertification_problems(record, tier["name"], result["recertification_months"], as_of)
    return finish(tier["name"])


def _control_problems(entries: list[dict[str, Any]], required: list[dict[str, Any]]) -> list[str]:
    problems = []
    by_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if entry["id"] in by_id:
            problems.append(f"control {entry['id']} is listed more than once")
        by_id.setdefault(entry["id"], entry)
    for control in required:
        label = f"{control['id']} ({control['name']})"
        status = by_id.get(control["id"])
        if status is None:
            problems.append(f"control {label} is required ({control['required_by']}) but missing from the record")
        elif status["status"] == "open":
            problems.append(f"control {label} is open: mark it done with evidence or waive it with an approver")
        elif status["status"] == "done" and not status.get("evidence_url", "").strip():
            problems.append(f"control {label} is done but has no evidence_url (evidence: {control['evidence']})")
        elif status["status"] == "waived":
            missing = [key for key in ("approver", "reason") if not status.get(key, "").strip()]
            if missing:
                problems.append(f"control {label} is waived without {' or '.join(missing)}")
    return problems


def _approval_problems(approvals: list[dict[str, Any]], roles: list[str]) -> list[str]:
    signed = {approval["role"] for approval in approvals if approval["name"].strip() and approval["date"]}
    missing = [role for role in roles if role not in signed]
    if not missing:
        return []
    return ["not signed off by: " + ", ".join(missing) + " (each approval needs the role, a name and a date)"]


def _recertification_problems(record: dict[str, Any], tier: str, months: int | None, as_of: date | None) -> list[str]:
    problems = []
    certified = date.fromisoformat(record["last_certified"])
    if as_of is not None and certified > as_of:
        problems.append(f"last_certified {certified} is in the future")
    due = None if record["recertify_by"] is None else date.fromisoformat(record["recertify_by"])
    if months is not None:
        latest = add_months(certified, months)
        if due is None:
            problems.append(f"recertify_by is not set: the {tier} tier re-certifies every {months} months ({latest})")
            due = latest
        elif due > latest:
            problems.append(
                f"recertify_by {due} is more than {months} months after last_certified {certified}: "
                f"the {tier} tier re-certifies every {months} months, so it is due by {latest}"
            )
            due = latest
    if as_of is not None and due is not None and as_of > due:
        problems.append(
            f"re-certification lapsed on {due}: repeat the gate review, then update last_certified and recertify_by"
        )
    return problems


# --------------------------------------------------------------------------- rendering


def _display(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _summary(results: Sequence[RecordCheck]) -> str:
    failed = sum(1 for result in results if not result.passed)
    return f"{_plural(len(results), 'use-case record')} checked: {len(results) - failed} passed, {failed} failed."


def render_text(results: Sequence[RecordCheck]) -> str:
    lines = []
    for result in results:
        details = ", ".join(part for part in (result.tier, result.policy) if part)
        heading = f"{'PASS' if result.passed else 'FAIL'}  {_display(result.path)}"
        if result.title:
            heading += f": {result.title}"
        lines.append(heading + (f" ({details})" if details else ""))
        lines += [f"      - {problem}" for problem in result.problems]
    lines.append(_summary(results))
    return "\n".join(lines) + "\n"


def _md(text: str) -> str:
    """Escape text for a Markdown table cell or list item (GitHub hides anything that looks like an HTML tag)."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace("|", "\\|")


def render_markdown(results: Sequence[RecordCheck]) -> str:
    failed = [result for result in results if not result.passed]
    if failed:
        heading = f"### AI governance check: {len(failed)} of {_plural(len(results), 'use case')} failing"
    else:
        heading = f"### AI governance check: passed for {_plural(len(results), 'use case')}"
    lines = [heading, "", "| Use case | Tier | Policy | Result |", "|---|---|---|---|"]
    for result in results:
        outcome = "Pass" if result.passed else f"**Fail** ({_plural(len(result.problems), 'issue')})"
        name = f"`{result.record_id}` {_md(result.title)}".strip()
        lines.append(f"| {name} | {_md(result.tier) or '-'} | {_md(result.policy) or '-'} | {outcome} |")
    for result in failed:
        title = f": {_md(result.title)}" if result.title else ""
        lines += ["", f"#### `{result.record_id}`{title}", "", f"`{_display(result.path)}`", ""]
        lines += [f"- {_md(problem)}" for problem in result.problems]
    lines += ["", _summary(results)]
    return "\n".join(lines) + "\n"


def render_json(results: Sequence[RecordCheck]) -> str:
    document = {
        "passed": all(result.passed for result in results),
        "records": [
            {
                "path": _display(result.path),
                "id": result.record_id,
                "title": result.title,
                "tier": result.tier,
                "policy": result.policy,
                "passed": result.passed,
                "problems": list(result.problems),
            }
            for result in results
        ],
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"
