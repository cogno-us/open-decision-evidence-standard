"""Reference validator for the Witness digest contract (0.1.0-draft).

Stdlib only. A draft: it states executably what the Control Plane's opt-in witness emits (``agent_control_plane.witness``, profile
``witness-digest/0.1``, command ``acp witness publish``) so the producer, the independent verifier (tier V3) and any witness holder
can be tested alone against golden fixtures. It does not import or modify ``odes`` or the Control Plane.

The document is the file a witness holds: a JSON array of records, oldest first (the wire form is one JSON object per line).

Layers:

1. Structure: the JSON Schema subset interpreter (``schema.json`` is the source of truth for members, types and the closed-member-set
   rule). A record names its profile in ``version``; a different value is ``unsupported_contract_version``.
2. File rules: the chain the witness keeps over its own records (digest recomputation, contiguity, linkage, one run, counts never
   decrease). Same condition and same code as the Control Plane's ``check_witness_chain`` (``witness_chain_invalid``).
3. Record rules (optional second argument, the run record document the witness covers): the checks of
   ``verify_against_witness`` (``witness_run_mismatch``, ``witness_ledger_shrunk``, ``witness_ledger_head_mismatch``).
   ``coverage`` reports what the latest record covers and which rows came after it; that is information, never a violation.

``validate`` returns a list of ``Violation`` (empty list means conformant). Refusal codes are stable strings; the last four are the
Control Plane's own verdict codes.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "schema.json"
CONTRACT = "witness-digest"
CONTRACT_VERSION = "0.1.0-draft"
PROFILE = "witness-digest/0.1"
GENESIS = "sha256:" + "0" * 64
RECORD_MEMBERS = ("version", "run_id", "sequence", "previous_digest", "ledgers", "digest")


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
    # This schema declares no enumeration, so the interpreter has no enum branch (a closed set added later needs one and a fixture).
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
    if isinstance(doc, list):
        for i, record in enumerate(doc):
            if isinstance(record, dict) and isinstance(record.get("version"), str) and record["version"] != PROFILE:
                return [Violation("unsupported_contract_version", f"$[{i}].version", f"this validator implements {PROFILE} only")]
    out: list[Violation] = []
    _check(doc, schema, schema, "$", out)
    return out


def _v(code: str, path: str, message: str) -> Violation:
    return Violation(code, path, message)


# --------------------------------------------------------------------------- the pinned digest chain

def commitment(value: Any) -> str:
    """The Control Plane's commitment (``bounded.commitment``): SHA-256 over sorted compact UTF-8 JSON, NaN refused."""
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def ledgers(record: Any) -> dict[str, list]:
    """The ledgers of a run record document: every list-valued top-level member, in name order."""
    return {name: value for name, value in sorted(record.items()) if isinstance(value, list)} if isinstance(record, dict) else {}


def chain_heads(rows: list) -> list[str]:
    """``heads[i]`` is the chain head after the first ``i`` rows; ``heads[0]`` is the genesis value."""
    heads = [GENESIS]
    for row in rows:
        heads.append(commitment({"prev": heads[-1], "row": commitment(row)}))
    return heads


def record_digest(record: dict[str, Any]) -> str:
    """A witness record's digest: the commitment of the record without its ``digest`` member (``extensions`` included)."""
    return commitment({k: v for k, v in record.items() if k != "digest"})


def head_digest(record: Any) -> dict[str, dict[str, Any]]:
    """Per-ledger ``{count, head}`` for every non-empty ledger (empty ledgers are omitted)."""
    return {name: {"count": len(rows), "head": chain_heads(rows)[-1]} for name, rows in ledgers(record).items() if rows}


