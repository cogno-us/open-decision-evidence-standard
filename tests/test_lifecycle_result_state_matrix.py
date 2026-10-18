"""Rule result_state_matrix (decision 39-K): the execution result's status, flags and observation agree, as the runtime producer's
export refuses otherwise (engine/producer_contract.py ``_validate_result_state``). A validated ``state`` observation and a route-B
recovery ``status`` report are different evidence and are told apart.
"""
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

DIR = Path(__file__).resolve().parents[1] / "contracts" / "execution-attempt-lifecycle"
_spec = importlib.util.spec_from_file_location("eal_matrix", DIR / "validate.py")
eal = importlib.util.module_from_spec(_spec)
sys.modules["eal_matrix"] = eal
_spec.loader.exec_module(eal)


def fx(name):
    return copy.deepcopy(json.loads((DIR / "fixtures" / "valid" / f"{name}.json").read_text(encoding="utf-8"))["document"])


def codes(doc):
    return {v.code for v in eal.validate(doc)}


def _result(doc, **members):
    doc["execution_result"].update(members)
    return doc


EXECUTED = "executor-normal-attempted-executed-observed"
UNKNOWN_ACK = "executor-unknown-ack-unobserved"
RECOVERY = "executor-unknown-recovery-observation-route-b"
OBSERVED = "executor-observed-effect-free-reconcile-route-b"
DENIED = "executor-denied-attempt-event"


@pytest.mark.parametrize("name", [EXECUTED, UNKNOWN_ACK, RECOVERY, OBSERVED, DENIED, "executor-unknown-recovery-hold-route-b",
                                  "executor-unknown-validated-absent-after-ambiguous-dispatch"])
def test_valid_controls_pass(name):
    assert codes(fx(name)) == set()


# (fixture, member changes, why it is outside the matrix)
CASES = [
    (EXECUTED, {"attempted": False}, "executed requires an attempted execution"),
    (EXECUTED, {"acknowledged": False}, "executed must be acknowledged"),
    (EXECUTED, {"newly_executed": False}, "executed must be a fresh execution"),
    (UNKNOWN_ACK, {"attempted": False}, "unknown requires an attempted execution"),
    (RECOVERY, {"acknowledged": True, "attempted": False}, "an acknowledgement requires an attempted execution"),
    (RECOVERY, {"newly_executed": True}, "a fresh execution must be acknowledged"),
    (DENIED, {"acknowledged": True}, "denied carries no acknowledgement"),
    (DENIED, {"newly_executed": True, "acknowledged": True}, "denied is never fresh"),
]


@pytest.mark.parametrize("name,change,why", CASES, ids=lambda v: v if isinstance(v, str) and len(v) < 40 else None)
def test_status_and_flags_outside_the_matrix_are_refused(name, change, why):
    doc = _result(fx(name), **change)
    assert codes(doc) == {"result_state_matrix"}, why


def test_failed_with_an_acknowledgement_is_refused():
    doc = fx(DENIED)
    doc["attempt_events"][-1]["status"] = "failed"
    _result(doc, status="failed", attempted=True, acknowledged=True)
    assert codes(doc) == {"result_state_matrix"}


def test_reconciled_that_is_a_fresh_execution_is_refused():
    doc = fx(EXECUTED)
    doc["attempt_events"][-1]["status"] = "reconciled"
    _result(doc, status="reconciled")
    assert codes(doc) == {"result_state_matrix"}


def test_reconciled_not_observed_as_applied_is_refused():
    doc = fx(EXECUTED)
    doc["attempt_events"][-1]["status"] = "reconciled"
    doc["execution_result"]["observation"]["state"] = "absent"
    _result(doc, status="reconciled", newly_executed=False, observed_state="absent")
    assert codes(doc) == {"result_state_matrix"}


def test_partial_observed_as_applied_is_refused():
    doc = fx(EXECUTED)
    doc["attempt_events"][-1]["status"] = "partial"
    _result(doc, status="partial", newly_executed=False)
    assert codes(doc) == {"result_state_matrix"}


def test_observation_state_contradicting_observed_state_is_refused():
    doc = fx(EXECUTED)
    doc["execution_result"]["observation"]["state"] = "partial"
    assert "result_state_matrix" in codes(doc) or codes(doc) != set()


def test_a_recovery_report_is_not_held_to_the_validated_state_row():
    """route B: a recovery report has `status`, no `state`; its observed_state follows the report, not a `state` member."""
    assert codes(fx(RECOVERY)) == set()


def test_absent_flag_members_skip_only_the_flag_rows():
    """The flags are optional members (a valid control omits them); the observation rows still apply."""
    doc = fx(EXECUTED)
    for name in ("attempted", "acknowledged", "newly_executed"):
        del doc["execution_result"][name]
    assert codes(doc) == set()
    doc["execution_result"]["observed_state"] = "partial"
    assert codes(doc) == {"result_state_matrix"}
