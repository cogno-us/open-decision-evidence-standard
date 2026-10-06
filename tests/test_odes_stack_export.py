from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from odes.exporter import ExportError, export_cognous_stack_package
from odes.recipient_validator import evaluate_recipient_package
from odes.schema_validation import validate_record


def _path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} not provided")
    path = Path(value)
    if not path.exists():
        pytest.skip(f"{name} path does not exist: {path}")
    return path


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest() -> dict:
    return _load(_path("UPSTREAM_MANIFEST_EXAMPLE"))


def _success() -> dict:
    return _load(_path("UPSTREAM_REPLAY_SUCCESS_EXAMPLE"))


def _lost_ack() -> dict:
    return _load(_path("UPSTREAM_REPLAY_LOST_ACK_EXAMPLE"))


def _records(bundle: dict, kind: str) -> list[dict]:
    return [record for record in bundle["records"] if record["record_type"] == kind]


def _policy(**overrides):
    policy = {
        "supported_profiles": ["odes_cognous_stack_export_0_1"],
        "relying_party": "recipient.example.org",
        "purpose": "audit",
        "now": "2026-10-06T00:00:00Z",
        "trusted_digests": [],
        "trusted_key_refs": [],
        "status_inputs": {},
    }
    policy.update(overrides)
    return policy


def _cp_only_decision(result: str) -> dict:
    bundle = copy.deepcopy(_success())
    keep = []
    for record in bundle["records"]:
        if record["record_type"] in {"runtime_proposal", "runtime_decision"}:
            keep.append(record)
    bundle["records"] = keep
    decision = _records(bundle, "runtime_decision")[0]
    decision["data"]["result"] = result
    decision["data"].pop("binding", None)
    decision["data"].pop("effect_id", None)
    decision["identifiers"].pop("effect_id", None)
    bundle["status"] = "reconstruction_partial"
    return bundle


def test_authorized_success_exports_and_recipient_accepts():
    package = export_cognous_stack_package(_manifest(), _success())
    validate_record(package["record"])
    assert package["record"]["schema_version"] == "0.1"
    assert package["profile"]["document_version"] == "0.2"
    assert package["profile"]["implementation_profile"] == "odes_cognous_stack_export_0_1"
    assert package["record"]["decision_type"] == "agent_action_authorized"
    assert package["provenance"]["execution_facts"]["acknowledgement_summary"] == "received"
    assert package["provenance"]["execution_facts"]["destination_observed"] == "applied"
    result = evaluate_recipient_package(package, _policy())
    assert result["schema_validity"]["status"] == "pass"
    assert result["declared_profile_conformance"]["status"] == "pass"
    assert result["integrity_authentication_checks"]["status"] == "pass"
    assert result["recipient_reliance_decision"]["status"] == "pass"


@pytest.mark.parametrize("decision_result,expected_type", [("hold", "agent_action_held"), ("deny", "agent_action_denied")])
def test_hold_and_deny_with_no_effect_are_valid_governance_records(decision_result: str, expected_type: str):
    package = export_cognous_stack_package(_manifest(), _cp_only_decision(decision_result))
    validate_record(package["record"])
    assert package["record"]["decision_type"] == expected_type
    assert package["provenance"]["execution_facts"]["destination_observed"] == "unavailable"
    assert package["provenance"]["execution_facts"]["acknowledgement_summary"] == "not_applicable"


def test_hold_with_execution_evidence_rejects_as_contradictory():
    bundle = copy.deepcopy(_success())
    decision = _records(bundle, "runtime_decision")[0]
    decision["data"]["result"] = "hold"
    decision["data"].pop("binding", None)
    with pytest.raises(ExportError):
        export_cognous_stack_package(_manifest(), bundle)


def test_lost_ack_preserves_unknown_ack_and_applied_destination():
    package = export_cognous_stack_package(_manifest(), _lost_ack())
    facts = package["provenance"]["execution_facts"]
    assert facts["acknowledgement_summary"] == "unknown"
    assert facts["destination_observed"] == "applied"
    assert facts["destination_observation_counts"].get("applied") == 2


