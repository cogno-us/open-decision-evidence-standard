from __future__ import annotations

import multiprocessing
from copy import deepcopy
from datetime import datetime
from typing import Any

from .common import (
    BUDGET_EXCEEDED,
    BudgetExceeded,
    check_budget,
    CANONICALIZATION_PROFILE,
    PACKAGE_TYPE,
    PACKAGE_VERSION,
    PROFILE_ID,
    PROFILE_V2_ID,
    PROFILE_V2_RESTRICTIONS_ID,
    RESTRICTION_SEMANTICS_VERSION,
    RESTRICTION_UNKNOWN_LIMIT,
    RESTRICTION_VERSION_SUFFIX,
    PROFILE_V2_VERSION,
    REFUSAL_PROFILE_VERSION,
    SECURITY_RUNTIME_GENERATIONS,
    REFUSAL_REVISIONS,
    MERGED_PROFILE_VERSION,
    MERGED_REVISIONS,
    ALL_V2_CONTROL_PLANE_REVISIONS,
    PROFILE_VERSION,
    SCHEMA_NAME,
    SCHEMA_VERSION,
    SUPPORTED_V2_CONTROL_PLANE_REVISIONS,
    SUPPORTED_V2_REPLAY_REVISIONS,
    instant_problem,
    parse_instant,
    window_expired,
)
from .canonicalization import SUPPORTED_CANONICALIZATION_PROFILES, digest_for
from .evidence_inventory import evaluate_native_evidence_inventory
from .generic_profile import GENERIC_PROFILE_ID, GENERIC_PROFILE_VERSION, GENERIC_PROVENANCE_MEMBERS, GENERIC_REQUIRED_PROVENANCE
from .schema_validation import schema_errors


PACKAGE_TOP_LEVEL_MEMBERS = frozenset({"package_type", "package_version", "created_by", "created_at", "record", "profile", "integrity",
                                       "provenance", "package_digest"})


SEMANTIC_DEADLINE_SECONDS = 5
V2_FAMILY = frozenset({PROFILE_V2_ID, PROFILE_V2_RESTRICTIONS_ID})
_RESTRICTION_STATES = frozenset({"explicit_true", "explicit_false", "unknown"})


class DeadlineExceeded(Exception):
    """The semantic worker did not finish within the deadline and was terminated."""


class WorkerFailed(Exception):
    """The semantic worker raised or exited without a result."""


def _worker(fn, conn) -> None:
    try:
        conn.send(("ok", fn()))
    except BaseException as exc:  # reported to the parent as a failure; the worker never raises into the caller
        try:
            conn.send(("error", f"{type(exc).__name__}: {exc}"))
        except Exception:
            pass
    finally:
        conn.close()


def _run_with_deadline(fn, seconds: float):
    """Run ``fn`` in a forked worker and return its (picklable) result, or raise ``DeadlineExceeded`` after terminating the worker.

    The parent holds no state the worker could corrupt and the worker is killed on timeout, which an in-process call cannot guarantee.
    Memory and CPU containment beyond the deadline is a process-level matter (see docs/recipient-validation.md).
    """
    context = multiprocessing.get_context("fork")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(fn, child), daemon=True)
    process.start()
    child.close()
    try:
        if not parent.poll(seconds):
            raise DeadlineExceeded(f"semantic validation exceeded {seconds} seconds")
        try:
            kind, payload = parent.recv()
        except EOFError as exc:
            raise WorkerFailed("semantic worker exited without a result") from exc
    finally:
        if process.is_alive():
            process.kill()
        process.join(5)
        parent.close()
    if kind != "ok":
        raise WorkerFailed(payload)
    return payload


