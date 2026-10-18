"""Reference validator for the governed-exchange contract (0.1.0-draft).

Stdlib only. A spike in the same pattern as ``contracts/execution-attempt-lifecycle``: it states the contract
executably so each side of the boundary can be tested alone against golden fixtures. It does not import or modify
``odes`` and imports no exchange code.

Two layers:

1. Structure: a minimal interpreter for the JSON Schema subset used by ``schema.json`` (the schema is the single
   source of truth for members, types, enumerations and the closed-member-set rule).
2. Exchange rules: the cross-record rules in README.md. Every rule here is read from what the exchange reference
   code does (``gax_ref.py``, ``gax_ref_runtime.py``, ``transport.py`` on cognous-governed-exchange main).

``validate`` returns a list of ``Violation`` (empty means conformant). Refusal codes are stable strings. Where the
exchange already names a refusal (the retained-export and successor checks) the contract reuses its string.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "schema.json"
CONTRACT = "governed-exchange"
CONTRACT_VERSION = "0.1.0-draft"

MESSAGE_PROFILE = "urn:cognous:profiles:odex-gax-imx-refund-exchange:0.1.0"
TRANSPORT_PROFILE = "urn:cognous:profiles:governed-message-transport:0.1.0"
RESULT_PROFILE = "urn:cognous:profiles:governed-message-recipient-result"
EXPORT_PROFILE = "urn:cognous:profiles:gax-retained-artifacts"
EXPORT_VERSIONS = ("1.0.0", "1.1.0")
UNSUPPORTED_LIMITS = {"cryptographically_authenticated_network_identity",
                      "distributed_exactly_once_delivery", "independent_effect_verification"}
DERIVED_EXPORT_STATES = {"original_complete", "regenerated_derivative", "recovery_denied_derivative",
                         "reconciled_derivative"}
DERIVATIVE_STATES = DERIVED_EXPORT_STATES - {"original_complete"}
STATE_RELATIONSHIP = {"original_complete": "original", "regenerated_derivative": "regenerated_derivative",
                      "recovery_denied_derivative": "recovery_denial_derivative",
                      "reconciled_derivative": "observation_reconciliation_derivative"}
EXPORT_REF_KEYS = ("reconstruction_bundle_id", "reconstruction_digest", "odes_package_digest",
                   "odes_validation_digest", "successor_packet_id", "successor_packet_digest")


@dataclass(frozen=True)
class Violation:
    code: str
    path: str
    message: str


# --------------------------------------------------------------------------- input hardening

class InputRefused(ValueError):
    """The input file is not a strict JSON document (duplicate member, non-finite number, bad encoding)."""


_TIME_SHAPE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})")


def _pattern_ok(pattern: str, value: str) -> bool:
    """A schema pattern matches the whole string: ``^`` and ``$`` are anchors, never "before a trailing newline"."""
    body = pattern[1:] if pattern.startswith("^") else pattern
    if body.endswith("$") and not body.endswith("\\$"):
        body = body[:-1]
    return re.fullmatch(body, value, re.ASCII) is not None


def _printable(text: str) -> str:
    return text.encode("ascii", "backslashreplace").decode("ascii")


def _scan_input(value: Any, root: str = "$") -> list[Violation]:
    """Refuse non-finite numbers and text that is not valid Unicode before any rule reads the document."""
    out: list[Violation] = []
    todo = [(value, root)]
    while todo:
        item, path = todo.pop()
        if isinstance(item, float) and not math.isfinite(item):
            out.append(Violation("schema_violation", path, "non-finite numbers (NaN, Infinity) are refused"))
        elif isinstance(item, str):
            try:
                item.encode("utf-8")
            except UnicodeEncodeError:
                out.append(Violation("schema_violation", path, "text is not valid Unicode (unpaired surrogate)"))
        elif isinstance(item, dict):
            for key, member in reversed(list(item.items())):
                if isinstance(key, str):
                    try:
                        key.encode("utf-8")
                    except UnicodeEncodeError:
                        out.append(Violation("schema_violation", f"{path}.{_printable(key)}",
                                             "member name is not valid Unicode (unpaired surrogate)"))
                todo.append((member, f"{path}.{_printable(str(key))}"))
        elif isinstance(item, list):
            for i in range(len(item) - 1, -1, -1):
                todo.append((item[i], f"{path}[{i}]"))
    return out


def _guarded(fn):
    """Wrap ``validate`` so a document can only be accepted or refused with typed violations, never raise."""
    def validate(doc: Any, *args: Any, **kwargs: Any) -> list[Violation]:
        found = _scan_input(doc)
        for n, extra in enumerate(list(args) + list(kwargs.values()), 1):
            if isinstance(extra, (dict, list)):
                found.extend(_scan_input(extra, f"$input{n}"))
        if found:
            return found
        try:
            return fn(doc, *args, **kwargs)
        except (UnicodeError, ArithmeticError, ValueError, RecursionError) as exc:
            return [Violation("schema_violation", "$", f"the document could not be evaluated ({type(exc).__name__})")]
    validate.__doc__ = fn.__doc__
    validate.__name__ = "validate"
    return validate


def _refuse_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise InputRefused(f"duplicate member name {_printable(key)!r}")
        seen[key] = value
    return seen


def _refuse_constant(name: str) -> Any:
    raise InputRefused(f"non-finite number {name} is not JSON")


def _parse_float(text: str) -> float:
    number = float(text)
    if not math.isfinite(number):
        raise InputRefused("number outside the finite range")
    return number


def strict_loads(text: str) -> Any:
    """Strict JSON: no duplicate members, no NaN or Infinity (also by overflow), UTF-8 text only."""
    try:
        return json.loads(text, object_pairs_hook=_refuse_duplicates, parse_constant=_refuse_constant,
                          parse_float=_parse_float)
    except RecursionError as exc:
        raise InputRefused("nesting too deep") from exc


def load_strict_json(path: Path) -> Any:
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InputRefused("file is not UTF-8") from exc
    try:
        return strict_loads(text)
    except InputRefused:
        raise
    except ValueError as exc:
        raise InputRefused(f"file is not valid JSON ({type(exc).__name__})") from exc


def _after(start: datetime, seconds: Any) -> datetime | None:
    """``start`` plus ``seconds``; None when the sum is outside the representable range."""
    try:
        return start + timedelta(seconds=seconds)
    except (OverflowError, ValueError):
        return None



def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- structure

def _is_type(value: Any, name: str) -> bool:
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    raise ValueError(f"unsupported schema type {name!r}")


def _resolve(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if ref is None:
        return schema
    if not ref.startswith("#/"):
        raise ValueError(f"unsupported $ref {ref!r}")
    node: Any = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def _check(value: Any, schema: dict[str, Any], root: dict[str, Any], path: str, out: list[Violation]) -> None:
    schema = _resolve(schema, root)
    if "const" in schema and value != schema["const"]:
        out.append(Violation("schema_violation", path, f"expected constant {schema['const']!r}"))
        return
    if "enum" in schema and not any(value == option and type(value) is type(option) for option in schema["enum"]):
        # Closed enumeration: an unknown value is refused with its own typed code and never coerced.
        out.append(Violation("unknown_enum_value", path, f"value {value!r} not in declared set"))
        return
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(value, n) for n in names):
            out.append(Violation("schema_violation", path, f"expected type {'|'.join(names)}"))
            return
    if "oneOf" in schema:
        matches = 0
        for option in schema["oneOf"]:
            trial: list[Violation] = []
            _check(value, option, root, path, trial)
            matches += not trial
        if matches != 1:
            for option in schema["oneOf"]:
                trial = []
                _check(value, option, root, path, trial)
                if trial and value is not None:
                    out.extend(trial)
                    return
            out.append(Violation("schema_violation", path, "does not match exactly one alternative"))
        return
    if "anyOf" in schema:
        if not any(not _sub(value, option, root, path) for option in schema["anyOf"]):
            out.append(Violation("schema_violation", path, "does not satisfy any required member group"))
    for option in schema.get("allOf", []):
        # Conditional members: `if` selects, `then` applies. Only if/then pairs are used by schema.json.
        if "if" in option:
            if not _sub(value, option["if"], root, path) and "then" in option:
                _check(value, option["then"], root, path, out)
        else:
            _check(value, option, root, path, out)
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            out.append(Violation("schema_violation", path, "string shorter than minimum length"))
        if "pattern" in schema and not _pattern_ok(schema["pattern"], value):
            out.append(Violation("schema_violation", path, f"string does not match {schema['pattern']}"))
        elif "T[0-9]{2}:[0-9]{2}:[0-9]{2}" in schema.get("pattern", "") and _real_time(value) is None:
            out.append(Violation("schema_violation", path, "string is not a real calendar time with a valid offset"))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            out.append(Violation("schema_violation", path, "number below minimum"))
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            _check(item, schema["items"], root, f"{path}[{i}]", out)
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                out.append(Violation("schema_violation", f"{path}.{name}", "required member missing"))
        extra = schema.get("additionalProperties", True)
        for name, member in value.items():
            if name in props:
                _check(member, props[name], root, f"{path}.{name}", out)
            elif extra is False:
                out.append(Violation("undeclared_member", f"{path}.{name}",
                                     "member is neither declared nor inside the extensions namespace"))
            elif isinstance(extra, dict):
                _check(member, extra, root, f"{path}.{name}", out)
        names_schema = schema.get("propertyNames")
        if names_schema is not None:
            for name in value:
                if _sub(name, names_schema, root, path):
                    out.append(Violation("invalid_extension_key", f"{path}.{name}",
                                         "extension member names must match the reserved x- form"))


def _sub(value: Any, schema: dict[str, Any], root: dict[str, Any], path: str) -> list[Violation]:
    out: list[Violation] = []
    _check(value, schema, root, path, out)
    return out


def _gates(doc: Any) -> list[Violation]:
    """Version and profile gates, refused with their own typed codes before structure is judged."""
    out: list[Violation] = []
    if not isinstance(doc, dict) or doc.get("contract") != CONTRACT:
        return out

    def gate(obj: Any, key: str, allowed: tuple[Any, ...], code: str, path: str) -> None:
        if isinstance(obj, dict) and isinstance(obj.get(key), str) and obj[key] not in allowed:
            out.append(Violation(code, f"{path}.{key}", f"{key} {obj[key]!r} is not supported by {CONTRACT_VERSION}"))

    gate(doc, "contract_version", (CONTRACT_VERSION,), "unsupported_contract_version", "$")
    if out:
        return out
    gate(doc.get("message"), "profile", (MESSAGE_PROFILE,), "unsupported_profile", "$.message")
    gate(doc.get("message"), "protocol_version", ("0.1.0",), "unsupported_profile", "$.message")
    env = doc.get("transport_envelope")
    gate(env, "transport_profile", (TRANSPORT_PROFILE,), "unsupported_transport_profile", "$.transport_envelope")
    gate(env, "transport_version", ("0.1.0",), "unsupported_transport_version", "$.transport_envelope")
    gate(env, "canonicalization_version", ("json-sort-keys-compact-v1",), "unsupported_canonicalization",
         "$.transport_envelope")
    result = doc.get("recipient_result")
    gate(result, "result_profile", (RESULT_PROFILE,), "unsupported_result_profile", "$.recipient_result")
    gate(result, "result_version", ("1.0.0",), "unsupported_result_profile", "$.recipient_result")
    for where, export in (("$.retained_artifact_export", doc.get("retained_artifact_export")),
                          ("$.recipient_result.artifact_export",
                           result.get("artifact_export") if isinstance(result, dict) else None)):
        gate(export, "export_profile", (EXPORT_PROFILE,), "unsupported_artifact_export_profile", where)
        gate(export, "export_version", EXPORT_VERSIONS, "unsupported_artifact_export_version", where)
    packet = doc.get("successor_packet")
    gate(packet, "profile", (MESSAGE_PROFILE,), "unsupported_profile_or_schema", "$.successor_packet")
    gate(packet, "schema_version", ("0.1.0",), "unsupported_profile_or_schema", "$.successor_packet")
    return out


def validate_structure(doc: Any) -> list[Violation]:
    gated = _gates(doc)
    if gated:
        return gated
    schema = load_schema()
    out: list[Violation] = []
    _check(doc, schema, schema, "$", out)
    return out


# --------------------------------------------------------------------------- exchange rules

def canonical_bytes(value: Any) -> bytes:
    """The exchange's canonicalisation (json-sort-keys-compact-v1): sorted keys, compact, UTF-8, no NaN."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _real_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def parse_time(value: str) -> datetime:
    parsed = _real_time(value)
    if parsed is None:
        raise ValueError(f"not a time: {value!r}")
    return parsed


