"""Conformance tests for the freshness-clocks extension profile draft (0.1.0-draft).

Docs-and-fixtures only: this exercises contracts/freshness-clocks/validate.py against the golden fixtures. The valid fixtures are
captures of real Control Plane runs (opt-in freshness/0.1, merged in #47); the invalid ones are single-defect mutations of them. The
cross-document rules take the run record (journal) and host configuration (host) as optional arguments. This file does not import or
alter the odes package and does not edit the journal, lifecycle or operation-identity contracts.
"""
import copy
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "contracts" / "freshness-clocks"
JOURNAL_DIR = ROOT / "contracts" / "control-plane-journal"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # validate.py defines a dataclass; register before exec
    spec.loader.exec_module(module)
    return module


fc = _load("fc_validate", CONTRACT_DIR / "validate.py")
cpj = _load("fc_cpj_validate", JOURNAL_DIR / "validate.py")


def _fixtures(kind):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((CONTRACT_DIR / "fixtures" / kind).glob("*.json"))]


VALID = _fixtures("valid")
INVALID = _fixtures("invalid")


def fx(fixture_id):
    return copy.deepcopy(next(f for f in VALID if f["fixture_id"] == fixture_id))


def run(f, journal=True, host=True):
    return fc.validate(f["document"], f.get("journal") if journal else None, f.get("host") if host else None)


def codes(f, **kw):
    return [v.code for v in run(f, **kw)]


# ------------------------------------------------------------------ fixtures

def test_fixture_sets_are_present_and_well_formed():
    assert len(VALID) >= 20 and len(INVALID) >= 85
    for f in VALID + INVALID:
        assert f["synthetic"] is True and f["reason"].strip() and f["provenance"]["source"]
        assert f["expected_outcome"] in {"accept", "reject"}
        assert f["document"]["contract"] == "freshness-clocks"
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
    assert len(captured) == len(VALID)
    assert {f["provenance"]["control_plane_commit"] for f in captured} == {"3f6a7668"}


@pytest.mark.parametrize("f", VALID, ids=lambda f: f["fixture_id"])
def test_valid_fixture_is_accepted_alone_and_with_its_context(f):
    assert fc.validate(f["document"]) == []
    assert run(f) == []
    assert run(f, host=False) == []


@pytest.mark.parametrize("f", INVALID, ids=lambda f: f["fixture_id"])
def test_invalid_fixture_is_refused_with_stated_reason(f):
    assert codes(f) == [f["expected_refusal"]], f["reason"]


