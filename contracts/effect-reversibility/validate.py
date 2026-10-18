"""Reference validator for the effect-reversibility extension profile (0.1.0-draft).

Stdlib only. A draft: it states the profile executably so each side can be tested alone against golden
fixtures. It does not import or modify ``odes`` and does not edit the control-plane-journal contract; it is an
optional profile layered on it. Optional context: a conforming journal run record (``journal``) and a conforming
bounded-deferral document (``deferrals``) for the cross-document rules. Neither is re-validated here.

Layers:

1. Structure: a minimal interpreter for the JSON Schema subset used by ``schema.json``.
2. Rules: class consistency, cached-snapshot acceptance, dispatch phases against open deferrals, lost
   acknowledgement classification (README.md).
3. Context (optional): rules that need the run record or the deferral document.

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
CONTRACT = "effect-reversibility"
CONTRACT_VERSION = "0.1.0-draft"
# The journal contract version this profile was reviewed against (tests pin it).
LAYERED_ON_JOURNAL_VERSION = "0.1.0-draft"
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
# Phases each effect class may use, and the phases at which an effect becomes observable to the counterparty.
CLASS_PHASES = {"stageable": {"stage", "commit"}, "stallable": {"start_stalled", "release_stalled"}, "blocking": {"send"}}
OBSERVABLE_PHASES = {"commit", "release_stalled", "send"}
# Lost acknowledgement of a phase: (classification, required_action).
LOST_ACK = {"stage": ("no_external_effect", "discard_staged"),
            "start_stalled": ("no_external_effect", "cancel_or_resume_stalled"),
            "commit": ("external_effect_possible", "reconcile_by_observation"),
            "release_stalled": ("external_effect_possible", "reconcile_by_observation"),
            "send": ("external_effect_possible", "reconcile_by_observation")}


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
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            out.append(Violation("schema_violation", path, "number below minimum"))
        if "maximum" in schema and value > schema["maximum"]:
            out.append(Violation("schema_violation", path, "number above maximum"))
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            out.append(Violation("schema_violation", path, "string shorter than minimum length"))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            out.append(Violation("schema_violation", path, "string longer than maximum length"))
        if "pattern" in schema and not _pattern_ok(schema["pattern"], value):
            out.append(Violation("schema_violation", path, f"string does not match {schema['pattern']}"))
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


def _v(code: str, path: str, message: str) -> Violation:
    return Violation(code, path, message)


def _profiles(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["class_id"]: c for c in doc["class_profiles"]}


def extract_class_profiles(journal: dict[str, Any]) -> list[dict[str, Any]]:
    """Action classes carrying the two x- members, taken from a journal run record's check events.

    The Control Plane's action class is an open object in the journal, so a producer that implements this profile
    can carry ``x-effect-class`` and ``x-reversibility`` there without any change to the journal contract.
    """
    seen: dict[str, dict[str, Any]] = {}
    for event in journal.get("check_events", []):
        cls = event.get("action_class") or {}
        if "x-effect-class" in cls and "x-reversibility" in cls and cls.get("class_id") not in seen:
            seen[cls["class_id"]] = cls
    return list(seen.values())


# --------------------------------------------------------------------------- rules

def _time_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []

    def need(value: Any, path: str) -> None:
        if value is not None and aware(value) is None:
            out.append(_v("timestamp_invalid", path, "times are ISO-8601 with a UTC offset"))

    for i, c in enumerate(doc["class_profiles"]):
        need(c["x-reversibility"]["reversible_until"], f"$.class_profiles[{i}].x-reversibility.reversible_until")
    for i, u in enumerate(doc.get("snapshot_uses", [])):
        p = f"$.snapshot_uses[{i}]"
        need(u["evaluated_at"], f"{p}.evaluated_at")
        if u["snapshot"] is not None:
            need(u["snapshot"]["observed_at"], f"{p}.snapshot.observed_at")
        if u["recorded_closure"] is not None:
            need(u["recorded_closure"]["closed_at"], f"{p}.recorded_closure.closed_at")
            need(u["recorded_closure"]["recorded_at"], f"{p}.recorded_closure.recorded_at")
    for i, d in enumerate(doc.get("dispatches", [])):
        need(d["dispatched_at"], f"$.dispatches[{i}].dispatched_at")
    return out


def _identity_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    seen: set[str] = set()
    for i, c in enumerate(doc["class_profiles"]):
        if c["class_id"] in seen:
            out.append(_v("duplicate_class_id", f"$.class_profiles[{i}]", "class ids are unique"))
        seen.add(c["class_id"])
    for section, key in (("snapshot_uses", "use_id"), ("dispatches", "dispatch_id"), ("lost_acks", "lost_ack_id")):
        ids: set[str] = set()
        for i, row in enumerate(doc.get(section, [])):
            if row[key] in ids:
                out.append(_v("duplicate_record_id", f"$.{section}[{i}]", f"{key} values are unique within {section}"))
            ids.add(row[key])
    return out


def _class_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    for i, c in enumerate(doc["class_profiles"]):
        p = f"$.class_profiles[{i}]"
        r = c["x-reversibility"]
        value = r["reversibility"]
        if (r["reversible_until"] is not None) != (value == "reversible_until") or (r["reversal_cost"] is not None) != (value == "reversible_at_cost"):
            out.append(_v("reversibility_member_mismatch", f"{p}.x-reversibility",
                          "reversible_until is set if and only if reversibility is 'reversible_until'; reversal_cost if and only if 'reversible_at_cost'"))
        if c["irreversible"] != (value == "irreversible"):
            out.append(_v("irreversible_flag_mismatch", p,
                          "the action class's irreversible flag is true if and only if reversibility is 'irreversible'"))
        if r["reads_protected_data"] and value != "irreversible":
            out.append(_v("protected_read_not_irreversible", f"{p}.x-reversibility",
                          "a read of protected data cannot be taken back: reversibility is 'irreversible'"))
        if not r["counterparty_observable"] and value != "irreversible":
            out.append(_v("unobservable_not_strict", f"{p}.x-reversibility",
                          "where the counterparty condition is unobservable the stricter value applies: 'irreversible'"))
    return out


def _reference_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    classes = _profiles(doc)
    for section, key in (("snapshot_uses", None), ("dispatches", "effect_class"), ("lost_acks", "effect_class")):
        for i, row in enumerate(doc.get(section, [])):
            cls = classes.get(row["class_id"])
            p = f"$.{section}[{i}]"
            if cls is None:
                out.append(_v("dangling_class_reference", p, "class_id names no class profile in this document"))
            elif key is not None and row[key] != cls["x-effect-class"]:
                out.append(_v("class_profile_mismatch", p, "effect_class is the class profile's x-effect-class"))
    return out


def _snapshot_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    classes = _profiles(doc)
    for i, u in enumerate(doc.get("snapshot_uses", [])):
        p = f"$.snapshot_uses[{i}]"
        cls = classes.get(u["class_id"])
        when = aware(u["evaluated_at"])
        if cls is None or when is None:
            continue
        snap, basis = u["snapshot"], u["basis"]
        if (snap is None) != (basis == "strict_default"):
            out.append(_v("snapshot_basis_mismatch", p, "live_read and cached_snapshot carry a snapshot; strict_default carries none"))
            continue
        if basis == "strict_default":
            if u["effective_status"] != "closed":
                out.append(_v("strict_default_not_closed", p, "the strict default is 'closed' (fail closed)"))
            continue
        observed = aware(snap["observed_at"])
        if observed is None:
            continue
        rev = cls["x-reversibility"]
        if observed > when:
            out.append(_v("snapshot_time_invalid", f"{p}.snapshot.observed_at", "a snapshot cannot be observed after it is used"))
            continue
        if basis == "cached_snapshot":
            until = aware(rev["reversible_until"]) if rev["reversible_until"] is not None else None
            if rev["reversibility"] == "irreversible":
                out.append(_v("cache_on_irreversible_class", p, "a cached snapshot is accepted only for reversible classes; irreversible effects need a live read"))
                continue
            if until is not None and when >= until:
                out.append(_v("cache_after_reversal_window", p, "the reversal window has closed: the class is treated as irreversible, no cache"))
                continue
            limit = _after(observed, cls["max_status_age_seconds"])
            if limit is None:
                out.append(_v("snapshot_stale", p, "the class max_status_age_seconds is outside the supported range, so freshness cannot be established"))
                continue
            if when > limit:
                out.append(_v("snapshot_stale", p, "a cached snapshot is accepted only within the class max_status_age_seconds"))
                continue
        closure = u["recorded_closure"]
        if closure is not None and u["effective_status"] == "open":
            recorded = aware(closure["recorded_at"])
            if recorded is not None and recorded <= when:
                out.append(_v("recorded_closure_overridden", p, "a recorded closure overrides any snapshot, cached or live"))
                continue
        if u["effective_status"] == "open" and snap["status"] != "open":
            out.append(_v("effective_status_unsupported", p, "effective 'open' needs a snapshot that says open; closed or unknown is treated as closed"))
    return out


def _open_at_dispatch(dispatch: dict[str, Any]) -> bool:
    return bool(dispatch["open_deferral_ids"])


def _dispatch_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    for i, d in enumerate(doc.get("dispatches", [])):
        p = f"$.dispatches[{i}]"
        if d["phase"] not in CLASS_PHASES[d["effect_class"]]:
            out.append(_v("phase_class_mismatch", p, f"a {d['effect_class']} effect uses phases {sorted(CLASS_PHASES[d['effect_class']])}"))
            continue
        if _open_at_dispatch(d):
            if d["effect_class"] == "blocking":
                out.append(_v("blocking_sent_while_deferred", p, "a blocking effect is never sent while a DEFER is open"))
            elif d["phase"] in OBSERVABLE_PHASES:
                out.append(_v("observable_while_deferred", p, "while a DEFER is open a stageable effect may only be staged and a stallable one only started stalled"))
    return out


def _lost_ack_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    classes = _profiles(doc)
    for i, a in enumerate(doc.get("lost_acks", [])):
        p = f"$.lost_acks[{i}]"
        if a["lost_phase"] not in CLASS_PHASES[a["effect_class"]]:
            out.append(_v("phase_class_mismatch", p, f"a {a['effect_class']} effect uses phases {sorted(CLASS_PHASES[a['effect_class']])}"))
            continue
        if (a["classification"], a["required_action"]) != LOST_ACK[a["lost_phase"]]:
            out.append(_v("lost_ack_misclassified", p,
                          f"a lost acknowledgement of '{a['lost_phase']}' is {LOST_ACK[a['lost_phase']][0]} and requires {LOST_ACK[a['lost_phase']][1]}"))
            continue
        cls = classes.get(a["class_id"])
        if a["reversal_available"] and cls is not None and cls["x-reversibility"]["reversibility"] == "irreversible":
            out.append(_v("reversal_claimed_for_irreversible", p, "an irreversible class has no reversal to offer"))
    return out


# --------------------------------------------------------------------------- context (optional)

def check_against_context(doc: dict[str, Any], journal: dict[str, Any] | None, deferrals: dict[str, Any] | None) -> list[Violation]:
    """Rules that need the run record and/or the bounded-deferral document."""
    out: list[Violation] = []
    classes = _profiles(doc)
    if deferrals is not None:
        for other, what in ((doc.get("run_id"), "the profile document"), (journal.get("run_id") if journal is not None else None, "the run record")):
            if other is not None and deferrals.get("run_id") != other:
                return [_v("journal_run_mismatch", "$.run_id", f"{what} and the bounded-deferral document describe the same run")]
    if journal is not None:
        if doc.get("run_id") is not None and journal.get("run_id") != doc["run_id"]:
            return [_v("journal_run_mismatch", "$.run_id", "the profile document and the run record describe the same run")]
        for i, c in enumerate(doc["class_profiles"]):
            for event in journal.get("check_events", []):
                cls = event.get("action_class") or {}
                if cls.get("class_id") == c["class_id"] and (
                        cls.get("irreversible") != c["irreversible"] or cls.get("max_status_age_seconds") != c["max_status_age_seconds"]):
                    out.append(_v("class_profile_journal_mismatch", f"$.class_profiles[{i}]",
                                  "irreversible and max_status_age_seconds equal the action class recorded in the run record"))
                    break
        rows: dict[str, list[dict[str, Any]]] = {}
        for a in journal["attempts"]:
            rows.setdefault(a["attempt_id"], []).append(a)
        for i, a in enumerate(doc.get("lost_acks", [])):
            history = rows.get(a["attempt_id"], [])
            if not history or history[-1]["status"] != "unknown" or history[-1]["effect_id"] != a["effect_id"]:
                out.append(_v("lost_ack_attempt_mismatch", f"$.lost_acks[{i}]",
                              "a lost acknowledgement names an attempt of that effect whose last row is 'unknown'"))
    if deferrals is not None:
        for i, d in enumerate(doc.get("dispatches", [])):
            when = aware(d["dispatched_at"])
            if when is None:
                continue
            computed = set()
            for x in deferrals["deferrals"]:
                opened = aware(x["opened_at"])
                resolved = aware(x["resolved_at"]) if x["resolved_at"] is not None else None
                if x["proposal_commitment"] == d["proposal_commitment"] and opened is not None and opened <= when \
                        and (resolved is None or when < resolved):
                    computed.add(x["deferral_id"])
            if computed != set(d["open_deferral_ids"]):
                out.append(_v("open_deferral_mismatch", f"$.dispatches[{i}].open_deferral_ids",
                              "the deferrals open at dispatch time (same proposal commitment, opened and not yet resolved) are exactly the ones listed"))
    return out


_CONTEXT_ERRORS = (AttributeError, TypeError, KeyError, IndexError, ValueError, RecursionError)


def _validate(doc: Any, journal: dict[str, Any] | None = None, deferrals: dict[str, Any] | None = None) -> list[Violation]:
    """Return all violations; an empty list means the document conforms to 0.1.0-draft."""
    out = validate_structure(doc)
    if out:
        return out
    for rule in (_time_rules, _identity_rules, _class_rules, _reference_rules, _snapshot_rules, _dispatch_rules, _lost_ack_rules):
        out.extend(rule(doc))
    if journal is not None or deferrals is not None:
        try:
            out.extend(check_against_context(doc, journal, deferrals))
        except _CONTEXT_ERRORS:
            out.append(_v("context_malformed", "$", "the optional run record and deferral document are checked for shape, not assumed to conform"))
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
