"""Conformance tests for the Control Plane journal contract draft (0.1.0-draft).

Docs-and-fixtures only: this exercises contracts/control-plane-journal/validate.py against the golden fixtures.
It does not import or alter the odes package.
"""
import copy
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "contracts" / "control-plane-journal"
LIFECYCLE_DIR = ROOT / "contracts" / "execution-attempt-lifecycle"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # validate.py defines a dataclass; register before exec
    spec.loader.exec_module(module)
    return module


cpj = _load("cpj_validate", CONTRACT_DIR / "validate.py")
eal = _load("cpj_eal_validate", LIFECYCLE_DIR / "validate.py")


def _fixtures(kind):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((CONTRACT_DIR / "fixtures" / kind).glob("*.json"))]


VALID = _fixtures("valid")
INVALID = _fixtures("invalid")


def doc(fixture_id):
    return copy.deepcopy(next(f for f in VALID if f["fixture_id"] == fixture_id)["document"])


def codes(d):
    return [v.code for v in cpj.validate(d)]


def test_fixture_sets_are_present_and_well_formed():
    assert len(VALID) >= 10 and len(INVALID) >= 40
    for fx in VALID + INVALID:
        assert fx["synthetic"] is True and fx["reason"].strip()
        assert fx["expected_outcome"] in {"accept", "reject"}
        assert fx["document"]["contract"] == "control-plane-journal"
        assert fx["document"]["contract_version"] == "0.1.0-draft" or fx["fixture_id"] == "unsupported-contract-version"
    assert all(f["expected_outcome"] == "accept" for f in VALID)
    assert all(f["expected_outcome"] == "reject" and f["expected_refusal"] for f in INVALID)
    names = [f["fixture_id"] for f in VALID + INVALID]
    assert len(names) == len(set(names))
    for kind in ("valid", "invalid"):
        for path in (CONTRACT_DIR / "fixtures" / kind).glob("*.json"):
            assert json.loads(path.read_text())["fixture_id"] == path.stem


@pytest.mark.parametrize("fx", VALID, ids=lambda f: f["fixture_id"])
def test_valid_fixture_is_accepted(fx):
    assert cpj.validate(fx["document"]) == []


@pytest.mark.parametrize("fx", INVALID, ids=lambda f: f["fixture_id"])
def test_invalid_fixture_is_refused_with_stated_reason(fx):
    assert codes(fx["document"]) == [fx["expected_refusal"]], fx["reason"]


def test_required_valid_cases_exist():
    ids = {f["fixture_id"] for f in VALID}
    assert {"normal-attempted-acknowledged-applied", "partial-dispatch-partial-observation",
            "lost-ack-unknown-then-closeout", "reconciled-existing-single-row", "effect-time-refusal",
            "held-decision-journal-mode", "observation-unavailable-rejected-reconciliation",
            "interrupted-check-is-unfinished-evidence", "failed-definitive-rejection", "no-journal-mode-normal",
            "extension-namespace-members-preserved", "tenant-binding-generation-0.2",
            "vocabulary-change-recorded"} <= ids


