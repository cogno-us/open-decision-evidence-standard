"""Build the destination-ledger fixtures from captured raw ledgers (step 2 of 2; step 1 is capture_fixtures.py).

Not a test and not vendored. Usage: ``python build_fixtures.py <raw-dir> <contract-dir>``. Valid fixtures are the captured
ledgers unchanged (plus three derived from them, marked in their reason); invalid fixtures are single-defect mutations of the
valid ones. Every outcome is asserted against ``validate.py`` as the file is written.
"""
import copy
import importlib.util
import json
import sys
from pathlib import Path

raw, contract = Path(sys.argv[1]), Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("dl_validate", contract / "validate.py")
dl = importlib.util.module_from_spec(spec)
sys.modules["dl_validate"] = dl
spec.loader.exec_module(dl)

CP = {"source": "control-plane-capture", "control_plane_commit": "128eaa5", "scenario": None}
OR = {"source": "orchestrator-overlay-capture", "orchestrator_commit": "ad79749", "control_plane_commit": "128eaa5",
      "runtime_commit": "d90a2ca", "verifier_commit": "5ed1ffb", "scenario": None}


def load(name):
    return json.loads((raw / name).read_text(encoding="utf-8"))


def prov(base, scenario):
    return {**base, "scenario": scenario}


def write(kind, fixture_id, reason, document, expected_refusal=None, provenance=None, observations=None):
    fx = {"fixture_id": fixture_id, "synthetic": True, "expected_outcome": "accept" if kind == "valid" else "reject",
          "reason": reason, "expected_refusal": expected_refusal, "provenance": provenance or {"source": "mutation"}}
    if observations is not None:
        fx["observations"] = observations
    fx["document"] = document
    found = [v.code for v in dl.validate(document, observations)]
    assert found == ([] if kind == "valid" else [expected_refusal]), (fixture_id, found)
    path = contract / "fixtures" / kind / f"{fixture_id}.json"
    path.write_text(json.dumps(fx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


for kind in ("valid", "invalid"):
    for old in (contract / "fixtures" / kind).glob("*.json"):
        old.unlink()
    (contract / "fixtures" / kind).mkdir(parents=True, exist_ok=True)

obs = load("orch-b-applied.observations.json")
V = {}


def valid(fid, reason, doc, provenance, observations=None):
    V[fid] = (doc, provenance, observations)
    write("valid", fid, reason, doc, provenance=provenance, observations=observations)


valid("control-plane-acp-run-applied",
      "Real `acp run` on the Control Plane's own examples/acp_run authorized inputs (fixed --now, throwaway store): the local destination snapshot (destination.json) unchanged. One applied row, no operation_digest, no operations member (default record).",
      load("cp-acp-run-authorized.json"), prov(CP, "acp-run-authorized"))
valid("control-plane-acp-run-held",
      "Real `acp run` on the held inputs: the destination was never reached, so the snapshot is the initial empty ledger.",
      load("cp-acp-run-held.json"), prov(CP, "acp-run-held"))
valid("control-plane-partial-effect",
      "Real LocalRefundDestination.apply(partial=True) in a throwaway store. The row state is `partial`; effect id is a placeholder chosen by the capture script.",
      load("cp-partial.json"), prov(CP, "destination-partial"))
valid("control-plane-operations-member",
      "Real LocalRefundDestination.apply with an operation_id (opt-in operation-identity/0.1): the snapshot gains the optional `operations` member mapping the operation id to the effect id. Rows still carry no operation_digest. Effect id is a placeholder chosen by the capture script.",
      load("cp-operations.json"), prov(CP, "destination-operations"))
valid("orchestrator-projection-a-without-operation-digest",
      "The orchestrator's projection A (overlay test, gap report F-1) of the runtime SQLite effect row for the adapter-route applied scenario: the row omits operation_digest. Valid, and byte-identical to a default record.",
      load("orch-a-applied.json"), prov(OR, "candidate-journal/off/applied, projection A"))
valid("orchestrator-projection-a-held-empty",
      "Projection A for the held scenario: no effect rows, empty counts.",
      load("orch-a-held.json"), prov(OR, "candidate-journal/off/held, projection A"))
valid("orchestrator-projection-b-with-operation-digest",
      "The orchestrator's projection B (gap report F-1): the same row keeps the runtime's operation_digest, `sha256:` plus 64 lowercase hex. Refused by the verifier's closed row at 5ed1ffb (ledger_shape); valid here by decision 25-A.",
      load("orch-b-applied.json"), prov(OR, "candidate-journal/off/applied, projection B"))
valid("orchestrator-projection-b-two-effects-one-operation",
      "Projection B for the legacy renewal race (identity off): two rows for one business operation under two effect ids, each with its own operation_digest, grant count 2. The ledger records both; this contract does not call it an error (that is the operation-identity profile's concern).",
      load("orch-b-renewal-race.json"), prov(OR, "candidate-destinations/renewal_race_identity_off, projection B"))
valid("orchestrator-atomic-route-projection",
      "The projection of the runtime route's effect rows for the atomic claim route (applied scenario), as written by the overlay (ledger-projection.json): no operation_digest.",
      load("orch-atomic-applied.json"), prov(OR, "candidate-handoff/applied"))
valid("row-digest-agrees-with-observation",
      "Projection B with the run record's accepted `applied` reconciliations (observation context, copied unchanged): the row and the destination_state carry the same operation_digest, so the cross-check passes.",
      load("orch-b-applied.json"), prov(OR, "candidate-journal/off/applied, projection B + reconciliations"), obs)
valid("row-without-digest-observation-with-digest",
      "Projection A with the same observations: only the observation carries operation_digest, so nothing is compared (the verifier reports could-not-check for that pairing; this contract has no rule about it).",
      load("orch-a-applied.json"), prov(OR, "candidate-journal/off/applied, projection A + reconciliations"), obs)
mixed = copy.deepcopy(load("orch-b-renewal-race.json"))
first = next(iter(mixed["effects"]))
del mixed["effects"][first]["operation_digest"]
valid("rows-with-and-without-digest-in-one-ledger",
      "Derived from the captured renewal-race projection B by deleting operation_digest from the first row only: a ledger may mix rows with and without the optional member.",
      mixed, {"source": "derived", "from": "orchestrator-projection-b-two-effects-one-operation"})
ext = copy.deepcopy(load("cp-acp-run-authorized.json"))
ext["extensions"] = {"x-exporter": {"name": "example"}}
next(iter(ext["effects"].values()))["extensions"] = {"x-note": "kept"}
valid("extension-namespace-members-preserved",
      "Derived from the captured acp run ledger by adding `extensions` members (document and row) with x- names: accepted, ignored by logic, preserved and part of the digest input. The verifier at 5ed1ffb has no extensions member and refuses this document (ledger_shape).",
      ext, {"source": "derived", "from": "control-plane-acp-run-applied"})


def mutate(base, fn):
    doc, _, observations = V[base]
    doc = copy.deepcopy(doc)
    fn(doc)
    return doc, observations


def invalid(fid, base, reason, refusal, fn):
    doc, observations = mutate(base, fn)
    write("invalid", fid, reason, doc, refusal, observations=observations)


A = "control-plane-acp-run-applied"
B = "orchestrator-projection-b-with-operation-digest"
BB = "orchestrator-projection-b-two-effects-one-operation"
row = lambda d: next(iter(d["effects"].values()))  # noqa: E731


def put(path_fn, value):
    def go(d):
        r = row(d)
        r[path_fn] = value
    return go


def drop(name):
    def go(d):
        del row(d)[name]
    return go


write("invalid", "document-not-an-object", "The export is a JSON array, not an object.", [], "schema_violation")
invalid("effects-missing", A, "Required member `effects` is absent.", "schema_violation", lambda d: d.pop("effects"))
invalid("grant-effect-counts-missing", A, "Required member `grant_effect_counts` is absent.", "schema_violation", lambda d: d.pop("grant_effect_counts"))
invalid("effects-not-an-object", A, "`effects` is an array.", "schema_violation", lambda d: d.__setitem__("effects", []))
invalid("grant-effect-counts-not-an-object", A, "`grant_effect_counts` is an array.", "schema_violation", lambda d: d.__setitem__("grant_effect_counts", []))
invalid("row-not-an-object", A, "A row is a string.", "schema_violation", lambda d: d["effects"].__setitem__(next(iter(d["effects"])), "applied"))
for name in ("effect_id", "grant_id", "target", "amount", "unit", "payload", "state"):
    invalid(f"row-missing-{name.replace('_', '-')}", A, f"Required row member `{name}` is absent.", "schema_violation", drop(name))
for name, value, label in (("effect_id", 7, "number"), ("grant_id", None, "null"), ("target", ["t"], "array"), ("amount", "50.0", "string"),
                           ("amount", True, "boolean"), ("unit", 1, "number"), ("payload", [], "array"), ("payload", None, "null"),
                           ("state", False, "boolean")):
    invalid(f"row-{name.replace('_', '-')}-wrong-type-{label}", A, f"Row member `{name}` is a {label}, not its declared type.", "schema_violation", put(name, value))
invalid("row-undeclared-member", A, "A row carries `note`, which is neither declared nor inside `extensions`.", "undeclared_member", put("note", "x"))
invalid("document-undeclared-member", A, "The export carries `generated_at`, which is neither declared nor inside `extensions`.", "undeclared_member", lambda d: d.__setitem__("generated_at", "2026-10-05T19:00:00Z"))
invalid("document-extension-key-without-x-prefix", A, "A document `extensions` key without the reserved x- form.", "invalid_extension_key", lambda d: d.__setitem__("extensions", {"exporter": 1}))
invalid("row-extension-key-without-x-prefix", A, "A row `extensions` key without the reserved x- form.", "invalid_extension_key", put("extensions", {"note": 1}))
invalid("count-negative", A, "A per-grant count is negative.", "schema_violation", lambda d: d["grant_effect_counts"].__setitem__(next(iter(d["grant_effect_counts"])), -1))
invalid("count-not-an-integer", A, "A per-grant count is a float.", "schema_violation", lambda d: d["grant_effect_counts"].__setitem__(next(iter(d["grant_effect_counts"])), 1.0))
invalid("count-a-string", A, "A per-grant count is a string.", "schema_violation", lambda d: d["grant_effect_counts"].__setitem__(next(iter(d["grant_effect_counts"])), "1"))
invalid("operations-not-an-object", "control-plane-operations-member", "`operations` is an array.", "schema_violation", lambda d: d.__setitem__("operations", []))
invalid("operations-value-not-a-string", "control-plane-operations-member", "An `operations` value is not a string.", "schema_violation", lambda d: d["operations"].__setitem__("op-order-100/refund-1", 1))
for fid, value, why in (
        ("operation-digest-wrong-type-number", 12345, "a number"),
        ("operation-digest-null", None, "null (an absent member is valid, an explicit null is not)"),
        ("operation-digest-empty", "", "an empty string"),
        ("operation-digest-bare-hex", "23e63e113d1793a22f42e4347620115d97d84aec119a5871a5f5c935252ffda9", "bare hex without the `sha256:` prefix"),
        ("operation-digest-wrong-prefix", "sha-256:23e63e113d1793a22f42e4347620115d97d84aec119a5871a5f5c935252ffda9", "a different prefix"),
        ("operation-digest-uppercase-hex", "sha256:23E63E113D1793A22F42E4347620115D97D84AEC119A5871A5F5C935252FFDA9", "uppercase hex (the runtime emits lowercase)"),
        ("operation-digest-short-hex", "sha256:23e63e113d1793a22f42e4347620115d97d84aec", "hex of the wrong length"),
        ("operation-digest-not-hex", "sha256:" + "g" * 64, "non-hex characters"),
        ("operation-digest-trailing-newline", "sha256:23e63e113d1793a22f42e4347620115d97d84aec119a5871a5f5c935252ffda9\n", "a trailing newline")):
    invalid(fid, B, f"Row `operation_digest` is {why}: it must be `sha256:` plus 64 lowercase hex (documented default).", "schema_violation", put("operation_digest", value))


def rekey(d):
    r = d["effects"].pop(next(iter(d["effects"])))
    d["effects"]["sha256:" + "0" * 64] = r


invalid("row-key-differs-from-effect-id", A, "The row is keyed by an id other than its own effect_id.", "ledger_key_mismatch", rekey)
invalid("count-higher-than-rows", A, "The per-grant count says 2, the rows say 1.", "ledger_count_mismatch", lambda d: d["grant_effect_counts"].__setitem__(next(iter(d["grant_effect_counts"])), 2))
invalid("count-lower-than-rows", BB, "The per-grant count says 1, the rows say 2.", "ledger_count_mismatch", lambda d: d["grant_effect_counts"].__setitem__(next(iter(d["grant_effect_counts"])), 1))
invalid("count-missing-for-a-grant-with-rows", A, "A grant has a row but no count entry (an absent count is read as 0).", "ledger_count_mismatch", lambda d: d["grant_effect_counts"].clear())
invalid("count-for-a-grant-without-rows", A, "A count names a grant that has no row.", "ledger_count_mismatch", lambda d: d["grant_effect_counts"].__setitem__("urn:cognous:grant:other", 1))
invalid("row-digest-differs-from-observation", "row-digest-agrees-with-observation",
        "The row's operation_digest differs from the accepted observation's destination_state.operation_digest (decision 25-A cross-check).",
        "operation_digest_mismatch", put("operation_digest", "sha256:" + "f" * 64))
