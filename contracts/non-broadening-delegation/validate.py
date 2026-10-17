"""Reference validator for the Non-broadening delegation contract (0.1.0-draft).

Stdlib only. A draft: it states the contract executably so each side of the boundary can be tested alone
against golden fixtures. It does not import or modify ``odes``.

Layers:

1. Structure: the JSON Schema subset interpreter (``schema.json`` is the source of truth for members, types and the closed-member-set rule).
2. Rules: the cross-grant rules in README.md. The grant and delegation shapes are the Control Plane grant model
   (``permissions`` with ``action``, ``targets``, ``data_scopes``, ``max_amount``, ``unit``, ``max_effects``; ``delegation`` with
   ``parent_grant_id``, ``may_delegate``, ``remaining_depth``), read from ``bounded.py`` and the Governed Exchange reference
   (``gax_ref.py``). NOTE: today the Control Plane REFUSES any grant with a ``parent_grant_id`` (``delegation_profile_unsupported``).
   This validator states the profile that would replace that refusal; no current component implements it.

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
CONTRACT = "non-broadening-delegation"
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


def _first_by_id(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for g in doc["grants"]:
        by_id.setdefault(g["grant_id"], g)
    return by_id


def _grant_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    seen: set[str] = set()
    for i, g in enumerate(doc["grants"]):
        p = f"$.grants[{i}]"
        if g["grant_id"] in seen:
            out.append(_v("duplicate_grant_id", p, "grant ids are unique within a document"))
        seen.add(g["grant_id"])
        nb, ex = aware(g["not_before"]), aware(g["expires_at"])
        if nb is None or ex is None:
            out.append(_v("timestamp_invalid", p, "not_before and expires_at are timezone-aware times"))
        elif nb >= ex:
            out.append(_v("window_invalid", p, "not_before is earlier than expires_at"))
        d = g["delegation"]
        if d["may_delegate"] != (d["remaining_depth"] > 0):
            out.append(_v("delegation_flags_inconsistent", f"{p}.delegation",
                          "may_delegate is true if and only if remaining_depth is above zero"))
    return out


def _cycles(by_id: dict[str, dict[str, Any]]) -> list[list[str]]:
    cycles: list[list[str]] = []
    done: set[str] = set()
    for start in by_id:
        path: list[str] = []
        pos: dict[str, int] = {}
        cur: str | None = start
        while cur is not None and cur in by_id and cur not in done:
            if cur in pos:
                cycles.append(path[pos[cur]:])
                break
            pos[cur] = len(path)
            path.append(cur)
            cur = by_id[cur]["delegation"]["parent_grant_id"]
        done.update(path)
    return cycles


def _permission_violation(child: dict[str, Any], parents: list[dict[str, Any]]) -> str | None:
    """None when the child permission fits inside ONE parent permission, else the most specific code."""
    same = [x for x in parents if x["action"] == child["action"]]
    scoped = [x for x in same if set(child["targets"]) <= set(x["targets"]) and set(child["data_scopes"]) <= set(x["data_scopes"])]
    if not scoped:
        return "scope_widened"
    same_unit = [x for x in scoped if x["unit"] == child["unit"]]
    if not same_unit:
        return "unit_changed"
    within_amount = [x for x in same_unit if child["max_amount"] <= x["max_amount"]]
    if not within_amount:
        return "amount_broadened"
    if not any(child["max_effects"] <= x["max_effects"] for x in within_amount):
        return "effects_broadened"
    return None


def _chain_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    by_id = _first_by_id(doc)
    index = {}
    for i, g in enumerate(doc["grants"]):
        index.setdefault(g["grant_id"], i)
    in_cycle: set[str] = set()
    for members in _cycles(by_id):
        in_cycle.update(members)
        first = min(members, key=lambda m: index[m])
        out.append(_v("delegation_cycle", f"$.grants[{index[first]}].delegation.parent_grant_id",
                      "parent references form a cycle: " + " -> ".join(members + [members[0]])))
    for i, g in enumerate(doc["grants"]):
        p = f"$.grants[{i}]"
        parent_id = g["delegation"]["parent_grant_id"]
        if parent_id is None or g["grant_id"] in in_cycle:
            continue
        parent = by_id.get(parent_id)
        if parent is None:
            out.append(_v("parent_missing", f"{p}.delegation.parent_grant_id", "the parent grant is not in the document"))
            continue
        if g["issuer"] != parent["grantee"]:
            out.append(_v("delegator_mismatch", f"{p}.issuer", "a delegated grant is issued by the grantee of its parent"))
        pd, cd = parent["delegation"], g["delegation"]
        if not pd["may_delegate"] or pd["remaining_depth"] < 1:
            out.append(_v("depth_exhausted", f"{p}.delegation", "the parent does not allow further delegation"))
        elif cd["remaining_depth"] > pd["remaining_depth"] - 1:
            out.append(_v("depth_not_decreased", f"{p}.delegation.remaining_depth",
                          "remaining_depth is at most the parent's remaining_depth minus one"))
        nb, ex, pnb, pex = aware(g["not_before"]), aware(g["expires_at"]), aware(parent["not_before"]), aware(parent["expires_at"])
        if None not in (nb, ex, pnb, pex) and (nb < pnb or ex > pex):
            out.append(_v("window_extended", p, "the delegated window lies inside the parent's window"))
        for k, cp in enumerate(g["permissions"]):
            code = _permission_violation(cp, parent["permissions"])
            if code is not None:
                out.append(_v(code, f"{p}.permissions[{k}]",
                              "each delegated permission fits inside a single permission of the parent (action, targets, data scopes, unit, amount, effects)"))
    return out


def validate(doc: Any) -> list[Violation]:
    """Return all violations; an empty list means the document conforms to 0.1.0-draft."""
    out = validate_structure(doc)
    if out:
        return out
    out.extend(_grant_rules(doc))
    out.extend(_chain_rules(doc))
    return out


def chain(doc: dict[str, Any], grant_id: str) -> list[str]:
    """Grant ids from the root grant down to ``grant_id`` (parent references followed; stops at a missing parent or a cycle)."""
    by_id = _first_by_id(doc)
    ids: list[str] = []
    cur: str | None = grant_id
    while cur is not None and cur in by_id and cur not in ids:
        ids.append(cur)
        cur = by_id[cur]["delegation"]["parent_grant_id"]
    return list(reversed(ids))


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
