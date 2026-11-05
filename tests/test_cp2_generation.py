"""CP-2 generation (strict-tenant effect identity): Control Plane 484fdbd2 / runtime f7a55e2a / Manifest fa170815 / Replay (CP2_REPLAY_REVISION).

Added BESIDE the current generation (CUR), which is unchanged (this is not a third in-place re-tie of CUR). Control Plane 484fdbd297235dd24148ddb0703f2055a31eabff is the
strict tenant-aware effect identity generation (``bounded-authorization-effect/0.3-strict-tenant``; assigned under the Constitution at pin 1c2e920f, adoption not recorded).
The Replay generation id is ``control-plane-strict-tenant-stack@484fdbd2`` (cognous-replay-bundle PR #87).

PROVISIONAL: the Replay pin R* below is the head of Replay PR #87 (d6c05bc5), to be re-pinned to the Replay MERGE SHA after #87 merges and an independent review is CLEAR.
The re-tie touches the literal ``R_STAR`` below, ``CP2_REPLAY_REVISION`` in ``src/odes/common.py`` and the short SHA in the docs register. UNQUALIFIED, non-authorizing.

What is real and what is asserted by the caller:
* ``tests/data/cp2_generation`` holds REAL Control Plane 484fdbd2 records (vendored byte-identically from the Replay PR; digests checked). They are tenant-aware, executor-less
  (no tenant-aware executor export exists), so they export as ``reconstruction_partial``. Strict-tenant records are proven to pass the security-runtime path ONLY for that case.
* The nine executor scenarios reuse the CUR fixtures (``tests/data/current_generation``, captured at b19c47dd / f7a55e2a, tenantless). Under the CP-2 label they are a CALLER-ASSERTED
  label: they exercise the ODES CP-2 path (stamps, gates, envelope, recipient validation); they are NOT evidence about Control Plane 484fdbd2 and say nothing about strict-tenant.
* Provenance labels are caller-asserted. Nothing measures a record against a Control Plane checkout, so a record relabelled before it enters Replay is not detected (see the
  characterization tests at the end). ODES never recomputes ``effect_id``; Replay is the only recompute site, and ODES retains it verbatim.

End-to-end tests need ODES_TEST_REPLAY_REPO (a git repository containing R* reachable through a branch or tag ref); ODES_REQUIRE_CP2_E2E=1 turns that skip into a FAILURE (CI).
"""
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from odes import exporter
from odes.common import (
    ALL_V2_CONTROL_PLANE_REVISIONS, CP2_PROFILE_VERSION, CP2_REPLAY_REVISION, CP2_REVISIONS, CUR_PROFILE_VERSION, CUR_REPLAY_REVISION, CUR_REVISIONS,
    F5B_PROFILE_VERSION, F5B_REVISIONS, P2_PROFILE_VERSION, P2_REVISIONS, P4_PROFILE_VERSION, P4_REVISIONS, PROFILE_ID, PROFILE_V2_ID, PROFILE_VERSION,
    SECURITY_PROFILE_VERSION, SECURITY_REVISIONS, SECURITY_RUNTIME_CP_REVISIONS, SECURITY_RUNTIME_GENERATIONS, accepted_replay_revisions,
    all_accepted_replay_revisions)
from odes.common import sha256 as digest_of
from odes.exporter import ExportError, ReplayRevisionUnsupportedError, _selected_v2_pins
from odes.recipient_validator import _evaluate_profile, _normalized_replay_material, evaluate_recipient_package

ROOT = Path(__file__).resolve().parents[1]
CUR_DATA = ROOT / "tests" / "data" / "current_generation"
DATA = ROOT / "tests" / "data" / "cp2_generation"
# The literals of this generation, written out here (not read back from common.py).
CP2_CP = "484fdbd297235dd24148ddb0703f2055a31eabff"
CP2_RT = "f7a55e2a8494801e49193f9f46935f0a971c248d"
CP2_MANIFEST = "fa170815ef96a54c233d0dd9da821b60debabf8b"
R_STAR = "d6c05bc552e404263a149548fc3f19ecbd8203b4"  # PROVISIONAL: Replay PR #87 head; re-pin to the Replay merge SHA after #87 merges and review is CLEAR
CP2_VERSION = "odes-cognous-stack-export-0.2.8-security-runtime-cp2-candidate"
CP2_PROFILE_ID = "control-plane-strict-tenant-stack@484fdbd2"
CUR_CP = "b19c47ddd020409d24e52e70b11359c46265edbb"
CUR_RT = "f7a55e2a8494801e49193f9f46935f0a971c248d"
CUR_REPLAY = "6f45e288ae37ec7e7712f9296760927d2d843bba"
P2_CP, P2_RT = P2_REVISIONS["control_plane"], P2_REVISIONS["moltbot_safe"]
HISTORICAL = [(SECURITY_PROFILE_VERSION, SECURITY_REVISIONS), (F5B_PROFILE_VERSION, F5B_REVISIONS),
              (P4_PROFILE_VERSION, P4_REVISIONS), (P2_PROFILE_VERSION, P2_REVISIONS)]
WITH_CUR = [*HISTORICAL, (CUR_PROFILE_VERSION, CUR_REVISIONS)]
STRICT_ID = "sha256:4e5844d6d53ab6f8694e9c76cb6238ec4110137dd35de73cb0b22963961ecde8"
LEGACY_ID = "sha256:f42a2866e8359b1adca34c53c91f5f56b375203b6957fd7408f70d211629452a"
STRICT_MARKER = "bounded-authorization-effect/0.3-strict-tenant"
LEGACY_MARKER = "bounded-authorization-effect/0.2"
SCENARIOS = {  # name -> (execution status, retained refusal reasons or None); CUR-captured fixtures presented under the CP-2 label (caller-asserted)
    "valid": ("executed", None), "lost_ack": ("reconciled", None), "race": ("failed", None),
    "revoked": ("denied", ["grant_revoked"]), "unreadable": ("denied", ["status_unreadable"]),
    "purpose_closed": ("denied", ["purpose_closed"]), "purpose_reopened": ("denied", ["purpose_epoch_changed"]),
    "tampered_evidence": ("denied", ["evidence_signature_invalid"]), "input_dropped": ("denied", ["required_input_not_read"]),
}
EFFECTIVE_CONFIGURATION = {"version": "effective-configuration-binding/0.1", "digest": "sha256:" + "1" * 64,
                           "members": {"scope": {"consumer_id": "consumer-test", "tenant_id": "tenant-alpha"}}}
POLICY_BINDING = {"approval_commitment_version": "approval-commitment/0.2", "policy_generation": 1, "policy_activation_ref": "sha256:" + "c" * 64}
LABEL_03 = "runtime-authority-reasons/0.3"
GOVERNED_SELECTOR = "registry-governed-effective-configuration/0.1"