def make_record(record: Any, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """The record to publish after ``previous`` (the witness's latest). A test aid that restates ``witness.make_record``."""
    out = {"version": PROFILE, "run_id": record["run_id"], "sequence": 0 if previous is None else previous["sequence"] + 1,
           "previous_digest": None if previous is None else previous["digest"], "ledgers": head_digest(record)}
    out["digest"] = record_digest(out)
    return out


# --------------------------------------------------------------------------- file rules

def _file_rules(records: list[dict[str, Any]]) -> list[Violation]:
    out: list[Violation] = []
    if not records:
        return [_v("witness_holds_no_digest", "$", "the witness holds no digest; nothing is verified")]
    previous: dict[str, Any] | None = None
    for i, rec in enumerate(records):
        p = f"$[{i}]"
        if rec["digest"] != record_digest(rec):
            out.append(_v("witness_chain_invalid", f"{p}.digest", "the digest does not recompute over the record without its digest member"))
        if rec["sequence"] != i:
            out.append(_v("witness_chain_invalid", f"{p}.sequence", f"sequence {rec['sequence']} is not contiguous (expected {i})"))
        want = None if previous is None else previous["digest"]
        if rec["previous_digest"] != want:
            out.append(_v("witness_chain_invalid", f"{p}.previous_digest", "previous_digest does not link to the record before it (null for the first)"))
        if previous is not None:
            if rec["run_id"] != previous["run_id"]:
                out.append(_v("witness_chain_invalid", f"{p}.run_id", "run_id differs from the record before it"))
            for name, old in previous["ledgers"].items():
                new = rec["ledgers"].get(name)
                if new is None or new["count"] < old["count"]:
                    out.append(_v("witness_chain_invalid", f"{p}.ledgers.{name}", "the ledger covers fewer rows than the record before it"))
        previous = rec
    return out


# --------------------------------------------------------------------------- record rules

def _record_rules(records: list[dict[str, Any]], run_record: Any) -> list[Violation]:
    out: list[Violation] = []
    run_id = run_record.get("run_id") if isinstance(run_record, dict) else None
    for i, rec in enumerate(records):
        if rec["run_id"] != run_id:
            out.append(_v("witness_run_mismatch", f"$[{i}].run_id", "the witness holds a chain for a different run than the record"))
            break
    if out:
        return out
    rows_by = ledgers(run_record)
    heads: dict[str, list[str]] = {}
    for i, rec in enumerate(records):
        for name, held in sorted(rec["ledgers"].items()):
            rows = rows_by.get(name, [])
            if name not in heads:
                heads[name] = chain_heads(rows)
            count = held["count"]
            if len(rows) < count:
                out.append(_v("witness_ledger_shrunk", f"$[{i}].ledgers.{name}",
                              f"the record holds {len(rows)} rows of {name}; the digest covers {count} (a covered row was dropped)"))
            elif heads[name][count] != held["head"]:
                out.append(_v("witness_ledger_head_mismatch", f"$[{i}].ledgers.{name}",
                              "the chain head over the first rows the digest covers differs (a covered row was rewritten, reordered, or dropped and replaced)"))
    return out


def coverage(records: list[dict[str, Any]], run_record: Any) -> dict[str, Any]:
    """What the latest record covers and what came after it: ``witnessed_through`` (ledger to rows covered) and ``unwitnessed_rows``
    (ledger to rows the record holds beyond that). Information only: unwitnessed rows are not a violation and not shown intact."""
    through = {name: held["count"] for name, held in sorted(records[-1]["ledgers"].items())} if records else {}
    extra = {name: len(rows) - through.get(name, 0) for name, rows in ledgers(run_record).items() if len(rows) > through.get(name, 0)}
    return {"witnessed_through": through, "unwitnessed_rows": extra}


def validate(doc: Any, record: Any = None) -> list[Violation]:
    """Return all violations; an empty list means the witness file conforms to 0.1.0-draft (and, with ``record``, matches it).

    Like the Control Plane's verifier, the record rules run only when the chain and the run id are sound."""
    out = validate_structure(doc)
    if out:
        return out
    out.extend(_file_rules(doc))
    if record is not None and not out:
        out.extend(_record_rules(doc, record))
    return out


def canonical_bytes(doc: Any) -> bytes:
    """Digest input: the whole document including every `extensions` member, never a projection."""
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def known_view(doc: Any) -> Any:
    """What a consumer of this version acts on: declared members only (extensions excluded from logic)."""
    def strip(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k != "extensions"}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value
    return strip(doc)


def preserve(doc: Any) -> Any:
    """Consumers re-emit what they received: ignore-but-preserve means a faithful deep copy."""
    return json.loads(json.dumps(doc))


def main(argv: list[str]) -> int:
    """Each argument is a fixture, a JSON array of records, or a JSON-lines witness file (``--record FILE`` names the run record)."""
    code = 0
    args = list(argv)
    record = None
    if "--record" in args:
        i = args.index("--record")
        record = json.loads(Path(args[i + 1]).read_text(encoding="utf-8"))
        del args[i:i + 2]
    for name in args:
        text = Path(name).read_text(encoding="utf-8")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = [json.loads(line) for line in text.splitlines() if line.strip()]
        wrapped = isinstance(data, dict) and "document" in data and "fixture_id" in data
        violations = validate(data["document"] if wrapped else data, data.get("record") if wrapped else record)
        for v in violations:
            print(f"{name}: {v.code} {v.path}: {v.message}")
        code |= bool(violations)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