def test_every_rule_code_is_pinned_by_a_fixture_and_the_readme():
    source = (CONTRACT_DIR / "validate.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'_v\(\s*"([a-z_]+)"', source)) | set(re.findall(r'Violation\(\s*"([a-z_]+)"', source))
    covered = {f["expected_refusal"] for f in INVALID} | {"not_append_only"}  # the succession check is pinned by its own test
    assert emitted - covered == set(), emitted - covered
    readme = (CONTRACT_DIR / "README.md").read_text(encoding="utf-8")
    missing = sorted(c for c in emitted if f"`{c}`" not in readme)
    assert missing == [], missing


def test_profile_terms_are_documented():
    readme = (CONTRACT_DIR / "README.md").read_text(encoding="utf-8")
    for term in (*fc.REASON_CODES, "evaluated_at", "recorded_at", "observed_at", "deadline", "age_bound_seconds", "extension_id", "nonce",
                 "overdue", "expired", "age_basis", "nonce_bound", "source_asserted", "nonce_mismatch", "status-nonce/0.1", "delayed-commit/0.1",
                 "pause_at", "defer_next_commit", "land", "age_extension", "age_extension_refusal", "recovery_run", "recovery_pass",
                 "second_attempt_for_effect"):
        assert f"`{term}`" in readme, term


def test_defaults_are_numbered_in_the_readme():
    readme = (CONTRACT_DIR / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Defaults taken", 1)[1].split("\n## ", 1)[0]
    numbers = [int(n) for n in re.findall(r"^(\d+)\. ", section, flags=re.M)]
    assert numbers == list(range(1, len(numbers) + 1)) and len(numbers) >= 15


# ------------------------------------------------------------------ member model

def test_unknown_member_is_refused_not_dropped():
    d = fx("expired-before-dispatch")["document"]
    d["clock_rows"][0]["injected"] = 1
    (v,) = fc.validate(d)
    assert v.code == "undeclared_member" and v.path.endswith("injected")


def test_extensions_are_preserved_and_bound_into_the_digest():
    d = fx("extension-namespace-members-preserved")["document"]
    assert fc.preserve(d) == d
    stripped = copy.deepcopy(d)
    del stripped["extensions"]
    assert fc.canonical_bytes(stripped) != fc.canonical_bytes(d)
    assert "extensions" not in fc.known_view(d) and "extensions" not in fc.known_view(d)["check_events"][0]
    d["input_reads"][0]["extensions"] = {"not-prefixed": 1}
    assert [v.code for v in fc.validate(d)] == ["invalid_extension_key"]


def test_a_verbatim_producer_report_carries_no_extensions():
    d = fx("freshness-counts-next-to-refusal-counts")["document"]
    d["freshness_reports"][0]["report"]["extensions"] = {"x-a": 1}
    assert [v.code for v in fc.validate(d)] == ["undeclared_member"]
    d = fx("freshness-counts-next-to-refusal-counts")["document"]
    d["freshness_reports"][0]["extensions"] = {"x-a": 1}
    assert fc.validate(d) == []  # the envelope may


def test_required_members_are_required():
    base = fx("expired-before-dispatch")["document"]
    for member in ["contract", "contract_version", "profile", "run_id", "check_events", "clock_rows", "input_reads", "age_extensions",
                   "age_extension_refusals", "recovery_runs", "freshness_reports"]:
        d = copy.deepcopy(base)
        del d[member]
        assert [v.code for v in fc.validate(d)] == ["schema_violation"], member
    for member in ["producer", "extensions"]:
        d = copy.deepcopy(base)
        d.pop(member, None)
        assert fc.validate(d) == [], member
    # on a check event only the identifying members, recorded_at and reasons are required; the profile's members are optional
    for member in list(base["check_events"][0]):
        d = copy.deepcopy(base)
        del d["check_events"][0][member]
        required = member in {"check_id", "phase", "stage", "recorded_at", "reasons"}
        assert bool(fc.validate_structure(d)) == required, member


def test_schema_is_draft_2020_12_and_agrees_with_reference_validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = fc.load_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    cls = jsonschema.Draft202012Validator
    cls.check_schema(schema)
    validator = cls(schema)
    for f in VALID:
        assert not list(validator.iter_errors(f["document"])), f["fixture_id"]
    structural = {"undeclared_member", "invalid_extension_key", "schema_violation", "unknown_enum_value", "unsupported_contract_version"}
    for f in INVALID:
        assert bool(list(validator.iter_errors(f["document"]))) == (f["expected_refusal"] in structural), f["fixture_id"]


def test_validator_cli_reads_fixtures(capsys):
    assert fc.main([str(next((CONTRACT_DIR / "fixtures" / "valid").glob("*.json")))]) == 0
    assert fc.main([str(next((CONTRACT_DIR / "fixtures" / "invalid").glob("*.json")))]) == 1
    assert capsys.readouterr().out.strip()


def test_contract_is_not_part_of_core_or_pder():
    for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "profiles").rglob("*")):
        if path.is_file():
            assert "freshness-clocks" not in path.read_text(encoding="utf-8", errors="ignore"), path


def test_the_ten_reason_codes_and_the_two_capabilities_are_stated():
    assert len(fc.REASON_CODES) == 10 and len(set(fc.REASON_CODES)) == 10
    assert fc.RESOLVER_CAPABILITY == "status-nonce/0.1" and fc.DESTINATION_CAPABILITY == "delayed-commit/0.1"
    assert fc.DESTINATION_METHODS == ("pause_at", "defer_next_commit", "land")


# ------------------------------------------------------------------ layering on the journal contract

