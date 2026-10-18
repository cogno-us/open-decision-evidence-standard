"""Write the ``v3-*`` fixtures of the verification-report contract (step 2 of 2; step 1 is ``capture_v3_reports.py``).

The valid fixtures are the captured reports (real ``cognous-verify`` output over witnessed Control Plane runs, with the tier V3
section moved into the draft-revision shape; see that script for exactly what was moved). The invalid ones are single-defect
mutations of them. ``build_fixtures.py`` leaves ``v3-*`` files alone and this script writes only them. Run from the repository root:

    python contracts/verification-report/provenance/build_v3_fixtures.py <reports-dir>
"""
import copy
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTRACT_DIR = HERE.parent
_spec = importlib.util.spec_from_file_location("vr_build", HERE / "build_fixtures.py")
bf = importlib.util.module_from_spec(_spec)
sys.modules["vr_build"] = bf
_spec.loader.exec_module(bf)
vr = bf.vr

PROVENANCE = ("verifier main 05afab8 (cogno-us/cognous-open-control-stack-verifier PR #10) over records and witness files captured from "
              "Control Plane 128eaa5 (`acp witness publish`, bounded workflow with fixed clock); tier V3 moved from extensions[\"x-tier-v3\"] "
              "into checks, subject.inputs and scope.tiers_run by capture_v3_reports.py; nothing else edited")

VALID = {
    "v3-witness-complete": ("witnessed-complete", "A real V3 report: the witness covers every row of the record; six V3 checks confirmed (records, digest-recompute, chain, run-id, ledger-heads, coverage). Summary counts them with the V1, V2 and V4 checks."),
    "v3-witness-first-publication-only": ("witnessed-first-only", "A real V3 report where the witness was published before execution: rows appended after the latest digest are not covered, so v3.witness.coverage is could_not_check (input_absent), not confirmed."),
    "v3-witness-and-holder-inventory": ("witnessed-with-inventory", "A real V3 report with both V3 input roles (witness and holder_inventory): the inventory's closed shape is confirmed; it says nothing about completeness."),
    "v3-held-for-missing-inventory": ("witnessed-held-without-inventory", "A real V3 report over a run held with holder_inventory_missing and no inventory supplied: v3.holder-inventory.record-reference is could_not_check, never confirmed."),
    "v3-witness-refutes-damaged-record": ("witnessed-damaged-record", "A real V3 report over a record from which one covered row (the last attempt) was removed after the digest was published: v3.witness.ledger-heads is refuted with witness_ledger_shrunk, and the derived outcome is reject."),
}


def find(doc, check_id):
    return next(c for c in doc["checks"] if c["check_id"] == check_id)


def refresh(doc):
    bf.refresh_subject(doc)
    doc["summary"] = bf.summary(doc["checks"])


