"""Current generation (CUR): Control Plane b19c47dd / runtime f7a55e2a / Manifest fa170815 / Replay (CUR_REPLAY_REVISION).

Added BESIDE the Programme 2 generation, which is unchanged. The end-to-end tests feed REAL current-generation records (Control Plane and
runtime run records written by their own flows at pristine b19c47dd / f7a55e2a checkouts; ``tests/data/current_generation``, provenance
alongside) through the Replay that defines the pairing, then ODES export and recipient validation, and check content, not only acceptance.

Replay setup for the end-to-end tests: the exporter requires the installed Replay HEAD to be an accepted, clean revision
(``exporter._require_installed_replay``). ``ODES_TEST_REPLAY_REPO`` names a git repository that contains CUR_REPLAY_REVISION (for example a
checkout of cognous-replay-bundle); the tests create a clean scratch clone of it at exactly that commit and never touch the checkout. The
end-to-end tests skip when it is not set (as the other Replay-dependent tests skip when Replay is not installed). This is a PROVISIONAL
DEVELOPMENT PIN, UNQUALIFIED, non-authorizing; provenance labels are caller-asserted.
"""
import copy
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from odes import exporter
from odes.common import (
    ALL_V2_CONTROL_PLANE_REVISIONS, CUR_PROFILE_VERSION, CUR_REPLAY_REVISION, CUR_REVISIONS, F5B_PROFILE_VERSION, F5B_REVISIONS,
    P2_PROFILE_VERSION, P2_REVISIONS, P4_PROFILE_VERSION, P4_REVISIONS, PROFILE_ID, PROFILE_V2_ID, SECURITY_PROFILE_VERSION,
    SECURITY_REVISIONS, SECURITY_RUNTIME_CP_REVISIONS, SECURITY_RUNTIME_GENERATIONS, accepted_replay_revisions, all_accepted_replay_revisions)
from odes.exporter import ExportError, ReplayRevisionUnsupportedError, _selected_v2_pins
from odes.recipient_validator import _evaluate_profile, _normalized_replay_material, evaluate_recipient_package

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "data" / "current_generation"
CUR_CP = "b19c47ddd020409d24e52e70b11359c46265edbb"
CUR_RT = "f7a55e2a8494801e49193f9f46935f0a971c248d"
CUR_MANIFEST = "fa170815ef96a54c233d0dd9da821b60debabf8b"
P2_CP, P2_RT = P2_REVISIONS["control_plane"], P2_REVISIONS["moltbot_safe"]
HISTORICAL = [(SECURITY_PROFILE_VERSION, SECURITY_REVISIONS), (F5B_PROFILE_VERSION, F5B_REVISIONS),
              (P4_PROFILE_VERSION, P4_REVISIONS), (P2_PROFILE_VERSION, P2_REVISIONS)]
LABEL_03 = "runtime-authority-reasons/0.3"
SCENARIOS = {  # name -> (execution status, retained refusal reasons or None)
    "valid": ("executed", None), "lost_ack": ("reconciled", None), "race": ("failed", None),
    "revoked": ("denied", ["grant_revoked"]), "unreadable": ("denied", ["status_unreadable"]),
    "purpose_closed": ("denied", ["purpose_closed"]), "purpose_reopened": ("denied", ["purpose_epoch_changed"]),
    "tampered_evidence": ("denied", ["evidence_signature_invalid"]), "input_dropped": ("denied", ["required_input_not_read"]),
}
# Shapes copied from real Control Plane b19c47dd records of the unsupported scope (registry-governed decision; policy-binding decision).
EFFECTIVE_CONFIGURATION = {"version": "effective-configuration-binding/0.1", "digest": "sha256:" + "1" * 64,
                           "members": {"scope": {"consumer_id": "consumer-test", "tenant_id": "tenant-alpha"}}}
POLICY_BINDING = {"approval_commitment_version": "approval-commitment/0.2", "policy_generation": 1, "policy_activation_ref": "sha256:" + "c" * 64}


