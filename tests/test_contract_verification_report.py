"""Conformance tests for the verification-report contract draft (0.1.0-draft).

Docs-and-fixtures only: this exercises contracts/verification-report/validate.py against the golden fixtures.
It does not import or alter the odes package.
"""
import copy
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "contracts" / "verification-report"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # validate.py defines a dataclass; register before exec
    spec.loader.exec_module(module)
    return module


vr = _load("vr_validate", CONTRACT_DIR / "validate.py")


def _fixtures(kind):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((CONTRACT_DIR / "fixtures" / kind).glob("*.json"))]


VALID = _fixtures("valid")
INVALID = _fixtures("invalid")


def doc(fixture_id):
    return copy.deepcopy(next(f for f in VALID if f["fixture_id"] == fixture_id)["document"])


def bad(fixture_id):
    return copy.deepcopy(next(f for f in INVALID if f["fixture_id"] == fixture_id)["document"])


def codes(d):
    return [v.code for v in vr.validate(d)]


def test_fixture_sets_are_present_and_well_formed():
    assert len(VALID) >= 8 and len(INVALID) >= 60
    for fx in VALID + INVALID:
        assert fx["synthetic"] is True and fx["reason"].strip()
        assert fx["expected_outcome"] in {"accept", "reject"}
        assert fx["document"]["contract"] == "verification-report"
        assert fx["document"]["contract_version"] == "0.1.0-draft" or fx["fixture_id"] == "unsupported-contract-version"
    assert all(f["expected_outcome"] == "accept" for f in VALID)
    assert all(f["expected_outcome"] == "reject" and f["expected_refusal"] for f in INVALID)
    names = [f["fixture_id"] for f in VALID + INVALID]
    assert len(names) == len(set(names))
    for kind in ("valid", "invalid"):
        for path in (CONTRACT_DIR / "fixtures" / kind).glob("*.json"):
            assert json.loads(path.read_text())["fixture_id"] == path.stem


@pytest.mark.parametrize("fx", VALID, ids=lambda f: f["fixture_id"])
def test_valid_fixture_is_accepted(fx):
    assert vr.validate(fx["document"]) == []


@pytest.mark.parametrize("fx", INVALID, ids=lambda f: f["fixture_id"])
def test_invalid_fixture_is_refused_with_stated_reason(fx):
    assert codes(fx["document"]) == [fx["expected_refusal"]], fx["reason"]


def test_every_rule_code_is_pinned_by_a_fixture_and_the_readme():
    """Every stable code the validator can emit is in the README and exercised by an invalid fixture."""
    source = (CONTRACT_DIR / "validate.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'_v\(\s*"([a-z_]+)"', source)) | set(re.findall(r'Violation\(\s*"([a-z_]+)"', source))
    covered = {f["expected_refusal"] for f in INVALID}
    assert emitted - covered == set(), emitted - covered
    readme = (CONTRACT_DIR / "README.md").read_text(encoding="utf-8")
    missing = sorted(c for c in emitted if f"`{c}`" not in readme)
    assert missing == [], missing


def test_unknown_member_is_refused_not_dropped():
    d = doc("trace-all-confirmed")
    d["injected_member"] = 1
    (violation,) = vr.validate(d)
    assert violation.code == "undeclared_member" and violation.path.endswith("injected_member")


def test_extensions_are_preserved_and_bound_into_the_digest():
    d = doc("extension-namespace-members-preserved")
    assert vr.preserve(d) == d
    stripped = json.loads(json.dumps(d))
    del stripped["extensions"]
    assert vr.canonical_bytes(stripped) != vr.canonical_bytes(d)
    # Ignore-but-preserve: the verdict does not depend on extension members.
    assert vr.validate(stripped) == []
    assert "extensions" not in vr.known_view(d)
    d["extensions"] = {"not-prefixed": 1}
    assert codes(d) == ["invalid_extension_key"]


def test_required_members_are_required():
    base = doc("trace-all-confirmed")
    for member in ['contract', 'contract_version', 'profile', 'report_kind', 'report_id', 'generated_at', 'verifier', 'subject', 'scope', 'checks', 'summary', 'does_not_prove', 'mutation_report']:
        d = copy.deepcopy(base)
        del d[member]
        assert codes(d) == ["schema_violation"], member
    d = copy.deepcopy(base)
    d.pop("extensions", None)
    assert codes(d) == []


def test_unsupported_contract_version_is_refused_typed():
    d = doc("trace-all-confirmed")
    d["contract_version"] = "9.0.0"
    assert codes(d) == ["unsupported_contract_version"]


def test_schema_is_draft_2020_12_and_agrees_with_reference_validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = vr.load_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    validator_cls = jsonschema.Draft202012Validator
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    for fx in VALID:
        assert not list(validator.iter_errors(fx["document"])), fx["fixture_id"]
    structural = {"undeclared_member", "invalid_extension_key", "schema_violation", "unknown_enum_value",
                  "unsupported_contract_version"}
    for fx in INVALID:
        errors = list(validator.iter_errors(fx["document"]))
        assert bool(errors) == (fx["expected_refusal"] in structural), fx["fixture_id"]


def test_validator_cli_reads_fixtures(capsys):
    assert vr.main([str(next((CONTRACT_DIR / "fixtures" / "valid").glob("*.json")))]) == 0
    assert vr.main([str(next((CONTRACT_DIR / "fixtures" / "invalid").glob("*.json")))]) == 1
    assert capsys.readouterr().out.strip()


def test_contract_is_not_part_of_core_or_pder():
    """Optional extension profile: no core code path or pder-v0.1 file mentions it."""
    for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "profiles").rglob("*")):
        if path.is_file():
            assert "verification-report" not in path.read_text(encoding="utf-8", errors="ignore"), path


