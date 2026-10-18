"""Reference validator for the Operation identity contract (0.1.0-draft).

Stdlib only. A draft: it states the contract executably so each side of the boundary can be tested alone
against golden fixtures. It does not import or modify ``odes`` and does not edit the control-plane-journal or
execution-attempt-lifecycle contracts; it is an optional profile layered on them by reference.

Layers:

1. Structure: the JSON Schema subset interpreter (``schema.json`` is the source of truth for members, types,
   enumerations and the closed-member-set rule).
2. Rules: the cross-record rules in README.md, read from the merged opt-in code (Control Plane
   ``operation_identity.py`` and ``bounded.py`` at main 83b49b5 which contains #45 at 9d00f38; runtime
   ``engine/operation_admission.py`` and ``engine/operation_identity_destination.py`` at 63a7c0fe2).
3. Journal context: an optional second argument, the run record (``BoundedRunRecord`` as a dict), for the rules
   that join the ledger to decisions, attempts, journal check events, resolution checks and refusals. The run
   record is NOT re-validated here; note the journal contract at 0.1.0-draft refuses a run record that carries
   the opt-in members (``undeclared_member``), so this profile is carried as a sidecar projection.

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
CONTRACT = "operation-identity"
CONTRACT_VERSION = "0.1.0-draft"
PROFILE = "operation-identity/0.1"
#: The capability string a destination declares before the Control Plane dispatches an operation id.
DESTINATION_CAPABILITY = "operation-identity/0.1"
#: The definitive destination rejection for a second effect under one operation id.
DESTINATION_REJECTION = "operation_already_committed"
#: The seven reason codes of the profile (registered in the Control Plane registry, 128 codes at main).
REASON_CODES = (
    "operation_id_missing", "operation_id_invalid", "operation_grant_mismatch", "operation_renewal_unrecorded",
    "operation_not_admitted", "renewal_not_written_by_grant_issuer", "renewal_revision_not_new",
)
OPERATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/#-]{0,127}")
COMMITTED = {"acknowledged", "partial"}          # attempt statuses that prove the destination committed the effect
POSSIBLY_COMMITTED = COMMITTED | {"unknown"}     # statuses where the destination may have committed it


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


def valid_operation_id(value: Any) -> bool:
    """The Control Plane's ``valid_operation_id``: 1 to 128 characters, first alphanumeric, then ``[A-Za-z0-9._:/#-]``."""
    return isinstance(value, str) and OPERATION_ID.fullmatch(value) is not None


def _v(code: str, path: str, message: str) -> Violation:
    return Violation(code, path, message)


def licensed_revisions(doc: dict[str, Any], operation_id: str) -> set[str]:
    """Grant revisions that may license an operation: its first revision plus every accepted renewal (as in the producer)."""
    op = next((o for o in doc["operations"] if o["operation_id"] == operation_id), None)
    if op is None:
        return set()
    return {op["first_grant_revision"]} | {r["to_revision"] for r in doc["operation_renewals"]
                                           if r["operation_id"] == operation_id and r["outcome"] == "accepted"}


def operation_status(doc: dict[str, Any], *, operation_id: str, principal_id: str, authority_domain: str, issuer: str,
                     grant_id: str, grant_revision: str) -> str:
    """Read-only judgement of a binding against the ledger: ``ok``, ``not_admitted``, ``collision`` or ``renewal_unrecorded``.

    Same decision order as the Control Plane ``operation_status``; map to reason codes with ``STATUS_REASON``.
    """
    op = next((o for o in doc["operations"] if o["operation_id"] == operation_id), None)
    if op is None:
        return "not_admitted"
    if (op["principal_id"], op["authority_domain"], op["issuer"], op["grant_id"]) != (principal_id, authority_domain, issuer, grant_id):
        return "collision"
    if grant_revision not in licensed_revisions(doc, operation_id):
        return "renewal_unrecorded"
    return "ok"


STATUS_REASON = {"not_admitted": "operation_not_admitted", "collision": "operation_grant_mismatch",
                 "renewal_unrecorded": "operation_renewal_unrecorded"}


# --------------------------------------------------------------------------- document rules