def test_layered_version_is_pinned_and_the_journal_contract_declares_none_of_the_profile_members():
    """The journal contract refuses the opt-in members of a run record (undeclared_member). If it ever declares them this test fails:
    review the README section on layering and the hand-back divergence note."""
    assert cpj.CONTRACT_VERSION == "0.1.0-draft"
    schema = json.loads((JOURNAL_DIR / "schema.json").read_text(encoding="utf-8"))
    defs = schema["$defs"]
    for member in ("age_extensions", "age_extension_refusals", "recovery_runs"):
        assert member not in schema["properties"], member
    assert set(defs["journal_event"]["properties"]["phase"]["enum"]) == {"opened", "input", "completed", "interrupted"}
    for member in ("evaluated_at", "deadline", "age_bound_seconds", "extension_id", "nonce"):
        assert member not in defs["journal_event"]["properties"], member
    assert "age_basis" not in defs["resolution_input"]["properties"]
    assert "nonce_mismatch" not in defs["resolution_input"]["properties"]["read_state"]["enum"]
    for kind in ("decision", "control_plane_attempt", "resolution_check"):
        assert "recorded_at" not in defs[kind]["properties"] or kind == "refusal", kind
    assert "deadline" not in defs["refusal"]["properties"] and "evaluated_at" not in defs["refusal"]["properties"]
    assert schema["additionalProperties"] is False


def test_a_retry_after_expiry_is_a_second_lifecycle_under_the_journal_contracts_own_rule():
    """The fixture journal is a subset of the run record, so only the rules that read these rows can be shown: the journal contract's own
    one-lifecycle rule counts the retry after an expired attempt as a second attempt; this contract states the exclusion."""
    f = fx("expired-then-retry-dispatches")
    attempts = f["journal"]["attempts"]
    starts = {a["effect_id"]: set() for a in attempts}
    for a in attempts:
        if a["status"] == "attempted":
            starts[a["effect_id"]].add(a["attempt_id"])
    (ids,) = [v for v in starts.values() if v]
    assert len(ids) == 2, "two lifecycles start with attempted: the journal contract's second_attempt_for_effect would fire on this record"
    assert codes(f) == []


# ------------------------------------------------------------------ the rules, one scenario each

def test_check_without_a_deadline_is_open_but_never_overdue():
    f = fx("default-path-carries-no-clock-members")
    d = f["document"]
    assert all("deadline" not in e and "nonce" not in e for e in d["check_events"]) and not d["clock_rows"] and not d["input_reads"]
    counts = fc.freshness_counts(d["check_events"], fc.aware("2030-01-01T00:00:00+00:00"))
    assert counts["overdue_count"] == 0 and counts["open_count"] == 0
    open_one = copy.deepcopy(d["check_events"][:1])
    open_one[0]["check_id"] = "x"
    got = fc.freshness_counts(open_one, fc.aware("2030-01-01T00:00:00+00:00"))
    assert (got["open_count"], got["overdue_count"]) == (1, 0)


def test_three_clocks_recorded_at_follows_the_write_and_evaluated_at_is_one_pass():
    f = fx("clocks-follow-the-service-clock")
    d = f["document"]
    stamps = [e["recorded_at"] for e in d["check_events"] if e["stage"] == "decision"]
    assert stamps == sorted(stamps) and len(set(stamps)) > 1
    assert {e["evaluated_at"] for e in d["check_events"] if e["stage"] == "decision"} == {d["clock_rows"][0]["evaluated_at"]}
    assert all(r["recorded_at"] >= r["evaluated_at"] for r in d["clock_rows"])
    assert {r["row_type"] for r in d["clock_rows"]} == {"decision", "attempt", "resolution_check"}


def test_operation_rows_use_admitted_at_as_their_write_time():
    f = fx("operation-rows-carry-the-clocks")
    op = f["journal"]["operations"][0]
    (row,) = [r for r in f["document"]["clock_rows"] if r["row_type"] == "operation"]
    assert "recorded_at" not in op and row["recorded_at"] == op["admitted_at"] and row["evaluated_at"] == op["evaluated_at"]
    assert {r["row_type"] for r in f["document"]["clock_rows"]} >= {"operation", "operation_renewal", "attempt_join"}
    row["recorded_at"] = "2026-10-05T19:00:09+00:00"
    assert codes(f) == ["clock_row_mismatch"]


