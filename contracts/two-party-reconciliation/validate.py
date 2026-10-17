"""Reference validator for the Two-party reconciliation contract (0.1.0-draft).

Stdlib only. A draft: it states the contract executably so each side of the boundary can be tested alone
against golden fixtures. It does not import or modify ``odes``.

Layers:

1. Structure: the JSON Schema subset interpreter.
2. Rules: the per-event rules in README.md. One reconciliation row per event reference compares the sender's record and the
   receiver's record of that event (``event_digest`` of each) and states an outcome before anything is committed.

The contract layers on the delivery vocabulary of ``governed-exchange`` and the attempt rows of ``execution-attempt-lifecycle``
by reference only; it edits neither. Catalog scenario D04 is ambiguous delivery.

``validate`` returns a list of ``Violation`` (empty list means conformant). Refusal codes are stable strings.
The structural interpreter is the one used by the other drafts (JSON Schema subset, plus ``minimum`` and ``minItems``).
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "schema.json"
CONTRACT = "two-party-reconciliation"
CONTRACT_VERSION = "0.1.0-draft"
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


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
        # Closed enumeration: an unknown value is refused with its own typed code and never coerced. A new
        # value in any enumeration is a major version bump (ODES item 6, decided 2026-10-17).
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
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            out.append(Violation("schema_violation", path, "string shorter than minimum length"))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            out.append(Violation("schema_violation", path, "string longer than maximum length"))
        if "pattern" in schema and not re.search(schema["pattern"], value):
            out.append(Violation("schema_violation", path, f"string does not match {schema['pattern']}"))
    if isinstance(value, list) and "minItems" in schema and len(value) < schema["minItems"]:
        out.append(Violation("schema_violation", path, "array shorter than minimum length"))
    if isinstance(value, (int, float)) and not isinstance(value, bool) and "minimum" in schema and value < schema["minimum"]:
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
            reserved = names_schema.get("pattern", "").startswith("^x-")
            for name in value:
                if _sub(name, names_schema, root, path):
                    out.append(Violation("invalid_extension_key" if reserved else "schema_violation", f"{path}.{name}",
                                         "extension member names must match the reserved x- form" if reserved
                                         else "member name does not match its declared form"))


def _sub(value: Any, schema: dict[str, Any], root: dict[str, Any], path: str) -> list[Violation]:
    out: list[Violation] = []
    _check(value, schema, root, path, out)
    return out


def validate_structure(doc: Any) -> list[Violation]:
    schema = load_schema()
    out: list[Violation] = []
    if isinstance(doc, dict) and isinstance(doc.get("contract_version"), str) \
            and doc["contract_version"] != CONTRACT_VERSION and doc.get("contract") == CONTRACT:
        return [Violation("unsupported_contract_version", "$.contract_version",
                          f"this validator implements {CONTRACT_VERSION} only")]
    _check(doc, schema, schema, "$", out)
    return out


# --------------------------------------------------------------------------- helpers

def aware(value: Any) -> datetime | None:
    """Parse an ISO-8601 time; None when malformed or without a UTC offset (naive times are not evidence)."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


def commitment(value: Any) -> str:
    """Control Plane commitment: SHA-256 over sorted compact UTF-8 JSON (``bounded.commitment``)."""
    import hashlib
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _v(code: str, path: str, message: str) -> Violation:
    return Violation(code, path, message)




# --------------------------------------------------------------------------- rules

def _v(code: str, path: str, message: str) -> Violation:
    return Violation(code, path, message)


