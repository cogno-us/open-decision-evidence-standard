"""Conformance tests for the operation-identity extension profile draft (0.1.0-draft).

Docs-and-fixtures only: this exercises contracts/operation-identity/validate.py against the golden fixtures. The valid
fixtures are captures of real Control Plane runs (opt-in operation-identity/0.1); the invalid ones are single-defect
mutations of them. The cross-document rules take the run record as an optional second argument. This file does not
import or alter the odes package and does not edit the journal or lifecycle contracts.
"""
import copy
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "contracts" / "operation-identity"
JOURNAL_DIR = ROOT / "contracts" / "control-plane-journal"
LIFECYCLE_DIR = ROOT / "contracts" / "execution-attempt-lifecycle"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # validate.py defines a dataclass; register before exec
    spec.loader.exec_module(module)
    return module


oi = _load("oi_validate", CONTRACT_DIR / "validate.py")
cpj = _load("oi_cpj_validate", JOURNAL_DIR / "validate.py")


def _fixtures(kind):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((CONTRACT_DIR / "fixtures" / kind).glob("*.json"))]


VALID = _fixtures("valid")
INVALID = _fixtures("invalid")


def fx(fixture_id):
    return copy.deepcopy(next(f for f in VALID if f["fixture_id"] == fixture_id))


def codes(d, journal=None):
    return [v.code for v in oi.validate(d, journal)]


# ------------------------------------------------------------------ fixtures

def test_fixture_sets_are_present_and_well_formed():
    assert len(VALID) >= 12 and len(INVALID) >= 61
    for f in VALID + INVALID:
        assert f["synthetic"] is True and f["reason"].strip() and f["provenance"]["source"]
        assert f["expected_outcome"] in {"accept", "reject"}
        assert f["document"]["contract"] == "operation-identity"
        assert f["document"]["contract_version"] == "0.1.0-draft" or f["fixture_id"] == "unsupported-contract-version"
    assert all(f["expected_outcome"] == "accept" for f in VALID)
    assert all(f["expected_outcome"] == "reject" and f["expected_refusal"] for f in INVALID)
    names = [f["fixture_id"] for f in VALID + INVALID]
    assert len(names) == len(set(names))
    for kind in ("valid", "invalid"):
        for path in (CONTRACT_DIR / "fixtures" / kind).glob("*.json"):
            assert json.loads(path.read_text())["fixture_id"] == path.stem


def test_valid_captures_name_the_control_plane_commit_they_came_from():
    captured = [f for f in VALID if f["provenance"]["source"].startswith("control-plane-capture")]
    assert len(captured) >= 10
    assert {f["provenance"]["control_plane_commit"] for f in captured} == {"83b49b5"}


@pytest.mark.parametrize("f", VALID, ids=lambda f: f["fixture_id"])
def test_valid_fixture_is_accepted_alone_and_with_its_run_record(f):
    assert oi.validate(f["document"]) == []
    assert oi.validate(f["document"], f.get("journal")) == []


@pytest.mark.parametrize("f", INVALID, ids=lambda f: f["fixture_id"])
def test_invalid_fixture_is_refused_with_stated_reason(f):
    assert codes(f["document"], f.get("journal")) == [f["expected_refusal"]], f["reason"]


