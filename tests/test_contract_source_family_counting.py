"""Conformance tests for the source-family counting contract draft (0.1.0-draft).

Docs-and-fixtures only: this exercises contracts/source-family-counting/validate.py against the golden fixtures.
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
CONTRACT_DIR = ROOT / "contracts" / "source-family-counting"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # validate.py defines a dataclass; register before exec
    spec.loader.exec_module(module)
    return module


sfc = _load("sfc_validate", CONTRACT_DIR / "validate.py")


def _fixtures(kind):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((CONTRACT_DIR / "fixtures" / kind).glob("*.json"))]


VALID = _fixtures("valid")
INVALID = _fixtures("invalid")


def doc(fixture_id):
    return copy.deepcopy(next(f for f in VALID if f["fixture_id"] == fixture_id)["document"])


def bad(fixture_id):
    return copy.deepcopy(next(f for f in INVALID if f["fixture_id"] == fixture_id)["document"])


def codes(d):
    return [v.code for v in sfc.validate(d)]


def test_fixture_sets_are_present_and_well_formed():
    assert len(VALID) >= 8 and len(INVALID) >= 21
    for fx in VALID + INVALID:
        assert fx["synthetic"] is True and fx["reason"].strip()
        assert fx["expected_outcome"] in {"accept", "reject"}
        assert fx["document"]["contract"] == "source-family-counting"
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
    assert sfc.validate(fx["document"]) == []


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
    d = doc("one-original-satisfies-one")
    d["injected_member"] = 1
    (violation,) = sfc.validate(d)
    assert violation.code == "undeclared_member" and violation.path.endswith("injected_member")


def test_extensions_are_preserved_and_bound_into_the_digest():
    d = doc("extension-namespace-members-preserved")
    assert sfc.preserve(d) == d
    stripped = json.loads(json.dumps(d))
    del stripped["extensions"]
    assert sfc.canonical_bytes(stripped) != sfc.canonical_bytes(d)
    # Ignore-but-preserve: the verdict does not depend on extension members.
    assert sfc.validate(stripped) == []
    assert "extensions" not in sfc.known_view(d)
    d["extensions"] = {"not-prefixed": 1}
    assert codes(d) == ["invalid_extension_key"]


def test_required_members_are_required():
    base = doc("one-original-satisfies-one")
    for member in ['contract', 'contract_version', 'profile', 'records', 'claims']:
        d = copy.deepcopy(base)
        del d[member]
        assert codes(d) == ["schema_violation"], member
    d = copy.deepcopy(base)
    d.pop("extensions", None)
    assert codes(d) == []


def test_unsupported_contract_version_is_refused_typed():
    d = doc("one-original-satisfies-one")
    d["contract_version"] = "9.0.0"
    assert codes(d) == ["unsupported_contract_version"]


def test_schema_is_draft_2020_12_and_agrees_with_reference_validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = sfc.load_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    validator_cls = jsonschema.Draft202012Validator
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    for fx in VALID:
        assert not list(validator.iter_errors(fx["document"])), fx["fixture_id"]
    structural = {"undeclared_member", "invalid_extension_key", "schema_violation", "unknown_enum_value",
                  "unsupported_contract_version"}
    for fx in INVALID:
        if fx["fixture_id"] == "unpaired-surrogate-text":
            continue  # text validity is a validator rule; the portable schema does not state it
        errors = list(validator.iter_errors(fx["document"]))
        assert bool(errors) == (fx["expected_refusal"] in structural), fx["fixture_id"]


def test_validator_cli_reads_fixtures(capsys):
    assert sfc.main([str(next((CONTRACT_DIR / "fixtures" / "valid").glob("*.json")))]) == 0
    assert sfc.main([str(next((CONTRACT_DIR / "fixtures" / "invalid").glob("*.json")))]) == 1
    assert capsys.readouterr().out.strip()


def test_contract_is_not_part_of_core_or_pder():
    """Optional extension profile: no core code path or pder-v0.1 file mentions it."""
    for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "profiles").rglob("*")):
        if path.is_file():
            assert "source-family-counting" not in path.read_text(encoding="utf-8", errors="ignore"), path


# ------------------------------------------------------------------ rule tests that need more than one mutation

def test_n_retries_of_one_message_count_as_one_confirmation():
    for n in (1, 2, 5, 50):
        records = [{"record_id": "m", "kind": "original", "family_id": "f", "derived_from": None}]
        records += [{"record_id": f"m-r{i}", "kind": "retry", "family_id": "f", "derived_from": "m"} for i in range(n)]
        ids = [r["record_id"] for r in records]
        d = doc("one-original-satisfies-one")
        d["records"] = records
        d["claims"] = [{"claim_id": "c", "required_families": 2, "confirmations": ids, "counted_families": 1, "satisfied": False}]
        assert codes(d) == [], n
        assert sfc.count_families(d, ids) == 1
        d["claims"][0].update(counted_families=len(ids), satisfied=len(ids) >= 2)
        assert codes(d) == ["family_count_mismatch"]


def test_family_helpers():
    d = doc("retries-plus-second-family-satisfies-two")
    assert sfc.family_of(d, "m-1-r2") == "fam-a" and sfc.family_of(d, "n-1") == "fam-b" and sfc.family_of(d, "absent") is None
    assert sfc.count_families(d, ["m-1", "m-1-r1", "n-1", "absent"]) == 2
    assert sfc.count_families(d, []) == 0


def test_inheritance_is_transitive():
    d = doc("resend-and-derived-inherit-the-family")
    assert {r["family_id"] for r in d["records"]} == {"fam-a"}
    d["records"][2]["family_id"] = "fam-z"  # derived from the re-send, which is fam-a
    assert codes(d) == ["family_not_inherited", "family_count_mismatch"]  # the count then also disagrees


def test_a_second_family_changes_the_outcome_not_a_second_record():
    d = doc("six-sends-of-one-message-count-one")
    assert d["claims"][0]["satisfied"] is False
    d["records"].append({"record_id": "n-1", "kind": "original", "family_id": "fam-b", "derived_from": None})
    d["claims"][0]["confirmations"].append("n-1")
    d["claims"][0].update(counted_families=2, satisfied=True)
    assert codes(d) == []


def test_the_family_of_an_original_is_declared_not_inferred():
    d = doc("two-originals-of-one-family-count-one")
    d["records"][1]["family_id"] = "fam-other"
    d["claims"][0].update(counted_families=2, satisfied=True)
    assert codes(d) == []


def test_unknown_confirmation_is_refused_not_ignored():
    d = doc("one-original-satisfies-one")
    d["claims"][0]["confirmations"].append("ghost")
    assert codes(d) == ["confirmation_dangling"]


def test_record_kinds_are_closed():
    assert sfc.load_schema()["$defs"]["record"]["properties"]["kind"]["enum"] == ["original", "retry", "resend", "derived"]


def test_headline_case_exists():
    ids = {f["fixture_id"] for f in INVALID}
    assert {"six-retries-counted-as-six", "retry-claims-a-new-family"} <= ids