# ================================================================================================ the pins (no Replay needed)
def test_p1_the_cp2_tuple_is_exactly_these_four_forty_hex_pins_and_the_replay_pin_is_defined_once():
    assert CP2_REVISIONS == {"manifest": CP2_MANIFEST, "replay": R_STAR, "control_plane": CP2_CP, "moltbot_safe": CP2_RT}
    assert CP2_REPLAY_REVISION == R_STAR == CP2_REVISIONS["replay"]
    assert all(re.fullmatch(r"[0-9a-f]{40}", v) for v in CP2_REVISIONS.values())
    assert CP2_PROFILE_VERSION == CP2_VERSION
    assert SECURITY_RUNTIME_GENERATIONS[CP2_CP] == (CP2_VERSION, CP2_REVISIONS)
    assert _selected_v2_pins(CP2_CP) == CP2_REVISIONS
    source = (ROOT / "src" / "odes" / "common.py").read_text(encoding="utf-8")
    assert source.count(R_STAR) == 1  # the R* pin is one line in common.py; every other use derives from the constant
    assert len(re.findall(r"^CP2_REPLAY_REVISION = \"[0-9a-f]{40}\"$", source, re.M)) == 1


def test_p1_the_cp2_manifest_and_runtime_are_literals_not_references_to_cur():
    source = (ROOT / "src" / "odes" / "common.py").read_text(encoding="utf-8")
    block = source.split("CP2_REVISIONS = {")[1].split("}")[0]
    assert CP2_MANIFEST in block and CP2_RT in block and "CUR_REVISIONS" not in block  # a later CUR re-tie cannot move CP-2


def test_p2_the_cp2_pins_are_in_each_generation_set_exactly_once_and_the_sets_are_explicit():
    assert set(SECURITY_RUNTIME_GENERATIONS) == {SECURITY_REVISIONS["control_plane"], F5B_REVISIONS["control_plane"], P4_REVISIONS["control_plane"],
                                                 P2_CP, CUR_CP, CP2_CP}
    assert SECURITY_RUNTIME_CP_REVISIONS == frozenset(SECURITY_RUNTIME_GENERATIONS)
    assert ALL_V2_CONTROL_PLANE_REVISIONS.count(CP2_CP) == 1
    assert ALL_V2_CONTROL_PLANE_REVISIONS[-3:] == (P2_CP, CUR_CP, CP2_CP)  # appended after CUR; CUR and P2 not moved
    assert accepted_replay_revisions(CP2_CP) == frozenset({R_STAR})
    assert R_STAR in all_accepted_replay_revisions()
    assert accepted_replay_revisions(CUR_CP) == frozenset({CUR_REPLAY})  # CUR is not re-tied
    for _, pins in WITH_CUR:
        assert R_STAR not in accepted_replay_revisions(pins["control_plane"]), pins["control_plane"]
        assert pins["replay"] not in accepted_replay_revisions(CP2_CP), pins["replay"]


def test_p3_the_cp2_generation_is_unique_and_shares_only_manifest_and_runtime_with_cur():
    versions = [v for v, _ in SECURITY_RUNTIME_GENERATIONS.values()]
    assert len(versions) == len(set(versions)) == 6 and versions.count(CP2_VERSION) == 1
    for version, pins in WITH_CUR:
        assert version != CP2_VERSION
        assert pins["control_plane"] != CP2_CP and pins["replay"] != R_STAR
    # Shared on purpose: the unchanged CUR runtime and Manifest. Runtime uniqueness is NOT asserted for CP-2.
    assert CUR_REVISIONS["moltbot_safe"] == CP2_REVISIONS["moltbot_safe"] and CUR_REVISIONS["manifest"] == CP2_REVISIONS["manifest"]
    assert P2_REVISIONS["manifest"] == CP2_REVISIONS["manifest"]
    assert not any(pins["moltbot_safe"] == CP2_RT for _, pins in HISTORICAL)  # the runtime is shared with CUR only
    assert not any(pins["manifest"] == CP2_MANIFEST for _, pins in HISTORICAL if pins is not P2_REVISIONS)


def test_p4_cur_and_every_historical_generation_are_byte_identical_to_before():
    assert CUR_REVISIONS == {"manifest": CP2_MANIFEST, "replay": CUR_REPLAY, "control_plane": CUR_CP, "moltbot_safe": CUR_RT}
    assert CUR_PROFILE_VERSION == "odes-cognous-stack-export-0.2.7-security-runtime-cur-candidate"
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
    for version, pins in WITH_CUR:
        assert SECURITY_RUNTIME_GENERATIONS[pins["control_plane"]] == (version, pins)
        assert _selected_v2_pins(pins["control_plane"]) == pins
    assert accepted_replay_revisions(CUR_CP) == frozenset({CUR_REPLAY})
    source = (ROOT / "src" / "odes" / "common.py").read_text(encoding="utf-8")
    assert source.count(CUR_REPLAY) == 1  # CUR still pins its own Replay once, in its own block


def _package(version, pins, replay=None, profile=PROFILE_V2_ID):
    pinned = {**pins, "replay": pins["replay"] if replay is None else replay}
    return {"package_version": "0.1.0",
            "profile": {"implementation_profile": profile, "implementation_profile_version": version,
                        "schema_name": "pder-v0.1", "schema_version": "0.1"},
            "record": {"verification": {"conformance_profile": profile}},
            "provenance": {"pinned_revisions": pinned, "selected_revisions": pinned,
                           "replay_validation": {"required_revision": pinned["replay"]}}}


def test_p5_the_cp2_profile_version_is_accepted_for_its_own_control_plane():
    assert _evaluate_profile(_package(CP2_VERSION, CP2_REVISIONS), [PROFILE_V2_ID])["status"] == "pass"
    left, right = _normalized_replay_material(_package(CP2_VERSION, CP2_REVISIONS), _package(CP2_VERSION, CP2_REVISIONS))
    assert left == right


@pytest.mark.parametrize("version,pins", WITH_CUR)
def test_p5_a_cp2_control_plane_with_another_profile_version_is_refused(version, pins):  # N4
    assert _evaluate_profile(_package(version, CP2_REVISIONS), [PROFILE_V2_ID])["status"] == "unsupported"


@pytest.mark.parametrize("version,pins", WITH_CUR)
def test_p5_another_control_plane_with_the_cp2_profile_version_is_refused(version, pins):  # N4
    assert _evaluate_profile(_package(CP2_VERSION, pins), [PROFILE_V2_ID])["status"] == "unsupported"


@pytest.mark.parametrize("version,pins", WITH_CUR)
def test_p5_cur_and_historical_profile_versions_are_still_accepted_for_their_own_control_plane(version, pins):
    assert _evaluate_profile(_package(version, pins), [PROFILE_V2_ID])["status"] == "pass"


def test_p5_the_cp2_control_plane_cannot_be_relabelled_as_the_historical_profile_0_1():
    assert _evaluate_profile(_package(CP2_VERSION, CP2_REVISIONS, profile=PROFILE_ID), [PROFILE_ID])["status"] == "unsupported"
    result = _evaluate_profile(_package(PROFILE_VERSION, CP2_REVISIONS, profile=PROFILE_ID), [PROFILE_ID])
    assert result["status"] == "fail" and any("cannot be relabeled" in reason for reason in result["reasons"])


@pytest.mark.parametrize("version,pins", WITH_CUR)
def test_p6_replay_pins_do_not_cross_between_cp2_and_every_other_generation(version, pins):  # N3 / N5
    with pytest.raises(ValueError, match="exact qualified Replay revision"):
        _normalized_replay_material(_package(CP2_VERSION, CP2_REVISIONS, pins["replay"]), _package(CP2_VERSION, CP2_REVISIONS))
    with pytest.raises(ValueError, match="exact qualified Replay revision"):
        _normalized_replay_material(_package(version, pins, R_STAR), _package(version, pins))