def _reconciliation_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    ids: set[str] = set()
    events: set[str] = set()
    record_ids: set[str] = set()
    for i, r in enumerate(doc["reconciliations"]):
        p = f"$.reconciliations[{i}]"
        if r["reconciliation_id"] in ids:
            out.append(_v("duplicate_reconciliation_id", p, "reconciliation ids are unique"))
        ids.add(r["reconciliation_id"])
        if r["event_ref"] in events:
            out.append(_v("duplicate_event_reconciliation", p,
                          "one reconciliation per event: a second row for the same event would be a second verdict on it"))
        events.add(r["event_ref"])
        sender, receiver, outcome = r["sender"], r["receiver"], r["outcome"]
        present = [x for x in (sender, receiver) if x is not None]
        for side, x in (("sender", sender), ("receiver", receiver)):
            if x is None:
                continue
            if x["record_id"] in record_ids:
                out.append(_v("duplicate_record_id", f"{p}.{side}", "record ids are unique across the document"))
            record_ids.add(x["record_id"])
            if x["event_ref"] != r["event_ref"]:
                out.append(_v("event_ref_mismatch", f"{p}.{side}.event_ref", "both records name the event the row reconciles"))
            if aware(x["recorded_at"]) is None:
                out.append(_v("timestamp_invalid", f"{p}.{side}.recorded_at", "times are timezone-aware"))
        compared = aware(r["compared_at"]) if r["compared_at"] is not None else None
        if r["compared_at"] is not None and compared is None:
            out.append(_v("timestamp_invalid", f"{p}.compared_at", "times are timezone-aware"))
        if sender is not None and receiver is not None and sender["party_id"] == receiver["party_id"]:
            out.append(_v("same_party", p, "sender and receiver are different parties"))
        if outcome == "awaiting_peer":
            if len(present) != 1 or r["compared_at"] is not None:
                out.append(_v("outcome_records_inconsistent", p, "awaiting_peer has exactly one record and no comparison time"))
        else:
            if len(present) != 2:
                out.append(_v("outcome_records_inconsistent", p, f"{outcome} needs both the sender's and the receiver's record"))
            elif r["compared_at"] is None:
                out.append(_v("comparison_missing", p, f"{outcome} states when the comparison was made"))
        both = len(present) == 2
        differ = both and sender["event_digest"] != receiver["event_digest"]
        if both and ((outcome == "matched" and differ) or (outcome == "mismatch" and not differ)):
            out.append(_v("outcome_digest_inconsistent", f"{p}.outcome", "matched if and only if the two event digests are equal"))
        if outcome == "mismatch" and r["mismatch"] is None:
            out.append(_v("mismatch_not_surfaced", f"{p}.mismatch", "a mismatch outcome carries the mismatch (differing members and a disposition)"))
        if outcome != "mismatch" and r["mismatch"] is not None:
            out.append(_v("mismatch_unexpected", f"{p}.mismatch", "only a mismatch outcome carries a mismatch member"))
        commit = r["commit"]
        if commit is not None:
            if differ:
                out.append(_v("mismatch_committed", f"{p}.commit", "records whose digests differ are never committed as valid"))
            elif outcome != "matched":
                out.append(_v("commit_without_match", f"{p}.commit", "only a matched outcome commits"))
            else:
                committed = aware(commit["committed_at"])
                if committed is None:
                    out.append(_v("timestamp_invalid", f"{p}.commit.committed_at", "times are timezone-aware"))
                elif compared is None or committed < compared:
                    out.append(_v("commit_before_comparison", f"{p}.commit", "the comparison precedes the commit"))
                if sorted(commit["record_ids"]) != sorted(x["record_id"] for x in present):
                    out.append(_v("commit_records_mismatch", f"{p}.commit.record_ids", "the commit names exactly the two compared records"))
        if both and compared is not None:
            for side, x in (("sender", sender), ("receiver", receiver)):
                t = aware(x["recorded_at"])
                if t is not None and t > compared:
                    out.append(_v("record_after_comparison", f"{p}.{side}.recorded_at", "a record compared is recorded before the comparison"))
    return out


def validate(doc: Any) -> list[Violation]:
    """Return all violations; an empty list means the document conforms to 0.1.0-draft."""
    out = validate_structure(doc)
    if out:
        return out
    out.extend(_reconciliation_rules(doc))
    return out


def committed_events(doc: dict[str, Any]) -> list[str]:
    """Event references that were compared, matched and committed (the only events with two agreeing records)."""
    return [r["event_ref"] for r in doc["reconciliations"] if r["commit"] is not None]


def open_events(doc: dict[str, Any]) -> list[str]:
    """Event references that are not safely committed: a surfaced mismatch or a peer still missing."""
    return [r["event_ref"] for r in doc["reconciliations"] if r["commit"] is None]


def canonical_bytes(doc: Any) -> bytes:
    """Digest input: the whole document including every `extensions` member, never a projection."""
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


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
        data = json.loads(Path(name).read_text(encoding="utf-8"))
        # fixtures wrap the document
        violations = validate(data["document"] if isinstance(data, dict) and "document" in data and "fixture_id" in data else data)
        for v in violations:
            print(f"{name}: {v.code} {v.path}: {v.message}")
        code |= bool(violations)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
