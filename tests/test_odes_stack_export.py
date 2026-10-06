from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from odes.common import CANONICALIZATION_PROFILE, PROFILE_ID, PROFILE_VERSION, sha256
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


def _current_success() -> dict:
    bundle = copy.deepcopy(_success())
    bundle.setdefault("metadata", {})["freshness"] = "current"
    return bundle


def _lost_ack() -> dict:
    return _load(_path("UPSTREAM_REPLAY_LOST_ACK_EXAMPLE"))


def _records(bundle: dict, kind: str) -> list[dict]:
    return [record for record in bundle["records"] if record["record_type"] == kind]


def _trusted_status(package: dict, **overrides) -> dict:
    status = {
        "record_id": package["record"]["decision_id"],
        "authority_basis": package["record"]["authority"]["authority_basis"],
        "evaluation_scope": "recipient_reliance",
        "evaluated_at": "2026-10-06T00:00:00Z",
        "evidence_freshness": "current",
        "freshness": "current",
        "revoked": False,
        "superseded": False,
        "authority_valid_at_decision_verified": True,
    }
    status.update(overrides)
    return status


def _policy(package: dict | None = None, **overrides):
    policy = {
        "supported_profiles": [PROFILE_ID],
        "relying_party": "recipient.example.org",
        "purpose": "audit",
        "now": "2026-10-06T00:00:00Z",
        "trusted_digests": [],
        "trusted_key_refs": [],
        "status_inputs": {},
    }
    if package is not None:
        policy["trusted_digests"] = [package["package_digest"]]
        policy["status_inputs"] = _trusted_status(package)
    policy.update(overrides)
    return policy


def _cp_only_decision(result: str) -> dict:
    bundle = copy.deepcopy(_success())
    bundle.setdefault("metadata", {})["freshness"] = "current"
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


def _recompute_digests(package: dict) -> None:
    package["integrity"]["value"] = sha256({"record": package["record"], "profile": package["profile"]})
    package["package_digest"] = sha256({"record": package["record"], "profile": package["profile"], "integrity": package["integrity"], "provenance": package["provenance"]})


def test_authorized_success_exports_and_recipient_gets_informational_only_without_authentication():
    package = export_cognous_stack_package(_manifest(), _current_success())
    validate_record(package["record"])
    assert package["record"]["schema_version"] == "0.1"
    assert package["profile"]["document_version"] == "0.2"
    assert package["profile"]["implementation_profile"] == PROFILE_ID
    assert package["record"]["decision_type"] == "agent_action_authorized"
    assert package["provenance"]["execution_facts"]["acknowledgement_summary"] == "received"
    assert package["provenance"]["execution_facts"]["destination_observed"] == "applied"
    result = evaluate_recipient_package(package, _policy(package, allow_unauthenticated_informational_inspection=True))
    assert result["schema_validity"]["status"] == "pass"
    assert result["declared_profile_conformance"]["status"] == "pass"
    assert result["package_content_integrity"]["status"] == "pass"
    assert result["integrity_authentication_checks"]["status"] == "unavailable"
    assert result["historical_authority_assertions"]["status"] == "pass"
    assert result["authority_status_and_freshness"]["status"] == "pass"
    assert result["recipient_reliance_decision"]["status"] == "informational_only"


def test_record_self_assertions_do_not_pass_authority_without_external_status_inputs():
    package = export_cognous_stack_package(_manifest(), _current_success())
    result = evaluate_recipient_package(package, _policy())
    assert result["schema_validity"]["status"] == "pass"
    assert result["package_content_integrity"]["status"] == "pass"
    assert result["integrity_authentication_checks"]["status"] == "unavailable"
    assert result["historical_authority_assertions"]["status"] == "unavailable"
    assert result["authority_status_and_freshness"]["status"] == "unavailable"
    assert result["recipient_reliance_decision"]["status"] == "fail"


@pytest.mark.parametrize("decision_result,expected_type", [("hold", "agent_action_held"), ("deny", "agent_action_denied")])
def test_hold_and_deny_with_no_effect_are_valid_governance_records_without_human_disposition(decision_result: str, expected_type: str):
    package = export_cognous_stack_package(_manifest(), _cp_only_decision(decision_result))
    validate_record(package["record"])
    assert package["record"]["decision_type"] == expected_type
    assert package["record"]["human_disposition"]["status"] == "unknown"
    assert package["record"]["machine_role"]["role"] == "escalation"
    assert package["provenance"]["execution_facts"]["destination_observed"] == "unavailable"
    assert package["provenance"]["execution_facts"]["acknowledgement_summary"] == "not_applicable"