def _document_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    ops: dict[str, dict[str, Any]] = {}
    for i, o in enumerate(doc["operations"]):
        p = f"$.operations[{i}]"
        if o["operation_id"] in ops:
            out.append(_v("duplicate_operation_id", p, "an operation is admitted once; later bindings are judged against its row"))
        ops.setdefault(o["operation_id"], o)
        if aware(o["admitted_at"]) is None:
            out.append(_v("timestamp_invalid", f"{p}.admitted_at", "times are timezone-aware"))

    # Renewals are replayed in list (append) order, as the producer writes them.
    licensed = {oid: {o["first_grant_revision"]} for oid, o in ops.items()}
    last_to = {oid: o["first_grant_revision"] for oid, o in ops.items()}
    renewal_ids: set[str] = set()
    for i, r in enumerate(doc["operation_renewals"]):
        p = f"$.operation_renewals[{i}]"
        if r["renewal_id"] in renewal_ids:
            out.append(_v("duplicate_renewal_id", p, "renewal ids are unique"))
        renewal_ids.add(r["renewal_id"])
        if aware(r["recorded_at"]) is None:
            out.append(_v("timestamp_invalid", f"{p}.recorded_at", "times are timezone-aware"))
        op = ops.get(r["operation_id"])
        derived = None
        if op is None:
            derived = "operation_not_admitted"
        elif r["written_by"] != op["issuer"]:
            derived = "renewal_not_written_by_grant_issuer"
        elif r["to_revision"] in licensed[r["operation_id"]]:
            derived = "renewal_revision_not_new"
        if (r["outcome"] == "accepted") != (r["refusal_code"] is None):
            out.append(_v("renewal_outcome_inconsistent", p, "outcome accepted if and only if refusal_code is null"))
            continue
        if op is None:
            if r["grant_id"] is not None or r["from_revision"] is not None:
                out.append(_v("renewal_context_mismatch", p, "a renewal of an unadmitted operation carries null grant_id and from_revision"))
        elif r["grant_id"] != op["grant_id"] or r["from_revision"] != last_to[r["operation_id"]]:
            out.append(_v("renewal_context_mismatch", p,
                          "grant_id is the operation's grant and from_revision the last accepted revision (else the first)"))
        if r["outcome"] == "accepted":
            if derived == "operation_not_admitted":
                out.append(_v("renewal_accepted_unadmitted_operation", p, "an accepted renewal names an admitted operation"))
            elif derived == "renewal_not_written_by_grant_issuer":
                out.append(_v("renewal_accepted_not_by_issuer", p, "only the issuer recorded at admission writes an accepted renewal"))
            elif derived == "renewal_revision_not_new":
                out.append(_v("renewal_accepted_revision_not_new", p, "an accepted renewal names a revision the operation does not already hold"))
            if op is not None:
                licensed[r["operation_id"]].add(r["to_revision"])
                last_to[r["operation_id"]] = r["to_revision"]
        elif derived is None:
            out.append(_v("renewal_refusal_unjustified", p, "a refused renewal states a defect the ledger does not show"))
        elif r["refusal_code"] != derived:
            out.append(_v("renewal_refusal_code_mismatch", p, f"the ledger gives {derived} (checked in the producer's order)"))

    join_ids: set[str] = set()
    attempt_ids: set[str] = set()
    check_ids: set[str] = set()
    for i, j in enumerate(doc["attempt_joins"]):
        p = f"$.attempt_joins[{i}]"
        if j["join_id"] in join_ids:
            out.append(_v("duplicate_join_id", p, "join ids are unique"))
        join_ids.add(j["join_id"])
        if j["attempt_id"] in attempt_ids:
            out.append(_v("duplicate_attempt_join", p, "one join row per attempt"))
        attempt_ids.add(j["attempt_id"])
        if j["check_id"] in check_ids:
            out.append(_v("duplicate_join_check_id", p, "a journal check licenses one attempt"))
        check_ids.add(j["check_id"])
        if aware(j["recorded_at"]) is None:
            out.append(_v("timestamp_invalid", f"{p}.recorded_at", "times are timezone-aware"))
        op = ops.get(j["operation_id"])
        if op is None:
            out.append(_v("join_operation_not_admitted", f"{p}.operation_id", "a join names an admitted operation"))
        else:
            if j["grant_id"] != op["grant_id"]:
                out.append(_v("join_grant_mismatch", f"{p}.grant_id", "the operation id is stable across revisions of one grant, not across grants"))
            if j["grant_revision"] not in licensed_revisions(doc, j["operation_id"]):
                out.append(_v("join_revision_unlicensed", f"{p}.grant_revision",
                              "the revision is the operation's first or one an accepted renewal names"))
        target = j["merged_into"]
        if target is not None:
            if target == j["operation_id"]:
                out.append(_v("merged_into_self", f"{p}.merged_into", "an operation is not merged into itself"))
            elif target not in ops:
                out.append(_v("merged_into_not_admitted", f"{p}.merged_into", "merged_into names an admitted operation id, never an attempt id"))
    return out


