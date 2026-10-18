from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from ai_product_governance.cli import main
from ai_product_governance.policy import load_effective_policy
from ai_product_governance.records import (
    add_months,
    check_record,
    check_records,
    find_records,
    new_record,
    record_workspace,
)
from ai_product_governance.skill import Skill
from ai_product_governance.validate import check_example_records

EXAMPLE = Path("examples") / "financial-services"
RECORD = Path(".ai-governance") / "use-cases" / "card-dispute-replies.json"
AS_OF = date(2026, 10, 18)  # after the example's last_certified (2026-10-16), before its recertify_by (2027-01-16)

Record = dict[str, Any]


@pytest.fixture
def workspace(repo: Path, tmp_path: Path) -> Path:
    """A copy of the bank example workspace: its policy and the passing card-dispute record."""
    target = tmp_path / "bank"
    shutil.copytree(repo / EXAMPLE / ".ai-governance", target / ".ai-governance")
    return target


def edit(workspace: Path, change: Callable[[Record], None]) -> Path:
    path = workspace / RECORD
    record = json.loads(path.read_text(encoding="utf-8"))
    change(record)
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def problems(path: Path, as_of: date | None = AS_OF, policy: str | None = None) -> list[str]:
    [result] = check_records([path], policy, as_of)
    return list(result.problems)


def control(record: Record, control_id: str) -> Record:
    found: Record = next(c for c in record["controls"] if c["id"] == control_id)
    return found


