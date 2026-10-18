"""Reference validator for the Freshness clocks contract (0.1.0-draft).

Stdlib only. A draft: it states the contract executably so each side of the boundary can be tested alone against golden
fixtures. It does not import or modify ``odes`` and does not edit the control-plane-journal, execution-attempt-lifecycle or
operation-identity contracts; it is an optional profile layered on them by reference.

Layers:

1. Structure: the JSON Schema subset interpreter (``schema.json`` is the source of truth for members, types, enumerations and the
   closed-member-set rule).
2. Rules: the document rules in README.md, read from the merged opt-in code (Control Plane ``freshness.py`` and ``bounded.py`` at
   3f6a7668, the N3 merge of #47; runtime ``engine/delayed_commit_destination.py`` at 6bfb77ee, #110).
3. Optional context, passed in by the caller and never re-validated here: ``journal`` (the run record, ``BoundedRunRecord`` as a
   dict) for the rules that join the sidecar to decisions, attempts, refusals, resolution checks, joins and operation rows, and
   ``host`` (host configuration that is in no record: the configured signer set, the declared age-extension limit, the resolver
   capability) for the rules that need it. A rule whose context is absent is skipped, never assumed.

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
CONTRACT = "freshness-clocks"
CONTRACT_VERSION = "0.1.0-draft"
PROFILE = "freshness/0.1"
#: A resolver that declares this capability implements ``nonce_read(nonce, method_name, *args) -> (record, echoed_nonce)``.
RESOLVER_CAPABILITY = "status-nonce/0.1"
#: A destination that declares this capability offers ``pause_at``, ``defer_next_commit`` and ``land`` (CI and local aid only).
DESTINATION_CAPABILITY = "delayed-commit/0.1"
DESTINATION_METHODS = ("pause_at", "defer_next_commit", "land")
#: The ten reason codes of the profile (registered in the Control Plane reason registry, 138 codes at main after N3).
CODE_EXPIRED = "check_expired_before_dispatch"
CODE_OVERDUE = "check_overdue"
CODE_LEASE = "check_lease_unavailable"
CODE_NONCE = "status_nonce_mismatch"
EXTENSION_CODES = ("age_extension_unsigned", "age_extension_self_signed", "age_extension_signer_not_configured",
                   "age_extension_exceeds_limit", "age_extension_invalid", "age_extension_authority_unconfigured")
REASON_CODES = (CODE_EXPIRED, CODE_OVERDUE, CODE_LEASE, CODE_NONCE) + EXTENSION_CODES
TERMINAL = {"completed", "interrupted", "expired"}
CLOCK_MEMBERS = ("deadline", "age_bound_seconds", "extension_id", "nonce")
EVENT_MEMBERS = ("check_id", "phase", "stage", "recorded_at", "evaluated_at", "deadline", "age_bound_seconds", "extension_id", "nonce",
                 "reasons")


@dataclass(frozen=True)
class Violation:
    code: str
    path: str
    message: str


# --------------------------------------------------------------------------- input hardening

class InputRefused(ValueError):
    """The input file is not a strict JSON document (duplicate member, non-finite number, bad encoding)."""


_TIME_SHAPE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T(?:[01][0-9]|2[0-3]):[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])")


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
    if "const" in schema and not (type(value) is type(schema["const"]) and value == schema["const"]):
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


def _v(code: str, path: str, message: str) -> Violation:
    return Violation(code, path, message)


def extension_shape_invalid(row: dict[str, Any]) -> bool:
    """The producer's ``age_extension_invalid`` test on values: the bound does not rise, or the window is empty or malformed."""
    nb, ex = aware(row["not_before"]), aware(row["expires_at"])
    if nb is None or ex is None:
        return True
    return row["to_max_age_seconds"] <= row["from_max_age_seconds"] or ex <= nb


