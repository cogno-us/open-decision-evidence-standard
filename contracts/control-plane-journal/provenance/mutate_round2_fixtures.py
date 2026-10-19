"""Mutate valid fixtures into the invalid ones for the round 2 rules (single-defect mutations; each fixture's `provenance` names its base).

    python mutate_round2_fixtures.py <contracts/control-plane-journal dir>

Rules: dispatch_license, reasons_minimum, causal_order. Stops if a mutation does not yield exactly its one expected code.
"""
import copy, importlib.util, json, sys
from pathlib import Path

CDIR = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("cpj", CDIR / "validate.py")
cpj = importlib.util.module_from_spec(spec)
sys.modules["cpj"] = cpj
spec.loader.exec_module(cpj)
VALID = CDIR / "fixtures" / "valid"
OUT = CDIR / "fixtures" / "invalid"
bad = []


def make(fid, base, code, why, fn):
    source = json.loads((VALID / f"{base}.json").read_text(encoding="utf-8"))
    doc = copy.deepcopy(source["document"])
    fn(doc)
    provenance = {"source": f"single-defect mutation of the valid fixture {base}"}
    if base.startswith("profile-"):  # a profile record keeps its capture commit and the profile- name prefix
        fid = "profile-" + fid
        provenance["control_plane_commit"] = source["provenance"]["control_plane_commit"]
    got = list(dict.fromkeys(v.code for v in cpj.validate(doc)))
    if got != [code]:
        bad.append((fid, code, got))
    fx = {"fixture_id": fid, "synthetic": True, "expected_outcome": "reject", "expected_refusal": code, "reason": why,
          "provenance": provenance, "document": doc}
    (OUT / f"{fid}.json").write_text(json.dumps(fx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def drop_effect_checks(doc):
    doc["resolution_checks"] = [c for c in doc["resolution_checks"] if c["stage"] != "effect"]
    doc["check_events"] = [e for e in doc.get("check_events", []) if e["stage"] != "effect"]


def delete_refusal_add_attempt(doc):
    d = doc["decisions"][0]
    doc["refusals"] = []
    doc["attempts"] = [{"attempt_id": "syn-attempt-9", "effect_id": d["effect_id"], "decision_id": d["decision_id"], "started_at": d["decided_at"],
                        "time_source": d["time_source"], "status": s, "acknowledgement": ack, "error": None}
                       for s, ack in (("attempted", {}), ("acknowledged", {"duplicate": False}))]


def drop_reason_everywhere(doc, code):
    for section in ("decisions", "resolution_checks", "refusals"):
        for row in doc[section]:
            row["reasons"] = [r for r in row["reasons"] if r != code]
    for e in doc["check_events"]:
        if e["phase"] == "completed":
            e["reasons"] = [r for r in e["reasons"] if r != code]


def replace_reason_everywhere(doc, old, new):
    for section in ("decisions", "resolution_checks", "refusals"):
        for row in doc[section]:
            row["reasons"] = [new if r == old else r for r in row["reasons"]]
    for e in doc["check_events"]:
        if e["phase"] == "completed":
            e["reasons"] = [new if r == old else r for r in e["reasons"]]


def blank_decision_check_reasons(doc):
    for c in doc["resolution_checks"]:
        c["reasons"] = []
    for e in doc["check_events"]:
        if e["phase"] == "completed":
            e["reasons"] = []


make("dispatch-license-attempt-without-effect-check", "normal-attempted-acknowledged-applied", "dispatch_license",
     "An attempt lifecycle exists but its effect-stage check (resolution check and journal events) was removed: no check licensed the dispatch.", drop_effect_checks)
make("dispatch-license-default-path-without-effect-check", "no-journal-mode-normal", "dispatch_license",
     "Default path (no journal): the attempt lifecycle has no passing effect-stage check row.",
     lambda doc: doc.__setitem__("resolution_checks", [c for c in doc["resolution_checks"] if c["stage"] != "effect"]))
make("dispatch-license-refusal-deleted-attempt-added", "effect-time-refusal", "dispatch_license",
     "The effect-stage check carries reasons, its refusal was deleted and an attempt lifecycle added for the same decision.", delete_refusal_add_attempt)
make("dispatch-license-check-reasons-without-refusal", "effect-time-refusal", "dispatch_license",
     "The effect-stage check carries reasons and there is no refusal for its decision.", lambda doc: doc.__setitem__("refusals", []))
make("reasons-minimum-unreadable-input-without-status-unreadable", "reasons-0-2-label-on-0-1-codes", "reasons_minimum",
     "The check's own input events show an unreadable grant read, but its completion (and the rows that repeat it) leave out status_unreadable.",
     lambda doc: drop_reason_everywhere(doc, "status_unreadable"))
make("reasons-minimum-missing-input-with-blank-reasons", "reasons-0-2-label-on-0-1-codes", "reasons_minimum",
     "Inputs show a missing grant, the check completion and rows carry no reasons.", blank_decision_check_reasons)
make("reasons-minimum-nonce-mismatch-without-reason", "profile-nonce-replay-rejected", "reasons_minimum",
     "An input read ended in nonce_mismatch but the completion does not carry status_nonce_mismatch.",
     lambda doc: replace_reason_everywhere(doc, "status_nonce_mismatch", "grant_not_active"))


def attempt_before_decision(doc):
    for a in doc["attempts"]:
        a["started_at"] = "2020-01-01T00:00:00+00:00"


make("causal-order-attempt-before-decision", "normal-attempted-acknowledged-applied", "causal_order",
     "Every row of the attempt starts at an evaluation time earlier than the decision's decided_at.", attempt_before_decision)


def attempt_after_the_reconciliation_that_closes_it(doc):
    for a in doc["attempts"]:
        a["started_at"] = "2030-01-01T00:00:00+00:00"


make("causal-order-closeout-rests-on-reconciliation-before-attempt", "lost-ack-unknown-then-closeout", "causal_order",
     "The attempt's rows start after the evaluation time of the reconciliation its closeout rests on.", attempt_after_the_reconciliation_that_closes_it)


if bad:
    sys.exit(f"mutation did not yield exactly its code: {bad}")
