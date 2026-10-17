"""Reference validator for the Source-family counting contract (0.1.0-draft).

Stdlib only. A draft: it states the contract executably so each side of the boundary can be tested alone
against golden fixtures. It does not import or modify ``odes``.

Layers:

1. Structure: the JSON Schema subset interpreter.
2. Rules: the record and claim rules in README.md. A record is an original, or a retry, re-send or derived record that names
   the record it came from (``derived_from``) and carries that record's ``family_id``. A claim lists the records put forward as
   confirmations, states how many distinct families they cover (``counted_families``) and whether that meets the requirement.

The contract layers on the exchange delivery records (``governed-exchange``) and the journal (``control-plane-journal``) by
reference only; it edits neither. Which sources belong to one family is declared by the producer, never inferred here.

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
CONTRACT = "source-family-counting"
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


def _first(doc: dict[str, Any]) -> dict[str, tuple[int, dict[str, Any]]]:
    first: dict[str, tuple[int, dict[str, Any]]] = {}
    for i, r in enumerate(doc["records"]):
        first.setdefault(r["record_id"], (i, r))
    return first


def _record_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    first = _first(doc)
    seen: set[str] = set()
    for i, r in enumerate(doc["records"]):
        p = f"$.records[{i}]"
        if r["record_id"] in seen:
            out.append(_v("duplicate_record_id", p, "record ids are unique"))
        seen.add(r["record_id"])
        parent_id = r["derived_from"]
        if (r["kind"] == "original") != (parent_id is None):
            out.append(_v("origin_inconsistent", p, "an original names no source record; a retry, re-send or derived record names one"))
            continue
        if parent_id is None:
            continue
        parent = first.get(parent_id)
        if parent is None:
            out.append(_v("origin_missing", f"{p}.derived_from", "the record this one came from is in the document"))
        elif parent[0] >= i:
            out.append(_v("origin_not_earlier", f"{p}.derived_from", "the source record appears earlier in the list (append-only order)"))
        elif parent[1]["family_id"] != r["family_id"]:
            out.append(_v("family_not_inherited", f"{p}.family_id", "a retry, re-send or derived record carries its source record's family"))
    return out


def family_of(doc: dict[str, Any], record_id: str) -> str | None:
    """The family of a record (the family of its original, since every derived record inherits it)."""
    entry = _first(doc).get(record_id)
    return None if entry is None else entry[1]["family_id"]


def count_families(doc: dict[str, Any], record_ids: list[str]) -> int:
    """Distinct source families among the named records (unknown ids are ignored)."""
    return len({f for f in (family_of(doc, rid) for rid in record_ids) if f is not None})


def _claim_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    first = _first(doc)
    seen: set[str] = set()
    for i, c in enumerate(doc["claims"]):
        p = f"$.claims[{i}]"
        if c["claim_id"] in seen:
            out.append(_v("duplicate_claim_id", p, "claim ids are unique"))
        seen.add(c["claim_id"])
        if len(set(c["confirmations"])) != len(c["confirmations"]):
            out.append(_v("duplicate_confirmation", f"{p}.confirmations", "a record is put forward once"))
        if any(rid not in first for rid in c["confirmations"]):
            out.append(_v("confirmation_dangling", f"{p}.confirmations", "every confirmation names a record in the document"))
            continue
        if c["counted_families"] != count_families(doc, c["confirmations"]):
            out.append(_v("family_count_mismatch", f"{p}.counted_families",
                          "counted_families is the number of distinct families among the confirmations, not the number of records"))
        if c["satisfied"] != (c["counted_families"] >= c["required_families"]):
            out.append(_v("satisfied_inconsistent", f"{p}.satisfied", "satisfied if and only if counted_families reaches required_families"))
    return out


def validate(doc: Any) -> list[Violation]:
    """Return all violations; an empty list means the document conforms to 0.1.0-draft."""
    out = validate_structure(doc)
    if out:
        return out
    out.extend(_record_rules(doc))
    out.extend(_claim_rules(doc))
    return out


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
