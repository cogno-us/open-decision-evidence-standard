"""Reference validator for the index-evidence-registry contract (0.1.0-draft).

Stdlib only. A spike in the same pattern as ``contracts/execution-attempt-lifecycle`` and ``contracts/governed-exchange``:
it states the contract executably so each side of the Index boundary can be tested alone against golden fixtures.
It does not import or modify ``odes`` and imports no Index or BitRep code (the BitRep statement digest and the link
content digest are re-implemented from their published byte definitions).

Two layers:

1. Structure: a minimal interpreter for the JSON Schema subset used by ``schema.json`` (the schema is the single
   source of truth for members, types, enumerations and the closed-member-set rule).
2. Index rules: the cross-member rules in README.md. Every rule is read from what the Index does
   (``app/evidence/link_attestation.py``, ``app/api/evidence.py``, ``app/evidence/service.py``, the vendored
   ``app/bitrep_verify`` and ``chain/PROTOCOL.md`` on cognous-evidence-registry main d17b8ac).

``validate`` returns a list of ``Violation`` (empty means conformant). Refusal codes are stable strings. Where the
Index already names a refusal reason (HTTP detail.reason, BitRep verification reason) the contract reuses its string.
What the validator cannot decide without the operator trust snapshot or the Index store (signature validity, key
status, idempotent resubmission, whether a link is true) is listed in README.md and not faked here.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "schema.json"
CONTRACT = "index-evidence-registry"
CONTRACT_VERSION = "0.1.0-draft"

LINK_STATEMENT_TYPE = "index.link.v1"
CHAIN_STATEMENT_TYPES = {1: "index-support/1", 2: "index-challenge/1"}
BITREP_DOMAIN = b"BitRep attestation v1\n"
STATEMENT_FIELDS = ("protocol_version", "algorithm", "attestation_id", "issuer", "key_id", "subject", "statement_type",
                    "audience", "content_digest", "issued_at", "not_before", "expires_at")
HTTP_REASONS = {401: {"attestation_required"}, 409: {"attestation_id_conflict"}, 503: {"trust_unavailable"}}
BITREP_REJECTIONS = {"unsupported_version", "unsupported_algorithm", "audience_mismatch", "unknown_key", "key_revoked",
                     "key_not_yet_valid", "key_expired", "issuance_outside_key_validity", "not_yet_valid",
                     "attestation_expired", "malformed_signature", "invalid_signature"}
REASONS_422 = BITREP_REJECTIONS | {"malformed_attestation", "attestation_binding_mismatch"}


@dataclass(frozen=True)
class Violation:
    code: str
    path: str
    message: str


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
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            out.append(Violation("schema_violation", path, "string longer than maximum length"))
        if "pattern" in schema and not re.search(schema["pattern"], value):
            out.append(Violation("schema_violation", path, f"string does not match {schema['pattern']}"))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            out.append(Violation("schema_violation", path, "number below minimum"))
        if "maximum" in schema and value > schema["maximum"]:
            out.append(Violation("schema_violation", path, "number above maximum"))
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
    """Version gate, refused with its own typed code before structure is judged."""
    if (isinstance(doc, dict) and doc.get("contract") == CONTRACT and isinstance(doc.get("contract_version"), str)
            and doc["contract_version"] != CONTRACT_VERSION):
        return [Violation("unsupported_contract_version", "$.contract_version",
                          f"contract_version {doc['contract_version']!r} is not supported by {CONTRACT_VERSION}")]
    return []


def validate_structure(doc: Any) -> list[Violation]:
    gated = _gates(doc)
    if gated:
        return gated
    schema = load_schema()
    out: list[Violation] = []
    _check(doc, schema, schema, "$", out)
    return out


# --------------------------------------------------------------------------- Index rules

def link_content_bytes(link: dict[str, Any]) -> bytes:
    """What ``statement.content_digest`` commits to: the Index's ``link_content_bytes`` (sorted keys, compact,
    ASCII-escaped; absent targets are null; strength is always a float)."""
    body = {"claim_id": link["claim_id"], "claim_id_2": link.get("claim_id_2"), "evidence_id": link.get("evidence_id"),
            "relation_type": link["relation_type"], "strength": float(link.get("strength", 1.0))}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def link_content_digest(link: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(link_content_bytes(link)).hexdigest()


def statement_digest(statement: dict[str, Any]) -> str:
    """BitRep v1 signed-statement digest: domain prefix plus sorted compact ASCII JSON of the twelve fields."""
    body = {k: statement[k] for k in STATEMENT_FIELDS}
    raw = BITREP_DOMAIN + json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _statement_rules(st: dict[str, Any], path: str) -> list[Violation]:
    if not st["issued_at"] <= st["not_before"] < st["expires_at"]:
        return [Violation("malformed_attestation", f"{path}.issued_at",
                          "require issued_at <= not_before < expires_at (BitRep v1 statement)")]
    return []


def _targets(doc: dict[str, Any], path: str) -> list[Violation]:
    if (doc.get("evidence_id") is None) == (doc.get("claim_id_2") is None):
        return [Violation("link_target_invalid", path, "exactly one of evidence_id and claim_id_2 is given")]
    return []


def _submission_rules(link: dict[str, Any], path: str) -> list[Violation]:
    out = _targets(link, path)
    if out:  # without exactly one target there is no link content for the statement to commit to
        return out
    if "attestation" not in link:
        out.append(Violation("attestation_required", f"{path}.attestation",
                             "a link is admitted only with a signed attestation; attested_by alone is not accepted"))
        return out
    st = link["attestation"]["statement"]
    out.extend(_statement_rules(st, f"{path}.attestation.statement"))
    expected = {"statement_type": LINK_STATEMENT_TYPE, "subject": link["claim_id"], "issuer": link["attested_by"],
                "content_digest": link_content_digest(link)}
    for field, want in expected.items():
        if st[field] != want:
            out.append(Violation("attestation_binding_mismatch", f"{path}.attestation.statement.{field}",
                                 f"statement {field} must equal {want!r}"))
    return out


def _stored_link_rules(link: dict[str, Any], path: str) -> list[Violation]:
    out = _targets(link, path)
    aid, dig = link.get("attestation_id"), link.get("attestation_statement_digest")
    if (aid is None) != (dig is None):
        out.append(Violation("attestation_commitment_incomplete", path,
                             "attestation_id and attestation_statement_digest are both present or both absent"))
    elif aid is None:
        out.append(Violation("link_without_attestation", path,
                             "a stored link names the verified attestation it was admitted under"))
    return out


def _verification_rules(doc: dict[str, Any], path: str) -> list[Violation]:
    res = doc["result"]
    out: list[Violation] = []
    ok = (res["outcome"] == "verified", res["reason"] == "ok", res["assurance"] == "issuer_signature_only")
    if len(set(ok)) != 1:
        out.append(Violation("verification_result_inconsistent", f"{path}.result",
                             "outcome verified, reason ok and assurance issuer_signature_only go together; "
                             "a rejection has assurance none"))
    if "envelope" in doc:
        out.extend(_statement_rules(doc["envelope"]["statement"], f"{path}.envelope.statement"))
        if res["statement_digest"] != statement_digest(doc["envelope"]["statement"]):
            out.append(Violation("statement_digest_mismatch", f"{path}.result.statement_digest",
                                 "statement_digest is the BitRep digest of the envelope's statement"))
    return out


def _outcome_rules(doc: dict[str, Any], path: str) -> list[Violation]:
    status, reason = doc["http_status"], doc.get("reason")
    out: list[Violation] = []
    if status in (200, 201):
        if reason is not None:
            out.append(Violation("outcome_status_reason_mismatch", f"{path}.reason", "a success carries no reason"))
        if "link" not in doc:
            out.append(Violation("outcome_link_mismatch", f"{path}.link", "a success returns the stored link"))
        else:
            out.extend(_stored_link_rules(doc["link"], f"{path}.link"))
        return out
    allowed = HTTP_REASONS.get(status, REASONS_422)
    if reason not in allowed:
        out.append(Violation("outcome_status_reason_mismatch", f"{path}.reason",
                             f"status {status} carries one of {sorted(allowed)}"))
    if "link" in doc:
        out.append(Violation("outcome_link_mismatch", f"{path}.link", "a refusal stores and returns no link"))
    return out


def _epistemic_rules(doc: dict[str, Any], path: str) -> list[Violation]:
    out: list[Violation] = []
    sup, con = doc["supporting_weight"], doc["contradicting_weight"]
    if doc["status"] != "deprecated":
        if con > sup:
            want = "refuted" if con > 3.0 else "contested"
        else:
            want = "supported" if sup > 2.0 else "proposed"
        if doc["status"] != want:
            out.append(Violation("status_weights_mismatch", f"{path}.status",
                                 f"weights {sup} / {con} give status {want}"))
    total = sup + con
    want_r = min(total / 10.0, 1.0) if total > 0 else 0.0
    if abs(doc["robustness_score"] - want_r) > 1e-9:
        out.append(Violation("robustness_mismatch", f"{path}.robustness_score",
                             "robustness is min(total weight / 10, 1), or 0 with no weight"))
    ind = doc["independence_score"]
    if ind != 1.0 and abs(ind * 5 - round(ind * 5)) > 1e-9:
        out.append(Violation("independence_not_distinct_source_count", f"{path}.independence_score",
                             "independence is min(distinct source identifiers / 5, 1), a multiple of 0.2 below 1; "
                             "it counts source identifiers, not evidence ids and not independence of origin"))
    return out


def _chain_rules(doc: dict[str, Any], path: str) -> list[Violation]:
    st = doc["statement"]
    out = _statement_rules(st, f"{path}.statement")
    audience = f"index:eip155:{doc['chain_id']}:{doc['contract_address']}:v1"
    subject = f"{audience}:claim:{doc['claim_id'][2:]}"
    checks = (
        ("chain_content_commitment_mismatch", "content_digest", doc["evidence_content_digest"]),
        ("chain_subject_mismatch", "subject", subject),
        ("chain_statement_type_mismatch", "statement_type", CHAIN_STATEMENT_TYPES[doc["relation"]]),
        ("chain_audience_mismatch", "audience", audience),
    )
    for code, field, want in checks:
        if st[field] != want:
            out.append(Violation(code, f"{path}.statement.{field}", f"statement {field} must equal {want!r}"))
    if doc["statement_digest"] != statement_digest(st):
        out.append(Violation("statement_digest_mismatch", f"{path}.statement_digest",
                             "statement_digest is the BitRep digest of the statement"))
    return out


RULES = (("link_submission", _submission_rules), ("stored_link", _stored_link_rules),
         ("verification_result", _verification_rules), ("link_outcome", _outcome_rules),
         ("epistemic_status", _epistemic_rules), ("chain_attestation_check", _chain_rules))


def validate(doc: Any) -> list[Violation]:
    """Structure first; rules run only on a structurally valid document."""
    out = validate_structure(doc)
    if out:
        return out
    for member, rule in RULES:
        if member in doc:
            out.extend(rule(doc[member], f"$.{member}"))
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


def main(argv: list[str]) -> int:
    code = 0
    for name in argv:
        violations = validate(json.loads(Path(name).read_text(encoding="utf-8")))
        for v in violations:
            print(f"{name}: {v.code} {v.path}: {v.message}")
        code |= bool(violations)
    return code


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