def _without(obj: dict[str, Any], key: str) -> dict[str, Any]:
    return {k: v for k, v in obj.items() if k != key}


def _digest_rules(message: dict[str, Any], path: str, *, content_required: bool) -> list[Violation]:
    out: list[Violation] = []
    if message["message_digest"] != digest(_without(message, "message_digest")):
        out.append(Violation("message_digest_mismatch", f"{path}.message_digest",
                             "message_digest is the digest of every other member"))
    if (content_required or "content_digest" in message) and message.get("content_digest") != digest(message.get("content")):
        out.append(Violation("content_digest_mismatch", f"{path}.content_digest",
                             "content_digest is the digest of the content member"))
    return out


def _message_rules(m: dict[str, Any], path: str) -> list[Violation]:
    out = _digest_rules(m, path, content_required=True)
    if parse_time(m["expires_at"]) <= parse_time(m["created_at"]):
        out.append(Violation("message_expiry_not_after_creation", f"{path}.expires_at",
                             "a governed message expires after it is created"))
    for i, ref in enumerate(m["evidence_refs"]):
        if ref["type"] == "replay_bundle" and "digest" not in ref:
            out.append(Violation("replay_bundle_ref_without_digest", f"{path}.evidence_refs[{i}]",
                                 "a replay_bundle evidence reference binds the bundle digest; without it the "
                                 "recipient cannot verify the bundle"))
    return out