def test_hold_with_execution_evidence_rejects_as_contradictory():
    bundle = copy.deepcopy(_current_success())
    decision = _records(bundle, "runtime_decision")[0]
    decision["data"]["result"] = "hold"
    decision["data"].pop("binding", None)
    with pytest.raises(ExportError):
        export_cognous_stack_package(_manifest(), bundle)


def test_authorized_but_never_executed_does_not_claim_machine_execution():
    bundle = copy.deepcopy(_current_success())
    bundle["records"] = [r for r in bundle["records"] if r["record_type"] in {"runtime_proposal", "runtime_decision"}]
    package = export_cognous_stack_package(_manifest(), bundle)
    assert package["record"]["decision_type"] == "agent_action_authorized"
    assert package["record"]["machine_role"]["role"] == "assistance"
    assert package["provenance"]["execution_facts"]["destination_observed"] == "unavailable"


def test_lost_ack_preserves_unknown_ack_and_applied_destination():
    bundle = _lost_ack()
    bundle.setdefault("metadata", {})["freshness"] = "current"
    package = export_cognous_stack_package(_manifest(), bundle)
    facts = package["provenance"]["execution_facts"]
    assert facts["acknowledgement_summary"] == "unknown"
    assert facts["destination_observed"] == "applied"
    assert facts["destination_observation_counts"].get("applied") == 2


def test_duplicate_restart_reconciliation_non_new_control_plane_attempt_reference():
    bundle = _lost_ack()
    bundle.setdefault("metadata", {})["freshness"] = "current"
    result = _records(bundle, "execution_result")[0]
    cp_attempt = _records(bundle, "control_plane_attempt_transition")[0]["data"]["attempt_id"]
    result["data"]["attempt_id"] = cp_attempt
    result["identifiers"]["attempt_id"] = cp_attempt
    result["data"]["status"] = "reconciled"
    result["data"]["newly_executed"] = False
    package = export_cognous_stack_package(_manifest(), bundle)
    assert package["provenance"]["execution_facts"]["execution_results"][0]["newly_executed"] is False


def test_partial_delivery_remains_visible_and_not_overridden_by_applied():
    bundle = copy.deepcopy(_current_success())
    obs = _records(bundle, "effect_observation")[0]
    obs["data"]["state"] = "partial"
    package = export_cognous_stack_package(_manifest(), bundle)
    assert package["provenance"]["execution_facts"]["destination_observed"] == "partial"


@pytest.mark.parametrize("mutation", ["payload", "target", "proposal_commitment", "dangling_reference", "destination_substitution"])
def test_tampering_and_mismatched_references_reject(mutation: str):
    bundle = copy.deepcopy(_current_success())
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
    package = export_cognous_stack_package(_manifest(), _current_success())
    wrong_purpose = evaluate_recipient_package(package, _policy(package, purpose="production_reuse"))
    assert wrong_purpose["consumption_conditions"]["status"] == "fail"
    assert wrong_purpose["recipient_reliance_decision"]["status"] == "fail"
    wrong_recipient = evaluate_recipient_package(package, _policy(package, relying_party="other.example.org"))
    assert wrong_recipient["consumption_conditions"]["status"] == "fail"


def test_recipient_rejects_revoked_expired_stale_unsupported_and_tampered():
    package = export_cognous_stack_package(_manifest(), _current_success())
    revoked = evaluate_recipient_package(package, _policy(package, status_inputs=_trusted_status(package, revoked=True, freshness="revoked")))
    assert revoked["authority_status_and_freshness"]["status"] == "fail"
    expired = evaluate_recipient_package(package, _policy(package, now="2030-01-01T00:00:00Z"))
    assert expired["authority_status_and_freshness"]["status"] == "fail"
    stale = evaluate_recipient_package(package, _policy(package, status_inputs=_trusted_status(package, evidence_freshness="stale")))
    assert stale["authority_status_and_freshness"]["status"] == "fail"
    unsupported = evaluate_recipient_package(package, _policy(package, supported_profiles=["other_profile"]))
    assert unsupported["declared_profile_conformance"]["status"] == "unsupported"
    tampered = copy.deepcopy(package)
    tampered["record"]["decision_type"] = "agent_action_denied"
    assert evaluate_recipient_package(tampered, _policy(package))["package_content_integrity"]["status"] == "fail"


def test_altered_provenance_with_unchanged_package_digest_fails_content_integrity():
    bundle = copy.deepcopy(_current_success())
    obs = _records(bundle, "effect_observation")[0]
    obs["data"]["state"] = "partial"
    package = export_cognous_stack_package(_manifest(), bundle)
    assert package["provenance"]["execution_facts"]["destination_observed"] == "partial"
    altered = copy.deepcopy(package)
    altered["provenance"]["execution_facts"]["destination_observed"] = "applied"
    result = evaluate_recipient_package(altered, _policy(package))
    assert result["package_content_integrity"]["status"] == "fail"
    assert result["recipient_reliance_decision"]["status"] == "fail"