@pytest.mark.parametrize("component", ["manifest", "moltbot_safe"])
def test_p6_a_cp2_package_carrying_a_historical_component_pin_cannot_match_the_reexport(component):  # N1 / N2 at package level
    mixed = _package(CP2_VERSION, {**CP2_REVISIONS, component: P4_REVISIONS[component]})
    left, right = _normalized_replay_material(mixed, _package(CP2_VERSION, _selected_v2_pins(CP2_CP)))
    assert left != right


def _near_misses(sha):
    return [sha[:8], sha[:12], sha[:39], sha.upper(), " " + sha, sha + " ", sha + "\n", sha[:-1] + ("0" if sha[-1] != "0" else "1"),
            "0" * 40, "a" * 40, "latest", sha[:8] + "*", ""]


@pytest.mark.parametrize("near", _near_misses(CP2_CP))
def test_p7_no_near_miss_of_the_cp2_control_plane_is_a_known_generation(near):  # N8
    assert near not in ALL_V2_CONTROL_PLANE_REVISIONS and near not in SECURITY_RUNTIME_GENERATIONS
    assert accepted_replay_revisions(near) == frozenset()
    with pytest.raises(ExportError, match="unsupported Control Plane compatibility revision"):
        _selected_v2_pins(near)


@pytest.mark.parametrize("near", _near_misses(R_STAR))
def test_p7_no_near_miss_of_the_cp2_replay_is_accepted_as_installed_or_declared(near, monkeypatch):  # N8
    assert near not in all_accepted_replay_revisions()
    monkeypatch.setenv("ODES_ALLOW_UNVERIFIED_REPLAY", "0")
    monkeypatch.setattr(exporter, "installed_replay_revision", lambda: near)
    monkeypatch.setattr(exporter, "installed_replay_checkout_dirty", lambda: False)
    with pytest.raises((ReplayRevisionUnsupportedError, exporter.ReplayDependencyError)):
        exporter._require_installed_replay(CP2_CP)
    with pytest.raises(ValueError, match="exact qualified Replay revision"):
        _normalized_replay_material(_package(CP2_VERSION, CP2_REVISIONS, near), _package(CP2_VERSION, CP2_REVISIONS))


def _installed(monkeypatch, revision, dirty=False):
    monkeypatch.setenv("ODES_ALLOW_UNVERIFIED_REPLAY", "0")
    monkeypatch.setattr(exporter, "installed_replay_revision", lambda: revision)
    monkeypatch.setattr(exporter, "installed_replay_checkout_dirty", lambda: dirty)


def test_p8_the_installed_replay_gate_accepts_r_star_for_cp2_when_clean_and_refuses_dirty_or_undeterminable(monkeypatch):
    _installed(monkeypatch, R_STAR)
    exporter._require_installed_replay(CP2_CP)
    _installed(monkeypatch, R_STAR, dirty=True)
    with pytest.raises(ExportError, match="uncommitted"):
        exporter._require_installed_replay(CP2_CP)
    _installed(monkeypatch, None)
    with pytest.raises(exporter.ReplayDependencyError):
        exporter._require_installed_replay(CP2_CP)


@pytest.mark.parametrize("installed", [CUR_REPLAY, P2_REVISIONS["replay"], P4_REVISIONS["replay"], F5B_REVISIONS["replay"], SECURITY_REVISIONS["replay"],
                                       "d395e37c443fedf1bf6b9a4651338b7b7de4a553", "d9b7418051d2f5078a7a223a04c8d9d01bafd0c3"])
def test_p8_the_cp2_declaration_is_exact_no_other_installed_replay_passes_even_an_accepted_one(installed, monkeypatch):
    _installed(monkeypatch, installed)
    with pytest.raises(ReplayRevisionUnsupportedError, match="is not the Replay revision of the declared Control Plane generation"):
        exporter._require_installed_replay(CP2_CP)


@pytest.mark.parametrize("declared", [CUR_CP, P2_CP, P4_REVISIONS["control_plane"], F5B_REVISIONS["control_plane"], SECURITY_REVISIONS["control_plane"]])
def test_p8_decision_37_union_rule_is_unchanged_an_installed_cp2_replay_still_serves_cur_and_historical_declarations(declared, monkeypatch):
    # Characterization of the pre-existing union gate: older packages are re-validated by a newer accepted Replay. Not tightened here.
    _installed(monkeypatch, R_STAR)
    exporter._require_installed_replay(declared)
    _installed(monkeypatch, CUR_REPLAY)  # and the CUR Replay still serves CUR
    exporter._require_installed_replay(CUR_CP)


def test_p8_an_unaccepted_installed_replay_is_still_refused_for_a_cur_declaration(monkeypatch):
    _installed(monkeypatch, "0" * 40)
    with pytest.raises(ReplayRevisionUnsupportedError, match="is not an accepted Replay revision"):
        exporter._require_installed_replay(CUR_CP)


# ================================================================================================ fixtures, documentation and CI (no Replay needed)
def test_the_cp2_fixtures_match_their_provenance_digests_and_the_replay_provenance():
    provenance = json.loads((DATA / "PROVENANCE.json").read_text(encoding="utf-8"))
    replay_provenance = json.loads((DATA / "REPLAY_PROVENANCE.json").read_text(encoding="utf-8"))
    assert provenance["replay_pull_request_head"] == R_STAR and "PROVISIONAL" in provenance["note"]
    assert provenance["vendored_from"] == "cogno-us/cognous-replay-bundle tests/fixtures/strict_tenant_generation (PR #87)"
    assert replay_provenance["producer"]["control_plane"] == CP2_CP
    assert hashlib.sha256((DATA / "REPLAY_PROVENANCE.json").read_bytes()).hexdigest() == provenance["replay_provenance_sha256"]
    files = sorted(p.name for p in DATA.iterdir() if p.is_file() and p.name not in ("PROVENANCE.json", "REPLAY_PROVENANCE.json"))
    assert sorted(replay_provenance["sha256"]) == files == sorted(provenance["sha256"])
    for name, expected in replay_provenance["sha256"].items():
        assert hashlib.sha256((DATA / name).read_bytes()).hexdigest() == expected == provenance["sha256"][name], name
    vectors = json.loads((DATA / "vectors.json").read_text(encoding="utf-8"))
    assert vectors["strict"]["effect_id"] == STRICT_ID and vectors["legacy"]["effect_id"] == LEGACY_ID
    assert vectors["strict"]["generation"] == STRICT_MARKER and vectors["legacy"]["generation"] == LEGACY_MARKER


def test_the_cp2_records_are_the_real_strict_and_legacy_tenant_records():
    for kind, marker, eid in (("strict", STRICT_MARKER, STRICT_ID), ("legacy", LEGACY_MARKER, LEGACY_ID)):
        cp = json.loads((DATA / f"{kind}_control_plane_run.json").read_text(encoding="utf-8"))
        binding = cp["decisions"][0]["binding"]
        assert binding["generation"] == marker and binding["tenant_id"] == "tenant-alpha" and cp["decisions"][0]["effect_id"] == eid
        for section in ("attempts", "observations", "reconciliations"):
            assert cp[section] and {x["effect_id"] for x in cp[section]} == {eid}
        assert cp["resolution_checks"] and cp["check_events"]  # the resolution journal the security-runtime path needs
        proposal = json.loads((DATA / f"{kind}_proposal.json").read_text(encoding="utf-8"))
        assert proposal["tenant_id"] == "tenant-alpha" and proposal["manifest_digest"] == digest_of(json.loads((CUR_DATA / "manifest.json").read_text(encoding="utf-8")))


