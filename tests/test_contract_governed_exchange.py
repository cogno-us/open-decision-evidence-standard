"""Conformance tests for the governed-exchange contract spike (0.1.0-draft).

Docs-and-fixtures only: this exercises contracts/governed-exchange/validate.py against the golden fixtures. It does
not import or alter the odes package, and it imports no exchange code. Fixture documents were captured from the
exchange reference code with synthetic inputs and stub peers.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

CONTRACT_DIR = Path(__file__).resolve().parents[1] / "contracts" / "governed-exchange"
_spec = importlib.util.spec_from_file_location("gx_validate", CONTRACT_DIR / "validate.py")
gx = importlib.util.module_from_spec(_spec)
sys.modules["gx_validate"] = gx
_spec.loader.exec_module(gx)


def _load(kind):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((CONTRACT_DIR / "fixtures" / kind).glob("*.json"))]


VALID = _load("valid")
INVALID = _load("invalid")
STRUCTURAL = {"undeclared_member", "invalid_extension_key", "schema_violation", "unknown_enum_value",
              "unsupported_contract_version", "unsupported_profile", "unsupported_transport_profile",
              "unsupported_transport_version", "unsupported_canonicalization", "unsupported_result_profile",
              "unsupported_artifact_export_profile", "unsupported_artifact_export_version",
              "unsupported_profile_or_schema"}


def _valid(fid):
    return json.loads(json.dumps(next(f for f in VALID if f["fixture_id"] == fid)["document"]))


def test_fixture_sets_are_present_and_well_formed():
    assert len(VALID) >= 20 and len(INVALID) >= 40
    for fx in VALID + INVALID:
        assert fx["synthetic"] is True and fx["reason"].strip()
        assert fx["expected_outcome"] in {"accept", "reject"}
    assert all(f["expected_outcome"] == "accept" for f in VALID)
    assert all(f["expected_outcome"] == "reject" and f["expected_refusal"] for f in INVALID)
    names = [f["fixture_id"] for f in VALID + INVALID]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("fx", VALID, ids=lambda f: f["fixture_id"])
def test_valid_fixture_is_accepted(fx):
    assert gx.validate(fx["document"]) == []


@pytest.mark.parametrize("fx", INVALID, ids=lambda f: f["fixture_id"])
def test_invalid_fixture_is_refused_with_stated_reason(fx):
    codes = [v.code for v in gx.validate(fx["document"])]
    assert codes == [fx["expected_refusal"]], fx["reason"]


def test_every_member_has_valid_and_invalid_coverage():
    members = {"message", "transport_envelope", "acknowledgement", "recipient_result", "retained_artifact_export",
               "successor_packet", "successor_acceptance", "transport_evidence", "delivery_result"}
    for kind in (VALID, INVALID):
        seen = {m for f in kind for m in members if m in f["document"]}
        assert seen == members


def test_required_refusal_codes_are_exercised():
    codes = {f["expected_refusal"] for f in INVALID}
    assert {"undeclared_member", "invalid_extension_key", "unknown_enum_value", "schema_violation",
            "unsupported_profile", "message_digest_mismatch", "content_digest_mismatch",
            "message_expiry_not_after_creation", "replay_bundle_ref_without_digest",
            "unsupported_transport_profile", "unsupported_transport_version", "unsupported_canonicalization",
            "message_identity_mismatch", "conversation_identity_mismatch", "envelope_created_before_message",
            "envelope_message_expiry_mismatch", "content_commitment_mismatch", "envelope_message_mismatch",
            "acknowledgement_binding_incomplete", "acknowledgement_envelope_mismatch",
            "receipt_for_unretained_result", "result_state_export_mismatch", "unavailable_result_carries_content",
            "execution_without_eligible_assessment", "refusal_without_failure", "not_understood_stage_mismatch", "informational_stage_mismatch",
            "derivative_result_claims_execution", "attempt_status_attempted_mismatch", "result_producer_refs_mismatch",
            "unsupported_result_profile", "artifact_export_mismatch", "unsupported_artifact_export_profile",
            "unsupported_artifact_export_version", "retained_reconstruction_identity_mismatch",
            "retained_reconstruction_digest_mismatch", "retained_reconstruction_commitment_mismatch",
            "retained_odes_package_digest_mismatch", "retained_odes_package_commitment_mismatch",
            "retained_odes_validation_digest_mismatch", "retained_odes_validation_commitment_mismatch",
            "retained_successor_identity_mismatch", "retained_successor_digest_mismatch",
            "retained_successor_content_digest_mismatch", "retained_successor_commitment_mismatch",
            "lineage_state_mismatch", "lineage_effect_reexecution", "recovery_denial_lineage_invalid",
            "packet_digest_mismatch", "unsupported_profile_or_schema", "successor_creates_effect",
            "successor_loaded_status_mismatch", "unsupported_limits_missing", "attempt_namespace_collision",
            "delivery_state_ack_mismatch", "delivery_result_inconsistent"} <= codes


def test_f10_protection_unknown_member_is_refused_not_dropped():
    fx = next(f for f in INVALID if f["fixture_id"] == "message-undeclared-member")
    (violation,) = gx.validate(fx["document"])
    assert violation.code == "undeclared_member" and violation.path.endswith("injected_member")


def test_extensions_are_preserved_and_bound_into_the_message_digest():
    doc = _valid("message-extensions-preserved")
    assert gx.preserve(doc) == doc
    stripped = json.loads(json.dumps(doc))
    del stripped["message"]["extensions"]
    # Stripping an extension is tampering: the message digest covers every member, extensions included.
    assert [v.code for v in gx.validate(stripped)] == ["message_digest_mismatch"]
    assert "extensions" not in gx.known_view(doc)["message"]


def test_canonicalisation_is_the_exchanges_json_sort_keys_compact_v1():
    value = {"b": [1, {"z": "é", "a": None}], "a": 1.5}
    assert gx.canonical_bytes(value) == '{"a":1.5,"b":[1,{"a":null,"z":"é"}]}'.encode("utf-8")
    assert gx.digest(value).startswith("sha256:") and len(gx.digest(value)) == 71


def test_acknowledgement_never_implies_effect_authorization_or_verification():
    doc = _valid("ack-durable-receipt-with-envelope")
    for member in ("authorization", "execution", "destination_observation", "independent_verification"):
        mutated = json.loads(json.dumps(doc))
        mutated["acknowledgement"]["detail"][member] = "established"
        assert [v.code for v in gx.validate(mutated)] == ["schema_violation"], member


def test_delivered_means_a_durable_receipt_and_nothing_more():
    doc = _valid("delivery-result-delivered-real-producer")
    assert doc["delivery_result"]["transport_state"] == "DELIVERED"
    for kind, state in (("TERMINAL_REJECTION", "DELIVERED"), ("DURABLE_RECEIPT_UNRESOLVED", "DELIVERED")):
        other = _valid("ack-terminal-rejection-content-commitment" if kind == "TERMINAL_REJECTION"
                       else "ack-receipt-unresolved")["acknowledgement"]
        other["message_id"] = doc["delivery_result"]["message_id"]
        other["delivery_attempt_id"] = doc["delivery_result"]["delivery_attempt_id"]
        mutated = json.loads(json.dumps(doc))
        mutated["delivery_result"]["acknowledgement"] = other
        assert [v.code for v in gx.validate(mutated)] == ["delivery_state_ack_mismatch"], kind


def test_unresolved_receipt_and_complete_receipt_are_different_kinds():
    doc = _valid("ack-receipt-unresolved")
    doc["acknowledgement"]["acknowledgement_kind"] = "DURABLE_RECEIPT"
    codes = {v.code for v in gx.validate(doc)}
    assert codes <= {"schema_violation", "undeclared_member"} and codes


def test_removing_an_optional_declared_member_stays_valid():
    doc = _valid("message-propose-real-producer")
    doc["message"].pop("acknowledgement_requested")
    doc["message"]["message_digest"] = gx.digest({k: v for k, v in doc["message"].items() if k != "message_digest"})
    assert gx.validate(doc) == []
    doc = _valid("export-original-complete-real-producer")
    doc["retained_artifact_export"]["lineage"].pop("effect_reexecution")
    assert gx.validate(doc) == []


def test_missing_required_member_is_refused():
    doc = _valid("message-propose-real-producer")
    doc.pop("contract_version")
    assert [v.code for v in gx.validate(doc)] == ["schema_violation"]


def test_unsupported_contract_version_is_refused_typed():
    doc = _valid("message-propose-real-producer")
    doc["contract_version"] = "9.0.0"
    assert [v.code for v in gx.validate(doc)] == ["unsupported_contract_version"]


def test_document_needs_at_least_one_member():
    doc = {"contract": "governed-exchange", "contract_version": "0.1.0-draft"}
    assert [v.code for v in gx.validate(doc)] == ["schema_violation"]


def test_export_checks_report_the_first_failing_check_in_the_exchanges_order():
    doc = _valid("export-original-complete-real-producer")
    export = doc["retained_artifact_export"]
    export["reconstruction_bundle"]["run_id"] = "syn-tampered"
    export["content_commitments"]["successor_packet"] = "sha256:" + "6" * 64
    # Two things are wrong; the exchange stops at the reconstruction digest, and so does the contract.
    assert [v.code for v in gx.validate(doc)] == ["retained_reconstruction_digest_mismatch"]


def test_schema_is_draft_2020_12_and_agrees_with_reference_validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = gx.load_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    validator_cls = jsonschema.Draft202012Validator
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    for fx in VALID:
        assert not list(validator.iter_errors(fx["document"])), fx["fixture_id"]
    for fx in INVALID:
        errors = list(validator.iter_errors(fx["document"]))
        assert bool(errors) == (fx["expected_refusal"] in STRUCTURAL), fx["fixture_id"]