def _budget_result(exc: BudgetExceeded, which: str) -> dict[str, Any]:
    reason = f"{which} {BUDGET_EXCEEDED}: {exc}"
    return {"schema_validity": _result("not_evaluated", [reason], {"reason_code": BUDGET_EXCEEDED, "input": which, "dimension": exc.dimension}),
            "recipient_reliance_decision": _result("fail", [reason], {"reason_code": BUDGET_EXCEEDED, "input": which, "dimension": exc.dimension})}


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
    problem = instant_problem(value)
    if problem == "unavailable":
        return None, [f"{label} is unavailable"]
    if problem == "naive":
        return None, [f"{label} must include a timezone"]
    if problem == "malformed":
        return None, [f"{label} is malformed"]
    return parse_instant(value), []


def _evaluate_schema(record: dict[str, Any]) -> dict[str, Any]:
    errors = schema_errors(record)
    if errors:
        return _result("fail", errors)
    return _result("pass")


def _evaluate_profile(package: dict[str, Any], supported_profiles: list[str]) -> dict[str, Any]:
    reasons: list[str] = []
    profile = package.get("profile") if isinstance(package.get("profile"), dict) else {}
    record = package.get("record") if isinstance(package.get("record"), dict) else {}
    verification = record.get("verification") if isinstance(record.get("verification"), dict) else {}
    declared = profile.get("implementation_profile") or verification.get("conformance_profile")
    if package.get("package_version") != PACKAGE_VERSION:
        return _result("unsupported", [f"unsupported package_version {package.get('package_version')!r}"], {"supported_package_version": PACKAGE_VERSION})
    if declared not in supported_profiles:
        return _result("unsupported", [f"unsupported declared profile {declared!r}"], {"declared_profile": declared, "supported_profiles": supported_profiles})
    if declared != verification.get("conformance_profile"):
        reasons.append("package profile and record verification.conformance_profile differ")
    provenance = package.get("provenance") if isinstance(package.get("provenance"), dict) else {}
    pinned = provenance.get("pinned_revisions")
    if "pinned_revisions" in provenance and not isinstance(pinned, dict):
        reasons.append("provenance.pinned_revisions must be an object")
    selected_control_plane = pinned.get("control_plane") if isinstance(pinned, dict) else None
    if not isinstance(selected_control_plane, str):
        if selected_control_plane is not None:
            reasons.append("provenance.pinned_revisions.control_plane must be a string")
        selected_control_plane = None
    if declared == PROFILE_ID and selected_control_plane in ALL_V2_CONTROL_PLANE_REVISIONS:
        reasons.append("repaired producer transformation cannot be relabeled as historical profile 0.1")
    if declared in {PROFILE_ID, PROFILE_V2_ID, PROFILE_V2_RESTRICTIONS_ID}:
        v2 = declared in V2_FAMILY
        integrity = package.get("integrity") if isinstance(package.get("integrity"), dict) else {}
        if "canonicalization_profile" in integrity and integrity["canonicalization_profile"] != CANONICALIZATION_PROFILE:
            reasons.append("the declared implementation profile is defined only with the legacy canonicalization profile")
        expected_version = SECURITY_RUNTIME_GENERATIONS[selected_control_plane][0] if v2 and selected_control_plane in SECURITY_RUNTIME_GENERATIONS else REFUSAL_PROFILE_VERSION if v2 and selected_control_plane == REFUSAL_REVISIONS["control_plane"] else MERGED_PROFILE_VERSION if v2 and selected_control_plane == MERGED_REVISIONS["control_plane"] else PROFILE_V2_VERSION if v2 else PROFILE_VERSION
        if declared == PROFILE_V2_RESTRICTIONS_ID:
            expected_version += RESTRICTION_VERSION_SUFFIX
        if profile.get("implementation_profile_version") != expected_version:
            return _result("unsupported", [f"unsupported implementation_profile_version {profile.get('implementation_profile_version')!r}"], {"supported_profile_version": expected_version})
        if profile.get("schema_name") != SCHEMA_NAME or profile.get("schema_version") != SCHEMA_VERSION:
            reasons.append("profile schema coordinates do not match pder-v0.1")
        if not isinstance(package.get("provenance"), dict):
            reasons.append("Cognous-stack profile requires package provenance outside the pder-v0.1 base record")
    evidence: dict[str, Any] = {"declared_profile": declared, "implementation_profile_version": profile.get("implementation_profile_version")}
    if declared == GENERIC_PROFILE_ID:
        if profile.get("implementation_profile_version") != GENERIC_PROFILE_VERSION:
            return _result("unsupported", [f"unsupported implementation_profile_version {profile.get('implementation_profile_version')!r}"], {"supported_profile_version": GENERIC_PROFILE_VERSION})
        if profile.get("schema_name") != SCHEMA_NAME or profile.get("schema_version") != SCHEMA_VERSION:
            reasons.append("profile schema coordinates do not match pder-v0.1")
        if not isinstance(package.get("provenance"), dict):
            reasons.append("generic profile requires package provenance outside the pder-v0.1 base record")
        else:
            for key in package["provenance"]:
                if key not in GENERIC_PROVENANCE_MEMBERS:
                    reasons.append(f"provenance member {key!r} is not defined by the generic recipient profile")
        # The profile carries no Cognous retained sources: the Replay reconstruction check does not apply and is never reported as passed.
        evidence["cognous_replay_reconstruction"] = "not_applicable"
    return _result("fail" if reasons else "pass", reasons, evidence)