def answers_file(tmp_path: Path, repo: Path, **overrides: Any) -> Path:
    answers = json.loads((repo / "examples" / "inputs" / "refund-agent.answers.json").read_text(encoding="utf-8"))
    path = tmp_path / "answers.json"
    path.write_text(json.dumps({"external_model_dependency": True, **answers, **overrides}), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- schema and example


def test_use_case_schema_is_a_valid_json_schema(skill: Skill) -> None:
    Draft202012Validator.check_schema(json.loads(skill.use_case_schema_path.read_text(encoding="utf-8")))


def test_example_record_passes_against_the_bank_policy(repo: Path) -> None:
    [result] = check_records(find_records([repo / EXAMPLE]), as_of=AS_OF)
    assert result.problems == ()
    assert (result.record_id, result.tier, result.policy) == (
        "card-dispute-replies",
        "High",
        "fs-bank-ai-policy v2.4.0",
    )


def test_validate_checks_example_records_but_never_expires_them(repo: Path, skill: Skill, tmp_path: Path) -> None:
    assert check_example_records(repo) == []
    shutil.copytree(skill.root, tmp_path / "skills" / skill.name)
    shutil.copytree(repo / EXAMPLE, tmp_path / EXAMPLE)

    def long_lapsed(record: Record) -> None:
        record["last_certified"], record["recertify_by"] = "2020-01-01", "2020-04-01"

    edit(tmp_path / EXAMPLE, long_lapsed)
    assert check_example_records(tmp_path) == []

    edit(tmp_path / EXAMPLE, lambda record: control(record, "GOV-01").update(status="open"))
    [finding] = check_example_records(tmp_path)
    assert finding.level == "error"
    assert finding.where == (EXAMPLE / RECORD).as_posix()
    assert "GOV-01 (AI inventory registration) is open" in finding.message


# --------------------------------------------------------------------------- what the check catches


def _remove_control(control_id: str) -> Callable[[Record], None]:
    def change(record: Record) -> None:
        record["controls"] = [c for c in record["controls"] if c["id"] != control_id]

    return change


def _remove_approval(role: str) -> Callable[[Record], None]:
    def change(record: Record) -> None:
        record["approvals"] = [a for a in record["approvals"] if a["role"] != role]

    return change


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        pytest.param(
            lambda r: r.update(tier="limited"),
            "the stored tier 'limited' is stale: the answers classify as 'high' under fs-bank-ai-policy v2.4.0",
            id="stale-tier",
        ),
        pytest.param(
            lambda r: control(r, "GOV-01").update(status="open"),
            "control GOV-01 (AI inventory registration) is open",
            id="open-control",
        ),
        pytest.param(
            lambda r: control(r, "TRN-02").update(approver=""),
            "control TRN-02 (Explanation and contestability) is waived without approver",
            id="waiver-without-approver",
        ),
        pytest.param(
            lambda r: control(r, "TRN-02").pop("reason"),
            "control TRN-02 (Explanation and contestability) is waived without reason",
            id="waiver-without-reason",
        ),
        pytest.param(
            lambda r: control(r, "EVAL-01").update(evidence_url=""),
            "control EVAL-01 (Offline evaluation) is done but has no evidence_url (evidence: Eval report",
            id="done-without-evidence",
        ),
        pytest.param(
            _remove_control("MRM-01"),
            "control MRM-01 (Independent model validation) is required (tier: high) but missing from the record",
            id="missing-control",
        ),
        pytest.param(
            lambda r: r["questionnaire"]["answers"].update(consequential_decisions=True),
            "control TRN-03 (Adverse action reasons) is required (condition: People adversely affected",
            id="answers-add-a-control",
        ),
        pytest.param(
            lambda r: r["controls"].append(dict(control(r, "GOV-01"))),
            "control GOV-01 is listed more than once",
            id="duplicate-control",
        ),
        pytest.param(
            _remove_approval("Compliance officer"),
            "not signed off by: Compliance officer",
            id="missing-approval",
        ),
        pytest.param(
            lambda r: r["approvals"][0].update(date=""),
            "not signed off by: Product owner",
            id="undated-approval",
        ),
        pytest.param(
            lambda r: r.update(recertify_by="2027-06-01"),
            "recertify_by 2027-06-01 is more than 3 months after last_certified 2026-10-16",
            id="cadence-exceeded",
        ),
        pytest.param(
            lambda r: r.update(recertify_by=None),
            "recertify_by is not set: the High tier re-certifies every 3 months (2027-01-16)",
            id="no-recertify-by",
        ),
        pytest.param(
            lambda r: r.update(last_certified="2026-12-01", recertify_by="2027-03-01"),
            "last_certified 2026-12-01 is in the future",
            id="certified-in-the-future",
        ),
        pytest.param(
            lambda r: r["questionnaire"]["answers"].pop("external_model_dependency"),
            "unanswered questions: external_model_dependency",
            id="unanswered-question",
        ),
        pytest.param(
            lambda r: r["questionnaire"]["answers"].update(favourite_colour=True),
            "the answers are not valid for fs-bank-ai-policy v2.4.0: unknown question IDs: favourite_colour",
            id="invalid-answers",
        ),
        pytest.param(
            lambda r: r["questionnaire"]["answers"].update(prohibited_practices=["social_scoring"]),
            "the answers classify as Prohibited: stop the work; there is no approval path",
            id="prohibited",
        ),
        pytest.param(lambda r: r.update(owner=" "), "owner is not set", id="no-owner"),
        pytest.param(
            lambda r: r["questionnaire"].update(answered_by=""),
            "questionnaire.answered_by is not set",
            id="no-answerer",
        ),
        pytest.param(
            lambda r: r.update(policy_id="aipg-default"),
            "the record was certified against policy 'aipg-default', not fs-bank-ai-policy v2.4.0",
            id="other-policy",
        ),
        pytest.param(
            lambda r: r.update(id="card-disputes"),
            "id 'card-disputes' does not match the file name card-dispute-replies.json",
            id="id-mismatch",
        ),
        pytest.param(
            lambda r: r["controls"][0].update(status="maybe"),
            "does not match use-case.schema.json at controls/0/status: 'maybe' is not one of",
            id="schema-status",
        ),
        pytest.param(
            lambda r: r.update(last_certified="2026-02-30"),
            "does not match use-case.schema.json at last_certified: '2026-02-30' is not a 'date'",
            id="schema-date",
        ),
    ],
)
def test_check_fails_with_a_clear_message(workspace: Path, change: Callable[[Record], None], expected: str) -> None:
    found = problems(edit(workspace, change))
    assert any(expected in problem for problem in found), found