def _envelope_rules(env: dict[str, Any], path: str) -> list[Violation]:
    msg = env["governed_message"]
    gpath = f"{path}.governed_message"
    out: list[Violation] = []
    if msg["message_id"] != env["message_id"]:
        out.append(Violation("message_identity_mismatch", f"{path}.message_id",
                             "the envelope names the governed message it carries"))
    if msg["conversation_id"] != env["conversation_id"]:
        out.append(Violation("conversation_identity_mismatch", f"{path}.conversation_id",
                             "the envelope repeats the governed message conversation id"))
    if parse_time(env["created_at"]) < parse_time(msg["created_at"]):
        out.append(Violation("envelope_created_before_message", f"{path}.created_at",
                             "a delivery attempt cannot precede the governed message it carries"))
    if parse_time(msg["expires_at"]) <= parse_time(msg["created_at"]):
        out.append(Violation("message_expiry_not_after_creation", f"{gpath}.expires_at",
                             "a governed message expires after it is created"))
    if parse_time(env["expires_at"]) != parse_time(msg["expires_at"]):
        out.append(Violation("envelope_message_expiry_mismatch", f"{path}.expires_at",
                             "the envelope expires when the governed message does"))
    if out:
        return out
    digests = _digest_rules(msg, gpath, content_required=False)
    if digests:
        return digests
    if env["content_commitment"] != msg["message_digest"]:
        out.append(Violation("content_commitment_mismatch", f"{path}.content_commitment",
                             "content_commitment is the governed message's message_digest"))
    return out