def _evaluate_package_content_integrity(package: dict[str, Any], trusted_digests: list[str]) -> dict[str, Any]:
    reasons: list[str] = []
    evidence: dict[str, Any] = {}
    integrity = package.get("integrity") if isinstance(package.get("integrity"), dict) else {}
    provenance = package.get("provenance") if isinstance(package.get("provenance"), dict) else {}

    if integrity.get("kind") != "content-digest":
        return _result("unsupported", ["no supported package content integrity method supplied"])
    if integrity.get("algorithm") != "SHA-256":
        return _result("unsupported", [f"unsupported integrity algorithm {integrity.get('algorithm')!r}"])
    canonicalization = integrity.get("canonicalization_profile")
    if not isinstance(canonicalization, str) or canonicalization not in SUPPORTED_CANONICALIZATION_PROFILES:
        return _result("unsupported", [f"unsupported canonicalization_profile {canonicalization!r}"], {"supported_canonicalization_profile": CANONICALIZATION_PROFILE, "supported_canonicalization_profiles": list(SUPPORTED_CANONICALIZATION_PROFILES)})

    try:
        record_profile_digest = digest_for(canonicalization, _package_core(package))
        expected_package_digest = digest_for(canonicalization, _material_package_content(package))
    except ValueError as exc:
        return _result("fail", [f"package content cannot be canonicalized under {canonicalization!r}: {exc}"])
    if integrity.get("value") != record_profile_digest:
        reasons.append("record/profile content digest does not match exported record and profile metadata")
    evidence["record_profile_digest"] = record_profile_digest

    if package.get("package_digest") != expected_package_digest:
        reasons.append("package_digest does not match complete material package content")
    evidence["package_digest"] = expected_package_digest
    evidence["configured_trusted_digests"] = trusted_digests

    # Top-level members (decision 39-M). The digest above covers record, profile, integrity and provenance. The rest must be
    # exactly the declared envelope: an extra member is refused (nothing binds it), and the four envelope members must be present
    # and well formed. created_by and created_at are not covered by this digest in packages already exported (they are retained
    # evidence); a recipient that needs them bound needs a digest that covers them.
    for key in package:
        if key not in PACKAGE_TOP_LEVEL_MEMBERS:
            reasons.append(f"package top-level member {key!r} is not covered by the package digest and is not part of the package format")
    if package.get("package_type") != PACKAGE_TYPE:
        reasons.append("package_type is not the declared package type")
    if package.get("package_version") != PACKAGE_VERSION:
        reasons.append("package_version is not the declared package version")
    if not isinstance(package.get("created_by"), str) or not package.get("created_by"):
        reasons.append("created_by must be a non-empty string")
    if parse_instant(package.get("created_at")) is None:
        reasons.append("created_at must be an RFC 3339 instant with an offset")
    generic = (package.get("profile") if isinstance(package.get("profile"), dict) else {}).get("implementation_profile") == GENERIC_PROFILE_ID
    required_provenance = list(GENERIC_REQUIRED_PROVENANCE) if generic else ["source_artifacts", "source_record_refs", "decision_facts", "execution_facts", "redaction", "unsupported_semantics", "limits"]
    for key in required_provenance:
        if key not in provenance:
            reasons.append(f"provenance.{key} is unavailable")
    if not generic and not isinstance(provenance.get("source_record_refs"), list):
        reasons.append("provenance.source_record_refs must be available as an array")
    if not generic and not isinstance(provenance.get("execution_facts"), dict):
        reasons.append("provenance.execution_facts must be available as an object")
    if not isinstance(provenance.get("unsupported_semantics"), list) or not isinstance(provenance.get("limits"), list):
        reasons.append("limitations and unsupported semantics must survive export")

    if reasons:
        return _result("fail", reasons, evidence)
    # Only package_digest anchors the complete-package pass: integrity.value (the record/profile digest) does not cover provenance
    # (limits, unsupported_semantics, restriction_semantics), so a trusted record/profile digest is not an anchor (decision 45).
    if trusted_digests and expected_package_digest not in trusted_digests:
        note = ("content digest matches package but is not in the configured trusted digest set"
                if record_profile_digest not in trusted_digests else
                "the configured trusted digest is the record/profile digest, which does not cover provenance (limits, unsupported semantics, "
                "restriction semantics); only package_digest anchors the complete package, so this is not accepted as an anchor")
        return _result("unavailable", [note], evidence)
    return _result("pass", ["complete material package content is bound by digest; this does not authenticate an issuer"], evidence)