def extension_defects(row: dict[str, Any], *, signers: Any = "absent", max_extension_seconds: int | None = None) -> list[str]:
    """Why an extension row does not count (the producer's ``extension_defects``), in the producer's order.

    ``signers`` is the rule-revision signer set: a list, ``None`` (profile not configured) or the string ``"absent"`` (not supplied:
    the authority rules are skipped). ``max_extension_seconds`` is the freshness profile's declared limit (``None``: not supplied).
    """
    out: list[str] = []
    if signers is None:
        out.append("age_extension_authority_unconfigured")
    if extension_shape_invalid(row):
        out.append("age_extension_invalid")
    elif max_extension_seconds is not None and row["to_max_age_seconds"] - row["from_max_age_seconds"] > max_extension_seconds:
        out.append("age_extension_exceeds_limit")
    if not row.get("signer"):
        out.append("age_extension_unsigned")
    elif row["signer"] == row["requested_by"]:
        out.append("age_extension_self_signed")
    elif isinstance(signers, list) and row["signer"] not in signers:
        out.append("age_extension_signer_not_configured")
    return out


def freshness_counts(check_events: list[dict[str, Any]], as_of: datetime) -> dict[str, Any]:
    """The counts of the producer's ``freshness.freshness_counts`` over journal check events (derivable from the sidecar's rows)."""
    by_check: dict[str, list[dict[str, Any]]] = {}
    for e in check_events:
        recorded = aware(e.get("recorded_at"))
        if recorded is not None and recorded > as_of:
            continue  # an event recorded after as_of is not visible to a report as of as_of (a report at the same instant sees it)
        by_check.setdefault(e["check_id"], []).append(e)
    open_ages: list[float] = []
    abandoned = expired = overdue = 0
    for events in by_check.values():
        opening = next((e for e in events if e["phase"] == "opened"), None)
        phases = {e["phase"] for e in events}
        abandoned += "interrupted" in phases
        expired += "expired" in phases
        if opening is None or phases & TERMINAL:
            continue
        deadline = aware(opening.get("deadline")) if opening.get("deadline") else None
        opened = aware(opening["recorded_at"])
        if deadline is not None and as_of > deadline:
            overdue += 1
        if opened is not None:
            open_ages.append((as_of - opened).total_seconds())
    return {"open_count": len(open_ages), "abandoned_open_count": abandoned, "overdue_count": overdue,
            "expired_before_dispatch_count": expired, "oldest_open_age_seconds": max(open_ages) if open_ages else None}


# --------------------------------------------------------------------------- time rules

def _time_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    stamps: list[tuple[str, Any]] = []
    for i, e in enumerate(doc["check_events"]):
        stamps += [(f"$.check_events[{i}].{k}", e[k]) for k in ("recorded_at", "evaluated_at", "deadline") if k in e]
    for i, r in enumerate(doc["clock_rows"]):
        stamps += [(f"$.clock_rows[{i}].{k}", r[k]) for k in ("recorded_at", "evaluated_at", "deadline") if k in r]
    for i, x in enumerate(doc["age_extensions"]):
        stamps += [(f"$.age_extensions[{i}].{k}", x[k]) for k in ("not_before", "expires_at", "recorded_at", "evaluated_at") if k in x]
    for i, x in enumerate(doc["age_extension_refusals"]):
        stamps.append((f"$.age_extension_refusals[{i}].recorded_at", x["recorded_at"]))
        stamps += [(f"$.age_extension_refusals[{i}].extension.{k}", x["extension"][k])
                   for k in ("not_before", "expires_at", "recorded_at", "evaluated_at") if k in x["extension"]]
    stamps += [(f"$.recovery_runs[{i}].recorded_at", x["recorded_at"]) for i, x in enumerate(doc["recovery_runs"])]
    stamps += [(f"$.freshness_reports[{i}].report.as_of", x["report"]["as_of"]) for i, x in enumerate(doc["freshness_reports"])]
    for path, value in stamps:
        if aware(value) is None:
            out.append(_v("timestamp_invalid", path, "times are timezone-aware ISO-8601"))
    if out:
        return out
    # recorded_at is the service clock at the write, evaluated_at the evaluation pass fixed before it: a row never records
    # itself before the pass that made it. Contract-only: the producer reads both clocks but compares neither.
    for name in ("check_events", "clock_rows", "age_extensions"):
        for i, r in enumerate(doc[name]):
            if "evaluated_at" in r and aware(r["recorded_at"]) < aware(r["evaluated_at"]):
                out.append(_v("recorded_before_evaluated", f"$.{name}[{i}]", "recorded_at does not precede evaluated_at"))
    return out


