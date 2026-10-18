"""An instant equal to the consumption expiry is expired (half-open window), matching the Control Plane grant rule."""
import pytest
from odes.recipient_validator import _evaluate_authority_and_freshness

EXPIRY = "2026-10-18T12:00:00Z"
MSG = "record consumption window has expired under recipient policy time"


def _reasons(now):
    out = _evaluate_authority_and_freshness({"consumption_conditions": {"expires_at": EXPIRY}}, {}, now, {})
    return out["reasons"] if "reasons" in out else out.get("details", [])


@pytest.mark.parametrize("now,expired", [
    ("2026-10-18T11:59:59Z", False),
    ("2026-10-18T12:00:00Z", True),
    ("2026-10-18T12:00:00+00:00", True),
    ("2026-10-18T14:00:00+02:00", True),
    ("2026-10-18T12:00:01Z", True),
])
def test_expiry_boundary(now, expired):
    assert (MSG in _reasons(now)) is expired