def _evaluate_authentication(package: dict[str, Any], trusted_key_refs: list[str], trusted_digests: list[str], detached: Any = None) -> dict[str, Any]:
    if detached is not None:
        # Optional detached signature section (recipient-owned keys). A failure here is reported as is; it never falls back to a weaker path.
        from .signatures import evaluate_detached_authentication
        return evaluate_detached_authentication(package, detached)
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
    issuer = record.get("issuer")
    if (not isinstance(issuer, dict) or not issuer.get("organization_id") or not issuer.get("system_id")
            or status_inputs.get("issuer") != issuer or policy.get("trusted_issuer") != issuer):
        reasons.append("status evidence and recipient trust must bind the exact issuer organization and system")
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

    conditions = record.get("consumption_conditions") if isinstance(record.get("consumption_conditions"), dict) else {}
    expires_at, expiry_errors = _parse_time_result(conditions.get("expires_at"), "record consumption expiry")
    if expiry_errors:
        reasons.extend(expiry_errors)
    expired = bool(expires_at and now_dt and window_expired(now_dt, expires_at))
    if expired:
        reasons.append("record consumption window has expired under recipient policy time")

    if not isinstance(status_inputs, dict) or not status_inputs:
        reasons.append("external status evidence is required for present authority/freshness acceptance")
        # A window that has definitively passed is a failure whether or not status evidence was supplied; only the absence of other evidence is unavailable.
        return _result("fail" if expired else "unavailable", reasons, {**evidence, "record_reported_freshness": status.get("freshness")})

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


