"""Restriction semantics for the explicit restriction profile.

Legacy exports are unchanged (an absent restriction value is exported as true, as before). The new profile id
``odes_cognous_stack_export_0_2_restrictions`` records, per flag, whether the value is explicit or unknown, keeps ``true`` as a
conservative placeholder for unknown (never ``false``), carries a mandatory limitation, and is evaluated by the recipient validator:
an unknown restriction blocks reliance, an explicit false must be attributable to a retained source record.
"""
import copy
import json
from pathlib import Path

import pytest

from odes import exporter
from odes.common import (PROFILE_V2_ID, PROFILE_V2_RESTRICTIONS_ID, PROFILE_V2_VERSION, RESTRICTION_SEMANTICS_VERSION,
                         RESTRICTION_UNKNOWN_LIMIT, RESTRICTION_VERSION_SUFFIX, sha256)
from odes.exporter import ExportError
from odes.recipient_validator import evaluate_recipient_package

ROOT = Path(__file__).resolve().parents[1]
LEGACY = json.loads((ROOT / "examples" / "producer-v2" / "lost_ack.package.json").read_text())
SOURCE = {"record_type": "runtime_proposal", "record_id": "r1", "record_hash": "sha256:" + "a" * 64}


def coords(risk, source=SOURCE):
    return exporter._restriction_coordinates(risk, source)


def test_absent_values_are_unknown_and_use_a_true_placeholder():
    flags, semantics = coords({})
    assert flags["restricted_use_flag"] is True and flags["prohibited_use_flag"] is True
    assert flags["jurisdiction"] == "unknown"
    assert semantics["restricted_use_flag"]["state"] == "unknown"
    assert semantics["prohibited_use_flag"]["state"] == "unknown"
    assert semantics["jurisdiction"]["state"] == "unknown"
    assert semantics["semantics_version"] == RESTRICTION_SEMANTICS_VERSION


def test_explicit_null_is_unknown_not_false():
    flags, semantics = coords({"restricted_use_flag": None, "prohibited_use_flag": None})
    assert flags["restricted_use_flag"] is True
    assert semantics["restricted_use_flag"]["state"] == "unknown"


def test_explicit_values_keep_their_meaning():
    flags, semantics = coords({"restricted_use_flag": False, "prohibited_use_flag": False, "jurisdiction": "US-WA", "risk_tier": "low"})
    assert (flags["restricted_use_flag"], flags["prohibited_use_flag"]) == (False, False)
    assert semantics["restricted_use_flag"]["state"] == "explicit_false"
    assert semantics["jurisdiction"] == {"state": "explicit"}
    assert semantics["source"] == SOURCE
    flags, semantics = coords({"restricted_use_flag": True, "prohibited_use_flag": True})
    assert (flags["restricted_use_flag"], flags["prohibited_use_flag"]) == (True, True)
    assert semantics["prohibited_use_flag"]["state"] == "explicit_true"


@pytest.mark.parametrize("risk", [
    {"restricted_use_flag": "no"}, {"prohibited_use_flag": 0}, {"restricted_use_flag": "false"},
    {"restricted_use_flag": False, "prohibited_use_flag": True},
    {"jurisdiction": 5}, {"jurisdiction": ""}, {"jurisdiction": ["US"]},
])
def test_contradictory_or_malformed_metadata_is_refused(risk):
    with pytest.raises(ExportError):
        coords(risk)


def test_explicit_false_without_a_source_record_is_refused():
    with pytest.raises(ExportError, match="source record"):
        coords({"restricted_use_flag": False, "prohibited_use_flag": False}, None)


def test_unknown_without_a_source_record_is_allowed():
    flags, semantics = coords({}, None)
    assert flags["restricted_use_flag"] is True
    assert semantics["source"] is None


def test_unknown_restriction_semantics_value_is_refused_by_the_exporter():
    with pytest.raises(ExportError, match="restriction_semantics"):
        exporter.export_cognous_stack_package({}, {}, restriction_semantics="lenient")