def test_expired_is_terminal_and_allowed_after_completed_and_overdue_never_closes_a_check():
    f = fx("expired-before-dispatch")
    effect = [e["phase"] for e in f["document"]["check_events"] if e["stage"] == "effect" and e["phase"] != "input"]
    assert effect == ["opened", "completed", "expired"]
    f = fx("overdue-reported-not-closed")
    phases = [e["phase"] for e in f["document"]["check_events"] if e["phase"] != "input"]
    assert phases == ["opened", "overdue", "completed"] and phases.count("overdue") == 1
    assert len(f["document"]["recovery_runs"]) == 2 and all(r["overdue"] for r in f["document"]["recovery_runs"])
    d = f["document"]
    d["check_events"].append({**d["check_events"][-1], "phase": "expired", "reasons": ["check_expired_before_dispatch"], "recorded_at": "2026-10-05T19:02:00+00:00"})
    assert [v.code for v in fc.validate(d)] == []  # expired after completed (and overdue) is the producer's own sequence


def test_the_failed_attempt_of_an_expired_check_is_excluded_from_the_prior_attempt_rule():
    f = fx("expired-then-retry-dispatches")
    final = {}
    for a in f["journal"]["attempts"]:
        final[a["attempt_id"]] = a
    assert sorted((a["status"], a.get("error")) for a in final.values()) == [("acknowledged", None), ("failed", "check_expired_before_dispatch")]
    assert codes(f) == []
    # a failed attempt with another error is a prior attempt: the retry is a second lifecycle
    for a in f["journal"]["attempts"]:
        if a.get("error") == "check_expired_before_dispatch":
            a["error"] = "destination_timeout"
    assert "prior_attempt_not_excluded" in codes(f)


def test_a_retry_after_expiry_opens_a_new_check_with_its_own_deadline_and_nonce():
    d = fx("expired-then-retry-dispatches")["document"]
    openings = [e for e in d["check_events"] if e["phase"] == "opened" and e["stage"] == "effect"]
    assert len(openings) == 2 and openings[0]["check_id"] != openings[1]["check_id"]
    assert openings[0]["nonce"] != openings[1]["nonce"] and openings[0]["deadline"] < openings[1]["deadline"]
    assert [e["phase"] for e in d["check_events"] if e["check_id"] == openings[1]["check_id"] and e["phase"] != "input"] == ["opened", "completed"]


def test_observation_clock_is_decoupled_the_deadline_decides():
    f = fx("observation-clock-decoupled")
    assert [e["phase"] for e in f["document"]["check_events"] if e["phase"] == "expired"] == ["expired"]
    assert not any("observation_time_future" in r["reasons"] for r in f["journal"]["reconciliations"]) if "reconciliations" in f["journal"] else True
    assert codes(f) == []


def test_deadline_is_the_openings_recorded_at_plus_the_bound_not_the_evaluation_time():
    f = fx("deadline-at-opening-within-bound")
    o = next(e for e in f["document"]["check_events"] if e["phase"] == "opened")
    assert o["evaluated_at"] == "2026-10-05T19:00:00+00:00" and o["recorded_at"] == "2026-10-05T19:00:02+00:00"
    assert (o["age_bound_seconds"], o["deadline"]) == (60, "2026-10-05T19:01:02+00:00")


def test_extension_reference_rules_use_the_row_the_opening_names():
    f = fx("extension-recorded-and-applied")
    openings = [e for e in f["document"]["check_events"] if e["phase"] == "opened"]
    assert [(e["age_bound_seconds"], bool(e.get("extension_id"))) for e in openings] == [(60, False), (200, True)]
    row = f["document"]["age_extensions"][0]
    assert row["extension_id"] == openings[1]["extension_id"] and (row["from_max_age_seconds"], row["to_max_age_seconds"]) == (60, 200)
    assert row["signer"] != row["requested_by"]


def test_accepted_extension_may_outlive_its_signers_authority_but_the_decision_then_holds():
    f = fx("extension-withdrawn-at-use")
    assert f["host"]["signers"] == ["urn:cognous:principal:policy-signer"]
    assert f["document"]["age_extensions"][0]["signer"] not in f["host"]["signers"]
    held = [d for d in f["journal"]["decisions"] if "age_extension_signer_not_configured" in d["reasons"]]
    assert len(held) == 1 and held[0]["result"] == "hold"
    assert codes(f) == []
    assert codes(f, host=False) == []
    f["host"]["signers"] = ["urn:cognous:principal:rule-signer"]  # the signer is configured: nothing explains the reason
    assert codes(f) == ["extension_reason_unexplained"]


