"""The regulatory crosswalk: control mappings in the schema, the shipped policies and the risk_tier output."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from ai_product_governance.policy import policy_problems

DEFAULT_POLICY = Path("skills") / "ai-product-governance" / "assets" / "policy" / "default-policy.json"
FS_POLICY = Path("examples") / "financial-services" / ".ai-governance" / "policy.json"
SHIPPED_POLICIES = [DEFAULT_POLICY, FS_POLICY]

# NIST AI 100-1 (AI RMF 1.0): number of subcategories in each category.
NIST_CATEGORIES = {
    "GOVERN": {1: 7, 2: 3, 3: 2, 4: 3, 5: 2, 6: 2},
    "MAP": {1: 6, 2: 3, 3: 5, 4: 2, 5: 2},
    "MEASURE": {1: 3, 2: 13, 3: 3, 4: 3},
    "MANAGE": {1: 4, 2: 4, 3: 2, 4: 3},
}
NIST_SUBCATEGORIES = {
    f"{function} {category}.{sub}"
    for function, categories in NIST_CATEGORIES.items()
    for category, count in categories.items()
    for sub in range(1, count + 1)
}
# ISO/IEC 42001:2023 Annex A: the last control in each objective (controls are numbered from .2).
ISO_OBJECTIVES = {
    "A.2": 4,
    "A.3": 3,
    "A.4": 6,
    "A.5": 5,
    "A.6.1": 3,
    "A.6.2": 8,
    "A.7": 6,
    "A.8": 5,
    "A.9": 4,
    "A.10": 4,
}
ISO_ANNEX_A = {f"{objective}.{n}" for objective, last in ISO_OBJECTIVES.items() for n in range(2, last + 1)}
ISO_CLAUSE = re.compile(r"^Clause (?:[4-9]|10)(?:\.\d+)*$")
EU_ARTICLE = re.compile(r"^Art\. (\d+)(?:\(\d+\))*$")
EU_ANNEX = re.compile(r"^Annex (?:I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|XIII)$")
EU_AI_ACT_ARTICLES = 113


def load(repo: Path, relative: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((repo / relative).read_text(encoding="utf-8"))
    return data


def all_mappings(policy: dict[str, Any]) -> list[dict[str, str]]:
    return [mapping for control in policy["controls"] for mapping in control.get("mappings", [])]


def test_reference_catalogues_are_complete() -> None:
    assert len(NIST_SUBCATEGORIES) == 72
    assert len(ISO_ANNEX_A) == 38


@pytest.mark.parametrize("relative", SHIPPED_POLICIES, ids=["default", "financial-services"])
def test_every_control_is_mapped_to_the_core_frameworks(repo: Path, relative: Path) -> None:
    policy = load(repo, relative)
    unmapped = [control["id"] for control in policy["controls"] if not control.get("mappings")]
    assert unmapped == []
    frameworks = {mapping["framework"] for mapping in all_mappings(policy)}
    assert {"EU AI Act", "NIST AI RMF 1.0", "ISO/IEC 42001:2023"} <= frameworks
    text = json.dumps(all_mappings(policy), ensure_ascii=False)
    assert text.isascii(), "mappings must stay ASCII so Markdown output is safe for legacy consoles"


@pytest.mark.parametrize("relative", SHIPPED_POLICIES, ids=["default", "financial-services"])
def test_references_are_real_identifiers(repo: Path, relative: Path) -> None:
    """Guard against typos and invented references in the frameworks with a fixed numbering."""
    for mapping in all_mappings(load(repo, relative)):
        framework, reference = mapping["framework"], mapping["reference"]
        if framework == "NIST AI RMF 1.0":
            assert reference in NIST_SUBCATEGORIES, reference
        elif framework == "ISO/IEC 42001:2023":
            assert reference in ISO_ANNEX_A or ISO_CLAUSE.match(reference), reference
        elif framework == "EU AI Act":
            article = EU_ARTICLE.match(reference)
            assert EU_ANNEX.match(reference) or (article and 1 <= int(article.group(1)) <= EU_AI_ACT_ARTICLES), (
                reference
            )


def test_financial_services_policy_covers_sector_regulations(repo: Path, risk_engine: ModuleType) -> None:
    policy = load(repo, FS_POLICY)
    frameworks = {mapping["framework"] for mapping in all_mappings(policy)}
    assert {"SR 26-2", "DORA", "ECOA / Regulation B", "SEC", "FINRA", "FCA Consumer Duty"} <= frameworks

    result = risk_engine.classify(policy, {"customer_facing": True, "consequential_decisions": True})
    controls = {control["id"]: control for control in result["required_controls"]}
    validation = controls["MRM-01"]["mappings"][0]
    assert (validation["framework"], validation["reference"]) == ("SR 26-2", "V. Model validation and monitoring")
    adverse_action = {(m["framework"], m["reference"]) for m in controls["TRN-03"]["mappings"]}
    assert ("ECOA / Regulation B", "12 CFR 1002.9") in adverse_action
    records = {(m["framework"], m["reference"]) for m in controls["OPS-07"]["mappings"]}
    assert {("SEC", "Rule 17a-4(b)(4)"), ("FINRA", "Rule 4511")} <= records


@pytest.mark.parametrize("relative", SHIPPED_POLICIES, ids=["default", "financial-services"])
def test_superseded_guidance_is_not_cited(repo: Path, relative: Path) -> None:
    """SR 26-2 replaced SR 11-7 in April 2026; the CFPB withdrew Circular 2022-03 in May 2025."""
    cited = {(m["framework"], m["reference"]) for m in all_mappings(load(repo, relative))}
    assert not {framework for framework, _ in cited} & {"SR 11-7", "OCC 2011-12"}
    assert not {reference for _, reference in cited} & {"CFPB Circular 2022-03"}


def test_required_controls_carry_their_mappings(risk_engine: ModuleType, policy: dict[str, Any]) -> None:
    result = risk_engine.classify(policy, {"consequential_decisions": True})
    assert all(isinstance(control["mappings"], list) for control in result["required_controls"])
    fairness = next(control for control in result["required_controls"] if control["id"] == "EVAL-03")
    assert {"framework": "NIST AI RMF 1.0", "reference": "MEASURE 2.11"}.items() <= fairness["mappings"][1].items()
    assert risk_engine.MAPPINGS_NOTE in result["notes"]


def test_markdown_lists_mappings_with_a_disclaimer(risk_engine: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    code = risk_engine.main(["--answers-json", json.dumps({"consequential_decisions": True}), "--format", "md"])
    out = capsys.readouterr().out
    assert code == 0
    assert "| Control | Name | Required by | Evidence | Maps to |" in out
    assert "| EVAL-03 | Fairness evaluation |" in out
    assert "NIST AI RMF 1.0 MEASURE 2.11" in out
    assert "not legal advice" in out
    assert out.isascii()


def test_policy_without_mappings_renders_as_before(risk_engine: ModuleType, policy: dict[str, Any]) -> None:
    for control in policy["controls"]:
        control.pop("mappings", None)
    result = risk_engine.classify(policy, {"customer_facing": True})
    assert all(control["mappings"] == [] for control in result["required_controls"])
    assert risk_engine.MAPPINGS_NOTE not in result["notes"]
    out = risk_engine.render_markdown(result)
    assert "| Control | Name | Required by | Evidence |\n|---|---|---|---|\n" in out
    assert "Maps to" not in out


def test_prohibited_tier_has_no_mapping_note(risk_engine: ModuleType, policy: dict[str, Any]) -> None:
    result = risk_engine.classify(policy, {"prohibited_practices": ["social_scoring"]})
    assert result["required_controls"] == []
    assert risk_engine.MAPPINGS_NOTE not in result["notes"]


@pytest.mark.parametrize(
    ("mappings", "message"),
    [
        ("EU AI Act Art. 14", "'mappings' must be a list"),
        ([{"framework": "EU AI Act"}], "mapping #0 needs"),
        ([{"framework": "EU AI Act", "reference": ""}], "mapping #0 needs"),
        ([{"framework": "EU AI Act", "reference": "Art. 14", "note": 14}], "mapping #0 needs"),
    ],
)
def test_engine_rejects_malformed_mappings(
    risk_engine: ModuleType, policy: dict[str, Any], mappings: Any, message: str
) -> None:
    policy["controls"][0]["mappings"] = mappings
    problems = risk_engine.validate_policy(policy)
    assert any(f"control '{policy['controls'][0]['id']}'" in p and message in p for p in problems), problems


def test_schema_rejects_unknown_mapping_fields(policy: dict[str, Any]) -> None:
    policy["controls"][0]["mappings"] = [{"framework": "EU AI Act", "reference": "Art. 14", "url": "https://x"}]
    assert any("controls/0/mappings/0" in p and "url" in p for p in policy_problems(policy))
    policy["controls"][0]["mappings"] = [{"framework": "EU AI Act", "reference": "Art. 14", "note": "Human oversight"}]
    assert policy_problems(policy) == []


@pytest.mark.parametrize("relative", SHIPPED_POLICIES, ids=["default", "financial-services"])
def test_every_cited_framework_has_a_dated_official_source(repo: Path, relative: Path) -> None:
    """The skill cannot look anything up, so each framework carries its source and a last-verified date."""
    policy = load(repo, relative)
    catalogue = {framework["id"]: framework for framework in policy["frameworks"]}
    assert {mapping["framework"] for mapping in all_mappings(policy)} == set(catalogue)
    for framework in catalogue.values():
        assert framework["url"].startswith("https://"), framework["id"]
        verified = date.fromisoformat(framework["last_verified"])
        assert date(2026, 1, 1) <= verified <= date.today(), framework["id"]
    assert json.dumps(policy["frameworks"], ensure_ascii=False).isascii()


def test_results_name_the_sources_behind_the_required_controls(
    risk_engine: ModuleType, policy: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    result = risk_engine.classify(policy, {"consequential_decisions": True})
    sources = {source["id"]: source for source in result["sources"]}
    assert {"EU AI Act", "NIST AI RMF 1.0", "ISO/IEC 42001:2023", "GDPR"} <= set(sources)
    assert sources["EU AI Act"]["url"] == "https://eur-lex.europa.eu/eli/reg/2024/1689/oj"
    assert "2026/1744" in sources["EU AI Act"]["note"]
    assert risk_engine.SOURCES_NOTE in result["notes"]

    assert risk_engine.main(["--answers-json", json.dumps({"consequential_decisions": True}), "--format", "md"]) == 0
    out = capsys.readouterr().out
    assert "**Sources** (official text; facts as of the date each was last verified):" in out
    assert "https://eur-lex.europa.eu/eli/reg/2024/1689/oj (last verified " in out
    assert out.isascii()


def test_a_mapping_to_an_unlisted_framework_is_an_error(risk_engine: ModuleType, policy: dict[str, Any]) -> None:
    policy["controls"][0]["mappings"].append({"framework": "SOC 2", "reference": "CC6.1"})
    assert any("framework 'SOC 2', which is not in 'frameworks'" in p for p in risk_engine.validate_policy(policy))


def test_validate_warns_when_mappings_have_no_sources(tmp_path: Path, policy: dict[str, Any]) -> None:
    from ai_product_governance.validate import check_policy_file

    del policy["frameworks"]
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    findings = check_policy_file(path, "policy.json")
    assert [f.level for f in findings] == ["warning"]
    assert "no 'frameworks' list" in findings[0].message


def test_gate_3_regulatory_flags_carry_sources_and_dates(skill: Any) -> None:
    text = skill.read_reference("gate-3-risk-and-controls")
    section = text.split("## 6. Regulatory flags", 1)[1].split("## Exit criteria", 1)[0]
    flags = [line for line in section.splitlines() if line.startswith("- **")]
    assert len(flags) >= 6
    for flag in flags:
        assert "last verified 20" in flag or "no source is bundled" in flag or "maps none" in flag, flag
    assert "as of" in section and "from memory" in section