# --------------------------------------------------------------------------- journal context (optional)

def _journal_rules(doc: dict[str, Any], journal: dict[str, Any], require_profile: bool = False) -> list[Violation]:
    if journal.get("run_id") != doc["run_id"]:
        return [_v("journal_run_mismatch", "$.run_id", "the profile document and the run record describe the same run")]
    out: list[Violation] = []
    ops = {o["operation_id"]: o for o in doc["operations"]}
    # Decision 6: the ledger counts as "on" when it is non-empty. A consumer that knows the host selected the profile (the Control Plane
    # `RuntimeAuthorityProfile.operation_identity` setting) passes ``require_profile=True`` (decision 37): an empty ledger then no longer
    # exempts the run, so an authorized decision without an operation id, or an attempt without a join, is refused.
    profile_on = require_profile or bool(doc["operations"])
    decisions = {d["decision_id"]: d for d in journal.get("decisions", [])}
    events = journal.get("check_events", [])
    resolution = {(c["check_id"], c["stage"]) for c in journal.get("resolution_checks", [])}
    rows_by_attempt: dict[str, list[dict[str, Any]]] = {}
    for a in journal.get("attempts", []):
        rows_by_attempt.setdefault(a["attempt_id"], []).append(a)
    joins = {j["attempt_id"]: j for j in doc["attempt_joins"]}

    first_authorized: dict[str, dict[str, Any]] = {}
    for k, d in enumerate(journal.get("decisions", [])):
        binding = d.get("binding")
        if d.get("result") != "authorized" or not binding:
            continue
        p = f"journal.decisions[{k}]"
        ext = binding.get("runtime_authority") or {}
        oid = ext.get("operation_id")
        if oid is None:
            if profile_on:
                out.append(_v("decision_operation_id_missing", p, "under the profile an authorized binding carries the issuer's operation id"))
            continue
        op = ops.get(oid)
        if op is None:
            out.append(_v("decision_operation_unadmitted", p, "an authorized decision's operation id is in the ledger"))
            continue
        first_authorized.setdefault(oid, d)
        if ext.get("operation_issuer") != op["issuer"]:
            out.append(_v("operation_issuer_mismatch", p, "the binding names the issuer recorded at admission"))
        if binding.get("principal") != op["principal_id"] or binding.get("grant_id") != op["grant_id"]:
            out.append(_v("decision_operation_binding_mismatch", p, "principal and grant are the ones the operation was admitted under"))
        if binding.get("grant_revision") not in licensed_revisions(doc, oid):
            out.append(_v("decision_revision_unlicensed", p, "the binding's revision is the first or an accepted renewal"))
    for i, o in enumerate(doc["operations"]):
        d = first_authorized.get(o["operation_id"])
        if d is not None and d["binding"]["grant_revision"] != o["first_grant_revision"]:
            out.append(_v("first_revision_mismatch", f"$.operations[{i}]", "an operation is admitted on its first authorized decision, at that decision's revision"))

    for i, j in enumerate(doc["attempt_joins"]):
        p = f"$.attempt_joins[{i}]"
        rows = rows_by_attempt.get(j["attempt_id"])
        if not rows:
            out.append(_v("join_attempt_missing", p, "the join names an attempt of the run record"))
        elif any(r["effect_id"] != j["effect_id"] or r["decision_id"] != j["decision_id"] for r in rows):
            out.append(_v("join_attempt_mismatch", p, "the join's effect and decision are the attempt's"))
        d = decisions.get(j["decision_id"])
        if d is None:
            out.append(_v("join_decision_missing", p, "the join names a decision of the run record"))
        elif d.get("result") != "authorized" or not d.get("binding"):
            out.append(_v("join_decision_unauthorized", p, "an attempt follows an authorized decision"))
        else:
            binding = d["binding"]
            if (binding.get("runtime_authority") or {}).get("operation_id") != j["operation_id"]:
                out.append(_v("join_operation_mismatch", p, "the join's operation is the one the decision's binding carries"))
            if (binding.get("grant_id"), binding.get("grant_revision")) != (j["grant_id"], j["grant_revision"]):
                out.append(_v("join_binding_mismatch", p, "the join's grant id and revision are the binding's"))
            if d["effect_id"] != j["effect_id"]:
                out.append(_v("join_effect_mismatch", p, "the join's effect id is the decision's"))
        opened = [e for e in events if e["check_id"] == j["check_id"] and e["stage"] == "effect" and e["phase"] == "opened"]
        if not opened:
            out.append(_v("join_check_missing", p, "the join's check id opens an effect-stage check in the journal"))
        else:
            if opened[0].get("effect_id") != j["effect_id"] or opened[0].get("decision_id") != j["decision_id"]:
                out.append(_v("join_check_lineage", p, "the journal check names the join's effect and decision"))
            if not any(e["check_id"] == j["check_id"] and e["phase"] == "completed" for e in events):
                out.append(_v("join_check_not_completed", p, "a check that did not complete licenses no dispatch"))
        if (j["check_id"], "effect") not in resolution:
            out.append(_v("join_resolution_check_missing", p, "the same id names the effect-stage resolution check"))

    if profile_on:
        for aid in rows_by_attempt:
            if aid not in joins:
                out.append(_v("attempt_without_join", f"journal.attempts[{aid}]", "under the profile every attempt has its join row"))
        for k, c in enumerate(journal.get("resolution_checks", [])):
            if not any(e["check_id"] == c["check_id"] and e["stage"] == c["stage"] for e in events):
                out.append(_v("resolution_check_not_in_journal", f"journal.resolution_checks[{k}]",
                              "under the profile a resolution check carries the id of the journal check it was read in"))
    for k, x in enumerate(journal.get("refusals", [])):
        p = f"journal.refusals[{k}]"
        cid = x.get("check_id")
        if cid is None:
            if profile_on:
                out.append(_v("refusal_check_id_missing", p, "under the profile a refusal names the check that refused"))
            continue
        if (cid, "effect") not in resolution:
            out.append(_v("refusal_check_missing", p, "the refusal's check id names an effect-stage resolution check"))
        opened = [e for e in events if e["check_id"] == cid and e["stage"] == "effect" and e["phase"] == "opened"]
        if opened and (opened[0].get("effect_id") != x["effect_id"] or opened[0].get("decision_id") != x["decision_id"]):
            out.append(_v("refusal_check_lineage", p, "the journal check names the refusal's effect and decision"))

    # One effect per operation, and the destination's definitive rejection.
    effects_by_operation: dict[str, dict[str, set[str]]] = {}
    for aid, rows in rows_by_attempt.items():
        j = joins.get(aid)
        if j is not None:
            effects_by_operation.setdefault(j["operation_id"], {}).setdefault(rows[0]["effect_id"], set()).update(r["status"] for r in rows)
    for oid, by_effect in sorted(effects_by_operation.items()):
        if sum(bool(s & COMMITTED) for s in by_effect.values()) > 1:
            out.append(_v("operation_committed_twice", f"journal.attempts[{oid}]",
                          "two different effect ids both reached acknowledged or partial for one operation"))
    for aid, rows in rows_by_attempt.items():
        last = rows[-1]
        j = joins.get(aid)
        if last["status"] == "failed" and last.get("error") == DESTINATION_REJECTION and j is not None:
            peers = [s for eff, s in effects_by_operation.get(j["operation_id"], {}).items() if eff != last["effect_id"]]
            if not any(s & POSSIBLY_COMMITTED for s in peers):
                out.append(_v("rejection_without_committed_peer", f"journal.attempts[{aid}]",
                              "operation_already_committed needs another effect of the operation that was acknowledged, partial or unknown"))
    return out