# ------------------------------------------------------------------ rule tests that need more than one mutation

def fx(fixture_id, kind=VALID):
    return copy.deepcopy(next(f for f in kind if f["fixture_id"] == fixture_id)["document"])


def test_overall_verdict_is_derived_three_valued_and_not_a_member():
    assert vr.overall_verdict(fx("trace-all-confirmed")) == "accept"
    assert vr.overall_verdict(fx("trace-could-not-check")) == "abstain"
    assert vr.overall_verdict(fx("trace-refuted-with-findings")) == "reject"
    assert vr.overall_verdict(fx("trace-three-verdicts")) == "reject"  # refuted outranks could_not_check
    assert "overall_verdict" not in vr.load_schema()["properties"]


def test_check_verdict_derivation():
    t = {"confirmed": 1, "could_not_check": 0, "refuted": 0, "n": 1}
    assert vr.derived_check_verdict(t) == "confirmed"
    assert vr.derived_check_verdict({**t, "could_not_check": 1, "n": 2}) == "could_not_check"
    assert vr.derived_check_verdict({**t, "could_not_check": 1, "refuted": 1, "n": 3}) == "refuted"


def test_no_composite_score_and_no_attestation_vocabulary_in_the_schema():
    schema = vr.load_schema()
    names = set()

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.get("properties", {}).items():
                names.add(key)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    assert not {n for n in names if "score" in n or "attest" in n or "rate" == n or "grade" in n or "overall" in n}, names
    assert schema["properties"]["report_kind"] == {"const": "verification_report"}


def test_every_number_in_a_mutation_report_is_a_count_or_a_k_over_n():
    """No float anywhere in a valid mutation report: figures are integers and k/n objects."""
    def walk(node):
        if isinstance(node, float):
            raise AssertionError(node)
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    for f in VALID:
        walk(f["document"])


def test_zero_denominator_reads_na_never_a_percentage():
    assert vr.render_fraction({"k": 0, "n": 0}).startswith("n/a")
    assert vr.render_fraction({"k": 3, "n": 4}) == "3/4"
    row = next(r for r in fx("mutation-report-full")["mutation_report"]["family_t"][1]["categories"] if r["category"] == "W1")
    assert row["metric_impact"]["changed"] == {"k": None, "n": 0}


def test_abstain_and_error_are_not_credited_as_detection():
    d = fx("mutation-report-full")
    row = next(r for r in d["mutation_report"]["family_t"][1]["categories"] if r["category"] == "D1")
    assert row["verdicts"]["abstain"] == 1 and row["detection"]["any_code"]["k"] == row["verdicts"]["reject"] == 19
    row = next(r for r in d["mutation_report"]["family_t"][1]["categories"] if r["category"] == "R5")
    assert row["verdicts"]["error"] == 1 and row["detection"]["any_code"] == {"k": 9, "n": 10}


