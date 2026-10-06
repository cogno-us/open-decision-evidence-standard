from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any

from .common import (
    CANONICALIZATION_PROFILE,
    DOCUMENT_VERSION,
    PACKAGE_TYPE,
    PACKAGE_VERSION,
    PINNED_REVISIONS,
    PROFILE_ID,
    PROFILE_VERSION,
    SCHEMA_NAME,
    SCHEMA_VERSION,
    sha256,
    utc_now_iso,
)
from .schema_validation import validate_record


class ExportError(ValueError):
    """Raised when retained producer records cannot support a bounded ODES export."""


def _obj(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExportError(f"{path} must be an object")
    return value


def _records(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    records = bundle.get("records")
    if not isinstance(records, list) or not records:
        raise ExportError("Reconstruction Bundle must contain a nonempty records array")
    return [_obj(record, f"records[{index}]") for index, record in enumerate(records)]


def _data(record: dict[str, Any]) -> dict[str, Any]:
    return _obj(record.get("data"), "record.data")


def _group(bundle: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in sorted(_records(bundle), key=lambda item: item.get("source_sequence", 0)):
        grouped[str(record.get("record_type"))].append(record)
    return grouped


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _manifest_id(manifest: dict[str, Any]) -> str:
    value = _first(manifest, "manifest_id", "id", "name")
    if not value:
        raise ExportError("Manifest identity is required")
    return str(value)


def _manifest_version(manifest: dict[str, Any]) -> str:
    value = _first(manifest, "manifest_version", "version", "schema_version")
    if str(value) != "1.1":
        raise ExportError(f"unsupported Manifest version {value!r}; expected 1.1")
    return str(value)


def _actions(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("actions", "tool_actions", "action_inventory", "declared_actions"):
        if isinstance(manifest.get(key), list):
            return [item for item in manifest[key] if isinstance(item, dict)]
    output: list[dict[str, Any]] = []
    for tool in manifest.get("tools", []) if isinstance(manifest.get("tools"), list) else []:
        if isinstance(tool, dict):
            for action in tool.get("actions", []) if isinstance(tool.get("actions"), list) else []:
                if isinstance(action, dict):
                    copied = dict(action)
                    copied.setdefault("tool_name", tool.get("tool_name") or tool.get("name") or tool.get("tool_id"))
                    output.append(copied)
    return output


def _find_action(manifest: dict[str, Any], action_id: str | None) -> dict[str, Any] | None:
    for action in _actions(manifest):
        if action_id in {action.get("action_id"), action.get("name"), action.get("action_name")}:
            return action
    return None


def _decision_result(data: dict[str, Any]) -> str:
    raw = str(_first(data, "result", "decision", "authorization", "status") or "unknown").lower().strip()
    if raw in {"allow", "allowed", "authorized", "grant", "granted", "approved"}:
        return "authorized"
    if raw in {"hold", "held", "escalate", "pending", "requires_review", "review"}:
        return "held"
    if raw in {"deny", "denied", "block", "blocked", "reject", "rejected"}:
        return "denied"
    return raw or "unknown"


def _state(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("state") or value.get("status") or value.get("result")
    raw = str(value or "unknown").lower().strip()
    if raw in {"applied", "present", "delivered", "success", "succeeded", "executed", "reconciled"}:
        return "applied"
    if raw in {"partial", "partially_applied", "partial_delivery"}:
        return "partial"
    if raw in {"absent", "not_found", "not_applied", "safe_to_retry"}:
        return "absent"
    if raw in {"unknown", "timeout", "acknowledgement_lost", "lost", "unavailable"}:
        return "unknown"
    return raw


def _extract_replay_inputs(bundle: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    grouped = _group(bundle)
    proposals = [_data(r) for r in grouped.get("runtime_proposal", [])]
    if len(proposals) > 1:
        raise ExportError("export supports one retained runtime_proposal operation")
    cp = {
        "run_id": bundle.get("run_id"),
        "decisions": [_data(r) for r in grouped.get("runtime_decision", [])],
        "attempts": [_data(r) for r in grouped.get("control_plane_attempt_transition", [])],
        "observations": [_data(r) for r in grouped.get("effect_observation", [])],
        "reconciliations": [_data(r) for r in grouped.get("reconciliation", [])],
    }
    proposal = proposals[0] if proposals else None
    has_execution = any(grouped.get(kind) for kind in ("execution_envelope", "execution_result", "destination_attempt", "destination_effect"))
    if not has_execution:
        return cp, proposal, None
    if len(grouped.get("execution_envelope", [])) != 1 or len(grouped.get("execution_result", [])) != 1:
        raise ExportError("execution evidence must include exactly one execution_envelope and one execution_result when present")
    moltbot = {
        "execution_envelope": _data(grouped["execution_envelope"][0]),
        "execution_result": _data(grouped["execution_result"][0]),
        "attempts": [_data(r) for r in grouped.get("destination_attempt", [])],
        "attempt_events": [_data(r) for r in grouped.get("destination_attempt_event", [])],
        "effects": [_data(r) for r in grouped.get("destination_effect", [])],
    }
    return cp, proposal, moltbot


def _run_replay_validation(bundle: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    cp, proposal, moltbot = _extract_replay_inputs(bundle)
    try:
        from agent_replay_bundle.importers import ImportContractError as ReplayImportContractError
        from agent_replay_bundle.importers import import_bounded_workflow
    except Exception as exc:  # pragma: no cover - exercised in environments without the pinned validator
        raise ExportError("pinned Replay validator is unavailable; install cogno-us/cognous-agent-replay-bundle at the pinned revision") from exc
    try:
        reconstructed = import_bounded_workflow(cp, proposal=proposal, moltbot_export=moltbot)
    except ReplayImportContractError as exc:
        raise ExportError(f"pinned Replay semantic validation failed: {exc}") from exc
    status = getattr(reconstructed, "status", "unknown")
    findings: list[dict[str, Any]] = []
    for report in getattr(reconstructed, "import_reports", []) or []:
        for finding in getattr(report, "findings", []) or []:
            findings.append(finding.model_dump() if hasattr(finding, "model_dump") else dict(finding))
    return str(status), findings


def _validate_manifest_binding(manifest: dict[str, Any], proposal: dict[str, Any] | None) -> None:
    _manifest_version(manifest)
    if not _actions(manifest):
        raise ExportError("Manifest must declare at least one action")
    if proposal is None:
        return
    if proposal.get("manifest_id") != _manifest_id(manifest):
        raise ExportError("proposal.manifest_id does not match supplied Manifest")
    if str(proposal.get("manifest_version")) != _manifest_version(manifest):
        raise ExportError("proposal.manifest_version does not match supplied Manifest")
    if proposal.get("manifest_digest") != sha256(manifest):
        raise ExportError("proposal.manifest_digest does not match supplied Manifest digest")
    if proposal.get("payload_commitment") != sha256(proposal.get("payload")):
        raise ExportError("proposal.payload_commitment does not match proposal.payload")


def _check_decision_execution_consistency(bundle: dict[str, Any]) -> tuple[dict[str, Any], str]:
    grouped = _group(bundle)
    decisions = [_data(record) for record in grouped.get("runtime_decision", [])]
    if len(decisions) != 1:
        raise ExportError("export supports exactly one retained runtime_decision")
    decision = decisions[0]
    result = _decision_result(decision)
    binding = decision.get("binding") if isinstance(decision.get("binding"), dict) else None
    has_execution = any(grouped.get(kind) for kind in ("execution_envelope", "execution_result", "destination_attempt", "destination_effect"))
    if result == "authorized" and binding is None:
        raise ExportError("authorized decision requires an authorization binding")
    if result != "authorized" and binding is not None:
        raise ExportError("held/denied decisions must not carry an authorization binding in this bounded profile")
    if result != "authorized" and has_execution:
        raise ExportError("held/denied decisions must not include execution or destination-effect evidence")
    if result == "authorized" and has_execution:
        proposal = _data(grouped.get("runtime_proposal", [])[0]) if grouped.get("runtime_proposal") else None
        if proposal is None:
            raise ExportError("authorized execution requires retained proposal for commitment validation")
        if binding.get("proposal_commitment") != sha256(proposal):
            raise ExportError("decision.binding.proposal_commitment does not match retained proposal")
        envelope = _data(grouped["execution_envelope"][0])
        operation = envelope.get("operation")
        if not isinstance(operation, dict):
            raise ExportError("execution_envelope.operation is required")
        if operation.get("proposal_commitment") != binding.get("proposal_commitment"):
            raise ExportError("execution envelope proposal commitment does not match decision binding")
        if operation.get("target") != proposal.get("target"):
            raise ExportError("execution target does not match proposal target")
        if operation.get("payload_commitment") != proposal.get("payload_commitment"):
            raise ExportError("execution payload commitment does not match proposal")
        allowed_attempts = {a.get("attempt_id") for a in [_data(r) for r in grouped.get("destination_attempt", [])]}
        allowed_attempts |= {a.get("attempt_id") for a in [_data(r) for r in grouped.get("control_plane_attempt_transition", [])]}
        allowed_attempts.discard(None)
        result_record = _data(grouped["execution_result"][0])
        attempt_id = result_record.get("attempt_id")
        if attempt_id and attempt_id not in allowed_attempts:
            raise ExportError("execution_result.attempt_id does not reference a retained destination or Control Plane attempt")
        for dest in [_data(r) for r in grouped.get("destination_effect", [])]:
            if dest.get("target") != operation.get("target"):
                raise ExportError("destination_effect.target does not match execution operation target")
    return decision, result


def _source_refs(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    refs = []
    for index, record in enumerate(_records(bundle)):
        refs.append({
            "record_id": str(record.get("record_id") or f"records[{index}]"),
            "record_type": str(record.get("record_type") or "unknown"),
            "source_path": str(record.get("source_path") or f"records[{index}]"),
            "producer_profile_id": record.get("producer_profile_id"),
            "hash": sha256(record),
        })
    return refs


def _event_summary(bundle: dict[str, Any]) -> dict[str, Any]:
    grouped = _group(bundle)
    cp_statuses: Counter[str] = Counter()
    ack_sources: list[dict[str, Any]] = []
    execution_results: list[dict[str, Any]] = []
    destination_effects: list[dict[str, Any]] = []
    observations: Counter[str] = Counter()
    reconciliations: Counter[str] = Counter()
    cp_attempts: set[str] = set()
    executor_attempts: set[str] = set()
    for record in grouped.get("control_plane_attempt_transition", []):
        data = _data(record)
        cp_statuses[str(data.get("status") or "unknown")] += 1
        if data.get("attempt_id"):
            cp_attempts.add(str(data["attempt_id"]))
        ack = data.get("acknowledgement")
        if isinstance(ack, dict) and ack:
            ack_sources.append({"record_id": record.get("record_id"), "status": "received", "attempt_id": ack.get("attempt_id"), "source": "control_plane_transition.acknowledgement"})
        elif str(data.get("status") or "").lower() in {"unknown", "acknowledgement_lost", "lost"}:
            ack_sources.append({"record_id": record.get("record_id"), "status": "unknown", "source": "control_plane_transition.status"})
    for record in grouped.get("destination_attempt", []):
        data = _data(record)
        if data.get("attempt_id"):
            executor_attempts.add(str(data["attempt_id"]))
    for record in grouped.get("execution_result", []):
        data = _data(record)
        status = "received" if data.get("acknowledged") is True or data.get("status") in {"executed", "reconciled"} else _state(data.get("status"))
        if data.get("acknowledged") is False:
            status = "unknown"
        execution_results.append({"record_id": record.get("record_id"), "status": status, "attempt_id": data.get("attempt_id"), "newly_executed": data.get("newly_executed"), "observed_state": data.get("observed_state")})
    for record in grouped.get("destination_effect", []):
        data = _data(record)
        destination_effects.append({"record_id": record.get("record_id"), "effect_id": data.get("effect_id"), "state": _state(data.get("status") or data.get("state") or "applied"), "target_hash": sha256(data.get("target"))})
        observations[_state(data.get("status") or data.get("state") or "applied")] += 1
    for record in grouped.get("effect_observation", []):
        observations[_state(_data(record).get("state"))] += 1
    for record in grouped.get("reconciliation", []):
        reconciliations[_state(_data(record).get("result"))] += 1
    if not ack_sources and not execution_results:
        ack_summary = "not_applicable"
    elif any(item.get("status") == "received" for item in ack_sources + execution_results):
        ack_summary = "received"
    else:
        ack_summary = "unknown"
    if observations.get("partial"):
        destination_summary = "partial"
    elif observations.get("unknown"):
        destination_summary = "unknown"
    elif observations.get("absent"):
        destination_summary = "absent"
    elif observations.get("applied"):
        destination_summary = "applied"
    else:
        destination_summary = "unavailable"
    return {
        "control_plane_transition_statuses": dict(sorted(cp_statuses.items())),
        "control_plane_attempt_ids": sorted(cp_attempts),
        "executor_attempt_ids": sorted(executor_attempts),
        "acknowledgement_summary": ack_summary,
        "acknowledgement_sources": ack_sources,
        "execution_results": execution_results,
        "destination_effects": destination_effects,
        "destination_observation_counts": dict(sorted(observations.items())),
        "destination_observed": destination_summary,
        "reconciliation_counts": dict(sorted(reconciliations.items())),
        "independent_delivery_verification": "unavailable",
    }


def _status_from_sources(bundle: dict[str, Any], decision_result: str) -> dict[str, Any]:
    metadata = bundle.get("metadata") if isinstance(bundle.get("metadata"), dict) else {}
    freshness = metadata.get("odes_freshness") or metadata.get("freshness") or "current"
    revoked = bool(metadata.get("revoked") or freshness == "revoked")
    superseded = bool(metadata.get("superseded") or freshness == "superseded")
    if decision_result in {"held", "denied"} and freshness == "current":
        freshness = "current"
    status = {"freshness": str(freshness), "superseded": superseded, "revoked": revoked}
    if superseded:
        status["superseded_by"] = str(metadata.get("superseded_by") or "unavailable-superseding-record")
    if revoked:
        status["revoked_at"] = str(metadata.get("revoked_at") or metadata.get("generated_at") or bundle.get("generated_at") or utc_now_iso())
    return status


def export_cognous_stack_package(manifest: dict[str, Any], reconstruction_bundle: dict[str, Any], *, relying_party: str = "recipient.example.org", purpose: str = "audit", expires_at: str = "2027-01-01T00:00:00Z") -> dict[str, Any]:
    manifest = deepcopy(_obj(manifest, "manifest"))
    bundle = deepcopy(_obj(reconstruction_bundle, "reconstruction_bundle"))
    replay_status, replay_findings = _run_replay_validation(bundle)
    _validate_manifest_binding(manifest, _extract_replay_inputs(bundle)[1])
    decision, decision_result = _check_decision_execution_consistency(bundle)
    grouped = _group(bundle)
    proposal = _data(grouped.get("runtime_proposal", [])[0]) if grouped.get("runtime_proposal") else {}
    binding = decision.get("binding") if isinstance(decision.get("binding"), dict) else {}
    action = _find_action(manifest, proposal.get("action_id") or binding.get("action_id")) or {}
    decided_at = decision.get("decided_at") or bundle.get("generated_at") or utc_now_iso()
    policy_versions = binding.get("policy_versions") if isinstance(binding.get("policy_versions"), list) else []
    policy_basis = []
    for item in policy_versions:
        if isinstance(item, dict):
            policy_basis.append({"policy_id": str(item.get("ref") or item.get("policy_id") or "unknown_policy"), "policy_version": str(item.get("version") or "unknown"), "policy_type": "internal_policy"})
    if not policy_basis:
        policy_basis.append({"policy_id": str(binding.get("requirement_id") or proposal.get("requirement_id") or action.get("action_id") or "unavailable_policy_basis"), "policy_type": "authority_requirement"})
    authority_basis = str(binding.get("grant_id") or proposal.get("authority_context_ref") or action.get("authority_requirement") or "unavailable_authority_basis")
    authority_valid = decision_result == "authorized"
    if decision_result == "held":
        human_status = "escalated"
    elif decision_result == "denied":
        human_status = "rejected"
    else:
        human_status = "unknown"
    record = {
        "record_type": "portable_decision_evidence_record",
        "schema_version": SCHEMA_VERSION,
        "decision_id": str(decision.get("decision_id") or sha256(decision)),
        "decision_type": f"agent_action_{decision_result}",
        "decision_timestamp": str(decided_at),
        "issuer": {"organization_id": "cognous.synthetic.baseline", "system_id": "cognous-stack-exporter"},
        "authority": {"human_reviewer_role": "unknown", "authority_basis": authority_basis, "authority_valid_at_decision": authority_valid},
        "machine_role": {"ai_used": True, "role": "execution" if decision_result == "authorized" else "escalation", "model_id": "unavailable", "model_version": "unavailable", "runtime_profile": "cognous-bounded-synthetic-baseline"},
        "human_disposition": {"status": human_status, "review_substantiveness": "unknown", "machine_reliance_level": "unknown"},
        "evidence": {"evidence_commitment_type": "hash", "evidence_hash": sha256({"manifest": manifest, "reconstruction_bundle": bundle}), "selective_disclosure_available": bool(bundle.get("derivation"))},
        "policy_basis": policy_basis,
        "risk_coordinates": {"risk_tier": "unknown", "jurisdiction": "synthetic", "restricted_use_flag": False, "prohibited_use_flag": False},
        "consumption_conditions": {"permitted_relying_parties": [relying_party], "permitted_purposes": [purpose], "expires_at": expires_at},
        "status": _status_from_sources(bundle, decision_result),
        "verification": {"signature_type": "content-digest", "issuer_key_reference": "content-digest-only:no-public-issuer-authentication", "conformance_profile": PROFILE_ID},
    }
    validate_record(record)
    event_summary = _event_summary(bundle)
    package_core = {
        "record": record,
        "profile": {"implementation_profile": PROFILE_ID, "implementation_profile_version": PROFILE_VERSION, "document_version": DOCUMENT_VERSION, "schema_name": SCHEMA_NAME, "schema_version": SCHEMA_VERSION},
    }
    package = {
        "package_type": PACKAGE_TYPE,
        "package_version": PACKAGE_VERSION,
        "created_by": "open-decision-evidence-standard/reference-exporter",
        "created_at": utc_now_iso(),
        "record": record,
        "profile": package_core["profile"],
        "integrity": {"kind": "content-digest", "algorithm": "SHA-256", "canonicalization_profile": CANONICALIZATION_PROFILE, "value": sha256(package_core), "verification_claim": "Binds the exported ODES record and profile metadata only; does not establish issuer identity or institutional authority."},
        "provenance": {
            "pinned_revisions": PINNED_REVISIONS,
            "source_artifacts": {"manifest_digest": sha256(manifest), "reconstruction_bundle_digest": sha256(bundle)},
            "replay_validation": {"status": replay_status, "required_revision": PINNED_REVISIONS["replay"], "findings": replay_findings},
            "source_record_refs": _source_refs(bundle),
            "decision_facts": {"decision_result": decision_result, "proposal_commitment": binding.get("proposal_commitment"), "actor": proposal.get("actor") or binding.get("actor"), "principal": proposal.get("principal") or binding.get("principal"), "grant_revision": binding.get("grant_revision"), "policy_versions": policy_versions, "reasons": decision.get("reasons", [])},
            "execution_facts": event_summary,
            "redaction": {"derivation": bundle.get("derivation"), "status": "redacted_derivative" if bundle.get("derivation") else "not_declared"},
            "unsupported_semantics": ["pder-v0.1 has no native fields for effect_id, separate Control Plane and executor attempt namespaces, reconciliation records, execution-result namespaces, restart recovery, partial delivery detail, or producer import findings; these are carried in this package provenance and in the proposed profile, not in the base record."],
            "limits": ["Export creates no external effect and renews no authorization.", "Schema validity does not establish deployment approval, operational effectiveness, compliance, current authority, delivery success, independent review, or institutional adoption.", "BitRep and The Index are related optional evidence interfaces and are not mandatory for generic ODES adoption."],
        },
    }
    package["package_digest"] = sha256({"record": package["record"], "profile": package["profile"], "integrity": package["integrity"], "provenance": package["provenance"]})
    return package