def _ack_rules(ack: dict[str, Any], doc: dict[str, Any], path: str = "$.acknowledgement") -> list[Violation]:
    out: list[Violation] = []
    echoed = ("message_id", "delivery_attempt_id", "content_commitment", "recipient_endpoint_ref")
    if ack["acknowledgement_kind"] != "TERMINAL_REJECTION":
        for name in echoed:
            if ack[name] is None:
                out.append(Violation("acknowledgement_binding_incomplete", f"{path}.{name}",
                                     "a receipt is only issued for a validated envelope, so every echoed member is set"))
    env = doc.get("transport_envelope")
    if env is not None:
        for name in echoed:
            if ack[name] != env[name]:
                out.append(Violation("acknowledgement_envelope_mismatch", f"{path}.{name}",
                                     f"the acknowledgement echoes the envelope's {name}"))
    result = doc.get("recipient_result")
    if (result is not None and ack["acknowledgement_kind"] == "DURABLE_RECEIPT"
            and result["result_state"] in {"recovery_required", "historical_artifacts_unavailable"}):
        out.append(Violation("receipt_for_unretained_result", f"{path}.acknowledgement_kind",
                             "a result without a retained artifact set is acknowledged as DURABLE_RECEIPT_UNRESOLVED, "
                             "never as a complete receipt"))
    return out


