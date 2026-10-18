"""Conformance tests for the execution-attempt lifecycle contract spike (0.1.0-draft).

Docs-and-fixtures only: this exercises contracts/execution-attempt-lifecycle/validate.py against the
golden fixtures. It does not import or alter the odes package.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

CONTRACT_DIR = Path(__file__).resolve().parents[1] / "contracts" / "execution-attempt-lifecycle"
_spec = importlib.util.spec_from_file_location("eal_validate", CONTRACT_DIR / "validate.py")
eal = importlib.util.module_from_spec(_spec)
sys.modules["eal_validate"] = eal
_spec.loader.exec_module(eal)


def _load(kind):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((CONTRACT_DIR / "fixtures" / kind).glob("*.json"))]


VALID = _load("valid")
INVALID = _load("invalid")


def test_fixture_sets_are_present_and_well_formed():
    assert len(VALID) >= 8 and len(INVALID) >= 8
    for fx in VALID + INVALID:
        assert fx["synthetic"] is True and fx["reason"].strip()
        assert fx["expected_outcome"] in {"accept", "reject"}
    assert all(f["expected_outcome"] == "accept" for f in VALID)
    assert all(f["expected_outcome"] == "reject" and f["expected_refusal"] for f in INVALID)
    names = [f["fixture_id"] for f in VALID + INVALID]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("fx", VALID, ids=lambda f: f["fixture_id"])
def test_valid_fixture_is_accepted(fx):
    assert eal.validate(fx["document"]) == []


@pytest.mark.parametrize("fx", INVALID, ids=lambda f: f["fixture_id"])
def test_invalid_fixture_is_refused_with_stated_reason(fx):
    codes = [v.code for v in eal.validate(fx["document"])]
    assert codes == [fx["expected_refusal"]], fx["reason"]


def test_required_valid_cases_exist():
    ids = {f["fixture_id"] for f in VALID}
    assert {"executor-unknown-ack-unobserved", "control-plane-reconciled-existing-acknowledged",
            "control-plane-reconciled-existing-partial", "executor-normal-attempted-executed-observed",
            "extension-namespace-member-preserved", "executor-unknown-recovery-observation-route-b",
            "executor-unknown-recovery-unavailable-route-b", "executor-unknown-recovery-hold-route-b",
            "executor-observed-effect-free-reconcile-route-b",
            "executor-unknown-recovery-separate-member-route-b", "executor-normal-observations-member",
            "executor-denied-attempt-event", "executor-unknown-validated-absent-after-ambiguous-dispatch",
            "executor-unknown-validated-unknown-after-ambiguous-dispatch",
            "control-plane-attempt-extensions-preserved", "resolution-journal-checks-extensions-preserved"} <= ids
    assert sum(i.startswith("resolution-checks-overlap") for i in ids) >= 2


def test_required_invalid_cases_exist():
    codes = {f["expected_refusal"] for f in INVALID}
    assert {"missing_start_record", "unknown_with_validated_observation", "status_terminal_mismatch", "terminal_event_missing",
            "resolution_checks_out_of_order", "undeclared_member", "invalid_reconciled_marker",
            "unknown_state_mismatch", "recovery_retry_eligible", "recovery_report_incomplete",
            "effect_free_reconcile_claims_attempt", "recovery_state_mismatch",
            "recovery_observations_mismatch", "unknown_enum_value", "schema_violation",
            "observed_result_claims_attempt", "executed_without_observation", "attempt_started_at_changed",
            "null_observation_state_mismatch", "observations_mismatch", "invalid_extension_key"} <= codes
    ids = {f["fixture_id"] for f in INVALID}
    assert {"empty-object-observation", "executor-unknown-with-validated-partial-observation",
            "executor-unknown-validated-absent-state-mismatch", "null-observation-state-absent",
            "mixed-layout-observations-disagree-with-result", "control-plane-attempt-undeclared-member",
            "control-plane-attempt-extension-key-without-x-prefix", "resolution-journal-extension-key-without-x-prefix",
            "resolution-check-undeclared-member"} <= ids


def test_f10_protection_unknown_member_is_refused_not_dropped():
    fx = next(f for f in INVALID if f["fixture_id"] == "undeclared-member-outside-extensions")
    (violation,) = eal.validate(fx["document"])
    assert violation.code == "undeclared_member" and violation.path.endswith("injected_member")


def test_extensions_are_preserved_and_bound_into_the_digest():
    doc = next(f for f in VALID if f["fixture_id"] == "extension-namespace-member-preserved")["document"]
    again = eal.preserve(doc)
    assert again == doc and again["extensions"]["x-syn-vendor.trace"] == {"span": "abc", "hops": 2}
    stripped = json.loads(json.dumps(doc))
    del stripped["extensions"]
    assert eal.canonical_bytes(stripped) != eal.canonical_bytes(doc)
    # Ignore-but-preserve: contract logic never reads extensions, so the verdict does not depend on them.
    assert eal.validate(stripped) == []
    assert "extensions" not in eal.known_view(doc)


def _route_b():
    return json.loads(json.dumps(next(f for f in VALID if f["fixture_id"] == "executor-unknown-recovery-observation-route-b")["document"]))


def test_recovery_observation_is_not_validated_evidence():
    doc = _route_b()
    assert eal.observation_kind(doc["execution_result"]["observation"]) == "recovery"
    assert eal.validate(doc) == []
    # The same record may not ride on a result that claims execution or reconciliation.
    doc["execution_result"]["status"] = "executed"
    codes = [v.code for v in eal.validate(doc)]
    assert codes == ["recovery_observation_status"]


def test_recovery_record_is_closed_and_typed():
    doc = _route_b()
    doc["execution_result"]["observation"]["surprise"] = 1
    assert [v.code for v in eal.validate(doc)] == ["schema_violation"]


def test_null_observation_requires_unknown_state_for_every_status():
    doc = json.loads(json.dumps(next(f for f in VALID if f["fixture_id"] == "executor-unknown-ack-unobserved")["document"]))
    doc["execution_result"]["observed_state"] = "applied"
    assert [v.code for v in eal.validate(doc)] == ["null_observation_state_mismatch"]


def test_empty_object_observation_is_never_valid():
    doc = json.loads(json.dumps(next(f for f in VALID if f["fixture_id"] == "executor-unknown-ack-unobserved")["document"]))
    doc["execution_result"]["observation"] = {}
    assert [v.code for v in eal.validate(doc)] == ["schema_violation"]


def test_unknown_may_carry_validated_absent_or_unknown_only():
    base = json.loads(json.dumps(next(f for f in VALID if f["fixture_id"] == "executor-unknown-ack-unobserved")["document"]))
    for state, ok in (("absent", True), ("unknown", True), ("applied", False), ("partial", False)):
        doc = json.loads(json.dumps(base))
        doc["execution_result"]["observation"] = {"effect_id": "syn-effect-1", "state": state}
        doc["execution_result"]["observed_state"] = state
        assert ([v.code for v in eal.validate(doc)] == []) == ok, state
        if not ok:
            assert [v.code for v in eal.validate(doc)] == ["unknown_with_validated_observation"]


def test_removing_an_optional_declared_member_stays_valid():
    doc = json.loads(json.dumps(next(f for f in VALID if f["fixture_id"] == "executor-unknown-ack-unobserved")["document"]))
    for name in ("attempted", "acknowledged", "newly_executed"):
        del doc["execution_result"][name]
    assert eal.validate(doc) == []


def test_missing_required_member_is_refused():
    doc = json.loads(json.dumps(VALID[0]["document"]))
    doc.pop("contract_version")
    assert [v.code for v in eal.validate(doc)] == ["schema_violation"]


def test_unsupported_contract_version_is_refused_typed():
    doc = json.loads(json.dumps(VALID[0]["document"]))
    doc["contract_version"] = "9.0.0"
    assert [v.code for v in eal.validate(doc)] == ["unsupported_contract_version"]


def test_schema_is_draft_2020_12_and_agrees_with_reference_validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = eal.load_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    validator_cls = jsonschema.Draft202012Validator
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    for fx in VALID:
        assert not list(validator.iter_errors(fx["document"])), fx["fixture_id"]
    structural = {"undeclared_member", "invalid_extension_key", "schema_violation", "unknown_enum_value"}
    for fx in INVALID:
        if fx["fixture_id"] == "unpaired-surrogate-text":
            continue  # text validity is a validator rule; the portable schema does not state it
        errors = list(validator.iter_errors(fx["document"]))
        assert bool(errors) == (fx["expected_refusal"] in structural), fx["fixture_id"]


# ---- reasons_match: a check row may carry only the completion's reasons plus the closed post-journal gate set

def _journal_doc():
    fx = next(f for f in VALID if f["fixture_id"] == "resolution-journal-checks-extensions-preserved")
    return json.loads(json.dumps(fx["document"]))


def test_post_journal_gate_codes_are_a_published_closed_set():
    codes = eal.POST_JOURNAL_GATE_CODES
    assert isinstance(codes, frozenset)
    assert codes == {
        "operation_grant_mismatch", "operation_renewal_unrecorded", "operation_not_admitted",
        "operation_merged_effect_exists", "operation_merged_effect_unresolved",
        "dedupe_unresolved_attempt_blocks_new_key", "dedupe_operation_effect_applied",
        "input_observation_time_regressed"}


def test_check_row_with_a_reason_the_journal_does_not_carry_is_refused():
    doc = _journal_doc()
    doc["resolution_checks"][0]["reasons"] = ["grant_revoked"]
    codes = {v.code for v in eal.validate(doc)}
    assert codes == {"journal_unbound_completion"}


@pytest.mark.parametrize("code", sorted(eal.POST_JOURNAL_GATE_CODES) if hasattr(eal, "POST_JOURNAL_GATE_CODES") else ["operation_not_admitted"])
def test_check_row_with_a_post_journal_gate_code_is_accepted(code):
    doc = _journal_doc()
    doc["resolution_checks"][0]["reasons"] = [code]
    assert eal.validate(doc) == []


def test_check_row_with_a_gate_code_and_a_non_gate_code_is_refused():
    doc = _journal_doc()
    doc["resolution_checks"][0]["reasons"] = ["operation_not_admitted", "grant_revoked"]
    assert {v.code for v in eal.validate(doc)} == {"journal_unbound_completion"}
