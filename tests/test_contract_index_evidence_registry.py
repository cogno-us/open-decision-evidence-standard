"""Conformance tests for the index-evidence-registry contract spike (0.1.0-draft).

Docs-and-fixtures only: this exercises contracts/index-evidence-registry/validate.py against the golden fixtures. It does
not import or alter the odes package, and it imports no Index or BitRep code. Fixture documents were captured from the
Index's own code (link attestation verification, the vendored BitRep verifier, EvidenceService) with synthetic inputs and
a throwaway Ed25519 key.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

CONTRACT_DIR = Path(__file__).resolve().parents[1] / "contracts" / "index-evidence-registry"
_spec = importlib.util.spec_from_file_location("ix_validate", CONTRACT_DIR / "validate.py")
ix = importlib.util.module_from_spec(_spec)
sys.modules["ix_validate"] = ix
_spec.loader.exec_module(ix)


def _load(kind):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((CONTRACT_DIR / "fixtures" / kind).glob("*.json"))]


VALID = _load("valid")
INVALID = _load("invalid")
STRUCTURAL = {"undeclared_member", "invalid_extension_key", "schema_violation", "unknown_enum_value",
              "unsupported_contract_version"}
MEMBERS = {"link_submission", "stored_link", "verification_result", "link_outcome", "epistemic_status",
           "chain_attestation_check"}


def _valid(fid):
    return json.loads(json.dumps(next(f for f in VALID if f["fixture_id"] == fid)["document"]))


def test_fixture_sets_are_present_and_well_formed():
    assert len(VALID) >= 25 and len(INVALID) >= 50
    for fx in VALID + INVALID:
        assert fx["synthetic"] is True and fx["reason"].strip()
        assert fx["expected_outcome"] in {"accept", "reject"}
    assert all(f["expected_outcome"] == "accept" for f in VALID)
    assert all(f["expected_outcome"] == "reject" and f["expected_refusal"] for f in INVALID)
    names = [f["fixture_id"] for f in VALID + INVALID]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("fx", VALID, ids=lambda f: f["fixture_id"])
def test_valid_fixture_is_accepted(fx):
    assert ix.validate(fx["document"]) == []


@pytest.mark.parametrize("fx", INVALID, ids=lambda f: f["fixture_id"])
def test_invalid_fixture_is_refused_with_stated_reason(fx):
    codes = [v.code for v in ix.validate(fx["document"])]
    assert codes == [fx["expected_refusal"]], fx["reason"]


def test_every_member_has_valid_and_invalid_coverage():
    for kind in (VALID, INVALID):
        seen = {m for f in kind for m in MEMBERS if m in f["document"]}
        assert seen == MEMBERS


def test_required_refusal_codes_are_exercised():
    codes = {f["expected_refusal"] for f in INVALID}
    assert {"undeclared_member", "invalid_extension_key", "unknown_enum_value", "schema_violation",
            "unsupported_contract_version", "link_target_invalid", "attestation_required", "malformed_attestation",
            "attestation_binding_mismatch", "attestation_commitment_incomplete", "link_without_attestation",
            "verification_result_inconsistent", "statement_digest_mismatch", "outcome_status_reason_mismatch",
            "outcome_link_mismatch", "status_weights_mismatch", "robustness_mismatch",
            "independence_not_distinct_source_count", "chain_audience_mismatch", "chain_subject_mismatch",
            "chain_statement_type_mismatch", "chain_content_commitment_mismatch"} <= codes


def test_f10_protection_unknown_member_is_refused_not_dropped():
    fx = next(f for f in INVALID if f["fixture_id"] == "submission-undeclared-member")
    (violation,) = ix.validate(fx["document"])
    assert violation.code == "undeclared_member" and violation.path.endswith("injected_member")


def test_extensions_are_preserved_and_ignored_by_logic():
    doc = _valid("submission-extensions-preserved")
    assert ix.preserve(doc) == doc
    assert "extensions" not in ix.known_view(doc)["link_submission"]
    # The extension is not signed: removing it leaves the document conformant (the link content digest ignores it).
    stripped = json.loads(json.dumps(doc))
    del stripped["link_submission"]["extensions"]
    assert ix.validate(stripped) == []


def test_link_content_digest_matches_the_signed_statement_in_every_captured_submission():
    for fx in VALID:
        sub = fx["document"].get("link_submission")
        if sub:
            assert sub["attestation"]["statement"]["content_digest"] == ix.link_content_digest(sub), fx["fixture_id"]


def test_link_content_bytes_is_the_indexs_ascii_sorted_compact_form():
    link = {"claim_id": "c", "evidence_id": "e", "relation_type": "supports", "strength": 1}
    assert ix.link_content_bytes(link) == (
        b'{"claim_id":"c","claim_id_2":null,"evidence_id":"e","relation_type":"supports","strength":1.0}')
    non_ascii = dict(link, claim_id="é")
    assert b"\\u00e9" in ix.link_content_bytes(non_ascii)  # ensure_ascii, unlike the exchange canonicalisation


def test_statement_digest_recomputes_for_every_captured_verification_result():
    seen = 0
    for fx in VALID:
        vr = fx["document"].get("verification_result")
        if vr and "envelope" in vr:
            seen += 1
            assert vr["result"]["statement_digest"] == ix.statement_digest(vr["envelope"]["statement"])
    assert seen >= 7


def test_verified_means_issuer_signature_only_and_nothing_more():
    doc = _valid("verification-verified")
    assert doc["verification_result"]["result"]["assurance"] == "issuer_signature_only"
    for member, value in (("assurance", "none"), ("outcome", "rejected"), ("reason", "invalid_signature")):
        mutated = json.loads(json.dumps(doc))
        mutated["verification_result"]["result"][member] = value
        assert [v.code for v in ix.validate(mutated)] == ["verification_result_inconsistent"], member


def test_every_bitrep_rejection_reason_is_an_accepted_422_reason_and_nothing_else_is():
    base = _valid("outcome-422-unknown-key")
    for reason in sorted(ix.REASONS_422):
        base["link_outcome"]["reason"] = reason
        assert ix.validate(base) == [], reason
    for status, reasons in ix.HTTP_REASONS.items():
        for reason in sorted(ix.REASONS_422 | {r for rs in ix.HTTP_REASONS.values() for r in rs}):
            doc = {"contract": ix.CONTRACT, "contract_version": ix.CONTRACT_VERSION,
                   "link_outcome": {"http_status": status, "reason": reason}}
            assert (ix.validate(doc) == []) == (reason in reasons), (status, reason)


def test_independence_counts_distinct_sources_not_records():
    doc = _valid("epistemic-five-records-one-source")
    assert doc["epistemic_status"]["independence_score"] == 0.2
    for k in range(0, 6):
        doc["epistemic_status"]["independence_score"] = k / 5
        assert ix.validate(doc) == []
    doc["epistemic_status"]["independence_score"] = 0.33
    assert [v.code for v in ix.validate(doc)] == ["independence_not_distinct_source_count"]


def test_epistemic_status_thresholds_follow_the_indexs_computation():
    def status(sup, con, robustness):
        return {"contract": ix.CONTRACT, "contract_version": ix.CONTRACT_VERSION,
                "epistemic_status": {"claim_id": "c", "status": "proposed", "supporting_weight": sup,
                                     "contradicting_weight": con, "independence_score": 0.0,
                                     "robustness_score": robustness, "last_computed_at": "2026-10-17T12:00:00"}}
    cases = [(0.0, 0.0, "proposed"), (2.0, 0.0, "proposed"), (2.1, 0.0, "supported"), (1.0, 1.5, "contested"),
             (0.0, 3.0, "contested"), (0.0, 3.1, "refuted"), (2.5, 2.5, "supported")]
    for sup, con, want in cases:
        doc = status(sup, con, min((sup + con) / 10, 1.0))
        doc["epistemic_status"]["status"] = want
        assert ix.validate(doc) == [], (sup, con, want)


def test_chain_binding_is_reconstructed_from_chain_data_not_read_from_the_statement():
    doc = _valid("chain-support-attestation")
    check = doc["chain_attestation_check"]
    assert check["statement"]["audience"] == f"index:eip155:{check['chain_id']}:{check['contract_address']}:v1"
    assert check["statement"]["subject"].endswith(":claim:" + check["claim_id"][2:])
    other = json.loads(json.dumps(doc))
    other["chain_attestation_check"]["chain_id"] = 1
    codes = [v.code for v in ix.validate(other)]
    assert codes == ["chain_subject_mismatch", "chain_audience_mismatch"]


def test_trust_dependent_rules_are_not_claimed_by_the_validator():
    # A bad signature cannot be told from a good one without the operator trust snapshot: structure and binding pass.
    doc = _valid("submission-evidence-link")
    sig = doc["link_submission"]["attestation"]["signature"]
    doc["link_submission"]["attestation"]["signature"] = ("A" if sig[0] != "A" else "B") + sig[1:]
    assert ix.validate(doc) == []


def test_unsupported_contract_version_is_refused_before_structure():
    doc = _valid("submission-evidence-link")
    doc["contract_version"] = "9.9.9"
    doc["not_a_member"] = True
    assert [v.code for v in ix.validate(doc)] == ["unsupported_contract_version"]


def test_schema_is_draft_2020_12_and_agrees_with_reference_validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = ix.load_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    validator_cls = jsonschema.Draft202012Validator
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    for fx in VALID:
        assert not list(validator.iter_errors(fx["document"])), fx["fixture_id"]
    for fx in INVALID:
        if fx["fixture_id"] == "unpaired-surrogate-text":
            continue  # text validity is a validator rule; the portable schema does not state it
        errors = list(validator.iter_errors(fx["document"]))
        assert bool(errors) == (fx["expected_refusal"] in STRUCTURAL), fx["fixture_id"]
