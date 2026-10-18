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


OPERATION_IDENTITY = _load("cpj_oi_validate", ROOT / "contracts" / "operation-identity" / "validate.py")


def oi_codes(run):
    """Violations the operation-identity sidecar reports over a run record that carries the profile's three lists."""
    sidecar = {"contract": "operation-identity", "contract_version": "0.1.0-draft", "profile": "operation-identity/0.1",
               "producer": run["producer"], "run_id": run["run_id"], "operations": run.get("operations", []),
               "operation_renewals": run.get("operation_renewals", []), "attempt_joins": run.get("attempt_joins", [])}
    return [v.code for v in OPERATION_IDENTITY.validate(sidecar, run)]


@pytest.mark.parametrize("fx", [f for f in INVALID if "refused_by" not in f], ids=lambda f: f["fixture_id"])
def test_invalid_fixture_is_refused_with_stated_reason(fx):
    assert codes(fx["document"]) == [fx["expected_refusal"]], fx["reason"]


def test_a_fixture_refused_by_a_sidecar_says_so_and_is_accepted_by_this_contract():
    """The journal contract sees the operations rows as opaque, so a record whose ledger row disagrees with its decisions is
    valid here and refused by the operation-identity validator; such a fixture names the validator in `refused_by`."""
    sidecar = [f for f in INVALID if "refused_by" in f]
    assert [f["fixture_id"] for f in sidecar] == ["profile-op-grant-mismatch-held"]
    for fx in sidecar:
        assert fx["refused_by"] == "operation-identity"
        assert codes(fx["document"]) == []
        assert oi_codes(fx["document"]) == [fx["expected_refusal"]] == ["decision_operation_binding_mismatch"]
        assert "derived tamper" in fx["reason"].lower() and "Real producer run, unchanged" not in fx["reason"]


def test_no_valid_journal_fixture_has_a_ledger_row_that_disagrees_with_its_decisions():
    """Rows that carry other profiles' members are structurally outside the sidecar's closed set, so only the cross-record
    binding rule is swept over the valid set."""
    swept = 0
    for fx in VALID:
        if "operations" in fx["document"]:
            swept += 1
            assert "decision_operation_binding_mismatch" not in oi_codes(fx["document"]), fx["fixture_id"]
    assert swept >= 10


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
        assert _without_profile_members(mine[name], name) == theirs[name], name
    narrowed = _without_profile_members(mine["journal_event"], "journal_event")
    narrowed["properties"]["reason_vocabulary_version"] = theirs["journal_event"]["properties"]["reason_vocabulary_version"]
    assert narrowed == theirs["journal_event"], "journal_event may only narrow reason_vocabulary_version"


def _without_profile_members(definition, name=None):
    """A $defs object as the lifecycle contract sees it: the optional profile members and profile enum values removed (the table is
    cpj.PROFILE_OWNED / PROFILE_VALUES, which another test pins against the schema). What is left must be identical, so the profile
    members can only be additions."""
    d = copy.deepcopy(definition)
    name = name or next(n for n, v in cpj.load_schema()["$defs"].items() if v == definition)
    for member in cpj.PROFILE_OWNED.get(name, {}):
        del d["properties"][member]
    for key, owned in cpj.PROFILE_VALUES.items():
        obj, member = key.split(".")
        if obj == name:
            d["properties"][member]["enum"] = [v for v in d["properties"][member]["enum"] if v not in owned]
    return d


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
        if fx["fixture_id"] == "unpaired-surrogate-text":
            continue  # text validity is a validator rule; the portable schema does not state it
        errors = list(validator.iter_errors(fx["document"]))
        assert bool(errors) == (fx["expected_refusal"] in structural), fx["fixture_id"]


# ------------------------------------------------------------------ optional profile members (draft revision 2, decision 23)

PROFILE_VALID = [f for f in VALID if f["fixture_id"].startswith("profile-")]
PROFILE_INVALID = [f for f in INVALID if f["fixture_id"].startswith("profile-")]
PROFILES = {"operation-identity/0.1", "rule-revision/0.1", "freshness/0.1"}


def test_profile_fixtures_are_unchanged_producer_output_with_provenance():
    assert len(PROFILE_VALID) >= 30 and len(PROFILE_INVALID) >= 15
    for fx in PROFILE_VALID + PROFILE_INVALID:
        assert fx["provenance"]["control_plane_commit"] and fx["provenance"]["source"]
    for fx in PROFILE_VALID:
        assert fx["provenance"]["source"] == "control-plane-capture" and fx["provenance"]["scenario"]
    assert (CONTRACT_DIR / "provenance" / "capture_profile_stack.py").is_file()
    assert (CONTRACT_DIR / "provenance" / "build_fixtures.py").is_file()
    assert (CONTRACT_DIR / "provenance" / "mutate_invalid_fixtures.py").is_file()


