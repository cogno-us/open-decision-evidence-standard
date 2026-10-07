from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from .common import (
    CANONICALIZATION_PROFILE,
    PACKAGE_TYPE,
    PACKAGE_VERSION,
    PROFILE_ID,
    PROFILE_V2_ID,
    PROFILE_V2_VERSION,
    PINNED_V2_REVISIONS,
    PROFILE_VERSION,
    SCHEMA_NAME,
    SCHEMA_VERSION,
    SUPPORTED_V2_CONTROL_PLANE_REVISIONS,
    SUPPORTED_V2_REPLAY_REVISIONS,
    parse_time,
    sha256,
)
from .schema_validation import schema_errors


def _result(status: str, reasons: list[str] | None = None, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"status": status, "reasons": reasons or [], "evidence": evidence or {}}


def _material_package_content(package: dict[str, Any]) -> dict[str, Any]:
    return {
        "record": package.get("record"),
        "profile": package.get("profile"),
        "integrity": package.get("integrity"),
        "provenance": package.get("provenance"),
    }


def _package_core(package: dict[str, Any]) -> dict[str, Any]:
    return {"record": package.get("record"), "profile": package.get("profile")}


def _parse_time_result(value: Any, label: str) -> tuple[datetime | None, list[str]]:
    if not isinstance(value, str) or not value:
        return None, [f"{label} is unavailable"]
    try:
        parsed = parse_time(value)
        if parsed is None or parsed.tzinfo is None or parsed.utcoffset() is None:
            return None, [f"{label} must include a timezone"]
        return parsed, []
    except Exception:
        return None, [f"{label} is malformed"]


def _evaluate_schema(record: dict[str, Any]) -> dict[str, Any]:
    errors = schema_errors(record)
    if errors:
        return _result("fail", errors)
    return _result("pass")


def _evaluate_profile(package: dict[str, Any], supported_profiles: list[str]) -> dict[str, Any]:
    reasons: list[str] = []
    profile = package.get("profile") if isinstance(package.get("profile"), dict) else {}
    record = package.get("record") if isinstance(package.get("record"), dict) else {}
    declared = profile.get("implementation_profile") or record.get("verification", {}).get("conformance_profile")
    if package.get("package_version") != PACKAGE_VERSION:
        return _result("unsupported", [f"unsupported package_version {package.get('package_version')!r}"], {"supported_package_version": PACKAGE_VERSION})
    if declared not in supported_profiles:
        return _result("unsupported", [f"unsupported declared profile {declared!r}"], {"declared_profile": declared, "supported_profiles": supported_profiles})
    if declared != record.get("verification", {}).get("conformance_profile"):
        reasons.append("package profile and record verification.conformance_profile differ")
    provenance = package.get("provenance") if isinstance(package.get("provenance"), dict) else {}
    selected_control_plane = provenance.get("pinned_revisions", {}).get("control_plane")
    if declared == PROFILE_ID and selected_control_plane in SUPPORTED_V2_CONTROL_PLANE_REVISIONS:
        reasons.append("repaired producer transformation cannot be relabeled as historical profile 0.1")
    if declared in {PROFILE_ID, PROFILE_V2_ID}:
        expected_version = PROFILE_V2_VERSION if declared == PROFILE_V2_ID else PROFILE_VERSION
        if profile.get("implementation_profile_version") != expected_version:
            return _result("unsupported", [f"unsupported implementation_profile_version {profile.get('implementation_profile_version')!r}"], {"supported_profile_version": expected_version})
        if profile.get("schema_name") != SCHEMA_NAME or profile.get("schema_version") != SCHEMA_VERSION:
            reasons.append("profile schema coordinates do not match pder-v0.1")
        if not isinstance(package.get("provenance"), dict):
            reasons.append("Cognous-stack profile requires package provenance outside the pder-v0.1 base record")
    return _result("fail" if reasons else "pass", reasons, {"declared_profile": declared, "implementation_profile_version": profile.get("implementation_profile_version")})