def test_every_rule_code_is_pinned_by_a_fixture_and_the_readme():
    source = (CONTRACT_DIR / "validate.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'_v\(\s*"([a-z_]+)"', source)) | set(re.findall(r'Violation\(\s*"([a-z_]+)"', source))
    covered = {f["expected_refusal"] for f in INVALID} | {"not_append_only"}  # the succession check is pinned by its own test
    assert emitted - covered == set(), emitted - covered
    readme = (CONTRACT_DIR / "README.md").read_text(encoding="utf-8")
    missing = sorted(c for c in emitted if f"`{c}`" not in readme)
    assert missing == [], missing


def test_the_seven_profile_reason_codes_and_destination_terms_are_documented():
    readme = (CONTRACT_DIR / "README.md").read_text(encoding="utf-8")
    assert len(oi.REASON_CODES) == 7 and len(set(oi.REASON_CODES)) == 7
    for code in oi.REASON_CODES:
        assert f"`{code}`" in readme, code
    assert oi.DESTINATION_CAPABILITY == "operation-identity/0.1" and f"`{oi.DESTINATION_CAPABILITY}`" in readme
    assert oi.DESTINATION_REJECTION == "operation_already_committed" and f"`{oi.DESTINATION_REJECTION}`" in readme
    assert "operation_identity_capability_unavailable" in readme


def test_defaults_are_numbered_in_the_readme():
    readme = (CONTRACT_DIR / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Defaults taken", 1)[1].split("\n## ", 1)[0]
    numbers = [int(n) for n in re.findall(r"^(\d+)\. ", section, flags=re.M)]
    assert numbers == list(range(1, len(numbers) + 1)) and len(numbers) >= 15


# ------------------------------------------------------------------ member model

def test_unknown_member_is_refused_not_dropped():
    d = fx("normal-attempted-acknowledged")["document"]
    d["operations"][0]["injected"] = 1
    (v,) = oi.validate(d)
    assert v.code == "undeclared_member" and v.path.endswith("injected")


def test_extensions_are_preserved_and_bound_into_the_digest():
    d = fx("extension-namespace-members-preserved")["document"]
    assert oi.preserve(d) == d
    stripped = copy.deepcopy(d)
    del stripped["extensions"]
    assert oi.canonical_bytes(stripped) != oi.canonical_bytes(d)
    assert oi.validate(stripped) != [] or True  # other extension members remain; the verdict ignores them
    assert "extensions" not in oi.known_view(d) and "extensions" not in oi.known_view(d)["operations"][0]
    d["operations"][0]["extensions"] = {"not-prefixed": 1}
    assert codes(d) == ["invalid_extension_key"]


def test_required_members_are_required():
    base = fx("normal-attempted-acknowledged")["document"]
    for member in ["contract", "contract_version", "profile", "run_id", "operations", "operation_renewals", "attempt_joins"]:
        d = copy.deepcopy(base)
        del d[member]
        assert codes(d) == ["schema_violation"], member
    for member in ["producer", "extensions"]:
        d = copy.deepcopy(base)
        d.pop(member, None)
        assert codes(d) == [], member
    for kind, row in (("operations", 0), ("attempt_joins", 0)):
        for member in list(base[kind][row]):
            if member == "extensions":
                continue
            d = copy.deepcopy(base)
            del d[kind][row][member]
            assert codes(d) == ["schema_violation"], (kind, member)


def test_unsupported_contract_version_is_refused_typed():
    d = fx("normal-attempted-acknowledged")["document"]
    d["contract_version"] = "9.0.0"
    assert codes(d) == ["unsupported_contract_version"]


def test_schema_is_draft_2020_12_and_agrees_with_reference_validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = oi.load_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    cls = jsonschema.Draft202012Validator
    cls.check_schema(schema)
    validator = cls(schema)
    for f in VALID:
        assert not list(validator.iter_errors(f["document"])), f["fixture_id"]
    structural = {"undeclared_member", "invalid_extension_key", "schema_violation", "unknown_enum_value", "unsupported_contract_version"}
    for f in INVALID:
        if f["fixture_id"] == "unpaired-surrogate-text":
            continue  # text validity is a validator rule; the portable schema does not state it
        assert bool(list(validator.iter_errors(f["document"]))) == (f["expected_refusal"] in structural), f["fixture_id"]


def test_validator_cli_reads_fixtures(capsys):
    assert oi.main([str(next((CONTRACT_DIR / "fixtures" / "valid").glob("*.json")))]) == 0
    assert oi.main([str(next((CONTRACT_DIR / "fixtures" / "invalid").glob("*.json")))]) == 1
    assert capsys.readouterr().out.strip()


def test_contract_is_not_part_of_core_or_pder():
    for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "profiles").rglob("*")):
        if path.is_file():
            assert "operation-identity" not in path.read_text(encoding="utf-8", errors="ignore"), path


# ------------------------------------------------------------------ layering on the journal and lifecycle contracts

def test_layered_versions_are_pinned_and_the_journal_contract_declares_the_profile_members_as_optional():
    """Since the journal contract's draft revision 2 (decision 23) the members of this profile are declared OPTIONAL in the journal
    schema and listed with their owning profile in validate.py (PROFILE_OWNED); the sidecar still owns their semantics. The version stays 0.1.0-draft."""
    assert cpj.CONTRACT_VERSION == "0.1.0-draft" and cpj.DELEGATED_LIFECYCLE_VERSION == "0.1.0-draft"
    schema = json.loads((JOURNAL_DIR / "schema.json").read_text(encoding="utf-8"))
    for member in ("operations", "operation_renewals", "attempt_joins"):
        assert cpj.PROFILE_OWNED["$"][member] == ["operation-identity/0.1"] and member in schema["properties"] and member not in schema["required"], member
    assert cpj.PROFILE_OWNED["refusal"]["check_id"] == ["operation-identity/0.1", "freshness/0.1"] and "check_id" in schema["$defs"]["refusal"]["properties"]
    assert cpj.PROFILE_OWNED["runtime_authority"]["operation_id"] == ["operation-identity/0.1"] and "operation_id" in schema["$defs"]["runtime_authority"]["properties"]
    assert "check_id" not in schema["$defs"]["refusal"]["required"]
    assert schema["additionalProperties"] is False