def test_the_documentation_states_the_pending_replay_repin_and_the_honest_limits():
    docs = (ROOT / "docs" / "capabilities-and-versions.md").read_text(encoding="utf-8")
    row = [line for line in docs.splitlines() if CP2_VERSION in line]
    assert len(row) == 1 and "484fdbd2" in row[0] and "d6c05bc5" in row[0] and "re-pinned to the Replay merge SHA" in row[0]
    assert "assigned under the Constitution at pin 1c2e920f, adoption not recorded" in row[0] and "UNQUALIFIED" in row[0] and "caller-asserted" in row[0]
    profiles = (ROOT / "docs" / "security-runtime-p4-p2-profiles.md").read_text(encoding="utf-8")
    assert CP2_VERSION in profiles and "caller-asserted" in profiles.split(CP2_VERSION)[1]
    contracts = (ROOT / "docs" / "engineering" / "ODES-INTERCOMPONENT-CONTRACTS.md").read_text(encoding="utf-8")
    entry = [line for line in contracts.splitlines() if line.startswith("50. DECIDED") and CP2_VERSION in line]
    assert len(entry) == 1 and "not a third in-place re-tie" in entry[0] and "decision authority reference not supplied" in entry[0]


def test_p10_the_ci_job_fetches_the_pinned_replay_and_forbids_skipping():
    text = (ROOT / ".github" / "workflows" / "cp2-generation-e2e.yml").read_text(encoding="utf-8")
    assert "name: CP-2 generation tests against pinned Replay" in text
    assert "from odes.common import CP2_REPLAY_REVISION" in text  # the revision comes from the one constant, never a second literal
    assert 'test "$(git -C "$RUNNER_TEMP/replay" rev-parse HEAD)" = "$REV"' in text  # fetched HEAD must equal the pin
    assert "ODES_REQUIRE_CP2_E2E: '1'" in text and "ODES_TEST_REPLAY_REPO: ${{ runner.temp }}/replay" in text
    assert "python -m pytest -q tests/test_cp2_generation.py" in text
    assert re.search(r"^    timeout-minutes: \d+$", text, re.M)  # a bounded job
    assert not re.search(r"\b[0-9a-f]{40}\b", text.split("Fetch Replay")[1].split("python -m pytest")[0])  # no hard-coded SHA in the fetch step
    cur = (ROOT / ".github" / "workflows" / "current-generation-e2e.yml").read_text(encoding="utf-8")
    assert "CUR_REPLAY_REVISION" in cur and "CP2_REPLAY_REVISION" not in cur  # the CUR job is untouched and keeps its own pin


def test_p11_the_require_flag_turns_an_unavailable_replay_into_a_failure_not_a_skip():
    """With ODES_REQUIRE_CP2_E2E=1 and no usable Replay the end-to-end tests FAIL (CI cannot go green by skipping); without it they skip."""
    if os.environ.get("ODES_NESTED_GUARD_CHECK"):
        pytest.skip("nested run")
    target = f"{Path(__file__).as_posix()}::test_real_cp2_record_without_executor_export_exports_as_partial"

    def nested(require):
        env = {**os.environ, "ODES_NESTED_GUARD_CHECK": "1", "ODES_TEST_REPLAY_REPO": str(ROOT / "no-such-replay-repository"), "PYTHONDONTWRITEBYTECODE": "1"}
        env.pop("ODES_REQUIRE_CP2_E2E", None)
        if require:
            env["ODES_REQUIRE_CP2_E2E"] = "1"
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", target], capture_output=True, text=True, env=env, cwd=ROOT, timeout=300)
    strict, lax = nested(True), nested(False)
    assert strict.returncode != 0 and "ODES_REQUIRE_CP2_E2E=1 but the end-to-end Replay could not be set up" in strict.stdout and "skipped" not in strict.stdout
    assert lax.returncode == 0 and "1 skipped" in lax.stdout


# ================================================================================================ end to end with the real Replay at exactly R*
def _scratch_replay(tmp_path_factory):
    repo = os.environ.get("ODES_TEST_REPLAY_REPO")
    if not repo or not (Path(repo) / ".git").exists():
        return None
    scratch = tmp_path_factory.mktemp("replay-at-pin") / "replay"
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        subprocess.run(["git", "clone", "-q", "--no-checkout", str(repo), str(scratch)], check=True, capture_output=True, env=env, timeout=300)
        subprocess.run(["git", "-C", str(scratch), "checkout", "-q", "--detach", CP2_REPLAY_REVISION], check=True, capture_output=True, env=env, timeout=300)
        head = subprocess.run(["git", "-C", str(scratch), "rev-parse", "HEAD"], check=True, capture_output=True, text=True, env=env).stdout.strip()
    except Exception:
        return None
    return scratch if head == CP2_REPLAY_REVISION else None


@pytest.fixture(scope="module")
def replay(tmp_path_factory):
    """A clean scratch clone of the Replay repository at exactly CP2_REPLAY_REVISION, importable for this module only."""
    scratch = _scratch_replay(tmp_path_factory)
    if scratch is None:
        msg = "needs ODES_TEST_REPLAY_REPO naming a git repository that contains the pinned CP-2 Replay revision"
        if os.environ.get("ODES_REQUIRE_CP2_E2E") == "1":
            pytest.fail("ODES_REQUIRE_CP2_E2E=1 but the end-to-end Replay could not be set up at CP2_REPLAY_REVISION: " + msg)
        pytest.skip(msg)
    saved_path = list(sys.path)
    saved_modules = {k: v for k, v in sys.modules.items() if k.split(".")[0] == "agent_replay_bundle"}
    for k in saved_modules:
        del sys.modules[k]
    saved_env = {k: os.environ.get(k) for k in ("ODES_ALLOW_UNVERIFIED_REPLAY", "PYTHONDONTWRITEBYTECODE")}
    os.environ["ODES_ALLOW_UNVERIFIED_REPLAY"] = "0"  # the real gate: installed HEAD must be an accepted revision and clean
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


MANIFEST = json.loads((CUR_DATA / "manifest.json").read_text(encoding="utf-8"))
POLICY_BASE = {"now": "2026-10-06T00:00:00Z", "purpose": "audit", "relying_party": "recipient.example.org", "status_inputs": {},
               "trusted_digests": [], "trusted_key_refs": [], "evaluation_scope": "audit", "status_max_age_seconds": 300,
               "allow_unauthenticated_informational_inspection": False}


def load_cur(name="valid"):
    return tuple(json.loads((CUR_DATA / name / f).read_text(encoding="utf-8")) for f in ("control_plane_run.json", "proposal.json", "runtime_export.json"))


def load_tenant(kind):
    return (json.loads((DATA / f"{kind}_control_plane_run.json").read_text(encoding="utf-8")),
            json.loads((DATA / f"{kind}_proposal.json").read_text(encoding="utf-8")))


def cur_bundle(replay, name="valid", *, executor=True, label=CP2_CP):
    """A CUR-captured record presented under ``label`` (default: the CP-2 label). The label is caller-asserted."""
    cp, proposal, runtime = load_cur(name)
    return replay.import_bounded_workflow(cp, proposal=proposal, moltbot_export=runtime if executor else None,
                                          control_plane_revision=label).model_dump(mode="json")