def _restriction_semantics_reasons(package: dict[str, Any]) -> list[str]:
    """Checks for the explicit restriction profile. Unknown is never unrestricted; an explicit false must be attributable."""
    record = package.get("record") if isinstance(package.get("record"), dict) else {}
    provenance = package.get("provenance") if isinstance(package.get("provenance"), dict) else {}
    risk = record.get("risk_coordinates") if isinstance(record.get("risk_coordinates"), dict) else {}
    semantics = provenance.get("restriction_semantics")
    if not isinstance(semantics, dict) or semantics.get("semantics_version") != RESTRICTION_SEMANTICS_VERSION:
        return ["provenance.restriction_semantics is missing or unsupported; the restriction state is not established"]
    reasons: list[str] = []
    unknown = False
    explicit_false = False
    for name in ("restricted_use_flag", "prohibited_use_flag"):
        entry = semantics.get(name)
        state = entry.get("state") if isinstance(entry, dict) else None
        if state not in _RESTRICTION_STATES:
            reasons.append(f"restriction_semantics.{name} has no supported state")
            continue
        expected = state != "explicit_false"
        if risk.get(name) is not expected:
            reasons.append(f"record {name} does not match restriction_semantics state {state}")
        unknown = unknown or state == "unknown"
        explicit_false = explicit_false or state == "explicit_false"
    jurisdiction = semantics.get("jurisdiction")
    jurisdiction_state = jurisdiction.get("state") if isinstance(jurisdiction, dict) else None
    if jurisdiction_state not in {"explicit", "unknown"}:
        reasons.append("restriction_semantics.jurisdiction has no supported state")
    elif jurisdiction_state == "unknown" or risk.get("jurisdiction") == "unknown":
        unknown = True
        reasons.append("record jurisdiction is unknown and never matches a recipient jurisdiction")
    source = semantics.get("source")
    if explicit_false and not (isinstance(source, dict) and source.get("record_id") and source.get("record_hash")):
        reasons.append("an explicit false restriction value is not attributable to a retained source record")
    if unknown:
        reasons.append("restriction is unknown: the source does not establish the restriction state, so reliance is blocked (this is not an established prohibition)")
        if RESTRICTION_UNKNOWN_LIMIT not in (provenance.get("limits") if isinstance(provenance.get("limits"), list) else []):
            reasons.append("the mandatory limitation for unknown restriction values is missing")
    return reasons


def _evaluate_consumption(record: dict[str, Any], relying_party: str | None, purpose: str | None, policy: dict[str, Any] | None = None, package: dict[str, Any] | None = None) -> dict[str, Any]:
    conditions = record.get("consumption_conditions", {})
    reasons: list[str] = []
    if not isinstance(conditions, dict):
        return _result("fail", ["record consumption_conditions must be an object"])
    parties = conditions.get("permitted_relying_parties") if isinstance(conditions.get("permitted_relying_parties"), list) else []
    purposes = conditions.get("permitted_purposes") if isinstance(conditions.get("permitted_purposes"), list) else []
    if not parties or not all(isinstance(x, str) and x for x in parties):
        # An absent, empty or malformed list names no recipient; it never means "any recipient" (decision 39-N).
        reasons.append("record names no permitted relying party; an absent or empty list admits no recipient")
    elif relying_party and relying_party not in parties:
        reasons.append("recipient relying party is not permitted")
    elif not relying_party:
        reasons.append("recipient relying party is decision-critical but unavailable")
    if purpose and purpose not in purposes:
        reasons.append("recipient purpose is not permitted")
    if not purpose:
        reasons.append("recipient purpose is decision-critical but unavailable")
    risk = record.get("risk_coordinates", {})
    policy = policy or {}
    if not isinstance(risk, dict) or risk.get("prohibited_use_flag") is not False:
        reasons.append("prohibited or unavailable use restriction")
    if isinstance(risk, dict):
        if risk.get("restricted_use_flag") is not False:
            reasons.append("restricted use has no implemented recipient authorization profile")
        if not policy.get("jurisdiction") or policy.get("jurisdiction") != risk.get("jurisdiction"):
            reasons.append("recipient jurisdiction is unavailable or differs from the record")
    if package is not None and (package.get("profile") or {}).get("implementation_profile") in {PROFILE_V2_RESTRICTIONS_ID, GENERIC_PROFILE_ID}:
        reasons.extend(_restriction_semantics_reasons(package))
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
    if lreplay in SUPPORTED_V2_REPLAY_REVISIONS and lprov["pinned_revisions"].get("control_plane") == MERGED_REVISIONS["control_plane"]:
        raise ValueError("historical Replay revision does not support merged producers")
    if lprov.get("pinned_revisions", {}).get("control_plane") == REFUSAL_REVISIONS["control_plane"] and lreplay != REFUSAL_REVISIONS["replay"]:
        raise ValueError("refusal profile requires exact qualified Replay revision")
    selected_cp = lprov.get("pinned_revisions", {}).get("control_plane")
    if selected_cp in SECURITY_RUNTIME_GENERATIONS and lreplay != SECURITY_RUNTIME_GENERATIONS[selected_cp][1]["replay"]:
        raise ValueError("security-runtime profile requires exact qualified Replay revision")
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
    profile = package.get("profile") if isinstance(package.get("profile"), dict) else {}
    if profile.get("implementation_profile") not in V2_FAMILY:
        return _result("not_applicable", ["historical profile validation unchanged"])
    try:
        return _run_with_deadline(lambda: _replay_semantic_check(package), SEMANTIC_DEADLINE_SECONDS)
    except DeadlineExceeded as exc:
        return _result("fail", [f"Replay semantic validation did not finish: {exc}"], {"reason_code": BUDGET_EXCEEDED, "dimension": "semantic_deadline"})
    except (WorkerFailed, ValueError, OSError) as exc:
        return _result("fail", [f"Replay semantic validation worker failed: {exc}"])


