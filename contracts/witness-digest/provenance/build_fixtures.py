"""Write the fixtures of the witness-digest contract (step 2 of 2; step 1 is capture_fixtures.py).

The valid fixtures are captured: witness files written by the Control Plane's ``acp witness publish`` / ``publish_head`` over run
records the Control Plane wrote, unchanged, with the run record each covers. Two are derived from captures and say so in their
``reason`` (the ``extensions`` fixture and the single-record file). The invalid fixtures are single-defect mutations of the valid
ones; where a mutation changes a witness record's content the chain is re-computed so that exactly one rule is broken. Run from the
repository root:

    python contracts/witness-digest/provenance/build_fixtures.py <raw-dir from capture_fixtures.py>
"""
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTRACT_DIR = HERE.parent
_spec = importlib.util.spec_from_file_location("wd_validate", CONTRACT_DIR / "validate.py")
wd = importlib.util.module_from_spec(_spec)
sys.modules["wd_validate"] = wd
_spec.loader.exec_module(wd)


def d(label):
    return "sha256:" + hashlib.sha256(label.encode()).hexdigest()


def jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def rechain(records, start=0):
    """Recompute the digest of every record from ``start`` on, keeping the members as written (so the chain defect, if any, is the
    only one)."""
    for rec in records[start:]:
        rec["digest"] = wd.record_digest(rec)
    return records


