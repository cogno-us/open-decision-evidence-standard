"""Opt-in lifecycle development profile ``odes_cognous_stack_export_0_2_restrictions_lifecycle_0_1`` (S1P): focused tests.

DEVELOPMENT ONLY, PROPOSED, UNQUALIFIED, NOT ADOPTED. All keys, policies, identities and fixture values are SYNTHETIC / NONPRODUCTION.
A native pass here is developer evidence on synthetic inputs only; it is not independent qualification, not real recipient trust and
not evidence about any production issuer. The lifecycle value is an attributed issuer assertion, not recipient status evidence.

Architect-selected checks (S1P authorization): OP1 (opt-in synthetic native pass, evaluator NOT stubbed), N1 (missing restriction metadata
stays restrictive), N3 (record-side unknown/stale/expired/pending freshness refuses even with favorable recipient inputs; malformed,
unsupported or unattributed lifecycle inputs are rejected), N4 (post-commitment mutation of risk metadata breaks Replay reconstruction;
altering or resealing lifecycle attribution mismatches or is rejected), and compatibility (default/restrictions exports carry no lifecycle
members; the existing byte/digest identity tests are run unchanged).

End-to-end tests need the pinned Replay: ODES_TEST_REPLAY_REPO names a git repository containing the CP-2 Replay revision (the same
mechanism as tests/test_cp2_generation.py). ODES_REQUIRE_LIFECYCLE_E2E=1 turns that skip into a failure. They need ``cryptography``.
The synthetic fixtures were generated with the real pinned Control Plane, never edited (tests/data/lifecycle_generation/GENERATION.md).
"""
from __future__ import annotations