def _replay_semantic_check(package: dict[str, Any]) -> dict[str, Any]:
    from .exporter import ReplayDependencyError, ReplayRevisionUnsupportedError, export_cognous_stack_package
    try:
        sources = package["provenance"]["retained_sources"]
        conditions = package["record"]["consumption_conditions"]
        parties, purposes = conditions["permitted_relying_parties"], conditions["permitted_purposes"]
        if len(parties) != 1 or len(purposes) != 1:
            raise ValueError("implementation profile requires exact single-recipient/purpose export")
        mode = "explicit" if package["profile"]["implementation_profile"] == PROFILE_V2_RESTRICTIONS_ID else "legacy"
        expected = export_cognous_stack_package(sources["manifest"], sources["reconstruction_bundle"],
            relying_party=parties[0], purpose=purposes[0], expires_at=conditions["expires_at"], restriction_semantics=mode)
        actual_material, expected_material = _normalized_replay_material(package, expected)
        if actual_material != expected_material:
            raise ValueError("package semantics differ from accepted Replay-derived transformation")
    except ReplayDependencyError as exc:
        # The check could not run (Replay absent, or its revision cannot be determined). Not a contradiction in the package; still not a pass.
        return _result("unavailable", [f"Replay semantic validation unavailable: {exc}"])
    except ReplayRevisionUnsupportedError as exc:
        return _result("unsupported", [f"Replay semantic validation unsupported: {exc}"])
    except Exception as exc:
        return _result("fail", [f"Replay semantic validation failed: {exc}"])
    return _result("pass", ["retained content matches accepted Replay validation; no source authentication or authority renewal"])


