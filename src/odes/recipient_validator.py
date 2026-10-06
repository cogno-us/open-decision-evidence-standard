from __future__ import annotations

from copy import deepcopy
from typing import Any

from .common import PACKAGE_TYPE, PROFILE_ID, sha256, parse_time
from .schema_validation import schema_errors


def _result(status: str, reasons: list[str] | None = None, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"status": status, "reasons": reasons or [], "evidence": evidence or {}}


def _package_core(package: dict[str, Any]) -> dict[str, Any]:
    return {"record": package.get("record"), "profile": package.get("profile")}


def _evaluate_schema(record: dict[str, Any]) -> dict[str, Any]:
    errors = schema_errors(record)
    if errors:
        return _result("fail", errors)
    return _result("pass")


def _evaluate_profile(package: dict[str, Any], supported_profiles: list[str]) -> dict[str, Any]:
    profile = package.get("profile") if isinstance(package.get("profile"), dict) else {}
    declared = profile.get("implementation_profile") or package.get("record", {}).get("verification", {}).get("conformance_profile")
    if declared not in supported_profiles:
        return _result("unsupported", [f"unsupported declared profile {declared!r}"], {"declared_profile": declared, "supported_profiles": supported_profiles})
    if declared != package.get("record", {}).get("verification", {}).get("conformance_profile"):
        return _result("fail", ["package profile and record verification.conformance_profile differ"])
    if declared == PROFILE_ID and not isinstance(package.get("provenance"), dict):
        return _result("fail", ["Cognous-stack profile requires package provenance outside the pder-v0.1 base record"])
    return _result("pass", evidence={"declared_profile": declared})


def _evaluate_integrity(package: dict[str, Any], trusted_digests: list[str], trusted_key_refs: list[str]) -> dict[str, Any]:
    integrity = package.get("integrity") if isinstance(package.get("integrity"), dict) else {}
    verification = package.get("record", {}).get("verification", {}) if isinstance(package.get("record"), dict) else {}
    if integrity.get("kind") == "content-digest":
        expected = sha256(_package_core(package))
        if integrity.get("value") != expected:
            return _result("fail", ["content digest does not match exported record and profile metadata"], {"expected": expected, "actual": integrity.get("value")})
        if trusted_digests and expected not in trusted_digests:
            return _result("unavailable", ["content digest matches package but is not in the configured trusted digest set"], {"digest": expected})
        return _result("pass", ["content binding checked; no public issuer identity is established"], {"digest": expected})
    if verification.get("signature_type") in {"none", "unknown", None}:
        return _result("unsupported", ["no supported signature or content-digest integrity method supplied"])
    if verification.get("issuer_key_reference") not in trusted_key_refs:
        return _result("unavailable", ["issuer key reference is not explicitly trusted by recipient policy"])
    return _result("unsupported", ["signature verification profile is not implemented by this reference validator"])


def _evaluate_authority_and_freshness(record: dict[str, Any], status_inputs: dict[str, Any], now: str | None) -> dict[str, Any]:
    reasons: list[str] = []
    authority = record.get("authority", {})
    status = record.get("status", {})
    if authority.get("authority_valid_at_decision") is not True:
        reasons.append("record does not assert authority valid at decision time")
    freshness = status_inputs.get("freshness", status.get("freshness", "unknown"))
    revoked = bool(status_inputs.get("revoked", status.get("revoked")))
    superseded = bool(status_inputs.get("superseded", status.get("superseded")))
    if revoked or freshness == "revoked":
        reasons.append("record or configured status is revoked")
    if superseded or freshness == "superseded":
        reasons.append("record or configured status is superseded")
    if freshness in {"stale", "expired", "pending_revalidation", "unknown"}:
        reasons.append(f"freshness is {freshness}")
    expires_at = parse_time(record.get("consumption_conditions", {}).get("expires_at"))
    now_dt = parse_time(now) if now else None
    if expires_at and now_dt and expires_at < now_dt:
        reasons.append("record consumption window has expired under recipient policy time")
    return _result("fail" if reasons else "pass", reasons, {"freshness": freshness, "configured_status_inputs": status_inputs})


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


def evaluate_recipient_package(package: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    package = deepcopy(package)
    policy = deepcopy(policy)
    if package.get("package_type") != PACKAGE_TYPE:
        return {"schema_validity": _result("not_evaluated", ["unsupported package_type"]), "recipient_reliance_decision": _result("fail", ["unsupported package_type"])}
    record = package.get("record") if isinstance(package.get("record"), dict) else {}
    layers = {
        "schema_validity": _evaluate_schema(record),
        "declared_profile_conformance": _evaluate_profile(package, policy.get("supported_profiles", [PROFILE_ID])),
        "integrity_authentication_checks": _evaluate_integrity(package, policy.get("trusted_digests", []), policy.get("trusted_key_refs", [])),
        "authority_status_and_freshness": _evaluate_authority_and_freshness(record, policy.get("status_inputs", {}), policy.get("now")),
        "consumption_conditions": _evaluate_consumption(record, policy.get("relying_party"), policy.get("purpose")),
    }
    failed = [name for name, layer in layers.items() if layer["status"] not in {"pass"}]
    if failed:
        reliance = _result("fail", ["recipient policy does not permit reliance because layer did not pass: " + ", ".join(failed)])
    else:
        reliance = _result("pass", ["recipient policy permits reliance on the record as exported; this is not independent institutional review and does not prove the underlying decision correct"])
    layers["recipient_reliance_decision"] = reliance
    layers["boundary_notes"] = [
        "Schema validity is structural only.",
        "Content digests bind record content but do not establish public issuer identity.",
        "BitRep signature verification and Index inclusion, if supplied separately, do not create institutional authority.",
        "Historical admission, present validity, and proven signing time are separate evaluations.",
        "The recipient validator does not access producer databases or execute workflows.",
    ]
    return layers
