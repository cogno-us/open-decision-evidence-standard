"""An empty relying-party list admits no recipient (decision 39-N)."""
import pytest

from odes.recipient_validator import _evaluate_consumption

RISK = {"prohibited_use_flag": False, "restricted_use_flag": False, "jurisdiction": "test"}
POLICY = {"jurisdiction": "test"}


def _record(**conditions):
    return {"consumption_conditions": {"permitted_purposes": ["audit"], **conditions}, "risk_coordinates": RISK}


# ------------------------------------------------------------------ an empty relying-party list admits no recipient

def test_listed_relying_party_passes_and_unlisted_fails():
    assert _evaluate_consumption(_record(permitted_relying_parties=["r"]), "r", "audit", POLICY)["status"] == "pass"
    assert _evaluate_consumption(_record(permitted_relying_parties=["r"]), "other", "audit", POLICY)["status"] == "fail"


@pytest.mark.parametrize("conditions", [{}, {"permitted_relying_parties": []}, {"permitted_relying_parties": None}, {"permitted_relying_parties": "r"}])
@pytest.mark.parametrize("party", ["r", None])
def test_absent_or_empty_relying_party_list_is_refused(conditions, party):
    result = _evaluate_consumption(_record(**conditions), party, "audit", POLICY)
    assert result["status"] == "fail"
    assert any("no permitted relying party" in r for r in result["reasons"])