def test_every_valid_profile_fixture_turns_a_profile_on_and_every_profile_is_covered():
    seen = set()
    for fx in PROFILE_VALID:
        present = cpj.profiles_present(fx["document"])
        # operation-identity on but the request carried no operation_id: the producer holds before writing any profile member,
        # so the record has the default shape (a real run, kept to show that "profile on" does not imply "member present")
        # terminal-revocation/0.1 adds a reason code only: its rows carry no profile member, so none is "present" (decision 33)
        assert present or fx["fixture_id"] == "profile-op-operation-id-missing-held" or fx["fixture_id"].startswith("profile-terminal-revocation-"), fx["fixture_id"]
        seen |= present
    assert seen == PROFILES
    stack = {f["fixture_id"]: cpj.profiles_present(f["document"]) for f in PROFILE_VALID if f["fixture_id"].startswith("profile-all-profiles-")}
    assert len(stack) == 3
    assert stack["profile-all-profiles-applied"] == stack["profile-all-profiles-expired-before-dispatch"] == PROFILES
    assert stack["profile-all-profiles-holder-inventory-missing"] == {"freshness/0.1", "rule-revision/0.1"}  # held before an operation row


def test_no_default_fixture_is_a_profile_record():
    """The default path is untouched: no earlier fixture owns a profile member, phase or read state."""
    for fx in VALID + INVALID:
        if not fx["fixture_id"].startswith("profile-") and fx["document"].get("contract_version") == "0.1.0-draft":
            try:
                assert cpj.profiles_present(fx["document"]) == set(), fx["fixture_id"]
            except (KeyError, TypeError, AttributeError):
                pass  # structurally broken on purpose; the structural rule refuses it before any profile rule


HARDENING_IDS = ("unpaired-surrogate-text", "trailing-line-break-digest", "non-ascii-digit-time", "trailing-line-break-time", "time-seven-fraction-digits")
HARDENING_PREFIX = ("profile-", "reasons-", *HARDENING_IDS)


def test_default_path_outcomes_are_exactly_those_of_the_validator_before_the_profile_members():
    """Every fixture that existed before draft revision 2 gets the same violations (code, path, message) it got at ODES 08afffe0
    (the journal contract was unchanged on main until this change)."""
    baseline = json.loads((CONTRACT_DIR / "fixtures" / "baseline-outcomes-pre-profile-members.json").read_text(encoding="utf-8"))["outcomes"]
    # revision 3 (decision 31) fixtures, prefix "reasons-", postdate the baseline and are covered by their own tests
    older = [f for f in VALID + INVALID if not f["fixture_id"].startswith(HARDENING_PREFIX)]
    assert len(baseline) == len(older) == 80
    for kind, group in (("valid", VALID), ("invalid", INVALID)):
        for fx in group:
            if not fx["fixture_id"].startswith(HARDENING_PREFIX):
                got = [[v.code, v.path, v.message] for v in cpj.validate(fx["document"])]
                assert got == baseline[f"{kind}/{fx['fixture_id']}"], fx["fixture_id"]