_ACK_STATES = {"DURABLE_RECEIPT": {"DELIVERED"}, "TERMINAL_REJECTION": {"TERMINAL_REJECTED"},
               "DURABLE_RECEIPT_UNRESOLVED": {"PENDING_RETRY", "UNRESOLVED"}}


def _delivery_rules(d: dict[str, Any], path: str) -> list[Violation]:
    out: list[Violation] = []
    if not d["attempted"]:
        extra = [k for k in ("delivery_attempt_id", "acknowledgement_received", "acknowledgement", "interruption") if k in d]
        if extra:
            out.append(Violation("delivery_result_inconsistent", path,
                                 "a result with attempted false carries no attempt id and no acknowledgement"))
        if d["transport_state"] == "BACKOFF" and "next_attempt_at" not in d:
            out.append(Violation("delivery_result_inconsistent", f"{path}.next_attempt_at",
                                 "BACKOFF names when the next attempt is due"))
        return out
    if d["transport_state"] == "BACKOFF" or "delivery_attempt_id" not in d or "acknowledgement_received" not in d:
        return [Violation("delivery_result_inconsistent", path,
                          "an attempted delivery carries its attempt id and acknowledgement_received, and is never BACKOFF")]
    if d["acknowledgement_received"] != ("acknowledgement" in d):
        out.append(Violation("delivery_result_inconsistent", f"{path}.acknowledgement_received",
                             "acknowledgement_received is true exactly when the acknowledgement is carried"))
        return out
    ack = d.get("acknowledgement")
    if ack is None:
        if d["transport_state"] == "DELIVERED":
            out.append(Violation("delivery_state_ack_mismatch", f"{path}.transport_state",
                                 "DELIVERED requires a received DURABLE_RECEIPT"))
        return out
    if ack["message_id"] != d["message_id"] or ack["delivery_attempt_id"] != d["delivery_attempt_id"]:
        out.append(Violation("delivery_result_inconsistent", f"{path}.acknowledgement",
                             "the acknowledgement answers the attempt this result names"))
    elif d["transport_state"] not in _ACK_STATES[ack["acknowledgement_kind"]]:
        out.append(Violation("delivery_state_ack_mismatch", f"{path}.transport_state",
                             f"acknowledgement kind {ack['acknowledgement_kind']} allows transport_state "
                             + "/".join(sorted(_ACK_STATES[ack["acknowledgement_kind"]]))))
    out.extend(_ack_rules(ack, {}, f"{path}.acknowledgement"))
    return out


