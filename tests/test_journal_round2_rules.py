"""Round 2 evidence check hardening over the control-plane-journal contract: dispatch_license, reasons_minimum, causal_order.

Every mutation starts from a valid producer fixture and changes one thing; the valid fixtures stay valid (see the contract tests).
"""
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "contracts" / "control-plane-journal"
_spec = importlib.util.spec_from_file_location("cpj_round2", DIR / "validate.py")
cpj = importlib.util.module_from_spec(_spec)
sys.modules["cpj_round2"] = cpj
_spec.loader.exec_module(cpj)


def fx(name):
    return copy.deepcopy(json.loads((DIR / "fixtures" / "valid" / f"{name}.json").read_text(encoding="utf-8"))["document"])


def codes(doc):
    return {v.code for v in cpj.validate(doc)}


def set_reasons(doc, reasons):
    """Set the reasons of every decision, effect or decision check row and completion event, and refusal: one consistent story."""
    for section in ("decisions", "resolution_checks", "refusals"):
        for row in doc[section]:
            row["reasons"] = list(reasons)
    for e in doc["check_events"]:
        if e["phase"] == "completed":
            e["reasons"] = list(reasons)


# ------------------------------------------------------------------ dispatch_license

def _drop_effect_check(doc):
    doc["resolution_checks"] = [c for c in doc["resolution_checks"] if c["stage"] != "effect"]
    doc["check_events"] = [e for e in doc["check_events"] if e["stage"] != "effect"]


def test_attempt_without_an_effect_check_is_refused():
    doc = fx("normal-attempted-acknowledged-applied")
    assert codes(doc) == set()
    _drop_effect_check(doc)
    assert "dispatch_license" in codes(doc)


def test_attempt_without_an_effect_check_is_refused_on_the_default_path():
    doc = fx("no-journal-mode-normal")
    assert codes(doc) == set()
    doc["resolution_checks"] = [c for c in doc["resolution_checks"] if c["stage"] != "effect"]
    assert "dispatch_license" in codes(doc)


def test_two_attempt_lifecycles_need_two_effect_checks():
    doc = fx("reconciled-existing-single-row")
    assert codes(doc) == set()
    effect = [c for c in doc["resolution_checks"] if c["stage"] == "effect"]
    assert len(effect) == 2
    doc["resolution_checks"].remove(effect[1])
    # remove one effect check from the journal too (its four events), so only the licence count is short
    ids = []
    for e in doc["check_events"]:
        if e["stage"] == "effect" and e["check_id"] not in ids:
            ids.append(e["check_id"])
    doc["check_events"] = [e for e in doc["check_events"] if e["check_id"] != ids[-1]]
    assert "dispatch_license" in codes(doc)


def test_refusal_deleted_and_attempt_added_is_refused():
    doc = fx("effect-time-refusal")
    assert codes(doc) == set()
    d = doc["decisions"][0]
    doc["refusals"] = []
    doc["attempts"] = [
        {"attempt_id": "syn-attempt-9", "effect_id": d["effect_id"], "decision_id": d["decision_id"], "started_at": d["decided_at"],
         "time_source": d["time_source"], "status": s, "acknowledgement": ack, "error": None}
        for s, ack in (("attempted", {}), ("acknowledged", {"duplicate": False}))]
    assert "dispatch_license" in codes(doc)


def test_effect_check_with_reasons_and_no_refusal_is_refused():
    doc = fx("effect-time-refusal")
    doc["refusals"] = []
    assert "dispatch_license" in codes(doc)


def test_refusal_kept_but_check_reasons_cleared_is_refused():
    doc = fx("profile-op-effect-time-refusal-carries-check-id")
    for c in doc["resolution_checks"]:
        if c["stage"] == "effect":
            c["reasons"] = []
    for e in doc["check_events"]:
        if e["phase"] == "completed" and e["stage"] == "effect":
            e["reasons"] = []
    assert "dispatch_license" in codes(doc)


