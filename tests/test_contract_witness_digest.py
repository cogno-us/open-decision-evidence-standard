"""Conformance tests for the witness-digest contract draft (0.1.0-draft).

Docs-and-fixtures only: this exercises contracts/witness-digest/validate.py against the golden fixtures. It does not import or alter
the odes package and does not read the Control Plane or the verifier.
"""
import copy
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "contracts" / "witness-digest"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # validate.py defines a dataclass; register before exec
    spec.loader.exec_module(module)
    return module


wd = _load("wd_validate", CONTRACT_DIR / "validate.py")


def _fixtures(kind):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((CONTRACT_DIR / "fixtures" / kind).glob("*.json"))]


VALID = _fixtures("valid")
INVALID = _fixtures("invalid")


def valid(fixture_id):
    fx = next(f for f in VALID if f["fixture_id"] == fixture_id)
    return copy.deepcopy(fx["document"]), copy.deepcopy(fx.get("record"))


def codes(doc, record=None):
    return [v.code for v in wd.validate(doc, record)]


def test_fixture_sets_are_present_and_well_formed():
    assert len(VALID) >= 7 and len(INVALID) >= 30
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


def test_valid_fixtures_are_captures_with_one_derived_extension_fixture():
    captured = [f for f in VALID if f["provenance"]["source"] == "control-plane-capture"]
    assert len(captured) == len(VALID)
    assert [f["fixture_id"] for f in VALID if "derived" in f["reason"].lower()] == ["extension-namespace-members-preserved"]
    assert any(len(f["document"]) == 2 for f in VALID) and any(len(f["document"]) == 1 for f in VALID)


@pytest.mark.parametrize("fx", VALID, ids=lambda f: f["fixture_id"])
def test_valid_fixture_is_accepted(fx):
    assert wd.validate(fx["document"], fx.get("record")) == []
    if "expected_coverage" in fx:
        # the Control Plane's own verdict (witnessed_through, unwitnessed_rows), captured from `acp witness verify`
        assert wd.coverage(fx["document"], fx["record"]) == fx["expected_coverage"]


@pytest.mark.parametrize("fx", INVALID, ids=lambda f: f["fixture_id"])
def test_invalid_fixture_is_refused_with_stated_reason(fx):
    assert codes(fx["document"], fx.get("record")) == [fx["expected_refusal"]], fx["reason"]


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
    schema = wd.load_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    validator_cls = jsonschema.Draft202012Validator
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    for fx in VALID:
        assert not list(validator.iter_errors(fx["document"])), fx["fixture_id"]
    structural = {"undeclared_member", "invalid_extension_key", "schema_violation", "unknown_enum_value", "unsupported_contract_version"}
    for fx in INVALID:
        errors = list(validator.iter_errors(fx["document"]))
        assert bool(errors) == (fx["expected_refusal"] in structural), fx["fixture_id"]


def test_validator_cli_reads_fixtures_and_a_json_lines_witness_file(capsys, tmp_path):
    assert wd.main([str(next((CONTRACT_DIR / "fixtures" / "valid").glob("*.json")))]) == 0
    assert wd.main([str(next((CONTRACT_DIR / "fixtures" / "invalid").glob("*.json")))]) == 1
    assert capsys.readouterr().out.strip()
    records, record = valid("staged-two-records-chained")
    wire = tmp_path / "witness.jsonl"
    wire.write_text("".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in records), encoding="utf-8")
    run = tmp_path / "record.json"
    run.write_text(json.dumps(record), encoding="utf-8")
    assert wd.main([str(wire), "--record", str(run)]) == 0
    record["decisions"].pop()
    run.write_text(json.dumps(record), encoding="utf-8")
    assert wd.main([str(wire), "--record", str(run)]) == 1


def test_contract_is_not_part_of_core_or_pder():
    for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "profiles").rglob("*")):
        if path.is_file():
            assert "witness-digest" not in path.read_text(encoding="utf-8", errors="ignore"), path


# ------------------------------------------------------------------ what the contract does and does not carry

def test_there_is_no_signer_proof_or_attestation_member_and_extensions_are_never_one():
    schema = wd.load_schema()
    names = set()

    def walk(node):
        if isinstance(node, dict):
            names.update(node.get("properties", {}))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    assert names == {"version", "run_id", "sequence", "previous_digest", "ledgers", "digest", "count", "head", "extensions"}
    assert not {n for n in names if re.search(r"sign|proof|attest|score|key|publish|time", n)}
    records, _ = valid("staged-two-records-chained")
    assert set(records[0]) == set(wd.RECORD_MEMBERS)


def test_the_producer_record_is_reproduced_from_the_run_record():
    """`make_record` restates the Control Plane's record: it reproduces the captured single-record witnesses byte for byte."""
    for fid in ("acp-run-authorized-one-record", "acp-run-held-one-record", "run-with-holder-inventory-journal-mode"):
        records, record = valid(fid)
        assert wd.make_record(record) == records[0], fid