def _evaluate_recipient_package(package: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(package, dict) or not isinstance(policy, dict):
        reason = "package and recipient policy must be JSON objects"
        return {"schema_validity": _result("not_evaluated", [reason]), "recipient_reliance_decision": _result("fail", [reason])}
    # Budgets come before any copy or traversal.
    for which, value in (("package", package), ("policy", policy)):
        try:
            check_budget(value)
        except BudgetExceeded as exc:
            return _budget_result(exc, which)
    package = deepcopy(package)
    policy = deepcopy(policy)
    if package.get("package_type") != PACKAGE_TYPE:
        return {"schema_validity": _result("not_evaluated", ["unsupported package_type"]), "recipient_reliance_decision": _result("fail", ["unsupported package_type"])}
    record = package.get("record") if isinstance(package.get("record"), dict) else {}
    trusted_digests = policy.get("trusted_digests", []) or policy.get("trusted_package_digests", []) or []
    status_inputs = policy.get("status_inputs", {})
    if not isinstance(status_inputs, dict):
        reason = "recipient policy status_inputs must be an object"
        return {"schema_validity": _result("not_evaluated", [reason]), "recipient_reliance_decision": _result("fail", [reason])}
    profile = package.get("profile") if isinstance(package.get("profile"), dict) else {}
    declared = profile.get("implementation_profile")
    verification = record.get("verification") if isinstance(record.get("verification"), dict) else {}
    record_declared = verification.get("conformance_profile")
    profile_consistent = bool(declared) and declared == record_declared
    layers = {
        "schema_validity": _evaluate_schema(record),
        **({"replay_semantic_consistency": _evaluate_replay_semantics(package)}
           if declared in V2_FAMILY or record_declared in V2_FAMILY else {}),
        "declared_profile_conformance": _evaluate_profile(package, policy.get("supported_profiles", [PROFILE_ID])),
        "package_content_integrity": _evaluate_package_content_integrity(package, trusted_digests),
        "integrity_authentication_checks": _evaluate_authentication(package, policy.get("trusted_key_refs", []), trusted_digests, policy.get("detached_authentication")),
        "historical_authority_assertions": _evaluate_historical_authority(record, status_inputs, policy),
        "authority_status_and_freshness": _evaluate_authority_and_freshness(record, status_inputs, policy.get("now"), policy),
        "consumption_conditions": _evaluate_consumption(record, policy.get("relying_party"), policy.get("purpose"), policy, package),
    }
    provenance_members = package.get("provenance") if isinstance(package.get("provenance"), dict) else {}
    if "native_evidence_inventory" in provenance_members or "native_evidence" in policy:
        layers["native_evidence_inventory"] = evaluate_native_evidence_inventory(provenance_members.get("native_evidence_inventory"), policy)
    if not profile_consistent:
        layers["declared_profile_conformance"] = _result("fail", ["explicit matching package and record profile declarations required"])
    failed = [name for name, layer in layers.items() if layer["status"] not in {"pass"}]
    auth_unavailable_only = failed == ["integrity_authentication_checks"]
    if not failed:
        reliance = _result("pass", ["recipient policy permits reliance on the record as exported; this is not independent institutional review and does not prove the underlying decision correct"])
    elif policy.get("allow_unauthenticated_informational_inspection") is True and auth_unavailable_only:
        reliance = _result("informational_only", ["content integrity passed, but issuer authentication is unavailable; policy permits informational inspection only, not reliance or authorization"])
    else:
        reliance = _result("fail", ["recipient policy does not permit reliance because layer did not pass: " + ", ".join(failed)],
                           {"blocking_layers": {name: layers[name]["status"] for name in failed}})
    layers["recipient_reliance_decision"] = reliance
    layers["boundary_notes"] = [
        "Schema validity is structural only.",
        "Package content digests bind material content but do not establish public issuer identity.",
        "Authentication, historical authority, present authority, and recipient reliance are separate evaluations.",
        "BitRep signature verification and Index inclusion, if supplied separately, do not create institutional authority.",
        "The recipient validator does not access producer databases or execute workflows.",
    ]
    if declared == GENERIC_PROFILE_ID:
        layers["boundary_notes"].append("The generic recipient profile carries no Cognous retained sources: no Cognous Replay reconstruction check was run, and a pass is not claimed.")
    return layers


def evaluate_recipient_package(package: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a package against a recipient policy. Malformed nested shapes yield a structured ``fail`` result."""
    try:
        return _evaluate_recipient_package(package, policy)
    except (AttributeError, TypeError, KeyError, IndexError) as exc:
        reason = f"recipient input has a malformed nested shape ({type(exc).__name__})"
        return {"schema_validity": _result("not_evaluated", [reason]), "recipient_reliance_decision": _result("fail", [reason])}