def test_expected_accept_categories_and_q_are_printed():
    cats = {r["category"]: r for r in fx("mutation-report-full")["mutation_report"]["family_t"][1]["categories"]}
    for c in ("F", "R6", "B"):
        assert cats[c]["expected_verdict"] == "accept"
    assert cats["Q"]["expected_verdict"] == "not_applicable" and cats["Q"]["detection"] is None


def test_families_and_clean_corpora_live_in_separate_lists():
    m = fx("mutation-report-full")["mutation_report"]
    assert set(m) >= {"family_t", "family_s", "clean"}
    assert m["family_s"][0]["context_only"] is True
    # family S rows have their own shape (cases, detected, survived, errored); a family T row in family S is refused
    d = fx("mutation-report-full")
    d["mutation_report"]["family_s"][0]["rows"] = [d["mutation_report"]["family_t"][1]["categories"][0]]
    assert "undeclared_member" in codes(d) or "schema_violation" in codes(d)
    # and the reverse
    d = fx("mutation-report-full")
    d["mutation_report"]["family_t"][1]["categories"] = d["mutation_report"]["family_s"][0]["rows"]
    assert codes(d)


def test_pooling_by_a_total_row_is_not_expressible():
    """Rows are per corpus and per category; the schema has no total, pooled or average member."""
    schema = vr.load_schema()
    names = {k for d in schema["$defs"].values() if isinstance(d, dict) for k in d.get("properties", {})}
    for word in ("total", "pooled", "average", "mean", "composite"):
        assert not any(word in n for n in names), word


def test_summary_is_counts_over_checks():
    d = fx("trace-three-verdicts")
    assert d["summary"] == {"checks": 3, "confirmed": 2, "could_not_check": 0, "refuted": 1}


def test_subject_digest_binds_the_inputs_and_the_pinned_profile():
    d = fx("trace-all-confirmed")
    assert d["subject"]["inputs_digest"] == vr.commitment(d["subject"]["inputs"])
    assert d["subject"]["canonicalization_profile"] == vr.CANONICALIZATION_PROFILE
    assert vr.CANONICALIZATION_PROFILE == "json-sort-keys-compact-utf8-no-nan-python-semantics-v0.1"
    d["subject"]["inputs"][0]["size_bytes"] += 1
    assert codes(d) == ["subject_digest_mismatch"]


def test_every_non_claim_is_in_the_schema_set_and_the_readme():
    schema = vr.load_schema()
    ids = schema["$defs"]["non_claim"]["properties"]["id"]["enum"]
    assert set(ids) == set(vr.CORE_NON_CLAIMS) | set(vr.MUTATION_NON_CLAIMS) | set(vr.V3_NON_CLAIMS) and len(ids) == 11
    readme = (CONTRACT_DIR / "README.md").read_text(encoding="utf-8")
    for i in ids:
        assert f"`{i}`" in readme


def test_the_mutation_non_claims_are_required_only_with_a_mutation_report():
    d = fx("trace-all-confirmed")
    assert {n["id"] for n in d["does_not_prove"]} == set(vr.CORE_NON_CLAIMS)
    assert {n["id"] for n in fx("mutation-report-full")["does_not_prove"]} == set(vr.CORE_NON_CLAIMS) | set(vr.MUTATION_NON_CLAIMS)


def test_category_set_is_the_design_catalogue():
    cats = vr.load_schema()["$defs"]["category"]["enum"]
    assert len(cats) == len(set(cats)) == 36
    for c in ("W1", "W5", "B", "S1", "I5", "D5", "J3", "T1", "A2", "R6", "X1", "L1", "F", "Q"):
        assert c in cats


def test_mutation_report_gates_nothing():
    assert vr.load_schema()["$defs"]["mutation_report"]["properties"]["report_only"] == {"const": True}


# ------------------------------------------------------------------ tier V3 (draft revision 2026-10-18, decision 27)

V3_FIXTURES = ("v3-witness-complete", "v3-witness-first-publication-only", "v3-witness-and-holder-inventory",
               "v3-held-for-missing-inventory", "v3-witness-refutes-damaged-record")


