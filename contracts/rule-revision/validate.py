"""Reference validator for the Rule revision contract (0.1.0-draft).

Stdlib only. A draft: it states the contract executably so each side of the boundary can be tested alone
against golden fixtures. It does not import or modify ``odes`` and does not edit the control-plane-journal or
execution-attempt-lifecycle contracts; it is an optional profile layered on them by reference.

Layers:

1. Structure: the JSON Schema subset interpreter (``schema.json`` is the source of truth for members, types,
   enumerations and the closed-member-set rule).
2. Rules: the cross-record rules in README.md, read from the merged opt-in code (Control Plane
   ``rule_revision.py``, ``reason_vocabulary.py`` and ``bounded.py`` at main 83b49b5, which contains #44 at 87f0233;
   ``docs/rule-revision-profile.md`` there; qualification probes #95).
3. Context (optional arguments): the run record (``journal``: decisions, refusals, vocabulary changes) for the rules
   that join identity rows and reports to it, and the configured signer set (``signers``), which is host
   configuration and is not in any record. The run record is NOT re-validated here; note the journal contract at
   0.1.0-draft refuses a run record that carries the profile's members (``undeclared_member``), so this profile
   is carried as a sidecar projection.

``validate`` returns a list of ``Violation`` (empty list means conformant). Refusal codes are stable strings.
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
CONTRACT = "rule-revision"
CONTRACT_VERSION = "0.1.0-draft"
PROFILE = "rule-revision/0.1"
#: Ordered verification levels; a rule identity names the highest level reached before verification stopped.
LEVELS = ("none", "revision_row_present", "signer_independent_and_configured", "digest_matches_signed_revision")
#: The reason that holds a decision when a policy digest does not resolve to ``adopted`` (an existing registry code).
POLICY_UNKNOWN = "policy_status_unknown"


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


def _v(code: str, path: str, message: str) -> Violation:
    return Violation(code, path, message)


def revision_defects(row: dict[str, Any], signers: list[str] | None = None) -> list[str]:
    """Why a row does not count toward adoption (the producer's ``revision_defects``). Empty means it counts.

    ``signers`` is the configured signer set; when it is not given, a signed row by a distinct signer counts.
    """
    if not row.get("signer"):
        return ["unsigned_revision_row"]
    if row["signer"] == row["reviser"]:
        return ["self_signed_revision_row"]
    if signers is not None and row["signer"] not in signers:
        return ["signer_not_configured"]
    return []


def counting_rows(rows: list[dict[str, Any]], rule_ref: str, signers: list[str] | None = None) -> list[dict[str, Any]]:
    """Valid rows of one rule in append order, minus rows superseded by a later valid row."""
    own = [x for x in rows if x["rule_ref"] == rule_ref]
    valid = [x for x in own if not revision_defects(x, signers)]
    superseded = {x["supersedes"] for x in valid if x.get("supersedes")}
    return [x for x in valid if x["revision_id"] not in superseded]


def adopted_digest(rows: list[dict[str, Any]], rule_ref: str, signers: list[str] | None = None) -> str | None:
    live = counting_rows(rows, rule_ref, signers)
    return live[-1]["to_digest"] if live else None


def resolve_rule(rows: list[dict[str, Any]], rule_ref: str, observed_digest: str | None, signers: list[str] | None = None) -> dict[str, Any]:
    """Resolve one rule to ``adopted`` or ``unknown`` over revision rows (the producer's ``resolve_rule``).

    ``unknown`` is never silently ``adopted``: the digest is adopted only when a counting row's ``to_digest`` equals it.
    """
    own = [x for x in rows if x["rule_ref"] == rule_ref]
    findings: list[str] = []
    level = 1 if own else 0
    for r in own:
        findings.extend(d for d in revision_defects(r, signers) if d not in findings)
    live = counting_rows(rows, rule_ref, signers)
    if live:
        level = 2
    adopted = live[-1]["to_digest"] if live else None
    if not live:
        findings.append("no_signed_revision")
    if observed_digest is None:
        findings.append("observed_digest_absent")
    elif live and observed_digest != adopted:
        findings.append("digest_mismatch_with_adopted")
    state = "unknown"
    if live and observed_digest is not None and observed_digest == adopted:
        state, level = "adopted", 3
    return {"rule_ref": rule_ref, "state": state, "observed_digest": observed_digest, "adopted_digest": adopted,
            "verified_through": LEVELS[level], "findings": findings}


def derive_recomputability(row: dict[str, Any]) -> str:
    """``recomputable`` only if the row retains its operands: at least one resolution input, each explicitly missing or
    carrying a non-empty record commitment and non-empty observed values (the producer's ``derive_recomputability``)."""
    inputs = row.get("resolution_inputs", [])
    if inputs and all(x.get("missing") or (x.get("record_commitment") and x.get("observed")) for x in inputs):
        return "recomputable"
    return "typed_only"


def arity_flags(declared: dict[str, int], measured: dict[str, Any]) -> list[dict[str, Any]]:
    """Declared (at signing) and measured arity are both kept; flag a code measured above its declaration or not declared at all."""
    out = []
    for code, m in sorted(measured["codes"].items()):
        if code not in declared:
            out.append({"code": code, "flag": "arity_undeclared", "measured": m["measured"], "as_of": measured["as_of"]})
        elif m["measured"] > declared[code]:
            out.append({"code": code, "flag": "measured_exceeds_declared", "declared": declared[code], "measured": m["measured"],
                        "as_of": measured["as_of"]})
    return out


def adoption_times(rule_revisions: list[dict[str, Any]], vocabulary_changes: list[dict[str, Any]]) -> dict[str, datetime]:
    """Earliest adoption instant per version label: a vocabulary change's ``version`` (``acknowledged_at``) or a
    ``reason_registry`` revision row's ``rule_ref`` (``recorded_at``), counting or not."""
    out: dict[str, datetime] = {}

    def put(label: Any, ts: Any) -> None:
        t = aware(ts)
        if isinstance(label, str) and t is not None and (label not in out or t < out[label]):
            out[label] = t
    for c in vocabulary_changes:
        put(c.get("version"), c.get("acknowledged_at"))
    for r in rule_revisions:
        if r["rule_kind"] == "reason_registry":
            put(r["rule_ref"], r["recorded_at"])
    return out


# --------------------------------------------------------------------------- revision and refusal rules

def _revision_rules(doc: dict[str, Any], signers: list[str] | None) -> list[Violation]:
    out: list[Violation] = []
    rows = doc["rule_revisions"]
    earlier: dict[str, int] = {}
    for i, r in enumerate(rows):
        p = f"$.rule_revisions[{i}]"
        if r["revision_id"] in earlier:
            out.append(_v("duplicate_revision_id", p, "revision ids are unique; rows are appended, never edited"))
        if aware(r["recorded_at"]) is None:
            out.append(_v("timestamp_invalid", f"{p}.recorded_at", "times are timezone-aware"))
        signed = bool(r["signer"])
        if signed and r["signer"] == r["reviser"]:
            out.append(_v("self_signed_row_accepted", p, "a self-signed revision is refused and kept as a refusal row, never accepted"))
        elif signed and signers is not None and r["signer"] not in signers:
            out.append(_v("signer_not_configured", p, "the signer is not in the configured signer set"))
        if r.get("declared_arity") is not None and r["rule_kind"] != "reason_registry":
            out.append(_v("declared_arity_on_non_registry_row", f"{p}.declared_arity", "arity is declared at signing on reason registry rows only"))
        target = None
        unknown_target = False
        if r["supersedes"] is not None:
            j = earlier.get(r["supersedes"])
            target = rows[j] if j is not None else None
            if target is None or target["rule_ref"] != r["rule_ref"]:
                unknown_target = True
                out.append(_v("supersedes_unknown", f"{p}.supersedes", "a row supersedes an earlier row of the same rule"))
        if signed and not unknown_target:
            expected = target["from_digest"] if target is not None else adopted_digest(rows[:i], r["rule_ref"], signers)
            if r["from_digest"] != expected:
                out.append(_v("from_digest_mismatch", f"{p}.from_digest",
                              "from_digest is the digest currently adopted for the rule (or the superseded row's from_digest)"))
        earlier.setdefault(r["revision_id"], i)

    ids = {r["revision_id"] for r in rows}
    seen: set[str] = set()
    for i, x in enumerate(doc["rule_revision_refusals"]):
        p = f"$.rule_revision_refusals[{i}]"
        if x["refusal_id"] in seen:
            out.append(_v("duplicate_refusal_id", p, "refusal ids are unique"))
        seen.add(x["refusal_id"])
        if aware(x["recorded_at"]) is None or aware(x["revision"]["recorded_at"]) is None:
            out.append(_v("timestamp_invalid", p, "times are timezone-aware"))
        reasons, rev = x["reasons"], x["revision"]
        if reasons != sorted(set(reasons)):
            out.append(_v("refusal_reasons_not_canonical", f"{p}.reasons", "reasons are sorted and unique"))
        signer, self_signed = rev["signer"], bool(rev["signer"]) and rev["signer"] == rev["reviser"]
        bad = ("self_signed_revision_row" in reasons) != self_signed
        if "signer_not_configured" in reasons:
            bad = bad or not signer or self_signed or (signers is not None and signer in signers)
        elif signers is not None and signer and not self_signed and signer not in signers:
            bad = True
        bad = bad or ("rule_revision_duplicate" in reasons and rev["revision_id"] not in ids)
        bad = bad or ("rule_revision_supersedes_unknown" in reasons and rev["supersedes"] is None)
        bad = bad or ("rule_revision_from_digest_mismatch" in reasons and not signer)
        if bad:
            out.append(_v("refusal_reason_mismatch", f"{p}.reasons", "each reason names a defect the embedded revision shows (an unsigned row is never refused for its signer)"))
    return out


# --------------------------------------------------------------------------- identity rows

def _identity_rules(doc: dict[str, Any], signers: list[str] | None) -> list[Violation]:
    out: list[Violation] = []
    seen: set[tuple[str, str]] = set()
    for i, row in enumerate(doc["identity_rows"]):
        p = f"$.identity_rows[{i}]"
        key = (row["row_type"], row["row_id"])
        if key in seen:
            out.append(_v("duplicate_identity_row", p, "one identity row per decision or refusal"))
        seen.add(key)
        t = aware(row["recorded_at"])
        if t is None:
            out.append(_v("timestamp_invalid", f"{p}.recorded_at", "times are timezone-aware"))
        ident = row["rule_identity"]
        rules = ident["rules"]
        if ident["unknown"] != sorted(r for r, v in rules.items() if v["state"] != "adopted"):
            out.append(_v("rule_identity_unknown_mismatch", f"{p}.rule_identity.unknown", "unknown lists, sorted, exactly the rules whose state is not adopted"))
        consistent = True
        for ref, st in rules.items():
            q = f"{p}.rule_identity.rules[{ref}]"
            findings = st["findings"]
            if len(set(findings)) != len(findings):
                out.append(_v("duplicate_finding", q, "a finding is listed once"))
                consistent = False
            if (st["state"] == "adopted") != (st["verified_through"] == "digest_matches_signed_revision"):
                out.append(_v("verified_through_state_mismatch", q, "adopted if and only if verification reached digest_matches_signed_revision"))
                consistent = False
                continue
            level = LEVELS.index(st["verified_through"])
            if ("no_signed_revision" in findings) != (level < 2):
                out.append(_v("finding_level_mismatch", q, "no_signed_revision if and only if no signed independent revision row was found (level none or revision_row_present)"))
                consistent = False
                continue
            absent, mismatch = "observed_digest_absent" in findings, "digest_mismatch_with_adopted" in findings
            if absent != (st["digest"] is None) or (mismatch and (st["digest"] is None or level != 2)) \
                    or (level == 2 and st["digest"] is not None and not mismatch):
                out.append(_v("observed_digest_finding_mismatch", q,
                              "observed_digest_absent if and only if the digest is null; digest_mismatch_with_adopted names an observed digest that differs from the adopted one"))
                consistent = False
        if not consistent or t is None or any(aware(r["recorded_at"]) is None for r in doc["rule_revisions"]):
            continue  # no reliable time basis to recompute from (timestamp_invalid is reported on the row itself)
        asof = [r for r in doc["rule_revisions"] if aware(r["recorded_at"]) <= t]
        for ref, st in rules.items():
            res = resolve_rule(asof, ref, st["digest"], signers)
            if (res["state"], res["verified_through"]) != (st["state"], st["verified_through"]):
                out.append(_v("rule_identity_recomputed_mismatch", f"{p}.rule_identity.rules[{ref}]",
                              f"the revision rows recorded by then give {res['state']} through {res['verified_through']}"))
            elif sorted(res["findings"]) != sorted(st["findings"]):
                out.append(_v("rule_identity_findings_mismatch", f"{p}.rule_identity.rules[{ref}]",
                              f"the revision rows recorded by then give findings {res['findings']}"))
    return out


# --------------------------------------------------------------------------- derived reports

def _trend_rules(doc: dict[str, Any], journal: dict[str, Any] | None) -> list[Violation]:
    out: list[Violation] = []
    seen: set[str] = set()
    sources = adoption_times(doc["rule_revisions"], (journal or {}).get("vocabulary_changes", []))
    for i, item in enumerate(doc["trend_reports"]):
        p = f"$.trend_reports[{i}]"
        if item["report_id"] in seen:
            out.append(_v("duplicate_report_id", p, "report ids are unique within a list"))
        seen.add(item["report_id"])
        rep = item["report"]
        flagged = rep.get("rows_predating_adoption")
        annotated = flagged is not None or "flagged_row_count" in rep or any("tainted_for_trend" in s or "taint_reasons" in s for s in rep["series"])
        complete = (flagged is not None and "flagged_row_count" in rep
                    and all("tainted_for_trend" in s and "taint_reasons" in s for s in rep["series"]))
        if annotated and not complete:
            out.append(_v("trend_annotation_incomplete", p, "rows_predating_adoption, flagged_row_count and every series' tainted_for_trend and taint_reasons are all present or all absent"))
            continue
        if not annotated:
            continue
        keys = set()
        for k, f in enumerate(flagged):
            q = f"{p}.report.rows_predating_adoption[{k}]"
            if (f["set"], f["index"]) in keys:
                out.append(_v("duplicate_flagged_row", q, "a row is flagged once"))
            keys.add((f["set"], f["index"]))
            rt, at = aware(f["row_time"]), aware(f["adoption_time"])
            if rt is None or at is None:
                out.append(_v("timestamp_invalid", q, "times are timezone-aware"))
                continue
            if not rt < at:
                out.append(_v("row_not_before_adoption", q, "a flagged row predates its version's adoption instant"))
            known = sources.get(f["version"])
            if known is None:
                if journal is not None:
                    out.append(_v("adoption_source_missing", q, "no reason_registry revision row or vocabulary change adopts this version"))
            elif known != at:
                out.append(_v("adoption_time_mismatch", q, "adoption_time is the earliest adoption row for the version"))
        if rep["flagged_row_count"] != len(keys):
            out.append(_v("flagged_count_mismatch", f"{p}.report.flagged_row_count", "flagged_row_count is the number of distinct flagged rows"))
        flagged_versions = {f["version"] for f in flagged}
        series_versions = {s["version"] for s in rep["series"]}
        for k, s in enumerate(rep["series"]):
            q = f"{p}.report.series[{k}]"
            reasons = s["taint_reasons"]
            if s["tainted_for_trend"] != bool(reasons) or len(set(reasons)) != len(reasons):
                out.append(_v("taint_flag_inconsistent", q, "tainted_for_trend if and only if taint_reasons is non-empty; each reason once"))
                continue
            if "row_predates_adoption" in reasons and s["version"] not in flagged_versions:
                out.append(_v("taint_without_flagged_row", q, "row_predates_adoption needs a flagged row of this version"))
            if journal is not None and "pre_split_count" in reasons and not any(
                    c.get("kind") == "split" and c.get("previous_version") == s["version"] and s["code"] in c.get("previous_codes", [])
                    for c in journal.get("vocabulary_changes", [])):
                out.append(_v("pre_split_without_change", q, "pre_split_count needs a split of this version that retires this code"))
        for v in sorted(flagged_versions & series_versions):
            if not any(s["version"] == v and "row_predates_adoption" in s["taint_reasons"] for s in rep["series"]):
                out.append(_v("flagged_row_without_taint", f"{p}.report.series", f"rows of version {v} are flagged but no series of it is marked row_predates_adoption"))
    return out


def _arity_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    seen: set[str] = set()
    by_id = {r["revision_id"]: r for r in doc["rule_revisions"]}
    for i, a in enumerate(doc["arity_reports"]):
        p = f"$.arity_reports[{i}]"
        if a["report_id"] in seen:
            out.append(_v("duplicate_report_id", p, "report ids are unique within a list"))
        seen.add(a["report_id"])
        m = a["measured"]
        if aware(m["as_of"]) is None:
            out.append(_v("timestamp_invalid", f"{p}.measured.as_of", "times are timezone-aware"))
        for code, c in m["codes"].items():
            shapes = c["shapes"]
            if c["measured"] != len(shapes):
                out.append(_v("measured_count_mismatch", f"{p}.measured.codes[{code}]", "measured is the number of distinct operand shapes"))
            elif any(s != sorted(set(s)) for s in shapes) or shapes != sorted(shapes) or any(shapes[k] == shapes[k + 1] for k in range(len(shapes) - 1)):
                out.append(_v("arity_shapes_invalid", f"{p}.measured.codes[{code}]", "each shape is a sorted list of distinct input types; the shapes are sorted and distinct"))
        if a["declared_from"] is not None:
            row = by_id.get(a["declared_from"])
            if row is None or row["rule_kind"] != "reason_registry":
                out.append(_v("declared_from_unknown", f"{p}.declared_from", "declared_from names a reason_registry revision row of the document"))
            elif row.get("declared_arity") != a["declared"]:
                out.append(_v("declared_arity_mismatch", f"{p}.declared", "declared is the declared_arity of the row it names"))
        if sorted(a["flags"], key=lambda f: f["code"]) != arity_flags(a["declared"], m):
            out.append(_v("arity_flags_mismatch", f"{p}.flags", "flags are exactly measured_exceeds_declared and arity_undeclared derived from declared and measured"))
    return out


def _recomputability_rules(doc: dict[str, Any], journal: dict[str, Any] | None) -> list[Violation]:
    out: list[Violation] = []
    seen: set[str] = set()
    for i, rep in enumerate(doc["recomputability_reports"]):
        p = f"$.recomputability_reports[{i}]"
        if rep["report_id"] in seen:
            out.append(_v("duplicate_report_id", p, "report ids are unique within a list"))
        seen.add(rep["report_id"])
        rows = (journal or {}).get(rep["rows_from"], [])
        for k, f in enumerate(rep["flags"]):
            q = f"{p}.flags[{k}]"
            if f["declared"] == f["derived"] or (f["flag"] == "declared_overclaim") != (f["declared"] == "recomputable"):
                out.append(_v("recomputability_flag_inconsistent", q, "a flag is raised only where declared and derived differ; declared_overclaim is declared recomputable"))
                continue
            if rep["declared_kinds"].get(f["code"]) != f["declared"]:
                out.append(_v("declared_kind_mismatch", q, "declared is the registry's reason_kind for the code, listed in declared_kinds"))
                continue
            if journal is not None:
                if f["row"] >= len(rows):
                    out.append(_v("recomputability_row_missing", q, "the flag names a row of the run record's list"))
                elif f["code"] not in rows[f["row"]].get("reasons", []):
                    out.append(_v("recomputability_code_not_in_row", q, "the flagged code is one of the row's reasons"))
                elif derive_recomputability(rows[f["row"]]) != f["derived"]:
                    out.append(_v("derived_recomputability_mismatch", q, "derived is recomputed from the row's retained inputs"))
    return out


# --------------------------------------------------------------------------- journal context (optional)

def _journal_rules(doc: dict[str, Any], journal: dict[str, Any]) -> list[Violation]:
    if journal.get("run_id") != doc["run_id"]:
        return [_v("journal_run_mismatch", "$.run_id", "the profile document and the run record describe the same run")]
    out: list[Violation] = []
    rows = {"decision": {d["decision_id"]: d for d in journal.get("decisions", [])},
            "refusal": {x["refusal_id"]: x for x in journal.get("refusals", [])}}
    for i, row in enumerate(doc["identity_rows"]):
        p = f"$.identity_rows[{i}]"
        src = rows[row["row_type"]].get(row["row_id"])
        if src is None:
            out.append(_v("identity_row_unknown_row", p, "an identity row names a decision or refusal of the run record"))
            continue
        t_src, t_row = aware(src.get("decided_at") or src.get("recorded_at")), aware(row["recorded_at"])
        if t_src is not None and t_row is not None and t_src != t_row:
            out.append(_v("identity_row_time_mismatch", p, "recorded_at is the row's decided_at (decision) or recorded_at (refusal)"))
        if src.get("rule_identity") != row["rule_identity"]:
            out.append(_v("identity_row_mismatch", p, "the identity row is the row's rule_identity, member for member"))
            continue
        ident = row["rule_identity"]["rules"]
        refs = [x["input_id"] for x in src.get("resolution_inputs", []) if x.get("input_type") == "policy"]
        if any(r not in ident for r in refs):
            out.append(_v("policy_input_without_rule_identity", p, "every policy the row read has a rule identity entry"))
        elif any(ident[r]["state"] != "adopted" for r in refs) and (
                POLICY_UNKNOWN not in src.get("reasons", []) or src.get("result", "hold") != "hold"):
            out.append(_v("unadopted_policy_not_held", p, f"a policy that does not resolve to adopted holds with {POLICY_UNKNOWN}"))
    return out


def validate(doc: Any, journal: dict[str, Any] | None = None, signers: list[str] | None = None) -> list[Violation]:
    """Return all violations; an empty list means the document conforms to 0.1.0-draft.

    ``journal`` is an optional run record (``run_id``, ``decisions``, ``refusals``, ``vocabulary_changes``) for the
    cross-document rules; ``signers`` is the configured signer set (host configuration, in no record) for the signer rules.
    """
    out = validate_structure(doc)
    if out:
        return out
    out.extend(_revision_rules(doc, signers))
    out.extend(_identity_rules(doc, signers))
    out.extend(_trend_rules(doc, journal))
    out.extend(_arity_rules(doc))
    out.extend(_recomputability_rules(doc, journal))
    if journal is not None:
        out.extend(_journal_rules(doc, journal))
    return out


def check_succession(earlier: dict[str, Any], later: dict[str, Any]) -> list[Violation]:
    """Two exports of one run: revision rows, refusal rows and identity rows are append-only (an earlier list is a prefix of the later)."""
    if earlier["run_id"] != later["run_id"]:
        return [_v("not_append_only", "$.run_id", "successive exports describe one run")]
    return [_v("not_append_only", f"$.{name}", "an earlier row was changed, reordered or dropped")
            for name in ("rule_revisions", "rule_revision_refusals", "identity_rows") if later[name][:len(earlier[name])] != earlier[name]]


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
        wrapped = isinstance(data, dict) and "document" in data and "fixture_id" in data
        violations = validate(data["document"] if wrapped else data, data.get("journal") if wrapped else None,
                              data.get("signers") if wrapped else None)
        for v in violations:
            print(f"{name}: {v.code} {v.path}: {v.message}")
        code |= bool(violations)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
