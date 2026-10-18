"""Conformance tests for the bounded-deferral extension profile draft (0.1.0-draft).

Docs-and-fixtures only: this exercises contracts/bounded-deferral/validate.py against the golden fixtures and,
for the cross-document rules, against journal documents taken from the control-plane-journal fixtures.
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
CONTRACT_DIR = ROOT / "contracts" / "bounded-deferral"
JOURNAL_DIR = ROOT / "contracts" / "control-plane-journal"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # validate.py defines a dataclass; register before exec
    spec.loader.exec_module(module)
    return module


bd = _load("bd_validate", CONTRACT_DIR / "validate.py")
cpj = _load("bd_cpj_validate", JOURNAL_DIR / "validate.py")


def _fixtures(kind):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((CONTRACT_DIR / "fixtures" / kind).glob("*.json"))]


VALID = _fixtures("valid")
INVALID = _fixtures("invalid")


def doc(fixture_id):
    return copy.deepcopy(next(f for f in VALID if f["fixture_id"] == fixture_id)["document"])


def codes(d, journal=None):
    return [v.code for v in bd.validate(d, journal)]


def journal_fixture(name):
    return json.loads((JOURNAL_DIR / "fixtures" / "valid" / f"{name}.json").read_text(encoding="utf-8"))["document"]


def held_journal():
    """Journal mode run: one held decision (syn-decision-1), action class synthetic-irreversible, bound 60 s."""
    return journal_fixture("held-decision-journal-mode")


def aligned_release(d):
    """The released fixture re-timed to the frozen clock of the mixed journal (decision and attempt at 19:00:00)."""
    x = d["deferrals"][0]
    x.update(decision_id="syn-held-1", released_decision_id="syn-decision-1", resolved_at="2026-10-05T19:00:00+00:00")
    x["responses"][0]["received_at"] = "2026-10-05T19:00:00+00:00"
    return d


def mixed_journal():
    """A plain run record with an authorized decision, its attempts and observations, and a held decision for the
    same proposal (the two fixtures share the proposal commitment and the frozen clock)."""
    j = journal_fixture("no-journal-mode-normal")
    held = copy.deepcopy(journal_fixture("held-decision-journal-mode")["decisions"][0])
    held["decision_id"] = "syn-held-1"
    held.pop("reason_vocabulary_version")
    j["decisions"].append(held)
    return j


# ------------------------------------------------------------------ fixtures

def test_fixture_sets_are_present_and_well_formed():
    assert len(VALID) >= 10 and len(INVALID) >= 30
    for fx in VALID + INVALID:
        assert fx["synthetic"] is True and fx["reason"].strip()
        assert fx["expected_outcome"] in {"accept", "reject"}
        assert fx["document"]["contract"] == "bounded-deferral"
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
    assert bd.validate(fx["document"]) == []


@pytest.mark.parametrize("fx", INVALID, ids=lambda f: f["fixture_id"])
def test_invalid_fixture_is_refused_with_stated_reason(fx):
    assert codes(fx["document"]) == [fx["expected_refusal"]], fx["reason"]


def test_required_valid_cases_exist():
    ids = {f["fixture_id"] for f in VALID}
    assert {"open-deferral-within-deadline", "released-by-resolver-before-deadline", "refused-by-resolver",
            "expired-deferral-refused-with-notice", "resolver-timeout-refused", "resolver-garbage-refused",
            "resolver-error-refused", "policy-refused-release-attempt-ignored", "late-release-after-deadline-refused",
            "extension-namespace-members-preserved"} <= ids


# Codes that need the journal run record; pinned by the tests below, not by single-document fixtures.
CONTEXT_CODES = {"journal_run_mismatch", "deferral_dangling_decision", "deferral_decision_not_held", "deferral_effect_mismatch",
                 "deferral_proposal_mismatch", "deferral_reasons_not_held", "deferral_before_decision", "deferral_max_age_mismatch",
                 "release_decision_unauthorized", "release_decision_before_release", "effect_attempted_before_release",
                 "effect_attempted_without_release", "refused_effect_observed"}


def test_every_rule_code_is_pinned_and_documented():
    source = (CONTRACT_DIR / "validate.py").read_text(encoding="utf-8")
    derived = {"release_overrides_refusal", "expired_deferral_not_refused", "refusal_overridden", "resolver_failure_released", "outcome_mismatch"}
    assert all(f'"{c}"' in source for c in derived)
    emitted = set(re.findall(r'_v\(\s*"([a-z_]+)"', source)) | derived
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
    (violation,) = bd.validate(fx["document"])
    assert violation.code == "undeclared_member" and violation.path.endswith("injected")


def test_extensions_are_preserved_and_bound_into_the_digest():
    d = doc("extension-namespace-members-preserved")
    assert bd.preserve(d) == d
    stripped = json.loads(json.dumps(d))
    del stripped["extensions"]
    assert bd.canonical_bytes(stripped) != bd.canonical_bytes(d)
    assert bd.validate(stripped) == []
    assert "extensions" not in bd.known_view(d) and "extensions" not in bd.known_view(d)["deferrals"][0]


def test_required_members_are_required():
    base = doc("open-deferral-within-deadline")
    for member in ("contract", "contract_version", "run_id", "evaluated_at", "deferrals"):
        d = copy.deepcopy(base)
        del d[member]
        assert codes(d) == ["schema_violation"], member
    for member in ("deferral_id", "decision_id", "effect_id", "proposal_commitment", "action_class_id", "policy", "opened_at",
                   "max_age_seconds", "deadline", "outcome", "responses", "resolved_at", "refusal_reason", "released_decision_id", "effect"):
        d = copy.deepcopy(base)
        del d["deferrals"][0][member]
        assert codes(d) == ["schema_violation"], member
    d = copy.deepcopy(base)
    del d["producer"]
    assert codes(d) == []


def test_max_age_must_be_a_positive_integer():
    for bad in (0, -5, 1.5, "60", None):
        d = doc("open-deferral-within-deadline")
        d["deferrals"][0]["max_age_seconds"] = bad
        assert codes(d)[:1] == ["schema_violation"], bad


# ------------------------------------------------------------------ the fail-closed property

def _deferral(verdict, responses, deadline_s=60):
    d = doc("open-deferral-within-deadline")["deferrals"][0]
    d["policy"] = {"policy_verdict": verdict, "deferred_reasons": ["a_reason"], "refusal_reasons": [] if verdict == "defer" else ["b_reason"]}
    d["responses"] = [{"response_id": f"r{i}", "resolver_id": "x", "received_at": at, "kind": kind} for i, (kind, at) in enumerate(responses)]
    return d


def test_release_is_derived_only_when_policy_deferred_and_the_first_response_is_an_in_time_release():
    t0 = "2026-10-05T19:00:%02d+00:00"
    kinds = ["release", "refuse", "timeout", "unparseable", "error"]
    times = [10, 59, 60, 61, 120]
    evaluated = bd.aware("2026-10-05T19:03:00+00:00")
    for verdict in ("defer", "refuse"):
        for n in (0, 1, 2):
            for combo in itertools.product(itertools.product(kinds, times), repeat=n):
                d = _deferral(verdict, [(k, t0 % s if s < 60 else f"2026-10-05T19:{s // 60:02d}:{s % 60:02d}+00:00") for k, s in combo])
                outcome, reason = bd.derive_outcome(d, evaluated)
                first = min(combo, key=lambda c: c[1]) if combo else None
                expect_release = verdict == "defer" and first is not None and first[0] == "release" and first[1] <= 60
                assert (outcome == "released") == expect_release, (verdict, combo)
                assert outcome != "deferred", "evaluated well after the deadline: nothing stays open"
                assert (reason is None) == (outcome == "released")


def test_nothing_is_derived_open_after_the_deadline_and_open_before_it_only_without_responses():
    d = _deferral("defer", [])
    assert bd.derive_outcome(d, bd.aware("2026-10-05T19:01:00+00:00")) == ("deferred", None)  # the deadline is inclusive
    assert bd.derive_outcome(d, bd.aware("2026-10-05T19:01:01+00:00")) == ("refused", "deadline_expired")


def test_the_contract_has_no_deny_outcome_and_no_default_release():
    schema = bd.load_schema()
    assert schema["$defs"]["deferral"]["properties"]["outcome"]["enum"] == ["deferred", "released", "refused"]
    assert "released" not in schema["$defs"]["deferral"]["properties"]["refusal_reason"]["oneOf"][0]["enum"]


# ------------------------------------------------------------------ layering on the journal contract

def test_profile_adds_nothing_to_the_core():
    journal_schema = json.loads((JOURNAL_DIR / "schema.json").read_text(encoding="utf-8"))
    assert journal_schema["$defs"]["decision"]["properties"]["result"]["enum"] == ["authorized", "hold"]
    for path in list((ROOT / "schema").rglob("*")) + [JOURNAL_DIR / "schema.json", JOURNAL_DIR / "validate.py", JOURNAL_DIR / "README.md"]:
        if path.is_file():
            assert "bounded-deferral" not in path.read_text(encoding="utf-8", errors="ignore"), path


def test_layered_journal_version_is_pinned():
    assert bd.LAYERED_ON_JOURNAL_VERSION == cpj.CONTRACT_VERSION, "review the deferral rules against the new journal version"


def test_a_deferral_is_a_bounded_hold_over_a_conforming_journal():
    journal = held_journal()
    assert cpj.validate(journal) == []
    assert codes(doc("open-deferral-within-deadline"), journal) == []
    refused = doc("expired-deferral-refused-with-notice")
    assert codes(refused, journal) == []


def test_released_deferral_is_valid_only_with_an_authorized_decision_for_the_same_proposal():
    journal = mixed_journal()
    assert cpj.validate(journal) == []
    d = aligned_release(doc("released-by-resolver-before-deadline"))
    assert codes(d, journal) == []
    d["deferrals"][0]["released_decision_id"] = "syn-held-1"
    assert codes(d, journal) == ["release_decision_unauthorized", "effect_attempted_without_release"]


CONTEXT_CASES = {
    "journal_run_mismatch": (held_journal, "open-deferral-within-deadline", lambda d: d.__setitem__("run_id", "run-2")),
    "deferral_dangling_decision": (held_journal, "open-deferral-within-deadline", lambda d: d["deferrals"][0].__setitem__("decision_id", "nope")),
    "deferral_decision_not_held": (mixed_journal, "open-deferral-within-deadline", lambda d: d["deferrals"][0].__setitem__("decision_id", "syn-decision-1")),
    "deferral_effect_mismatch": (held_journal, "open-deferral-within-deadline", lambda d: d["deferrals"][0].__setitem__("effect_id", "sha256:" + "1" * 64)),
    "deferral_proposal_mismatch": (held_journal, "open-deferral-within-deadline", lambda d: d["deferrals"][0].__setitem__("proposal_commitment", "sha256:" + "2" * 64)),
    "deferral_reasons_not_held": (held_journal, "open-deferral-within-deadline", lambda d: d["deferrals"][0]["policy"].__setitem__("deferred_reasons", ["status_unreadable"])),
    "deferral_before_decision": (held_journal, "open-deferral-within-deadline", lambda d: (
        d["deferrals"][0].update(opened_at="2026-10-05T18:58:00+00:00", deadline="2026-10-05T18:59:00+00:00"), d.__setitem__("evaluated_at", "2026-10-05T18:58:30+00:00"))),
    "deferral_max_age_mismatch": (held_journal, "open-deferral-within-deadline", lambda d: d["deferrals"][0].update(max_age_seconds=30, deadline="2026-10-05T19:00:30+00:00")),
    "release_decision_unauthorized": (mixed_journal, "released-by-resolver-before-deadline", lambda d: d["deferrals"][0].__setitem__("released_decision_id", "syn-held-1")),
    "release_decision_before_release": (mixed_journal, "released-by-resolver-before-deadline", lambda d: d["deferrals"][0]["responses"][0].__setitem__("received_at", "2026-10-05T19:00:30+00:00") or d["deferrals"][0].__setitem__("resolved_at", "2026-10-05T19:00:30+00:00")),
    "effect_attempted_before_release": (mixed_journal, "released-by-resolver-before-deadline", lambda d: d["deferrals"][0]["responses"][0].__setitem__("received_at", "2026-10-05T19:00:30+00:00") or d["deferrals"][0].__setitem__("resolved_at", "2026-10-05T19:00:30+00:00")),
    "effect_attempted_without_release": (mixed_journal, "open-deferral-within-deadline", lambda d: None),
    "refused_effect_observed": (mixed_journal, "refused-by-resolver", lambda d: None),
}


@pytest.mark.parametrize("code", sorted(CONTEXT_CASES))
def test_journal_context_rule(code):
    make_journal, fixture, mutate = CONTEXT_CASES[code]
    d = doc(fixture)
    if fixture == "released-by-resolver-before-deadline":
        aligned_release(d)
    elif make_journal is mixed_journal and code != "deferral_decision_not_held":
        d["deferrals"][0]["decision_id"] = "syn-held-1"
    mutate(d)
    assert code in codes(d, make_journal()), code


def test_every_context_code_has_a_case():
    assert set(CONTEXT_CASES) == CONTEXT_CODES


def test_refused_effect_is_never_attempted_or_observed_in_the_run_record():
    journal = mixed_journal()
    d = doc("refused-by-resolver")
    d["deferrals"][0]["decision_id"] = "syn-held-1"
    assert set(codes(d, journal)) == {"effect_attempted_without_release", "refused_effect_observed"}
    journal["attempts"], journal["observations"] = [], []
    assert codes(d, journal) == []


def test_notice_cannot_carry_the_grant_identifier_from_the_run_record():
    journal = mixed_journal()
    journal["decisions"][0]["binding"]["grant_id"] = "g-4711-private"
    d = doc("expired-deferral-refused-with-notice")
    d["deferrals"][0].update(decision_id="syn-held-1")
    d["deferrals"][0]["refusal_notice"]["statement"] = "The action for g-4711-private did not occur."
    assert codes(d) == []  # not recognisable without the run record
    assert "refusal_notice_private_state" in codes(d, journal)


# ------------------------------------------------------------------ vendoring

def test_vendored_copy_runs_standalone(tmp_path):
    vc = _load("bd_vendor_tool", ROOT / "contracts" / "tools" / "vendor_contract.py")
    meta = vc.copy("bounded-deferral", tmp_path / "bounded-deferral", "consumer", "L", "abc")
    assert vc.check(tmp_path / "bounded-deferral") == [] and meta["contract"] == "bounded-deferral"
    assert meta["contract_version"] == "0.1.0-draft"
    vendored = _load("bd_vendored_validate", tmp_path / "bounded-deferral" / "validate.py")
    for f in sorted((tmp_path / "bounded-deferral" / "fixtures" / "valid").glob("*.json")):
        assert vendored.validate(json.loads(f.read_text())["document"]) == [], f.name


def test_unsupported_contract_version_is_refused_typed():
    d = doc("open-deferral-within-deadline")
    d["contract_version"] = "9.0.0"
    assert codes(d) == ["unsupported_contract_version"]


def test_schema_is_draft_2020_12_and_agrees_with_reference_validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = bd.load_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    cls = jsonschema.Draft202012Validator
    cls.check_schema(schema)
    validator = cls(schema)
    for fx in VALID:
        assert not list(validator.iter_errors(fx["document"])), fx["fixture_id"]
    structural = {"undeclared_member", "invalid_extension_key", "schema_violation", "unknown_enum_value", "unsupported_contract_version"}
    for fx in INVALID:
        errors = list(validator.iter_errors(fx["document"]))
        assert bool(errors) == (fx["expected_refusal"] in structural), fx["fixture_id"]