def tenant_bundle(replay, kind="strict", *, label=CP2_CP, cp=None):
    base, proposal = load_tenant(kind)
    return replay.import_bounded_workflow(copy.deepcopy(base if cp is None else cp), proposal=proposal, moltbot_export=None,
                                          control_plane_revision=label).model_dump(mode="json")


def policy_for(package):
    return {**POLICY_BASE, "supported_profiles": [package["profile"]["implementation_profile"]]}


def seal(package):
    """Recompute the package digest after a deliberate tamper so the generation gates, not the digest, are what refuse it."""
    package["package_digest"] = digest_of({k: package[k] for k in ("record", "profile", "integrity", "provenance")})
    return package


def export(bundle):
    return exporter.export_cognous_stack_package(MANIFEST, bundle)


def _assert_cp2_stamps(package, *, status):
    assert package["profile"]["implementation_profile_version"] == CP2_VERSION
    prov = package["provenance"]
    assert prov["pinned_revisions"] == CP2_REVISIONS == prov["selected_revisions"]
    assert prov["replay_validation"]["required_revision"] == R_STAR and prov["replay_validation"]["status"] == status
    assert prov["supported_revisions"]["control_plane"] == [CP2_CP]
    meta = prov["retained_sources"]["reconstruction_bundle"]["metadata"]
    assert meta["control_plane_revision"] == CP2_CP  # the retained label is the one the records were imported under (a constants-only change fails here)
    assert meta["manifest_revision"] == CP2_MANIFEST
    profiles = {r["producer_profile_id"] for r in prov["retained_sources"]["reconstruction_bundle"]["records"]}
    assert CP2_PROFILE_ID in profiles and profiles <= {CP2_PROFILE_ID, "moltbot-safe-executor-producer-2.0.0@f7a55e2a"}  # the CP-2 generation id, plus the unchanged CUR runtime profile when an executor export is present


def _recipient_pass(package):
    result = evaluate_recipient_package(package, policy_for(package))
    assert result["replay_semantic_consistency"]["status"] == "pass"
    assert result["declared_profile_conformance"]["status"] == "pass"
    assert result["package_content_integrity"]["status"] == "pass"
    assert result["schema_validity"]["status"] == "pass"
    assert result["recipient_reliance_decision"]["status"] == "fail"  # no authority/freshness inputs: never reliance
    return result


def test_the_real_replay_in_use_is_exactly_r_star_and_clean(replay):
    from odes.common import installed_replay_checkout_dirty, installed_replay_revision
    assert installed_replay_revision() == R_STAR
    assert installed_replay_checkout_dirty() is False
    exporter._require_installed_replay(CP2_CP)


# ------------------------------------------------------------------------------------------------ E1/E4: real CP 484fdbd2 strict-tenant and legacy-tenant records
@pytest.mark.parametrize("kind,marker,eid", [("strict", STRICT_MARKER, STRICT_ID), ("legacy", LEGACY_MARKER, LEGACY_ID)])
def test_real_cp2_tenant_records_pass_the_security_runtime_path_with_effect_identity_retained_verbatim(replay, kind, marker, eid):
    cp, _ = load_tenant(kind)
    assert cp["decisions"][0]["binding"]["generation"] == marker and cp["decisions"][0]["effect_id"] == eid
    package = export(tenant_bundle(replay, kind))
    _assert_cp2_stamps(package, status="reconstruction_partial")  # executor-less by necessity: no tenant-aware executor export exists
    prov = package["provenance"]
    records = prov["retained_sources"]["reconstruction_bundle"]["records"]
    kinds = {"runtime_decision": 1, "control_plane_attempt_transition": 2, "effect_observation": 2, "reconciliation": 2}
    for record_type, count in kinds.items():
        assert [r["data"]["effect_id"] for r in records if r["record_type"] == record_type] == [eid] * count
    assert list(prov["execution_facts"]["effect_observation_history"]) == [eid]  # the package's own effect view is keyed by the unchanged source identity
    assert [r["data"] for r in records if r["record_type"] == "runtime_decision"] == [cp["decisions"][0]]  # decision (incl. tenant binding) retained as written
    facts = prov["execution_facts"]
    count = lambda v: len(v) if isinstance(v, list) else v  # noqa: E731  (the package reports some of these as lists, some as counts)
    assert count(facts["control_plane_attempt_transitions"]) == len(cp["attempts"]) == 2
    assert count(facts["accepted_control_plane_observations"]) == len(cp["observations"]) and count(facts["reconciliations"]) == len(cp["reconciliations"])
    assert count(facts["resolution_check"]) == len(cp["resolution_checks"]) and count(facts["resolution_check_event"]) == len(cp["check_events"])
    _recipient_pass(package)


def test_strict_and_legacy_identities_are_not_interchangeable_in_the_exported_packages(replay):
    strict = export(tenant_bundle(replay, "strict"))
    legacy = export(tenant_bundle(replay, "legacy"))
    assert STRICT_ID in json.dumps(strict) and LEGACY_ID not in json.dumps(strict)
    assert LEGACY_ID in json.dumps(legacy) and STRICT_ID not in json.dumps(legacy)
    assert strict["package_digest"] != legacy["package_digest"]


def _runtime_decision(bundle):
    return next(r for r in bundle["records"] if r["record_type"] == "runtime_decision")["data"]


@pytest.mark.parametrize("mutate,match", [
    (lambda d: d.update(effect_id=LEGACY_ID), "journal decision/effect lineage mismatch|invalid effect identity"),
    (lambda d: d["binding"].update(generation=LEGACY_MARKER), "invalid effect identity"),
    (lambda d: d["binding"].pop("generation"), "binding.generation is required on a tenant-aware binding"),
    (lambda d: d["binding"].update(generation="bounded-authorization-effect/0.4-unknown"), "not a supported tenant-binding generation"),
    (lambda d: d["binding"].update(tenant_generation=LEGACY_MARKER), "conflicts with binding.generation"),
], ids=["legacy-id-on-strict", "marker-downgraded", "marker-missing", "marker-unknown", "marker-conflicting"])
def test_a_strict_record_with_a_wrong_missing_or_conflicting_generation_is_refused_at_export_and_no_package_exists(replay, mutate, match):
    bundle = tenant_bundle(replay, "strict")
    mutate(_runtime_decision(bundle))
    with pytest.raises(ExportError, match="pinned Replay semantic validation failed: .*(" + match + ")"):
        export(bundle)


@pytest.mark.parametrize("section", ["control_plane_attempt_transition", "effect_observation", "reconciliation"])
def test_a_recovery_or_redelivered_row_that_swaps_in_the_legacy_identity_is_refused_at_export(replay, section):
    bundle = tenant_bundle(replay, "strict")
    row = [r for r in bundle["records"] if r["record_type"] == section][-1]
    row["data"]["effect_id"] = LEGACY_ID
    with pytest.raises(ExportError, match="pinned Replay semantic validation failed|differs from accepted validator"):
        export(bundle)


def test_replay_refuses_strict_records_mutated_at_source_so_no_bundle_reaches_odes(replay):
    cp, proposal = load_tenant("strict")
    for edit in (lambda c: c["decisions"][0].update(effect_id=LEGACY_ID), lambda c: c["decisions"][0]["binding"].pop("generation"),
                 lambda c: c["attempts"][-1].update(effect_id=LEGACY_ID)):
        mutated = copy.deepcopy(cp)
        edit(mutated)
        with pytest.raises(replay.ImportContractError):
            replay.import_bounded_workflow(mutated, proposal=copy.deepcopy(proposal), control_plane_revision=CP2_CP)