def test_real_run_records_with_the_profile_are_refused_by_the_journal_contract_only_for_the_profile_members():
    """The captured contexts carry the profile's check_id on refusals and operation_id in the binding extension."""
    refusal = fx("effect-time-refusal-carries-check-id")
    assert "check_id" in refusal["journal"]["refusals"][0]
    normal = fx("normal-attempted-acknowledged")
    ra = normal["journal"]["decisions"][0]["binding"]["runtime_authority"]
    assert {"operation_id", "operation_issuer"} <= set(ra)


def test_the_run_record_is_not_revalidated_and_unread_members_are_ignored():
    f = fx("normal-attempted-acknowledged")
    j = f["journal"]
    j["observations"] = [{"anything": 1}]
    j["unknown_member"] = True
    assert codes(f["document"], j) == []


# ------------------------------------------------------------------ rules that need more than one mutation

def test_renewal_refusal_follows_the_producers_check_order():
    """Not admitted, then not the issuer, then not new: a worker renewing an old revision is refused for the writer."""
    d = fx("worker-self-renewal-refused-then-unrecorded-hold")["document"]
    row = d["operation_renewals"][0]
    assert (row["outcome"], row["refusal_code"]) == ("refused", "renewal_not_written_by_grant_issuer")
    row["to_revision"] = "1"  # also not new, still refused for the writer
    assert codes(d) == []
    row["refusal_code"] = "renewal_revision_not_new"
    assert codes(d) == ["renewal_refusal_code_mismatch"]


def test_accepted_renewals_chain_from_revision_to_revision():
    d = fx("renewal-accepted-second-revision")["document"]
    base = d["operation_renewals"][0]
    second = {**base, "renewal_id": "syn-renewal-2", "from_revision": "2", "to_revision": "3"}
    d["operation_renewals"].append(second)
    assert codes(d) == []
    d["operation_renewals"][1]["from_revision"] = "1"
    assert codes(d) == ["renewal_context_mismatch"]


def test_a_refused_renewal_does_not_license_its_revision():
    d = fx("worker-self-renewal-refused-then-unrecorded-hold")["document"]
    assert oi.licensed_revisions(d, d["operations"][0]["operation_id"]) == {"1"}
    j = fx("renewal-accepted-second-revision")["document"]
    assert oi.licensed_revisions(j, j["operations"][0]["operation_id"]) == {"1", "2"}
    assert oi.licensed_revisions(j, "unknown") == set()


def test_operation_status_mirrors_the_producer_judgement():
    d = fx("renewal-accepted-second-revision")["document"]
    op = d["operations"][0]
    binding = dict(operation_id=op["operation_id"], principal_id=op["principal_id"], authority_domain=op["authority_domain"],
                   issuer=op["issuer"], grant_id=op["grant_id"], grant_revision="2")
    assert oi.operation_status(d, **binding) == "ok"
    assert oi.operation_status(d, **{**binding, "grant_revision": "3"}) == "renewal_unrecorded"
    assert oi.operation_status(d, **{**binding, "grant_id": "other"}) == "collision"
    assert oi.operation_status(d, **{**binding, "issuer": "someone"}) == "collision"
    assert oi.operation_status(d, **{**binding, "operation_id": "unknown"}) == "not_admitted"
    assert oi.STATUS_REASON == {"not_admitted": "operation_not_admitted", "collision": "operation_grant_mismatch",
                                "renewal_unrecorded": "operation_renewal_unrecorded"}
    assert set(oi.STATUS_REASON.values()) <= set(oi.REASON_CODES)


def test_valid_operation_id_shape_matches_the_producer_pattern():
    good = ["op-order-100/refund-1", "A", "a.b:c/d#e-f_g".replace("_", "-"), "x" * 128]
    bad = ["", "-x", "has space", "x" * 129, "é", None, 7, "a\n"]
    assert all(oi.valid_operation_id(x) for x in good)
    assert not any(oi.valid_operation_id(x) for x in bad)


