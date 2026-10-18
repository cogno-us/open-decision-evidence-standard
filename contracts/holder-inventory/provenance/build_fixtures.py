"""Write the fixtures of the holder-inventory contract.

Raw material comes from ``contracts/witness-digest/provenance/capture_fixtures.py`` (one capture serves both drafts): the inventory
documents are the Control Plane's ``HolderInventory.model_dump(mode="json")`` unchanged, and ``decision.json`` is the first decision
of the run that used (or lacked) the inventory. Valid fixtures are captures except where the ``reason`` says DERIVED; the invalid ones
are single-defect mutations. Run from the repository root:

    python contracts/holder-inventory/provenance/build_fixtures.py <raw-dir from the witness-digest capture>
"""
import copy
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTRACT_DIR = HERE.parent
_spec = importlib.util.spec_from_file_location("hi_validate", CONTRACT_DIR / "validate.py")
hi = importlib.util.module_from_spec(_spec)
sys.modules["hi_validate"] = hi
_spec.loader.exec_module(hi)


def write(kind, fid, payload):
    (CONTRACT_DIR / "fixtures" / kind / f"{fid}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(raw: Path) -> int:
    cp = json.loads((raw / "capture.json").read_text(encoding="utf-8"))["control_plane_revision"][:8]
    load = lambda scenario, name: json.loads((raw / scenario / name).read_text(encoding="utf-8"))
    two = load("holder-inventory-enumerated", "holder-inventory.json")
    none = load("holder-inventory-empty-held", "holder-inventory.json")
    prov = lambda scenario: {"source": "control-plane-capture", "control_plane_revision": cp, "scenario": scenario}
    valid = {}

    def add_valid(fid, reason, doc, provenance, context=None):
        valid[fid] = {"fixture_id": fid, "synthetic": True, "expected_outcome": "accept", "reason": reason, "expected_refusal": None,
                      "provenance": provenance, "document": doc}
        if context is not None:
            valid[fid]["context"] = context

    ctx_two = load("holder-inventory-enumerated", "decision.json")
    ctx_none = load("holder-inventory-empty-held", "decision.json")
    add_valid("two-holders-routed-and-self-credentialed", "The inventory of a captured run: one routed holder and one self-credentialed holder. `context` is that run's decision: the action class requires revocation assurance and the decision was authorized, because an inventory that enumerates a holder exists.",
              two, prov("holder-inventory-enumerated"), ctx_two)
    add_valid("enumerates-no-holder", "Valid in shape and claims nothing: the inventory of a captured run in which the same flagged class was held with `holder_inventory_missing`. The profile counts an inventory only if it enumerates at least one holder.",
              none, prov("holder-inventory-empty-held"), ctx_none)
    ref = copy.deepcopy(two)
    ref["holders"][1]["credential_ref"] = "vault://refunds/destination-key"
    add_valid("holder-with-a-credential-reference", "DERIVED from the capture: `credential_ref` set on the self-credentialed holder. It is a reference, never a secret, and nothing here resolves or checks it.",
              ref, {**prov("holder-inventory-enumerated"), "derived": "credential_ref set"})
    other = copy.deepcopy(two)
    other["holders"].append({"holder_id": "h-other", "kind": "other", "enforcement_point": "unspecified", "credential_ref": None})
    add_valid("holder-of-kind-other", "DERIVED from the capture: a holder of kind `other` (neither a routed nor a self-credentialed claim is made).",
              other, {**prov("holder-inventory-enumerated"), "derived": "third holder of kind other"})
    dup = copy.deepcopy(two)
    dup["holders"].append(copy.deepcopy(dup["holders"][0]))
    add_valid("repeated-holder-id-is-not-refused", "DERIVED from the capture: the same holder_id listed twice. The profile defines no uniqueness rule and the Control Plane accepts it, so this contract does not refuse it (README, Not checked here).",
              dup, {**prov("holder-inventory-enumerated"), "derived": "first holder listed twice"})
    ext = copy.deepcopy(two)
    ext["extensions"] = {"x-source": "host-config"}
    ext["holders"][0]["extensions"] = {"x-owner": "payments"}
    add_valid("extension-namespace-members-preserved", "DERIVED from the capture: `x-` members on the inventory and on a holder. Ignored for contract logic, preserved, part of the digest. The producer emits none and its own model refuses them (README, Divergences).",
              ext, {**prov("holder-inventory-enumerated"), "derived": "x- members added"})
    for fid, fx in valid.items():
        assert hi.validate(fx["document"]) == [], (fid, hi.validate(fx["document"]))
        if "context" in fx:
            flagged = fx["context"]["class_requires_revocation_assurance"]
            assert hi.class_holds(fx["document"], flagged) == fx["context"]["reasons"], fid
            assert (fx["context"]["result"] == "authorized") == (not hi.class_holds(fx["document"], flagged)), fid
        write("valid", fid, fx)

    out = {}

    def add(fid, code, fn, reason, base=two):
        doc = copy.deepcopy(base)
        fn(doc)
        out[fid] = (code, reason, doc)

    add("inventory-member-undeclared", "undeclared_member", lambda x: x.update({"holder_count": 2}), "The inventory is a closed object; a member the profile does not declare is refused, never dropped.")
    add("holder-member-undeclared", "undeclared_member", lambda x: x["holders"][0].update({"secret": "s"}), "A holder is a closed object (the Control Plane's model forbids extra members); a credential value has no member here.")
    add("extension-key-without-x-prefix", "invalid_extension_key", lambda x: x.update({"extensions": {"note": 1}}), "Extension names start with x-.")
    add("version-is-another-profile", "unsupported_contract_version", lambda x: x.update({"version": "holder-inventory/0.2"}), "Only holder-inventory/0.1 is implemented.")
    add("version-not-a-string", "schema_violation", lambda x: x.update({"version": 1}), "The version is the profile id string.")
    add("kind-expired", "unknown_enum_value", lambda x: x["holders"][0].update({"kind": "expired"}), "Holder kinds are routed, self_credentialed and other; a lifecycle word is not a kind (the inventory never says a holder expired).")
    add("kind-missing", "schema_violation", lambda x: x["holders"][0].pop("kind"), "A holder states its kind.")
    add("enforcement-point-empty", "schema_violation", lambda x: x["holders"][0].update({"enforcement_point": ""}), "A holder names where its authority is enforced.")
    add("holder-id-too-long", "schema_violation", lambda x: x["holders"][0].update({"holder_id": "h" * 257}), "At most 256 characters.")
    add("credential-ref-not-a-string", "schema_violation", lambda x: x["holders"][0].update({"credential_ref": 5}), "credential_ref is null or a string.")
    add("credential-ref-member-missing", "schema_violation", lambda x: x["holders"][0].pop("credential_ref"), "The producer always writes credential_ref (null when unset), so it is a required nullable member here; the producer's own model would accept its absence (README default 5).")
    add("recorded-by-empty", "schema_violation", lambda x: x.update({"recorded_by": ""}), "An inventory names who recorded it.")
    add("inventory-id-missing", "schema_violation", lambda x: x.pop("inventory_id"), "An inventory has an id.")
    add("holders-not-a-list", "schema_violation", lambda x: x.update({"holders": {}}), "holders is a list.")
    add("holders-member-missing", "schema_violation", lambda x: x.pop("holders"), "holders is required, even when empty.")
    add("recorded-at-naive", "timestamp_invalid", lambda x: x.update({"recorded_at": "2026-10-05T19:00:00"}), "Times carry a UTC offset (stricter than the producer, README default 4).")
    add("recorded-at-not-a-time", "timestamp_invalid", lambda x: x.update({"recorded_at": "yesterday"}), "recorded_at is a time.")
    out["document-is-a-list"] = ("schema_violation", "The document is one inventory object, not a list of holders.", copy.deepcopy(two["holders"]))
    failures = []
    for fid, (code, reason, doc) in out.items():
        got = [v.code for v in hi.validate(doc)]
        if got != [code]:
            failures.append((fid, code, got))
            continue
        write("invalid", fid, {"fixture_id": fid, "synthetic": True, "expected_outcome": "reject", "reason": reason, "expected_refusal": code,
                               "provenance": {"source": "single-defect mutation of a Control Plane capture", "control_plane_revision": cp}, "document": doc})
    for f in failures:
        print("FAIL", f)
    print(f"valid {len(valid)} invalid {len(out)} failures {len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    for kind in ("valid", "invalid"):
        (CONTRACT_DIR / "fixtures" / kind).mkdir(parents=True, exist_ok=True)
        for old in (CONTRACT_DIR / "fixtures" / kind).glob("*.json"):
            old.unlink()
    raise SystemExit(main(Path(sys.argv[1]).resolve()))
