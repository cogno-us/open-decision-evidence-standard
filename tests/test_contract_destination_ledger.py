"""Conformance tests for the destination-ledger contract draft (0.1.0-draft).

Docs-and-fixtures only: this exercises contracts/destination-ledger/validate.py against the golden fixtures. It does not import or
alter the odes package and does not read the verifier.
"""
import copy
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "contracts" / "destination-ledger"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # validate.py defines a dataclass; register before exec
    spec.loader.exec_module(module)
    return module


dl = _load("dl_validate", CONTRACT_DIR / "validate.py")


def _fixtures(kind):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((CONTRACT_DIR / "fixtures" / kind).glob("*.json"))]


VALID = _fixtures("valid")
INVALID = _fixtures("invalid")


def doc(fixture_id):
    return copy.deepcopy(next(f for f in VALID if f["fixture_id"] == fixture_id)["document"])


def obs(fixture_id):
    return copy.deepcopy(next(f for f in VALID if f["fixture_id"] == fixture_id)["observations"])


def codes(d, observations=None):
    return [v.code for v in dl.validate(d, observations)]


def test_fixture_sets_are_present_and_well_formed():
    assert len(VALID) >= 10 and len(INVALID) >= 40
    for fx in VALID + INVALID:
        assert fx["synthetic"] is True and fx["reason"].strip() and fx["provenance"]["source"]
        assert fx["expected_outcome"] in {"accept", "reject"}
    assert all(f["expected_outcome"] == "accept" and f["expected_refusal"] is None for f in VALID)
    assert all(f["expected_outcome"] == "reject" and f["expected_refusal"] for f in INVALID)
    names = [f["fixture_id"] for f in VALID + INVALID]
    assert len(names) == len(set(names))
    for kind in ("valid", "invalid"):
        for path in (CONTRACT_DIR / "fixtures" / kind).glob("*.json"):
            assert json.loads(path.read_text())["fixture_id"] == path.stem


def test_valid_fixtures_include_real_captures_with_and_without_the_digest():
    captured = [f for f in VALID if f["provenance"]["source"].endswith("-capture")]
    assert {f["provenance"]["source"] for f in captured} == {"control-plane-capture", "orchestrator-overlay-capture"}
    rows = [r for f in VALID for r in f["document"]["effects"].values()]
    assert any("operation_digest" in r for r in rows) and any("operation_digest" not in r for r in rows)
    assert {f["document"]["effects"][k]["state"] for f in VALID for k in f["document"]["effects"]} == {"applied", "partial"}


@pytest.mark.parametrize("fx", VALID, ids=lambda f: f["fixture_id"])
def test_valid_fixture_is_accepted(fx):
    assert dl.validate(fx["document"], fx.get("observations")) == []


@pytest.mark.parametrize("fx", INVALID, ids=lambda f: f["fixture_id"])
def test_invalid_fixture_is_refused_with_stated_reason(fx):
    assert codes(fx["document"], fx.get("observations")) == [fx["expected_refusal"]], fx["reason"]


