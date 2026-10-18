"""Conformance tests for the effect-reversibility extension profile draft (0.1.0-draft).

Docs-and-fixtures only: this exercises contracts/effect-reversibility/validate.py against the golden fixtures and,
for the cross-document rules, against journal and bounded-deferral documents taken from their fixtures.
It does not import or alter the odes package and does not edit the journal contract.
"""
import copy
import importlib.util
import itertools
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "contracts" / "effect-reversibility"
JOURNAL_DIR = ROOT / "contracts" / "control-plane-journal"
DEFERRAL_DIR = ROOT / "contracts" / "bounded-deferral"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # validate.py defines a dataclass; register before exec
    spec.loader.exec_module(module)
    return module


er = _load("er_validate", CONTRACT_DIR / "validate.py")
cpj = _load("er_cpj_validate", JOURNAL_DIR / "validate.py")
bd = _load("er_bd_validate", DEFERRAL_DIR / "validate.py")


def _fixtures(kind):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((CONTRACT_DIR / "fixtures" / kind).glob("*.json"))]


VALID = _fixtures("valid")
INVALID = _fixtures("invalid")


def doc(fixture_id):
    return copy.deepcopy(next(f for f in VALID if f["fixture_id"] == fixture_id)["document"])


def codes(d, journal=None, deferrals=None):
    return [v.code for v in er.validate(d, journal, deferrals)]


def journal_fixture(name):
    return json.loads((JOURNAL_DIR / "fixtures" / "valid" / f"{name}.json").read_text(encoding="utf-8"))["document"]


def deferral_fixture(name):
    return json.loads((DEFERRAL_DIR / "fixtures" / "valid" / f"{name}.json").read_text(encoding="utf-8"))["document"]


# ------------------------------------------------------------------ fixtures

def test_fixture_sets_are_present_and_well_formed():
    assert len(VALID) >= 10 and len(INVALID) >= 30
    for fx in VALID + INVALID:
        assert fx["synthetic"] is True and fx["reason"].strip()
        assert fx["expected_outcome"] in {"accept", "reject"}
        assert fx["document"]["contract"] == "effect-reversibility"
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
    assert er.validate(fx["document"]) == []


@pytest.mark.parametrize("fx", INVALID, ids=lambda f: f["fixture_id"])
def test_invalid_fixture_is_refused_with_stated_reason(fx):
    assert [v.code for v in er.validate(fx["document"])] == [fx["expected_refusal"]], fx["reason"]


CONTEXT_CODES = {"journal_run_mismatch", "class_profile_journal_mismatch", "lost_ack_attempt_mismatch", "open_deferral_mismatch", "context_malformed"}