def _make(states, flags, *, jurisdiction="unknown", jurisdiction_state=None, source=SOURCE, limit=True, drop_semantics=False):
    p = copy.deepcopy(LEGACY)
    p["profile"]["implementation_profile"] = PROFILE_V2_RESTRICTIONS_ID
    p["profile"]["implementation_profile_version"] = PROFILE_V2_VERSION + RESTRICTION_VERSION_SUFFIX
    p["record"]["verification"]["conformance_profile"] = PROFILE_V2_RESTRICTIONS_ID
    risk = p["record"]["risk_coordinates"]
    risk["restricted_use_flag"], risk["prohibited_use_flag"] = flags
    risk["jurisdiction"] = jurisdiction
    unknown = "unknown" in states or (jurisdiction_state or ("unknown" if jurisdiction == "unknown" else "explicit")) == "unknown"
    if not drop_semantics:
        p["provenance"]["restriction_semantics"] = {
            "semantics_version": RESTRICTION_SEMANTICS_VERSION, "source": source,
            "restricted_use_flag": {"state": states[0]}, "prohibited_use_flag": {"state": states[1]},
            "jurisdiction": {"state": jurisdiction_state or ("unknown" if jurisdiction == "unknown" else "explicit")}}
    if unknown and limit:
        p["provenance"]["limits"] = [*p["provenance"]["limits"], RESTRICTION_UNKNOWN_LIMIT]
    return _seal(p)


def _seal(p):
    core = {"record": p["record"], "profile": p["profile"]}
    p["integrity"]["value"] = sha256(core)
    p["package_digest"] = sha256({k: p[k] for k in ("record", "profile", "integrity", "provenance")})
    return p


POLICY = {"supported_profiles": [PROFILE_V2_RESTRICTIONS_ID], "now": "2026-01-01T00:00:00Z", "relying_party": "recipient.example.org",
          "purpose": "audit", "jurisdiction": "US-WA"}


def consumption(package, policy=POLICY):
    return evaluate_recipient_package(package, policy)


def test_unknown_restriction_blocks_consumption_without_asserting_a_prohibition():
    result = consumption(_make(("unknown", "unknown"), (True, True)))
    layer = result["consumption_conditions"]
    assert layer["status"] == "fail"
    assert any("restriction is unknown" in r for r in layer["reasons"])
    assert result["package_content_integrity"]["status"] == "pass"
    assert result["declared_profile_conformance"]["status"] == "pass"
    assert result["recipient_reliance_decision"]["status"] == "fail"


def test_unknown_restriction_cannot_become_informational_only():
    policy = {**POLICY, "allow_unauthenticated_informational_inspection": True}
    result = consumption(_make(("unknown", "unknown"), (True, True)), policy)
    assert result["recipient_reliance_decision"]["status"] == "fail"


def test_missing_mandatory_limitation_fails():
    layer = consumption(_make(("unknown", "unknown"), (True, True), limit=False))["consumption_conditions"]
    assert layer["status"] == "fail"
    assert any("mandatory limitation" in r for r in layer["reasons"])


def test_missing_semantics_member_fails():
    layer = consumption(_make(("explicit_false", "explicit_false"), (False, False), jurisdiction="US-WA", drop_semantics=True))["consumption_conditions"]
    assert layer["status"] == "fail"
    assert any("restriction_semantics" in r for r in layer["reasons"])


def test_explicit_false_with_a_source_and_matching_jurisdiction_passes_consumption():
    layer = consumption(_make(("explicit_false", "explicit_false"), (False, False), jurisdiction="US-WA"))["consumption_conditions"]
    assert layer["status"] == "pass", layer["reasons"]


def test_explicit_false_without_attribution_fails():
    layer = consumption(_make(("explicit_false", "explicit_false"), (False, False), jurisdiction="US-WA", source=None))["consumption_conditions"]
    assert layer["status"] == "fail"
    assert any("attributable" in r for r in layer["reasons"])


@pytest.mark.parametrize("states,flags", [
    (("explicit_false", "explicit_false"), (True, False)),
    (("explicit_false", "explicit_false"), (False, True)),
    (("explicit_true", "explicit_true"), (False, False)),
    (("unknown", "unknown"), (False, False)),
    (("unknown", "explicit_false"), (False, False)),
])
def test_record_flag_must_match_the_declared_state(states, flags):
    layer = consumption(_make(states, flags, jurisdiction="US-WA"))["consumption_conditions"]
    assert layer["status"] == "fail"
    assert any("does not match" in r for r in layer["reasons"])


