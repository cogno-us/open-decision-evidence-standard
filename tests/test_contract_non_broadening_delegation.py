"""Conformance tests for the non-broadening delegation contract draft (0.1.0-draft).

Docs-and-fixtures only: this exercises contracts/non-broadening-delegation/validate.py against the golden fixtures.
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
CONTRACT_DIR = ROOT / "contracts" / "non-broadening-delegation"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # validate.py defines a dataclass; register before exec
    spec.loader.exec_module(module)
    return module


nbd = _load("nbd_validate", CONTRACT_DIR / "validate.py")


def _fixtures(kind):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((CONTRACT_DIR / "fixtures" / kind).glob("*.json"))]


VALID = _fixtures("valid")
INVALID = _fixtures("invalid")


def doc(fixture_id):
    return copy.deepcopy(next(f for f in VALID if f["fixture_id"] == fixture_id)["document"])


def bad(fixture_id):
    return copy.deepcopy(next(f for f in INVALID if f["fixture_id"] == fixture_id)["document"])


def codes(d):
    return [v.code for v in nbd.validate(d)]


def test_fixture_sets_are_present_and_well_formed():
    assert len(VALID) >= 7 and len(INVALID) >= 23
    for fx in VALID + INVALID:
        assert fx["synthetic"] is True and fx["reason"].strip()
        assert fx["expected_outcome"] in {"accept", "reject"}
        assert fx["document"]["contract"] == "non-broadening-delegation"
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
    assert nbd.validate(fx["document"]) == []


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
    d = doc("delegation-equal-bounds")
    d["injected_member"] = 1
    (violation,) = nbd.validate(d)
    assert violation.code == "undeclared_member" and violation.path.endswith("injected_member")


def test_extensions_are_preserved_and_bound_into_the_digest():
    d = doc("extension-namespace-members-preserved")
    assert nbd.preserve(d) == d
    stripped = json.loads(json.dumps(d))
    del stripped["extensions"]
    assert nbd.canonical_bytes(stripped) != nbd.canonical_bytes(d)
    # Ignore-but-preserve: the verdict does not depend on extension members.
    assert nbd.validate(stripped) == []
    assert "extensions" not in nbd.known_view(d)
    d["extensions"] = {"not-prefixed": 1}
    assert codes(d) == ["invalid_extension_key"]


def test_required_members_are_required():
    base = doc("delegation-equal-bounds")
    for member in ['contract', 'contract_version', 'profile', 'grants']:
        d = copy.deepcopy(base)
        del d[member]
        assert codes(d) == ["schema_violation"], member
    d = copy.deepcopy(base)
    d.pop("extensions", None)
    assert codes(d) == []


def test_unsupported_contract_version_is_refused_typed():
    d = doc("delegation-equal-bounds")
    d["contract_version"] = "9.0.0"
    assert codes(d) == ["unsupported_contract_version"]


def test_schema_is_draft_2020_12_and_agrees_with_reference_validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = nbd.load_schema()
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
    assert nbd.main([str(next((CONTRACT_DIR / "fixtures" / "valid").glob("*.json")))]) == 0
    assert nbd.main([str(next((CONTRACT_DIR / "fixtures" / "invalid").glob("*.json")))]) == 1
    assert capsys.readouterr().out.strip()


def test_contract_is_not_part_of_core_or_pder():
    """Optional extension profile: no core code path or pder-v0.1 file mentions it."""
    for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "profiles").rglob("*")):
        if path.is_file():
            assert "non-broadening-delegation" not in path.read_text(encoding="utf-8", errors="ignore"), path


# ------------------------------------------------------------------ rule tests that need more than one mutation

def test_required_cases_exist():
    ids = {f["fixture_id"] for f in INVALID}
    assert {"broadened-amount", "window-expires-later", "widened-data-scope", "depth-exhausted", "missing-parent", "cycle"} <= ids


def test_chain_helper_returns_root_first():
    d = doc("two-level-chain-depth-exhausts")
    assert nbd.chain(d, "urn:grant:grandchild") == ["urn:grant:root", "urn:grant:child", "urn:grant:grandchild"]
    assert nbd.chain(d, "urn:grant:root") == ["urn:grant:root"]
    assert nbd.chain(d, "urn:grant:absent") == []


def test_every_edge_bound_is_independently_enforced():
    base = doc("delegation-equal-bounds")
    child = base["grants"][1]["permissions"][0]
    for member, value, code in (("max_amount", 100.01, "amount_broadened"), ("max_effects", 4, "effects_broadened"),
                                ("unit", "EUR", "unit_changed"), ("action", "other", "scope_widened"),
                                ("targets", ["acct-1", "acct-3"], "scope_widened"), ("data_scopes", ["x"], "scope_widened")):
        d = copy.deepcopy(base)
        d["grants"][1]["permissions"][0][member] = value
        assert codes(d) == [code], member
    d = copy.deepcopy(base)
    d["grants"][1]["permissions"][0]["max_amount"] = 100  # integer equal to the float bound is not broader
    assert codes(d) == []


def test_pooling_across_parent_permissions_is_refused():
    d = doc("child-permission-fits-second-parent-permission")
    # An amount above either single parent permission of the same action cannot be assembled from two.
    d["grants"][1]["permissions"][0]["max_amount"] = 60.0
    assert codes(d) == ["amount_broadened"]


def test_window_is_checked_at_both_ends_and_equality_passes():
    d = doc("delegation-equal-bounds")
    assert codes(d) == []
    d["grants"][1]["not_before"] = "2026-09-30T23:59:59+00:00"
    assert codes(d) == ["window_extended"]
    d = doc("delegation-equal-bounds")
    d["grants"][1]["expires_at"] = "2026-10-31T00:00:01+00:00"
    assert codes(d) == ["window_extended"]
    d = doc("delegation-equal-bounds")  # same instant written with another offset is equal
    d["grants"][1]["expires_at"] = "2026-10-31T02:00:00+02:00"
    assert codes(d) == []


def test_depth_chain_must_strictly_decrease():
    d = doc("two-level-chain-depth-exhausts")
    assert [g["delegation"]["remaining_depth"] for g in d["grants"]] == [2, 1, 0]
    d["grants"][2]["delegation"].update(may_delegate=True, remaining_depth=1)
    assert codes(d) == ["depth_not_decreased"]
    d = doc("two-level-chain-depth-exhausts")
    d["grants"][1]["delegation"].update(may_delegate=False, remaining_depth=0)
    d["grants"][2]["delegation"].update(may_delegate=False, remaining_depth=0)
    assert codes(d) == ["depth_exhausted"]


def test_a_three_cycle_is_reported_once_and_edge_rules_are_skipped():
    d = doc("two-level-chain-depth-exhausts")
    d["grants"][0]["delegation"]["parent_grant_id"] = "urn:grant:grandchild"
    assert codes(d) == ["delegation_cycle"]


def test_a_cycle_does_not_hide_a_broadening_outside_it():
    d = bad("cycle")
    extra = copy.deepcopy(d["grants"][0])
    extra.update(grant_id="urn:grant:tail", issuer="urn:principal:a", grantee="urn:principal:z")
    extra["delegation"].update(parent_grant_id="urn:grant:a", may_delegate=False, remaining_depth=0)
    extra["permissions"][0]["max_amount"] = 1000.0
    d["grants"].append(extra)
    assert sorted(codes(d)) == ["amount_broadened", "delegation_cycle"]


def test_the_profile_marker_is_exact():
    d = doc("delegation-equal-bounds")
    d["profile"] = "non-broadening-delegation/0.2"
    assert codes(d) == ["schema_violation"]


def test_current_refusal_is_documented_and_not_claimed_as_support():
    readme = (CONTRACT_DIR / "README.md").read_text(encoding="utf-8")
    assert "delegation_profile_unsupported" in readme and "does NOT support delegation" in readme
    assert "C18" in readme