@pytest.mark.parametrize("kind", ["strict", "legacy"])
def test_a_resealed_tampered_strict_package_does_not_validate(replay, kind):
    package = export(tenant_bundle(replay, kind))
    for r in package["provenance"]["retained_sources"]["reconstruction_bundle"]["records"]:
        if r["record_type"] == "runtime_decision":
            r["data"]["effect_id"] = LEGACY_ID if kind == "strict" else STRICT_ID
    result = evaluate_recipient_package(seal(package), policy_for(package))
    assert result["replay_semantic_consistency"]["status"] != "pass" and result["recipient_reliance_decision"]["status"] != "pass"


# ------------------------------------------------------------------------------------------------ E1/E2: executor scenarios (CUR-captured records under a CALLER-ASSERTED CP-2 label)
@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_cur_captured_scenarios_under_the_cp2_label_export_with_cp2_stamps_and_recipient_validate(replay, name):
    status, reasons = SCENARIOS[name]
    cp, proposal, runtime = load_cur(name)
    assert runtime["repository"]["revision"] == CP2_RT and runtime["execution_result"]["status"] == status
    package = export(cur_bundle(replay, name))
    _assert_cp2_stamps(package, status="reconstruction_complete")
    prov = package["provenance"]
    assert prov["retained_sources"]["manifest"] == MANIFEST
    meta = prov["retained_sources"]["reconstruction_bundle"]["metadata"]
    assert (meta["control_plane_revision"], meta["moltbot_safe_revision"], meta["manifest_revision"]) == (CP2_CP, CP2_RT, CP2_MANIFEST)
    assert meta["moltbot_producer_contract"]["compatible_control_plane_revisions"] == [CP2_CP]  # Replay's CP-2-only list, not the CUR one
    facts = prov["execution_facts"]
    assert [r["status"] for r in facts["execution_results"]] == [status]
    assert facts["control_plane_evidence"] == [runtime["control_plane_evidence"]]
    assert len(facts["control_plane_attempt_transitions"]) == len(cp["attempts"])
    assert prov["decision_facts"]["proposal_commitment"] == cp["decisions"][0]["binding"]["proposal_commitment"]
    if reasons is not None:  # denied
        assert facts["control_plane_evidence"][0]["refusal"]["reasons"] == reasons and facts["execution_results"][0]["attempted"] is False
        assert [r["reasons"] for r in cp["refusals"]] == [reasons]
    _recipient_pass(package)


def test_real_cp2_record_without_executor_export_exports_as_partial(replay):
    package = export(tenant_bundle(replay, "strict"))
    assert package["provenance"]["replay_validation"]["status"] == "reconstruction_partial"
    assert package["provenance"]["pinned_revisions"] == CP2_REVISIONS
    assert evaluate_recipient_package(package, policy_for(package))["replay_semantic_consistency"]["status"] == "pass"
    cur_without_executor = export(cur_bundle(replay, executor=False))  # the CUR-captured record, executor-less, under the CP-2 label
    assert cur_without_executor["provenance"]["replay_validation"]["status"] == "reconstruction_partial"
    assert cur_without_executor["provenance"]["pinned_revisions"] == CP2_REVISIONS


def test_explicit_restriction_semantics_also_export_under_the_cp2_generation(replay):
    package = exporter.export_cognous_stack_package(MANIFEST, cur_bundle(replay), restriction_semantics="explicit")
    assert package["profile"]["implementation_profile_version"].startswith(CP2_VERSION)
    assert evaluate_recipient_package(package, policy_for(package))["replay_semantic_consistency"]["status"] == "pass"


# ------------------------------------------------------------------------------------------------ unsupported / mislabelled revisions are refused
@pytest.mark.parametrize("near", [n for n in _near_misses(CP2_CP) if n != ""])
def test_p9_a_bundle_labelled_with_a_near_miss_of_the_cp2_control_plane_is_refused_at_export(replay, near):
    bundle = tenant_bundle(replay, "strict")
    bundle["metadata"]["control_plane_revision"] = near
    with pytest.raises(ExportError, match="unsupported Control Plane compatibility revision"):
        export(bundle)


def test_p9_a_bundle_without_a_control_plane_revision_is_refused(replay):  # N11
    bundle = tenant_bundle(replay, "strict")
    del bundle["metadata"]["control_plane_revision"]
    with pytest.raises(ExportError, match="control_plane_revision"):
        export(bundle)


def test_replay_refuses_cp2_records_under_a_lock_unknown_or_near_miss_label_so_no_bundle_reaches_odes(replay):
    cp, proposal = load_tenant("strict")
    for label in ("0a41faa9ac05ab7a4f8d17a1b3e4e2bf36e99d50", CP2_CP[:8], CP2_CP.upper(), CP2_CP + "0", "latest", ""):
        with pytest.raises(replay.ImportContractError):
            replay.import_bounded_workflow(copy.deepcopy(cp), proposal=proposal, control_plane_revision=label)


def test_replay_refuses_the_cp2_label_with_a_historical_runtime_export(replay):
    cp, proposal, runtime = load_cur()
    historical = copy.deepcopy(runtime)
    historical["repository"]["revision"] = P2_RT
    historical["provenance"]["source_asserted"]["repository_revision"] = P2_RT
    with pytest.raises(replay.ImportContractError, match="combination"):
        replay.import_bounded_workflow(copy.deepcopy(cp), proposal=proposal, moltbot_export=historical, control_plane_revision=CP2_CP)


OTHER_CPS = [CUR_CP, P2_CP, P4_REVISIONS["control_plane"], F5B_REVISIONS["control_plane"], SECURITY_REVISIONS["control_plane"]]


@pytest.mark.parametrize("label_cp", OTHER_CPS)
@pytest.mark.parametrize("source", ["tenant", "cur_captured"])
def test_a_cp2_bundle_relabelled_to_another_generation_is_refused_at_export(replay, source, label_cp):  # N1
    bundle = tenant_bundle(replay, "strict") if source == "tenant" else cur_bundle(replay)
    bundle["metadata"]["control_plane_revision"] = label_cp
    with pytest.raises(ExportError, match="pinned Replay semantic validation failed|differs from accepted validator|unsupported Control Plane"):
        export(bundle)


@pytest.mark.parametrize("label_rt", [P2_RT, P4_REVISIONS["moltbot_safe"], SECURITY_REVISIONS["moltbot_safe"]])
def test_a_cp2_bundle_whose_runtime_label_is_a_historical_runtime_is_refused_at_export(replay, label_rt):  # N2
    bundle = cur_bundle(replay)
    bundle["metadata"]["moltbot_safe_revision"] = label_rt
    with pytest.raises(ExportError, match="pinned Replay semantic validation failed|differs from accepted validator"):
        export(bundle)


@pytest.mark.parametrize("field,value", [("manifest_revision", P4_REVISIONS["manifest"]), ("manifest_revision", "0" * 40), ("manifest_revision", None), ("manifest_revision", ""),
                                         ("moltbot_safe_revision", P2_RT), ("moltbot_safe_revision", CP2_RT[:8]), ("moltbot_safe_revision", None)])