# ================================================================================================ the pins (no Replay needed)
def test_the_replay_pin_is_this_one_literal_and_defined_in_one_place():
    # The only literal 40-hex Replay value in this file. Re-tying to the Replay merge SHA is a one-line change in common.py plus this literal.
    assert CUR_REPLAY_REVISION == "d48b8f1995fecdb928315aba27acbe0c48ad997c"
    assert CUR_REVISIONS["replay"] == CUR_REPLAY_REVISION
    source = (ROOT / "src" / "odes" / "common.py").read_text(encoding="utf-8")
    assert source.count(CUR_REPLAY_REVISION) == 1  # defined once; every other use derives from the constant


def test_the_current_tuple_is_exactly_these_four_forty_hex_pins():
    assert CUR_REVISIONS == {"manifest": CUR_MANIFEST, "replay": CUR_REPLAY_REVISION, "control_plane": CUR_CP, "moltbot_safe": CUR_RT}
    assert all(re.fullmatch(r"[0-9a-f]{40}", v) for v in CUR_REVISIONS.values())
    assert CUR_PROFILE_VERSION == "odes-cognous-stack-export-0.2.7-security-runtime-cur-candidate"
    assert SECURITY_RUNTIME_GENERATIONS[CUR_CP] == (CUR_PROFILE_VERSION, CUR_REVISIONS)
    assert _selected_v2_pins(CUR_CP) == CUR_REVISIONS


def test_the_current_generation_is_unique_and_shares_no_control_plane_runtime_or_replay_with_any_other():
    versions = [v for v, _ in SECURITY_RUNTIME_GENERATIONS.values()]
    assert len(versions) == len(set(versions)) == 5 and versions.count(CUR_PROFILE_VERSION) == 1
    for version, pins in HISTORICAL:
        assert version != CUR_PROFILE_VERSION
        for key in ("replay", "control_plane", "moltbot_safe"):
            assert pins[key] != CUR_REVISIONS[key], key
    # The Manifest is the one component the P2 generation and the current generation share (fa170815); nothing else is.
    assert P2_REVISIONS["manifest"] == CUR_REVISIONS["manifest"]
    assert not any(CUR_REVISIONS["manifest"] == pins["manifest"] for _, pins in HISTORICAL if pins is not P2_REVISIONS)


def test_the_current_pins_are_in_each_generation_set_exactly_once_and_the_sets_are_explicit():
    assert set(SECURITY_RUNTIME_GENERATIONS) == {SECURITY_REVISIONS["control_plane"], F5B_REVISIONS["control_plane"],
                                                 P4_REVISIONS["control_plane"], P2_CP, CUR_CP}
    assert SECURITY_RUNTIME_CP_REVISIONS == frozenset(SECURITY_RUNTIME_GENERATIONS)
    assert ALL_V2_CONTROL_PLANE_REVISIONS.count(CUR_CP) == 1
    assert ALL_V2_CONTROL_PLANE_REVISIONS[-2:] == (P2_CP, CUR_CP)  # appended after P2, P2 not moved
    assert accepted_replay_revisions(CUR_CP) == frozenset({CUR_REPLAY_REVISION})
    assert CUR_REPLAY_REVISION in all_accepted_replay_revisions()
    for _, pins in HISTORICAL:
        assert CUR_REPLAY_REVISION not in accepted_replay_revisions(pins["control_plane"])
        assert pins["replay"] not in accepted_replay_revisions(CUR_CP)