@pytest.mark.parametrize("name", ["reconciled-existing-single-row", "normal-attempted-acknowledged-applied", "no-journal-mode-normal",
                                  "profile-expired-then-retry-dispatches", "profile-op-worker-self-renewal-then-unrecorded-hold",
                                  "profile-terminal-revocation-suspension-stays-reversible", "profile-op-duplicate-submission-reconciled-existing"])
def test_valid_controls_still_pass(name):
    assert codes(fx(name)) == set()


# ------------------------------------------------------------------ reasons_minimum

def test_unreadable_input_requires_status_unreadable():
    doc = fx("reasons-0-2-label-on-0-1-codes")
    assert codes(doc) == set()
    for section in ("decisions", "resolution_checks"):
        for row in doc[section]:
            row["reasons"] = [r for r in row["reasons"] if r != "status_unreadable"]
    for e in doc["check_events"]:
        if e["phase"] == "completed":
            e["reasons"] = [r for r in e["reasons"] if r != "status_unreadable"]
    assert codes(doc) == {"reasons_minimum"}


def test_blank_check_reasons_while_inputs_show_missing_is_refused():
    doc = fx("reasons-0-2-label-on-0-1-codes")
    for c in doc["resolution_checks"]:
        c["reasons"] = []
    for e in doc["check_events"]:
        if e["phase"] == "completed":
            e["reasons"] = []
    assert "reasons_minimum" in codes(doc)


def test_nonce_mismatch_input_requires_its_reason():
    doc = fx("profile-nonce-replay-rejected")
    assert codes(doc) == set()
    for section in ("decisions", "resolution_checks", "refusals"):
        for row in doc[section]:
            row["reasons"] = ["grant_not_active" if r == "status_nonce_mismatch" else r for r in row["reasons"]]
    for e in doc["check_events"]:
        if e["phase"] == "completed":
            e["reasons"] = ["grant_not_active" if r == "status_nonce_mismatch" else r for r in e["reasons"]]
    assert codes(doc) == {"reasons_minimum"}


def test_an_unreadable_read_rescued_by_a_cached_positive_implies_nothing():
    lc = cpj.lifecycle()
    unreadable = {"input_type": "grant", "input_id": "g", "missing": True, "read_state": "unreadable"}
    rescued = {"input_type": "grant", "input_id": "g", "missing": False, "read_state": "cached_positive"}
    assert lc.implied_reasons([unreadable]) == ({"status_unreadable"}, True)
    assert lc.implied_reasons([unreadable, rescued]) == (set(), False)


def test_implication_table_is_published():
    lc = cpj.lifecycle()
    assert lc.IMPLIED_REASONS == {"unreadable": "status_unreadable", "nonce_mismatch": "status_nonce_mismatch",
                                  "authority_context_missing": "authority_context_missing", "purpose_missing": "purpose_unreadable"}


# ------------------------------------------------------------------ causal_order

def test_attempt_before_its_decision_is_refused():
    doc = fx("normal-attempted-acknowledged-applied")
    for a in doc["attempts"]:
        a["started_at"] = "2020-01-01T00:00:00+00:00"
    assert codes(doc) == {"causal_order"}


def test_attempt_at_the_decision_instant_is_in_order():
    doc = fx("normal-attempted-acknowledged-applied")
    for a in doc["attempts"]:
        a["started_at"] = doc["decisions"][0]["decided_at"]
    assert codes(doc) == set()


def test_service_clock_decoupled_from_evaluation_clock_is_not_refused():
    """freshness/0.1: recorded_at (service time) may run far from evaluated_at; they are never compared with each other."""
    doc = fx("profile-clocks-follow-the-service-clock")
    assert codes(doc) == set()
    for row in doc["decisions"] + doc["attempts"]:
        if "recorded_at" in row:
            row["recorded_at"] = row["recorded_at"].replace("2026", "2027") if row in doc["attempts"] else row["recorded_at"]
    assert "causal_order" not in codes(doc)


def test_closeout_resting_on_a_reconciliation_before_the_attempt_is_refused():
    doc = fx("lost-ack-unknown-then-closeout")
    assert codes(doc) == set()
    for a in doc["attempts"]:
        a["started_at"] = "2030-01-01T00:00:00+00:00"
    assert codes(doc) == {"causal_order"}
