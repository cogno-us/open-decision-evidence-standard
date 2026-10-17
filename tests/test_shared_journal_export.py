"""Regression for #42: an unauthorized hold sharing the journal must not block export of the valid flow."""
import pytest

from odes.exporter import ExportError, _check_decision_execution_consistency


def rec(kind, seq, **data):
    return {"record_type": kind, "source_sequence": seq, "data": data}


def bundle(*records):
    return {"bundle_version": "0.2.0", "records": list(records)}


def authorized(decision_id):
    return rec("runtime_decision", 1, decision_id=decision_id, result="authorized", binding={"action_id": "a"})


def hold(decision_id):
    return rec("runtime_decision", 2, decision_id=decision_id, result="hold")


def test_unauthorized_hold_in_shared_journal_does_not_block_valid_flow():
    b = bundle(hold("held-1"), authorized("good"), rec("control_plane_attempt_transition", 3, decision_id="good"))
    decision, result = _check_decision_execution_consistency(b)
    assert decision["decision_id"] == "good" and result == "authorized"


def test_two_decisions_without_execution_evidence_still_fail_closed():
    with pytest.raises(ExportError, match="exactly one retained runtime_decision"):
        _check_decision_execution_consistency(bundle(hold("h1"), hold("h2")))


def test_two_decisions_both_linked_to_execution_still_fail_closed():
    b = bundle(authorized("g1"), authorized("g2"),
               rec("execution_envelope", 3, decision_id="g1"), rec("execution_result", 4, decision_id="g2"))
    with pytest.raises(ExportError, match="exactly one retained runtime_decision"):
        _check_decision_execution_consistency(b)


def test_decision_referenced_by_no_evidence_is_ambiguous():
    b = bundle(authorized("g1"), hold("h1"), rec("execution_envelope", 3, decision_id="unknown"))
    with pytest.raises(ExportError, match="exactly one retained runtime_decision"):
        _check_decision_execution_consistency(b)