def test_historical_generations_are_byte_identical_to_before():
    assert SECURITY_REVISIONS == {"manifest": "e385f8c19b4444817a8b84b72ed6edbc37deb807", "replay": "3601fb218d5c02f5d86e55d2cf33983e5e130ac3",
        "control_plane": "996baeb476c8745b1a58ddc968b9eecc6a39b76b", "moltbot_safe": "fd6b76fa0e85feb5b67324114bf790d3a12fdaf1"}
    assert F5B_REVISIONS == {"manifest": "2c36bcd0b620dbfe7ad924bc7196a3f0c04c5c5e", "replay": "def0ee0f3af713283ea3cd13f0caf79e1607b651",
        "control_plane": "a34c3dc26f84a767a55f9d5c89dc0b53e63fefa5", "moltbot_safe": "4a83b175d2ef0e65a7ee22a0513bb94a5fdf3a6f"}
    assert P4_REVISIONS == {"manifest": "2c36bcd0b620dbfe7ad924bc7196a3f0c04c5c5e", "replay": "9aab3f6c34d2721ef1be3f6468b71dc3bad99a2a",
        "control_plane": "26a7e6594eb535827ccc248cbca36a7d119d613b", "moltbot_safe": "3024ef6e6ecf7da22e5f4fdf90d873f93b2a55c9"}
    assert P2_REVISIONS == {"manifest": "fa170815ef96a54c233d0dd9da821b60debabf8b", "replay": "40012b8c174c6f25685bd5d9bc93ff46cc9a5842",
        "control_plane": "7a4bcd40b3b49e61ff3c294dcca53b52f460b22c", "moltbot_safe": "c5e97e87dd239c821b1b4a406a55dcd03c5bc61f"}
    assert [v for v, _ in HISTORICAL] == ["odes-cognous-stack-export-0.2.3-security-runtime-candidate",
        "odes-cognous-stack-export-0.2.4-security-runtime-f5b-candidate", "odes-cognous-stack-export-0.2.5-security-runtime-p4-candidate",
        "odes-cognous-stack-export-0.2.6-security-runtime-p2-candidate"]
    for version, pins in HISTORICAL:
        assert SECURITY_RUNTIME_GENERATIONS[pins["control_plane"]] == (version, pins)
        assert _selected_v2_pins(pins["control_plane"]) == pins


def _package(version, pins, replay=None, profile=PROFILE_V2_ID):
    pinned = {**pins, "replay": pins["replay"] if replay is None else replay}
    return {"package_version": "0.1.0",
            "profile": {"implementation_profile": profile, "implementation_profile_version": version,
                        "schema_name": "pder-v0.1", "schema_version": "0.1"},
            "record": {"verification": {"conformance_profile": profile}},
            "provenance": {"pinned_revisions": pinned, "selected_revisions": pinned,
                           "replay_validation": {"required_revision": pinned["replay"]}}}


def test_the_current_profile_version_is_accepted_for_its_own_control_plane():
    assert _evaluate_profile(_package(CUR_PROFILE_VERSION, CUR_REVISIONS), [PROFILE_V2_ID])["status"] == "pass"
    left, right = _normalized_replay_material(_package(CUR_PROFILE_VERSION, CUR_REVISIONS), _package(CUR_PROFILE_VERSION, CUR_REVISIONS))
    assert left == right


@pytest.mark.parametrize("version,pins", HISTORICAL)
def test_historical_profile_versions_are_still_accepted_for_their_own_control_plane(version, pins):
    assert _evaluate_profile(_package(version, pins), [PROFILE_V2_ID])["status"] == "pass"


@pytest.mark.parametrize("version,pins", HISTORICAL)
def test_a_current_control_plane_with_a_historical_profile_version_is_refused(version, pins):  # N4
    assert _evaluate_profile(_package(version, CUR_REVISIONS), [PROFILE_V2_ID])["status"] == "unsupported"


@pytest.mark.parametrize("version,pins", HISTORICAL)
def test_a_historical_control_plane_with_the_current_profile_version_is_refused(version, pins):  # N4
    assert _evaluate_profile(_package(CUR_PROFILE_VERSION, pins), [PROFILE_V2_ID])["status"] == "unsupported"


def test_the_current_control_plane_cannot_be_relabelled_as_the_historical_profile_0_1():
    from odes.common import PROFILE_VERSION
    assert _evaluate_profile(_package(CUR_PROFILE_VERSION, CUR_REVISIONS, profile=PROFILE_ID), [PROFILE_ID])["status"] == "unsupported"
    result = _evaluate_profile(_package(PROFILE_VERSION, CUR_REVISIONS, profile=PROFILE_ID), [PROFILE_ID])
    assert result["status"] == "fail" and any("cannot be relabeled" in reason for reason in result["reasons"])


@pytest.mark.parametrize("version,pins", HISTORICAL)
def test_replay_pins_do_not_cross_between_the_current_and_each_historical_generation(version, pins):  # N3 / N5
    with pytest.raises(ValueError, match="exact qualified Replay revision"):
        _normalized_replay_material(_package(CUR_PROFILE_VERSION, CUR_REVISIONS, pins["replay"]), _package(CUR_PROFILE_VERSION, CUR_REVISIONS))
    with pytest.raises(ValueError, match="exact qualified Replay revision"):
        _normalized_replay_material(_package(version, pins, CUR_REPLAY_REVISION), _package(version, pins))