def test_a_tampered_runtime_or_manifest_label_is_refused_at_export(replay, field, value):
    bundle = cur_bundle(replay)
    bundle["metadata"][field] = value
    with pytest.raises(ExportError, match="differs from accepted validator|pinned Replay semantic validation failed"):
        export(bundle)


@pytest.mark.parametrize("edit", [
    lambda p: p["provenance"]["pinned_revisions"].update(control_plane=CUR_CP),
    lambda p: p["provenance"]["selected_revisions"].update(control_plane=CUR_CP),
    lambda p: p["provenance"]["pinned_revisions"].update(replay=CUR_REPLAY),
    lambda p: p["provenance"]["pinned_revisions"].update(replay=P2_REVISIONS["replay"]),
    lambda p: p["provenance"]["pinned_revisions"].update(moltbot_safe=P2_RT),
    lambda p: p["provenance"]["pinned_revisions"].update(manifest=P4_REVISIONS["manifest"]),
    lambda p: p["provenance"]["pinned_revisions"].update(replay=R_STAR[:8]),
    lambda p: p["provenance"]["replay_validation"].update(required_revision=CUR_REPLAY),
    lambda p: p["profile"].update(implementation_profile_version=CUR_PROFILE_VERSION),
    lambda p: p["profile"].update(implementation_profile_version=CP2_VERSION + "x"),
    lambda p: p["profile"].update(implementation_profile=PROFILE_ID),
], ids=["cp-pin-cur", "cp-selected-cur", "replay-pin-cur", "replay-pin-p2", "runtime-pin-p2", "manifest-pin-p4", "replay-pin-short", "required-replay-cur",
        "profile-version-cur", "profile-version-suffix", "profile-id-0.1"])
def test_a_resealed_tampered_cp2_package_does_not_validate(replay, edit):
    package = export(cur_bundle(replay))
    edit(package)
    result = evaluate_recipient_package(seal(package), policy_for(package))
    assert result["replay_semantic_consistency"]["status"] != "pass"
    assert result["recipient_reliance_decision"]["status"] != "pass"


def test_a_cp2_package_does_not_validate_when_its_retained_label_is_edited_to_cur(replay):
    package = export(tenant_bundle(replay, "strict"))
    package["provenance"]["retained_sources"]["reconstruction_bundle"]["metadata"]["control_plane_revision"] = CUR_CP
    result = evaluate_recipient_package(seal(package), policy_for(package))
    assert result["replay_semantic_consistency"]["status"] != "pass"


# ------------------------------------------------------------------------------------------------ the installed Replay gate in the real export path
def test_the_export_refuses_a_cp2_declaration_when_the_installed_replay_is_the_cur_replay(replay, monkeypatch):
    bundle = tenant_bundle(replay, "strict")
    _installed(monkeypatch, CUR_REPLAY)
    with pytest.raises(ReplayRevisionUnsupportedError, match="is not the Replay revision of the declared Control Plane generation"):
        export(bundle)


def test_the_export_refuses_a_cp2_declaration_when_the_installed_replay_is_p2(replay, monkeypatch):
    bundle = cur_bundle(replay)
    _installed(monkeypatch, P2_REVISIONS["replay"])
    with pytest.raises(ReplayRevisionUnsupportedError, match="is not the Replay revision of the declared Control Plane generation"):
        export(bundle)


# ------------------------------------------------------------------------------------------------ explicit unsupported scope stays refused under the CP-2 label
def _authority(cp):
    return [d["binding"]["runtime_authority"] for d in cp["decisions"] if d.get("binding")]


def test_effective_configuration_is_refused_under_the_cp2_label(replay):
    cp, proposal, runtime = load_cur()
    for a in _authority(cp):
        a["effective_configuration"] = copy.deepcopy(EFFECTIVE_CONFIGURATION)
    with pytest.raises(replay.ImportContractError, match="runtime authority fields unsupported"):
        replay.import_bounded_workflow(copy.deepcopy(cp), proposal=proposal, moltbot_export=copy.deepcopy(runtime), control_plane_revision=CP2_CP)
    bundle = cur_bundle(replay)
    for r in bundle["records"]:
        if r["record_type"] == "runtime_decision":
            r["data"]["binding"]["runtime_authority"]["effective_configuration"] = copy.deepcopy(EFFECTIVE_CONFIGURATION)
    with pytest.raises(ExportError, match="pinned Replay semantic validation failed"):
        export(bundle)


@pytest.mark.parametrize("members", [{"approval_commitment_version": POLICY_BINDING["approval_commitment_version"]}, {"policy_generation": 1},
                                     {"policy_activation_ref": POLICY_BINDING["policy_activation_ref"]}, POLICY_BINDING])
def test_policy_binding_members_are_refused_under_the_cp2_label(replay, members):
    cp, proposal, runtime = load_cur()
    for a in _authority(cp):
        a.update(members)
    with pytest.raises(replay.ImportContractError, match="runtime authority fields unsupported"):
        replay.import_bounded_workflow(copy.deepcopy(cp), proposal=proposal, moltbot_export=copy.deepcopy(runtime), control_plane_revision=CP2_CP)
    bundle = cur_bundle(replay)
    for r in bundle["records"]:
        if r["record_type"] == "runtime_decision":
            r["data"]["binding"]["runtime_authority"].update(copy.deepcopy(members))
    with pytest.raises(ExportError, match="pinned Replay semantic validation failed"):
        export(bundle)


def test_reason_vocabulary_0_3_is_refused_under_the_cp2_label(replay):
    cp, proposal, runtime = load_cur("revoked")
    for holder in (cp["refusals"][0], runtime["control_plane_evidence"]["refusal"]):
        holder["reason_vocabulary_version"] = LABEL_03
    with pytest.raises(replay.ImportContractError):
        replay.import_bounded_workflow(copy.deepcopy(cp), proposal=proposal, moltbot_export=copy.deepcopy(runtime), control_plane_revision=CP2_CP)
    bundle = cur_bundle(replay, "revoked")
    for r in bundle["records"]:
        if r["record_type"] == "runtime_decision":
            r["data"]["reason_vocabulary_version"] = LABEL_03
    with pytest.raises(ExportError, match="pinned Replay semantic validation failed"):
        export(bundle)


@pytest.mark.parametrize("member", ["selection_refusal", "authorization_pin"])
def test_selection_refusal_and_authorization_pin_evidence_are_refused_under_the_cp2_label(replay, member):
    cp, proposal, runtime = load_cur("revoked")
    runtime["control_plane_evidence"][member] = {"version": "0.1"}
    runtime["execution_result"]["control_plane_evidence"][member] = {"version": "0.1"}
    with pytest.raises(replay.ImportContractError):
        replay.import_bounded_workflow(copy.deepcopy(cp), proposal=proposal, moltbot_export=copy.deepcopy(runtime), control_plane_revision=CP2_CP)
    bundle = cur_bundle(replay, "revoked")
    for r in bundle["records"]:
        if r["record_type"] == "executor_control_plane_evidence":
            r["data"][member] = {"version": "0.1"}
    with pytest.raises(ExportError, match="pinned Replay semantic validation failed"):
        export(bundle)


@pytest.mark.parametrize("profile", [GOVERNED_SELECTOR, "registry-authenticated-selection/0.1", "anything"])
def test_registry_profile_selectors_are_refused_by_replay_for_the_cp2_label(replay, profile):
    cp, proposal = load_tenant("strict")
    with pytest.raises(replay.ImportContractError, match="unsupported Control Plane profile selector"):
        replay.import_bounded_workflow(copy.deepcopy(cp), proposal=proposal, control_plane_revision=CP2_CP, control_plane_profile=profile)