def _assessment_rules(a: dict[str, Any], path: str) -> list[Violation]:
    out: list[Violation] = []
    handling = a.get("permitted_handling")
    failed = {k for k, v in a["stages"].items() if v == "failed"}
    if handling in {"REFUSE", "NOT_UNDERSTOOD"} and (not a["errors"] or not failed):
        out.append(Violation("refusal_without_failure", f"{path}.errors",
                             "a refusal carries at least one error and one failed stage"))
    if handling == "INFORMATIONAL_ONLY" and a["stages"].get("communicative_act") != "informational_no_effect":
        out.append(Violation("informational_stage_mismatch", f"{path}.stages.communicative_act",
                             "an informational message is handled as informational_no_effect"))
    understood_failure = bool(failed & {"structure", "profile"})
    if handling in {"REFUSE", "NOT_UNDERSTOOD"} and (handling == "NOT_UNDERSTOOD") != understood_failure:
        out.append(Violation("not_understood_stage_mismatch", f"{path}.permitted_handling",
                             "NOT_UNDERSTOOD is the handling exactly when the structure or profile stage failed"))
    if "message_understood" in a and handling in {"REFUSE", "NOT_UNDERSTOOD"} and a["message_understood"] == understood_failure:
        out.append(Violation("not_understood_stage_mismatch", f"{path}.message_understood",
                             "message_understood is false exactly when the structure or profile stage failed"))
    return out


def _execution_rules(ex: dict[str, Any], result: dict[str, Any], path: str) -> list[Violation]:
    out: list[Violation] = []
    handling = (result.get("assessment") or {}).get("permitted_handling")
    export = result.get("artifact_export")
    if ex["attempted"] and handling != "ACCEPT_FOR_ASSESSMENT":
        out.append(Violation("execution_without_eligible_assessment", f"{path}.attempted",
                             "an effect is only attempted for a message accepted for assessment"))
    status = ex.get("attempt_status")
    if status in {"deny", "hold", "unresolved_duplicate"} and ex["attempted"]:
        out.append(Violation("attempt_status_attempted_mismatch", f"{path}.attempted",
                             f"attempt_status {status!r} means nothing was dispatched"))
    if status in {"interrupted_after_dispatch", "evidence_export_failed"} and not ex["attempted"]:
        out.append(Violation("attempt_status_attempted_mismatch", f"{path}.attempted",
                             f"attempt_status {status!r} means an effect was dispatched"))
    if export is not None and export["state"] in DERIVATIVE_STATES and (ex["attempted"] or ex.get("newly_executed")):
        out.append(Violation("derivative_result_claims_execution", path,
                             "a derivative result is evidence-only: attempted and newly_executed are false"))
    return out