def test_profile_members_are_all_optional_and_documented():
    """The ownership table in validate.py agrees with the schema: every listed member is declared, optional, owned by a known profile
    and says so in its description; the schema has no keyword outside the plain set a minimal interpreter reads."""
    schema = cpj.load_schema()
    nodes = {"$": schema, **schema["$defs"]}
    found = 0
    for name, members in cpj.PROFILE_OWNED.items():
        node = nodes[name]
        for member, owners in members.items():
            found += 1
            assert member in node["properties"], (name, member)
            assert member not in node.get("required", []), (name, member)
            assert set(owners) <= PROFILES, (name, member)
            assert all(o in node["properties"][member]["description"] for o in owners), (name, member)
    assert found == 26
    for key, owned in cpj.PROFILE_VALUES.items():
        obj, member = key.split(".")
        spec = schema["$defs"][obj]["properties"][member]
        for value, owners in owned.items():
            assert value in spec["enum"] and set(owners) <= PROFILES and f"'{value}'" in schema["description"] and "freshness/0.1" in schema["description"]
    plain = {"$schema", "$id", "$defs", "$ref", "title", "description", "type", "enum", "const", "required", "properties",
             "additionalProperties", "items", "oneOf", "anyOf", "pattern", "minLength", "maxLength", "propertyNames"}

    def keywords(node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield k
                if k in {"properties", "$defs"}:
                    for sub in v.values():
                        yield from keywords(sub)
                elif k in {"items", "additionalProperties", "propertyNames"} or k in {"oneOf", "anyOf"}:
                    for sub in (v if isinstance(v, list) else [v]):
                        yield from keywords(sub)
    assert set(keywords(schema)) <= plain
    for name, node in nodes.items():
        assert node.get("additionalProperties", False) is False or name == "extensions"


def test_the_closed_set_stays_closed_with_profile_members_present():
    d = copy.deepcopy(next(f for f in PROFILE_VALID if f["fixture_id"] == "profile-op-normal")["document"])
    d["operations"][0]["extensions"] = {"x-ticket": 1}
    d["unknown_member"] = True
    assert codes(d) == ["undeclared_member"]


def test_a_member_dropped_from_a_profile_record_leaves_a_valid_default_record():
    """Profile members are optional: stripping every profile-owned member and value from a profile-on run that only adds members
    leaves a record the contract accepts (absent = valid)."""
    d = copy.deepcopy(next(f for f in PROFILE_VALID if f["fixture_id"] == "profile-nonce-bound-reads")["document"])
    for name in cpj.profile_members("$"):
        d.pop(name, None)
    for section, obj in (("decisions", "decision"), ("attempts", "control_plane_attempt"), ("resolution_checks", "resolution_check"),
                         ("refusals", "refusal"), ("check_events", "journal_event")):
        for row in d.get(section, []):
            for m in cpj.profile_members(obj):
                row.pop(m, None)
    for section, key in (("decisions", "resolution_inputs"), ("refusals", "resolution_inputs"), ("resolution_checks", "inputs")):
        for row in d[section]:
            for x in row[key]:
                x.pop("age_basis", None)
    for e in d["check_events"]:
        if e["input"]:
            e["input"].pop("age_basis", None)
    assert codes(d) == []
    assert cpj.profiles_present(d) == set()


def test_succession_covers_the_profile_lists_and_expired_is_terminal():
    base = copy.deepcopy(next(f for f in PROFILE_VALID if f["fixture_id"] == "profile-all-profiles-applied")["document"])
    assert cpj.check_succession(base, base) == []
    rewritten = copy.deepcopy(base)
    rewritten["operations"][0]["principal_id"] = "someone-else"
    assert [v.code for v in cpj.check_succession(base, rewritten)] == ["not_append_only"]
    dropped = copy.deepcopy(base)
    dropped["rule_revisions"] = []
    assert [v.code for v in cpj.check_succession(base, dropped)] == ["not_append_only"]
    expired = next(f for f in PROFILE_VALID if f["fixture_id"] == "profile-expired-before-dispatch")["document"]
    assert cpj.unfinished_checks(expired) == [], "an expired check is closed evidence, not an unfinished one"
    overdue = next(f for f in PROFILE_VALID if f["fixture_id"] == "profile-overdue-reported-not-closed")["document"]
    assert cpj.unfinished_checks(overdue) == [], "the owner completed it after the overdue report"


def test_profile_rules_do_not_relax_the_default_path():
    """The three relaxations key on a profile member being present; the same shapes without it are still refused."""
    d = copy.deepcopy(next(f for f in PROFILE_VALID if f["fixture_id"] == "profile-expired-then-retry-dispatches")["document"])
    for r in d["refusals"]:
        r.pop("deadline")
    assert codes(d) == ["second_attempt_for_effect"]
    d = copy.deepcopy(next(f for f in PROFILE_VALID if f["fixture_id"] == "profile-lease-unavailable-holds")["document"])
    d["decisions"][0].pop("evaluated_at")
    assert codes(d) == ["journal_missing"]


# ------------------------------------------------------------------ registry label 0.2 (draft revision 3, decision 31)

def test_registry_labels_and_the_zero_two_only_codes():
    assert cpj.VOCABULARY_0_1 == "runtime-authority-reasons/0.1" and cpj.VOCABULARY_0_2 == "runtime-authority-reasons/0.2"
    assert len(cpj.CODES_ADDED_IN_0_2) == 37  # 158 - 121, from the Control Plane's two registry files at 6b8fb627
    assert "grant_revocation_recorded" in cpj.CODES_ADDED_IN_0_2  # terminal-revocation/0.1
    assert {"holder_inventory_missing", "check_expired_before_dispatch", "operation_id_missing"} <= cpj.CODES_ADDED_IN_0_2
    enums = [cpj.load_schema()["$defs"][n]["properties"]["reason_vocabulary_version"]["enum"] for n in ("journal_event", "decision", "refusal")]
    assert all(e == [cpj.VOCABULARY_0_1, cpj.VOCABULARY_0_2] for e in enums), enums


def test_a_label_matches_the_codes_in_every_captured_row():
    """The producer rule: 0.2 only with a 0.2-only code present is not asserted (superset), but 0.1 never holds one."""
    swept = 0
    for fx in VALID:
        for section in ("decisions", "refusals", "check_events"):
            for row in fx["document"].get(section, []):
                if row.get("reason_vocabulary_version") == cpj.VOCABULARY_0_1:
                    assert not set(row["reasons"]) & cpj.CODES_ADDED_IN_0_2, fx["fixture_id"]
                    swept += 1
    assert swept > 50


def test_label_cases_on_a_held_decision():
    d = doc("reasons-0-2-label-with-a-0-2-code")
    assert codes(d) == []
    d["decisions"][0]["reason_vocabulary_version"] = cpj.VOCABULARY_0_1
    assert codes(d) == ["reason_label_mismatch"]
    d["decisions"][0]["reason_vocabulary_version"] = "runtime-authority-reasons/0.3"
    assert codes(d) == ["unknown_enum_value"]
    # a check event and a refusal row are held to the same rule
    e = doc("reasons-0-2-label-with-a-0-2-code")
    ev = next(x for x in e["check_events"] if x["reasons"])
    ev["reason_vocabulary_version"] = cpj.VOCABULARY_0_1
    assert codes(e) == ["reason_label_mismatch"]
    # a code outside both registries is not judged under either label
    f = doc("held-decision-journal-mode")
    assert codes(f) == []


def test_profile_fixtures_are_recaptured_producer_output_not_relabelled():
    """Decision 31-B: the profile fixtures were re-captured at Control Plane 3755c71a, which writes the registry labels itself; none
    carries a relabel note and the relabel script is gone from the build path."""
    assert not (CONTRACT_DIR / "provenance" / "relabel_vocabulary.py").exists()
    # the terminal-revocation fixtures were captured later, at 6b8fb627 (the older ones are deliberately not re-captured)
    for fx in PROFILE_VALID:
        commit = "6b8fb627" if fx["fixture_id"].startswith("profile-terminal-revocation-") else "3755c71a"
        assert "vocabulary_label" not in fx["provenance"], fx["fixture_id"]
        assert fx["provenance"]["control_plane_commit"] == commit, fx["fixture_id"]
        assert f"Real producer run, unchanged (Control Plane {commit}" in fx["reason"], fx["fixture_id"]
    for fx in PROFILE_INVALID:
        commit = "6b8fb627" if fx["fixture_id"].startswith("profile-terminal-revocation-") else "3755c71a"
        assert "vocabulary_label" not in fx["provenance"], fx["fixture_id"]
        assert fx["provenance"].get("control_plane_commit") == commit, fx["fixture_id"]
    tamper = next(f for f in PROFILE_INVALID if f["fixture_id"] == "profile-op-grant-mismatch-held")
    assert tamper["expected_outcome"] == "reject" and "derived tamper" in tamper["reason"].lower()


# ------------------------------------------------------------------ terminal-revocation/0.1 (Control Plane 6b8fb627)

TERMINAL = [f for f in PROFILE_VALID if f["fixture_id"].startswith("profile-terminal-revocation-")]


def test_terminal_revocation_needs_no_new_member_and_carries_the_zero_two_label():
    """The profile adds one reason code and no record member: its rows validate under the closed member sets as declared."""
    assert len(TERMINAL) == 3
    for fx in TERMINAL:
        assert codes(copy.deepcopy(fx["document"])) == [], fx["fixture_id"]
        assert cpj.profiles_present(fx["document"]) == set(), fx["fixture_id"]
    refusal = next(f for f in TERMINAL if f["fixture_id"].endswith("refused-after-recorded-revocation"))["document"]["refusals"][-1]
    assert refusal["reasons"] == ["grant_revocation_recorded"] and refusal["reason_vocabulary_version"] == cpj.VOCABULARY_0_2
    assert any(c["kind"] == "successor_grant_revision" for c in refusal["reopen_conditions"])


def test_terminal_revocation_code_under_a_0_1_label_is_refused():
    fx = next(f for f in PROFILE_INVALID if f["fixture_id"] == "profile-terminal-revocation-code-under-a-0-1-label")
    assert fx["expected_refusal"] == "reason_label_mismatch" and codes(copy.deepcopy(fx["document"])) == ["reason_label_mismatch"]
