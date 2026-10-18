"""Reference validator for the Control Plane journal contract (0.1.0-draft).

Stdlib only. A draft: it states the contract executably so each side of the boundary can be tested alone
against golden fixtures. It does not import or modify ``odes``.

Layers:

1. Structure: a minimal interpreter for the JSON Schema subset used by ``schema.json`` (the schema is the
   single source of truth for members, types, enumerations and the closed-member-set rule).
2. Rules: the cross-record rules in README.md, derived from the Control Plane producer
   (``bounded.py``) and from what Replay enforces on import.
3. Delegation: attempt-lifecycle and journal-protocol rules are NOT restated here. They are owned by the
   ``execution-attempt-lifecycle`` contract, and this validator projects the run record onto that contract's
   document form and calls its validator, so the two cannot drift apart.

``validate`` returns a list of ``Violation`` (empty list means conformant). Refusal codes are stable strings.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "schema.json"
CONTRACT = "control-plane-journal"
CONTRACT_VERSION = "0.1.0-draft"
# The lifecycle contract version whose attempt and journal rules are delegated to. A change of that version
# must be reviewed here (tests pin this value).
DELEGATED_LIFECYCLE_VERSION = "0.1.0-draft"
LIFECYCLE_PATH = HERE.parent / "execution-attempt-lifecycle" / "validate.py"
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
REASON_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
UNCERTAIN = {"attempted", "unknown", "failed"}


@dataclass(frozen=True)
class Violation:
    code: str
    path: str
    message: str


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


_LIFECYCLE: Any = None


def lifecycle() -> Any:
    """The execution-attempt lifecycle validator module (loaded from the sibling contract directory)."""
    global _LIFECYCLE
    if _LIFECYCLE is None:
        if not LIFECYCLE_PATH.is_file():
            raise FileNotFoundError(
                f"the execution-attempt-lifecycle contract must be present next to this one ({LIFECYCLE_PATH}); "
                "a vendored copy of control-plane-journal needs the lifecycle contract vendored beside it")
        spec = importlib.util.spec_from_file_location("odes_eal_validate", LIFECYCLE_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module  # the module defines a dataclass; register before exec
        spec.loader.exec_module(module)
        _LIFECYCLE = module
    return _LIFECYCLE


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


# --------------------------------------------------------------------------- optional profile members
#
# The three opt-in extension profiles (operation-identity/0.1, rule-revision/0.1, freshness/0.1) add optional members,
# two check phases and one read state to the run record. They are declared in schema.json as optional members and values
# (the schema keeps to plain keywords so a minimal interpreter can read it) and listed here with their owning profile.
# This contract checks only their presence, type and closedness; the sidecar contract of the owning profile validates their
# semantics. Every relaxation below applies only when the corresponding profile member is present; with none present the
# validator behaves exactly as before (tests pin this against a baseline of every earlier fixture). A test pins this table
# against the schema: each member is declared, optional and says which profile owns it.

FRESHNESS = "freshness/0.1"
EXPIRED_REASON = "check_expired_before_dispatch"
LEASE_REASON = "check_lease_unavailable"
PROFILE_PHASES = {"overdue", "expired"}
PROFILE_READ_STATE = "nonce_mismatch"
PROFILE_TIME_MEMBERS = {"decisions": ("evaluated_at", "recorded_at"), "attempts": ("evaluated_at", "recorded_at"),
                        "refusals": ("evaluated_at", "deadline"), "resolution_checks": ("recorded_at",),
                        "check_events": ("evaluated_at", "deadline")}


# Members owned by an opt-in profile, by object (a ``$defs`` name, or ``$`` for the document): member -> owning profiles.
PROFILE_OWNED: dict[str, dict[str, list[str]]] = {
    "$": {
        "operations": ["operation-identity/0.1"],
        "operation_renewals": ["operation-identity/0.1"],
        "attempt_joins": ["operation-identity/0.1"],
        "rule_revisions": ["rule-revision/0.1"],
        "rule_revision_refusals": ["rule-revision/0.1"],
        "age_extensions": ["freshness/0.1"],
        "age_extension_refusals": ["freshness/0.1"],
        "recovery_runs": ["freshness/0.1"],
    },
    "resolution_input": {
        "age_basis": ["freshness/0.1"],
    },
    "resolution_check": {
        "recorded_at": ["freshness/0.1"],
    },
    "control_plane_attempt": {
        "evaluated_at": ["freshness/0.1"],
        "recorded_at": ["freshness/0.1"],
    },
    "journal_event": {
        "evaluated_at": ["freshness/0.1"],
        "deadline": ["freshness/0.1"],
        "age_bound_seconds": ["freshness/0.1"],
        "extension_id": ["freshness/0.1"],
        "nonce": ["freshness/0.1"],
    },
    "runtime_authority": {
        "operation_id": ["operation-identity/0.1"],
        "operation_issuer": ["operation-identity/0.1"],
    },
    "decision": {
        "evaluated_at": ["freshness/0.1"],
        "recorded_at": ["freshness/0.1"],
        "rule_identity": ["rule-revision/0.1"],
    },
    "refusal": {
        "evaluated_at": ["freshness/0.1"],
        "deadline": ["freshness/0.1"],
        "check_id": ["operation-identity/0.1", "freshness/0.1"],
        "rule_identity": ["rule-revision/0.1"],
    },
}

# Enumeration values owned by an opt-in profile: "<$defs name>.<member>" -> value -> owning profiles.
PROFILE_VALUES: dict[str, dict[str, list[str]]] = {
    "resolution_input.read_state": {
        "nonce_mismatch": ["freshness/0.1"],
    },
    "journal_event.phase": {
        "overdue": ["freshness/0.1"],
        "expired": ["freshness/0.1"],
    },
}


def _owners() -> dict[str, dict[str, list[str]]]:
    """Profile-owned members by object (``$defs`` name, or ``$`` for the document)."""
    return {name: PROFILE_OWNED.get(name, {}) for name in ["$"] + list(load_schema()["$defs"])}


def profile_members(obj: str) -> set[str]:
    """Members of a declared object (``$defs`` name, or ``$``) owned by an extension profile."""
    return set(_owners()[obj])


def _exclusive(obj: str, row: Any) -> set[str]:
    """Profiles whose exclusive members are present on ``row`` (a member shared by two profiles proves neither)."""
    if not isinstance(row, dict):
        return set()
    return {owners[0] for m, owners in _owners()[obj].items() if m in row and len(owners) == 1}


def _row_inputs(doc: dict[str, Any]):
    for row in doc["decisions"] + doc["refusals"]:
        yield from row["resolution_inputs"]
    for row in doc["resolution_checks"]:
        yield from row["inputs"]
    for e in doc.get("check_events", []):
        if e["input"] is not None:
            yield e["input"]


def profiles_present(doc: dict[str, Any]) -> set[str]:
    """Profiles that own a member or value present in the run record (empty for every default-path record)."""
    found = _exclusive("$", doc)
    for section, obj in (("decisions", "decision"), ("attempts", "control_plane_attempt"), ("refusals", "refusal"),
                         ("resolution_checks", "resolution_check"), ("check_events", "journal_event")):
        for row in doc.get(section, []):
            found |= _exclusive(obj, row)
    for d in doc["decisions"]:
        if d["binding"] is not None:
            found |= _exclusive("runtime_authority", d["binding"].get("runtime_authority"))
    for e in doc.get("check_events", []):
        if e["phase"] in PROFILE_PHASES:
            found.add(FRESHNESS)
    for x in _row_inputs(doc):
        found |= _exclusive("resolution_input", x)
        if x.get("read_state") == PROFILE_READ_STATE:
            found.add(FRESHNESS)
    return found


def _expired_attempts(doc: dict[str, Any]) -> set[str]:
    """Attempts whose failed start is excused by their effect-time refusal (freshness/0.1).

    An attempt is excused only if its latest row is ``failed`` with ``check_expired_before_dispatch`` AND a refusal of
    the same effect carries that reason and the profile's ``deadline`` member. One refusal excuses one attempt.
    """
    refusals: dict[str, int] = {}
    for r in doc["refusals"]:
        if "deadline" in r and EXPIRED_REASON in r["reasons"]:
            refusals[r["effect_id"]] = refusals.get(r["effect_id"], 0) + 1
    if not refusals:
        return set()
    latest: dict[str, dict[str, Any]] = {}
    for a in doc["attempts"]:
        latest[a["attempt_id"]] = a
    excused: set[str] = set()
    for aid, a in latest.items():
        if a["status"] == "failed" and a.get("error") == EXPIRED_REASON and refusals.get(a["effect_id"], 0) > 0:
            refusals[a["effect_id"]] -= 1
            excused.add(aid)
    return excused


# --------------------------------------------------------------------------- rules

def _all_inputs(doc: dict[str, Any]):
    for i, d in enumerate(doc["decisions"]):
        for j, x in enumerate(d["resolution_inputs"]):
            yield f"$.decisions[{i}].resolution_inputs[{j}]", x
    for i, r in enumerate(doc["refusals"]):
        for j, x in enumerate(r["resolution_inputs"]):
            yield f"$.refusals[{i}].resolution_inputs[{j}]", x
    for i, c in enumerate(doc["resolution_checks"]):
        for j, x in enumerate(c["inputs"]):
            yield f"$.resolution_checks[{i}].inputs[{j}]", x
    for i, e in enumerate(doc.get("check_events", [])):
        if e["input"] is not None:
            yield f"$.check_events[{i}].input", e["input"]


def _decision_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    seen: set[str] = set()
    for i, d in enumerate(doc["decisions"]):
        p = f"$.decisions[{i}]"
        if d["decision_id"] in seen:
            out.append(_v("duplicate_decision_id", p, "decision ids are unique (the store resolves a decision only when exactly one row matches)"))
        seen.add(d["decision_id"])
        binding = d["binding"]
        authorized = d["result"] == "authorized"
        if authorized != (not d["reasons"]) or authorized != (binding is not None):
            out.append(_v("decision_result_inconsistent", p,
                          "result 'authorized' if and only if reasons is empty and a binding is present"))
            continue
        if binding is not None:
            expected = commitment({"proposal": binding["proposal_commitment"], "grant_id": binding["grant_id"],
                                   "grant_revision": binding["grant_revision"]})
            if d["effect_id"] != expected:
                out.append(_v("invalid_effect_identity", f"{p}.effect_id",
                              "effect_id is the commitment of {proposal, grant_id, grant_revision} from the binding"))
            horizon = d["operation_horizon"]
            if horizon is not None and horizon["proposal_commitment"] != binding["proposal_commitment"]:
                out.append(_v("horizon_binding_mismatch", f"{p}.operation_horizon",
                              "the operation horizon commits to the same proposal as the binding"))
            if (binding.get("generation") is None) != (binding.get("tenant_id") is None):
                out.append(_v("tenant_binding_incomplete", f"{p}.binding",
                              "generation and tenant_id are carried together (tenant binding) or not at all"))
    return out


def _reference_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    decisions = {d["decision_id"]: d for d in doc["decisions"]}
    effects = {d["effect_id"] for d in doc["decisions"]}
    for section, label in (("attempts", "attempt"), ("refusals", "refusal")):
        for i, row in enumerate(doc[section]):
            p = f"$.{section}[{i}]"
            d = decisions.get(row["decision_id"])
            if d is None:
                out.append(_v("dangling_decision_reference", p, f"{label} names a decision that is not in decisions"))
            elif d["effect_id"] != row["effect_id"]:
                out.append(_v("effect_id_mismatch", p, f"{label} effect_id differs from its decision's effect_id"))
            elif d["result"] != "authorized" or d["binding"] is None:
                out.append(_v("attempt_on_unauthorized_decision" if section == "attempts" else "refusal_requires_authorized_decision",
                              p, f"a {label} requires an authorized decision with a binding"))
    for i, e in enumerate(doc.get("check_events", [])):
        if e["decision_id"] is not None:
            d = decisions.get(e["decision_id"])
            if d is None or d["effect_id"] != e["effect_id"]:
                out.append(_v("journal_lineage_mismatch", f"$.check_events[{i}]",
                              "journal decision_id and effect_id must name an existing decision and its effect"))
        if e["stage"] in {"decision", "effect"} and (e["decision_id"] is not None) != (e["stage"] == "effect"):
            out.append(_v("journal_stage_binding", f"$.check_events[{i}]",
                          "a decision-stage check has no decision yet (null); an effect-stage check names its decision"))
    for section in ("observations", "reconciliations"):
        for i, row in enumerate(doc[section]):
            if row["effect_id"] not in effects:
                out.append(_v("dangling_effect_reference", f"$.{section}[{i}]", "effect_id matches no decision"))
    return out


def _attempt_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    starts: dict[str, set[str]] = {}
    excused = _expired_attempts(doc)
    for i, row in enumerate(doc["attempts"]):
        p = f"$.attempts[{i}]"
        status, ack, error = row["status"], row["acknowledgement"], row.get("error")
        if status in {"attempted", "failed", "unknown"} and set(ack) - {"reconciled_existing"}:
            out.append(_v("attempt_acknowledgement_inconsistent", p + ".acknowledgement",
                          f"a '{status}' row carries no acknowledgement (empty object; the reconciled_existing marker is checked by the lifecycle rules)"))
        bad_error = (
            (status == "failed" and not (isinstance(error, str) and REASON_CODE.fullmatch(error)))
            or (status == "unknown" and not (isinstance(error, str) and error.startswith("destination_outcome_unknown:")))
            or (status in {"attempted", "acknowledged", "partial"} and error is not None)
        )
        if bad_error:
            out.append(_v("attempt_error_inconsistent", p + ".error",
                          "error is null on attempted/acknowledged/partial rows, a bounded reason code on 'failed', "
                          "and 'destination_outcome_unknown:<ExceptionName>' on 'unknown'"))
        if status == "attempted" and row["attempt_id"] not in excused:
            starts.setdefault(row["effect_id"], set()).add(row["attempt_id"])
    for effect, ids in starts.items():
        if len(ids) > 1:
            out.append(_v("second_attempt_for_effect", "$.attempts",
                          f"effect {effect} has more than one attempt lifecycle that starts with 'attempted'; "
                          "observed absence never establishes retry eligibility after a prior attempt"))
    return out


def _accepted(rec: dict[str, Any]) -> bool:
    return rec["observation_accepted"] is True


def _reconciliation_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    freshness = FRESHNESS in profiles_present(doc)
    for i, rec in enumerate(doc["reconciliations"]):
        p = f"$.reconciliations[{i}]"
        if rec["retry_eligible"] is not False:
            out.append(_v("reconciliation_retry_eligible", p + ".retry_eligible",
                          "a reconciliation never establishes retry eligibility; retry_eligible must be false"))
            continue
        if not _accepted(rec):
            if rec["result"] != "hold" or not rec["reasons"]:
                out.append(_v("rejected_observation_not_held", p,
                              "a rejected or unavailable observation is recorded with result 'hold' and non-empty reasons"))
            continue
        if rec["reasons"]:
            out.append(_v("accepted_observation_has_reasons", p + ".reasons", "an accepted observation carries no rejection reasons"))
            continue
        obs = rec["observation"]
        if obs is None:
            out.append(_v("accepted_observation_missing", p + ".observation", "an accepted reconciliation carries its observation"))
            continue
        effect = rec["effect_id"]
        state = obs["state"]
        dest = obs.get("destination_state", {})
        if obs["effect_id"] != effect:
            out.append(_v("observation_effect_id_mismatch", p + ".observation.effect_id",
                          "the accepted observation names the reconciled effect"))
            continue
        if state == "unknown":
            out.append(_v("observation_state_unknown", p + ".observation.state", "an observation in state 'unknown' is never accepted"))
            continue
        if state in {"applied", "partial"}:
            if dest.get("effect_id") != effect:
                out.append(_v("destination_effect_id_mismatch", p + ".observation.destination_state",
                              "positive destination evidence names the same effect"))
                continue
            if dest.get("state") != state:
                out.append(_v("destination_state_contradiction", p + ".observation.destination_state",
                              "destination_state.state equals the observation state"))
                continue
        elif dest:
            out.append(_v("absence_has_destination_state", p + ".observation.destination_state",
                          "an 'absent' observation carries an empty destination_state"))
            continue
        maximum, tolerance = rec["observation_max_age_seconds"], rec["observation_clock_tolerance_seconds"]
        if maximum is None or maximum <= 0 or tolerance is None or tolerance < 0:
            out.append(_v("observation_policy_missing", p,
                          "an accepted observation records the policy it was accepted under (max age > 0, tolerance >= 0)"))
            continue
        observed, evaluated = aware(obs.get("observed_at")), aware(rec["evaluation_time"])
        if observed is None or evaluated is None:
            out.append(_v("observation_time_invalid", p,
                          "an accepted observation has a timezone-aware observed_at and the reconciliation a timezone-aware evaluation_time"))
            continue
        age = (evaluated - observed).total_seconds()
        # freshness/0.1 decouples the observation clock: "future" is judged against the service clock re-read at
        # reconciliation (reconciled_at) when that is later than the evaluation pass; staleness stays relative to the
        # evaluation. Without a freshness member the evaluation time is the only reference.
        reference = max(evaluated, aware(rec["reconciled_at"]) or evaluated) if freshness else evaluated
        if (reference - observed).total_seconds() < -tolerance:
            out.append(_v("observation_time_future", p, "observed_at is later than evaluation_time plus the recorded tolerance"))
            continue
        if age > maximum:
            out.append(_v("observation_stale", p, "observed_at is older than the recorded maximum age"))
            continue
        expected = {"applied": "applied", "absent": "observed_absent", "partial": "hold"}[state]
        if rec["result"] != expected:
            out.append(_v("reconciliation_result_mismatch", p + ".result",
                          f"an accepted '{state}' observation is recorded as result '{expected}'"))
    if out:
        return out
    # The observations member lists the accepted observations, in the order they were accepted (per effect).
    accepted: dict[str, list[Any]] = {}
    for rec in doc["reconciliations"]:
        if _accepted(rec):
            accepted.setdefault(rec["effect_id"], []).append(rec["observation"])
    listed: dict[str, list[Any]] = {}
    for obs in doc["observations"]:
        listed.setdefault(obs["effect_id"], []).append(obs)
    if accepted != listed:
        out.append(_v("observations_mismatch", "$.observations",
                      "observations lists exactly the accepted reconciliation observations (per effect, in order)"))
    return out


def _closeout_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    keys: set[tuple[str, str]] = set()
    for i, c in enumerate(doc["closeouts"]):
        p = f"$.closeouts[{i}]"
        key = (c["attempt_id"], c["observed_state"])
        if key in keys:
            out.append(_v("duplicate_closeout", p, "one closeout per attempt and observed state"))
        keys.add(key)
        if not any(a["attempt_id"] == c["attempt_id"] and a["effect_id"] == c["effect_id"] and a["status"] == c["original_status"]
                   for a in doc["attempts"]):
            out.append(_v("closeout_lineage_missing", p, "a closeout names an attempt row with the same effect and original status"))
            continue
        if not any(_accepted(r) and r["effect_id"] == c["effect_id"] and (r["observation"] or {}).get("state") == c["observed_state"]
                   and (r["observation"] or {}).get("observed_at") == c["observed_at"] for r in doc["reconciliations"]):
            out.append(_v("closeout_observation_missing", p, "a closeout names an accepted observation of that effect, state and time"))
    if out:
        return out
    latest: dict[str, dict[str, Any]] = {}
    for a in doc["attempts"]:
        latest[a["attempt_id"]] = a
    reported: set[tuple[str, str]] = set()
    for rec in doc["reconciliations"]:
        state = (rec["observation"] or {}).get("state")
        if _accepted(rec) and state in {"applied", "partial"}:
            for aid, a in latest.items():
                if a["effect_id"] == rec["effect_id"] and a["status"] in UNCERTAIN and (aid, state) not in keys | reported:
                    reported.add((aid, state))
                    out.append(_v("closeout_missing", "$.closeouts",
                                  f"attempt {aid} is still {a['status']!r}; an accepted {state!r} observation "
                                  "of its effect requires a closeout"))
    return out


def _refusal_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    decisions = {d["decision_id"]: d for d in doc["decisions"]}
    seen: set[str] = set()
    for i, r in enumerate(doc["refusals"]):
        p = f"$.refusals[{i}]"
        if r["refusal_id"] in seen:
            out.append(_v("duplicate_refusal_id", p, "refusal ids are unique"))
        seen.add(r["refusal_id"])
        if not r["reasons"]:
            out.append(_v("refusal_without_reasons", p + ".reasons", "a refusal carries typed reasons"))
        d = decisions.get(r["decision_id"])
        if d is not None and r["original_operation_horizon"] != d["operation_horizon"]:
            out.append(_v("refusal_horizon_mismatch", p + ".original_operation_horizon",
                          "the original horizon equals the horizon of the decision being refused"))
        for j, change in enumerate(r["changed_inputs"]):
            if not any(x["input_type"] == change["input_type"] and x["input_id"] == change["input_id"] for x in r["resolution_inputs"]):
                out.append(_v("changed_input_unattributed", f"{p}.changed_inputs[{j}]",
                              "a changed input is attributed to an actual read in resolution_inputs"))
    return out


def _input_and_time_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    for p, x in _all_inputs(doc):
        if x["missing"] and x["record_commitment"] is not None:
            out.append(_v("missing_input_commitment", p, "a missing input claims no record commitment"))
        if x["previous_observed_at"] is not None and aware(x["previous_observed_at"]) is None:
            out.append(_v("timestamp_invalid", p + ".previous_observed_at", "timestamps are timezone-aware ISO-8601"))
    stamps: list[tuple[str, Any]] = []
    for i, d in enumerate(doc["decisions"]):
        h = d["operation_horizon"]
        if h:
            stamps += [(f"$.decisions[{i}].operation_horizon.{k}", h[k]) for k in ("not_before", "expires_at") if h[k] is not None]
    stamps += [(f"$.decisions[{i}].decided_at", d["decided_at"]) for i, d in enumerate(doc["decisions"])]
    stamps += [(f"$.attempts[{i}].started_at", a["started_at"]) for i, a in enumerate(doc["attempts"])]
    for i, r in enumerate(doc["refusals"]):
        stamps.append((f"$.refusals[{i}].recorded_at", r["recorded_at"]))
        for name in ("original_operation_horizon", "operation_horizon"):
            h = r[name]
            if h:
                stamps += [(f"$.refusals[{i}].{name}.{k}", h[k]) for k in ("not_before", "expires_at") if h[k] is not None]
    stamps += [(f"$.resolution_checks[{i}].evaluated_at", c["evaluated_at"]) for i, c in enumerate(doc["resolution_checks"])]
    stamps += [(f"$.check_events[{i}].recorded_at", e["recorded_at"]) for i, e in enumerate(doc.get("check_events", []))]
    stamps += [(f"$.closeouts[{i}].{k}", c[k]) for i, c in enumerate(doc["closeouts"]) for k in ("observed_at", "reconciled_at")]
    stamps += [(f"$.reconciliations[{i}].reconciled_at", r["reconciled_at"]) for i, r in enumerate(doc["reconciliations"])]
    stamps += [(f"$.reconciliations[{i}].evaluation_time", r["evaluation_time"])
               for i, r in enumerate(doc["reconciliations"]) if r["evaluation_time"] is not None]
    stamps += [(f"$.vocabulary_changes[{i}].acknowledged_at", c["acknowledged_at"]) for i, c in enumerate(doc.get("vocabulary_changes", []))]
    stamps += [(f"$.input_time_floors.{k}", v) for k, v in doc["input_time_floors"].items()]
    for section, members in PROFILE_TIME_MEMBERS.items():  # freshness/0.1 times, when present
        stamps += [(f"$.{section}[{i}].{m}", row[m]) for i, row in enumerate(doc.get(section, [])) for m in members if m in row]
    for p, s in stamps:
        if aware(s) is None:
            out.append(_v("timestamp_invalid", p, "timestamps are timezone-aware ISO-8601"))
    return out


def _journal_mode_rules(doc: dict[str, Any]) -> list[Violation]:
    """Journal mode: check_events present (non-empty). Then vocabulary and runtime-authority members are required;
    outside journal mode they must not appear (the producer emits them only under a runtime-authority profile)."""
    out: list[Violation] = []
    journal = bool(doc.get("check_events"))
    for section in ("decisions", "refusals"):
        for i, row in enumerate(doc[section]):
            has = "reason_vocabulary_version" in row
            if has and not journal and section == "decisions" and _lease_hold(row):
                continue  # freshness/0.1: the lease is refused before the check is journalled, so no journal exists
            if journal and not has:
                out.append(_v("vocabulary_version_missing", f"$.{section}[{i}]", "journal mode: the reason vocabulary version is recorded on every decision and refusal"))
            elif has and not journal:
                out.append(_v("journal_missing", f"$.{section}[{i}].reason_vocabulary_version",
                              "a vocabulary version without a resolution journal (check_events)"))
    for i, d in enumerate(doc["decisions"]):
        b = d["binding"]
        if b is None:
            continue
        has = "runtime_authority" in b
        if journal and not has:
            out.append(_v("runtime_authority_binding_missing", f"$.decisions[{i}].binding", "journal mode: an authorized binding carries runtime_authority"))
        elif has and not journal:
            out.append(_v("journal_missing", f"$.decisions[{i}].binding.runtime_authority", "runtime_authority without a resolution journal (check_events)"))
    return out


# ------------------------------------------------------------------ reason registry labels (draft revision 3, decision 31)

VOCABULARY_0_1 = "runtime-authority-reasons/0.1"
VOCABULARY_0_2 = "runtime-authority-reasons/0.2"
# The 36 codes the Control Plane registry labels runtime-authority-reasons/0.2 registers and 0.1 does not (0.2 is a 157-code
# superset of the original 121). Source: cogno-us/cognous-control-plane schemas/runtime_authority_reasons_0_2.json minus
# runtime_authority_reasons_0_1.json at main 3755c71a. Producer rule (runtime_authority.vocabulary_for): a row carries 0.2 only if
# one of its reasons is in this set, else 0.1.
CODES_ADDED_IN_0_2 = frozenset({
    "age_extension_authority_unconfigured",
    "age_extension_exceeds_limit",
    "age_extension_invalid",
    "age_extension_irreversible_class",
    "age_extension_self_signed",
    "age_extension_signer_not_configured",
    "age_extension_unsigned",
    "attempt_unresolved_past_horizon",
    "check_expired_before_dispatch",
    "check_lease_unavailable",
    "check_overdue",
    "dedupe_operation_effect_applied",
    "dedupe_unresolved_attempt_blocks_new_key",
    "escalation_after_key_ttl",
    "holder_inventory_missing",
    "merge_authority_unfunded",
    "merge_operation_already_folded",
    "merge_operation_discriminator_mismatch",
    "merge_operation_ids_invalid",
    "merge_operation_not_admitted",
    "merge_rule_unknown",
    "merge_survivor_already_folded",
    "operation_grant_mismatch",
    "operation_id_invalid",
    "operation_id_missing",
    "operation_merged_effect_exists",
    "operation_merged_effect_unresolved",
    "operation_not_admitted",
    "operation_renewal_unrecorded",
    "purpose_cache_after_reversal_window",
    "purpose_cache_irreversible_class",
    "purpose_cache_stale",
    "purpose_closure_recorded",
    "renewal_not_written_by_grant_issuer",
    "renewal_revision_not_new",
    "status_nonce_mismatch",
})


def _reason_label_rules(doc: dict[str, Any]) -> list[Violation]:
    """A row labelled runtime-authority-reasons/0.1 holds no code that only 0.2 registers. The converse is not checked: 0.2 is a
    superset, so a 0.2 label on a row of 0.1 codes states a true thing the producer happens not to write. Codes outside both
    registries are not judged (the contract has never closed the reason string set)."""
    out: list[Violation] = []
    for section in ("decisions", "refusals", "check_events"):
        for i, row in enumerate(doc.get(section, [])):
            if row.get("reason_vocabulary_version") != VOCABULARY_0_1:
                continue
            late = sorted(set(row.get("reasons", [])) & CODES_ADDED_IN_0_2)
            if late:
                out.append(_v("reason_label_mismatch", f"$.{section}[{i}].reason_vocabulary_version",
                              f"label {VOCABULARY_0_1} but the reasons include {', '.join(late)}, which only {VOCABULARY_0_2} registers"))
    return out


def _lease_hold(decision: dict[str, Any]) -> bool:
    """A hold for ``check_lease_unavailable`` alone, written under freshness/0.1 (it carries the profile's ``evaluated_at``)."""
    return (decision["result"] == "hold" and decision["reasons"] == [LEASE_REASON] and decision["binding"] is None
            and "evaluated_at" in decision)


def _profile_rules(doc: dict[str, Any]) -> list[Violation]:
    """What this contract checks of profile-owned values; the owning sidecar contract validates the rest."""
    out: list[Violation] = []
    opened: set[str] = set()
    for i, e in enumerate(doc.get("check_events", [])):
        p = f"$.check_events[{i}]"
        if e["phase"] == "opened":
            opened.add(e["check_id"])
        elif e["phase"] in PROFILE_PHASES:
            if "deadline" not in e:
                out.append(_v("profile_value_without_member", p + ".phase",
                              f"phase {e['phase']!r} belongs to {FRESHNESS} and its event carries the profile's deadline"))
            elif e["check_id"] not in opened:
                out.append(_v("journal_protocol", p, "journal event without an open check (missing opening or already closed)"))
    for p, x in _all_inputs(doc):
        if x.get("read_state") == PROFILE_READ_STATE and "age_basis" not in x:
            out.append(_v("profile_value_without_member", p + ".read_state",
                          f"read state {PROFILE_READ_STATE!r} belongs to {FRESHNESS} and its input carries age_basis"))
    return out


def _floor_and_vocabulary_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    seen: set[str] = set()
    for i, c in enumerate(doc.get("vocabulary_changes", [])):
        p = f"$.vocabulary_changes[{i}]"
        if c["change_id"] in seen:
            out.append(_v("duplicate_vocabulary_change", p, "a vocabulary change is recorded once"))
        seen.add(c["change_id"])
        if c["version"] == c["previous_version"] or (c["kind"] == "split" and len(c["codes"]) < 2):
            out.append(_v("invalid_vocabulary_transition", p, "version differs from previous_version; a split yields at least two codes"))
    return out


def _strip_input(x: dict[str, Any]) -> dict[str, Any]:
    drop = profile_members("resolution_input") | ({"read_state"} if x.get("read_state") == PROFILE_READ_STATE else set())
    return {k: v for k, v in x.items() if k not in drop}


def _lifecycle_projection(doc: dict[str, Any]) -> dict[str, Any]:
    """The run record as the lifecycle contract's document. Profile-owned members, the two profile phases and the
    profile read state are not the lifecycle contract's (their sidecar validates them) and are left out; a record
    without any of them projects exactly as before."""
    lc = lifecycle()
    attempt_drop = profile_members("control_plane_attempt")
    proj: dict[str, Any] = {"contract": lc.CONTRACT, "contract_version": lc.CONTRACT_VERSION, "producer": "control-plane",
                            "control_plane_attempts": [{k: v for k, v in a.items() if k not in attempt_drop} for a in doc["attempts"]]}
    if doc.get("check_events") is not None:
        event_drop = profile_members("journal_event")
        check_drop = profile_members("resolution_check")
        proj["resolution_journal"] = [
            {k: (_strip_input(v) if k == "input" and v is not None else v) for k, v in e.items() if k not in event_drop}
            for e in doc["check_events"] if e["phase"] not in PROFILE_PHASES]
        proj["resolution_checks"] = [
            {k: ([_strip_input(x) for x in v] if k == "inputs" else v) for k, v in c.items() if k not in check_drop}
            for c in doc["resolution_checks"]]
    return proj


_PATHS = (("$.control_plane_attempts", "$.attempts"), ("$.resolution_journal", "$.check_events"))


def _delegated_rules(doc: dict[str, Any]) -> list[Violation]:
    """Attempt lifecycle and journal protocol are the lifecycle contract's rules (single source)."""
    lc = lifecycle()
    out: list[Violation] = []
    for v in lc.validate(_lifecycle_projection(doc)):
        if v.code == "duplicate_check_id":  # reported by this contract for every run, journal or not
            continue
        path = v.path
        for old, new in _PATHS:
            path = path.replace(old, new)
        out.append(Violation(v.code, path, v.message))
    return out


def _check_id_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    seen: set[str] = set()
    for i, row in enumerate(doc["resolution_checks"]):
        if row["check_id"] in seen:
            out.append(_v("duplicate_check_id", f"$.resolution_checks[{i}]", "duplicate resolution check id"))
        seen.add(row["check_id"])
    return out


def validate(doc: Any) -> list[Violation]:
    """Return all violations; an empty list means the document conforms to 0.1.0-draft."""
    out = validate_structure(doc)
    if out:
        return out
    for rule in (_decision_rules, _reference_rules, _attempt_rules, _reconciliation_rules, _closeout_rules,
                 _refusal_rules, _input_and_time_rules, _journal_mode_rules, _reason_label_rules, _floor_and_vocabulary_rules, _check_id_rules,
                 _profile_rules):
        out.extend(rule(doc))
    if not out:
        out.extend(_delegated_rules(doc))
    return out


# --------------------------------------------------------------------------- succession, unfinished checks, extensions

def check_succession(earlier: dict[str, Any], later: dict[str, Any]) -> list[Violation]:
    """Append-only rule between two exports of the same run (the Exchange reference runtime relies on it).

    Every record list of ``earlier`` is a prefix of the same list in ``later``; ``input_time_floors`` never move
    backwards and never lose a key. Both documents must conform on their own.
    """
    out: list[Violation] = []
    if earlier.get("run_id") != later.get("run_id"):
        return [_v("not_append_only", "$.run_id", "successive exports describe the same run")]
    for name in ("decisions", "attempts", "observations", "reconciliations", "refusals", "resolution_checks", "closeouts",
                 "check_events", "vocabulary_changes",
                 "operations", "operation_renewals", "attempt_joins", "rule_revisions", "rule_revision_refusals",
                 "age_extensions", "age_extension_refusals", "recovery_runs"):
        old, new = earlier.get(name, []), later.get(name, [])
        # A journal event may be rewritten only by appending a closing event; rows are never edited in place.
        if new[:len(old)] != old:
            out.append(_v("not_append_only", f"$.{name}", f"{name} of the later export extends the earlier list unchanged"))
    for key, stamp in earlier["input_time_floors"].items():
        newer = later["input_time_floors"].get(key)
        if newer is None or (aware(newer) and aware(stamp) and aware(newer) < aware(stamp)):
            out.append(_v("not_append_only", f"$.input_time_floors.{key}", "input time floors never move backwards or disappear"))
    return out


def unfinished_checks(doc: dict[str, Any]) -> list[str]:
    """Journal check ids that never completed (opened only, or interrupted), in journal order.

    Such a check is evidence that an authority evaluation did not complete. It is valid, and a consumer must
    report it as incomplete rather than read it as an authorization.
    """
    state: dict[str, str] = {}
    order: list[str] = []
    for e in doc.get("check_events", []):
        if e["phase"] == "opened":
            order.append(e["check_id"])
            state[e["check_id"]] = "open"
        elif e["phase"] in {"completed", "interrupted", "expired"}:  # expired: freshness/0.1, terminal
            state[e["check_id"]] = e["phase"]
    return [c for c in order if state[c] in {"open", "interrupted"}]


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
        violations = validate(json.loads(Path(name).read_text(encoding="utf-8")))
        for v in violations:
            print(f"{name}: {v.code} {v.path}: {v.message}")
        code |= bool(violations)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