def _validate(doc: Any, journal: dict[str, Any] | None = None, require_profile: bool = False) -> list[Violation]:
    """Return all violations; an empty list means the document conforms to 0.1.0-draft.

    ``journal`` is an optional run record (a dict with at least ``run_id``) for the cross-document rules. ``require_profile`` states that
    the host selected the profile, so an empty ledger does not switch the ledger-dependent rules off (decision 37).
    """
    out = validate_structure(doc)
    if out:
        return out
    out.extend(_document_rules(doc))
    if journal is not None:
        out.extend(_journal_rules(doc, journal, require_profile))
    return out


def check_succession(earlier: dict[str, Any], later: dict[str, Any]) -> list[Violation]:
    """Two exports of one run: every ledger list of the earlier export is a prefix of the later one (rows are appended, never edited)."""
    out: list[Violation] = []
    if earlier["run_id"] != later["run_id"]:
        return [_v("not_append_only", "$.run_id", "successive exports describe one run")]
    for name in ("operations", "operation_renewals", "attempt_joins"):
        if later[name][:len(earlier[name])] != earlier[name]:
            out.append(_v("not_append_only", f"$.{name}", "an earlier row was changed, reordered or dropped"))
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
        violations = validate(data["document"] if wrapped else data, data.get("journal") if wrapped else None)
        for v in violations:
            print(f"{name}: {v.code} {v.path}: {_printable(v.message)}")
        code |= bool(violations)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