def test_extension_refusals_carry_one_reason_per_defect_and_two_when_the_producer_derives_two():
    got = [x["reasons"] for x in fx("extension-refusals-kept")["document"]["age_extension_refusals"]]
    assert got == [["age_extension_unsigned"], ["age_extension_self_signed"], ["age_extension_signer_not_configured"],
                   ["age_extension_exceeds_limit"], ["age_extension_invalid"], ["age_extension_invalid"]]
    assert fx("extension-refusals-kept")["document"]["age_extensions"] == []
    f = fx("extension-without-authority-or-limit")
    assert f["document"]["age_extension_refusals"][0]["reasons"] == ["age_extension_authority_unconfigured", "age_extension_exceeds_limit"]
    assert f["host"] == {"signers": None, "max_age_extension_seconds": 0}


def test_extension_defects_reference_order_and_precedence():
    row = {"to_max_age_seconds": 200, "from_max_age_seconds": 60, "not_before": "2026-10-05T19:00:00+00:00", "expires_at": "2026-10-05T20:00:00+00:00",
           "requested_by": "a", "signer": "b"}
    assert fc.extension_defects(row, signers=["b"], max_extension_seconds=300) == []
    assert fc.extension_defects(row) == []  # nothing supplied: only the intrinsic defects
    assert fc.extension_defects({**row, "signer": None}, signers=None, max_extension_seconds=0) == [
        "age_extension_authority_unconfigured", "age_extension_exceeds_limit", "age_extension_unsigned"]
    assert fc.extension_defects({**row, "to_max_age_seconds": 60}, max_extension_seconds=0) == ["age_extension_invalid"]  # invalid shadows exceeds
    assert fc.extension_defects({**row, "signer": "a"}, signers=["b"]) == ["age_extension_self_signed"]  # self-signed shadows not configured
    assert fc.extension_defects({**row, "signer": "c"}, signers=["b"]) == ["age_extension_signer_not_configured"]


def test_nonce_reads_are_nonce_bound_only_where_the_resolver_echoes_and_a_replay_is_never_bound():
    bound = fx("nonce-bound-reads")
    assert {x["age_basis"] for x in bound["document"]["input_reads"]} == {"nonce_bound"}
    assert bound["host"] == {"resolver_capability": "status-nonce/0.1"}
    asserted = fx("source-asserted-without-capability")
    assert {x["age_basis"] for x in asserted["document"]["input_reads"]} == {"source_asserted"} and asserted["host"] == {"resolver_capability": None}
    assert any(e.get("nonce") for e in asserted["document"]["check_events"]), "the check still sends a nonce; the resolver does not echo it"
    replay = fx("nonce-replay-rejected")
    (mm,) = {(x["input_id"], x["expected_nonce"], x["observed_nonce"]) for x in replay["document"]["input_reads"] if x["read_state"] == "nonce_mismatch"}
    assert mm[1] != mm[2]
    refusal = replay["journal"]["refusals"][0]
    assert "status_nonce_mismatch" in refusal["reasons"] and refusal["changed_inputs"][0]["expected_version"] == f"nonce={mm[1]}"


def test_manifest_reads_carry_no_age_basis_and_are_not_listed():
    f = fx("nonce-bound-reads")
    assert "manifest" not in {x["input_type"] for x in f["document"]["input_reads"]}
    assert any(i["input_type"] == "manifest" and "age_basis" not in i for d in f["journal"]["decisions"] for i in d["resolution_inputs"])


def test_lease_unavailable_is_a_hold_with_no_check_and_no_read():
    f = fx("lease-unavailable-holds")
    (d,) = f["journal"]["decisions"]
    assert d["reasons"] == ["check_lease_unavailable"] and d["result"] == "hold" and not f["journal"]["attempts"]
    assert f["document"]["check_events"] == [] and f["document"]["input_reads"] == []
    assert f["journal"]["resolution_checks"][0]["inputs"] == []


