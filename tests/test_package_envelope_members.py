"""Package top-level members (decision 39-M)."""
import json
from pathlib import Path

import pytest

from odes.recipient_validator import _evaluate_package_content_integrity, evaluate_recipient_package

ROOT = Path(__file__).resolve().parents[1]


def _package():
    return json.loads((ROOT / "examples/producer-v2/lost_ack.package.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ package top-level members

def test_example_package_digest_still_passes():
    assert _evaluate_package_content_integrity(_package(), [])["status"] == "pass"


def test_extra_top_level_member_is_refused():
    p = _package()
    p["note"] = "added after export"
    result = _evaluate_package_content_integrity(p, [])
    assert result["status"] == "fail" and any("top-level member" in r for r in result["reasons"])


@pytest.mark.parametrize("member,value", [("created_by", 5), ("created_by", ""), ("created_at", "yesterday"), ("created_at", None),
                                          ("package_type", "other"), ("package_version", "9.9.9")])
def test_malformed_envelope_members_are_refused(member, value):
    p = _package()
    p[member] = value
    assert _evaluate_package_content_integrity(p, [])["status"] == "fail"
    assert evaluate_recipient_package(p, {})["recipient_reliance_decision"]["status"] == "fail"


def test_missing_envelope_member_is_refused():
    p = _package()
    del p["created_by"]
    assert _evaluate_package_content_integrity(p, [])["status"] == "fail"
