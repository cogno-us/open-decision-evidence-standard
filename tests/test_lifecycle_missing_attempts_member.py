"""Rule coverage when the optional ``attempts`` member is absent (decision 44): a missing member is an empty row list, so the
result and event rules still run. A result naming an attempt that no row defines is refused (``result_attempt_unresolved``) and
events out of order are refused (``event_order``); a record with none of ``attempts``, ``attempt_events`` and ``execution_result``
stays valid. Before this change ``_executor_rules`` returned early and an ``executed`` ghost result validated.
"""
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

DIR = Path(__file__).resolve().parents[1] / "contracts" / "execution-attempt-lifecycle"
_spec = importlib.util.spec_from_file_location("eal_missing_attempts", DIR / "validate.py")
eal = importlib.util.module_from_spec(_spec)
sys.modules["eal_missing_attempts"] = eal
_spec.loader.exec_module(eal)


def fx(name, kind="valid"):
    return copy.deepcopy(json.loads((DIR / "fixtures" / kind / f"{name}.json").read_text(encoding="utf-8"))["document"])


def codes(doc):
    return [v.code for v in eal.validate(doc)]


NEW_INVALID = {
    "executor-ghost-result-without-attempts-member": "result_attempt_unresolved",
    "executor-events-out-of-order-without-attempts-member": "event_order",
    "control-plane-empty-attempts-ghost-result": "result_attempt_unresolved",
}


@pytest.mark.parametrize("name", sorted(NEW_INVALID))
def test_missing_attempts_member_does_not_skip_result_and_event_rules(name):
    doc = fx(name, "invalid")
    assert codes(doc) == [NEW_INVALID[name]]


def test_record_with_no_attempts_events_or_result_stays_valid():
    doc = {"contract": "execution-attempt-lifecycle", "contract_version": "0.1.0-draft", "producer": "runtime-executor",
           "resolution_journal": []}
    assert codes(doc) == []


def test_explicit_empty_attempts_member_matches_a_missing_one():
    doc = fx("control-plane-empty-attempts-ghost-result", "invalid")
    missing = copy.deepcopy(doc)
    missing.pop("attempts", None)
    assert codes(missing) == codes(doc) == ["result_attempt_unresolved"]
