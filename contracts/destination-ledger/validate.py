"""Reference validator for the Destination ledger contract (0.1.0-draft).

Stdlib only. A draft: it states executably the closed row shape the independent verifier hard-codes
(``cognous_verify/ledger.py``, ``ROW_MEMBERS``, finding ``ledger_shape``) and the two producers emit, so each side of the boundary
can be tested alone against golden fixtures. It does not import or modify ``odes``.

Layers:

1. Structure: the JSON Schema subset interpreter (``schema.json`` is the source of truth for members, types and the closed-member-set
   rule). The export has no in-band contract marker, so there is no ``unsupported_contract_version`` here.
2. Document rules: the two self-consistency rules a single export can break (a row is keyed by its own ``effect_id``; the per-grant
   counts equal the rows per grant).
3. Observation context (optional second argument): destination states from accepted observations, for the ``operation_digest``
   cross-check of decision 25-A.

``validate`` returns a list of ``Violation`` (empty list means conformant). Refusal codes are stable strings.
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
CONTRACT = "destination-ledger"
CONTRACT_VERSION = "0.1.0-draft"
#: The documented default format of ``operation_digest`` (the runtime emits ``"sha256:" + lowercase hex``).
OPERATION_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


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
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(value, n) for n in names):
            out.append(Violation("schema_violation", path, f"expected type {'|'.join(names)}"))
            return
    if isinstance(value, str):
        # The length bounds also close the gap between `$` in Python (matches before a trailing newline) and in JSON Schema.
        if (("minLength" in schema and len(value) < schema["minLength"])
                or ("maxLength" in schema and len(value) > schema["maxLength"])
                or ("pattern" in schema and not _pattern_ok(schema["pattern"], value))):
            out.append(Violation("schema_violation", path, "string does not match its declared form"))
    if isinstance(value, (int, float)) and not isinstance(value, bool) and "minimum" in schema and value < schema["minimum"]:
        out.append(Violation("schema_violation", path, "number below minimum"))
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                out.append(Violation("schema_violation", f"{path}.{name}", "required member missing"))
        extra = schema.get("additionalProperties", True)
        for name, member in value.items():
            where = f"{path}.{name}" if name.isidentifier() else f"{path}[{name!r}]"
            if name in props:
                _check(member, props[name], root, where, out)
            elif extra is False:
                out.append(Violation("undeclared_member", where,
                                     "member is neither declared nor inside the extensions namespace"))
            elif isinstance(extra, dict):
                _check(member, extra, root, where, out)
        names_schema = schema.get("propertyNames")
        if names_schema is not None:
            for name in value:
                if not _pattern_ok(names_schema["pattern"], name):
                    out.append(Violation("invalid_extension_key", f"{path}.{name}",
                                         "extension member names must match the reserved x- form"))


def validate_structure(doc: Any) -> list[Violation]:
    schema = load_schema()
    out: list[Violation] = []
    _check(doc, schema, schema, "$", out)
    return out


# --------------------------------------------------------------------------- rules

def _v(code: str, path: str, message: str) -> Violation:
    return Violation(code, path, message)


def _document_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    rows = doc["effects"]
    per_grant: dict[str, int] = {}
    for key, row in rows.items():
        if row["effect_id"] != key:
            out.append(_v("ledger_key_mismatch", f"$.effects[{key!r}]", "a ledger row is keyed by its own effect_id"))
        per_grant[row["grant_id"]] = per_grant.get(row["grant_id"], 0) + 1
    counts = doc["grant_effect_counts"]
    for grant in sorted(set(per_grant) | set(counts)):
        if counts.get(grant, 0) != per_grant.get(grant, 0):
            out.append(_v("ledger_count_mismatch", f"$.grant_effect_counts[{grant!r}]",
                          f"the count says {counts.get(grant, 0)}, the rows say {per_grant.get(grant, 0)}"))
    return out


def destination_states(context: Any) -> list[dict[str, Any]]:
    """Accepted observed destination states from a run record (``reconciliations``) or an already extracted list."""
    if isinstance(context, dict):
        context = context.get("reconciliations", [])
    states: list[dict[str, Any]] = []
    for item in context or []:
        if not isinstance(item, dict):
            continue
        obs = item.get("observation") if "observation" in item else item
        if "observation_accepted" in item and item["observation_accepted"] is not True:
            continue
        if isinstance(obs, dict) and isinstance(obs.get("destination_state"), dict):
            states.append({"effect_id": obs.get("effect_id"), **obs["destination_state"]})
    return states


def _observation_rules(doc: dict[str, Any], context: Any) -> list[Violation]:
    """Decision 25-A: if a row and an accepted observation's destination_state both carry operation_digest they agree."""
    out: list[Violation] = []
    for state in destination_states(context):
        row = doc["effects"].get(state.get("effect_id"))
        if row is None or "operation_digest" not in row or "operation_digest" not in state:
            continue
        if row["operation_digest"] != state["operation_digest"] and not any(
                v.path == f"$.effects[{state['effect_id']!r}].operation_digest" for v in out):
            out.append(_v("operation_digest_mismatch", f"$.effects[{state['effect_id']!r}].operation_digest",
                          "the row and the accepted observation's destination_state carry different operation_digest values"))
    return out


def _validate(doc: Any, observations: Any = None) -> list[Violation]:
    """Return all violations; an empty list means the document conforms to 0.1.0-draft.

    ``observations`` is optional: a run record (a dict with ``reconciliations``) or a list of accepted observation records, for the
    ``operation_digest`` cross-check.
    """
    out = validate_structure(doc)
    if out:
        return out
    out.extend(_document_rules(doc))
    if observations is not None:
        out.extend(_observation_rules(doc, observations))
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
        violations = validate(data["document"] if wrapped else data, data.get("observations") if wrapped else None)
        for v in violations:
            print(f"{name}: {v.code} {v.path}: {_printable(v.message)}")
        code |= bool(violations)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