def write(kind, fid, payload):
    path = CONTRACT_DIR / "fixtures" / kind / f"{fid}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(raw: Path) -> int:
    meta = json.loads((raw / "capture.json").read_text(encoding="utf-8"))
    cp = meta["control_plane_revision"][:8]
    prov = lambda scenario, how: {"source": "control-plane-capture", "control_plane_revision": cp, "scenario": scenario, "how": how}

    def load(scenario, witness="witness.jsonl"):
        return jsonl(raw / scenario / witness), json.loads((raw / scenario / "record.json").read_text(encoding="utf-8"))

    def cp_verdict(scenario, name="verify-output.json"):
        v = json.loads((raw / scenario / name).read_text(encoding="utf-8"))
        return {"witnessed_through": v["witnessed_through"], "unwitnessed_rows": v["unwitnessed_rows"]}

    auth_w, auth_r = load("acp-run-authorized")
    held_w, held_r = load("acp-run-held")
    stg_w, stg_r = load("staged-journal-applied")
    first_w, _ = load("staged-journal-applied", "witness-first-only.jsonl")
    inv_w, inv_r = load("holder-inventory-enumerated")
    valid = {}

    def add_valid(fid, reason, doc, record, provenance, coverage=None):
        valid[fid] = {"fixture_id": fid, "synthetic": True, "expected_outcome": "accept", "reason": reason, "expected_refusal": None,
                      "provenance": provenance, "document": doc}
        if record is not None:
            valid[fid]["record"] = record
        if coverage is not None:
            valid[fid]["expected_coverage"] = coverage

    add_valid("acp-run-authorized-one-record", "One record published by `acp witness publish` over the record store of an authorized and applied `acp run`; it covers every row, so nothing is unwitnessed.",
              auth_w, auth_r, prov("acp-run-authorized", "acp run, then acp witness publish"), cp_verdict("acp-run-authorized"))
    add_valid("acp-run-held-one-record", "One record over the store of a held `acp run`: empty ledgers (attempts, observations, reconciliations, refusals, closeouts) are omitted from the record.",
              held_w, held_r, prov("acp-run-held", "acp run, then acp witness publish"), cp_verdict("acp-run-held"))
    add_valid("staged-two-records-chained", "Two records published by the same witness, after the decision and again after execution: sequence 0 and 1, the second linked to the first, counts that never decrease; the record is covered through its end.",
              stg_w, stg_r, prov("staged-journal-applied", "publish_head after decide, publish_head after execute"), cp_verdict("staged-journal-applied", "verify-output-witness.json"))
    add_valid("first-publication-only-leaves-rows-unwitnessed", "The first of the two records against the record as it stands after execution: valid, and the rows appended since (attempts, observations, reconciliations and later check and resolution rows) are reported as unwitnessed, not as intact.",
              first_w, stg_r, prov("staged-journal-applied", "the first line of the staged witness"), cp_verdict("staged-journal-applied", "verify-output-witness-first-only.json"))
    add_valid("witness-file-alone-two-records", "The staged witness file validated without any run record: the chain rules only.",
              stg_w, None, prov("staged-journal-applied", "witness.jsonl as written"))
    add_valid("run-with-holder-inventory-journal-mode", "One record over a journal-mode run whose action class requires revocation assurance (an inventory of two holders was configured): the witness covers the journal ledgers `check_events` and `resolution_checks` like any other list-valued ledger.",
              inv_w, inv_r, prov("holder-inventory-enumerated", "publish_head over the run record"))
    ext = copy.deepcopy(stg_w)
    ext[0]["extensions"] = {"x-publisher-note": "after decision"}
    ext[1]["extensions"] = {"x-publisher-note": "after execution"}
    rechain(ext)
    ext[1]["previous_digest"] = ext[0]["digest"]
    rechain(ext, 1)
    add_valid("extension-namespace-members-preserved", "DERIVED from the staged capture: `x-` members added to both records and the chain re-computed (the digest covers extensions). Ignored for contract logic, preserved, part of the digest. The producer emits no extensions (README, Divergences).",
              ext, stg_r, prov("staged-journal-applied", "derived: x- members added, digests re-computed"))
    for fid, fx in valid.items():
        got = wd.validate(fx["document"], fx.get("record"))
        assert got == [], (fid, got)
        if "expected_coverage" in fx:
            assert wd.coverage(fx["document"], fx["record"]) == fx["expected_coverage"], fid
        write("valid", fid, fx)

    out = {}

    def add(fid, code, doc, record, fn, reason):
        doc = copy.deepcopy(doc)
        record = copy.deepcopy(record) if record is not None else None
        fn(doc, record)
        out[fid] = (code, reason, doc, record)

    def set0(key, value, recompute=True):
        def fn(doc, record):
            doc[0][key] = value
            if recompute:
                rechain(doc)
        return fn

    def set1(key, value):
        def fn(doc, record):
            doc[1][key] = value
            rechain(doc, 1)
        return fn

    # structure
    add("record-signer-member", "undeclared_member", held_w, None, lambda x, r: x[0].update({"signer": "urn:cognous:principal:witness-1"}),
        "A witness record carries no signer: the profile has none, and a member that looks like one is refused, not read as a signature.")
    add("record-proof-member", "undeclared_member", held_w, None, lambda x, r: x[0].update({"proof": {"alg": "ed25519", "sig": "00"}}),
        "A witness record carries no keyed proof member either; a proof would be a new profile version.")
    add("extension-key-without-x-prefix", "invalid_extension_key", held_w, None, lambda x, r: x[0].update({"extensions": {"note": 1}}),
        "Extension names start with x-.")
    add("version-is-another-profile", "unsupported_contract_version", held_w, None, lambda x, r: x[0].update({"version": "witness-digest/0.2"}),
        "Only witness-digest/0.1 is implemented.")
    add("version-not-a-string", "schema_violation", held_w, None, lambda x, r: x[0].update({"version": 1}), "The version is the profile id string.")
    add("sequence-negative", "schema_violation", held_w, None, lambda x, r: x[0].update({"sequence": -1}), "A sequence number is a non-negative integer.")
    add("run-id-empty", "schema_violation", held_w, None, lambda x, r: x[0].update({"run_id": ""}), "A record names a run.")
    add("previous-digest-empty-string", "schema_violation", held_w, None, lambda x, r: x[0].update({"previous_digest": ""}), "previous_digest is null or a digest, never an empty string.")
    add("digest-not-sha256", "schema_violation", held_w, None, lambda x, r: x[0].update({"digest": "abc"}), "The record digest is sha256: plus 64 lowercase hex.")
    add("ledger-head-not-sha256", "schema_violation", held_w, None, lambda x, r: x[0]["ledgers"]["decisions"].update({"head": "sha1:abc"}), "A ledger head is a sha256 digest.")
    add("ledger-count-zero", "schema_violation", held_w, None, lambda x, r: x[0]["ledgers"]["decisions"].update({"count": 0}), "Empty ledgers are omitted from a record; a ledger entry covers at least one row.")
    add("ledger-entry-extra-member", "undeclared_member", held_w, None, lambda x, r: x[0]["ledgers"]["decisions"].update({"rows": []}), "A ledger entry is exactly count and head (never the rows themselves).")
    add("record-member-missing", "schema_violation", held_w, None, lambda x, r: x[0].pop("ledgers"), "Every declared member is required.")
    add("ledgers-not-an-object", "schema_violation", held_w, None, lambda x, r: x[0].update({"ledgers": []}), "ledgers maps a ledger name to its entry.")
    out["witness-file-is-an-object"] = ("schema_violation", "The document is the array of records the witness holds, not one object.", copy.deepcopy(held_w[0]), None)
    # chain rules (file)
    add("empty-witness-file", "witness_holds_no_digest", held_w, None, lambda x, r: x.clear(), "A witness that holds no digest verifies nothing.")
    add("digest-does-not-recompute", "witness_chain_invalid", stg_w, None, lambda x, r: x[1].update({"digest": d("other")}),
        "A record's digest recomputes over the record without its digest member.")
    add("sequence-gap", "witness_chain_invalid", stg_w, None, set1("sequence", 2), "Sequence numbers are contiguous from 0 (records are renumbered, not skipped).")
    add("previous-digest-does-not-link", "witness_chain_invalid", stg_w, None, set1("previous_digest", d("elsewhere")), "A record links to the digest of the record before it.")
    add("first-record-has-previous-digest", "witness_chain_invalid", held_w, None, set0("previous_digest", d("elsewhere")), "The first record links to nothing (null).")
    add("run-id-changes-mid-chain", "witness_chain_invalid", stg_w, None, set1("run_id", "run-2"), "One witness chain covers one run.")

    def count_down(x, r):
        x[1]["ledgers"]["check_events"]["count"] = 12
        rechain(x, 1)
    add("ledger-count-decreases", "witness_chain_invalid", stg_w, None, count_down, "A ledger's covered count never decreases: a witness only extends.")

    def ledger_gone(x, r):
        del x[1]["ledgers"]["check_events"]
        rechain(x, 1)
    add("ledger-missing-from-a-later-record", "witness_chain_invalid", stg_w, None, ledger_gone, "A ledger covered earlier is covered later (a missing entry counts as zero rows, which is a decrease).")
    # record rules
    add("record-for-another-run", "witness_run_mismatch", held_w, held_r, lambda x, r: r.update({"run_id": "run-other"}), "The witness holds a chain for a different run than the record.")
    add("record-without-run-id", "witness_run_mismatch", held_w, held_r, lambda x, r: r.pop("run_id"), "A record with no run id cannot be matched to a witness chain.")
    add("covered-row-dropped", "witness_ledger_shrunk", held_w, held_r, lambda x, r: r["decisions"].pop(), "A covered decision row was dropped after the digest was published.")
    add("ledger-removed-from-record", "witness_ledger_shrunk", held_w, held_r, lambda x, r: r.pop("resolution_checks"), "A ledger that disappears counts as emptied.")
    add("covered-row-rewritten", "witness_ledger_head_mismatch", held_w, held_r, lambda x, r: r["decisions"][0].update({"result": "authorized"}), "A covered row was rewritten after publication: the head over the covered prefix differs.")

    def replaced(x, r):
        r["attempts"].pop(0)
        r["attempts"].append({"attempt_id": "forged"})
    add("covered-row-replaced", "witness_ledger_head_mismatch", auth_w, auth_r, replaced, "A dropped row replaced by another keeps the count and changes the head.")
    add("covered-rows-reordered", "witness_ledger_head_mismatch", auth_w, auth_r, lambda x, r: r["attempts"].reverse(), "The chain is order-sensitive.")

    def broken_chain_and_damage(x, r):
        r["attempts"].pop()
        x[0]["digest"] = d("other")
    add("chain-defect-stops-the-record-checks", "witness_chain_invalid", auth_w, auth_r, broken_chain_and_damage,
        "Like the Control Plane's verifier, the record rules run only over a sound chain: a broken chain is reported alone, even when the record is also damaged.")
    failures = []
    for fid, (code, reason, doc, record) in out.items():
        got = [v.code for v in wd.validate(doc, record)]
        if got != [code]:
            failures.append((fid, code, got))
            continue
        fx = {"fixture_id": fid, "synthetic": True, "expected_outcome": "reject", "reason": reason, "expected_refusal": code,
              "provenance": {"source": "single-defect mutation of a Control Plane capture", "control_plane_revision": cp}, "document": doc}
        if record is not None:
            fx["record"] = record
        write("invalid", fid, fx)
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
