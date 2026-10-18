"""Round 2 (decision 39-I, 39-J): recipient consumption conditions, package top-level members, and the exporter's qualified-build gate."""
import copy
import json
from pathlib import Path

import pytest

from odes import exporter
from odes.exporter import ExportError
from odes.recipient_validator import _evaluate_consumption, _evaluate_package_content_integrity, evaluate_recipient_package

ROOT = Path(__file__).resolve().parents[1]
RISK = {"prohibited_use_flag": False, "restricted_use_flag": False, "jurisdiction": "test"}
POLICY = {"jurisdiction": "test"}


def _record(**conditions):
    return {"consumption_conditions": {"permitted_purposes": ["audit"], **conditions}, "risk_coordinates": RISK}


def _package():
    return json.loads((ROOT / "examples/producer-v2/lost_ack.package.json").read_text(encoding="utf-8"))


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


# ------------------------------------------------------------------ exporter gate

def test_dirty_replay_checkout_is_refused_unless_development_override(monkeypatch):
    from odes.common import P2_REVISIONS
    monkeypatch.setenv("ODES_ALLOW_UNVERIFIED_REPLAY", "0")
    monkeypatch.setattr(exporter, "installed_replay_revision", lambda: P2_REVISIONS["replay"])
    monkeypatch.setattr(exporter, "installed_replay_checkout_dirty", lambda: False)
    exporter._require_installed_replay(P2_REVISIONS["control_plane"])
    monkeypatch.setattr(exporter, "installed_replay_checkout_dirty", lambda: True)
    with pytest.raises(ExportError, match="uncommitted"):
        exporter._require_installed_replay(P2_REVISIONS["control_plane"])
    monkeypatch.setenv("ODES_ALLOW_UNVERIFIED_REPLAY", "1")
    exporter._require_installed_replay(P2_REVISIONS["control_plane"])


def test_dirty_state_of_a_real_checkout_is_read(tmp_path, monkeypatch):
    import os, subprocess, sys
    from odes.common import installed_replay_checkout_dirty
    repo = tmp_path / "replay"
    (repo / "agent_replay_bundle").mkdir(parents=True)
    (repo / "agent_replay_bundle" / "__init__.py").write_text("")
    env = {"GIT_AUTHOR_NAME": "a", "GIT_AUTHOR_EMAIL": "a@example.org", "GIT_COMMITTER_NAME": "a", "GIT_COMMITTER_EMAIL": "a@example.org", "PATH": os.environ["PATH"]}
    for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "x"]):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True, env=env)
    monkeypatch.syspath_prepend(str(repo))
    sys.modules.pop("agent_replay_bundle", None)
    assert installed_replay_checkout_dirty() is False
    (repo / "agent_replay_bundle" / "__init__.py").write_text("changed = 1\n")
    assert installed_replay_checkout_dirty() is True
    sys.modules.pop("agent_replay_bundle", None)


@pytest.mark.parametrize("bundle", [{}, {"metadata": None}, {"metadata": {}}, {"metadata": {"control_plane_revision": 5}}, {"metadata": "x"}])
def test_bundle_without_a_control_plane_revision_is_refused(bundle):
    with pytest.raises(ExportError, match="control_plane_revision"):
        exporter._bundle_control_plane_revision(bundle)


def test_bundle_with_a_control_plane_revision_is_read():
    from odes.common import P2_REVISIONS
    assert exporter._bundle_control_plane_revision({"metadata": {"control_plane_revision": P2_REVISIONS["control_plane"]}}) == P2_REVISIONS["control_plane"]