def _unique_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    for name, key, code in (("age_extensions", ("extension_id",), "duplicate_extension_id"),
                            ("age_extension_refusals", ("refusal_id",), "duplicate_extension_refusal_id"),
                            ("recovery_runs", ("run_id",), "duplicate_recovery_run_id"),
                            ("freshness_reports", ("report_id",), "duplicate_report_id"),
                            ("clock_rows", ("row_type", "row_id", "seq"), "duplicate_clock_row"),
                            ("input_reads", ("row_type", "row_id", "input_type", "input_id"), "duplicate_input_read")):
        seen: set[tuple] = set()
        for i, r in enumerate(doc[name]):
            k = tuple(r[m] for m in key)
            if k in seen:
                out.append(_v(code, f"$.{name}[{i}]", f"{'/'.join(key)} is unique within {name}"))
            seen.add(k)
    return out


# --------------------------------------------------------------------------- check journal rules

def _check_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    groups: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for i, e in enumerate(doc["check_events"]):
        groups.setdefault(e["check_id"], []).append((i, e))
    nonces: dict[str, str] = {}
    extensions = {x["extension_id"]: x for x in doc["age_extensions"]}
    for check_id, events in groups.items():
        first_i, opening = events[0]
        if opening["phase"] != "opened":
            out.append(_v("check_opening_missing", f"$.check_events[{first_i}]", "the first event of a check is its opening"))
            continue
        seen: list[str] = []
        previous = None
        for i, e in events:
            p, phase = f"$.check_events[{i}]", e["phase"]
            if phase == "opened" and seen:
                out.append(_v("duplicate_check_opening", p, "a check is opened once"))
            elif seen and any(s in TERMINAL for s in seen):
                if phase == "expired":
                    if any(s in {"interrupted", "expired"} for s in seen):
                        out.append(_v("expired_after_closed_check", p, "expired is allowed after completed, never after interrupted or expired"))
                else:
                    out.append(_v("check_event_after_close", p, "no event follows a terminal event, except expired after completed"))
            elif phase == "overdue" and "overdue" in seen:
                out.append(_v("overdue_repeated", p, "a check is reported overdue once"))
            seen.append(phase)
            if previous is not None and aware(e["recorded_at"]) < aware(previous["recorded_at"]):
                out.append(_v("check_event_time_regression", p, "recorded_at does not move backwards within a check"))
            previous = e
            if e is opening:
                continue
            for m in CLOCK_MEMBERS:
                if e.get(m) != opening.get(m):
                    out.append(_v("check_event_clock_drift", f"{p}.{m}", f"{m} is the opening's value on every later event of the check"))
            if "evaluated_at" in e and e["evaluated_at"] != opening.get("evaluated_at"):
                out.append(_v("check_event_clock_drift", f"{p}.evaluated_at", "evaluated_at, when present, is the opening's value"))
            if phase in {"overdue", "expired"}:
                want = [CODE_OVERDUE if phase == "overdue" else CODE_EXPIRED]
                if e["reasons"] != want:
                    out.append(_v("phase_reasons_mismatch", f"{p}.reasons", f"a {phase} event carries exactly {want[0]}"))
                if not opening.get("deadline"):
                    if phase == "overdue":
                        out.append(_v("overdue_without_deadline", p, "an overdue event needs a check opened with a deadline"))
                    else:
                        out.append(_v("expired_without_deadline", p, "an expired event needs a check opened with a deadline"))
                elif aware(e["recorded_at"]) <= aware(opening["deadline"]):
                    if phase == "overdue":
                        out.append(_v("overdue_before_deadline", p, "an overdue event is written after the deadline"))
                    else:
                        out.append(_v("expired_not_past_deadline", p, "an expired event is written after the deadline"))
        po = f"$.check_events[{first_i}]"
        if ("deadline" in opening) != ("age_bound_seconds" in opening):
            out.append(_v("deadline_members_incomplete", po, "deadline and age_bound_seconds are carried together or not at all"))
        elif "deadline" in opening and aware(opening["deadline"]) != _after(aware(opening["recorded_at"]), opening["age_bound_seconds"]):
            out.append(_v("deadline_mismatch", po, "deadline is the opening's recorded_at plus age_bound_seconds"))
        nonce = opening.get("nonce")
        if nonce is not None:
            if nonces.get(nonce, check_id) != check_id:
                out.append(_v("nonce_reused_across_checks", po, "a nonce belongs to one check"))
            nonces.setdefault(nonce, check_id)
        ext = opening.get("extension_id")
        if ext is not None:
            row = extensions.get(ext)
            if row is None:
                out.append(_v("extension_unknown", po, "an extension_id names an age_extensions row"))
                continue
            if opening.get("age_bound_seconds") != row["to_max_age_seconds"]:
                out.append(_v("extension_bound_mismatch", po, "age_bound_seconds is the extension's to_max_age_seconds"))
            evaluated = aware(opening.get("evaluated_at"))
            if evaluated is not None and not (aware(row["not_before"]) <= evaluated < aware(row["expires_at"])):
                out.append(_v("extension_outside_window", po, "the extension window covers the evaluation pass"))
            if aware(row["recorded_at"]) > aware(opening["recorded_at"]):
                out.append(_v("extension_recorded_after_use", po, "an extension recorded after the opening cannot have raised its bound"))
    return out