def test_unknown_jurisdiction_never_matches_even_a_policy_that_says_unknown():
    package = _make(("explicit_false", "explicit_false"), (False, False), jurisdiction="unknown")
    layer = consumption(package, {**POLICY, "jurisdiction": "unknown"})["consumption_conditions"]
    assert layer["status"] == "fail"
    assert any("jurisdiction" in r for r in layer["reasons"])


def test_new_profile_requires_explicit_support_in_the_policy():
    package = _make(("unknown", "unknown"), (True, True))
    result = consumption(package, {**POLICY, "supported_profiles": [PROFILE_V2_ID]})
    assert result["declared_profile_conformance"]["status"] == "unsupported"


def test_relabelling_between_legacy_and_the_new_profile_fails():
    package = _make(("unknown", "unknown"), (True, True))
    package["profile"]["implementation_profile"] = PROFILE_V2_ID
    package["record"]["verification"]["conformance_profile"] = PROFILE_V2_ID
    assert consumption(_seal(package), {**POLICY, "supported_profiles": [PROFILE_V2_ID]})["declared_profile_conformance"]["status"] == "unsupported"
    legacy = copy.deepcopy(LEGACY)
    legacy["profile"]["implementation_profile"] = PROFILE_V2_RESTRICTIONS_ID
    legacy["record"]["verification"]["conformance_profile"] = PROFILE_V2_RESTRICTIONS_ID
    assert consumption(_seal(legacy))["declared_profile_conformance"]["status"] == "unsupported"


def test_control_legacy_package_is_evaluated_as_before():
    result = consumption(copy.deepcopy(LEGACY), {**POLICY, "supported_profiles": [PROFILE_V2_ID]})
    assert result["declared_profile_conformance"]["status"] == "pass"
    assert result["package_content_integrity"]["status"] == "pass"
    reasons = result["consumption_conditions"]["reasons"]
    assert "prohibited or unavailable use restriction" in reasons
    assert not any("restriction is unknown" in r for r in reasons)


def _pinned_replay_available():
    try:
        import agent_replay_bundle  # noqa: F401
        from odes.common import all_accepted_replay_revisions, installed_replay_revision
        return installed_replay_revision() in all_accepted_replay_revisions()
    except Exception:
        return False


needs_replay = pytest.mark.skipif(not _pinned_replay_available(), reason="needs the accepted Replay revision installed")


def _export(mode):
    sources = LEGACY["provenance"]["retained_sources"]
    cond = LEGACY["record"]["consumption_conditions"]
    return exporter.export_cognous_stack_package(sources["manifest"], sources["reconstruction_bundle"], relying_party="recipient.example.org",
                                                 purpose="audit", expires_at=cond["expires_at"], restriction_semantics=mode)


@needs_replay
def test_control_legacy_export_is_digest_identical_to_the_retained_example():
    exported = _export("legacy")
    assert exported["package_digest"] == LEGACY["package_digest"]
    assert exported["integrity"]["value"] == LEGACY["integrity"]["value"]


@needs_replay
def test_explicit_export_end_to_end():
    exported = _export("explicit")
    assert exported["profile"]["implementation_profile"] == PROFILE_V2_RESTRICTIONS_ID
    assert exported["record"]["verification"]["conformance_profile"] == PROFILE_V2_RESTRICTIONS_ID
    risk = exported["record"]["risk_coordinates"]
    assert risk["restricted_use_flag"] is True and risk["prohibited_use_flag"] is True
    assert RESTRICTION_UNKNOWN_LIMIT in exported["provenance"]["limits"]
    assert exported["provenance"]["restriction_semantics"]["restricted_use_flag"]["state"] == "unknown"
    result = evaluate_recipient_package(exported, {**POLICY, "supported_profiles": [PROFILE_V2_RESTRICTIONS_ID]})
    assert result["replay_semantic_consistency"]["status"] == "pass"
    assert result["package_content_integrity"]["status"] == "pass"
    assert result["declared_profile_conformance"]["status"] == "pass"
    assert result["consumption_conditions"]["status"] == "fail"
    assert result["recipient_reliance_decision"]["status"] == "fail"