def test_recomputed_hashes_do_not_create_issuer_authentication_or_reliance():
    package = export_cognous_stack_package(_manifest(), _current_success())
    altered = copy.deepcopy(package)
    altered["provenance"]["execution_facts"]["destination_observed"] = "applied"
    _recompute_digests(altered)
    result = evaluate_recipient_package(altered, _policy(altered))
    assert result["package_content_integrity"]["status"] == "pass"
    assert result["integrity_authentication_checks"]["status"] == "unavailable"
    assert result["recipient_reliance_decision"]["status"] == "fail"


def test_absent_recipient_clock_with_expired_record_prevents_acceptance():
    package = export_cognous_stack_package(_manifest(), _current_success(), expires_at="2020-01-01T00:00:00Z")
    result = evaluate_recipient_package(package, _policy(package, now=None))
    assert result["authority_status_and_freshness"]["status"] == "fail"
    assert result["recipient_reliance_decision"]["status"] == "fail"


@pytest.mark.parametrize("status_override", [
    {"record_id": "wrong-record"},
    {"authority_basis": "wrong-authority"},
    {"evaluation_scope": "unsupported"},
    {"evaluated_at": "not-a-time"},
    {"authority_valid_at_decision_verified": False},
])
def test_missing_stale_and_mismatched_authority_status_evidence_blocks_acceptance(status_override: dict):
    package = export_cognous_stack_package(_manifest(), _current_success())
    result = evaluate_recipient_package(package, _policy(package, status_inputs=_trusted_status(package, **status_override)))
    assert result["historical_authority_assertions"]["status"] in {"fail", "pass"}
    assert result["authority_status_and_freshness"]["status"] == "fail"
    assert result["recipient_reliance_decision"]["status"] == "fail"


def test_unsupported_package_profile_and_canonicalization_versions_are_not_accepted():
    package = export_cognous_stack_package(_manifest(), _current_success())
    bad_package = copy.deepcopy(package)
    bad_package["package_version"] = "9.9.9"
    assert evaluate_recipient_package(bad_package, _policy(package))["declared_profile_conformance"]["status"] == "unsupported"
    bad_profile = copy.deepcopy(package)
    bad_profile["profile"]["implementation_profile_version"] = "9.9.9"
    _recompute_digests(bad_profile)
    assert evaluate_recipient_package(bad_profile, _policy(bad_profile))["declared_profile_conformance"]["status"] == "unsupported"
    bad_canon = copy.deepcopy(package)
    bad_canon["integrity"]["canonicalization_profile"] = "unsupported"
    bad_canon["package_digest"] = sha256({"record": bad_canon["record"], "profile": bad_canon["profile"], "integrity": bad_canon["integrity"], "provenance": bad_canon["provenance"]})
    assert evaluate_recipient_package(bad_canon, _policy(bad_canon))["package_content_integrity"]["status"] == "unsupported"
    assert package["integrity"]["canonicalization_profile"] == CANONICALIZATION_PROFILE
    assert package["profile"]["implementation_profile_version"] == PROFILE_VERSION


def test_unknown_decision_time_is_export_limitation_and_unknown_freshness_is_not_invented_current():
    missing_time = copy.deepcopy(_success())
    missing_time.setdefault("metadata", {}).pop("freshness", None)
    _records(missing_time, "runtime_decision")[0]["data"].pop("decided_at", None)
    with pytest.raises(ExportError, match="decision_timestamp is required"):
        export_cognous_stack_package(_manifest(), missing_time)
    package = export_cognous_stack_package(_manifest(), _success())
    assert package["record"]["status"]["freshness"] == "unknown"
    result = evaluate_recipient_package(package, _policy(package))
    assert result["authority_status_and_freshness"]["status"] == "fail"


def test_redacted_derivative_and_source_findings_survive_export():
    bundle = copy.deepcopy(_current_success())
    bundle["derivation"] = {"relationship": "redacted_derivative", "source_bundle_id": "source-bundle", "derived_at": "2026-10-06T00:00:00Z"}
    bundle.setdefault("metadata", {})["redacted_fields"] = ["payload.customer_id"]
    package = export_cognous_stack_package(_manifest(), bundle)
    assert package["provenance"]["redaction"]["status"] == "redacted_derivative"
    assert package["provenance"]["replay_validation"]["findings"] is not None


def test_consumer_evaluation_does_not_change_exported_package():
    package = export_cognous_stack_package(_manifest(), _current_success())
    before = copy.deepcopy(package)
    evaluate_recipient_package(package, _policy(package))
    assert package == before