import base64
import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from odes import exporter, recipient_validator as rv
from odes.common import (
    CP2_REPLAY_REVISION,
    CP2_REVISIONS,
    LIFECYCLE_ISSUER_ASSERTED_LIMIT,
    PROFILE_V2_ID,
    PROFILE_V2_LIFECYCLE_ID,
    PROFILE_V2_RESTRICTIONS_ID,
    parse_instant,
    sha256 as digest_of,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "data"
LIFE = DATA / "lifecycle_generation"
CP2_DATA = DATA / "cp2_generation"
CP2_CP = CP2_REVISIONS["control_plane"]
MANIFEST = json.loads((DATA / "current_generation" / "manifest.json").read_text(encoding="utf-8"))
SYNTH_JURISDICTION = "SYNTHETIC-JURISDICTION-NONPRODUCTION"
SEED = bytes(range(32))  # SYNTHETIC / NONPRODUCTION test key material only
NOW = "2026-10-06T00:00:00Z"
EVALUATED_AT = "2026-10-05T23:59:00Z"
ISSUER = {"organization_id": "cognous.synthetic.baseline", "system_id": "cognous-stack-exporter"}


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
    """A clean scratch clone of Replay at exactly the CP-2 revision, importable for this module only (real gate: unverified Replay refused)."""
    pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519", exc_type=ImportError)
    scratch = _scratch_replay(tmp_path_factory)
    if scratch is None:
        msg = "needs ODES_TEST_REPLAY_REPO naming a git repository that contains the pinned CP-2 Replay revision"
        if os.environ.get("ODES_REQUIRE_LIFECYCLE_E2E") == "1":
            pytest.fail("ODES_REQUIRE_LIFECYCLE_E2E=1 but the end-to-end Replay could not be set up: " + msg)
        pytest.skip(msg)
    saved_path = list(sys.path)
    saved_modules = {k: v for k, v in sys.modules.items() if k.split(".")[0] == "agent_replay_bundle"}
    for k in saved_modules:
        del sys.modules[k]
    saved_env = {k: os.environ.get(k) for k in ("ODES_ALLOW_UNVERIFIED_REPLAY", "PYTHONDONTWRITEBYTECODE")}
    os.environ["ODES_ALLOW_UNVERIFIED_REPLAY"] = "0"
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


def _load(directory: Path, run: str, proposal: str):
    return (json.loads((directory / run).read_text(encoding="utf-8")), json.loads((directory / proposal).read_text(encoding="utf-8")))


def lifecycle_bundle(replay, *, proposal=None):
    cp, prop = _load(LIFE, "lifecycle_control_plane_run.json", "lifecycle_proposal.json")
    return replay.import_bounded_workflow(cp, proposal=prop if proposal is None else proposal, moltbot_export=None,
                                          control_plane_revision=CP2_CP).model_dump(mode="json")


def unmarked_bundle(replay):
    """The existing CP-2 strict fixture: its proposal carries risk_metadata == {} (restriction and jurisdiction unknown)."""
    cp, prop = _load(CP2_DATA, "strict_control_plane_run.json", "strict_proposal.json")
    return replay.import_bounded_workflow(cp, proposal=prop, moltbot_export=None, control_plane_revision=CP2_CP).model_dump(mode="json")


def decided_at(bundle) -> str:
    record = next(r for r in bundle["records"] if r["record_type"] == "runtime_decision")
    return record["data"]["decided_at"]


def assertion(bundle, freshness="current", **over):
    """A SYNTHETIC attributed lifecycle assertion, one minute after the retained decision (never defaulted by the exporter)."""
    at = parse_instant(decided_at(bundle))
    value = {"freshness": freshness, "asserted_by": {**ISSUER, "actor_id": "synthetic-test-actor-nonproduction"},
             "asserted_at": (at.replace(microsecond=0) + __import__("datetime").timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
             "source": {"reference": "urn:synthetic:nonproduction:lifecycle-assertion:1"}}
    value.update(over)
    return value


def export(bundle, *, lifecycle=None, mode="explicit"):
    kwargs = {"restriction_semantics": mode}
    if lifecycle is not None:
        kwargs["lifecycle_assertion"] = lifecycle
    return exporter.export_cognous_stack_package(MANIFEST, bundle, **kwargs)


def seal(package):
    """Recompute both digests after a deliberate edit so validation, not the digest, is what must refuse it."""
    package["integrity"]["value"] = digest_of({"record": package["record"], "profile": package["profile"]})
    package["package_digest"] = digest_of({k: package[k] for k in ("record", "profile", "integrity", "provenance")})
    return package


def _key():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    return Ed25519PrivateKey.from_private_bytes(SEED)


def policy_for(package, *, signed=True, **over):
    from cryptography.hazmat.primitives import serialization
    from odes import signatures
    record = package["record"]
    raw = _key().public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    policy = {
        "now": NOW, "purpose": "audit", "relying_party": "recipient.example.org", "jurisdiction": SYNTH_JURISDICTION,
        "supported_profiles": [package["profile"]["implementation_profile"]], "evaluation_scope": "audit", "status_max_age_seconds": 300,
        "trusted_issuer": record["issuer"], "trusted_digests": [package["package_digest"]],
        "status_inputs": {"issuer": record["issuer"], "record_id": record["decision_id"], "authority_basis": record["authority"]["authority_basis"],
                          "evaluation_scope": "audit", "authority_valid_at_decision_verified": True, "evaluated_at": EVALUATED_AT,
                          "evidence_freshness": "current", "freshness": "current", "revoked": False, "superseded": False},
    }
    if signed:
        policy["detached_authentication"] = {
            "envelope": signatures.sign_package(package, _key(), "synthetic-issuer-key-nonproduction"),
            "trusted_keys": [{"keyid": "synthetic-issuer-key-nonproduction", "algorithm": "ed25519",
                              "public_key": base64.b64encode(raw).decode(), "issuer": "synthetic/nonproduction"}]}
    policy.update(over)
    return policy


def evaluate(package, **over):
    return rv.evaluate_recipient_package(package, policy_for(package, **over))


def layer_statuses(result):
    return {k: v["status"] for k, v in result.items() if isinstance(v, dict) and "status" in v}


# ============================================================================================ OP1
def test_op1_opt_in_synthetic_native_pass_with_real_evaluator(replay):
    """OP1. SYNTHETIC native pass: attributed lifecycle + committed explicit restrictions + synthetic recipient policy/auth/status. Evaluator not stubbed."""
    bundle = lifecycle_bundle(replay)
    package = export(bundle, lifecycle=assertion(bundle))
    assert package["profile"]["implementation_profile"] == PROFILE_V2_LIFECYCLE_ID
    assert package["profile"]["implementation_profile_version"].endswith("+restriction-semantics-1+lifecycle-semantics-1")
    assert package["record"]["status"] == {"freshness": "current", "superseded": False, "revoked": False}
    assert package["record"]["risk_coordinates"]["restricted_use_flag"] is False and package["record"]["risk_coordinates"]["prohibited_use_flag"] is False
    assert package["record"]["risk_coordinates"]["jurisdiction"] == SYNTH_JURISDICTION
    member = package["provenance"]["lifecycle_semantics"]
    assert member["bound_to"]["decision_id"] == package["record"]["decision_id"] and LIFECYCLE_ISSUER_ASSERTED_LIMIT in package["provenance"]["limits"]
    result = evaluate(package)
    assert layer_statuses(result) == {name: "pass" for name in (
        "schema_validity", "replay_semantic_consistency", "declared_profile_conformance", "package_content_integrity",
        "integrity_authentication_checks", "historical_authority_assertions", "authority_status_and_freshness", "consumption_conditions",
        "recipient_reliance_decision")}, result["recipient_reliance_decision"]


def test_op1_requires_explicit_policy_opt_in_and_independent_inputs(replay):
    bundle = lifecycle_bundle(replay)
    package = export(bundle, lifecycle=assertion(bundle))
    default = rv.evaluate_recipient_package(package, {**policy_for(package), "supported_profiles": [PROFILE_V2_RESTRICTIONS_ID, PROFILE_V2_ID]})
    assert default["declared_profile_conformance"]["status"] == "unsupported" and default["recipient_reliance_decision"]["status"] != "pass"
    no_default = rv.evaluate_recipient_package(package, {k: v for k, v in policy_for(package).items() if k != "supported_profiles"})
    assert no_default["declared_profile_conformance"]["status"] == "unsupported"
    for missing in ("status_inputs", "detached_authentication"):
        policy = policy_for(package)
        del policy[missing]
        assert rv.evaluate_recipient_package(package, policy)["recipient_reliance_decision"]["status"] != "pass"


# ============================================================================================ N1
def test_n1_missing_risk_metadata_remains_restrictive(replay):
    bundle = unmarked_bundle(replay)
    package = export(bundle, lifecycle=assertion(bundle))
    coords = package["record"]["risk_coordinates"]
    assert coords["restricted_use_flag"] is True and coords["prohibited_use_flag"] is True and coords["jurisdiction"] == "unknown"
    result = evaluate(package)
    assert result["consumption_conditions"]["status"] == "fail" and result["recipient_reliance_decision"]["status"] != "pass"
    plain = export(bundle)  # explicit, no lifecycle: unchanged conservative behavior
    assert plain["profile"]["implementation_profile"] == PROFILE_V2_RESTRICTIONS_ID
    assert evaluate(plain, signed=True)["consumption_conditions"]["status"] == "fail"


# ============================================================================================ N3
@pytest.mark.parametrize("freshness", ["stale", "expired", "pending_revalidation"])
def test_n3_record_side_non_current_freshness_refuses_despite_favorable_recipient_inputs(replay, freshness):
    bundle = lifecycle_bundle(replay)
    package = export(bundle, lifecycle=assertion(bundle, freshness))
    result = evaluate(package)
    assert result["authority_status_and_freshness"]["status"] == "fail"
    assert result["recipient_reliance_decision"]["status"] != "pass"


def test_n3_record_side_unknown_freshness_refuses_despite_favorable_recipient_inputs(replay):
    bundle = lifecycle_bundle(replay)
    package = export(bundle)  # explicit restrictions, no lifecycle assertion: freshness stays unknown
    assert package["record"]["status"]["freshness"] == "unknown"
    result = evaluate(package)
    assert result["authority_status_and_freshness"]["status"] == "fail" and result["recipient_reliance_decision"]["status"] != "pass"


BAD = {
    "list_freshness": {"freshness": ["current"]}, "unknown": {"freshness": "unknown"}, "unsupported_value": {"freshness": "fresh"}, "recent": {"freshness": "recent"},
    "revoked": {"freshness": "revoked"}, "superseded": {"freshness": "superseded"}, "no_freshness": {"freshness": None},
    "not_issuer": {"asserted_by": {"organization_id": "other.org", "system_id": "other", "actor_id": "x"}},
    "no_actor": {"asserted_by": {"organization_id": ISSUER["organization_id"], "system_id": ISSUER["system_id"]}},
    "blank_actor": {"asserted_by": {**ISSUER, "actor_id": "  "}}, "naive_time": {"asserted_at": "2026-10-05T19:30:00"},
    "bad_time": {"asserted_at": "yesterday"}, "before_decision": {"asserted_at": "2026-10-05T18:00:00Z"},
    "future_time": {"asserted_at": "2999-01-01T00:00:00Z"}, "empty_source": {"source": {"reference": ""}},
    "no_source": {"source": None}, "extra_source_member": {"source": {"reference": "x", "extra": 1}},
}


@pytest.mark.parametrize("name", sorted(BAD))
def test_n3_malformed_unsupported_or_unattributed_lifecycle_input_is_rejected(replay, name):
    bundle = lifecycle_bundle(replay)
    with pytest.raises(exporter.ExportError):
        export(bundle, lifecycle=assertion(bundle, **BAD[name]))


def test_n3_lifecycle_input_shape_and_mode_are_closed(replay):
    bundle = lifecycle_bundle(replay)
    good = assertion(bundle)
    for bad in ({**good, "extra": 1}, {k: v for k, v in good.items() if k != "source"}, "current", ["current"]):
        with pytest.raises(exporter.ExportError):
            export(bundle, lifecycle=bad)
    with pytest.raises(exporter.ExportError):
        export(bundle, lifecycle=good, mode="legacy")  # requires explicit restriction semantics
    meta_bundle = copy.deepcopy(bundle)
    meta_bundle["metadata"]["freshness"] = "stale"
    with pytest.raises(exporter.ExportError):
        export(meta_bundle, lifecycle=good)  # never combined with, or overriding, bundle-carried lifecycle state


def test_n3_package_claiming_the_lifecycle_profile_without_the_assertion_is_rejected(replay):
    bundle = lifecycle_bundle(replay)
    package = export(bundle, lifecycle=assertion(bundle))
    del package["provenance"]["lifecycle_semantics"]
    seal(package)
    result = evaluate(package)
    assert result["declared_profile_conformance"]["status"] == "fail" and result["replay_semantic_consistency"]["status"] != "pass"
    assert result["recipient_reliance_decision"]["status"] != "pass"
    relabel = export(bundle)  # a restrictions package relabelled as the lifecycle profile
    relabel["profile"]["implementation_profile"] = relabel["record"]["verification"]["conformance_profile"] = PROFILE_V2_LIFECYCLE_ID
    seal(relabel)
    assert evaluate(relabel)["recipient_reliance_decision"]["status"] != "pass"


# ============================================================================================ N4
def test_n4_risk_metadata_mutated_after_proposal_commitment_breaks_replay(replay):
    cp, prop = _load(LIFE, "lifecycle_control_plane_run.json", "lifecycle_proposal.json")
    changed = copy.deepcopy(prop)
    changed["risk_metadata"]["jurisdiction"] = "ANOTHER-JURISDICTION"
    with pytest.raises(replay.ImportContractError, match="conflicts with committed operation"):
        replay.import_bounded_workflow(cp, proposal=changed, moltbot_export=None, control_plane_revision=CP2_CP)
    flipped = copy.deepcopy(prop)
    flipped["risk_metadata"]["restricted_use_flag"] = True
    with pytest.raises(replay.ImportContractError, match="conflicts with committed operation"):
        replay.import_bounded_workflow(cp, proposal=flipped, moltbot_export=None, control_plane_revision=CP2_CP)


def test_n4_lifecycle_alteration_or_resealing_is_a_mismatch_or_rejection(replay):
    bundle = lifecycle_bundle(replay)
    base = export(bundle, lifecycle=assertion(bundle))

    def tampered(edit):
        package = copy.deepcopy(base)
        edit(package)
        return seal(package)

    cases = {
        "record_status_only": lambda p: p["record"]["status"].__setitem__("freshness", "stale"),
        "provenance_freshness_only": lambda p: p["provenance"]["lifecycle_semantics"].__setitem__("freshness", "stale"),
        "bound_decision_id": lambda p: p["provenance"]["lifecycle_semantics"]["bound_to"].__setitem__("decision_id", "other-decision"),
        "bound_bundle_digest": lambda p: p["provenance"]["lifecycle_semantics"]["bound_to"].__setitem__("reconstruction_bundle_digest", "sha256:" + "0" * 64),
        "attributed_to_other_org": lambda p: p["provenance"]["lifecycle_semantics"]["asserted_by"].__setitem__("organization_id", "other.org"),
        "attribution_removed": lambda p: p["provenance"]["lifecycle_semantics"].pop("asserted_by"),
        "limit_removed": lambda p: p["provenance"]["limits"].remove(LIFECYCLE_ISSUER_ASSERTED_LIMIT),
    }
    for name, edit in cases.items():
        result = evaluate(tampered(edit), trusted_digests=[base["package_digest"]])
        explicit_rejection = result["declared_profile_conformance"]["status"] == "fail"
        mismatch = result["replay_semantic_consistency"]["status"] != "pass"
        assert explicit_rejection or mismatch, name
        assert result["recipient_reliance_decision"]["status"] != "pass", name


def test_n4_a_consistent_rewrite_is_caught_only_by_the_independent_digest_anchor_not_by_replay(replay):
    """Documented limit: an issuer rewriting the assertion consistently and resealing passes Replay consistency; the recipient's trusted digest catches it."""
    bundle = lifecycle_bundle(replay)
    base = export(bundle, lifecycle=assertion(bundle))
    rewritten = export(bundle, lifecycle=assertion(bundle, source={"reference": "urn:synthetic:nonproduction:lifecycle-assertion:2"}))
    assert rewritten["package_digest"] != base["package_digest"]
    anchored = evaluate(rewritten, trusted_digests=[base["package_digest"]])
    assert anchored["package_content_integrity"]["status"] != "pass" and anchored["recipient_reliance_decision"]["status"] != "pass"


# ============================================================================================ Compat
def test_compat_default_and_restrictions_exports_carry_no_lifecycle_material(replay):
    bundle = lifecycle_bundle(replay)
    for mode, profile in (("legacy", PROFILE_V2_ID), ("explicit", PROFILE_V2_RESTRICTIONS_ID)):
        package = export(bundle, mode=mode)
        assert package["profile"]["implementation_profile"] == profile
        assert "lifecycle_semantics" not in package["provenance"] and LIFECYCLE_ISSUER_ASSERTED_LIMIT not in package["provenance"]["limits"]
        assert "lifecycle" not in package["profile"]["implementation_profile_version"] and package["record"]["status"]["freshness"] == "unknown"
        assert exporter.export_cognous_stack_package(MANIFEST, bundle, restriction_semantics=mode, lifecycle_assertion=None)["package_digest"] == package["package_digest"]


def test_compat_the_lifecycle_id_is_not_in_any_default_or_historical_set():
    assert PROFILE_V2_LIFECYCLE_ID not in {PROFILE_V2_ID, PROFILE_V2_RESTRICTIONS_ID}
    assert PROFILE_V2_LIFECYCLE_ID in rv.V2_FAMILY and PROFILE_V2_RESTRICTIONS_ID in rv.V2_FAMILY and PROFILE_V2_ID in rv.V2_FAMILY
    assert rv.evaluate_recipient_package({"package_type": "x"}, {})["recipient_reliance_decision"]["status"] == "fail"