@pytest.mark.parametrize("keys", [{"control_plane_profile": GOVERNED_SELECTOR}, {"effective_configuration_verification": "internal_consistency_only_registry_source_revision_unverified"}])
def test_a_plain_cp2_bundle_carrying_governed_metadata_labels_is_refused_at_export(replay, keys):
    bundle = cur_bundle(replay)
    bundle["metadata"].update(keys)
    with pytest.raises(ExportError, match="retained Replay (control_plane_profile|effective_configuration_verification|metadata keys) differ"):
        export(bundle)


def test_an_unsupported_member_injected_into_an_exported_cp2_package_does_not_validate(replay):
    package = export(cur_bundle(replay))
    for r in package["provenance"]["retained_sources"]["reconstruction_bundle"]["records"]:
        if r["record_type"] == "runtime_decision":
            r["data"]["binding"]["runtime_authority"]["effective_configuration"] = copy.deepcopy(EFFECTIVE_CONFIGURATION)
    result = evaluate_recipient_package(seal(package), policy_for(package))
    assert result["replay_semantic_consistency"]["status"] != "pass" and result["recipient_reliance_decision"]["status"] != "pass"


# ------------------------------------------------------------------------------------------------ E8: the retained bundle envelope is an exact allowlist for CP-2 too
@pytest.mark.parametrize("executor", [True, False])
@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_every_genuine_cp2_bundle_has_exactly_the_allowlisted_key_sets_and_still_exports(replay, name, executor):
    bundle = cur_bundle(replay, name, executor=executor)
    assert set(bundle) == exporter.CUR_BUNDLE_TOP_LEVEL_KEYS and set(bundle["metadata"]) == exporter.CUR_BUNDLE_METADATA_KEYS
    assert bundle["metadata"]["executor_failure_reference_verification"] == "source_asserted_not_independently_verified"
    assert (bundle["metadata"]["moltbot_safe_revision"] is None) is (not executor)
    package = export(bundle)
    assert package["provenance"]["retained_sources"]["reconstruction_bundle"]["metadata"] == bundle["metadata"]


@pytest.mark.parametrize("kind", ["strict", "legacy"])
def test_the_genuine_cp2_tenant_bundles_have_the_allowlisted_key_sets(replay, kind):
    bundle = tenant_bundle(replay, kind)
    assert set(bundle) == exporter.CUR_BUNDLE_TOP_LEVEL_KEYS and set(bundle["metadata"]) == exporter.CUR_BUNDLE_METADATA_KEYS


@pytest.mark.parametrize("source", ["tenant", "cur_captured"])
def test_a_cp2_bundle_with_an_extra_top_level_or_metadata_key_is_refused_by_the_envelope_check(replay, source):
    for place, key in (("top", "authority_claim"), ("metadata", "authority_claim"), ("metadata", "control_plane_profile"), ("metadata", "tenant_id")):
        bundle = tenant_bundle(replay, "strict") if source == "tenant" else cur_bundle(replay)
        (bundle if place == "top" else bundle["metadata"])[key] = "x" if key != "control_plane_profile" else None
        with pytest.raises(ExportError, match="retained Replay (bundle keys|metadata keys|control_plane_profile)"):
            export(bundle)


@pytest.mark.parametrize("key", ["effect_observation_history", "control_plane_revision", "moltbot_safe_revision", "moltbot_producer_contract",
                                 "manifest_revision", "executor_failure_reference_verification", "alvorada_revision"])
def test_dropping_any_genuine_metadata_key_of_a_cp2_bundle_is_refused(replay, key):
    bundle = cur_bundle(replay)
    del bundle["metadata"][key]
    with pytest.raises(ExportError, match="retained Replay|differs from accepted validator|pinned Replay semantic validation failed|control_plane_revision"):
        export(bundle)


def test_a_stronger_executor_failure_reference_verification_label_is_refused_for_cp2(replay):
    bundle = cur_bundle(replay)
    bundle["metadata"]["executor_failure_reference_verification"] = "independently_verified_authoritative"
    with pytest.raises(ExportError, match="retained Replay metadata differs from accepted validator"):
        export(bundle)


def test_the_envelope_allowlist_is_entered_for_cur_and_cp2_only():
    import inspect
    source = inspect.getsource(exporter._run_replay_validation)
    assert source.count("_require_exact_current_bundle_envelope") == 1  # the CUR call site is textually unchanged
    assert 'if revision == CUR_REVISIONS["control_plane"]:\n                _require_exact_current_bundle_envelope' in source
    assert 'elif revision == CP2_REVISIONS["control_plane"]:\n                _require_exact_cp2_bundle_envelope' in source


# ------------------------------------------------------------------------------------------------ E7: the stamp follows the DECLARED label (caller-asserted), never the record or the executing Replay
def test_cur_label_through_the_cp2_replay_still_exports_under_the_cur_profile_not_cp2(replay):
    # The installed Replay is R* (CP-2). A CUR-labelled bundle is validated by it (decision 37 union gate, characterization) and keeps the CUR stamps.
    package = export(cur_bundle(replay, label=CUR_CP))
    assert package["profile"]["implementation_profile_version"] == CUR_PROFILE_VERSION
    assert package["provenance"]["pinned_revisions"] == CUR_REVISIONS and package["provenance"]["pinned_revisions"]["replay"] == CUR_REPLAY
    assert package["provenance"]["replay_validation"]["required_revision"] == CUR_REPLAY  # stamped from the declared label, not from the executing Replay
    assert package["provenance"]["supported_revisions"]["control_plane"] == [CUR_CP]


def test_p2_label_through_the_cp2_replay_still_exports_under_the_p2_profile(replay):
    cp, proposal, _ = load_cur()
    bundle = replay.import_bounded_workflow(cp, proposal=proposal, control_plane_revision=P2_CP).model_dump(mode="json")
    package = export(bundle)
    assert package["profile"]["implementation_profile_version"] == P2_PROFILE_VERSION and package["provenance"]["pinned_revisions"] == P2_REVISIONS


@pytest.mark.parametrize("label,version,pins", [(CUR_CP, CUR_PROFILE_VERSION, CUR_REVISIONS), (P2_CP, P2_PROFILE_VERSION, P2_REVISIONS)])
def test_provenance_labels_are_caller_asserted_a_strict_tenant_record_imported_under_another_label_exports_under_that_label(replay, label, version, pins):
    """LIMIT, pinned honestly: nothing measures a record against a Control Plane checkout and no relabel is detected. A real CP 484fdbd2 strict-tenant record that the CALLER
    declares as CUR or P2 is accepted by Replay under that label and exported under that generation's profile. What the CP-2 generation provides is that a record CAN now
    carry its true label end to end; it does not stop a record from being mislabelled before it enters Replay. (A bundle already built under the CP-2 label and then edited
    to another label IS refused: see the relabel tests above.)"""
    cp, proposal = load_tenant("strict")
    bundle = replay.import_bounded_workflow(copy.deepcopy(cp), proposal=proposal, control_plane_revision=label).model_dump(mode="json")
    package = export(bundle)
    assert package["profile"]["implementation_profile_version"] == version and package["provenance"]["pinned_revisions"] == pins
    assert package["provenance"]["pinned_revisions"]["control_plane"] != CP2_CP