def _export_rules(ex: dict[str, Any], path: str) -> list[Violation]:
    """Retained-export checks in the exchange's own order; the first failing check is the refusal."""
    recon, refs, commits, odes = ex["reconstruction_bundle"], ex["producer_refs"], ex["content_commitments"], ex["odes"]

    def bad(code: str, where: str, message: str) -> list[Violation]:
        return [Violation(code, f"{path}.{where}", message)]

    if refs.get("reconstruction_bundle_id") != recon.get("bundle_id"):
        return bad("retained_reconstruction_identity_mismatch", "producer_refs.reconstruction_bundle_id",
                   "producer_refs.reconstruction_bundle_id equals the retained bundle's bundle_id")
    if refs.get("reconstruction_digest") != digest(recon):
        return bad("retained_reconstruction_digest_mismatch", "producer_refs.reconstruction_digest",
                   "reconstruction_digest is the digest of the retained bundle")
    if commits.get("reconstruction_bundle") != refs.get("reconstruction_digest"):
        return bad("retained_reconstruction_commitment_mismatch", "content_commitments.reconstruction_bundle",
                   "the bundle commitment equals producer_refs.reconstruction_digest")
    for member, ref_key, digest_code, commit_code in (
            ("odes_package", "odes_package_digest", "retained_odes_package_digest_mismatch",
             "retained_odes_package_commitment_mismatch"),
            ("recipient_validation", "odes_validation_digest", "retained_odes_validation_digest_mismatch",
             "retained_odes_validation_commitment_mismatch")):
        value = odes[member]
        if value is None:
            continue
        if refs.get(ref_key) != digest(value):
            return bad(digest_code, f"producer_refs.{ref_key}", f"{ref_key} is the digest of the retained {member}")
        if commits.get(member) != refs.get(ref_key):
            return bad(commit_code, f"content_commitments.{member}",
                       f"the {member} commitment equals producer_refs.{ref_key}")
    packet = ex["successor_packet"]
    if packet is not None:
        if refs.get("successor_packet_id") != packet["packet_id"]:
            return bad("retained_successor_identity_mismatch", "producer_refs.successor_packet_id",
                       "successor_packet_id equals the retained packet's packet_id")
        if refs.get("successor_packet_digest") != packet["packet_digest"]:
            return bad("retained_successor_digest_mismatch", "producer_refs.successor_packet_digest",
                       "successor_packet_digest equals the retained packet's packet_digest")
        if packet["packet_digest"] != digest(_without(packet, "packet_digest")):
            return bad("retained_successor_content_digest_mismatch", "successor_packet.packet_digest",
                       "packet_digest is the digest of every other packet member")
        if commits.get("successor_packet") != refs.get("successor_packet_digest"):
            return bad("retained_successor_commitment_mismatch", "content_commitments.successor_packet",
                       "the packet commitment equals producer_refs.successor_packet_digest")
    out: list[Violation] = []
    lineage = ex["lineage"]
    if lineage["relationship"] != STATE_RELATIONSHIP[ex["state"]]:
        out.append(Violation("lineage_state_mismatch", f"{path}.lineage.relationship",
                             f"state {ex['state']!r} carries lineage relationship {STATE_RELATIONSHIP[ex['state']]!r}"))
    if lineage.get("effect_reexecution") not in (None, False):
        out.append(Violation("lineage_effect_reexecution", f"{path}.lineage.effect_reexecution",
                             "no retained export ever re-executes an effect"))
    if ex["state"] == "recovery_denied_derivative" and not out:
        flags = ("destination_observation_performed", "replacement_dispatch_performed", "renewed_authorization")
        if any(lineage.get(f) is not False for f in flags) or lineage.get("recovery_status") != "denied":
            out.append(Violation("recovery_denial_lineage_invalid", f"{path}.lineage",
                                 "a denied recovery records recovery_status 'denied' and that no destination "
                                 "observation, replacement dispatch or renewed authorization happened"))
    return out


def _result_rules(res: dict[str, Any], path: str) -> list[Violation]:
    out: list[Violation] = []
    state, export = res["result_state"], res["artifact_export"]
    if state in DERIVED_EXPORT_STATES:
        if export is None or export["state"] != state:
            out.append(Violation("result_state_export_mismatch", f"{path}.result_state",
                                 f"result_state {state!r} mirrors the retained export's state"))
    elif export is not None:
        out.append(Violation("result_state_export_mismatch", f"{path}.artifact_export",
                             f"result_state {state!r} means no complete artifact set is retained"))
    if state == "unavailable" and any(k in res for k in ("assessment", "execution", "producer_refs")):
        out.append(Violation("unavailable_result_carries_content", path,
                             "an unavailable result carries no assessment, execution or producer_refs"))
    if out:
        return out
    if "assessment" in res:
        out.extend(_assessment_rules(res["assessment"], f"{path}.assessment"))
    if "execution" in res:
        out.extend(_execution_rules(res["execution"], res, f"{path}.execution"))
    if export is not None and "producer_refs" in res:
        for key in EXPORT_REF_KEYS:
            if key in res["producer_refs"] and res["producer_refs"][key] != export["producer_refs"].get(key):
                out.append(Violation("result_producer_refs_mismatch", f"{path}.producer_refs.{key}",
                                     "result producer_refs repeat the export's references unchanged"))
    return out