def test_every_rule_code_is_pinned_by_a_fixture_and_the_readme():
    source = (CONTRACT_DIR / "validate.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'_v\(\s*"([a-z_]+)"', source)) | set(re.findall(r'Violation\(\s*"([a-z_]+)"', source))
    covered = {f["expected_refusal"] for f in INVALID}
    assert emitted - covered == set(), emitted - covered
    readme = (CONTRACT_DIR / "README.md").read_text(encoding="utf-8")
    missing = sorted(c for c in emitted if f"`{c}`" not in readme)
    assert missing == [], missing


def test_unknown_member_is_refused_not_dropped():
    d = doc("control-plane-acp-run-applied")
    d["injected_member"] = 1
    (violation,) = dl.validate(d)
    assert violation.code == "undeclared_member" and violation.path.endswith("injected_member")
    d = doc("control-plane-acp-run-applied")
    next(iter(d["effects"].values()))["injected"] = 1
    assert codes(d) == ["undeclared_member"]


def test_extensions_are_preserved_and_bound_into_the_digest():
    d = doc("extension-namespace-members-preserved")
    assert dl.preserve(d) == d
    stripped = json.loads(json.dumps(d))
    del stripped["extensions"]
    assert dl.canonical_bytes(stripped) != dl.canonical_bytes(d)
    assert dl.validate(stripped) == []  # ignore-but-preserve: the verdict does not depend on extension members
    assert "extensions" not in dl.known_view(d)
    assert all("extensions" not in r for r in dl.known_view(d)["effects"].values())


def test_required_members_are_required():
    base = doc("control-plane-acp-run-applied")
    for member in ("effects", "grant_effect_counts"):
        d = copy.deepcopy(base)
        del d[member]
        assert codes(d) == ["schema_violation"], member
    for member in ("effect_id", "grant_id", "target", "amount", "unit", "payload", "state"):
        d = copy.deepcopy(base)
        del next(iter(d["effects"].values()))[member]
        assert codes(d) == ["schema_violation"], member
    d = copy.deepcopy(base)
    d.pop("operations", None)
    assert codes(d) == []


def test_operation_digest_is_optional_and_absent_rows_are_unchanged():
    """Decision 25-A: an absent member is valid, and adding no member changes no byte of a default record."""
    with_digest = doc("orchestrator-projection-b-with-operation-digest")
    without = doc("orchestrator-projection-a-without-operation-digest")
    assert codes(with_digest) == [] and codes(without) == []
    stripped = copy.deepcopy(with_digest)
    for row in stripped["effects"].values():
        del row["operation_digest"]
    assert stripped == without  # the same row, member for member, apart from the optional digest
    assert dl.canonical_bytes(stripped) == dl.canonical_bytes(without)
    assert "operation_digest" not in dl.load_schema()["$defs"]["row"]["required"]


def test_operation_digest_format_is_the_runtime_default():
    for fx in VALID:
        for row in fx["document"]["effects"].values():
            if "operation_digest" in row:
                assert dl.OPERATION_DIGEST.fullmatch(row["operation_digest"]), fx["fixture_id"]
    d = doc("orchestrator-projection-b-with-operation-digest")
    row = next(iter(d["effects"].values()))
    for value in ("sha256:" + "0" * 64, "sha256:" + "abcdef0123456789" * 4):
        row["operation_digest"] = value
        assert codes(d) == []
    for value in ("sha256:" + "0" * 63, "sha256:" + "0" * 65, "SHA256:" + "0" * 64, " sha256:" + "0" * 64, "0" * 64):
        row["operation_digest"] = value
        assert codes(d) == ["schema_violation"], value


def test_digest_cross_check_reads_only_accepted_observations_that_carry_it():
    d = doc("row-digest-agrees-with-observation")
    o = obs("row-digest-agrees-with-observation")
    assert codes(d, o) == []
    other = copy.deepcopy(d)
    next(iter(other["effects"].values()))["operation_digest"] = "sha256:" + "e" * 64
    assert codes(other, o) == ["operation_digest_mismatch"]
    not_accepted = copy.deepcopy(o)
    for r in not_accepted:
        r["observation_accepted"] = False
    assert codes(other, not_accepted) == []
    assert codes(other) == []  # no observation context, no cross-check
    no_digest = copy.deepcopy(o)
    for r in no_digest:
        del r["observation"]["destination_state"]["operation_digest"]
    assert codes(other, no_digest) == []
    assert codes(other, {"reconciliations": o}) == ["operation_digest_mismatch"]  # a run record is read the same way


def test_amount_is_a_number_not_a_boolean_and_form_is_not_normalised():
    d = doc("control-plane-acp-run-applied")
    row = next(iter(d["effects"].values()))
    row["amount"] = 50
    assert codes(d) == []
    row["amount"] = True
    assert codes(d) == ["schema_violation"]


def test_schema_is_draft_2020_12_and_agrees_with_reference_validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = dl.load_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    validator_cls = jsonschema.Draft202012Validator
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    for fx in VALID:
        assert not list(validator.iter_errors(fx["document"])), fx["fixture_id"]
    structural = {"undeclared_member", "invalid_extension_key", "schema_violation"}
    # JSON Schema reads `1.0` as an integer; the reference validator (like the verifier's strict parse) keeps it a float and refuses
    # it as a count. A generic JSON Schema validator cannot see that difference; the README says so.
    schema_blind = {"count-not-an-integer"}
    for fx in INVALID:
        errors = list(validator.iter_errors(fx["document"]))
        if fx["fixture_id"] in schema_blind:
            assert not errors
            continue
        assert bool(errors) == (fx["expected_refusal"] in structural), fx["fixture_id"]


def test_validator_cli_reads_fixtures(capsys):
    assert dl.main([str(next((CONTRACT_DIR / "fixtures" / "valid").glob("*.json")))]) == 0
    assert dl.main([str(next((CONTRACT_DIR / "fixtures" / "invalid").glob("*.json")))]) == 1
    assert capsys.readouterr().out.strip()


def test_contract_is_not_part_of_core_or_pder():
    """Optional extension profile: no core code path or pder-v0.1 file mentions it."""
    for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "profiles").rglob("*")):
        if path.is_file():
            assert "destination-ledger" not in path.read_text(encoding="utf-8", errors="ignore"), path