def _evaluate_package_content_integrity(package: dict[str, Any], trusted_digests: list[str]) -> dict[str, Any]:
    reasons: list[str] = []
    evidence: dict[str, Any] = {}
    integrity = package.get("integrity") if isinstance(package.get("integrity"), dict) else {}
    provenance = package.get("provenance") if isinstance(package.get("provenance"), dict) else {}

    if integrity.get("kind") != "content-digest":
        return _result("unsupported", ["no supported package content integrity method supplied"])
    if integrity.get("algorithm") != "SHA-256":
        return _result("unsupported", [f"unsupported integrity algorithm {integrity.get('algorithm')!r}"])
    if integrity.get("canonicalization_profile") != CANONICALIZATION_PROFILE:
        return _result("unsupported", [f"unsupported canonicalization_profile {integrity.get('canonicalization_profile')!r}"], {"supported_canonicalization_profile": CANONICALIZATION_PROFILE})

    record_profile_digest = sha256(_package_core(package))
    if integrity.get("value") != record_profile_digest:
        reasons.append("record/profile content digest does not match exported record and profile metadata")
    evidence["record_profile_digest"] = record_profile_digest

    expected_package_digest = sha256(_material_package_content(package))
    if package.get("package_digest") != expected_package_digest:
        reasons.append("package_digest does not match complete material package content")
    evidence["package_digest"] = expected_package_digest
    evidence["configured_trusted_digests"] = trusted_digests

    required_provenance = ["source_artifacts", "source_record_refs", "decision_facts", "execution_facts", "redaction", "unsupported_semantics", "limits"]
    for key in required_provenance:
        if key not in provenance:
            reasons.append(f"provenance.{key} is unavailable")
    if not isinstance(provenance.get("source_record_refs"), list):
        reasons.append("provenance.source_record_refs must be available as an array")
    if not isinstance(provenance.get("execution_facts"), dict):
        reasons.append("provenance.execution_facts must be available as an object")
    if not isinstance(provenance.get("unsupported_semantics"), list) or not isinstance(provenance.get("limits"), list):
        reasons.append("limitations and unsupported semantics must survive export")

    if reasons:
        return _result("fail", reasons, evidence)
    if trusted_digests and expected_package_digest not in trusted_digests and record_profile_digest not in trusted_digests:
        return _result("unavailable", ["content digest matches package but is not in the configured trusted digest set"], evidence)
    return _result("pass", ["complete material package content is bound by digest; this does not authenticate an issuer"], evidence)


def _evaluate_authentication(package: dict[str, Any], trusted_key_refs: list[str], trusted_digests: list[str]) -> dict[str, Any]:
    record = package.get("record") if isinstance(package.get("record"), dict) else {}
    verification = record.get("verification", {}) if isinstance(record.get("verification"), dict) else {}
    signature_type = verification.get("signature_type")
    key_ref = verification.get("issuer_key_reference")
    if signature_type == "content-digest":
        digest = package.get("package_digest")
        if digest in trusted_digests:
            return _result("unavailable", ["recipient trusts this content digest for inspection, but a public issuer authentication method is not supplied"], {"package_digest": digest})
        return _result("unavailable", ["content digest is not issuer authentication; no supported public authentication evidence supplied"], {"package_digest": digest})
    if signature_type in {"none", "unknown", None}:
        return _result("unavailable", ["no supported issuer authentication method supplied"])
    if key_ref not in trusted_key_refs:
        return _result("unavailable", ["issuer key reference is not explicitly trusted by recipient policy"], {"issuer_key_reference": key_ref})
    return _result("unsupported", ["signature verification profile is not implemented by this reference validator"], {"signature_type": signature_type, "issuer_key_reference": key_ref})