@pytest.mark.parametrize("component", ["manifest", "moltbot_safe"])
def test_a_current_package_carrying_a_historical_component_pin_cannot_match_the_reexport(component):  # N1 / N2 at package level
    other = P4_REVISIONS[component]
    mixed = _package(CUR_PROFILE_VERSION, {**CUR_REVISIONS, component: other})
    left, right = _normalized_replay_material(mixed, _package(CUR_PROFILE_VERSION, _selected_v2_pins(CUR_CP)))
    assert left != right
    mixed_p2 = _package(P2_PROFILE_VERSION, {**P2_REVISIONS, "moltbot_safe": CUR_RT})
    left, right = _normalized_replay_material(mixed_p2, _package(P2_PROFILE_VERSION, _selected_v2_pins(P2_CP)))
    assert left != right


def _near_misses(sha):
    return [sha[:8], sha[:12], sha[:39], sha.upper(), " " + sha, sha + " ", sha + "\n", sha[:-1] + ("0" if sha[-1] != "0" else "1"),
            "0" * 40, "a" * 40, "latest", sha[:8] + "*", ""]


@pytest.mark.parametrize("near", _near_misses(CUR_CP))
def test_no_near_miss_of_the_current_control_plane_is_a_known_generation(near):  # N8
    assert near not in ALL_V2_CONTROL_PLANE_REVISIONS and near not in SECURITY_RUNTIME_GENERATIONS
    assert accepted_replay_revisions(near) == frozenset()
    with pytest.raises(ExportError, match="unsupported Control Plane compatibility revision"):
        _selected_v2_pins(near)


@pytest.mark.parametrize("near", _near_misses(CUR_REPLAY_REVISION))
def test_no_near_miss_of_the_current_replay_is_accepted_as_installed_or_declared(near, monkeypatch):  # N8
    assert near not in all_accepted_replay_revisions()
    monkeypatch.setenv("ODES_ALLOW_UNVERIFIED_REPLAY", "0")
    monkeypatch.setattr(exporter, "installed_replay_revision", lambda: near)
    monkeypatch.setattr(exporter, "installed_replay_checkout_dirty", lambda: False)
    with pytest.raises((ReplayRevisionUnsupportedError, exporter.ReplayDependencyError)):
        exporter._require_installed_replay(CUR_CP)
    with pytest.raises(ValueError, match="exact qualified Replay revision"):
        _normalized_replay_material(_package(CUR_PROFILE_VERSION, CUR_REVISIONS, near), _package(CUR_PROFILE_VERSION, CUR_REVISIONS))


def test_the_installed_replay_gate_accepts_the_current_pin_when_clean_and_refuses_it_when_dirty(monkeypatch):
    monkeypatch.setenv("ODES_ALLOW_UNVERIFIED_REPLAY", "0")
    monkeypatch.setattr(exporter, "installed_replay_revision", lambda: CUR_REPLAY_REVISION)
    monkeypatch.setattr(exporter, "installed_replay_checkout_dirty", lambda: False)
    exporter._require_installed_replay(CUR_CP)
    monkeypatch.setattr(exporter, "installed_replay_checkout_dirty", lambda: True)
    with pytest.raises(ExportError, match="uncommitted"):
        exporter._require_installed_replay(CUR_CP)
    monkeypatch.setattr(exporter, "installed_replay_checkout_dirty", lambda: False)
    monkeypatch.setattr(exporter, "installed_replay_revision", lambda: None)
    with pytest.raises(exporter.ReplayDependencyError):
        exporter._require_installed_replay(CUR_CP)


# ================================================================================================ end to end with the real Replay
def _scratch_replay(tmp_path_factory):
    repo = os.environ.get("ODES_TEST_REPLAY_REPO")
    if not repo or not (Path(repo) / ".git").exists():
        return None
    scratch = tmp_path_factory.mktemp("replay-at-pin") / "replay"
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        subprocess.run(["git", "clone", "-q", "--no-checkout", str(repo), str(scratch)], check=True, capture_output=True, env=env, timeout=300)
        subprocess.run(["git", "-C", str(scratch), "checkout", "-q", "--detach", CUR_REPLAY_REVISION], check=True, capture_output=True, env=env, timeout=300)
        head = subprocess.run(["git", "-C", str(scratch), "rev-parse", "HEAD"], check=True, capture_output=True, text=True, env=env).stdout.strip()
    except Exception:
        return None
    return scratch if head == CUR_REPLAY_REVISION else None


