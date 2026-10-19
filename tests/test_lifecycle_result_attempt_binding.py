"""Rule result_attempt_unresolved: a result whose status claims an attempt (failed, partial, unknown, executed, reconciled) names exactly
one attempt row of the record. A null attempt id and an id that matches no row are both refused, whatever the flags say. Results that
claim no attempt (observed, denied) and every producer-valid combination keep their behaviour.
"""
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

DIR = Path(__file__).resolve().parents[1] / "contracts" / "execution-attempt-lifecycle"
_spec = importlib.util.spec_from_file_location("eal_binding", DIR / "validate.py")
eal = importlib.util.module_from_spec(_spec)
sys.modules["eal_binding"] = eal
_spec.loader.exec_module(eal)


def fx(name, kind="valid"):
    return copy.deepcopy(json.loads((DIR / "fixtures" / kind / f"{name}.json").read_text(encoding="utf-8"))["document"])


def codes(doc):
    return [v.code for v in eal.validate(doc)]


# status -> (attempted, acknowledged, newly_executed, observed_state): a combination the producer allows for that status
ALLOWED = {
    "failed": (True, False, False, "unknown"),
    "partial": (True, True, False, "partial"),
    "unknown": (True, False, False, "unknown"),
    "executed": (True, True, True, "applied"),
    "reconciled": (True, True, False, "applied"),
}


def result_of(status, attempt_id):
    """The valid executed lifecycle document, with its result replaced by an allowed combination of ``status``."""
    doc = fx("executor-normal-attempted-executed-observed")
    attempted, acknowledged, fresh, state = ALLOWED[status]
    terminal = {"reconciled": ["executed", "reconciled"]}.get(status, [status])
    doc["attempt_events"] = [
        {"event_id": i + 1, "attempt_id": "syn-attempt-1", "status": s, "error": "x" if s == "failed" else None,
         "created_at": 1000.0 + i} for i, s in enumerate(["attempted", *terminal])]
    doc["execution_result"].update(
        status=status, attempted=attempted, acknowledged=acknowledged, newly_executed=fresh, observed_state=state,
        attempt_id=attempt_id, error=None,
        observation=None if state == "unknown" else {"effect_id": "syn-effect-1", "state": state,
                                                      "observed_at": "2026-01-01T00:00:05Z"})
    return doc


@pytest.mark.parametrize("status", sorted(ALLOWED))
def test_control_the_allowed_combination_naming_its_row_is_accepted(status):
    assert codes(result_of(status, "syn-attempt-1")) == []


@pytest.mark.parametrize("status", sorted(ALLOWED))
def test_a_null_attempt_id_on_an_attempt_claiming_status_is_refused(status):
    assert codes(result_of(status, None)) == ["result_attempt_unresolved"]


@pytest.mark.parametrize("status", sorted(ALLOWED))
def test_an_attempt_id_that_matches_no_row_is_refused(status):
    assert codes(result_of(status, "unregistered-attempt")) == ["result_attempt_unresolved"]


@pytest.mark.parametrize("status,change", [
    ("partial", {"acknowledged": False}), ("partial", {"newly_executed": True}), ("unknown", {"acknowledged": True}),
    ("reconciled", {"acknowledged": False}), ("executed", {"acknowledged": False}), ("failed", {"acknowledged": True})])
def test_a_contradictory_combination_without_a_row_is_refused(status, change):
    doc = result_of(status, None)
    doc["execution_result"].update(change)
    assert codes(doc) != []


@pytest.mark.parametrize("status", ["observed", "denied"])
def test_results_that_claim_no_attempt_keep_a_null_attempt_id(status):
    doc = fx("executor-observed-effect-free-reconcile-route-b" if status == "observed" else "executor-denied-attempt-event")
    doc["execution_result"]["attempt_id"] = None
    assert codes(doc) == []


def test_a_repeated_attempt_row_is_reported_once_under_its_own_code():
    doc = fx("executor-normal-attempted-executed-observed")
    doc["attempts"].append(copy.deepcopy(doc["attempts"][0]))
    assert codes(doc) == ["duplicate_attempt_row"]


def test_the_result_of_another_attempt_row_of_the_record_is_not_refused_by_this_rule():
    doc = fx("executor-normal-attempted-executed-observed")
    doc["attempts"].append({"attempt_id": "syn-attempt-2", "effect_id": "syn-effect-1", "decision_id": "syn-decision-1"})
    doc["attempt_events"] += [{"event_id": 3, "attempt_id": "syn-attempt-2", "status": "attempted", "error": None, "created_at": 1002.0},
                              {"event_id": 4, "attempt_id": "syn-attempt-2", "status": "executed", "error": None, "created_at": 1003.0}]
    doc["execution_result"]["attempt_id"] = "syn-attempt-2"
    assert "result_attempt_unresolved" not in codes(doc)
