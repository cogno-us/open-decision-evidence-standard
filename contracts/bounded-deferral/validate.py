"""Reference validator for the bounded-deferral extension profile (0.1.0-draft).

Stdlib only. A draft: it states the profile executably so each side can be tested alone against golden
fixtures. It does not import or modify ``odes`` and does not edit the control-plane-journal contract; it is an
optional profile layered on it. A conforming journal run record may be passed as ``journal`` to check the
cross-document rules (the journal is assumed to conform on its own; this validator does not re-validate it).

Layers:

1. Structure: a minimal interpreter for the JSON Schema subset used by ``schema.json``.
2. Rules: the deferral rules in README.md (deadline derivation, fail-closed resolution, no release of a policy
   refusal, no effect before release, refusal notice).
3. Journal context (optional): rules that need the run record (held decision, class max age, attempts,
   observations).

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
CONTRACT = "bounded-deferral"
CONTRACT_VERSION = "0.1.0-draft"
# The journal contract version this profile was reviewed against (tests pin it).
LAYERED_ON_JOURNAL_VERSION = "0.1.0-draft"
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
FAILURE_KINDS = {"timeout": "resolver_timeout", "unparseable": "resolver_unparseable", "error": "resolver_error"}


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


# --------------------------------------------------------------------------- rules

def derive_outcome(deferral: dict[str, Any], evaluated_at: datetime) -> tuple[str, str | None]:
    """The only outcome the rules allow, as ``(outcome, refusal_reason)``.

    Fail closed: the policy verdict wins over any resolver; the first response decides (later ones are recorded and
    ignored); a failing, garbled or late response, or none by the deadline, is a refusal. Never a release by default.
    """
    if deferral["policy"]["policy_verdict"] == "refuse":
        return "refused", "policy_refused"
    deadline = aware(deferral["deadline"])
    responses = sorted(deferral["responses"], key=lambda r: aware(r["received_at"]))
    if responses and aware(responses[0]["received_at"]) <= deadline:
        kind = responses[0]["kind"]
        if kind == "release":
            return "released", None
        return "refused", "resolver_refused" if kind == "refuse" else FAILURE_KINDS[kind]
    if evaluated_at > deadline or responses:
        return "refused", "deadline_expired"
    return "deferred", None


def _times(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    if aware(doc["evaluated_at"]) is None:
        out.append(_v("timestamp_invalid", "$.evaluated_at", "times are ISO-8601 with a UTC offset"))
    for i, d in enumerate(doc["deferrals"]):
        p = f"$.deferrals[{i}]"
        for member in ("opened_at", "deadline"):
            if aware(d[member]) is None:
                out.append(_v("timestamp_invalid", f"{p}.{member}", "times are ISO-8601 with a UTC offset"))
        if d["resolved_at"] is not None and aware(d["resolved_at"]) is None:
            out.append(_v("timestamp_invalid", f"{p}.resolved_at", "times are ISO-8601 with a UTC offset"))
        if d["effect"]["first_observable_at"] is not None and aware(d["effect"]["first_observable_at"]) is None:
            out.append(_v("timestamp_invalid", f"{p}.effect.first_observable_at", "times are ISO-8601 with a UTC offset"))
        for j, r in enumerate(d["responses"]):
            if aware(r["received_at"]) is None:
                out.append(_v("timestamp_invalid", f"{p}.responses[{j}].received_at", "times are ISO-8601 with a UTC offset"))
    return out


def _identity_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    ids: set[str] = set()
    decisions: set[str] = set()
    for i, d in enumerate(doc["deferrals"]):
        p = f"$.deferrals[{i}]"
        if d["deferral_id"] in ids:
            out.append(_v("duplicate_deferral_id", p, "deferral ids are unique"))
        ids.add(d["deferral_id"])
        if d["decision_id"] in decisions:
            out.append(_v("duplicate_deferral_for_decision", p, "a held decision has at most one deferral"))
        decisions.add(d["decision_id"])
    return out


def _policy_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    for i, d in enumerate(doc["deferrals"]):
        pol = d["policy"]
        deferrable = pol["policy_verdict"] == "defer"
        if deferrable != (not pol["refusal_reasons"]) or (deferrable and not pol["deferred_reasons"]):
            out.append(_v("policy_verdict_inconsistent", f"$.deferrals[{i}].policy",
                          "verdict 'defer' if and only if refusal_reasons is empty, and a deferral names at least one deferred reason"))
    return out


def _deadline_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    for i, d in enumerate(doc["deferrals"]):
        opened, deadline = aware(d["opened_at"]), aware(d["deadline"])
        if opened is None or deadline is None:
            continue
        if deadline != _after(opened, d["max_age_seconds"]):
            out.append(_v("deadline_mismatch", f"$.deferrals[{i}].deadline",
                          "the deadline is opened_at plus max_age_seconds (the action class max_status_age_seconds), never open-ended"))
        for j, r in enumerate(d["responses"]):
            got = aware(r["received_at"])
            if got is not None and got < opened:
                out.append(_v("response_before_opening", f"$.deferrals[{i}].responses[{j}]",
                              "a resolver response cannot precede the deferral it answers"))
    return out


def _outcome_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    evaluated = aware(doc["evaluated_at"])
    for i, d in enumerate(doc["deferrals"]):
        p = f"$.deferrals[{i}]"
        times = [aware(d["deadline"]), evaluated] + [aware(r["received_at"]) for r in d["responses"]]
        if any(t is None for t in times):
            continue
        outcome, reason = derive_outcome(d, evaluated)
        declared = d["outcome"]
        if declared != outcome:
            if declared == "released":
                code = {"policy_refused": "release_overrides_refusal", "deadline_expired": "expired_deferral_not_refused",
                        "resolver_refused": "refusal_overridden"}.get(reason, "resolver_failure_released")
            elif declared == "deferred" and reason == "deadline_expired":
                code = "expired_deferral_not_refused"
            else:
                code = "outcome_mismatch"
            out.append(_v(code, f"{p}.outcome", f"the rules derive outcome '{outcome}' ({reason}) from the policy verdict, the first response and the deadline"))
            continue
        if d["refusal_reason"] != reason:
            out.append(_v("refusal_reason_mismatch", f"{p}.refusal_reason",
                          f"refusal_reason is {reason!r} for this outcome (null unless refused)"))
        if (d["released_decision_id"] is not None) != (declared == "released"):
            out.append(_v("release_decision_inconsistent", f"{p}.released_decision_id",
                          "a released deferral names the decision taken after release; no other state does"))
        resolved = aware(d["resolved_at"]) if d["resolved_at"] is not None else None
        if declared == "deferred":
            ok = d["resolved_at"] is None
        elif reason == "deadline_expired":
            ok = resolved is not None and resolved >= aware(d["deadline"])
        elif reason == "policy_refused":
            ok = resolved is not None and resolved >= aware(d["opened_at"])
        else:
            first = min(aware(r["received_at"]) for r in d["responses"])
            ok = resolved is not None and resolved == first
        if not ok:
            out.append(_v("resolved_at_inconsistent", f"{p}.resolved_at",
                          "null while deferred; the deciding response time when a response decided; not before the deadline on expiry"))
    return out


def _effect_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    for i, d in enumerate(doc["deferrals"]):
        p = f"$.deferrals[{i}].effect"
        eff = d["effect"]
        first = aware(eff["first_observable_at"]) if eff["first_observable_at"] is not None else None
        if eff["observable"] != (eff["first_observable_at"] is not None):
            out.append(_v("effect_observability_inconsistent", p, "observable is true if and only if first_observable_at is set"))
        elif d["outcome"] == "refused" and eff["observable"]:
            out.append(_v("refused_effect_observable", p, "a refused effect never becomes observable"))
        elif d["outcome"] == "deferred" and eff["observable"]:
            out.append(_v("effect_observable_before_release", p, "no effect is observable while the deferral is open"))
        elif d["outcome"] == "released" and first is not None and d["resolved_at"] is not None:
            resolved = aware(d["resolved_at"])
            if resolved is not None and first < resolved:
                out.append(_v("effect_observable_before_release", p, "no effect is observable before RELEASE"))
    return out


_PRIVATE_SHAPE = re.compile(r"sha256:[0-9a-f]{16,}|\b(?:grant|tenant)[_-]?id\b|urn:cognous:", re.I)


def _notice_rules(doc: dict[str, Any], journal: dict[str, Any] | None = None) -> list[Violation]:
    out: list[Violation] = []
    for i, d in enumerate(doc["deferrals"]):
        notice = d.get("refusal_notice")
        if notice is None:
            continue
        p = f"$.deferrals[{i}].refusal_notice"
        if d["outcome"] != "refused":
            out.append(_v("refusal_notice_on_non_refusal", p, "a refusal notice exists only on a refused deferral"))
            continue
        if notice["effect_id"] != d["effect_id"]:
            out.append(_v("refusal_notice_effect_mismatch", f"{p}.effect_id", "the notice names the deferral's own effect"))
        allowed = {d["refusal_reason"], *d["policy"]["deferred_reasons"], *d["policy"]["refusal_reasons"]}
        if notice["constraint_failed"]["code"] not in allowed:
            out.append(_v("refusal_notice_constraint_mismatch", f"{p}.constraint_failed.code",
                          "the failed constraint is the refusal reason or a reason the policy recorded for this deferral"))
        private = set()
        if journal is not None:
            for dec in journal.get("decisions", []):
                b = dec.get("binding") or {}
                private |= {v for v in (b.get("grant_id"), b.get("tenant_id")) if isinstance(v, str) and v}
        texts = [notice["statement"], notice["constraint_failed"]["description"]] + [a["description"] for a in notice["admissible_alternatives"]] \
            + [a["alternative_id"] for a in notice["admissible_alternatives"]]
        if any(_PRIVATE_SHAPE.search(t) or any(secret in t for secret in private) for t in texts):
            out.append(_v("refusal_notice_private_state", p, "a notice carries no commitments, grant or tenant identifiers or other private state"))
    return out


# --------------------------------------------------------------------------- journal context (optional)

def check_against_journal(doc: dict[str, Any], journal: dict[str, Any]) -> list[Violation]:
    """Rules that need the conforming run record the deferrals are layered on."""
    out: list[Violation] = []
    if journal.get("run_id") != doc["run_id"]:
        return [_v("journal_run_mismatch", "$.run_id", "the profile document and the run record describe the same run")]
    decisions = {d["decision_id"]: d for d in journal["decisions"]}
    for i, d in enumerate(doc["deferrals"]):
        p = f"$.deferrals[{i}]"
        dec = decisions.get(d["decision_id"])
        if dec is None:
            out.append(_v("deferral_dangling_decision", p, "a deferral names a decision in the run record"))
            continue
        if dec["result"] != "hold" or dec["binding"] is not None:
            out.append(_v("deferral_decision_not_held", p, "only a held decision (result hold, no binding) can be deferred"))
            continue
        if dec["effect_id"] != d["effect_id"]:
            out.append(_v("deferral_effect_mismatch", p, "the deferral carries its held decision's effect_id"))
        horizon = dec.get("operation_horizon") or {}
        if horizon.get("proposal_commitment") != d["proposal_commitment"]:
            out.append(_v("deferral_proposal_mismatch", p, "the deferral commits to the held decision's proposal"))
        if set(dec["reasons"]) != set(d["policy"]["deferred_reasons"]) | set(d["policy"]["refusal_reasons"]):
            out.append(_v("deferral_reasons_not_held", f"{p}.policy",
                          "deferred and refusal reasons together are exactly the held decision's reasons"))
        opened, decided = aware(d["opened_at"]), aware(dec["decided_at"])
        if opened is not None and decided is not None and opened < decided:
            out.append(_v("deferral_before_decision", f"{p}.opened_at", "a deferral opens at or after the decision that held"))
        cls = next((e["action_class"] for e in journal.get("check_events", [])
                    if e["stage"] == "decision" and e["proposal_commitment"] == d["proposal_commitment"]), None)
        if cls is not None and (cls.get("class_id") != d["action_class_id"] or cls.get("max_status_age_seconds") != d["max_age_seconds"]):
            out.append(_v("deferral_max_age_mismatch", p,
                          "the deferral's class and bound are the action class's class_id and max_status_age_seconds"))
        out.extend(_journal_effect_rules(p, d, journal, decisions))
    return out


def _journal_effect_rules(p: str, d: dict[str, Any], journal: dict[str, Any], decisions: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    resolved = aware(d["resolved_at"]) if d["resolved_at"] is not None else None
    sibling = {x["effect_id"]: x for x in journal["decisions"]
               if x["binding"] is not None and x["binding"]["proposal_commitment"] == d["proposal_commitment"]}
    others = set(sibling)
    if d["outcome"] == "released":
        rel = decisions.get(d["released_decision_id"])
        if rel is None or rel["result"] != "authorized" or rel["binding"] is None \
                or rel["binding"]["proposal_commitment"] != d["proposal_commitment"]:
            out.append(_v("release_decision_unauthorized", f"{p}.released_decision_id",
                          "RELEASE is not authority: it names an authorized decision for the same proposal"))
        else:
            others.discard(rel["effect_id"])
            when = aware(rel["decided_at"])
            if resolved is not None and when is not None and when < resolved:
                out.append(_v("release_decision_before_release", f"{p}.released_decision_id", "the authorizing decision follows the release"))
            for a in journal["attempts"]:
                if a["effect_id"] == rel["effect_id"] and resolved is not None and aware(a.get("started_at")) is not None \
                        and aware(a["started_at"]) < resolved:
                    out.append(_v("effect_attempted_before_release", p, "no attempt starts before RELEASE"))
                    break
    for a in journal["attempts"]:
        if a["effect_id"] in others:
            out.append(_v("effect_attempted_without_release", p, "no attempt on this proposal exists unless the deferral was released"))
            break
    if d["outcome"] == "refused":
        for o in journal["observations"]:
            if o["effect_id"] in sibling and o["state"] in {"applied", "partial"}:
                out.append(_v("refused_effect_observed", p, "a refused effect is never observed as applied or partial"))
                break
    return out


def _validate(doc: Any, journal: dict[str, Any] | None = None) -> list[Violation]:
    """Return all violations; an empty list means the document conforms to 0.1.0-draft.

    ``journal`` is an optional conforming control-plane-journal document for the cross-document rules.
    """
    out = validate_structure(doc)
    if out:
        return out
    for rule in (_times, _identity_rules, _policy_rules, _deadline_rules, _outcome_rules, _effect_rules):
        out.extend(rule(doc))
    out.extend(_notice_rules(doc, journal))
    if journal is not None:
        out.extend(check_against_journal(doc, journal))
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