def test_a_chained_record_is_reproduced_after_its_predecessor():
    records, record = valid("staged-two-records-chained")
    assert wd.make_record(record, previous=records[0]) == records[1]


def test_chain_heads_are_prefix_stable_order_and_content_sensitive():
    rows = [{"a": 1}, {"a": 2}]
    assert wd.chain_heads([])[-1] == wd.GENESIS
    assert wd.chain_heads(rows + [{"a": 3}])[:3] == wd.chain_heads(rows)
    assert wd.chain_heads(rows)[-1] != wd.chain_heads(list(reversed(rows)))[-1]
    assert wd.chain_heads(rows)[-1] != wd.chain_heads([{"a": 1}, {"a": 3}])[-1]


def test_only_list_valued_ledgers_are_covered_and_empty_ones_are_omitted():
    records, record = valid("acp-run-held-one-record")
    assert set(records[0]["ledgers"]) == {"decisions", "resolution_checks"}
    assert "run_id" not in records[0]["ledgers"] and "input_time_floors" not in records[0]["ledgers"]
    assert all(rows == [] for name, rows in record.items() if isinstance(rows, list) and name not in records[0]["ledgers"])


def test_rows_after_the_latest_digest_are_reported_not_refused_and_not_called_intact():
    records, record = valid("first-publication-only-leaves-rows-unwitnessed")
    assert codes(records, record) == []
    cov = wd.coverage(records, record)
    assert cov["unwitnessed_rows"] and set(cov["unwitnessed_rows"]) >= {"attempts", "observations", "reconciliations"}
    assert cov["witnessed_through"] == {name: held["count"] for name, held in records[0]["ledgers"].items()}
    # appending a row to a covered ledger after publication is unwitnessed, never a violation
    records, record = valid("acp-run-authorized-one-record")
    record["attempts"].append({"attempt_id": "later"})
    assert codes(records, record) == [] and wd.coverage(records, record)["unwitnessed_rows"] == {"attempts": 1}


def test_a_witness_and_a_record_rewritten_together_are_accepted():
    """The limit, pinned: a witness supplied by whoever supplied the records vouches for nothing that party could rewrite."""
    records, record = valid("acp-run-authorized-one-record")
    record["decisions"][0]["result"] = "hold"
    forged = wd.make_record(record)
    assert codes([forged], record) == []
    assert codes(records, record) == ["witness_ledger_head_mismatch"]


def test_the_digest_covers_extensions_and_the_verdict_ignores_them():
    records, record = valid("extension-namespace-members-preserved")
    assert wd.preserve(records) == records
    stripped = wd.known_view(records)
    assert all("extensions" not in r for r in stripped)
    assert wd.canonical_bytes(stripped) != wd.canonical_bytes(records)
    plain = copy.deepcopy(records)
    for r in plain:
        del r["extensions"]
    assert set(codes(plain, record)) == {"witness_chain_invalid"}   # the digests were computed over the extensions: dropping them breaks the chain


def test_a_count_written_as_a_float_is_refused_by_the_reference_validator():
    records, _ = valid("acp-run-held-one-record")
    records[0]["ledgers"]["decisions"]["count"] = 1.0
    assert codes(records) == ["schema_violation"]   # a generic JSON Schema validator reads 1.0 as an integer; this one does not
    records, _ = valid("acp-run-held-one-record")
    records[0]["sequence"] = 0.0
    assert codes(records) == ["schema_violation"]


def test_a_boolean_is_not_a_count():
    records, _ = valid("acp-run-held-one-record")
    records[0]["ledgers"]["decisions"]["count"] = True
    assert codes(records) == ["schema_violation"]


def test_record_rules_run_only_over_a_sound_chain():
    records, record = valid("staged-two-records-chained")
    record["attempts"].pop()
    assert codes(records, record) == ["witness_ledger_shrunk"]
    records[1]["digest"] = "sha256:" + "1" * 64
    assert codes(records, record) == ["witness_chain_invalid"]


def test_a_witness_that_holds_nothing_verifies_nothing():
    assert codes([]) == ["witness_holds_no_digest"]
    assert codes([], {"run_id": "r"}) == ["witness_holds_no_digest"]


def test_required_members_are_required():
    base, _ = valid("acp-run-held-one-record")
    for member in wd.RECORD_MEMBERS:
        d = copy.deepcopy(base)
        del d[0][member]
        assert codes(d) == ["schema_violation"], member
    for member in ("count", "head"):
        d = copy.deepcopy(base)
        del d[0]["ledgers"]["decisions"][member]
        assert codes(d) == ["schema_violation"], member
