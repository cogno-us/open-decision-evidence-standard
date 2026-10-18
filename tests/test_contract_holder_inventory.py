"""Conformance tests for the holder-inventory contract draft (0.1.0-draft).

Docs-and-fixtures only: this exercises contracts/holder-inventory/validate.py against the golden fixtures. It does not import or
alter the odes package and does not read the Control Plane or the verifier.
"""
import copy
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "contracts" / "holder-inventory"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # validate.py defines a dataclass; register before exec
    spec.loader.exec_module(module)
    return module


hi = _load("hi_validate", CONTRACT_DIR / "validate.py")


def _fixtures(kind):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((CONTRACT_DIR / "fixtures" / kind).glob("*.json"))]


VALID = _fixtures("valid")
INVALID = _fixtures("invalid")


def doc(fixture_id):
    return copy.deepcopy(next(f for f in VALID if f["fixture_id"] == fixture_id)["document"])


def codes(d):
    return [v.code for v in hi.validate(d)]


def test_fixture_sets_are_present_and_well_formed():
    assert len(VALID) >= 6 and len(INVALID) >= 16
    for fx in VALID + INVALID:
        assert fx["synthetic"] is True and fx["reason"].strip() and fx["provenance"]["source"]
        assert fx["expected_outcome"] in {"accept", "reject"}
    assert all(f["expected_outcome"] == "accept" and f["expected_refusal"] is None for f in VALID)
    assert all(f["expected_outcome"] == "reject" and f["expected_refusal"] for f in INVALID)
    names = [f["fixture_id"] for f in VALID + INVALID]
    assert len(names) == len(set(names))
    for kind in ("valid", "invalid"):
        for path in (CONTRACT_DIR / "fixtures" / kind).glob("*.json"):
            assert json.loads(path.read_text(encoding="utf-8"))["fixture_id"] == path.stem


def test_the_two_captured_inventories_are_unchanged_producer_output_and_the_rest_are_derived():
    captured = [f["fixture_id"] for f in VALID if "derived" not in f["provenance"]]
    assert captured == ["enumerates-no-holder", "two-holders-routed-and-self-credentialed"]
    assert all("DERIVED" in f["reason"] for f in VALID if "derived" in f["provenance"])


@pytest.mark.parametrize("fx", VALID, ids=lambda f: f["fixture_id"])
def test_valid_fixture_is_accepted(fx):
    assert hi.validate(fx["document"]) == []


@pytest.mark.parametrize("fx", INVALID, ids=lambda f: f["fixture_id"])
def test_invalid_fixture_is_refused_with_stated_reason(fx):
    assert codes(fx["document"]) == [fx["expected_refusal"]], fx["reason"]


def test_every_rule_code_is_pinned_by_a_fixture_and_the_readme():
    source = (CONTRACT_DIR / "validate.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'_v\(\s*"([a-z_]+)"', source)) | set(re.findall(r'Violation\(\s*"([a-z_]+)"', source))
    covered = {f["expected_refusal"] for f in INVALID}
    assert emitted - covered == set(), emitted - covered
    readme = (CONTRACT_DIR / "README.md").read_text(encoding="utf-8")
    missing = sorted(c for c in emitted if f"`{c}`" not in readme)
    assert missing == [], missing


def test_schema_is_draft_2020_12_and_agrees_with_reference_validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = hi.load_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    validator_cls = jsonschema.Draft202012Validator
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    for fx in VALID:
        assert not list(validator.iter_errors(fx["document"])), fx["fixture_id"]
    structural = {"undeclared_member", "invalid_extension_key", "schema_violation", "unknown_enum_value", "unsupported_contract_version"}
    for fx in INVALID:
        if fx["fixture_id"] == "unpaired-surrogate-text":
            continue  # text validity is a validator rule; the portable schema does not state it
        errors = list(validator.iter_errors(fx["document"]))
        assert bool(errors) == (fx["expected_refusal"] in structural), fx["fixture_id"]


def test_validator_cli_reads_fixtures(capsys):
    assert hi.main([str(next((CONTRACT_DIR / "fixtures" / "valid").glob("*.json")))]) == 0
    assert hi.main([str(next((CONTRACT_DIR / "fixtures" / "invalid").glob("*.json")))]) == 1
    assert capsys.readouterr().out.strip()


def test_contract_is_not_part_of_core_or_pder():
    for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "profiles").rglob("*")):
        if path.is_file():
            assert "holder-inventory" not in path.read_text(encoding="utf-8", errors="ignore"), path