@pytest.fixture(scope="module")
def replay(tmp_path_factory):
    """A clean scratch clone of the Replay repository at exactly CUR_REPLAY_REVISION, importable for this module only."""
    scratch = _scratch_replay(tmp_path_factory)
    if scratch is None:
        pytest.skip("needs ODES_TEST_REPLAY_REPO naming a git repository that contains the pinned Replay revision")
    saved_path = list(sys.path)
    saved_modules = {k: v for k, v in sys.modules.items() if k.split(".")[0] == "agent_replay_bundle"}
    for k in saved_modules:
        del sys.modules[k]
    saved_env = {k: os.environ.get(k) for k in ("ODES_ALLOW_UNVERIFIED_REPLAY", "PYTHONDONTWRITEBYTECODE")}
    os.environ["ODES_ALLOW_UNVERIFIED_REPLAY"] = "0"  # the real gate: installed HEAD must equal an accepted revision and be clean
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(scratch / "src"))
    try:
        from agent_replay_bundle import ImportContractError
        from agent_replay_bundle.importers import import_bounded_workflow
        yield type("ReplayAtPin", (), {"ImportContractError": ImportContractError, "import_bounded_workflow": staticmethod(import_bounded_workflow)})
    finally:
        sys.path[:] = saved_path
        for k in [k for k in sys.modules if k.split(".")[0] == "agent_replay_bundle"]:
            del sys.modules[k]
        sys.modules.update(saved_modules)
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def load(name="valid"):
    return tuple(json.loads((DATA / name / f).read_text(encoding="utf-8")) for f in ("control_plane_run.json", "proposal.json", "runtime_export.json"))


MANIFEST = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
POLICY_BASE = {"now": "2026-10-06T00:00:00Z", "purpose": "audit", "relying_party": "recipient.example.org", "status_inputs": {},
               "trusted_digests": [], "trusted_key_refs": [], "evaluation_scope": "audit", "status_max_age_seconds": 300,
               "allow_unauthenticated_informational_inspection": False}


def bundle_of(replay, name="valid", *, executor=True, label=CUR_CP):
    cp, proposal, runtime = load(name)
    return replay.import_bounded_workflow(cp, proposal=proposal, moltbot_export=runtime if executor else None,
                                          control_plane_revision=label).model_dump(mode="json")


def policy_for(package):
    return {**POLICY_BASE, "supported_profiles": [package["profile"]["implementation_profile"]]}


def seal(package):
    """Recompute the package digest after a deliberate tamper so the generation gates, not the digest, are what refuse it."""
    from odes.common import sha256 as digest
    package["package_digest"] = digest({k: package[k] for k in ("record", "profile", "integrity", "provenance")})
    return package


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_real_current_records_export_and_recipient_validate_with_their_content_retained(replay, name):
    status, reasons = SCENARIOS[name]
    cp, proposal, runtime = load(name)
    assert runtime["repository"]["revision"] == CUR_RT and runtime["execution_result"]["status"] == status
    package = exporter.export_cognous_stack_package(MANIFEST, bundle_of(replay, name))
    # profile and tuple stamped from the one generation
    assert package["profile"]["implementation_profile_version"] == CUR_PROFILE_VERSION
    prov = package["provenance"]
    assert prov["pinned_revisions"] == CUR_REVISIONS == prov["selected_revisions"]
    assert prov["replay_validation"]["required_revision"] == CUR_REPLAY_REVISION and prov["replay_validation"]["status"] == "reconstruction_complete"
    assert prov["supported_revisions"]["control_plane"] == [CUR_CP]
    # content, not only acceptance
    assert prov["retained_sources"]["manifest"] == MANIFEST
    meta = prov["retained_sources"]["reconstruction_bundle"]["metadata"]
    assert (meta["control_plane_revision"], meta["moltbot_safe_revision"], meta["manifest_revision"]) == (CUR_CP, CUR_RT, CUR_MANIFEST)
    facts = prov["execution_facts"]
    assert [r["status"] for r in facts["execution_results"]] == [status]
    assert facts["control_plane_evidence"] == [runtime["control_plane_evidence"]]
    assert len(facts["control_plane_attempt_transitions"]) == len(cp["attempts"])
    assert prov["decision_facts"]["proposal_commitment"] == cp["decisions"][0]["binding"]["proposal_commitment"]
    if reasons is not None:
        assert facts["control_plane_evidence"][0]["refusal"]["reasons"] == reasons and facts["execution_results"][0]["attempted"] is False
        assert [r["reasons"] for r in cp["refusals"]] == [reasons]
    # recipient validation
    result = evaluate_recipient_package(package, policy_for(package))
    assert result["replay_semantic_consistency"]["status"] == "pass"
    assert result["declared_profile_conformance"]["status"] == "pass"
    assert result["package_content_integrity"]["status"] == "pass"
    assert result["schema_validity"]["status"] == "pass"
    assert result["recipient_reliance_decision"]["status"] == "fail"  # no authority/freshness inputs: never reliance


