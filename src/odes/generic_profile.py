"""Generic recipient profile: a package profile that is not tied to the Cognous export profiles.

Profile identifier ``odes_generic_recipient_0_1``, version ``odes-generic-recipient-0.1.0-draft``. A package under this profile is the
ordinary package envelope (record, profile, integrity, provenance, package_digest) with a closed provenance: ``limits``,
``unsupported_semantics``, ``restriction_semantics`` (required) and ``native_evidence_inventory`` (optional). It carries no Cognous
retained sources, so the Cognous Replay reconstruction check does not apply, is never run and is never reported as passed. Recipient checks
are schema, declared profile, content integrity, authentication, authority and status, consumption conditions (with the explicit restriction
semantics) and, when present, the native evidence inventory.

This module only builds packages. Evaluation is ``recipient_validator.evaluate_recipient_package``.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .canonicalization import digest_for
from .common import (
    CANONICALIZATION_PROFILE,
    PACKAGE_TYPE,
    PACKAGE_VERSION,
    RESTRICTION_UNKNOWN_LIMIT,
    RESTRICTION_SEMANTICS_VERSION,
    SCHEMA_NAME,
    SCHEMA_VERSION,
)

GENERIC_PROFILE_ID = "odes_generic_recipient_0_1"
GENERIC_PROFILE_VERSION = "odes-generic-recipient-0.1.0-draft"
GENERIC_REQUIRED_PROVENANCE = ("limits", "unsupported_semantics", "restriction_semantics")
GENERIC_OPTIONAL_PROVENANCE = ("native_evidence_inventory",)
GENERIC_PROVENANCE_MEMBERS = frozenset(GENERIC_REQUIRED_PROVENANCE + GENERIC_OPTIONAL_PROVENANCE)
_FLAG_STATES = frozenset({"explicit_true", "explicit_false", "unknown"})


def build_generic_package(record: Mapping[str, Any], *, created_by: str, created_at: str, restrictions: Mapping[str, Any],
                          limits: list[str] | None = None, unsupported_semantics: list[str] | None = None,
                          native_evidence_inventory: Mapping[str, Any] | None = None,
                          canonicalization: str = CANONICALIZATION_PROFILE) -> dict[str, Any]:
    """A generic-profile package over ``record``.

    ``restrictions`` states each restriction value explicitly: ``restricted_use_flag`` and ``prohibited_use_flag`` (``explicit_true``,
    ``explicit_false`` or ``unknown``), ``jurisdiction`` (``{"state": "explicit", "value": <text>}`` or ``{"state": "unknown"}``) and, when
    any flag is ``explicit_false``, ``source`` (``record_id`` and ``record_hash`` of the retained source). An unknown value is recorded as the
    conservative base boolean ``true`` and the mandatory limitation text is added to ``limits``; it is never exported as ``false``. An
    explicit ``false`` without a source is refused.
    """
    record = deepcopy(dict(record))
    states: dict[str, Any] = {"semantics_version": RESTRICTION_SEMANTICS_VERSION}
    risk = record.setdefault("risk_coordinates", {})
    any_unknown = False
    explicit_false = False
    for name in ("restricted_use_flag", "prohibited_use_flag"):
        state = restrictions.get(name)
        if state not in _FLAG_STATES:
            raise ValueError(f"restrictions.{name} must be one of {sorted(_FLAG_STATES)}")
        states[name] = {"state": state}
        risk[name] = state != "explicit_false"
        any_unknown = any_unknown or state == "unknown"
        explicit_false = explicit_false or state == "explicit_false"
    jurisdiction = restrictions.get("jurisdiction")
    if not isinstance(jurisdiction, Mapping) or jurisdiction.get("state") not in {"explicit", "unknown"}:
        raise ValueError("restrictions.jurisdiction must have state explicit or unknown")
    if jurisdiction["state"] == "explicit":
        if not isinstance(jurisdiction.get("value"), str) or not jurisdiction["value"] or jurisdiction["value"] == "unknown":
            raise ValueError("an explicit jurisdiction needs a non-empty value other than 'unknown'")
        risk["jurisdiction"] = jurisdiction["value"]
        states["jurisdiction"] = {"state": "explicit"}
    else:
        risk["jurisdiction"] = "unknown"
        states["jurisdiction"] = {"state": "unknown"}
        any_unknown = True
    if explicit_false:
        source = restrictions.get("source")
        if not (isinstance(source, Mapping) and source.get("record_id") and source.get("record_hash")):
            raise ValueError("an explicit false restriction value must be attributable to a retained source record")
        states["source"] = {key: source[key] for key in ("record_id", "record_hash")}
    limits = list(limits or [])
    if any_unknown and RESTRICTION_UNKNOWN_LIMIT not in limits:
        limits.append(RESTRICTION_UNKNOWN_LIMIT)

    verification = record.setdefault("verification", {})
    verification["conformance_profile"] = GENERIC_PROFILE_ID
    provenance: dict[str, Any] = {"limits": limits, "unsupported_semantics": list(unsupported_semantics or []), "restriction_semantics": states}
    if native_evidence_inventory is not None:
        provenance["native_evidence_inventory"] = deepcopy(dict(native_evidence_inventory))
    profile = {"implementation_profile": GENERIC_PROFILE_ID, "implementation_profile_version": GENERIC_PROFILE_VERSION,
               "schema_name": SCHEMA_NAME, "schema_version": SCHEMA_VERSION}
    integrity: dict[str, Any] = {"kind": "content-digest", "algorithm": "SHA-256", "canonicalization_profile": canonicalization,
                                 "verification_claim": "Binds the exported ODES record and profile metadata only; does not establish issuer identity or institutional authority."}
    integrity["value"] = digest_for(canonicalization, {"record": record, "profile": profile})
    package = {"package_type": PACKAGE_TYPE, "package_version": PACKAGE_VERSION, "created_by": created_by, "created_at": created_at,
               "record": record, "profile": profile, "integrity": integrity, "provenance": provenance}
    package["package_digest"] = digest_for(canonicalization, {key: package[key] for key in ("record", "profile", "integrity", "provenance")})
    return package