def _evidence_rules(ev: dict[str, Any], path: str) -> list[Violation]:
    out: list[Violation] = []
    if set(ev["unsupported"]) != UNSUPPORTED_LIMITS:
        out.append(Violation("unsupported_limits_missing", f"{path}.unsupported",
                             "the evidence summary names all three honest limits"))
    foreign = {a["transport_attempt_id"] for a in ev["delivery_attempts"]}
    refs = ev["producer_refs"]
    seen = {refs.get("executor_attempt_id"), *refs.get("executor_attempt_ids", []),
            *refs.get("control_plane_attempt_ids", [])}
    if foreign & seen:
        out.append(Violation("attempt_namespace_collision", f"{path}.producer_refs",
                             "transport attempt ids never appear among executor or Control Plane attempt ids"))
    return out


def _validate(doc: Any) -> list[Violation]:
    """Return all violations; an empty list means the document conforms to 0.1.0-draft."""
    out = validate_structure(doc)
    if out:
        return out
    if "message" in doc:
        out.extend(_message_rules(doc["message"], "$.message"))
    if "transport_envelope" in doc:
        out.extend(_envelope_rules(doc["transport_envelope"], "$.transport_envelope"))
        if "message" in doc and doc["transport_envelope"]["governed_message"] != doc["message"]:
            out.append(Violation("envelope_message_mismatch", "$.transport_envelope.governed_message",
                                 "the envelope carries the governed message verbatim"))
    if "acknowledgement" in doc:
        out.extend(_ack_rules(doc["acknowledgement"], doc))
    if "delivery_result" in doc:
        out.extend(_delivery_rules(doc["delivery_result"], "$.delivery_result"))
    if "retained_artifact_export" in doc:
        out.extend(_export_rules(doc["retained_artifact_export"], "$.retained_artifact_export"))
    if "recipient_result" in doc:
        res = doc["recipient_result"]
        out.extend(_result_rules(res, "$.recipient_result"))
        if res["artifact_export"] is not None:
            out.extend(_export_rules(res["artifact_export"], "$.recipient_result.artifact_export"))
        if "retained_artifact_export" in doc and res["artifact_export"] != doc["retained_artifact_export"]:
            out.append(Violation("artifact_export_mismatch", "$.recipient_result.artifact_export",
                                 "a result's artifact_export is the retained export, unchanged"))
    if "successor_packet" in doc:
        packet = doc["successor_packet"]
        if packet["packet_digest"] != digest(_without(packet, "packet_digest")):
            out.append(Violation("packet_digest_mismatch", "$.successor_packet.packet_digest",
                                 "packet_digest is the digest of every other packet member"))
    if "successor_acceptance" in doc:
        acc = doc["successor_acceptance"]
        if acc["effect_created"] is not False:
            out.append(Violation("successor_creates_effect", "$.successor_acceptance.effect_created",
                                 "loading a successor packet never creates an effect or a grant"))
        elif acc["loaded"] != (acc["status"] == "loaded_for_reconciliation"):
            out.append(Violation("successor_loaded_status_mismatch", "$.successor_acceptance.loaded",
                                 "loaded is true exactly for status loaded_for_reconciliation"))
    if "transport_evidence" in doc:
        out.extend(_evidence_rules(doc["transport_evidence"], "$.transport_evidence"))
    return out


# --------------------------------------------------------------------------- extension handling

def known_view(doc: dict[str, Any]) -> dict[str, Any]:
    """What a consumer of this version acts on: declared members only (extensions excluded from logic)."""
    def strip(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k != "extensions"}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value
    return strip(doc)


def preserve(doc: dict[str, Any]) -> dict[str, Any]:
    """Consumers re-emit what they received: ignore-but-preserve means a faithful deep copy."""
    return json.loads(json.dumps(doc))


validate = _guarded(_validate)


def main(argv: list[str]) -> int:
    code = 0
    for name in argv:
        try:
            data = load_strict_json(Path(name))
        except (InputRefused, OSError) as exc:
            print(f"{name}: input_refused $: {_printable(str(exc))}")
            code |= 2
            continue
        wrapped = isinstance(data, dict) and "document" in data and "fixture_id" in data
        violations = validate(data["document"] if wrapped else data)
        for v in violations:
            print(f"{name}: {v.code} {v.path}: {_printable(v.message)}")
        code |= bool(violations)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