def _status_identity_matches(record: dict[str, Any], status_inputs: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    authority = record.get("authority", {}) if isinstance(record.get("authority"), dict) else {}
    if status_inputs.get("record_id") != record.get("decision_id"):
        reasons.append("status evidence record_id does not match record.decision_id")
    if status_inputs.get("authority_basis") != authority.get("authority_basis"):
        reasons.append("status evidence authority_basis does not match record.authority.authority_basis")
    scope = status_inputs.get("evaluation_scope")
    expected_scope = policy.get("evaluation_scope")
    if expected_scope not in {"recipient_reliance", "audit", "inspection"}:
        reasons.append("recipient policy evaluation_scope is unsupported or unavailable")
    elif scope != expected_scope:
        reasons.append("status evidence evaluation_scope does not match recipient policy evaluation_scope")
    return reasons


def _evaluate_historical_authority(record: dict[str, Any], status_inputs: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    evidence: dict[str, Any] = {}
    authority = record.get("authority", {}) if isinstance(record.get("authority"), dict) else {}
    asserted = authority.get("authority_valid_at_decision")
    evidence["record_assertion_authority_valid_at_decision"] = asserted
    if not status_inputs:
        return _result("unavailable", ["no external authority/status evidence supplied; record self-assertion is not authority verification"], evidence)
    reasons.extend(_status_identity_matches(record, status_inputs, policy))
    if status_inputs.get("authority_valid_at_decision_verified") is not True:
        reasons.append("external status evidence does not verify historical authority at decision time")
    if reasons:
        return _result("fail", reasons, evidence)
    return _result("pass", ["historical authority is accepted only under explicitly configured recipient status evidence"], evidence)


def _evaluate_authority_and_freshness(record: dict[str, Any], status_inputs: dict[str, Any], now: str | None, policy: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    evidence: dict[str, Any] = {}
    status = record.get("status", {}) if isinstance(record.get("status"), dict) else {}

    now_dt, now_errors = _parse_time_result(now, "recipient evaluation time")
    if now_errors:
        reasons.extend(now_errors)
    evidence["recipient_evaluation_time"] = now

    expires_at, expiry_errors = _parse_time_result(record.get("consumption_conditions", {}).get("expires_at"), "record consumption expiry")
    if expiry_errors:
        reasons.extend(expiry_errors)
    if expires_at and now_dt and expires_at < now_dt:
        reasons.append("record consumption window has expired under recipient policy time")

    if not isinstance(status_inputs, dict) or not status_inputs:
        return _result("unavailable", reasons + ["external status evidence is required for present authority/freshness acceptance"], {**evidence, "record_reported_freshness": status.get("freshness")})

    max_age = policy.get("status_max_age_seconds")
    valid_max_age = type(max_age) is int and max_age >= 0
    if not valid_max_age:
        reasons.append("recipient policy status_max_age_seconds must be an explicit non-negative integer")
    evidence["status_max_age_seconds"] = max_age
    reasons.extend(_status_identity_matches(record, status_inputs, policy))
    evaluated_at, evaluated_at_errors = _parse_time_result(status_inputs.get("evaluated_at"), "status evidence evaluated_at")
    if evaluated_at_errors:
        reasons.extend(evaluated_at_errors)
    else:
        evidence["status_evidence_evaluated_at"] = status_inputs.get("evaluated_at")
        if now_dt and evaluated_at:
            age_seconds = (now_dt - evaluated_at).total_seconds()
            evidence["status_age_seconds"] = age_seconds
            if age_seconds < 0:
                reasons.append("status evidence evaluated_at is after recipient evaluation time")
            elif valid_max_age and age_seconds > max_age:
                reasons.append("status evidence exceeds recipient policy status_max_age_seconds")
    if status_inputs.get("evidence_freshness") not in {"current", "recent"}:
        reasons.append("status evidence freshness is missing, stale, or unsupported")
    if status_inputs.get("authority_valid_at_decision_verified") is not True:
        reasons.append("status evidence does not verify historical authority required for present reliance")

    freshness = status_inputs.get("freshness")
    if freshness not in {"current"}:
        reasons.append(f"present freshness is not current: {freshness!r}")
    if status_inputs.get("revoked") is not False:
        reasons.append("status evidence does not establish non-revocation")
    if status_inputs.get("superseded") is not False:
        reasons.append("status evidence does not establish non-supersession")
    if status.get("freshness") in {"revoked", "superseded"} or status.get("revoked") is True or status.get("superseded") is True:
        reasons.append("record self-reported status is revoked or superseded")
    if status.get("freshness") in {"stale", "expired", "pending_revalidation", "unknown"}:
        reasons.append(f"record self-reported freshness is {status.get('freshness')}")

    return _result("fail" if reasons else "pass", reasons, {**evidence, "configured_status_inputs": status_inputs, "record_reported_freshness": status.get("freshness")})


def _evaluate_consumption(record: dict[str, Any], relying_party: str | None, purpose: str | None) -> dict[str, Any]:
    conditions = record.get("consumption_conditions", {})
    reasons: list[str] = []
    parties = conditions.get("permitted_relying_parties") if isinstance(conditions.get("permitted_relying_parties"), list) else []
    purposes = conditions.get("permitted_purposes") if isinstance(conditions.get("permitted_purposes"), list) else []
    if relying_party and parties and relying_party not in parties:
        reasons.append("recipient relying party is not permitted")
    if not relying_party and parties:
        reasons.append("recipient relying party is decision-critical but unavailable")
    if purpose and purpose not in purposes:
        reasons.append("recipient purpose is not permitted")
    if not purpose:
        reasons.append("recipient purpose is decision-critical but unavailable")
    return _result("fail" if reasons else "pass", reasons, {"permitted_relying_parties": parties, "permitted_purposes": purposes})


def _normalized_replay_material(package: dict[str, Any], expected: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compare semantic material while tolerating older accepted Replay adapter pins.

    Existing packages generated under the previous accepted Replay revision remain
    valid if their retained source records re-export to the same decision,
    execution, and recipient material. The selected Replay revision is provenance
    about the validator used, not a re-labeling of producer records.
    """
    left = deepcopy(_material_package_content(package))
    right = deepcopy(_material_package_content(expected))
    lprov = left.get("provenance") or {}
    rprov = right.get("provenance") or {}
    lreplay = (lprov.get("pinned_revisions") or {}).get("replay")
    if (lreplay == SUPPORTED_V2_REPLAY_REVISIONS[0]
            and lprov["pinned_revisions"].get("control_plane") != SUPPORTED_V2_CONTROL_PLANE_REVISIONS[0]):
        raise ValueError("historical Replay revision does not support selected Control Plane revision")
    if lreplay in SUPPORTED_V2_REPLAY_REVISIONS:
        rprov.setdefault("pinned_revisions", {})["replay"] = lreplay
        rprov.setdefault("replay_validation", {})["required_revision"] = lreplay
    if "supported_revisions" not in lprov:
        rprov.pop("supported_revisions", None)
    if "selected_revisions" not in lprov:
        rprov.pop("selected_revisions", None)
    else:
        rprov["selected_revisions"] = deepcopy(rprov["pinned_revisions"])
    return left, right


def _evaluate_replay_semantics(package: dict[str, Any]) -> dict[str, Any]:
    if package.get("profile", {}).get("implementation_profile") != PROFILE_V2_ID:
        return _result("not_applicable", ["historical profile validation unchanged"])
    try:
        from .exporter import export_cognous_stack_package
        sources = package["provenance"]["retained_sources"]
        conditions = package["record"]["consumption_conditions"]
        parties, purposes = conditions["permitted_relying_parties"], conditions["permitted_purposes"]
        if len(parties) != 1 or len(purposes) != 1:
            raise ValueError("implementation profile requires exact single-recipient/purpose export")
        expected = export_cognous_stack_package(sources["manifest"], sources["reconstruction_bundle"],
            relying_party=parties[0], purpose=purposes[0], expires_at=conditions["expires_at"])
        actual_material, expected_material = _normalized_replay_material(package, expected)
        if actual_material != expected_material:
            raise ValueError("package semantics differ from accepted Replay-derived transformation")
    except Exception as exc:
        return _result("fail", [f"Replay semantic validation failed: {exc}"])
    return _result("pass", ["retained content matches accepted Replay validation; no source authentication or authority renewal"])


def evaluate_recipient_package(package: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    package = deepcopy(package)
    policy = deepcopy(policy)
    if package.get("package_type") != PACKAGE_TYPE:
        return {"schema_validity": _result("not_evaluated", ["unsupported package_type"]), "recipient_reliance_decision": _result("fail", ["unsupported package_type"])}
    record = package.get("record") if isinstance(package.get("record"), dict) else {}
    trusted_digests = policy.get("trusted_digests", []) or policy.get("trusted_package_digests", []) or []
    status_inputs = policy.get("status_inputs", {})
    profile = package.get("profile") if isinstance(package.get("profile"), dict) else {}
    layers = {
        "schema_validity": _evaluate_schema(record),
        **({"replay_semantic_consistency": _evaluate_replay_semantics(package)}
           if profile.get("implementation_profile") == PROFILE_V2_ID else {}),
        "declared_profile_conformance": _evaluate_profile(package, policy.get("supported_profiles", [PROFILE_ID])),
        "package_content_integrity": _evaluate_package_content_integrity(package, trusted_digests),
        "integrity_authentication_checks": _evaluate_authentication(package, policy.get("trusted_key_refs", []), trusted_digests),
        "historical_authority_assertions": _evaluate_historical_authority(record, status_inputs, policy),
        "authority_status_and_freshness": _evaluate_authority_and_freshness(record, status_inputs, policy.get("now"), policy),
        "consumption_conditions": _evaluate_consumption(record, policy.get("relying_party"), policy.get("purpose")),
    }
    failed = [name for name, layer in layers.items() if layer["status"] not in {"pass"}]
    auth_unavailable_only = failed == ["integrity_authentication_checks"]
    if not failed:
        reliance = _result("pass", ["recipient policy permits reliance on the record as exported; this is not independent institutional review and does not prove the underlying decision correct"])
    elif policy.get("allow_unauthenticated_informational_inspection") is True and auth_unavailable_only:
        reliance = _result("informational_only", ["content integrity passed, but issuer authentication is unavailable; policy permits informational inspection only, not reliance or authorization"])
    else:
        reliance = _result("fail", ["recipient policy does not permit reliance because layer did not pass: " + ", ".join(failed)])
    layers["recipient_reliance_decision"] = reliance
    layers["boundary_notes"] = [
        "Schema validity is structural only.",
        "Package content digests bind material content but do not establish public issuer identity.",
        "Authentication, historical authority, present authority, and recipient reliance are separate evaluations.",
        "BitRep signature verification and Index inclusion, if supplied separately, do not create institutional authority.",
        "The recipient validator does not access producer databases or execute workflows.",
    ]
    return layers