def test_every_rule_code_is_pinned_and_documented():
    source = (CONTRACT_DIR / "validate.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'_v\(\s*"([a-z_]+)"', source))
    emitted |= {"unsupported_contract_version", "undeclared_member", "unknown_enum_value", "invalid_extension_key", "schema_violation"}
    covered = {f["expected_refusal"] for f in INVALID} | CONTEXT_CODES
    assert emitted - covered == set(), emitted - covered
    assert CONTEXT_CODES <= emitted
    readme = (CONTRACT_DIR / "README.md").read_text(encoding="utf-8")
    missing = sorted(c for c in emitted if f"`{c}`" not in readme)
    assert missing == [], missing


# ------------------------------------------------------------------ structure and extension model

def test_unknown_member_is_refused_not_dropped():
    fx = next(f for f in INVALID if f["fixture_id"] == "undeclared-member")
    (violation,) = er.validate(fx["document"])
    assert violation.code == "undeclared_member" and violation.path.endswith("injected")


def test_extensions_are_preserved_and_bound_into_the_digest():
    d = doc("extension-namespace-members-preserved")
    assert er.preserve(d) == d
    stripped = json.loads(json.dumps(d))
    del stripped["extensions"]
    assert er.canonical_bytes(stripped) != er.canonical_bytes(d)
    assert er.validate(stripped) == []
    assert "extensions" not in er.known_view(d) and "extensions" not in er.known_view(d)["snapshot_uses"][0]


def test_required_members_are_required_and_records_stay_optional():
    base = doc("class-profiles-three-effect-classes")
    for member in ("contract", "contract_version", "class_profiles"):
        d = copy.deepcopy(base)
        del d[member]
        assert [v.code for v in er.validate(d)] == ["schema_violation"], member
    for member in ("class_id", "irreversible", "max_status_age_seconds", "x-effect-class", "x-reversibility"):
        d = copy.deepcopy(base)
        del d["class_profiles"][0][member]
        assert [v.code for v in er.validate(d)] == ["schema_violation"], member
    for member in ("reversibility", "reversible_until", "reversal_cost", "reads_protected_data", "counterparty_observable"):
        d = copy.deepcopy(base)
        del d["class_profiles"][0]["x-reversibility"][member]
        assert [v.code for v in er.validate(d)] == ["schema_violation"], member
    for member in ("producer", "run_id", "snapshot_uses", "dispatches", "lost_acks"):
        d = copy.deepcopy(base)
        d.pop(member, None)
        assert er.validate(d) == [], member


# ------------------------------------------------------------------ layering: nothing is added to the core

def test_profile_adds_nothing_to_the_core():
    journal_schema = json.loads((JOURNAL_DIR / "schema.json").read_text(encoding="utf-8"))
    assert journal_schema["$defs"]["decision"]["properties"]["result"]["enum"] == ["authorized", "hold"]
    for path in list((ROOT / "schema").rglob("*")) + [JOURNAL_DIR / "schema.json", JOURNAL_DIR / "validate.py", JOURNAL_DIR / "README.md"]:
        if path.is_file():
            assert "effect-reversibility" not in path.read_text(encoding="utf-8", errors="ignore"), path


def test_layered_journal_version_is_pinned():
    assert er.LAYERED_ON_JOURNAL_VERSION == cpj.CONTRACT_VERSION, "review the profile against the new journal version"


def test_the_two_members_ride_on_the_journals_open_action_class_without_changing_the_journal_contract():
    journal = journal_fixture("held-decision-journal-mode")
    assert cpj.validate(journal) == []
    profile = doc("class-profiles-three-effect-classes")["class_profiles"][2]  # blocking, irreversible
    for event in journal["check_events"]:
        event["action_class"] = {"class_id": "synthetic-irreversible", "irreversible": True, "max_status_age_seconds": 60,
                                 "on_unreadable": "refuse", "x-effect-class": profile["x-effect-class"],
                                 "x-reversibility": profile["x-reversibility"]}
    assert cpj.validate(journal) == []  # the core accepts them untouched
    (found,) = er.extract_class_profiles(journal)
    d = {"contract": "effect-reversibility", "contract_version": "0.1.0-draft", "run_id": "run-1", "class_profiles": [found]}
    assert er.validate(d, journal) == []


# ------------------------------------------------------------------ properties of the rules

def test_class_value_matrix_is_consistent_for_every_combination():
    for value, protected, observable in itertools.product(("irreversible", "reversible_until", "reversible_at_cost"), (False, True), (False, True)):
        r = {"reversibility": value, "reversible_until": "2026-10-06T19:00:00+00:00" if value == "reversible_until" else None,
             "reversal_cost": {"description": "c"} if value == "reversible_at_cost" else None,
             "reads_protected_data": protected, "counterparty_observable": observable}
        d = {"contract": "effect-reversibility", "contract_version": "0.1.0-draft",
             "class_profiles": [{"class_id": "c", "irreversible": value == "irreversible", "max_status_age_seconds": 60,
                                 "x-effect-class": "stageable", "x-reversibility": r}]}
        expected = set()
        if protected and value != "irreversible":
            expected.add("protected_read_not_irreversible")
        if not observable and value != "irreversible":
            expected.add("unobservable_not_strict")
        assert set(codes(d)) == expected, (value, protected, observable)


def _dispatch_doc(effect_class, phase, open_ids):
    base = doc("class-profiles-three-effect-classes")
    cls = {"stageable": "cls-stage", "stallable": "cls-stall", "blocking": "cls-block"}[effect_class]
    base["dispatches"] = [{"dispatch_id": "d", "effect_id": "e", "proposal_commitment": "sha256:" + "1" * 64, "class_id": cls,
                           "effect_class": effect_class, "phase": phase, "dispatched_at": "2026-10-05T19:00:10+00:00",
                           "open_deferral_ids": open_ids}]
    return base


def test_blocking_is_never_sent_while_a_defer_is_open_and_observable_phases_wait_for_release():
    phases = ["stage", "start_stalled", "release_stalled", "commit", "send"]
    for effect_class, phase, is_open in itertools.product(("stageable", "stallable", "blocking"), phases, (False, True)):
        got = codes(_dispatch_doc(effect_class, phase, ["x"] if is_open else []))
        if phase not in er.CLASS_PHASES[effect_class]:
            assert got == ["phase_class_mismatch"]
        elif not is_open:
            assert got == []
        elif effect_class == "blocking":
            assert got == ["blocking_sent_while_deferred"]
        elif phase in er.OBSERVABLE_PHASES:
            assert got == ["observable_while_deferred"]
        else:
            assert got == []


def test_lost_ack_classification_is_total_and_never_retry_eligible():
    for phase, (classification, action) in er.LOST_ACK.items():
        assert classification == ("no_external_effect" if phase in {"stage", "start_stalled"} else "external_effect_possible")
        assert (action == "reconcile_by_observation") == (classification == "external_effect_possible")
    assert set(er.LOST_ACK) == {"stage", "start_stalled", "release_stalled", "commit", "send"}
    schema = er.load_schema()
    assert schema["$defs"]["lost_ack"]["properties"]["retry_eligible"] == {"const": False}


def test_cached_snapshots_are_accepted_only_for_reversible_classes_within_the_window_and_age():
    base = doc("cached-snapshot-reversible-class-within-age")
    assert codes(base) == []
    for cls_id, expect in (("cls-stage", []), ("cls-stall", []), ("cls-block", ["cache_on_irreversible_class"]),
                           ("cls-read", ["cache_on_irreversible_class"]), ("cls-unobs", ["cache_on_irreversible_class"])):
        d = copy.deepcopy(base)
        d["snapshot_uses"][0]["class_id"] = cls_id
        assert codes(d) == expect, cls_id
    # The age bound is inclusive.
    d = copy.deepcopy(base)
    d["snapshot_uses"][0]["snapshot"]["observed_at"] = "2026-10-05T18:59:30+00:00"
    assert codes(d) == []
    d["snapshot_uses"][0]["snapshot"]["observed_at"] = "2026-10-05T18:59:29+00:00"
    assert codes(d) == ["snapshot_stale"]


def test_a_recorded_closure_overrides_cache_and_live_reads_alike():
    for basis, cls_id in (("cached_snapshot", "cls-stage"), ("live_read", "cls-block")):
        d = doc("recorded-closure-overrides-cached-open")
        u = d["snapshot_uses"][0]
        u.update(basis=basis, class_id=cls_id, effective_status="open")
        assert codes(d) == ["recorded_closure_overridden"], basis
        u["effective_status"] = "closed"
        assert codes(d) == [], basis
    # A closure recorded after the use does not yet override it.
    d = doc("recorded-closure-overrides-cached-open")
    d["snapshot_uses"][0].update(effective_status="open")
    d["snapshot_uses"][0]["recorded_closure"] = {"closed_at": "2026-10-05T19:00:35+00:00", "recorded_at": "2026-10-05T19:00:40+00:00"}
    assert codes(d) == []


# ------------------------------------------------------------------ journal and deferral context

def test_class_must_match_the_action_class_in_the_run_record():
    journal = journal_fixture("held-decision-journal-mode")
    d = {"contract": "effect-reversibility", "contract_version": "0.1.0-draft", "run_id": "run-1",
         "class_profiles": [copy.deepcopy(doc("class-profiles-three-effect-classes")["class_profiles"][2])]}
    d["class_profiles"][0]["class_id"] = "synthetic-irreversible"
    assert codes(d, journal) == []
    d["class_profiles"][0]["max_status_age_seconds"] = 30
    assert codes(d, journal) == ["class_profile_journal_mismatch"]
    d["class_profiles"][0]["max_status_age_seconds"] = 60
    d["run_id"] = "run-2"
    assert codes(d, journal) == ["journal_run_mismatch"]


def test_lost_ack_names_an_attempt_whose_last_row_is_unknown():
    journal = journal_fixture("lost-ack-unknown-then-closeout")
    d = doc("lost-ack-send-irreversible-reconcile")
    d["lost_acks"][0]["effect_id"] = journal["attempts"][0]["effect_id"]
    assert codes(d, journal) == []
    d["lost_acks"][0]["attempt_id"] = "syn-attempt-9"
    assert codes(d, journal) == ["lost_ack_attempt_mismatch"]
    d["lost_acks"][0]["attempt_id"] = "syn-attempt-1"
    ok = journal_fixture("normal-attempted-acknowledged-applied")
    d["lost_acks"][0]["effect_id"] = ok["attempts"][0]["effect_id"]
    assert codes(d, ok) == ["lost_ack_attempt_mismatch"], "an acknowledged attempt lost no acknowledgement"


def _deferral_dispatch(open_ids, at, deferrals):
    d = doc("blocking-send-with-no-open-deferral")
    d["dispatches"][0].update(proposal_commitment=deferrals["deferrals"][0]["proposal_commitment"], dispatched_at=at, open_deferral_ids=open_ids)
    return d


def test_open_deferrals_at_dispatch_are_computed_from_the_deferral_document():
    still_open = deferral_fixture("open-deferral-within-deadline")
    assert bd.validate(still_open) == []
    assert codes(_deferral_dispatch(["syn-deferral-1"], "2026-10-05T19:00:10+00:00", still_open), deferrals=still_open) == ["blocking_sent_while_deferred"]
    assert codes(_deferral_dispatch([], "2026-10-05T19:00:10+00:00", still_open), deferrals=still_open) == ["open_deferral_mismatch"]
    released = deferral_fixture("released-by-resolver-before-deadline")
    assert bd.validate(released) == []
    # Open until the release is resolved (19:00:20), exclusive; sent at the release instant is after it.
    assert codes(_deferral_dispatch([], "2026-10-05T19:00:20+00:00", released), deferrals=released) == []
    assert codes(_deferral_dispatch([], "2026-10-05T19:00:10+00:00", released), deferrals=released) == ["open_deferral_mismatch"]
    assert codes(_deferral_dispatch(["syn-deferral-1"], "2026-10-05T19:00:20+00:00", released), deferrals=released) == ["blocking_sent_while_deferred", "open_deferral_mismatch"]
    refused = deferral_fixture("refused-by-resolver")
    assert codes(_deferral_dispatch([], "2026-10-05T19:00:30+00:00", refused), deferrals=refused) == []


# ------------------------------------------------------------------ vendoring

def test_vendored_copy_runs_standalone(tmp_path):
    vc = _load("er_vendor_tool", ROOT / "contracts" / "tools" / "vendor_contract.py")
    meta = vc.copy("effect-reversibility", tmp_path / "effect-reversibility", "consumer", "L", "abc")
    assert vc.check(tmp_path / "effect-reversibility") == [] and meta["contract"] == "effect-reversibility"
    assert meta["contract_version"] == "0.1.0-draft"
    vendored = _load("er_vendored_validate", tmp_path / "effect-reversibility" / "validate.py")
    for f in sorted((tmp_path / "effect-reversibility" / "fixtures" / "valid").glob("*.json")):
        assert vendored.validate(json.loads(f.read_text())["document"]) == [], f.name


def test_unsupported_contract_version_is_refused_typed():
    d = doc("class-profiles-three-effect-classes")
    d["contract_version"] = "9.0.0"
    assert codes(d) == ["unsupported_contract_version"]


def test_schema_is_draft_2020_12_and_agrees_with_reference_validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = er.load_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    cls = jsonschema.Draft202012Validator
    cls.check_schema(schema)
    validator = cls(schema)
    for fx in VALID:
        assert not list(validator.iter_errors(fx["document"])), fx["fixture_id"]
    structural = {"undeclared_member", "invalid_extension_key", "schema_violation", "unknown_enum_value", "unsupported_contract_version"}
    for fx in INVALID:
        if fx["fixture_id"] == "unpaired-surrogate-text":
            continue  # text validity is a validator rule; the portable schema does not state it
        errors = list(validator.iter_errors(fx["document"]))
        assert bool(errors) == (fx["expected_refusal"] in structural), fx["fixture_id"]


def test_deferral_document_must_describe_the_same_run_as_the_profile_and_the_run_record():
    still_open = deferral_fixture("open-deferral-within-deadline")
    d = _deferral_dispatch(["syn-deferral-1"], "2026-10-05T19:00:10+00:00", still_open)
    d["run_id"] = still_open["run_id"] + "-other"
    assert "journal_run_mismatch" in codes(d, deferrals=still_open)
    # No run_id on the profile document: the run record and the deferral document are still compared.
    d.pop("run_id")
    journal = journal_fixture("held-decision-journal-mode")
    if journal["run_id"] != still_open["run_id"]:
        assert "journal_run_mismatch" in codes(d, journal, still_open)


@pytest.mark.parametrize("bad", [5, [], "x", {"attempts": 5}, {"run_id": "run-1", "attempts": [5], "check_events": [7]}, {"run_id": "run-1", "check_events": 3}])
def test_malformed_journal_context_is_a_typed_violation_not_an_exception(bad):
    d = doc("lost-ack-send-irreversible-reconcile")
    assert "context_malformed" in codes(d, bad) or "journal_run_mismatch" in codes(d, bad)


@pytest.mark.parametrize("bad", [5, {"deferrals": 5}, {"run_id": "run-1", "deferrals": [5]}, {"run_id": "run-1", "deferrals": [{}]}])
def test_malformed_deferral_context_is_a_typed_violation_not_an_exception(bad):
    d = doc("blocking-send-with-no-open-deferral")
    found = codes(d, deferrals=bad)
    assert "context_malformed" in found or "journal_run_mismatch" in found