def write(kind, fid, payload):
    path = CONTRACT_DIR / "fixtures" / kind / f"{fid}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(reports: Path) -> int:
    docs = {}
    for fid, (name, reason) in VALID.items():
        doc = json.loads((reports / f"{name}.json").read_text(encoding="utf-8"))
        assert vr.validate(doc) == [], (fid, vr.validate(doc))
        docs[fid] = doc
        write("valid", fid, {"fixture_id": fid, "synthetic": True, "expected_outcome": "accept", "reason": reason,
                             "expected_refusal": None, "provenance": PROVENANCE, "document": doc})
    complete, first, inv, damaged = (docs[k] for k in ("v3-witness-complete", "v3-witness-first-publication-only",
                                                        "v3-witness-and-holder-inventory", "v3-witness-refutes-damaged-record"))
    out = {}

    def add(fid, code, base, fn, reason):
        doc = copy.deepcopy(base)
        fn(doc)
        out[fid] = (code, reason, doc)

    def drop_non_claim(x):
        x["does_not_prove"] = [n for n in x["does_not_prove"] if n["id"] != "witness_is_not_publication"]

    def drop_witness_input(x):
        x["subject"]["inputs"] = [i for i in x["subject"]["inputs"] if i["role"] != "witness"]
        bf.refresh_subject(x)

    def drop_v3(x):
        x["scope"]["tiers_run"] = [t for t in x["scope"]["tiers_run"] if t != "V3"]
        x["checks"] = [c for c in x["checks"] if c["tier"] != "V3"]
        refresh(x)

    def not_counted(x):
        x["summary"] = bf.summary([c for c in x["checks"] if c["tier"] != "V3"])

    def verdict_confirmed(x):
        find(x, "v3.witness.ledger-heads")["verdict"] = "confirmed"
        x["summary"] = bf.summary(x["checks"])

    def second_witness(x):
        x["subject"]["inputs"].append(copy.deepcopy(next(i for i in x["subject"]["inputs"] if i["role"] == "witness")))
        x["subject"]["inputs"].sort(key=lambda i: (i["role"], i["name"], i["digest"]))
        bf.refresh_subject(x)

    add("v3-without-witness-or-inventory-input", "v3_input_missing", complete, drop_witness_input,
        "A report that ran V3 names a witness file or a holder inventory as an input; with the witness input removed there is none.")
    add("v3-input-without-v3-tier", "v3_input_without_tier", complete, drop_v3,
        "A witness input is read by tier V3; a report that lists the input but not the tier (and no V3 check) is refused.")
    add("v3-non-claim-missing", "non_claim_missing", complete, drop_non_claim,
        "A report that ran V3 carries the witness_is_not_publication non-claim.")
    add("v3-checks-not-counted-in-summary", "summary_mismatch", complete, not_counted,
        "The summary counts every check in checks, V3 included (the shape the verifier used before the revision, V3 outside the summary, is a mismatch).")
    add("v3-tally-does-not-sum", "tally_sum_mismatch", complete, lambda x: find(x, "v3.witness.chain")["tally"].update({"n": 4}),
        "A V3 check's tally sums to its n like any other check.")
    add("v3-confirmed-verdict-over-a-refuted-item", "check_verdict_inconsistent", damaged, verdict_confirmed,
        "One refuted item makes the V3 check refuted; the verdict is the derived one.")
    add("v3-refuted-without-finding", "refuted_without_finding", damaged, lambda x: find(x, "v3.witness.ledger-heads").update({"findings": []}),
        "A refuted V3 check names what refuted it.")
    add("v3-could-not-check-without-reason", "could_not_check_unexplained", first, lambda x: find(x, "v3.witness.coverage").update({"could_not_check_reason": None}),
        "Unwitnessed rows are could_not_check and say why (input_absent); the reason cannot be dropped.")
    add("v3-composite-score-member", "undeclared_member", complete, lambda x: x["summary"].update({"score": 1.0}),
        "Admitting V3 adds no score: a witnessed report has no composite number either.")
    add("v3-input-altered-after-digest", "subject_digest_mismatch", complete,
        lambda x: next(i for i in x["subject"]["inputs"] if i["role"] == "witness").update({"digest": bf.d("tampered-witness")}),
        "A witness input digest changed without recomputing the subject digest.")
    add("v3-duplicate-witness-input", "duplicate_input", complete, second_witness,
        "One input per role and name; the same witness file twice is refused.")
    add("unknown-input-role-witness-chain", "unknown_enum_value", complete,
        lambda x: next(i for i in x["subject"]["inputs"] if i["role"] == "witness").update({"role": "witness_chain"}),
        "The input roles are a closed set; witness and holder_inventory are the V3 roles and another name is a major bump.")
    failures = []
    for fid, (code, reason, doc) in out.items():
        got = [v.code for v in vr.validate(doc)]
        if got != [code]:
            failures.append((fid, code, got))
            continue
        write("invalid", fid, {"fixture_id": fid, "synthetic": True, "expected_outcome": "reject", "reason": reason,
                               "expected_refusal": code, "provenance": "single-defect mutation of a captured V3 report (see the README, Fixtures); the base: " + PROVENANCE,
                               "document": doc})
    for f in failures:
        print("FAIL", f)
    print(f"valid {len(VALID)} invalid {len(out)} failures {len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]).resolve()))