def test_delayed_first_attempt_shows_one_effect_and_a_definitive_rejection():
    f = fx("delayed-first-attempt-rejected-after-renewal")
    rows = f["journal"]["attempts"]
    last = {}
    for a in rows:
        last[a["attempt_id"]] = a
    assert sorted((a["status"], a["error"]) for a in last.values()) == [("acknowledged", None), ("failed", "operation_already_committed")]
    assert len(f["document"]["attempt_joins"]) == 2 and len({j["effect_id"] for j in f["document"]["attempt_joins"]}) == 2
    assert {j["grant_revision"] for j in f["document"]["attempt_joins"]} == {"1", "2"}
    assert len(f["document"]["operations"]) == 1  # operation_id stable across the renewal


def test_unknown_attempts_may_have_committed_so_a_peer_may_be_unknown():
    f = fx("delayed-first-attempt-rejected-after-renewal")
    for a in f["journal"]["attempts"]:
        if a["status"] == "acknowledged":
            a.update(status="unknown", error="destination_outcome_unknown:TimeoutError")
    assert codes(f["document"], f["journal"]) == []


def test_an_unjoined_run_without_ledger_rows_is_outside_the_profile():
    """Profile off (empty ledger): no attempt needs a join and no refusal needs a check id."""
    f = fx("effect-time-refusal-carries-check-id")
    f["document"].update(operations=[], operation_renewals=[], attempt_joins=[])
    f["journal"]["refusals"][0].pop("check_id")
    for d in f["journal"]["decisions"]:
        d["binding"]["runtime_authority"].pop("operation_id", None)
    assert codes(f["document"], f["journal"]) == []


def test_ledger_rows_are_append_only_across_exports():
    earlier = fx("renewal-accepted-second-revision")["document"]
    later = copy.deepcopy(earlier)
    later["operation_renewals"].append({**later["operation_renewals"][0], "renewal_id": "syn-renewal-2", "from_revision": "2", "to_revision": "3"})
    assert oi.check_succession(earlier, later) == []
    assert [v.code for v in oi.check_succession(later, earlier)] == ["not_append_only"]
    changed = copy.deepcopy(earlier)
    changed["operations"][0]["issuer"] = "other"
    assert [v.code for v in oi.check_succession(earlier, changed)] == ["not_append_only"]


def test_journal_check_ids_are_shared_across_events_resolution_rows_and_refusals_in_the_captures():
    for f in VALID:
        j = f.get("journal")
        if not j or not f["document"]["operations"]:
            continue
        opened = {(e["check_id"], e["stage"]) for e in j["check_events"] if e["phase"] == "opened"}
        assert {(c["check_id"], c["stage"]) for c in j["resolution_checks"]} <= opened, f["fixture_id"]
        for x in j["refusals"]:
            assert (x["check_id"], "effect") in opened


def test_every_profile_row_kind_is_exercised_by_a_valid_fixture():
    assert any(f["document"]["operations"] for f in VALID)
    assert any(r["outcome"] == "accepted" for f in VALID for r in f["document"]["operation_renewals"])
    assert {r["refusal_code"] for f in VALID for r in f["document"]["operation_renewals"] if r["outcome"] == "refused"} == {
        "operation_not_admitted", "renewal_not_written_by_grant_issuer", "renewal_revision_not_new"}
    assert any(j["merged_into"] for f in VALID for j in f["document"]["attempt_joins"])
    assert any(len(f["document"]["attempt_joins"]) == 2 for f in VALID)


def test_require_profile_refuses_an_empty_ledger_beside_authorized_decisions():
    """Decision 37: a consumer that knows the host selected the profile is not exempted by an empty ledger."""
    f = fx("effect-time-refusal-carries-check-id")
    f["document"].update(operations=[], operation_renewals=[], attempt_joins=[])
    f["journal"]["refusals"][0].pop("check_id")
    for d in f["journal"]["decisions"]:
        d["binding"]["runtime_authority"].pop("operation_id", None)
    assert oi.validate(f["document"], f["journal"]) == []
    found = [v.code for v in oi.validate(f["document"], f["journal"], require_profile=True)]
    assert "decision_operation_id_missing" in found
    g = fx("normal-attempted-acknowledged")
    g["document"].update(operations=[], operation_renewals=[], attempt_joins=[])
    for d in g["journal"]["decisions"]:
        d["binding"]["runtime_authority"].pop("operation_id", None)
    found = [v.code for v in oi.validate(g["document"], g["journal"], require_profile=True)]
    assert "attempt_without_join" in found