def test_every_rule_code_is_pinned_by_a_fixture_or_a_test():
    """Every stable code the validator can emit appears in the README table and is exercised by an invalid fixture."""
    source = (CONTRACT_DIR / "validate.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'_v\(\s*"([a-z_]+)"', source)) | set(re.findall(r'Violation\(\s*"([a-z_]+)"', source))
    emitted |= {"attempt_on_unauthorized_decision", "refusal_requires_authorized_decision", "not_append_only"}
    covered = {f["expected_refusal"] for f in INVALID} | {"not_append_only"}
    assert emitted - covered == set(), emitted - covered
    readme = (CONTRACT_DIR / "README.md").read_text(encoding="utf-8")
    missing = sorted(c for c in emitted if f"`{c}`" not in readme)
    assert missing == [], missing


def test_f10_protection_unknown_member_is_refused_not_dropped():
    fx = next(f for f in INVALID if f["fixture_id"] == "undeclared-member-outside-extensions")
    (violation,) = cpj.validate(fx["document"])
    assert violation.code == "undeclared_member" and violation.path.endswith("injected_member")


def test_extensions_are_preserved_and_bound_into_the_digest():
    d = doc("extension-namespace-members-preserved")
    assert cpj.preserve(d) == d
    stripped = json.loads(json.dumps(d))
    del stripped["extensions"]
    assert cpj.canonical_bytes(stripped) != cpj.canonical_bytes(d)
    # Ignore-but-preserve: the verdict does not depend on extension members.
    assert cpj.validate(stripped) == []
    assert "extensions" not in cpj.known_view(d)
    assert "extensions" not in cpj.known_view(d)["decisions"][0]["binding"]["runtime_authority"]


def test_required_members_are_required_and_additions_stay_optional():
    base = doc("normal-attempted-acknowledged-applied")
    for member in ("contract", "contract_version", "run_id", "decisions", "attempts", "observations", "reconciliations",
                   "refusals", "resolution_checks", "closeouts", "input_time_floors"):
        d = copy.deepcopy(base)
        del d[member]
        assert codes(d) == ["schema_violation"], member
    # Optional members: producer, check_events and vocabulary_changes (omitted when empty), extensions.
    for member in ("producer", "check_events", "vocabulary_changes", "extensions"):
        d = copy.deepcopy(base)
        d.pop(member, None)
        if member == "check_events":
            for row in d["decisions"]:
                row.pop("reason_vocabulary_version", None)
                row["binding"].pop("runtime_authority", None)
        assert codes(d) == [], member


def test_journal_mode_is_all_or_nothing():
    base = doc("normal-attempted-acknowledged-applied")
    d = copy.deepcopy(base)
    del d["check_events"]
    assert set(codes(d)) == {"journal_missing"}
    plain = doc("no-journal-mode-normal")
    assert "check_events" not in plain and "reason_vocabulary_version" not in plain["decisions"][0]


# ------------------------------------------------------------------ delegation to the lifecycle contract

def test_delegated_lifecycle_version_is_pinned():
    assert cpj.DELEGATED_LIFECYCLE_VERSION == eal.CONTRACT_VERSION, "review the delegated attempt/journal rules"
    assert cpj.lifecycle().CONTRACT == "execution-attempt-lifecycle"


def test_shared_definitions_are_identical_to_the_lifecycle_contract():
    mine, theirs = cpj.load_schema()["$defs"], eal.load_schema()["$defs"]
    for name in ("extensions", "resolution_input", "resolution_check", "control_plane_attempt"):
        assert mine[name] == theirs[name], name
    narrowed = copy.deepcopy(mine["journal_event"])
    narrowed["properties"]["reason_vocabulary_version"] = theirs["journal_event"]["properties"]["reason_vocabulary_version"]
    assert narrowed == theirs["journal_event"], "journal_event may only narrow reason_vocabulary_version"


def test_delegated_rules_come_from_the_lifecycle_validator():
    for fx in INVALID:
        if fx["fixture_id"].startswith("delegated-"):
            projected = cpj._lifecycle_projection(fx["document"])
            assert [v.code for v in eal.validate(projected)] == [fx["expected_refusal"]], fx["fixture_id"]


def test_valid_run_projects_onto_valid_lifecycle_documents():
    for fx in VALID:
        assert eal.validate(cpj._lifecycle_projection(fx["document"])) == [], fx["fixture_id"]


def test_missing_lifecycle_contract_is_reported_not_skipped(monkeypatch, tmp_path):
    monkeypatch.setattr(cpj, "LIFECYCLE_PATH", tmp_path / "absent" / "validate.py")
    monkeypatch.setattr(cpj, "_LIFECYCLE", None)
    with pytest.raises(FileNotFoundError):
        cpj.validate(doc("normal-attempted-acknowledged-applied"))


def test_vendored_copies_run_with_the_lifecycle_contract_beside_them(tmp_path):
    vc = _load("cpj_vendor_tool", ROOT / "contracts" / "tools" / "vendor_contract.py")
    for name in ("execution-attempt-lifecycle", "control-plane-journal"):
        meta = vc.copy(name, tmp_path / name, "consumer", "L", "abc")
        assert vc.check(tmp_path / name) == [] and meta["contract"] == name
    vendored = _load("cpj_vendored_validate", tmp_path / "control-plane-journal" / "validate.py")
    for f in sorted((tmp_path / "control-plane-journal" / "fixtures" / "valid").glob("*.json")):
        assert vendored.validate(json.loads(f.read_text())["document"]) == [], f.name


# ------------------------------------------------------------------ rules that need more than one mutation

def test_decision_effect_identity_is_the_binding_commitment():
    d = doc("normal-attempted-acknowledged-applied")
    b = d["decisions"][0]["binding"]
    assert d["decisions"][0]["effect_id"] == cpj.commitment(
        {"proposal": b["proposal_commitment"], "grant_id": b["grant_id"], "grant_revision": b["grant_revision"]})


def test_rejected_reconciliations_are_retained_and_never_listed_as_observations():
    d = doc("observation-unavailable-rejected-reconciliation")
    assert d["observations"] == [] and d["reconciliations"][0]["observation_accepted"] is False
    # A rejected observation may carry malformed content; it is attributed evidence, not an accepted observation.
    d["reconciliations"][0]["observation"] = {"effect_id": "syn-other-effect", "state": "applied", "observed_at": "yesterday"}
    assert codes(d) == []


def test_partial_observation_is_accepted_with_result_hold():
    d = doc("partial-dispatch-partial-observation")
    last = d["reconciliations"][-1]
    assert last["observation"]["state"] == "partial" and last["result"] == "hold" and last["retry_eligible"] is False
    last["result"] = "applied"
    assert codes(d) == ["reconciliation_result_mismatch"]


def test_observations_keep_acceptance_order_within_an_effect():
    d = doc("lost-ack-unknown-then-closeout")
    assert [o["state"] for o in d["observations"]] == ["absent", "applied", "applied"]
    d["observations"] = list(reversed(d["observations"]))
    assert codes(d) == ["observations_mismatch"]


def test_unfinished_checks_are_valid_evidence_of_incomplete_evaluation():
    d = doc("interrupted-check-is-unfinished-evidence")
    assert cpj.validate(d) == []
    assert cpj.unfinished_checks(d) == [d["check_events"][0]["check_id"]]
    assert cpj.unfinished_checks(doc("normal-attempted-acknowledged-applied")) == []
    opened_only = copy.deepcopy(d)
    opened_only["check_events"] = opened_only["check_events"][:-1]
    assert cpj.validate(opened_only) == [] and len(cpj.unfinished_checks(opened_only)) == 1


def test_a_refusal_is_not_an_attempt():
    d = doc("effect-time-refusal")
    assert d["refusals"] and d["attempts"] == []


def test_held_decision_has_no_binding_and_no_attempts():
    d = doc("held-decision-journal-mode")
    assert d["decisions"][0]["result"] == "hold" and d["decisions"][0]["binding"] is None and d["attempts"] == []


def test_reconciled_existing_starts_no_second_lifecycle():
    d = doc("reconciled-existing-single-row")
    rows = [a for a in d["attempts"] if a["acknowledgement"] == {"reconciled_existing": True}]
    assert len(rows) == 1 and [a["status"] for a in d["attempts"]].count("attempted") == 1


# ------------------------------------------------------------------ succession (append-only, Exchange reliance)

def test_successive_exports_extend_the_earlier_one():
    lost = doc("lost-ack-unknown-then-closeout")
    earlier = copy.deepcopy(lost)
    earlier["closeouts"] = []
    earlier["reconciliations"] = lost["reconciliations"][:1]
    earlier["observations"] = lost["observations"][:1]
    earlier["attempts"] = lost["attempts"][:1]
    assert cpj.check_succession(lost, lost) == []
    assert cpj.check_succession(earlier, lost) == []
    assert [v.code for v in cpj.check_succession(lost, earlier)] == ["not_append_only"] * 4


def test_succession_refuses_rewritten_rows_and_regressed_floors():
    base = doc("normal-attempted-acknowledged-applied")
    rewritten = copy.deepcopy(base)
    rewritten["attempts"][0]["status"] = "unknown"
    assert [v.code for v in cpj.check_succession(base, rewritten)] == ["not_append_only"]
    regressed = copy.deepcopy(base)
    key = next(iter(regressed["input_time_floors"]))
    regressed["input_time_floors"][key] = "2000-01-01T00:00:00+00:00"
    assert [v.code for v in cpj.check_succession(base, regressed)] == ["not_append_only"]
    other_run = copy.deepcopy(base)
    other_run["run_id"] = "run-other"
    assert [v.code for v in cpj.check_succession(base, other_run)] == ["not_append_only"]


def test_unsupported_contract_version_is_refused_typed():
    d = doc("normal-attempted-acknowledged-applied")
    d["contract_version"] = "9.0.0"
    assert codes(d) == ["unsupported_contract_version"]


def test_schema_is_draft_2020_12_and_agrees_with_reference_validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = cpj.load_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    validator_cls = jsonschema.Draft202012Validator
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    for fx in VALID:
        assert not list(validator.iter_errors(fx["document"])), fx["fixture_id"]
    structural = {"undeclared_member", "invalid_extension_key", "schema_violation", "unknown_enum_value",
                  "unsupported_contract_version"}
    for fx in INVALID:
        errors = list(validator.iter_errors(fx["document"]))
        assert bool(errors) == (fx["expected_refusal"] in structural), fx["fixture_id"]