def test_reaper_rows_close_the_dead_and_record_each_pass():
    f = fx("reaper-closes-the-dead-and-reports-the-late")
    runs = f["document"]["recovery_runs"]
    assert [r["trigger"] for r in runs] == ["startup", "interval"] and runs[0]["interrupted"] == ["orphan"]
    assert [e["phase"] for e in f["document"]["check_events"]] == ["opened", "interrupted"]


def test_freshness_counts_are_recomputed_from_the_events():
    f = fx("freshness-counts-next-to-refusal-counts")
    block = f["document"]["freshness_reports"][0]["report"]
    assert (block["open_count"], block["abandoned_open_count"], block["overdue_count"], block["expired_before_dispatch_count"]) == (1, 1, 1, 1)
    assert block["oldest_open_age_seconds"] == 90.0
    assert fc.freshness_counts(f["document"]["check_events"], fc.aware(block["as_of"])) == {k: v for k, v in block.items() if k != "as_of"}
    # a later as_of ages the open check and keeps the others
    block["as_of"] = "2026-10-05T19:05:00+00:00"
    assert codes(f) == ["freshness_counts_mismatch"]


def test_without_a_journal_or_host_the_context_rules_are_skipped_not_assumed():
    f = fx("extension-withdrawn-at-use")
    f["journal"]["decisions"][-1]["reasons"].append("age_extension_unsigned")
    assert codes(f, host=False) == [] and codes(f, journal=False) == []
    assert codes(f) == ["extension_reason_unexplained"]
    f = fx("nonce-bound-reads")
    assert codes(f, host=False) == []
    f["host"]["resolver_capability"] = None
    assert codes(f, host=False) == [] and codes(f) == ["nonce_bound_without_capability"]


def test_the_run_record_is_not_revalidated_and_unread_members_are_ignored():
    f = fx("expired-before-dispatch")
    f["journal"]["observations"] = [{"anything": 1}]
    f["journal"]["unknown_member"] = True
    assert codes(f) == []


def test_row_lists_are_append_only_across_exports():
    earlier = fx("overdue-reported-not-closed")["document"]
    later = copy.deepcopy(earlier)
    later["recovery_runs"].append({**later["recovery_runs"][-1], "run_id": "syn-recovery-run-9", "recorded_at": "2026-10-05T19:01:30+00:00"})
    assert fc.check_succession(earlier, later) == []
    assert [v.code for v in fc.check_succession(later, earlier)] == ["not_append_only"]
    changed = copy.deepcopy(earlier)
    changed["check_events"][0]["recorded_at"] = "2026-10-05T19:00:09+00:00"
    assert [v.code for v in fc.check_succession(earlier, changed)] == ["not_append_only"]
    other = copy.deepcopy(earlier)
    other["run_id"] = "other"
    assert [v.code for v in fc.check_succession(earlier, other)] == ["not_append_only"]


def test_every_profile_shape_is_exercised_by_a_valid_fixture():
    docs = [f["document"] for f in VALID]
    assert {e["phase"] for d in docs for e in d["check_events"]} == {"opened", "input", "completed", "interrupted", "overdue", "expired"}
    assert {x["row_type"] for d in docs for x in d["clock_rows"]} == {"decision", "attempt", "refusal", "resolution_check", "attempt_join", "operation", "operation_renewal"}
    assert {x["age_basis"] for d in docs for x in d["input_reads"]} == {"nonce_bound", "source_asserted"}
    assert {x["read_state"] for d in docs for x in d["input_reads"]} == {None, "nonce_mismatch"}
    assert any(d["age_extensions"] for d in docs) and any(d["freshness_reports"] for d in docs)
    assert {t for d in docs for x in d["recovery_runs"] for t in [x["trigger"]]} == {"startup", "interval", "manual"}
    assert {r for d in docs for x in d["age_extension_refusals"] for r in x["reasons"]} == set(fc.EXTENSION_CODES)
    seen = set()
    for f in VALID:
        for d in f.get("journal", {}).get("decisions", []):
            seen |= set(d["reasons"])
        for x in f.get("journal", {}).get("refusals", []):
            seen |= set(x["reasons"])
        for e in f["document"]["check_events"]:
            seen |= set(e["reasons"])
    assert {"check_expired_before_dispatch", "check_overdue", "check_lease_unavailable", "status_nonce_mismatch",
            "age_extension_signer_not_configured"} <= seen