def test_real_current_record_without_executor_export_exports_as_partial(replay):
    package = exporter.export_cognous_stack_package(MANIFEST, bundle_of(replay, executor=False))
    assert package["provenance"]["replay_validation"]["status"] == "reconstruction_partial"
    assert package["provenance"]["pinned_revisions"] == CUR_REVISIONS
    assert evaluate_recipient_package(package, policy_for(package))["replay_semantic_consistency"]["status"] == "pass"


def test_the_real_replay_in_use_is_exactly_the_pin_and_clean(replay):
    from odes.common import installed_replay_checkout_dirty, installed_replay_revision
    assert installed_replay_revision() == CUR_REPLAY_REVISION
    assert installed_replay_checkout_dirty() is False
    exporter._require_installed_replay(CUR_CP)


def test_explicit_restriction_semantics_also_export_under_the_current_generation(replay):
    package = exporter.export_cognous_stack_package(MANIFEST, bundle_of(replay), restriction_semantics="explicit")
    assert package["profile"]["implementation_profile_version"].startswith(CUR_PROFILE_VERSION)
    assert evaluate_recipient_package(package, policy_for(package))["replay_semantic_consistency"]["status"] == "pass"


# ------------------------------------------------------------------------------------------------ mixed and relabelled records
def test_a_current_bundle_relabelled_to_a_historical_generation_is_refused_at_export(replay):  # N1 / N2
    for label_cp, label_rt in ((P2_CP, CUR_RT), (CUR_CP, P2_RT)):
        bundle = bundle_of(replay)
        bundle["metadata"]["control_plane_revision"] = label_cp
        bundle["metadata"]["moltbot_safe_revision"] = label_rt
        with pytest.raises(ExportError, match="pinned Replay semantic validation failed|differs from accepted validator"):
            exporter.export_cognous_stack_package(MANIFEST, bundle)


@pytest.mark.parametrize("field,value", [("control_plane_revision", P2_CP), ("control_plane_revision", CUR_CP[:8]), ("control_plane_revision", CUR_CP.upper()),
                                         ("moltbot_safe_revision", P2_RT), ("moltbot_safe_revision", CUR_RT[:8]), ("manifest_revision", P4_REVISIONS["manifest"]),
                                         ("manifest_revision", "0" * 40)])
def test_a_tampered_bundle_revision_is_refused_at_export(replay, field, value):  # exporter.py retained-metadata equality; N8
    bundle = bundle_of(replay)
    bundle["metadata"][field] = value
    with pytest.raises(ExportError, match="pinned Replay semantic validation failed|differs from accepted validator|unsupported Control Plane"):
        exporter.export_cognous_stack_package(MANIFEST, bundle)


def test_a_bundle_without_a_control_plane_revision_is_refused(replay):  # N11
    bundle = bundle_of(replay)
    del bundle["metadata"]["control_plane_revision"]
    with pytest.raises(ExportError, match="control_plane_revision"):
        exporter.export_cognous_stack_package(MANIFEST, bundle)