def test_tier_v3_and_the_two_input_roles_are_in_the_closed_sets():
    schema = vr.load_schema()
    assert schema["$defs"]["scope"]["properties"]["tiers_run"]["items"]["enum"] == ["V1", "V2", "V3", "V4"]
    assert schema["$defs"]["check"]["properties"]["tier"]["enum"] == ["V1", "V2", "V3", "V4"]
    roles = schema["$defs"]["input"]["properties"]["role"]["enum"]
    assert set(vr.V3_INPUT_ROLES) <= set(roles) and len(roles) == 8
    d = doc("trace-all-confirmed")
    d["scope"]["tiers_run"].append("V5")
    assert codes(d) == ["unknown_enum_value"]


def test_v3_fixtures_are_captured_reports_with_v3_inside_checks():
    for fid in V3_FIXTURES:
        d = fx(fid)
        assert "V3" in d["scope"]["tiers_run"]
        assert any(c["tier"] == "V3" for c in d["checks"])
        assert "x-tier-v3" not in d.get("extensions", {}), fid      # the section moved into checks
        assert {i["role"] for i in d["subject"]["inputs"]} & set(vr.V3_INPUT_ROLES)
        assert d["summary"]["checks"] == len(d["checks"])             # V3 checks are counted like any other
        assert "witness_is_not_publication" in {n["id"] for n in d["does_not_prove"]}
        assert not any("score" in k for k in d["summary"])
        assert vr.validate(d) == []


def test_v3_verdicts_are_derived_like_any_other_check():
    refuted = fx("v3-witness-refutes-damaged-record")
    head = next(c for c in refuted["checks"] if c["check_id"] == "v3.witness.ledger-heads")
    assert head["verdict"] == "refuted" and head["findings"][0]["code"] == "witness_ledger_shrunk"
    assert vr.overall_verdict(refuted) == "reject"
    first = fx("v3-witness-first-publication-only")
    cov = next(c for c in first["checks"] if c["check_id"] == "v3.witness.coverage")
    assert cov["verdict"] == "could_not_check" and cov["could_not_check_reason"] == "input_absent"
    complete = fx("v3-witness-complete")
    assert {c["verdict"] for c in complete["checks"] if c["tier"] == "V3"} == {"confirmed"}


def test_v3_requires_an_outside_input_and_an_input_requires_v3():
    d = fx("v3-witness-complete")
    d["subject"]["inputs"] = [i for i in d["subject"]["inputs"] if i["role"] != "witness"]
    d["subject"]["inputs_digest"] = vr.commitment(d["subject"]["inputs"])
    assert codes(d) == ["v3_input_missing"]
    # a holder inventory alone also licenses V3 (its checks are about the inventory, not the witness)
    d = fx("v3-witness-and-holder-inventory")
    d["subject"]["inputs"] = [i for i in d["subject"]["inputs"] if i["role"] != "witness"]
    d["subject"]["inputs_digest"] = vr.commitment(d["subject"]["inputs"])
    assert codes(d) == []
    d = fx("v3-witness-complete")
    d["scope"]["tiers_run"].remove("V3")
    assert "v3_input_without_tier" in codes(d) and "check_tier_not_run" in codes(d)


def test_the_v3_non_claim_is_required_only_when_v3_ran():
    d = fx("trace-all-confirmed")
    assert "witness_is_not_publication" not in {n["id"] for n in d["does_not_prove"]}
    d = fx("v3-witness-complete")
    d["does_not_prove"] = [n for n in d["does_not_prove"] if n["id"] != "witness_is_not_publication"]
    assert codes(d) == ["non_claim_missing"]


def test_every_default_path_fixture_that_predates_the_revision_is_unchanged():
    """The hand-written valid fixtures and every invalid fixture except the V3 ones kept their documents (the one that changed is
    named: `tier-v3-claimed` became `tier-v3-claimed-without-input`)."""
    ids = {f["fixture_id"] for f in INVALID}
    assert "tier-v3-claimed" not in ids and "tier-v3-claimed-without-input" in ids
    for fid in ("trace-all-confirmed", "trace-could-not-check", "trace-refuted-with-findings", "trace-three-verdicts",
                "mutation-report-full", "mutation-report-with-per-scenario-tables", "trace-with-mutation-report",
                "extension-namespace-members-preserved"):
        assert "V3" not in fx(fid)["scope"]["tiers_run"]
