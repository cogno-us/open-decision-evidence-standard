"""Transition table parity with the independent verifier (decision 39-P).

The verifier's tables are recorded here as data (its EXECUTOR_NEXT and its Control Plane rule: ``attempted`` opens an attempt, an
``unknown`` row may only be followed by acknowledged, partial or failed, and acknowledged, partial and failed are closed). The
verifier names the violation ``attempt_transition_invalid``; this validator names it ``attempt_transition``. The names are not
renamed; the test maps them.
"""
import importlib.util
import itertools
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parents[1] / "contracts" / "execution-attempt-lifecycle"
_spec = importlib.util.spec_from_file_location("eal_parity", DIR / "validate.py")
eal = importlib.util.module_from_spec(_spec)
sys.modules["eal_parity"] = eal
_spec.loader.exec_module(eal)

NAME_MAP = {"attempt_transition_invalid": "attempt_transition"}

VERIFIER_EXECUTOR_NEXT = {
    "attempted": {"executed", "partial", "failed", "unknown", "denied", "reconciled"},
    "executed": {"unknown", "reconciled"},
    "partial": {"unknown", "reconciled"},
    "unknown": {"reconciled", "executed", "partial", "failed"},
    "reconciled": set(),
    "failed": set(),
    "denied": set(),
}
CP_STATUSES = ["attempted", "unknown", "acknowledged", "partial", "failed"]
CP_TERMINAL = {"acknowledged", "partial", "failed"}
CP_AFTER_UNKNOWN = {"acknowledged", "partial", "failed"}


def _verifier_cp_allows(before, after):
    if after == "attempted":
        return False
    if before == "attempted":
        return True
    if before == "unknown":
        return after in CP_AFTER_UNKNOWN
    return before not in CP_TERMINAL


def test_code_name_mapping_is_the_only_naming_difference():
    assert NAME_MAP == {"attempt_transition_invalid": "attempt_transition"}


def test_executor_table_equals_the_verifier_table_over_all_pairs():
    for before, after in itertools.product(VERIFIER_EXECUTOR_NEXT, repeat=2):
        if after == "attempted":
            continue  # 'attempted' only opens an attempt; both sides report it as a different rule
        assert (after in eal.EXECUTOR_TRANSITIONS[before]) == (after in VERIFIER_EXECUTOR_NEXT[before]), (before, after)


def test_producer_written_edges_are_allowed():
    assert "unknown" in eal.EXECUTOR_TRANSITIONS["executed"]
    assert "unknown" in eal.EXECUTOR_TRANSITIONS["partial"]


def test_control_plane_table_equals_the_verifier_rule_over_all_pairs():
    for before, after in itertools.product(CP_STATUSES, repeat=2):
        if after == "attempted":
            continue
        assert (after in eal.CONTROL_PLANE_TRANSITIONS[before]) == _verifier_cp_allows(before, after), (before, after)


def test_terminal_statuses_stay_closed():
    for status in ("reconciled", "failed", "denied"):
        assert eal.EXECUTOR_TRANSITIONS[status] == frozenset()
