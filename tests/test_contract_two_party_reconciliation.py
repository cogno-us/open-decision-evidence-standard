"""Conformance tests for the two-party reconciliation contract draft (0.1.0-draft).

Docs-and-fixtures only: this exercises contracts/two-party-reconciliation/validate.py against the golden fixtures.
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
CONTRACT_DIR = ROOT / "contracts" / "two-party-reconciliation"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # validate.py defines a dataclass; register before exec
    spec.loader.exec_module(module)
    return module


tpr = _load("tpr_validate", CONTRACT_DIR / "validate.py")


def _fixtures(kind):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((CONTRACT_DIR / "fixtures" / kind).glob("*.json"))]


VALID = _fixtures("valid")
INVALID = _fixtures("invalid")


def doc(fixture_id):
    return copy.deepcopy(next(f for f in VALID if f["fixture_id"] == fixture_id)["document"])


def bad(fixture_id):
    return copy.deepcopy(next(f for f in INVALID if f["fixture_id"] == fixture_id)["document"])


def codes(d):
    return [v.code for v in tpr.validate(d)]


def test_fixture_sets_are_present_and_well_formed():
    assert len(VALID) >= 7 and len(INVALID) >= 26
    for fx in VALID + INVALID:
        assert fx["synthetic"] is True and fx["reason"].strip()
        assert fx["expected_outcome"] in {"accept", "reject"}
        assert fx["document"]["contract"] == "two-party-reconciliation"
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
    assert tpr.validate(fx["document"]) == []


@pytest.mark.parametrize("fx", INVALID, ids=lambda f: f["fixture_id"])
def test_invalid_fixture_is_refused_with_stated_reason(fx):
    assert codes(fx["document"]) == [fx["expected_refusal"]], fx["reason"]


def test_every_rule_code_is_pinned_by_a_fixture_and_the_readme():
    """Every stable code the validator can emit is in the README and exercised by an invalid fixture."""
    source = (CONTRACT_DIR / "validate.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'_v\(\s*"([a-z_]+)"', source)) | set(re.findall(r'Violation\(\s*"([a-z_]+)"', source))
    if '"enum"' not in (CONTRACT_DIR / "schema.json").read_text(encoding="utf-8"):
        emitted.discard("unknown_enum_value")  # the structural interpreter can emit it; this schema declares no enumeration
    covered = {f["expected_refusal"] for f in INVALID}
    assert emitted - covered == set(), emitted - covered
    readme = (CONTRACT_DIR / "README.md").read_text(encoding="utf-8")
    missing = sorted(c for c in emitted if f"`{c}`" not in readme)
    assert missing == [], missing


def test_unknown_member_is_refused_not_dropped():
    d = doc("matched-and-committed")
    d["injected_member"] = 1
    (violation,) = tpr.validate(d)
    assert violation.code == "undeclared_member" and violation.path.endswith("injected_member")


def test_extensions_are_preserved_and_bound_into_the_digest():
    d = doc("extension-namespace-members-preserved")
    assert tpr.preserve(d) == d
    stripped = json.loads(json.dumps(d))
    del stripped["extensions"]
    assert tpr.canonical_bytes(stripped) != tpr.canonical_bytes(d)
    # Ignore-but-preserve: the verdict does not depend on extension members.
    assert tpr.validate(stripped) == []
    assert "extensions" not in tpr.known_view(d)
    d["extensions"] = {"not-prefixed": 1}
    assert codes(d) == ["invalid_extension_key"]


def test_required_members_are_required():
    base = doc("matched-and-committed")
    for member in ['contract', 'contract_version', 'profile', 'reconciliations']:
        d = copy.deepcopy(base)
        del d[member]
        assert codes(d) == ["schema_violation"], member
    d = copy.deepcopy(base)
    d.pop("extensions", None)
    assert codes(d) == []


def test_unsupported_contract_version_is_refused_typed():
    d = doc("matched-and-committed")
    d["contract_version"] = "9.0.0"
    assert codes(d) == ["unsupported_contract_version"]


def test_schema_is_draft_2020_12_and_agrees_with_reference_validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = tpr.load_schema()
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
    assert tpr.main([str(next((CONTRACT_DIR / "fixtures" / "valid").glob("*.json")))]) == 0
    assert tpr.main([str(next((CONTRACT_DIR / "fixtures" / "invalid").glob("*.json")))]) == 1
    assert capsys.readouterr().out.strip()


def test_contract_is_not_part_of_core_or_pder():
    """Optional extension profile: no core code path or pder-v0.1 file mentions it."""
    for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "profiles").rglob("*")):
        if path.is_file():
            assert "two-party-reconciliation" not in path.read_text(encoding="utf-8", errors="ignore"), path


# ------------------------------------------------------------------ rule tests that need more than one mutation

def test_headline_case_exists_and_is_the_only_refusal():
    fx = next(f for f in INVALID if f["fixture_id"] == "mismatch-committed-as-two-valid-records")
    assert codes(fx["document"]) == ["mismatch_committed"]


def test_changing_one_digest_flips_a_committed_match_to_a_refusal():
    d = doc("matched-and-committed")
    assert tpr.validate(d) == [] and tpr.committed_events(d) == ["evt-refund-1"]
    d["reconciliations"][0]["receiver"]["event_digest"] = tpr.commitment({"other": 1}) if hasattr(tpr, "commitment") else "sha256:" + "0" * 64
    assert sorted(codes(d)) == ["mismatch_committed", "outcome_digest_inconsistent"]


def test_surfacing_the_mismatch_is_valid_and_the_event_stays_open():
    d = doc("mismatch-surfaced-not-committed")
    assert tpr.validate(d) == []
    assert tpr.committed_events(d) == [] and tpr.open_events(d) == ["evt-refund-1"]


def test_ambiguous_delivery_never_commits_and_stays_open():
    d = doc("ambiguous-delivery-sender-only")
    assert tpr.committed_events(d) == [] and tpr.open_events(d) == ["evt-refund-1"]
    d["reconciliations"][0]["outcome"] = "matched"
    assert "outcome_records_inconsistent" in codes(d)


def test_mixed_document_partitions_events():
    d = doc("several-events-mixed")
    assert tpr.committed_events(d) == ["evt-1"]
    assert tpr.open_events(d) == ["evt-2", "evt-3"]


def test_commit_at_the_comparison_instant_is_allowed_and_one_second_earlier_is_not():
    d = doc("matched-and-committed")
    row = d["reconciliations"][0]
    row["commit"]["committed_at"] = row["compared_at"]
    assert codes(d) == []
    row["commit"]["committed_at"] = "2026-10-17T10:00:04+00:00"
    assert codes(d) == ["commit_before_comparison"]


def test_disposition_is_never_accept():
    schema = tpr.load_schema()
    assert schema["$defs"]["mismatch"]["properties"]["disposition"]["enum"] == ["hold", "escalate"]


def test_ambiguous_delivery_mapping_is_documented():
    readme = (CONTRACT_DIR / "README.md").read_text(encoding="utf-8")
    assert "D04" in readme and "awaiting_peer" in readme and "ambiguous delivery" in readme