# ------------------------------------------------------------------ what the contract does and does not carry

def test_holder_kinds_are_a_closed_set_with_no_lifecycle_word():
    kinds = hi.load_schema()["$defs"]["holder"]["properties"]["kind"]["enum"]
    assert kinds == ["routed", "self_credentialed", "other"] == list(hi.KINDS)
    for word in ("expired", "revoked", "lapsed", "inactive", "unknown"):
        assert word not in kinds


def test_there_is_no_member_that_could_carry_a_secret_or_a_signature():
    schema = hi.load_schema()
    names = set(schema["properties"]) | set(schema["$defs"]["holder"]["properties"])
    assert names == {"version", "inventory_id", "recorded_by", "recorded_at", "holders", "extensions", "holder_id", "kind",
                     "enforcement_point", "credential_ref"}
    assert not {n for n in names if re.search(r"secret|password|token|sign|proof|attest|complete", n)}


def test_an_inventory_that_enumerates_no_holder_is_valid_and_claims_nothing():
    d = doc("enumerates-no-holder")
    assert d["holders"] == [] and codes(d) == [] and not hi.enumerates_a_holder(d)
    assert hi.class_holds(d) == ["holder_inventory_missing"]
    assert hi.class_holds(None) == ["holder_inventory_missing"]
    assert hi.class_holds(doc("two-holders-routed-and-self-credentialed")) == []
    assert hi.class_holds(None, requires_revocation_assurance=False) == []   # an unflagged class is never held by an inventory


def test_the_behaviour_helper_agrees_with_the_captured_decisions():
    seen = []
    for fx in VALID:
        ctx = fx.get("context")
        if ctx is None:
            continue
        seen.append(ctx["result"])
        assert hi.class_holds(fx["document"], ctx["class_requires_revocation_assurance"]) == ctx["reasons"]
        assert ctx["result"] == ("hold" if ctx["reasons"] else "authorized")
    assert sorted(seen) == ["authorized", "hold"]


def test_repeated_holder_ids_are_not_refused_because_the_profile_has_no_such_rule():
    d = doc("repeated-holder-id-is-not-refused")
    assert d["holders"][0]["holder_id"] == d["holders"][2]["holder_id"] and codes(d) == []


def test_at_most_ten_thousand_holders():
    d = doc("two-holders-routed-and-self-credentialed")
    d["holders"] = [{"holder_id": f"h{i}", "kind": "other", "enforcement_point": "x", "credential_ref": None} for i in range(10000)]
    assert codes(d) == []
    d["holders"].append(copy.deepcopy(d["holders"][0]))
    assert codes(d) == ["schema_violation"]


def test_extensions_are_preserved_and_bound_into_the_digest():
    d = doc("extension-namespace-members-preserved")
    assert hi.preserve(d) == d
    stripped = json.loads(json.dumps(d))
    del stripped["extensions"]
    assert hi.canonical_bytes(stripped) != hi.canonical_bytes(d)
    assert hi.validate(stripped) == []
    assert "extensions" not in hi.known_view(d) and all("extensions" not in h for h in hi.known_view(d)["holders"])


def test_required_members_are_required():
    base = doc("two-holders-routed-and-self-credentialed")
    for member in ("version", "inventory_id", "recorded_by", "recorded_at", "holders"):
        d = copy.deepcopy(base)
        del d[member]
        assert codes(d) == ["schema_violation"], member
    for member in ("holder_id", "kind", "enforcement_point", "credential_ref"):
        d = copy.deepcopy(base)
        del d["holders"][0][member]
        assert codes(d) == ["schema_violation"], member
