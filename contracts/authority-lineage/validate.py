"""Reference validator for the Authority lineage contract (0.1.0-draft).

Stdlib only. A draft: it states the contract executably so each side of the boundary can be tested alone
against golden fixtures. It does not import or modify ``odes``.

Layers:

1. Structure: the JSON Schema subset interpreter.
2. Rules: the hop and continuity rules in README.md. A hop is hash-linked to the previous hop: ``previous_hash`` is that hop's
   ``hop_hash`` and ``hop_hash`` is the commitment (SHA-256 over sorted compact UTF-8 JSON, the Control Plane commitment form)
   of ``{hop_id, kind, subject_ref, previous_hop_id, previous_hash, content_digest}``. ``content_digest`` is the producer's
   digest of the record the hop stands for (a grant, a delegation record, an effect); it is not verifiable at this boundary.

The record layers on the grant shape (``non-broadening-delegation``) and on the Control Plane ``effect_id`` by reference only.

``validate`` returns a list of ``Violation`` (empty list means conformant). Refusal codes are stable strings.
The structural interpreter is the one used by the other drafts (JSON Schema subset, plus ``minimum`` and ``minItems``).
"""
from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "schema.json"
CONTRACT = "authority-lineage"
CONTRACT_VERSION = "0.1.0-draft"
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class Violation:
    code: str
    path: str
    message: str


# --------------------------------------------------------------------------- input hardening

class InputRefused(ValueError):
    """The input file is not a strict JSON document (duplicate member, non-finite number, bad encoding)."""


_TIME_SHAPE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])")


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
        if "pattern" in schema and not _pattern_ok(schema["pattern"], value):
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
    if _TIME_SHAPE.fullmatch(value) is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
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


def hop_hash(hop: dict[str, Any]) -> str:
    """The hop's own hash: commitment over its identity, its link to the previous hop and its content digest."""
    return commitment({"hop_id": hop["hop_id"], "kind": hop["kind"], "subject_ref": hop["subject_ref"],
                       "previous_hop_id": hop["previous_hop_id"], "previous_hash": hop["previous_hash"],
                       "content_digest": hop["content_digest"]})


def _first(doc: dict[str, Any]) -> dict[str, tuple[int, dict[str, Any]]]:
    first: dict[str, tuple[int, dict[str, Any]]] = {}
    for i, h in enumerate(doc["hops"]):
        first.setdefault(h["hop_id"], (i, h))
    return first


def _hop_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    first = _first(doc)
    seen: set[str] = set()
    for i, h in enumerate(doc["hops"]):
        p = f"$.hops[{i}]"
        if h["hop_id"] in seen:
            out.append(_v("duplicate_hop_id", p, "hop ids are unique"))
        seen.add(h["hop_id"])
        if (h["previous_hop_id"] is None) != (h["previous_hash"] is None):
            out.append(_v("previous_incomplete", p, "previous_hop_id and previous_hash are both null or both set"))
        if h["hop_hash"] != hop_hash(h):
            out.append(_v("hop_hash_mismatch", f"{p}.hop_hash", "hop_hash is the commitment of the hop's identity, link and content digest"))
        if h["kind"] == "grant" and h["previous_hop_id"] is not None:
            out.append(_v("grant_has_previous", p, "a grant hop is the origin of a lineage and links to nothing"))
            continue
        prev = first.get(h["previous_hop_id"]) if h["previous_hop_id"] is not None else None
        if prev is not None:
            j, ph = prev
            if j >= i:
                out.append(_v("previous_not_earlier", p, "the previous hop appears earlier in the list (append-only order)"))
            elif ph["kind"] == "effect":
                out.append(_v("previous_kind_invalid", p, "an effect is terminal: no hop links to it"))
    return out


def find_break(doc: dict[str, Any], hop_id: str) -> tuple[str, str] | None:
    """Walk the previous links from a hop. None when the walk reaches a grant hop through intact links.

    Otherwise ``(break_hop_id, reason)`` for the first hop whose link fails: ``previous_missing`` (the named previous
    hop is not in the document), ``previous_hash_mismatch`` (its hop_hash differs from the recorded previous_hash) or
    ``no_origin`` (a delegation or effect hop with no previous, or a walk that does not end at a grant).
    """
    first = _first(doc)
    cur = first[hop_id][1]
    seen: set[str] = set()
    while True:
        if cur["hop_id"] in seen:
            return cur["hop_id"], "no_origin"
        seen.add(cur["hop_id"])
        pid = cur["previous_hop_id"]
        if pid is None:
            return None if cur["kind"] == "grant" else (cur["hop_id"], "no_origin")
        nxt = first.get(pid)
        if nxt is None:
            return cur["hop_id"], "previous_missing"
        if cur["previous_hash"] != nxt[1]["hop_hash"]:
            return cur["hop_id"], "previous_hash_mismatch"
        cur = nxt[1]


def unresolved_effects(doc: dict[str, Any]) -> list[str]:
    """Effect hop ids that do not resolve to a grant (the ones that must carry a lineage_discontinuity flag)."""
    return [h["hop_id"] for h in doc["hops"] if h["kind"] == "effect" and find_break(doc, h["hop_id"]) is not None]


def _continuity_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    first = _first(doc)
    flagged: set[str] = set()
    for i, f in enumerate(doc["lineage_discontinuities"]):
        p = f"$.lineage_discontinuities[{i}]"
        target = first.get(f["effect_hop_id"])
        if target is None or target[1]["kind"] != "effect":
            out.append(_v("discontinuity_flag_dangling", p, "a flag names an effect hop in the document"))
            continue
        if f["effect_hop_id"] in flagged:
            out.append(_v("duplicate_discontinuity_flag", p, "one flag per effect"))
            continue
        flagged.add(f["effect_hop_id"])
        found = find_break(doc, f["effect_hop_id"])
        if found is None:
            out.append(_v("discontinuity_flag_false", p, "the effect resolves to a grant; it is not discontinuous"))
        elif found != (f["break_hop_id"], f["reason"]):
            out.append(_v("discontinuity_flag_mismatch", p, f"the first break is hop {found[0]!r} with reason {found[1]!r}"))
    for i, h in enumerate(doc["hops"]):
        if h["kind"] == "effect" and h["hop_id"] not in flagged and find_break(doc, h["hop_id"]) is not None:
            out.append(_v("lineage_discontinuity_unflagged", f"$.hops[{i}]",
                          "an effect that does not resolve to a grant carries a lineage_discontinuity flag"))
    return out


def _validate(doc: Any) -> list[Violation]:
    """Return all violations; an empty list means the document conforms to 0.1.0-draft."""
    out = validate_structure(doc)
    if out:
        return out
    out.extend(_hop_rules(doc))
    out.extend(_continuity_rules(doc))
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
