"""Reference validator for the Verification report contract (0.1.0-draft).

Stdlib only. A draft: it states the contract executably so the verifier (producer) and the qualification repository (consumer
of the mutation report) can each be tested alone against golden fixtures. It does not import or modify ``odes``.

Layers:

1. Structure: the JSON Schema subset interpreter used by the other drafts.
2. Rules: the document rules in README.md. A report states three-valued verdicts per check with explicit k/n tallies, carries no
   composite score, names its subject (digests of the exact inputs, the pinned canonicalization profile) and its verifier, always
   carries the ``does_not_prove`` block, and may carry per-corpus, per-family mutation tables whose denominators are never pooled.

It is a verification report, not an attestation: nothing here signs, attests or authorizes anything.

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
CONTRACT = "verification-report"
CONTRACT_VERSION = "0.1.0-draft"
CANONICALIZATION_PROFILE = "json-sort-keys-compact-utf8-no-nan-python-semantics-v0.1"
CORE_NON_CLAIMS = (
    "relative_to_pinned_controller", "semantic_quality_not_certified", "receipt_source_bounded",
    "self_consistent_forgery_not_detected", "not_an_attestation", "parse_strictness_is_refusal_not_repair",
    "no_v1_scope_claim", "differential_agreement_is_not_equivalence",
)
MUTATION_NON_CLAIMS = ("no_imported_headline_numbers", "seeds_are_regression_not_detection")
# Tier V3 (witness re-derivation, draft revision 2026-10-18, decision 27): the tier runs only over an outside input and carries one more
# non-claim.
V3_INPUT_ROLES = ("witness", "holder_inventory")
V3_NON_CLAIMS = ("witness_is_not_publication",)
# Optional non-claim (decision 29): permitted in any report, required in none (a report that ran no profile-on sidecar check has nothing to disclaim).
OPTIONAL_NON_CLAIMS = ("profile_sidecar_semantics_only",)
# Family H (damage to the outside-held witness and holder-inventory artifacts, draft revision 2026-10-18, decision 28). Rows of these
# categories are measured only on a witnessed population: a corpus that carries any of them carries only H rows and the two controls
# that make sense there (B, F), and a report with such a corpus also carries a witnessed clean corpus. Denominators of a witnessed
# population are never pooled with those of an unwitnessed one.
WITNESS_CATEGORIES = ("H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8")
WITNESSED_POPULATION_CATEGORIES = WITNESS_CATEGORIES + ("B", "F")


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


def _has_witness_rows(m: dict[str, Any]) -> bool:
    for c in m["family_t"]:
        tables = [c["categories"]] + [sc["categories"] for sc in (c["scenarios"] or [])]
        if any(r["category"] in WITNESS_CATEGORIES for t in tables for r in t):
            return True
    return any(r["category"] in WITNESS_CATEGORIES for c in m["clean"] for r in c["rows"])


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
    """Pinned canonicalization profile: SHA-256 over sorted compact UTF-8 JSON, NaN refused."""
    import hashlib
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _v(code: str, path: str, message: str) -> Violation:
    return Violation(code, path, message)


def render_fraction(fraction: dict[str, Any]) -> str:
    """``k/n``; a zero denominator reads ``n/a (0 ...)``, never a percentage."""
    k, n = fraction["k"], fraction["n"]
    if n == 0:
        return "n/a (0 in denominator)"
    return f"{k}/{n}"


def derived_check_verdict(tally: dict[str, int]) -> str:
    """refuted if any item is refuted; otherwise could_not_check if any could not be checked; otherwise confirmed."""
    if tally["refuted"] > 0:
        return "refuted"
    if tally["could_not_check"] > 0:
        return "could_not_check"
    return "confirmed"


def overall_verdict(doc: dict[str, Any]) -> str:
    """Per-trace outcome used by the mutation harness: ``reject`` (any check refuted), ``abstain`` (none refuted, some could not
    be checked), ``accept`` (every check confirmed). It is derived, not a member and not a score. A verifier crash produces no
    report and is counted as ``error`` by the harness, never as detection."""
    verdicts = [c["verdict"] for c in doc["checks"]]
    if "refuted" in verdicts:
        return "reject"
    if "could_not_check" in verdicts or not verdicts:
        return "abstain"
    return "accept"


# --------------------------------------------------------------------------- document rules

def _document_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    subject, scope = doc["subject"], doc["scope"]
    if aware(doc["generated_at"]) is None:
        out.append(_v("timestamp_invalid", "$.generated_at", "times are timezone-aware"))
    inputs = subject["inputs"]
    keys = [(i["role"], i["name"], i["digest"]) for i in inputs]
    if len({(i["role"], i["name"]) for i in inputs}) != len(inputs):
        out.append(_v("duplicate_input", "$.subject.inputs", "one input per role and name"))
    elif keys != sorted(keys):
        out.append(_v("inputs_not_canonical_order", "$.subject.inputs", "inputs are listed sorted by role, name, digest"))
    if subject["inputs_digest"] != commitment(inputs):
        out.append(_v("subject_digest_mismatch", "$.subject.inputs_digest",
                      "inputs_digest is the commitment over the inputs list exactly as written"))
    roles = {i["role"] for i in inputs}
    v3_ran = "V3" in scope["tiers_run"]
    if v3_ran and not roles & set(V3_INPUT_ROLES):
        out.append(_v("v3_input_missing", "$.scope.tiers_run",
                      "tier V3 re-derives from a witness file or a holder inventory: one of them is an input of the subject"))
    if roles & set(V3_INPUT_ROLES) and not v3_ran:
        out.append(_v("v3_input_without_tier", "$.scope.tiers_run",
                      "a witness or holder inventory input is read by tier V3, which the report says it ran"))
    if not subject["pinned"]["contract_versions"]:
        out.append(_v("pinned_contract_versions_empty", "$.subject.pinned.contract_versions",
                      "a report names the contract draft versions it was checked against"))

    seen: set[str] = set()
    counts = {"confirmed": 0, "could_not_check": 0, "refuted": 0}
    for i, c in enumerate(doc["checks"]):
        p = f"$.checks[{i}]"
        if c["check_id"] in seen:
            out.append(_v("duplicate_check_id", f"{p}.check_id", "check ids are unique"))
        seen.add(c["check_id"])
        if c["tier"] not in scope["tiers_run"]:
            out.append(_v("check_tier_not_run", f"{p}.tier", "a check belongs to a tier the report says it ran"))
        t = c["tally"]
        if t["confirmed"] + t["could_not_check"] + t["refuted"] != t["n"]:
            out.append(_v("tally_sum_mismatch", f"{p}.tally", "confirmed + could_not_check + refuted equals n"))
        elif c["verdict"] != derived_check_verdict(t):
            out.append(_v("check_verdict_inconsistent", f"{p}.verdict",
                          "refuted if any item is refuted, else could_not_check if any could not be checked, else confirmed"))
        if t["could_not_check"] > 0 and c["could_not_check_reason"] is None:
            out.append(_v("could_not_check_unexplained", f"{p}.could_not_check_reason", "an item that could not be checked says why"))
        if t["could_not_check"] == 0 and c["could_not_check_reason"] is not None:
            out.append(_v("could_not_check_reason_unexpected", f"{p}.could_not_check_reason", "a reason without an item that could not be checked"))
        if t["refuted"] > 0 and not c["findings"]:
            out.append(_v("refuted_without_finding", f"{p}.findings", "a refuted check names what refuted it"))
        if t["refuted"] == 0 and c["findings"]:
            out.append(_v("finding_without_refutation", f"{p}.findings", "findings belong to a refuted check"))
        counts[c["verdict"]] += 1
    s = doc["summary"]
    if (s["checks"], s["confirmed"], s["could_not_check"], s["refuted"]) != (
            len(doc["checks"]), counts["confirmed"], counts["could_not_check"], counts["refuted"]):
        out.append(_v("summary_mismatch", "$.summary", "the summary counts the checks as written; it is counts, not a score"))
    if not doc["checks"] and doc["mutation_report"] is None:
        out.append(_v("empty_report", "$.checks", "a report with no check and no mutation report states nothing"))

    ids = [n["id"] for n in doc["does_not_prove"]]
    if len(set(ids)) != len(ids):
        out.append(_v("duplicate_non_claim", "$.does_not_prove", "each non-claim appears once"))
    witness_rows = doc["mutation_report"] is not None and _has_witness_rows(doc["mutation_report"])
    required = list(CORE_NON_CLAIMS) + (list(MUTATION_NON_CLAIMS) if doc["mutation_report"] is not None else []) \
        + (list(V3_NON_CLAIMS) if v3_ran or witness_rows else [])
    for need in required:
        if need not in ids:
            out.append(_v("non_claim_missing", "$.does_not_prove", f"the non-claim {need!r} is mandatory"))
    return out


# --------------------------------------------------------------------------- mutation report rules

def _fraction_range(label: str, f: dict[str, Any] | None, path: str, out: list[Violation]) -> None:
    if f is not None and f["k"] is not None and f["k"] > f["n"]:
        out.append(_v("fraction_out_of_range", path, f"{label}: k exceeds n"))


def _expect(f: dict[str, Any] | None, k: int, n: int) -> bool:
    return f is not None and f["k"] == k and f["n"] == n


def _trace_row_rules(row: dict[str, Any], provenance: str, p: str, out: list[Violation]) -> None:
    v = row["verdicts"]
    n_eff = row["n_eff"]
    if row["n_gen"] - row["n_noop"] - row["n_na"] != n_eff:
        out.append(_v("effective_count_mismatch", p, "n_eff = n_gen - n_noop - n_na (no-op and not-applicable mutants are excluded and counted)"))
        return
    if v["reject"] + v["accept"] + v["abstain"] + v["error"] != n_eff:
        out.append(_v("verdict_sum_mismatch", f"{p}.verdicts", "reject + accept + abstain + error equals n_eff"))
        return
    det, reg, fa, ab, er, mi = (row[k] for k in ("detection", "regression", "false_acceptance", "abstained", "errored", "metric_impact"))
    if row["expected_verdict"] == "not_applicable":
        if n_eff or row["n_gen"] or any(x is not None for x in (det, reg, fa, ab, er, mi)):
            out.append(_v("not_applicable_reports_a_rate", p, "a category with no verifier claim (semantic quality) shows n/a, never a rate"))
        return
    for label, f in (("false_acceptance", fa), ("abstained", ab), ("errored", er)):
        _fraction_range(label, f, f"{p}.{label}", out)
    if det is not None:
        _fraction_range("detection.any_code", det["any_code"], f"{p}.detection.any_code", out)
        _fraction_range("detection.intended_code", det["intended_code"], f"{p}.detection.intended_code", out)
    if reg is not None:
        _fraction_range("regression", reg["refused_with_intended_code"], f"{p}.regression", out)
    if provenance == "seed":
        if det is not None:
            out.append(_v("seed_corpus_reports_detection", f"{p}.detection",
                          "a seed corpus is a regression check: it reports regression, never a detection rate"))
        if mi is not None:
            out.append(_v("seed_corpus_reports_metric_impact", f"{p}.metric_impact", "metric impact is reported on the generated corpus only"))
        if reg is None or not _expect(reg["refused_with_intended_code"], reg["refused_with_intended_code"]["k"], n_eff):
            out.append(_v("regression_mismatch", f"{p}.regression", "seeds refused with the intended code, out of n_eff"))
        elif reg["refused_with_intended_code"]["k"] > v["reject"]:
            out.append(_v("localized_exceeds_detected", f"{p}.regression", "seeds refused with the intended code cannot exceed those rejected"))
    else:
        if reg is not None:
            out.append(_v("generated_corpus_reports_regression", f"{p}.regression", "regression figures belong to the seed corpus"))
        if det is None:
            out.append(_v("rate_missing", f"{p}.detection", "an applicable category on a generated corpus reports detection"))
        elif not _expect(det["any_code"], v["reject"], n_eff):
            out.append(_v("detection_mismatch", f"{p}.detection.any_code", "detection is reject over n_eff; abstain and error are not credited"))
        elif det["intended_code"]["n"] != n_eff or det["intended_code"]["k"] > v["reject"]:
            out.append(_v("localized_exceeds_detected", f"{p}.detection.intended_code", "localized detection is over n_eff and cannot exceed detection"))
        if not _expect(fa, v["accept"], n_eff):
            out.append(_v("false_acceptance_mismatch", f"{p}.false_acceptance", "false acceptance is accept over n_eff (not 1 - detection)"))
        if not _expect(ab, v["abstain"], n_eff):
            out.append(_v("abstained_mismatch", f"{p}.abstained", "abstain is reported on its own line over n_eff"))
        if not _expect(er, v["error"], n_eff):
            out.append(_v("errored_mismatch", f"{p}.errored", "error is reported on its own line over n_eff and is never detection"))
        if mi is None:
            out.append(_v("rate_missing", f"{p}.metric_impact", "an applicable category on a generated corpus reports metric impact (n/a when nothing was accepted)"))
        else:
            ch = mi["changed"]
            if ch["n"] != v["accept"]:
                out.append(_v("metric_impact_denominator_mismatch", f"{p}.metric_impact.changed",
                              "metric impact is conditioned on false acceptance: its denominator is the accepted count"))
            elif (ch["k"] is None) != (ch["n"] == 0):
                out.append(_v("metric_impact_na_inconsistent", f"{p}.metric_impact.changed",
                              "with 0 accepted the field is n/a (k null), never 0; with accepted mutants k is a count"))
            else:
                _fraction_range("metric_impact", ch, f"{p}.metric_impact.changed", out)
                for j, d in enumerate(mi["deltas"]):
                    if ch["k"] is None or d["nonzero_mutants"] > ch["k"] or d["min"] > d["max"]:
                        out.append(_v("delta_inconsistent", f"{p}.metric_impact.deltas[{j}]",
                                      "deltas describe accepted mutants whose measures changed, with min at most max"))


def _category_rows(rows: list[dict[str, Any]], provenance: str, p: str, out: list[Violation]) -> None:
    seen: set[str] = set()
    for i, row in enumerate(rows):
        rp = f"{p}[{i}]"
        if row["category"] in seen:
            out.append(_v("duplicate_category", rp, "one row per category in a corpus (no pooled or repeated denominators)"))
        seen.add(row["category"])
        _trace_row_rules(row, provenance, rp, out)


def _mutation_rules(doc: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    m = doc["mutation_report"]
    ids: set[str] = set()

    def corpus_id(cid: str, p: str) -> None:
        if cid in ids:
            out.append(_v("duplicate_corpus_id", p, "corpus ids are unique across the family S, family T and clean lists"))
        ids.add(cid)

    def witnessed_population(cats: list[str], p: str) -> bool:
        """True for a corpus with any family H row; it may then carry only H rows and the B and F controls (never pooled)."""
        if not any(c in WITNESS_CATEGORIES for c in cats):
            return False
        if any(c not in WITNESSED_POPULATION_CATEGORIES for c in cats):
            out.append(_v("witnessed_corpus_mixed", p,
                          "a witnessed population carries only family H rows and the B and F controls; "
                          "unwitnessed categories are measured on an unwitnessed corpus, and denominators are never pooled"))
        return True

    witnessed_t = False
    for i, c in enumerate(m["family_t"]):
        p = f"$.mutation_report.family_t[{i}]"
        corpus_id(c["corpus_id"], f"{p}.corpus_id")
        _category_rows(c["categories"], c["provenance"], f"{p}.categories", out)
        scenario_cats = [r["category"] for sc in (c["scenarios"] or []) for r in sc["categories"]]
        witnessed_t |= witnessed_population([r["category"] for r in c["categories"]] + scenario_cats, p)
        scenarios = c["scenarios"] or []
        seen_s: set[str] = set()
        for j, s in enumerate(scenarios):
            if s["scenario_id"] in seen_s:
                out.append(_v("duplicate_scenario_id", f"{p}.scenarios[{j}]", "one table per scenario in a corpus"))
            seen_s.add(s["scenario_id"])
            _category_rows(s["categories"], c["provenance"], f"{p}.scenarios[{j}].categories", out)
    for i, c in enumerate(m["family_s"]):
        p = f"$.mutation_report.family_s[{i}]"
        corpus_id(c["corpus_id"], f"{p}.corpus_id")
        seen_src: set[str] = set()
        for j, r in enumerate(c["rows"]):
            rp = f"{p}.rows[{j}]"
            if r["source_id"] in seen_src:
                out.append(_v("duplicate_source_id", rp, "one row per source in a corpus"))
            seen_src.add(r["source_id"])
            if r["detected"] + r["survived"] + r["errored"] != r["n_cases"]:
                out.append(_v("case_sum_mismatch", rp, "detected + survived + errored equals n_cases (control-removal cases, context only)"))
    witnessed_clean = False
    for i, c in enumerate(m["clean"]):
        p = f"$.mutation_report.clean[{i}]"
        corpus_id(c["corpus_id"], f"{p}.corpus_id")
        witnessed_clean |= witnessed_population([r["category"] for r in c["rows"]], p)
        seen_c: set[str] = set()
        for j, r in enumerate(c["rows"]):
            rp = f"{p}.rows[{j}]"
            if r["category"] in seen_c:
                out.append(_v("duplicate_category", rp, "one row per category in a clean corpus"))
            seen_c.add(r["category"])
            _fraction_range("false_rejection", r["false_rejection"], f"{rp}.false_rejection", out)

    if witnessed_t and not witnessed_clean:
        out.append(_v("witnessed_clean_corpus_missing", "$.mutation_report.clean",
                      "family H rows need a witnessed clean corpus (false rejection of family H checks on unmutated witnessed traces), "
                      "separate from the unwitnessed clean corpora"))

    by_role: dict[str, set[str]] = {}
    for i in doc["subject"]["inputs"]:
        by_role.setdefault(i["role"], set()).add(i["digest"])
    if m["operator_set_digest"] not in by_role.get("operator_set", set()):
        out.append(_v("operator_set_input_missing", "$.mutation_report.operator_set_digest",
                      "the operator set the report names is one of the subject's inputs"))
    for group in ("family_t", "clean"):
        for i, c in enumerate(m[group]):
            if c["corpus_digest"] not in by_role.get("corpus", set()):
                out.append(_v("corpus_input_missing", f"$.mutation_report.{group}[{i}].corpus_digest",
                              "every corpus digest the report names is one of the subject's inputs"))
    return out


def _validate(doc: Any) -> list[Violation]:
    """Return all violations; an empty list means the document conforms to 0.1.0-draft."""
    out = validate_structure(doc)
    if out:
        return out
    out.extend(_document_rules(doc))
    if doc["mutation_report"] is not None:
        out.extend(_mutation_rules(doc))
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