def test_replay_refuses_a_current_record_under_a_historical_or_unknown_label_so_no_bundle_reaches_odes(replay):
    cp, proposal, runtime = load()
    for label in (P2_CP, P4_REVISIONS["control_plane"], CUR_CP[:8], CUR_CP.upper(), "latest", ""):
        with pytest.raises(replay.ImportContractError):
            replay.import_bounded_workflow(copy.deepcopy(cp), proposal=proposal, moltbot_export=copy.deepcopy(runtime), control_plane_revision=label)
    historical = copy.deepcopy(runtime)
    historical["repository"]["revision"] = P2_RT
    historical["provenance"]["source_asserted"]["repository_revision"] = P2_RT
    with pytest.raises(replay.ImportContractError, match="combination"):
        replay.import_bounded_workflow(copy.deepcopy(cp), proposal=proposal, moltbot_export=historical, control_plane_revision=CUR_CP)


@pytest.mark.parametrize("edit", [
    lambda p: p["provenance"]["pinned_revisions"].update(control_plane=P2_CP),
    lambda p: p["provenance"]["selected_revisions"].update(control_plane=P2_CP),
    lambda p: p["provenance"]["pinned_revisions"].update(replay=P2_REVISIONS["replay"]),
    lambda p: p["provenance"]["pinned_revisions"].update(moltbot_safe=P2_RT),
    lambda p: p["provenance"]["pinned_revisions"].update(manifest=P4_REVISIONS["manifest"]),
    lambda p: p["provenance"]["pinned_revisions"].update(replay=CUR_REPLAY_REVISION[:8]),
    lambda p: p["provenance"]["replay_validation"].update(required_revision=P2_REVISIONS["replay"]),
    lambda p: p["profile"].update(implementation_profile_version=P2_PROFILE_VERSION),
    lambda p: p["profile"].update(implementation_profile_version=CUR_PROFILE_VERSION + "x"),
    lambda p: p["profile"].update(implementation_profile=PROFILE_ID),
], ids=["cp-pin-p2", "cp-selected-p2", "replay-pin-p2", "runtime-pin-p2", "manifest-pin-p4", "replay-pin-short", "required-replay-p2",
        "profile-version-p2", "profile-version-suffix", "profile-id-0.1"])
def test_a_resealed_tampered_current_package_does_not_validate(replay, edit):
    package = exporter.export_cognous_stack_package(MANIFEST, bundle_of(replay))
    edit(package)
    result = evaluate_recipient_package(seal(package), policy_for(package))
    assert result["replay_semantic_consistency"]["status"] != "pass"
    assert result["recipient_reliance_decision"]["status"] != "pass"


def test_a_p2_package_still_validates_semantically_when_built_from_a_p2_bundle_label(replay):
    # Historical preserved end to end: the same real current-shaped records labelled P2 are accepted by Replay only in the cp-only form that
    # the P2 generation always accepted, and export under the P2 profile, not the current one (no relabel into the current generation).
    cp, proposal, _ = load()
    bundle = replay.import_bounded_workflow(cp, proposal=proposal, control_plane_revision=P2_CP).model_dump(mode="json")
    package = exporter.export_cognous_stack_package(MANIFEST, bundle)
    assert package["profile"]["implementation_profile_version"] == P2_PROFILE_VERSION
    assert package["provenance"]["pinned_revisions"] == P2_REVISIONS
    assert package["provenance"]["pinned_revisions"]["replay"] != CUR_REPLAY_REVISION


# ------------------------------------------------------------------------------------------------ explicit unsupported scope stays refused
def _authority(cp):
    return [d["binding"]["runtime_authority"] for d in cp["decisions"] if d.get("binding")]


def test_effective_configuration_is_refused_end_to_end(replay):
    cp, proposal, runtime = load()
    for a in _authority(cp):
        a["effective_configuration"] = copy.deepcopy(EFFECTIVE_CONFIGURATION)
    with pytest.raises(replay.ImportContractError, match="runtime authority fields unsupported"):
        replay.import_bounded_workflow(copy.deepcopy(cp), proposal=proposal, moltbot_export=copy.deepcopy(runtime), control_plane_revision=CUR_CP)
    bundle = bundle_of(replay)
    for r in bundle["records"]:
        if r["record_type"] == "runtime_decision":
            r["data"]["binding"]["runtime_authority"]["effective_configuration"] = copy.deepcopy(EFFECTIVE_CONFIGURATION)
    with pytest.raises(ExportError, match="pinned Replay semantic validation failed"):
        exporter.export_cognous_stack_package(MANIFEST, bundle)


