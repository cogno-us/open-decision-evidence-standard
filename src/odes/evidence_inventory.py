"""Native evidence inventory (separately versioned, package level).

An inventory lists opaque artifacts that were produced by other systems in their own formats (receipts, attestations, records). ODES does
not interpret, normalize or re-serialize them:

* Each entry carries the artifact's exact bytes (base64) or an opaque locator, its byte length, and a digest computed over those original
  bytes with ``hashlib`` directly. No JSON canonicalization is involved, so the digest cannot depend on one.
* Producer assertions about an artifact live in ``producer_assertions`` and are reported as ``not_evaluated``; they never contribute to a
  verdict. Native verification outcomes are recipient-generated reports supplied by the recipient (policy or caller), bound to the
  artifact digest and naming the verifier and the recipient policy. A native verdict is not a decision authority verdict.
* A required artifact that cannot be checked is ``unavailable``. A digest or length mismatch is ``fail``. A digest algorithm this
  implementation does not support is ``unsupported``.
* Nothing is fetched. A locator is never dereferenced: this module does no network access, reads no local files, loads no plugins and
  changes no trust store. Bytes for a locator entry can only be handed in by the recipient (``supplied_artifacts``).
* Entry count, per-artifact size, total declared size, string lengths and the size of producer-assertion objects are bounded, and the
  bounds are checked before any base64 decoding.

The inventory sits at ``provenance.native_evidence_inventory`` of a package, so the package digest binds it.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping

INVENTORY_TYPE = "odes_native_evidence_inventory"
INVENTORY_VERSION = "0.1.0-draft"
DIGEST_ALGORITHMS = ("sha256",)
RELATIONS = frozenset({"decision_evidence", "authority_evidence", "execution_evidence", "status_evidence", "attestation", "supporting_context"})
REPORT_STATUSES = frozenset({"pass", "fail", "unavailable", "unsupported", "not_evaluated"})

BOUNDARY = ("A native verification result concerns the artifact's own format and keys. It is not a decision authority verdict and does not "
            "establish authority, recipient reliance or the truth of the artifact's content.")

_INVENTORY_MEMBERS = frozenset({"inventory_type", "inventory_version", "artifacts"})
_ENTRY_REQUIRED = frozenset({"artifact_id", "source_format", "source_format_version", "relation", "media_type", "byte_length", "digest_algorithm", "digest_value"})
_ENTRY_OPTIONAL = frozenset({"bytes_base64", "locator", "required", "producer_assertions", "limitations", "native_signature_scope", "lineage"})
_REPORT_MEMBERS = frozenset({"artifact_id", "artifact_digest_value", "verifier_id", "verifier_version", "recipient_policy_id", "status"})
_POLICY_MEMBERS = frozenset({"required_artifacts", "required_native_verification", "verification_reports", "supplied_artifacts",
                             "max_artifact_bytes", "max_entries", "max_total_bytes"})
_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_MEDIA_TYPE = re.compile(r"[a-z0-9!#$&^_.+-]{1,63}/[a-z0-9!#$&^_.+-]{1,63}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_STRING_LIMIT = 4096


@dataclass(frozen=True)
class InventoryLimits:
    max_entries: int = 256
    max_artifact_bytes: int = 8 * 1024 * 1024
    max_total_bytes: int = 32 * 1024 * 1024


def _lowered(limits: InventoryLimits, policy: Mapping[str, Any]) -> InventoryLimits:
    """Policy may only tighten the bounds."""
    def pick(name: str) -> int:
        base = getattr(limits, name)
        value = policy.get(name)
        return min(base, value) if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else base
    return InventoryLimits(pick("max_entries"), pick("max_artifact_bytes"), pick("max_total_bytes"))


# ------------------------------------------------------------------------------------------------ building and extracting

def build_inventory_entry(artifact_id: str, *, data: bytes = b"", source_format: str, source_format_version: str, relation: str, media_type: str,
                          embed: bool = True, locator: dict[str, Any] | None = None, required: bool = False,
                          producer_assertions: dict[str, Any] | None = None, limitations: list[str] | None = None,
                          native_signature_scope: str | None = None, lineage: list[str] | None = None,
                          byte_length: int | None = None, digest_value: str | None = None) -> dict[str, Any]:
    """One entry over the exact ``data`` bytes. ``byte_length`` and ``digest_value`` default to the values computed from ``data``."""
    if embed and locator is not None:
        raise ValueError("an entry carries embedded bytes or a locator, not both")
    if not embed and locator is None:
        raise ValueError("an entry without embedded bytes needs a locator")
    entry: dict[str, Any] = {
        "artifact_id": artifact_id, "source_format": source_format, "source_format_version": source_format_version, "relation": relation,
        "media_type": media_type, "byte_length": len(data) if byte_length is None else byte_length, "digest_algorithm": "sha256",
        "digest_value": hashlib.sha256(data).hexdigest() if digest_value is None else digest_value, "required": required,
    }
    if embed:
        entry["bytes_base64"] = base64.b64encode(data).decode("ascii")
    else:
        entry["locator"] = locator
    if producer_assertions is not None:
        entry["producer_assertions"] = producer_assertions
    if limitations is not None:
        entry["limitations"] = limitations
    if native_signature_scope is not None:
        entry["native_signature_scope"] = native_signature_scope
    if lineage is not None:
        entry["lineage"] = lineage
    return entry


def build_inventory(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {"inventory_type": INVENTORY_TYPE, "inventory_version": INVENTORY_VERSION, "artifacts": list(entries)}


def _decode(text: Any, limits: InventoryLimits) -> bytes:
    if not isinstance(text, str) or not text.isascii():
        raise ValueError("embedded bytes must be an ASCII base64 string")
    if len(text) > ((limits.max_artifact_bytes + 2) // 3) * 4:
        raise ValueError("embedded bytes exceed the per-artifact limit")
    try:
        data = base64.b64decode(text, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("embedded bytes are not valid base64") from None
    if base64.b64encode(data).decode("ascii") != text:
        raise ValueError("embedded bytes are not canonical base64")
    return data


def extract_artifact(entry: Mapping[str, Any], limits: InventoryLimits | None = None) -> bytes:
    """The exact embedded bytes of an entry, after checking length and digest. Raises ``ValueError`` otherwise."""
    limits = limits or InventoryLimits()
    if entry.get("digest_algorithm") not in DIGEST_ALGORITHMS:
        raise ValueError("unsupported digest algorithm")
    data = _decode(entry.get("bytes_base64"), limits)
    if len(data) != entry.get("byte_length"):
        raise ValueError("byte length does not match")
    if hashlib.sha256(data).hexdigest() != entry.get("digest_value"):
        raise ValueError("digest does not match")
    return data


# ------------------------------------------------------------------------------------------------ evaluation

def _string(value: Any, limit: int = 256) -> bool:
    return isinstance(value, str) and 0 < len(value) <= limit


def _bounded_json(value: Any, max_depth: int = 8, max_nodes: int = 1000) -> bool:
    stack = [(value, 1)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > max_nodes or depth > max_depth:
            return False
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str) or len(key) > 256:
                    return False
                stack.append((child, depth + 1))
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
        elif isinstance(item, str):
            if len(item) > _STRING_LIMIT:
                return False
        elif item is not None and not isinstance(item, (bool, int, float)):
            return False
    return True


def _structure_problems(entry: Any, limits: InventoryLimits) -> tuple[list[str], str]:
    """Problems with one entry's shape, and the status they imply (``fail`` unless the only problem is an unsupported digest algorithm)."""
    if not isinstance(entry, dict):
        return ["entry must be an object"], "fail"
    problems: list[str] = []
    members = set(entry)
    unknown = sorted(str(m) for m in members - _ENTRY_REQUIRED - _ENTRY_OPTIONAL)
    if unknown:
        problems.append(f"unknown entry members {unknown}")
    missing = sorted(_ENTRY_REQUIRED - members)
    if missing:
        problems.append(f"missing entry members {missing}")
    if ("bytes_base64" in entry) == ("locator" in entry):
        problems.append("exactly one of bytes_base64 and locator is required")
    if problems:
        return problems, "fail"
    if not isinstance(entry["artifact_id"], str) or _ID.fullmatch(entry["artifact_id"]) is None:
        problems.append("artifact_id is malformed")
    if not _string(entry["source_format"], 128) or not _string(entry["source_format_version"], 64):
        problems.append("source_format and source_format_version must be non-empty strings within their limits")
    if entry["relation"] not in RELATIONS:
        problems.append("relation is not a defined relation")
    if not isinstance(entry["media_type"], str) or _MEDIA_TYPE.fullmatch(entry["media_type"]) is None:
        problems.append("media_type is malformed")
    length = entry["byte_length"]
    if not isinstance(length, int) or isinstance(length, bool) or length < 0:
        problems.append("byte_length must be a non-negative integer")
    elif length > limits.max_artifact_bytes:
        problems.append("byte_length exceeds the per-artifact limit")
    if not isinstance(entry["digest_value"], str) or _HEX64.fullmatch(entry["digest_value"]) is None:
        problems.append("digest_value must be 64 lowercase hex digits")
    if "bytes_base64" in entry:
        text = entry["bytes_base64"]
        if not isinstance(text, str) or len(text) > ((limits.max_artifact_bytes + 2) // 3) * 4:
            problems.append("bytes_base64 is malformed or exceeds the per-artifact limit")
    else:
        loc = entry["locator"]
        if (not isinstance(loc, dict) or set(loc) != {"kind", "reference"} or not _string(loc.get("kind"), 64)
                or not _string(loc.get("reference"), 1024)):
            problems.append("locator must be an object with non-empty kind and reference strings")
    if "required" in entry and not isinstance(entry["required"], bool):
        problems.append("required must be a boolean")
    if "producer_assertions" in entry and not (isinstance(entry["producer_assertions"], dict) and _bounded_json(entry["producer_assertions"])):
        problems.append("producer_assertions must be a bounded object")
    if "limitations" in entry:
        lim = entry["limitations"]
        if not isinstance(lim, list) or len(lim) > 64 or not all(_string(x, 1024) for x in lim):
            problems.append("limitations must be a bounded list of strings")
    if "native_signature_scope" in entry and not _string(entry["native_signature_scope"], 1024):
        problems.append("native_signature_scope must be a non-empty string within its limit")
    if "lineage" in entry:
        lin = entry["lineage"]
        if not isinstance(lin, list) or len(lin) > 64 or not all(isinstance(x, str) and _ID.fullmatch(x) for x in lin):
            problems.append("lineage must be a bounded list of artifact ids")
    if problems:
        return problems, "fail"
    if entry["digest_algorithm"] not in DIGEST_ALGORITHMS:
        return [f"unsupported digest algorithm {entry['digest_algorithm']!r}"], "unsupported"
    return [], "pass"


def _report_problems(report: Any) -> list[str]:
    if not isinstance(report, dict):
        return ["verification report must be an object"]
    problems: list[str] = []
    extra = set(report) - _REPORT_MEMBERS - {"reasons"}
    missing = _REPORT_MEMBERS - set(report)
    if extra:
        problems.append(f"unknown report members {sorted(str(m) for m in extra)}")
    if missing:
        problems.append(f"missing report members {sorted(missing)}")
    if problems:
        return problems
    if not _ID.fullmatch(report["artifact_id"]) if isinstance(report["artifact_id"], str) else True:
        problems.append("report artifact_id is malformed")
    if not isinstance(report["artifact_digest_value"], str) or _HEX64.fullmatch(report["artifact_digest_value"]) is None:
        problems.append("report artifact_digest_value is malformed")
    for name in ("verifier_id", "verifier_version", "recipient_policy_id"):
        if not _string(report[name]):
            problems.append(f"report {name} must be a non-empty string")
    if not isinstance(report["status"], str) or report["status"] not in REPORT_STATUSES:
        problems.append("report status is not a defined status")
    if "reasons" in report and not (isinstance(report["reasons"], list) and len(report["reasons"]) <= 64 and all(_string(x, 1024) for x in report["reasons"])):
        problems.append("report reasons must be a bounded list of strings")
    return problems


def _result(status: str, reasons: list[str], evidence: dict[str, Any]) -> dict[str, Any]:
    return {"status": status, "reasons": reasons, "evidence": evidence}


def evaluate_native_evidence_inventory(inventory: Any, policy: Mapping[str, Any] | None = None,
                                       supplied_artifacts: Mapping[str, bytes] | None = None,
                                       limits: InventoryLimits | None = None) -> dict[str, Any]:
    """Layer result for an inventory under a recipient policy (``policy["native_evidence"]``). Never raises on malformed input."""
    evidence: dict[str, Any] = {"boundary": BOUNDARY, "artifacts": {}, "unavailable_optional": []}
    reasons: list[str] = []
    cfg_raw = policy.get("native_evidence") if isinstance(policy, Mapping) else None
    cfg: dict[str, Any] = {}
    if cfg_raw is not None:
        if not isinstance(cfg_raw, dict) or set(cfg_raw) - _POLICY_MEMBERS:
            return _result("fail", ["recipient policy native_evidence is malformed or has unknown members"], evidence)
        cfg = cfg_raw
    limits = _lowered(limits or InventoryLimits(), cfg)

    required_artifacts: dict[str, Any] = {}
    for item in cfg.get("required_artifacts", []) if isinstance(cfg.get("required_artifacts", []), list) else [None]:
        if (not isinstance(item, dict) or set(item) != {"artifact_id", "relation"} or not isinstance(item["artifact_id"], str)
                or item["relation"] not in RELATIONS):
            return _result("fail", ["recipient policy required_artifacts is malformed"], evidence)
        required_artifacts[item["artifact_id"]] = item["relation"]
    native_required = cfg.get("required_native_verification", [])
    if not isinstance(native_required, list) or not all(isinstance(x, str) for x in native_required):
        return _result("fail", ["recipient policy required_native_verification is malformed"], evidence)
    reports_in = cfg.get("verification_reports", [])
    if not isinstance(reports_in, list):
        return _result("fail", ["recipient policy verification_reports is malformed"], evidence)
    policy_supplied = cfg.get("supplied_artifacts", {})
    if not isinstance(policy_supplied, dict) or not all(isinstance(k, str) for k in policy_supplied):
        return _result("fail", ["recipient policy supplied_artifacts is malformed"], evidence)
    has_requirement = bool(required_artifacts or native_required)

    if inventory is None:
        return _result("unavailable", ["no native evidence inventory supplied"], evidence)
    if not isinstance(inventory, dict):
        return _result("fail", ["inventory must be an object"], evidence)
    missing = _INVENTORY_MEMBERS - set(inventory)
    extra = set(inventory) - _INVENTORY_MEMBERS
    if missing or extra:
        return _result("fail", [f"inventory members are not the declared set (missing {sorted(missing)}, unknown {sorted(str(e) for e in extra)})"], evidence)
    if inventory["inventory_type"] != INVENTORY_TYPE:
        return _result("fail", ["inventory_type is not the declared inventory type"], evidence)
    if inventory["inventory_version"] != INVENTORY_VERSION:
        return _result("unsupported", [f"unsupported inventory_version {inventory['inventory_version']!r}"], evidence)
    entries = inventory["artifacts"]
    if not isinstance(entries, list):
        return _result("fail", ["inventory artifacts must be a list"], evidence)
    if len(entries) > limits.max_entries:
        return _result("fail", ["inventory has more entries than the limit allows"], evidence)

    # Pass 1: shape, duplicate ids and every size bound, before any decoding.
    problems_by_index: list[tuple[list[str], str]] = []
    seen: dict[str, int] = {}
    duplicates: list[str] = []
    total = 0
    for index, entry in enumerate(entries):
        problems_by_index.append(_structure_problems(entry, limits))
        if isinstance(entry, dict):
            aid = entry.get("artifact_id")
            if isinstance(aid, str):
                if aid in seen:
                    duplicates.append(aid)
                seen[aid] = index
            length = entry.get("byte_length")
            if isinstance(length, int) and not isinstance(length, bool) and length >= 0:
                total += length
    if duplicates:
        evidence["duplicate_ids"] = sorted(set(duplicates))
        reasons.append("duplicate artifact ids in inventory: " + ", ".join(sorted(set(duplicates))))
    if total > limits.max_total_bytes:
        return _result("fail", reasons + ["declared artifact bytes exceed the inventory total limit"], evidence)
    if duplicates:
        return _result("fail", reasons, evidence)

    # Reports (recipient-generated); one per artifact, bound to the artifact digest.
    reports: dict[str, dict[str, Any]] = {}
    report_problems: dict[str, list[str]] = {}
    for report in reports_in:
        problems = _report_problems(report)
        aid = report.get("artifact_id") if isinstance(report, dict) and isinstance(report.get("artifact_id"), str) else None
        if aid is None:
            reasons.append("verification report without a usable artifact_id: " + "; ".join(problems or ["malformed"]))
            continue
        if aid in reports or aid in report_problems:
            report_problems.setdefault(aid, []).append("more than one verification report for the artifact")
            continue
        if problems:
            report_problems[aid] = problems
        else:
            reports[aid] = report
    for aid in list(reports) + list(report_problems):
        if aid not in seen:
            reasons.append(f"verification report names {aid!r}, which is not in the inventory")

    any_fail = bool(reasons)
    any_unavailable = False
    any_unsupported = False
    by_id: dict[str, dict[str, Any]] = {}

    # Pass 2: bytes, digests and native results per artifact.
    for entry, (problems, shape) in zip(entries, problems_by_index):
        aid = entry.get("artifact_id") if isinstance(entry, dict) else None
        key = aid if isinstance(aid, str) else f"#invalid-{len(by_id)}"
        art: dict[str, Any] = {"required": False, "bytes_digest": "fail", "reasons": []}
        by_id[key] = art
        if shape == "fail":
            art["reasons"] = problems
            reasons.extend(f"{key}: {p}" for p in problems)
            any_fail = True
            continue
        is_required = (entry.get("required") is True or key in required_artifacts or key in native_required)
        art["required"] = is_required
        if "producer_assertions" in entry:
            art["producer_assertions"] = entry["producer_assertions"]
            art["producer_assertions_status"] = "not_evaluated"
        for field in ("limitations", "native_signature_scope", "lineage"):
            if field in entry:
                art[field] = entry[field]
        if key in required_artifacts and entry["relation"] != required_artifacts[key]:
            art["reasons"].append("relation differs from the relation the recipient policy requires")
            reasons.append(f"{key}: relation differs from the relation the recipient policy requires")
            any_fail = True
        if shape == "unsupported":
            art["bytes_digest"] = "unsupported"
            art["reasons"].extend(problems)
            any_unsupported = True  # an entry whose digest cannot be checked is never treated as verified, required or not
            reasons.extend(f"{key}: {p}" for p in problems)
            continue

        # bytes: embedded and/or recipient supplied
        candidates: list[bytes] = []
        failed_bytes = False
        try:
            if "bytes_base64" in entry:
                candidates.append(_decode(entry["bytes_base64"], limits))
            if supplied_artifacts is not None and key in supplied_artifacts:
                value = supplied_artifacts[key]
                if not isinstance(value, (bytes, bytearray)) or len(value) > limits.max_artifact_bytes:
                    raise ValueError("supplied artifact is not bytes or exceeds the per-artifact limit")
                candidates.append(bytes(value))
            if key in policy_supplied:
                candidates.append(_decode(policy_supplied[key], limits))
        except ValueError as exc:
            art["reasons"].append(str(exc))
            reasons.append(f"{key}: {exc}")
            failed_bytes = True
        if not failed_bytes and any(c != candidates[0] for c in candidates):
            art["reasons"].append("supplied bytes differ from the other copy of the artifact")
            reasons.append(f"{key}: supplied bytes differ from the other copy of the artifact")
            failed_bytes = True
        if failed_bytes:
            any_fail = True
        elif not candidates:
            art["bytes_digest"] = "unavailable"
            art["reasons"].append("artifact bytes are not available; locator is opaque and never dereferenced")
            if is_required:
                any_unavailable = True
                reasons.append(f"{key}: required artifact bytes are unavailable")
            else:
                evidence["unavailable_optional"].append(key)
        else:
            data = candidates[0]
            if len(data) != entry["byte_length"]:
                art["reasons"].append("byte length does not match the artifact bytes")
                reasons.append(f"{key}: byte length does not match the artifact bytes")
                any_fail = True
            elif hashlib.sha256(data).hexdigest() != entry["digest_value"]:
                art["reasons"].append("digest does not match the original artifact bytes")
                reasons.append(f"{key}: digest does not match the original artifact bytes")
                any_fail = True
            else:
                art["bytes_digest"] = "pass"

        # native verification: recipient-generated report only
        native: dict[str, Any] = {"status": "not_evaluated", "source": "none"}
        report = reports.get(key)
        if key in report_problems:
            native = {"status": "fail", "source": "recipient_report", "reasons": report_problems[key]}
            reasons.extend(f"{key}: {p}" for p in report_problems[key])
            any_fail = True
        elif report is not None:
            native = {"status": report["status"], "source": "recipient_report", "verifier_id": report["verifier_id"],
                      "verifier_version": report["verifier_version"], "recipient_policy_id": report["recipient_policy_id"]}
            if "reasons" in report:
                native["reasons"] = report["reasons"]
            if report["artifact_digest_value"] != entry["digest_value"]:
                native["status"] = "fail"
                native["reasons"] = ["report is not bound to this artifact's digest"]
                reasons.append(f"{key}: verification report is not bound to this artifact's digest")
                any_fail = True
        if key in native_required:
            effective = native["status"]
            if report is None and key not in report_problems:
                native["status"] = effective = "unavailable"
                native["reasons"] = ["no recipient-generated verification report; producer assertions are not a verification result"]
                reasons.append(f"{key}: native verification is required and no recipient report was supplied")
                any_unavailable = True
            elif effective == "fail":
                reasons.append(f"{key}: native verification failed")
                any_fail = True
            elif effective in {"unavailable", "not_evaluated"}:
                reasons.append(f"{key}: native verification is {effective}")
                any_unavailable = True
            elif effective == "unsupported":
                reasons.append(f"{key}: native verification is unsupported")
                any_unsupported = True
        elif native["status"] == "fail" and report is not None:
            # A failing report is a negative fact even when the recipient did not require it.
            reasons.append(f"{key}: recipient native verification reported fail")
            any_fail = True
        art["native_verification"] = native
        by_id[key] = art

    # Requirements naming artifacts the inventory does not list.
    for aid in sorted(set(required_artifacts) | set(native_required)):
        if aid not in seen:
            reasons.append(f"{aid}: required artifact is not in the inventory")
            any_unavailable = True
    if not entries and not has_requirement:
        reasons.append("inventory lists no artifacts")
        any_unavailable = True

    evidence["artifacts"] = by_id
    if any_fail:
        return _result("fail", reasons, evidence)
    if any_unavailable:
        return _result("unavailable", reasons, evidence)
    if any_unsupported:
        return _result("unsupported", reasons, evidence)
    return _result("pass", ["every required artifact's bytes match their digest and length; this is not authentication of the artifacts' content or issuer"], evidence)
