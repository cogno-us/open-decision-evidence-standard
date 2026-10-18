"""Conformance tests for the authority lineage contract draft (0.1.0-draft).

Docs-and-fixtures only: this exercises contracts/authority-lineage/validate.py against the golden fixtures.
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
CONTRACT_DIR = ROOT / "contracts" / "authority-lineage"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # validate.py defines a dataclass; register before exec
    spec.loader.exec_module(module)
    return module


al = _load("al_validate", CONTRACT_DIR / "validate.py")


def _fixtures(kind):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((CONTRACT_DIR / "fixtures" / kind).glob("*.json"))]


VALID = _fixtures("valid")
INVALID = _fixtures("invalid")


def doc(fixture_id):
    return copy.deepcopy(next(f for f in VALID if f["fixture_id"] == fixture_id)["document"])


def bad(fixture_id):
    return copy.deepcopy(next(f for f in INVALID if f["fixture_id"] == fixture_id)["document"])


def codes(d):
    return [v.code for v in al.validate(d)]


def test_fixture_sets_are_present_and_well_formed():
    assert len(VALID) >= 10 and len(INVALID) >= 22
    for fx in VALID + INVALID:
        assert fx["synthetic"] is True and fx["reason"].strip()
        assert fx["expected_outcome"] in {"accept", "reject"}
        assert fx["document"]["contract"] == "authority-lineage"
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
    assert al.validate(fx["document"]) == []


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
    d = doc("grant-to-effect")
    d["injected_member"] = 1
    (violation,) = al.validate(d)
    assert violation.code == "undeclared_member" and violation.path.endswith("injected_member")


def test_extensions_are_preserved_and_bound_into_the_digest():
    d = doc("extension-namespace-members-preserved")
    assert al.preserve(d) == d
    stripped = json.loads(json.dumps(d))
    del stripped["extensions"]
    assert al.canonical_bytes(stripped) != al.canonical_bytes(d)
    # Ignore-but-preserve: the verdict does not depend on extension members.
    assert al.validate(stripped) == []
    assert "extensions" not in al.known_view(d)
    d["extensions"] = {"not-prefixed": 1}
    assert codes(d) == ["invalid_extension_key"]


def test_required_members_are_required():
    base = doc("grant-to-effect")
    for member in ['contract', 'contract_version', 'profile', 'hops', 'lineage_discontinuities']:
        d = copy.deepcopy(base)
        del d[member]
        assert codes(d) == ["schema_violation"], member
    d = copy.deepcopy(base)
    d.pop("extensions", None)
    assert codes(d) == []


def test_unsupported_contract_version_is_refused_typed():
    d = doc("grant-to-effect")
    d["contract_version"] = "9.0.0"
    assert codes(d) == ["unsupported_contract_version"]


def test_schema_is_draft_2020_12_and_agrees_with_reference_validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = al.load_schema()
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
    assert al.main([str(next((CONTRACT_DIR / "fixtures" / "valid").glob("*.json")))]) == 0
    assert al.main([str(next((CONTRACT_DIR / "fixtures" / "invalid").glob("*.json")))]) == 1
    assert capsys.readouterr().out.strip()


def test_contract_is_not_part_of_core_or_pder():
    """Optional extension profile: no core code path or pder-v0.1 file mentions it."""
    for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "profiles").rglob("*")):
        if path.is_file():
            assert "authority-lineage" not in path.read_text(encoding="utf-8", errors="ignore"), path


# ------------------------------------------------------------------ rule tests that need more than one mutation

def rehash(d):
    """Recompute hop hashes and links in list order after a mutation (keeps the document self-consistent)."""
    by = {}
    for h in d["hops"]:
        if h["previous_hop_id"] in by:
            h["previous_hash"] = by[h["previous_hop_id"]]
        h["hop_hash"] = al.hop_hash(h)
        by[h["hop_id"]] = h["hop_hash"]
    return d


def test_hop_hash_is_the_documented_commitment():
    h = doc("grant-to-effect")["hops"][0]
    expected = al.commitment({k: h[k] for k in ("hop_id", "kind", "subject_ref", "previous_hop_id", "previous_hash", "content_digest")})
    assert h["hop_hash"] == expected == al.hop_hash(h)


def test_every_terminal_effect_resolves_or_is_flagged():
    for fx in VALID:
        d = fx["document"]
        flagged = {f["effect_hop_id"] for f in d["lineage_discontinuities"]}
        assert set(al.unresolved_effects(d)) == flagged, fx["fixture_id"]


def test_changing_an_early_hop_breaks_every_later_link():
    d = doc("grant-delegation-delegation-effect")
    d["hops"][0]["content_digest"] = al.commitment({"changed": True})
    d["hops"][0]["hop_hash"] = al.hop_hash(d["hops"][0])  # an attacker re-hashes only the altered hop
    result = codes(d)
    assert result == ["lineage_discontinuity_unflagged"], result
    (effect,) = al.unresolved_effects(d)
    assert al.find_break(d, effect) == ("h-del-1", "previous_hash_mismatch")


def test_rehashing_the_whole_chain_after_a_change_keeps_it_valid():
    d = doc("grant-delegation-delegation-effect")
    d["hops"][0]["content_digest"] = al.commitment({"changed": True})
    assert codes(rehash(d)) == []


def test_flag_cannot_excuse_a_tampered_hop():
    d = doc("effect-without-origin-flagged")
    d["hops"][1]["content_digest"] = al.commitment({"x": 1})
    assert codes(d) == ["hop_hash_mismatch"]


def test_find_break_reports_each_reason():
    assert al.find_break(doc("grant-to-effect"), "h-eff-direct") is None
    assert al.find_break(doc("previous-missing-flagged"), "h-eff-missing") == ("h-eff-missing", "previous_missing")
    assert al.find_break(doc("previous-hash-mismatch-flagged"), "h-eff-badlink") == ("h-eff-badlink", "previous_hash_mismatch")
    assert al.find_break(doc("effect-without-origin-flagged"), "h-eff-orphan") == ("h-eff-orphan", "no_origin")
    assert al.find_break(doc("break-deeper-in-the-chain-flagged-at-the-break"), "h-eff-deep") == ("h-del-2b", "previous_hash_mismatch")


def test_an_unresolved_delegation_with_no_effect_needs_no_flag():
    d = doc("grant-only")
    orphan_delegation = {"hop_id": "h-del-lone", "kind": "delegation", "subject_ref": "urn:grant:lone", "previous_hop_id": None,
                         "previous_hash": None, "content_digest": al.commitment({"lone": 1})}
    orphan_delegation["hop_hash"] = al.hop_hash(orphan_delegation)
    d["hops"].append(orphan_delegation)
    assert codes(d) == []
    assert al.find_break(d, "h-del-lone") == ("h-del-lone", "no_origin")
    assert al.unresolved_effects(d) == []


def test_a_forest_with_several_origins_is_valid():
    d = doc("grant-to-effect")
    second = copy.deepcopy(d["hops"])
    for h in second:
        h["hop_id"] += "-2"
        if h["previous_hop_id"]:
            h["previous_hop_id"] += "-2"
        h["subject_ref"] += "-2"
    d["hops"] += second
    assert codes(rehash(d)) == []


def test_flagging_does_not_claim_authorization():
    readme = (CONTRACT_DIR / "README.md").read_text(encoding="utf-8")
    assert "never means the effect was authorized" in readme