@pytest.mark.parametrize("members", [{"approval_commitment_version": POLICY_BINDING["approval_commitment_version"]}, {"policy_generation": 1},
                                     {"policy_activation_ref": POLICY_BINDING["policy_activation_ref"]}, POLICY_BINDING])
def test_policy_binding_members_are_refused_end_to_end(replay, members):
    cp, proposal, runtime = load()
    for a in _authority(cp):
        a.update(members)
    with pytest.raises(replay.ImportContractError, match="runtime authority fields unsupported"):
        replay.import_bounded_workflow(copy.deepcopy(cp), proposal=proposal, moltbot_export=copy.deepcopy(runtime), control_plane_revision=CUR_CP)
    bundle = bundle_of(replay)
    for r in bundle["records"]:
        if r["record_type"] == "runtime_decision":
            r["data"]["binding"]["runtime_authority"].update(copy.deepcopy(members))
    with pytest.raises(ExportError, match="pinned Replay semantic validation failed"):
        exporter.export_cognous_stack_package(MANIFEST, bundle)


def test_reason_vocabulary_0_3_is_refused_end_to_end(replay):
    cp, proposal, runtime = load("revoked")
    for holder in (cp["refusals"][0], runtime["control_plane_evidence"]["refusal"]):
        holder["reason_vocabulary_version"] = LABEL_03
    with pytest.raises(replay.ImportContractError):
        replay.import_bounded_workflow(copy.deepcopy(cp), proposal=proposal, moltbot_export=copy.deepcopy(runtime), control_plane_revision=CUR_CP)
    cp, proposal, _ = load()
    cp["decisions"][0]["reason_vocabulary_version"] = LABEL_03
    with pytest.raises(replay.ImportContractError):
        replay.import_bounded_workflow(cp, proposal=proposal, control_plane_revision=CUR_CP)
    bundle = bundle_of(replay, "revoked")
    for r in bundle["records"]:
        if r["record_type"] == "runtime_decision":
            r["data"]["reason_vocabulary_version"] = LABEL_03
    with pytest.raises(ExportError, match="pinned Replay semantic validation failed"):
        exporter.export_cognous_stack_package(MANIFEST, bundle)


@pytest.mark.parametrize("member", ["selection_refusal", "authorization_pin"])
def test_selection_refusal_and_authorization_pin_evidence_are_refused_end_to_end(replay, member):
    cp, proposal, runtime = load("revoked")
    runtime["control_plane_evidence"][member] = {"version": "0.1"}
    runtime["execution_result"]["control_plane_evidence"][member] = {"version": "0.1"}
    with pytest.raises(replay.ImportContractError):
        replay.import_bounded_workflow(copy.deepcopy(cp), proposal=proposal, moltbot_export=copy.deepcopy(runtime), control_plane_revision=CUR_CP)
    bundle = bundle_of(replay, "revoked")
    for r in bundle["records"]:
        if r["record_type"] == "executor_control_plane_evidence":
            r["data"][member] = {"version": "0.1"}
    with pytest.raises(ExportError, match="pinned Replay semantic validation failed"):
        exporter.export_cognous_stack_package(MANIFEST, bundle)


def test_an_unsupported_member_injected_into_an_exported_package_does_not_validate(replay):
    package = exporter.export_cognous_stack_package(MANIFEST, bundle_of(replay))
    for r in package["provenance"]["retained_sources"]["reconstruction_bundle"]["records"]:
        if r["record_type"] == "runtime_decision":
            r["data"]["binding"]["runtime_authority"]["effective_configuration"] = copy.deepcopy(EFFECTIVE_CONFIGURATION)
    result = evaluate_recipient_package(seal(package), policy_for(package))
    assert result["replay_semantic_consistency"]["status"] != "pass"
    assert result["recipient_reliance_decision"]["status"] != "pass"