# --------------------------------------------------------------------------- extension rules

def _extension_rules(doc: dict[str, Any], host: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    signers = host.get("signers", "absent")
    limit = host.get("max_age_extension_seconds")
    for i, x in enumerate(doc["age_extensions"]):
        p = f"$.age_extensions[{i}]"
        if extension_shape_invalid(x):
            out.append(_v("accepted_extension_invalid", p, "an accepted extension raises the bound and has a non-empty window"))
        if not x["signer"]:
            out.append(_v("accepted_extension_unsigned", p, "an unsigned extension never counts; it is refused and kept as a refusal"))
        elif x["signer"] == x["requested_by"]:
            out.append(_v("accepted_extension_self_signed", p, "the signer is not the requester"))
        if limit is not None and not extension_shape_invalid(x) and x["to_max_age_seconds"] - x["from_max_age_seconds"] > limit:
            out.append(_v("accepted_extension_exceeds_limit", p, "an accepted extension does not exceed the declared limit"))
        if signers is None:
            out.append(_v("accepted_extension_authority_unconfigured", p, "no extension is accepted without a configured rule-revision signer set"))
    accepted_ids = {x["extension_id"] for x in doc["age_extensions"]}
    for i, r in enumerate(doc["age_extension_refusals"]):
        p = f"$.age_extension_refusals[{i}]"
        reasons, ext = r["reasons"], r["extension"]
        if reasons != sorted(set(reasons)):
            out.append(_v("extension_refusal_reasons_not_canonical", f"{p}.reasons", "reasons are sorted and unique"))
        if r["recorded_at"] != ext["recorded_at"]:
            out.append(_v("extension_refusal_time_mismatch", p, "a refusal is recorded at the extension's own recorded_at"))
        signer_set = signers if isinstance(signers, list) or signers is None else "absent"
        derived = set(extension_defects(ext, signers=signer_set, max_extension_seconds=limit))
        if ext["extension_id"] in accepted_ids:
            derived.add("age_extension_invalid")  # the producer refuses a reused id as invalid
        # Reasons that only host configuration can derive are checked when the host supplied it.
        checkable = {"age_extension_unsigned", "age_extension_self_signed", "age_extension_invalid"}
        if signers != "absent":
            checkable |= {"age_extension_authority_unconfigured", "age_extension_signer_not_configured"}
        if limit is not None:
            checkable.add("age_extension_exceeds_limit")
        if {c for c in reasons if c in checkable} != derived & checkable:
            out.append(_v("extension_refusal_reason_mismatch", f"{p}.reasons", "each reason names a defect the embedded extension shows"))
    return out


# --------------------------------------------------------------------------- recovery rules

def _recovery_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    events: dict[tuple[str, str], dict[str, Any]] = {}
    for e in doc["check_events"]:
        events.setdefault((e["check_id"], e["phase"]), e)
    for i, r in enumerate(doc["recovery_runs"]):
        p = f"$.recovery_runs[{i}]"
        if r["open_count"] < len(r["overdue"]):
            out.append(_v("recovery_run_open_count_below_overdue", p, "open_count includes every overdue check"))
        if (r["oldest_open_age_seconds"] is None) != (r["open_count"] == 0):
            out.append(_v("recovery_run_oldest_age_inconsistent", p, "oldest_open_age_seconds is null if and only if no check is open"))
        at = aware(r["recorded_at"])
        for cid in r["interrupted"]:
            e = events.get((cid, "interrupted"))
            if e is None or aware(e["recorded_at"]) != at:
                out.append(_v("recovery_interrupted_without_event", p, "each interrupted check has an interrupted event stamped with the pass time"))
        for cid in r["overdue"]:
            e = events.get((cid, "overdue"))
            if e is None or aware(e["recorded_at"]) > at:
                out.append(_v("recovery_overdue_without_event", p, "each overdue check has an overdue event written at or before the pass"))
    return out


# --------------------------------------------------------------------------- age basis rules

def _read_rules(doc: dict[str, Any], host: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    openings = {e["check_id"]: e for e in doc["check_events"] if e["phase"] == "opened"}
    capability_reported, no_nonce_reported = False, set()
    for i, x in enumerate(doc["input_reads"]):
        p = f"$.input_reads[{i}]"
        mismatch = x["read_state"] == "nonce_mismatch"
        if mismatch and x["age_basis"] != "source_asserted":
            out.append(_v("nonce_mismatch_basis", p, "a read whose echoed nonce differs is never nonce_bound"))
        both = x["expected_nonce"] is not None and x["observed_nonce"] is not None
        if mismatch != (both and x["expected_nonce"] != x["observed_nonce"]) or (not mismatch and (x["expected_nonce"] or x["observed_nonce"])):
            out.append(_v("nonce_members_inconsistent", p, "nonce_mismatch carries two different nonces; any other read carries none"))
        if x["age_basis"] == "nonce_bound" and host.get("resolver_capability", RESOLVER_CAPABILITY) != RESOLVER_CAPABILITY and not capability_reported:
            capability_reported = True  # one finding per document: the cause is the resolver, not each read
            out.append(_v("nonce_bound_without_capability", p, f"nonce_bound needs a resolver that declares {RESOLVER_CAPABILITY}"))
        cid = x["check_id"]
        if cid is None:
            continue
        opening = openings.get(cid)
        if opening is None:
            out.append(_v("input_read_check_unknown", p, "check_id names a check opened in check_events"))
        elif x["age_basis"] == "nonce_bound" and not opening.get("nonce"):
            if cid not in no_nonce_reported:  # one finding per check
                no_nonce_reported.add(cid)
                out.append(_v("nonce_bound_without_nonce", p, "a nonce_bound read belongs to a check that sent a nonce"))
        elif mismatch and x["expected_nonce"] != opening.get("nonce"):
            out.append(_v("nonce_expected_not_check_nonce", p, "the expected nonce is the nonce the check sent"))
    return out


def _report_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    for i, rep in enumerate(doc["freshness_reports"]):
        block = rep["report"]
        derived = freshness_counts(doc["check_events"], aware(block["as_of"]))
        if any(block[k] != derived[k] for k in derived):
            out.append(_v("freshness_counts_mismatch", f"$.freshness_reports[{i}].report",
                          "the counts are derived from the check events of this document as of as_of"))
    return out


# --------------------------------------------------------------------------- journal context (optional)

def _event_view(e: dict[str, Any]) -> dict[str, Any]:
    return {k: e[k] for k in EVENT_MEMBERS if k in e}


def expected_clock_rows(journal: dict[str, Any]) -> dict[tuple, dict[str, Any]]:
    """The clock rows the run record implies: rows that carry the profile's members, keyed (row_type, row_id, seq)."""
    rows: dict[tuple, dict[str, Any]] = {}

    def put(kind: str, row_id: str, seq: int, **members: Any) -> None:
        rows[(kind, row_id, seq)] = {k: v for k, v in members.items() if v is not None}
    for d in journal.get("decisions", []):
        if "recorded_at" in d:
            put("decision", d["decision_id"], 0, evaluated_at=d.get("evaluated_at"), recorded_at=d["recorded_at"])
    counts: dict[str, int] = {}
    for a in journal.get("attempts", []):
        seq = counts.get(a["attempt_id"], 0)
        counts[a["attempt_id"]] = seq + 1
        if "recorded_at" in a:
            put("attempt", a["attempt_id"], seq, evaluated_at=a.get("evaluated_at"), recorded_at=a["recorded_at"])
    for x in journal.get("refusals", []):
        if "evaluated_at" in x or "deadline" in x:
            put("refusal", x["refusal_id"], 0, evaluated_at=x.get("evaluated_at"), recorded_at=x["recorded_at"], deadline=x.get("deadline"))
    for c in journal.get("resolution_checks", []):
        if "recorded_at" in c:
            put("resolution_check", c["check_id"], 0, evaluated_at=c["evaluated_at"], recorded_at=c["recorded_at"])
    for j in journal.get("attempt_joins", []):
        if "evaluated_at" in j:
            put("attempt_join", j["join_id"], 0, evaluated_at=j["evaluated_at"], recorded_at=j["recorded_at"])
    for o in journal.get("operations", []):
        if "evaluated_at" in o:
            put("operation", o["operation_id"], 0, evaluated_at=o["evaluated_at"], recorded_at=o["admitted_at"])
    for r in journal.get("operation_renewals", []):
        if "evaluated_at" in r:
            put("operation_renewal", r["renewal_id"], 0, evaluated_at=r["evaluated_at"], recorded_at=r["recorded_at"])
    return rows


def expected_input_reads(journal: dict[str, Any]) -> dict[tuple, dict[str, Any]]:
    rows: dict[tuple, dict[str, Any]] = {}
    sources = [("decision", d["decision_id"], None, d["resolution_inputs"]) for d in journal.get("decisions", [])]
    sources += [("refusal", x["refusal_id"], x.get("check_id"), x["resolution_inputs"]) for x in journal.get("refusals", [])]
    sources += [("resolution_check", c["check_id"], c["check_id"], c["inputs"]) for c in journal.get("resolution_checks", [])]
    for kind, row_id, check_id, inputs in sources:
        for item in inputs:
            if item.get("age_basis") is None:
                continue
            mismatch = item.get("read_state") == "nonce_mismatch"
            rows[(kind, row_id, item["input_type"], item["input_id"])] = {
                "check_id": check_id, "age_basis": item["age_basis"], "read_state": item.get("read_state"),
                "expected_nonce": item["expected"].get("nonce") if mismatch else None,
                "observed_nonce": item["observed"].get("nonce") if mismatch else None}
    return rows


def _journal_rules(doc: dict[str, Any], journal: dict[str, Any], host: dict[str, Any]) -> list[Violation]:
    if journal.get("run_id") != doc["run_id"]:
        return [_v("journal_run_mismatch", "$.run_id", "the sidecar and the run record describe the same run")]
    out: list[Violation] = []
    if [_event_view(e) for e in journal.get("check_events", [])] != [_event_view(e) for e in doc["check_events"]]:
        out.append(_v("check_events_mismatch", "$.check_events", "the sidecar's check events are the run record's, member for member, in order"))
    for name in ("age_extensions", "age_extension_refusals", "recovery_runs"):
        if journal.get(name, []) != doc[name]:
            out.append(_v("profile_rows_mismatch", f"$.{name}", f"{name} are the run record's rows"))
    want = expected_clock_rows(journal)
    have: dict[tuple, int] = {}
    for i, r in enumerate(doc["clock_rows"]):
        key = (r["row_type"], r["row_id"], r["seq"])
        have[key] = i
        exp = want.get(key)
        if exp is None:
            out.append(_v("clock_row_unknown_row", f"$.clock_rows[{i}]", "a clock row names a row of the run record that carries the profile's members"))
        elif {k: r[k] for k in ("evaluated_at", "recorded_at", "deadline") if k in r} != exp:
            out.append(_v("clock_row_mismatch", f"$.clock_rows[{i}]", "the clock row is the row's evaluated_at, recorded_at and deadline"))
    for key in want:
        if key not in have:
            out.append(_v("clock_row_missing", "$.clock_rows", f"{key[0]} {key[1]} carries profile members and has no clock row"))
    want_reads = expected_input_reads(journal)
    seen_reads: set[tuple] = set()
    for i, x in enumerate(doc["input_reads"]):
        key = (x["row_type"], x["row_id"], x["input_type"], x["input_id"])
        seen_reads.add(key)
        exp = want_reads.get(key)
        if exp is None:
            out.append(_v("input_read_unknown_input", f"$.input_reads[{i}]", "an input read names an input of a row of the run record that carries age_basis"))
        elif {k: x[k] for k in exp} != exp:
            out.append(_v("input_read_mismatch", f"$.input_reads[{i}]", "the input read is the input's age_basis, read_state and nonces"))
    for key in want_reads:
        if key not in seen_reads:
            out.append(_v("input_read_missing", "$.input_reads", f"{key[0]} {key[1]} read {key[2]} {key[3]} with an age_basis and has no input read"))
    out.extend(_evaluation_alias_rules(journal))
    out.extend(_reason_rules(doc, journal, host))
    out.extend(_dispatch_rules(doc, journal))
    return out


def _evaluation_alias_rules(journal: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    for i, d in enumerate(journal.get("decisions", [])):
        if "evaluated_at" in d and d["evaluated_at"] != d["decided_at"]:
            out.append(_v("evaluation_alias_mismatch", f"$.decisions[{i}]", "decided_at keeps its evaluation-time meaning: it equals evaluated_at"))
    for i, a in enumerate(journal.get("attempts", [])):
        if "evaluated_at" in a and a["evaluated_at"] != a["started_at"]:
            out.append(_v("evaluation_alias_mismatch", f"$.attempts[{i}]", "started_at keeps its evaluation-time meaning: it equals evaluated_at"))
    return out


def _reason_rules(doc: dict[str, Any], journal: dict[str, Any], host: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    mismatched = lambda inputs: any(x.get("read_state") == "nonce_mismatch" for x in inputs)
    for name, key in (("decisions", "resolution_inputs"), ("refusals", "resolution_inputs"), ("resolution_checks", "inputs")):
        for i, r in enumerate(journal.get(name, [])):
            if (CODE_NONCE in r["reasons"]) != mismatched(r[key]):
                out.append(_v("nonce_reason_mismatch", f"$.{name}[{i}]",
                              f"{CODE_NONCE} is a reason if and only if an input read ended in nonce_mismatch"))
    for i, d in enumerate(journal.get("decisions", [])):
        if CODE_LEASE in d["reasons"]:
            if d["reasons"] != [CODE_LEASE]:
                out.append(_v("lease_unavailable_with_other_reasons", f"$.decisions[{i}]", f"{CODE_LEASE} is the only reason: no read happened"))
            if any(a["decision_id"] == d["decision_id"] for a in journal.get("attempts", [])):
                out.append(_v("lease_unavailable_dispatched", f"$.decisions[{i}]", f"a decision held for {CODE_LEASE} has no attempt"))
    expired_events = {e["check_id"]: e for e in doc["check_events"] if e["phase"] == "expired"}
    refusals = journal.get("refusals", [])
    refused_checks = {x.get("check_id"): x for x in refusals if CODE_EXPIRED in x["reasons"]}
    if set(expired_events) != set(refused_checks):
        out.append(_v("expired_refusal_mismatch", "$.refusals",
                      f"a check has an expired event if and only if a refusal row with {CODE_EXPIRED} names it (check_id)"))
    for cid, e in expired_events.items():
        x = refused_checks.get(cid)
        if x is not None and x.get("deadline") != e.get("deadline"):
            out.append(_v("expired_refusal_deadline_mismatch", "$.refusals", "the refusal's deadline is the check's deadline"))
        if x is not None and not any(a["effect_id"] == x["effect_id"] and a["status"] == "failed" and a.get("error") == CODE_EXPIRED
                                     for a in journal.get("attempts", [])):
            out.append(_v("expired_without_failed_attempt", "$.attempts", f"check {cid} expired and its attempt is not failed with {CODE_EXPIRED}"))
    for i, a in enumerate(journal.get("attempts", [])):
        if a.get("error") == CODE_EXPIRED:
            if a["status"] != "failed":
                out.append(_v("expired_attempt_not_failed", f"$.attempts[{i}]", f"{CODE_EXPIRED} is only the error of a failed attempt"))
            if not any(x["effect_id"] == a["effect_id"] and CODE_EXPIRED in x["reasons"] for x in refusals):
                out.append(_v("expired_attempt_without_refusal", f"$.attempts[{i}]", f"an attempt failed with {CODE_EXPIRED} has a refusal row for its effect"))
    signers = host.get("signers", "absent")
    if signers != "absent" or "max_age_extension_seconds" in host:
        for i, d in enumerate(journal.get("decisions", [])):
            at = aware(d.get("evaluated_at") or d["decided_at"])
            if at is None:
                continue
            active = [x for x in doc["age_extensions"] if aware(x["not_before"]) <= at < aware(x["expires_at"])]
            explained: set[str] = set()
            for x in active:
                explained |= set(extension_defects(x, signers=signers, max_extension_seconds=host.get("max_age_extension_seconds")))
            for code in d["reasons"]:
                if code in EXTENSION_CODES and code not in explained:
                    out.append(_v("extension_reason_unexplained", f"$.decisions[{i}]", f"{code} needs an extension active at the evaluation pass that shows it"))
    return out


def _dispatch_rules(doc: dict[str, Any], journal: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    latest: dict[str, dict[str, Any]] = {}
    for a in journal.get("attempts", []):
        latest[a["attempt_id"]] = a
    expired = {e["check_id"] for e in doc["check_events"] if e["phase"] == "expired"}
    for i, j in enumerate(journal.get("attempt_joins", [])):
        a = latest.get(j["attempt_id"])
        if j["check_id"] in expired and a is not None and a["status"] != "failed":
            out.append(_v("expired_check_dispatched", f"$.attempt_joins[{i}]", "a check whose licence expired at the gate licensed no dispatch"))
    # The journal contract's one-lifecycle rule (second_attempt_for_effect), with the profile's exclusion: an attempt refused at the
    # dispatch gate never reached the destination and does not count as a prior attempt.
    starts: dict[str, set[str]] = {}
    for a in journal.get("attempts", []):
        if a["status"] == "attempted":
            final = latest[a["attempt_id"]]
            if not (final["status"] == "failed" and final.get("error") == CODE_EXPIRED):
                starts.setdefault(a["effect_id"], set()).add(a["attempt_id"])
    for effect, ids in starts.items():
        if len(ids) > 1:
            out.append(_v("prior_attempt_not_excluded", "$.attempts", f"effect {effect} has more than one attempt lifecycle after excluding those refused with {CODE_EXPIRED}"))
    return out


_CONTEXT_ERRORS = (AttributeError, TypeError, KeyError, IndexError)


def _validate(doc: Any, journal: dict[str, Any] | None = None, host: dict[str, Any] | None = None) -> list[Violation]:
    """Return all violations; an empty list means the document conforms to 0.1.0-draft.

    ``journal`` is the optional run record for the cross-document rules; ``host`` is optional host configuration
    (``signers``: the rule-revision signer set or None when that profile is not configured, ``max_age_extension_seconds``,
    ``resolver_capability``: the declared capability or None) for the rules that need it.
    """
    out = validate_structure(doc)
    if out:
        return out
    host = host or {}
    out.extend(_time_rules(doc))
    if out:
        return out
    out.extend(_unique_rules(doc))
    out.extend(_check_rules(doc))
    try:
        out.extend(_extension_rules(doc, host))
        out.extend(_recovery_rules(doc))
        out.extend(_read_rules(doc, host))
        out.extend(_report_rules(doc))
        if journal is not None:
            out.extend(_journal_rules(doc, journal, host))
    except _CONTEXT_ERRORS:
        out.append(_v("context_malformed", "$", "an optional context argument (run record, host configuration or signer set) does not have the shape the cross-document rules need; it is refused, not assumed"))
    return out


LISTS = ("check_events", "clock_rows", "input_reads", "age_extensions", "age_extension_refusals", "recovery_runs")


def check_succession(earlier: dict[str, Any], later: dict[str, Any]) -> list[Violation]:
    """Two exports of one run: the row lists are append-only (an earlier list is a prefix of the later). Reports are recomputed."""
    if earlier["run_id"] != later["run_id"]:
        return [_v("not_append_only", "$.run_id", "successive exports describe one run")]
    return [_v("not_append_only", f"$.{name}", "an earlier row was changed, reordered or dropped")
            for name in LISTS if later[name][:len(earlier[name])] != earlier[name]]


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
        violations = validate(data["document"] if wrapped else data, data.get("journal") if wrapped else None, data.get("host") if wrapped else None)
        for v in violations:
            print(f"{name}: {v.code} {v.path}: {_printable(v.message)}")
        code |= bool(violations)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
