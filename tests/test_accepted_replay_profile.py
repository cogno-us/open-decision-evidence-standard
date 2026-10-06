from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

from agent_replay_bundle.importers import import_bounded_workflow
from odes.common import PINNED_REVISIONS, PROFILE_ID, sha256
from odes.exporter import ExportError, export_cognous_stack_package
from odes.recipient_validator import evaluate_recipient_package


MOLTBOT_REVISION = "1d308faf664c504b6e310db3c7a310153ef7b067"
REPLAY_REVISION = "f63ce914504dd06813c4ccd199b0570dbd8dd427"


def _root(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} not configured")
    path = Path(value)
    if not path.exists():
        pytest.skip(f"{name} does not exist: {path}")
    return path


def _load_moltbot_fixture():
    cp_root = _root("ODES_PINNED_CONTROL_PLANE_ROOT")
    molt_root = _root("ODES_PINNED_MOLTBOT_ROOT")
    manifest = _root("ODES_PINNED_MANIFEST_FIXTURE")

    sys.path.insert(0, str(cp_root / "src"))
    sys.path.insert(0, str(molt_root))
    os.environ["MOLTBOT_SAFE_CONTROL_PLANE_ROOT"] = str(cp_root)
    os.environ["MOLTBOT_SAFE_MANIFEST_FIXTURE"] = str(manifest)

    helper_path = molt_root / "tests" / "test_safe_executor.py"
    spec = importlib.util.spec_from_file_location(
        "odes_accepted_moltbot_fixture", helper_path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest() -> dict:
    return json.loads(
        _root("ODES_PINNED_MANIFEST_FIXTURE").read_text(encoding="utf-8")
    )


def _export_sources(workflow, proposal, request, result, destination):
    from engine.producer_contract import export_execution_artifacts

    cp = workflow.records.load().model_dump(mode="json")
    producer = export_execution_artifacts(
        request,
        result,
        destination,
        repository_revision=MOLTBOT_REVISION,
        source_asserted_provenance={"test_source": "odes_accepted_profile"},
    )
    proposal_data = proposal.model_dump(mode="json", exclude_none=False)
    return cp, proposal_data, producer


def _replay_bundle(cp, proposal, producer) -> dict:
    bundle = import_bounded_workflow(
        cp, proposal=proposal, moltbot_export=producer
    ).model_dump(mode="json")
    bundle.setdefault("metadata", {})["freshness"] = "current"
    return bundle


def _accepted_success(tmp_path):
    h = _load_moltbot_fixture()
    helper, proposal, resolver, workflow, decision, destination, executor, request = (
        h._integrated(tmp_path)
    )
    result = executor.execute(
        envelope=request, proposal=proposal, decision=decision, now=h.NOW
    )
    assert result.status == "executed"
    cp, p, producer = _export_sources(
        workflow, proposal, request, result, destination
    )
    return h, proposal, resolver, workflow, decision, destination, executor, request, _replay_bundle(cp, p, producer)


def _trusted_status(package: dict, **overrides) -> dict:
    value = {
        "record_id": package["record"]["decision_id"],
        "authority_basis": package["record"]["authority"]["authority_basis"],
        "evaluation_scope": "recipient_reliance",
        "evaluated_at": "2026-10-06T00:00:00Z",
        "evidence_freshness": "current",
        "freshness": "current",
        "revoked": False,
        "superseded": False,
        "authority_valid_at_decision_verified": True,
    }
    value.update(overrides)
    return value


def _policy(package: dict, **overrides) -> dict:
    value = {
        "supported_profiles": [PROFILE_ID],
        "relying_party": "recipient.example.org",
        "purpose": "audit",
        "now": "2026-10-06T00:00:00Z",
        "trusted_digests": [package["package_digest"]],
        "trusted_key_refs": [],
        "status_inputs": _trusted_status(package),
        "evaluation_scope": "recipient_reliance",
        "status_max_age_seconds": 300,
        "allow_unauthenticated_informational_inspection": True,
    }
    value.update(overrides)
    return value


def _record(bundle: dict, kind: str) -> list[dict]:
    return [r for r in bundle["records"] if r["record_type"] == kind]


def test_accepted_profile_success_exports_without_promoting_provenance(tmp_path):
    *_, bundle = _accepted_success(tmp_path)
    package = export_cognous_stack_package(_manifest(), bundle)

    assert PINNED_REVISIONS["moltbot_safe"] == MOLTBOT_REVISION
    assert PINNED_REVISIONS["replay"] == REPLAY_REVISION
    assert package["provenance"]["replay_validation"]["status"] in {
        "reconstruction_complete",
        "reconstruction_partial",
    }
    contract = bundle["metadata"]["moltbot_producer_contract"]
    assert contract["interface_profile_version"] == "1.0.0"
    assert contract["repository_revision"] == MOLTBOT_REVISION
    assert contract["provenance"]["source_asserted"]["repository_revision"] == MOLTBOT_REVISION
    assert contract["provenance"]["independently_established"] == []

    result = evaluate_recipient_package(package, _policy(package))
    assert result["package_content_integrity"]["status"] == "pass"
    assert result["integrity_authentication_checks"]["status"] == "unavailable"
    assert result["recipient_reliance_decision"]["status"] == "informational_only"


def test_accepted_profile_reconciliation_preserves_attempt_namespaces(tmp_path):
    h = _load_moltbot_fixture()
    helper, proposal, resolver, workflow, decision, destination, executor, request = (
        h._integrated(tmp_path)
    )
    first = executor.execute(
        envelope=request, proposal=proposal, decision=decision, now=h.NOW
    )
    assert first.status == "executed"
    restarted_destination = h.DurableRefundDestination(destination.root)
    restarted_executor = h.PinnedControlPlaneExecutor(
        workflow=workflow,
        destination=restarted_destination,
        policy=h.policy(request.operation),
    )
    reconciled = restarted_executor.execute(
        envelope=request, proposal=proposal, decision=decision, now=h.NOW
    )
    assert reconciled.status == "reconciled"

    cp, p, producer = _export_sources(
        workflow, proposal, request, reconciled, restarted_destination
    )
    assert producer["attempt_identity"]["namespace"] == "control_plane"
    bundle = _replay_bundle(cp, p, producer)
    package = export_cognous_stack_package(_manifest(), bundle)

    facts = package["provenance"]["execution_facts"]
    cp_attempt_id = producer["attempt_identity"]["attempt_id"]
    assert cp_attempt_id in facts["attempt_namespaces"]["control_plane"]
    assert cp_attempt_id not in facts["attempt_namespaces"]["executor"]
    assert len(_record(bundle, "destination_effect")) == 1


@pytest.mark.parametrize("mode", ["lost_ack", "partial"])
def test_accepted_profile_lost_ack_and_partial_survive_odes(tmp_path, mode):
    h = _load_moltbot_fixture()
    helper, proposal, resolver, workflow, decision, destination, executor, request = (
        h._integrated(tmp_path)
    )
    result = executor.execute(
        envelope=request,
        proposal=proposal,
        decision=decision,
        now=h.NOW,
        simulate=mode,
    )
    cp, p, producer = _export_sources(
        workflow, proposal, request, result, destination
    )
    bundle = _replay_bundle(cp, p, producer)
    package = export_cognous_stack_package(_manifest(), bundle)
    facts = package["provenance"]["execution_facts"]

    if mode == "lost_ack":
        assert facts["acknowledgement_summary"] == "unknown"
        assert facts["destination_observed"] == "applied"
    else:
        assert facts["destination_observed"] == "partial"


@pytest.mark.parametrize("state", ["absent", "unknown"])
def test_accepted_profile_historical_absent_unknown_survive_odes(tmp_path, state):
    h = _load_moltbot_fixture()
    helper, proposal, resolver, workflow, decision, destination, executor, request = (
        h._integrated(tmp_path)
    )
    if state == "absent":
        result = executor.observe_historical(request)
    else:
        from engine.safe_executor import ExecutionResult
        result = ExecutionResult(
            status="observed",
            decision_id=request.decision_id,
            effect_id=request.effect_id,
            attempt_id=None,
            attempted=False,
            acknowledged=False,
            observed_state="unknown",
            newly_executed=False,
            observation={
                "effect_id": request.effect_id,
                "state": "unknown",
                "destination_state": {},
            },
        )
    cp, p, producer = _export_sources(
        workflow, proposal, request, result, destination
    )
    bundle = _replay_bundle(cp, p, producer)
    package = export_cognous_stack_package(_manifest(), bundle)
    assert package["provenance"]["execution_facts"]["destination_observed"] in {
        state,
        "unavailable",
    }


def test_accepted_profile_denied_no_effect_survives_odes(tmp_path):
    h = _load_moltbot_fixture()
    helper, proposal, resolver, workflow, decision, destination, executor, request = (
        h._integrated(tmp_path)
    )
    grant = resolver.contexts[helper.PROFILE]["grant"]
    resolver.statuses[grant["grant_id"]].status = "revoked"
    denied = executor.execute(
        envelope=request, proposal=proposal, decision=decision, now=h.NOW
    )
    assert denied.status == "denied"
    cp, p, producer = _export_sources(
        workflow, proposal, request, denied, destination
    )
    bundle = _replay_bundle(cp, p, producer)
    package = export_cognous_stack_package(_manifest(), bundle)
    assert package["provenance"]["execution_facts"]["destination_effects"] == []


@pytest.mark.parametrize("mutation", ["revision", "profile", "attempt_lineage"])
def test_odes_rejects_incorrect_versioned_producer_contract(tmp_path, mutation):
    h = _load_moltbot_fixture()
    helper, proposal, resolver, workflow, decision, destination, executor, request = (
        h._integrated(tmp_path)
    )
    result = executor.execute(
        envelope=request, proposal=proposal, decision=decision, now=h.NOW
    )
    cp, p, producer = _export_sources(
        workflow, proposal, request, result, destination
    )
    bundle = _replay_bundle(cp, p, producer)

    if mutation == "revision":
        bundle["metadata"]["moltbot_producer_contract"]["repository_revision"] = "unsupported"
        bundle["metadata"]["moltbot_producer_contract"]["provenance"]["source_asserted"]["repository_revision"] = "unsupported"
    elif mutation == "profile":
        bundle["metadata"]["moltbot_producer_contract"]["interface_profile_id"] = "urn:unsupported"
    else:
        result_record = _record(bundle, "execution_result")[0]
        result_record["data"]["attempt_id"] = "dangling-attempt"
        result_record["identifiers"]["attempt_id"] = "dangling-attempt"

    with pytest.raises(ExportError):
        export_cognous_stack_package(_manifest(), bundle)


def test_package_tampering_wrong_recipient_and_wrong_purpose_still_fail(tmp_path):
    *_, bundle = _accepted_success(tmp_path)
    package = export_cognous_stack_package(_manifest(), bundle)

    tampered = copy.deepcopy(package)
    tampered["provenance"]["execution_facts"]["destination_observed"] = "unknown"
    assert evaluate_recipient_package(
        tampered, _policy(package)
    )["package_content_integrity"]["status"] == "fail"

    wrong_recipient = evaluate_recipient_package(
        package, _policy(package, relying_party="wrong.example.org")
    )
    assert wrong_recipient["consumption_conditions"]["status"] == "fail"

    wrong_purpose = evaluate_recipient_package(
        package, _policy(package, purpose="production_reuse")
    )
    assert wrong_purpose["consumption_conditions"]["status"] == "fail"


def test_current_label_does_not_override_stale_or_future_status_time(tmp_path):
    *_, bundle = _accepted_success(tmp_path)
    package = export_cognous_stack_package(_manifest(), bundle)

    stale = _policy(
        package,
        status_inputs=_trusted_status(
            package,
            evaluated_at="2026-10-05T23:54:59Z",
            evidence_freshness="current",
            freshness="current",
        ),
    )
    stale_result = evaluate_recipient_package(package, stale)
    assert stale_result["authority_status_and_freshness"]["status"] == "fail"

    future = _policy(
        package,
        status_inputs=_trusted_status(
            package,
            evaluated_at="2026-10-06T00:00:01Z",
            evidence_freshness="current",
            freshness="current",
        ),
    )
    future_result = evaluate_recipient_package(package, future)
    assert future_result["authority_status_and_freshness"]["status"] == "fail"


def test_missing_freshness_policy_scope_and_authentication_remain_unavailable_or_fail(tmp_path):
    *_, bundle = _accepted_success(tmp_path)
    package = export_cognous_stack_package(_manifest(), bundle)

    no_age = _policy(package)
    no_age.pop("status_max_age_seconds")
    no_age_result = evaluate_recipient_package(package, no_age)
    assert no_age_result["authority_status_and_freshness"]["status"] == "fail"

    scope = _policy(package)
    scope["status_inputs"]["evaluation_scope"] = "audit"
    scope_result = evaluate_recipient_package(package, scope)
    assert scope_result["authority_status_and_freshness"]["status"] == "fail"

    no_status = _policy(package, status_inputs={})
    no_status_result = evaluate_recipient_package(package, no_status)
    assert no_status_result["historical_authority_assertions"]["status"] == "unavailable"
    assert no_status_result["authority_status_and_freshness"]["status"] == "unavailable"

    auth = evaluate_recipient_package(package, _policy(package))
    assert auth["integrity_authentication_checks"]["status"] == "unavailable"