def test_duplicate_restart_reconciliation_non_new_control_plane_attempt_reference():
    bundle = copy.deepcopy(_lost_ack())
    result = _records(bundle, "execution_result")[0]
    cp_attempt = _records(bundle, "control_plane_attempt_transition")[0]["data"]["attempt_id"]
    result["data"]["attempt_id"] = cp_attempt
    result["identifiers"]["attempt_id"] = cp_attempt
    result["data"]["status"] = "reconciled"
    result["data"]["newly_executed"] = False
    package = export_cognous_stack_package(_manifest(), bundle)
    assert package["provenance"]["execution_facts"]["execution_results"][0]["newly_executed"] is False


def test_partial_delivery_remains_visible_and_not_overridden_by_applied():
    bundle = copy.deepcopy(_success())
    obs = _records(bundle, "effect_observation")[0]
    obs["data"]["state"] = "partial"
    package = export_cognous_stack_package(_manifest(), bundle)
    assert package["provenance"]["execution_facts"]["destination_observed"] == "partial"


@pytest.mark.parametrize("mutation", ["payload", "target", "proposal_commitment", "dangling_reference", "destination_substitution"])
def test_tampering_and_mismatched_references_reject(mutation: str):
    bundle = copy.deepcopy(_success())
    if mutation == "payload":
        _records(bundle, "runtime_proposal")[0]["data"]["payload"]["refund_reason"] = "tampered"
    elif mutation == "target":
        _records(bundle, "execution_envelope")[0]["data"]["operation"]["target"] = "urn:cognous:synthetic-account:attacker"
    elif mutation == "proposal_commitment":
        _records(bundle, "runtime_decision")[0]["data"]["binding"]["proposal_commitment"] = "sha256:" + "0" * 64
    elif mutation == "dangling_reference":
        _records(bundle, "execution_result")[0]["data"]["attempt_id"] = "missing-attempt"
    elif mutation == "destination_substitution":
        _records(bundle, "destination_effect")[0]["data"]["target"] = "urn:cognous:synthetic-account:attacker"
    with pytest.raises(ExportError):
        export_cognous_stack_package(_manifest(), bundle)


def test_recipient_rejects_wrong_purpose_and_wrong_recipient():
    package = export_cognous_stack_package(_manifest(), _success())
    wrong_purpose = evaluate_recipient_package(package, _policy(purpose="production_reuse"))
    assert wrong_purpose["consumption_conditions"]["status"] == "fail"
    assert wrong_purpose["recipient_reliance_decision"]["status"] == "fail"
    wrong_recipient = evaluate_recipient_package(package, _policy(relying_party="other.example.org"))
    assert wrong_recipient["consumption_conditions"]["status"] == "fail"


def test_recipient_rejects_revoked_expired_stale_unsupported_and_tampered():
    package = export_cognous_stack_package(_manifest(), _success())
    revoked = evaluate_recipient_package(package, _policy(status_inputs={"revoked": True, "freshness": "revoked"}))
    assert revoked["authority_status_and_freshness"]["status"] == "fail"
    expired = evaluate_recipient_package(package, _policy(now="2030-01-01T00:00:00Z"))
    assert expired["authority_status_and_freshness"]["status"] == "fail"
    stale = evaluate_recipient_package(package, _policy(status_inputs={"freshness": "stale"}))
    assert stale["authority_status_and_freshness"]["status"] == "fail"
    unsupported = evaluate_recipient_package(package, _policy(supported_profiles=["other_profile"]))
    assert unsupported["declared_profile_conformance"]["status"] == "unsupported"
    tampered = copy.deepcopy(package)
    tampered["record"]["decision_type"] = "agent_action_denied"
    assert evaluate_recipient_package(tampered, _policy())["integrity_authentication_checks"]["status"] == "fail"


def test_redacted_derivative_and_source_findings_survive_export():
    bundle = copy.deepcopy(_success())
    bundle["derivation"] = {"relationship": "redacted_derivative", "source_bundle_id": "source-bundle", "derived_at": "2026-10-06T00:00:00Z"}
    bundle.setdefault("metadata", {})["redacted_fields"] = ["payload.customer_id"]
    package = export_cognous_stack_package(_manifest(), bundle)
    assert package["provenance"]["redaction"]["status"] == "redacted_derivative"
    assert package["provenance"]["replay_validation"]["findings"] is not None


def test_consumer_evaluation_does_not_change_exported_package():
    package = export_cognous_stack_package(_manifest(), _success())
    before = copy.deepcopy(package)
    evaluate_recipient_package(package, _policy())
    assert package == before