def test_re_certification_lapses_after_recertify_by(workspace: Path) -> None:
    path = workspace / RECORD
    assert problems(path, as_of=date(2027, 1, 16)) == []
    assert problems(path, as_of=date(2027, 1, 17)) == [
        "re-certification lapsed on 2027-01-16: repeat the gate review, then update last_certified and recertify_by"
    ]


def test_a_new_policy_version_requires_re_certification(workspace: Path) -> None:
    policy_path = workspace / ".ai-governance" / "policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["version"] = "2.5.0"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    assert problems(workspace / RECORD) == [
        "the policy changed since certification (v2.4.0 -> v2.5.0): repeat the gate review, then update "
        "policy_version, last_certified and recertify_by"
    ]


def test_each_record_uses_its_own_workspace_policy(
    workspace: Path, skill: Skill, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert record_workspace(workspace / RECORD) == workspace.resolve()
    assert record_workspace(elsewhere / "card-dispute-replies.json") is None
    assert problems(workspace / RECORD) == []
    # An explicit policy (or $AIPG_POLICY) wins, exactly as in the engine's resolution order.
    found = problems(workspace / RECORD, policy=str(skill.default_policy_path))
    assert "the record was certified against policy 'fs-bank-ai-policy', not aipg-default v1.0.0" in found


def test_unreadable_records_and_policies_fail(workspace: Path, tmp_path: Path) -> None:
    broken = workspace / ".ai-governance" / "use-cases" / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    [result] = check_records([broken], as_of=AS_OF)
    assert result.problems[0].startswith("cannot read the record:")
    [result] = check_records([workspace / RECORD], str(tmp_path / "missing-policy.json"), AS_OF)
    assert result.problems[0].startswith("cannot load the effective policy: Policy file not found")


# --------------------------------------------------------------------------- aipg check


def test_check_command_exit_codes_and_formats(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check", str(workspace), "--as-of", "2026-10-18"]) == 0
    out = capsys.readouterr().out
    assert "PASS" in out and "Card dispute reply drafting (High, fs-bank-ai-policy v2.4.0)" in out
    assert out.rstrip().endswith("1 use-case record checked: 1 passed, 0 failed.")

    edit(workspace, _remove_approval("Legal counsel"))
    assert main(["check", str(workspace / RECORD), "--as-of", "2026-10-18", "--format", "md"]) == 1
    markdown = capsys.readouterr().out
    assert markdown.startswith("### AI governance check: 1 of 1 use case failing\n")
    assert (
        "| `card-dispute-replies` Card dispute reply drafting | High | fs-bank-ai-policy v2.4.0 | **Fail** (1 issue) |"
        in markdown
    )
    assert "#### `card-dispute-replies`: Card dispute reply drafting" in markdown
    assert "- not signed off by: Legal counsel" in markdown

    assert main(["check", str(workspace), "--as-of", "2026-10-18", "--format", "json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["passed"] is False
    assert report["records"][0]["problems"][0].startswith("not signed off by: Legal counsel")


def test_check_command_defaults_to_the_workspace_records(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(workspace)
    assert main(["check", "--as-of", "2026-10-18"]) == 0
    assert "PASS  .ai-governance/use-cases/card-dispute-replies.json" in capsys.readouterr().out


def test_check_command_needs_records_to_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["check"]) == 2
    assert "no use-case records found in .ai-governance/use-cases" in capsys.readouterr().err
    assert main(["check", "nowhere"]) == 2
    assert "nowhere does not exist" in capsys.readouterr().err


# --------------------------------------------------------------------------- aipg record new


def test_record_new_writes_an_open_record_that_check_rejects(
    workspace: Path, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(workspace)
    argv = ["record", "new", "--answers", str(answers_file(tmp_path, repo)), "--id", "refund-agent"]
    assert main([*argv, "--date", "2026-01-31", "--owner", "Payments team"]) == 0
    out = capsys.readouterr().out
    assert "Refund agent: High tier under fs-bank-ai-policy v2.4.0, from the workspace policy" in out

    path = workspace / ".ai-governance" / "use-cases" / "refund-agent.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    policy = load_effective_policy(cwd=workspace)
    _, expected = new_record(record["questionnaire"]["answers"], "refund-agent", policy, on=date(2026, 1, 31))
    assert (record["policy_id"], record["policy_version"], record["tier"]) == ("fs-bank-ai-policy", "2.4.0", "high")
    assert (record["owner"], record["last_certified"], record["questionnaire"]["answered_on"]) == (
        "Payments team",
        "2026-01-31",
        "2026-01-31",
    )
    assert record["recertify_by"] == "2026-04-30", "3 months after 31 January, clamped to the end of April"
    assert [c["id"] for c in record["controls"]] == [c["id"] for c in expected["required_controls"]]
    assert {c["status"] for c in record["controls"]} == {"open"}
    assert [a["role"] for a in record["approvals"]] == expected["approvers"]

    found = problems(path, as_of=date(2026, 2, 1))
    assert "questionnaire.answered_by is not set: name who answered the questionnaire" in found
    assert sum("is open" in problem for problem in found) == len(record["controls"])
    assert f"{len(found)} item(s) to resolve before `aipg check` passes" in out

    assert main(argv) == 2
    assert "already exists; pass --force" in capsys.readouterr().err
    assert main([*argv, "--force"]) == 0


def test_a_completed_new_record_passes(workspace: Path, repo: Path) -> None:
    policy = load_effective_policy(cwd=workspace)
    answers = json.loads(answers_file(workspace, repo).read_text(encoding="utf-8"))
    record, result = new_record(
        answers, "refund-agent", policy, on=date(2026, 10, 1), owner="Payments", answered_by="A"
    )
    for entry in record["controls"]:
        entry.update(status="done", owner="Payments", evidence_url=f"https://grc.example.com/{entry['id']}")
    for approval in record["approvals"]:
        approval.update(name="Signer", date="2026-10-02")
    path = workspace / ".ai-governance" / "use-cases" / "refund-agent.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    assert check_record(path, policy, as_of=AS_OF).problems == ()
    assert result["tier"]["id"] == "high"


def test_record_new_refuses_prohibited_and_invalid_input(
    workspace: Path, repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = workspace / ".ai-governance" / "use-cases" / "scoring.json"
    prohibited = answers_file(tmp_path, repo, prohibited_practices=["social_scoring"])
    assert main(["record", "new", "--answers", str(prohibited), "--id", "scoring", "--out", str(out)]) == 1
    assert "no record was written" in capsys.readouterr().err
    assert not out.exists()

    valid = str(answers_file(tmp_path, repo))
    assert (
        main(["record", "new", "--answers", valid, "--id", "Bad_ID", "--out", str(out.with_name("Bad_ID.json"))]) == 2
    )
    assert "invalid record ID 'Bad_ID'" in capsys.readouterr().err
    invalid = answers_file(tmp_path, repo, autonomy_level="L9")
    assert main(["record", "new", "--answers", str(invalid), "--id", "scoring", "--out", str(out)]) == 2
    assert "'autonomy_level' must be one of" in capsys.readouterr().err
    assert main(["record", "new", "--answers", valid, "--id", "other", "--out", str(out)]) == 2
    assert "--out must name the file other.json" in capsys.readouterr().err
    assert not out.exists()


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (date(2026, 10, 16), 3, date(2027, 1, 16)),
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2028, 1, 31), 1, date(2028, 2, 29)),
        (date(2026, 11, 30), 3, date(2027, 2, 28)),
        (date(2026, 5, 15), 12, date(2027, 5, 15)),
    ],
)
def test_add_months_clamps_to_the_end_of_the_month(start: date, months: int, expected: date) -> None:
    assert add_months(start, months) == expected
