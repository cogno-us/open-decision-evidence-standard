"""Conformance tests for the rule-revision extension profile draft (0.1.0-draft).

Docs-and-fixtures only: this exercises contracts/rule-revision/validate.py against the golden fixtures. The valid fixtures
are captures of real Control Plane runs and real outputs of its trend, arity and recomputability functions (opt-in
rule-revision/0.1); the invalid ones are single-defect mutations of them. The cross-document rules take the run record
and the configured signer set as optional arguments. This file does not import or alter the odes package and does not edit
the journal or lifecycle contracts.
"""
import copy
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "contracts" / "rule-revision"
JOURNAL_DIR = ROOT / "contracts" / "control-plane-journal"
POLICY = "urn:cognous:policy:refund-policy"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # validate.py defines a dataclass; register before exec
    spec.loader.exec_module(module)
    return module


rr = _load("rr_validate", CONTRACT_DIR / "validate.py")
cpj = _load("rr_cpj_validate", JOURNAL_DIR / "validate.py")


def _fixtures(kind):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((CONTRACT_DIR / "fixtures" / kind).glob("*.json"))]


VALID = _fixtures("valid")
INVALID = _fixtures("invalid")


def fx(fixture_id):
    return copy.deepcopy(next(f for f in VALID if f["fixture_id"] == fixture_id))


def run(f, journal=True, signers=True):
    return rr.validate(f["document"], f.get("journal") if journal else None, f.get("signers") if signers else None)


def codes(f, **kw):
    return [v.code for v in run(f, **kw)]


# ------------------------------------------------------------------ fixtures

def test_fixture_sets_are_present_and_well_formed():
    assert len(VALID) >= 15 and len(INVALID) >= 76
    for f in VALID + INVALID:
        assert f["synthetic"] is True and f["reason"].strip() and f["provenance"]["source"]
        assert f["expected_outcome"] in {"accept", "reject"}
        assert f["document"]["contract"] == "rule-revision"
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
    assert len(captured) >= 14
    by = {f["fixture_id"]: f["provenance"]["control_plane_commit"] for f in captured}
    assert by.pop("recomputability-derivation-unavailable") == "fd0d5e0"  # re-captured after the N2b producer fix
    assert set(by.values()) == {"83b49b5"}


@pytest.mark.parametrize("f", VALID, ids=lambda f: f["fixture_id"])
def test_valid_fixture_is_accepted_alone_and_with_its_context(f):
    assert rr.validate(f["document"]) == []
    assert run(f) == []


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
    for term in ("tainted_for_trend", "verified_through", "measured_exceeds_declared", "arity_undeclared", "declared_overclaim",
                 "declared_underclaim", "derivation_unavailable", "policy_status_unknown", "rule_identity", "rule_revision_refusal", "digest_matches_signed_revision",
                 "signer_independent_and_configured", "revision_row_present", "no_signed_revision", "unsigned_revision_row",
                 "self_signed_revision_row", "signer_not_configured", "digest_mismatch_with_adopted", "observed_digest_absent",
                 "pre_split_count", "row_predates_adoption"):
        assert f"`{term}`" in readme, term
    for level in rr.LEVELS:
        assert f"`{level}`" in readme


def test_defaults_are_numbered_in_the_readme():
    readme = (CONTRACT_DIR / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Defaults taken", 1)[1].split("\n## ", 1)[0]
    numbers = [int(n) for n in re.findall(r"^(\d+)\. ", section, flags=re.M)]
    assert numbers == list(range(1, len(numbers) + 1)) and len(numbers) >= 15


# ------------------------------------------------------------------ member model

def test_unknown_member_is_refused_not_dropped():
    d = fx("adopted-policy-decision-and-refusal-rows")["document"]
    d["identity_rows"][0]["rule_identity"]["rules"][POLICY]["injected"] = 1
    (v,) = rr.validate(d)
    assert v.code == "undeclared_member" and v.path.endswith("injected")


def test_extensions_are_preserved_and_bound_into_the_digest():
    d = fx("extension-namespace-members-preserved")["document"]
    assert rr.preserve(d) == d
    stripped = copy.deepcopy(d)
    del stripped["extensions"]
    assert rr.canonical_bytes(stripped) != rr.canonical_bytes(d)
    assert "extensions" not in rr.known_view(d) and "extensions" not in rr.known_view(d)["rule_revisions"][0]
    d["identity_rows"][0]["extensions"] = {"not-prefixed": 1}
    assert [v.code for v in rr.validate(d)] == ["invalid_extension_key"]


def test_a_verbatim_producer_report_carries_no_extensions():
    d = fx("trend-flags-from-registry-adoption-row")["document"]
    d["trend_reports"][0]["report"]["extensions"] = {"x-a": 1}
    assert [v.code for v in rr.validate(d)] == ["undeclared_member"]
    d = fx("trend-flags-from-registry-adoption-row")["document"]
    d["trend_reports"][0]["extensions"] = {"x-a": 1}
    assert rr.validate(d) == []  # the envelope may


def test_required_members_are_required():
    base = fx("adopted-policy-decision-and-refusal-rows")["document"]
    for member in ["contract", "contract_version", "profile", "run_id", "rule_revisions", "rule_revision_refusals", "identity_rows",
                   "trend_reports", "arity_reports", "recomputability_reports"]:
        d = copy.deepcopy(base)
        del d[member]
        assert [v.code for v in rr.validate(d)] == ["schema_violation"], member
    for member in ["producer", "extensions"]:
        d = copy.deepcopy(base)
        d.pop(member, None)
        assert rr.validate(d) == [], member
    for member in list(base["rule_revisions"][0]):
        if member in ("extensions", "declared_arity"):
            continue
        d = copy.deepcopy(base)
        del d["rule_revisions"][0][member]
        assert [v.code for v in rr.validate(d)] == ["schema_violation"], member
    d = copy.deepcopy(base)
    d["rule_revisions"][0].pop("declared_arity", None)
    assert rr.validate(d) == []  # optional


def test_schema_is_draft_2020_12_and_agrees_with_reference_validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = rr.load_schema()
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
    assert rr.main([str(next((CONTRACT_DIR / "fixtures" / "valid").glob("*.json")))]) == 0
    assert rr.main([str(next((CONTRACT_DIR / "fixtures" / "invalid").glob("*.json")))]) == 1
    assert capsys.readouterr().out.strip()


def test_contract_is_not_part_of_core_or_pder():
    for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "profiles").rglob("*")):
        if path.is_file():
            assert "rule-revision" not in path.read_text(encoding="utf-8", errors="ignore"), path


# ------------------------------------------------------------------ layering on the journal contract

def test_layered_version_is_pinned_and_the_journal_contract_declares_the_profile_members_as_optional():
    """Since the journal contract's draft revision 2 (decision 23) the members of this profile are declared OPTIONAL in the journal
    schema and listed with their owning profile in validate.py (PROFILE_OWNED); the sidecar still owns their semantics. The version stays 0.1.0-draft."""
    assert cpj.CONTRACT_VERSION == "0.1.0-draft"
    schema = json.loads((JOURNAL_DIR / "schema.json").read_text(encoding="utf-8"))
    for member in ("rule_revisions", "rule_revision_refusals"):
        assert cpj.PROFILE_OWNED["$"][member] == ["rule-revision/0.1"] and member in schema["properties"] and member not in schema["required"], member
    for obj in ("decision", "refusal"):
        assert cpj.PROFILE_OWNED[obj]["rule_identity"] == ["rule-revision/0.1"] and "rule_identity" in schema["$defs"][obj]["properties"]
        assert "rule_identity" not in schema["$defs"][obj]["required"]
    assert schema["additionalProperties"] is False


def test_the_captured_run_records_carry_the_profile_members_the_journal_contract_refuses():
    f = fx("adopted-policy-decision-and-refusal-rows")
    assert "rule_identity" in f["journal"]["decisions"][0] and "rule_identity" in f["journal"]["refusals"][0]


def test_the_run_record_is_not_revalidated_and_unread_members_are_ignored():
    f = fx("adopted-policy-decision-and-refusal-rows")
    f["journal"]["attempts"] = [{"anything": 1}]
    f["journal"]["unknown_member"] = True
    assert codes(f) == []


# ------------------------------------------------------------------ rules that need more than one mutation

def test_reference_resolution_matches_the_captured_identity_rows():
    """Every identity row of every captured run is recomputed from the revision rows recorded by then (the producer's resolve_rule)."""
    checked = 0
    for f in VALID:
        d = f["document"]
        for row in d["identity_rows"]:
            t = rr.aware(row["recorded_at"])
            rows = [r for r in d["rule_revisions"] if rr.aware(r["recorded_at"]) <= t]
            for ref, st in row["rule_identity"]["rules"].items():
                res = rr.resolve_rule(rows, ref, st["digest"], f.get("signers"))
                assert (res["state"], res["verified_through"]) == (st["state"], st["verified_through"]), (f["fixture_id"], ref)
                assert sorted(res["findings"]) == sorted(st["findings"]), (f["fixture_id"], ref)
                checked += 1
    assert checked >= 15


def _row(rid, to, frm=None, *, signer="s", reviser="r", ref="p", kind="policy", supersedes=None, at="2026-10-05T19:00:00+00:00"):
    return {"revision_id": rid, "rule_kind": kind, "rule_ref": ref, "from_digest": frm, "to_digest": to, "reviser": reviser, "signer": signer,
            "authority_ref": None, "reason": "x", "supersedes": supersedes, "recorded_at": at}


def test_resolution_levels_and_findings():
    a, b = "sha256:" + "a" * 64, "sha256:" + "b" * 64
    assert rr.resolve_rule([], "p", a)["verified_through"] == "none"
    res = rr.resolve_rule([_row("1", a, signer=None)], "p", a)
    assert (res["state"], res["verified_through"], res["findings"]) == ("unknown", "revision_row_present", ["unsigned_revision_row", "no_signed_revision"])
    res = rr.resolve_rule([_row("1", a)], "p", None)
    assert (res["state"], res["verified_through"], res["findings"]) == ("unknown", "signer_independent_and_configured", ["observed_digest_absent"])
    res = rr.resolve_rule([_row("1", a)], "p", b)
    assert (res["state"], res["findings"]) == ("unknown", ["digest_mismatch_with_adopted"])
    res = rr.resolve_rule([_row("1", a)], "p", a)
    assert (res["state"], res["verified_through"], res["findings"]) == ("adopted", "digest_matches_signed_revision", [])
    # self-signed and (with a signer set) unconfigured rows never count
    assert rr.resolve_rule([_row("1", a, signer="r")], "p", a)["state"] == "unknown"
    assert rr.resolve_rule([_row("1", a, signer="x")], "p", a, signers=["s"])["findings"][0] == "signer_not_configured"
    assert rr.resolve_rule([_row("1", a, signer="x")], "p", a)["state"] == "adopted"  # no signer set supplied
    # a later signed row moves the adopted digest; a superseded row stops counting
    rows = [_row("1", a), _row("2", b, a)]
    assert rr.adopted_digest(rows, "p") == b and rr.resolve_rule(rows, "p", a)["state"] == "unknown"
    rows = [_row("1", a, signer=None), _row("1b", a, supersedes="1")]
    assert [x["revision_id"] for x in rr.counting_rows(rows, "p")] == ["1b"]
    # an unsigned row's supersedes does not hide a valid row
    rows = [_row("1", a), _row("2", b, a, signer=None, supersedes="1")]
    assert [x["revision_id"] for x in rr.counting_rows(rows, "p")] == ["1"]


def test_a_revision_row_recorded_after_a_decision_does_not_count_for_it():
    f = fx("policy-edited-in-place-held-then-readopted")
    d = f["document"]
    times = [(row["row_id"], row["recorded_at"], row["rule_identity"]["rules"][POLICY]["state"]) for row in d["identity_rows"]]
    assert [s for _, _, s in times] == ["adopted", "unknown", "adopted"]
    assert [r["recorded_at"] for r in d["rule_revisions"]] == ["2026-10-05T18:58:20+00:00", "2026-10-05T19:00:10+00:00"]
    assert times[1][1] < d["rule_revisions"][1]["recorded_at"] < times[2][1]  # the re-adopting row sits between the second and third decision
    d["rule_revisions"][1]["recorded_at"] = "2026-10-05T19:00:01+00:00"  # earlier than the held decision: now it would have counted
    assert rr.validate(d, f["journal"], f["signers"])[0].code == "rule_identity_recomputed_mismatch"


def test_chain_follows_supersession_and_ignores_unsigned_rows():
    f = fx("unsigned-then-resigned-by-supersession")
    d = f["document"]
    assert [r["signer"] is None for r in d["rule_revisions"]] == [True, False]
    assert rr.validate(d, f["journal"], f["signers"]) == []
    d["rule_revisions"][1]["from_digest"] = "sha256:" + "0" * 64  # superseding row must keep the superseded row's from_digest (null)
    assert [v.code for v in rr.validate(d)] == ["from_digest_mismatch"]


def test_unsigned_rows_are_kept_but_never_checked_against_the_chain():
    d = fx("adopted-policy-decision-and-refusal-rows")["document"]
    extra = {**copy.deepcopy(d["rule_revisions"][0]), "revision_id": "rev-9", "signer": None, "from_digest": "sha256:" + "0" * 64,
             "to_digest": "sha256:" + "d" * 64, "recorded_at": "2027-01-01T00:00:00+00:00"}
    d["rule_revisions"].append(extra)
    assert rr.validate(d) == []


def test_only_policy_rules_gate_a_decision_and_host_rules_do_not():
    f = fx("host-rule-unadopted-does-not-gate")
    ident = f["journal"]["decisions"][0]["rule_identity"]
    assert ident["unknown"] == ["runtime-authority-reasons/0.1"]
    assert f["journal"]["decisions"][0]["result"] == "authorized"
    assert codes(f) == []


def test_unadopted_policy_gate_applies_to_refusal_rows_as_well():
    f = fx("adopted-policy-decision-and-refusal-rows")
    refusal = f["journal"]["refusals"][0]
    refusal["rule_identity"]["rules"][POLICY].update(state="unknown", verified_through="none", findings=["no_signed_revision"])
    refusal["rule_identity"]["unknown"] = [POLICY]
    f["document"]["identity_rows"][1]["rule_identity"] = copy.deepcopy(refusal["rule_identity"])
    # internally consistent but contradicted by the revision rows, and the refusal does not carry policy_status_unknown
    assert sorted(codes(f)) == ["rule_identity_recomputed_mismatch", "unadopted_policy_not_held"]


def test_trend_series_without_annotation_is_valid_and_annotation_members_come_together():
    f = fx("trend-plain-without-adoption-annotation")
    assert codes(f) == []
    rep = f["document"]["trend_reports"][0]["report"]
    assert "rows_predating_adoption" not in rep and all("tainted_for_trend" not in s for s in rep["series"])
    rep["series"][0]["tainted_for_trend"] = False
    assert codes(f) == ["trend_annotation_incomplete"]


def test_trend_adoption_source_may_be_a_vocabulary_change_in_the_run_record():
    f = fx("trend-flags-from-registry-adoption-row")
    j = f["journal"]
    j["vocabulary_changes"] = [{"change_id": "c", "previous_version": "v0", "version": "runtime-authority-reasons/0.1", "registry_digest": "sha256:" + "1" * 64,
                                "kind": "addition", "previous_codes": [], "codes": [], "acknowledged_by": "s", "acknowledged_at": "2026-10-05T19:00:01+00:00"}]
    # the earliest adoption row wins: the vocabulary change is earlier than the revision row (19:00:03), so adoption_time must be 19:00:01
    assert set(codes(f)) == {"adoption_time_mismatch"}


def test_arity_declared_and_measured_are_both_kept_and_flags_are_derived():
    f = fx("arity-measured-exceeds-declared-and-undeclared")
    rep = f["document"]["arity_reports"][0]
    assert rep["declared"] == {"policy_status_unknown": 1}
    assert {c: v["measured"] for c, v in rep["measured"]["codes"].items()} == {"grant_revoked": 1, "policy_status_unknown": 2}
    assert {x["flag"] for x in rep["flags"]} == {"measured_exceeds_declared", "arity_undeclared"}
    assert rr.arity_flags(rep["declared"], rep["measured"]) == rep["flags"]
    assert rr.arity_flags({"policy_status_unknown": 2, "grant_revoked": 1}, rep["measured"]) == []
    assert [x["flag"] for x in rr.arity_flags({}, rep["measured"])] == ["arity_undeclared"] * 2


def test_real_recomputability_output_is_derivation_unavailable_when_operands_are_not_retained():
    """A real row keeps `observed == {}` on its manifest input, so operands are absent: the real grant_revoked hold derives
    underivable and is flagged derivation_unavailable, never declared_overclaim (Control Plane fd0d5e0, N2b)."""
    f = fx("recomputability-derivation-unavailable")
    (flag,) = f["document"]["recomputability_reports"][0]["flags"]
    assert (flag["code"], flag["declared"], flag["derived"], flag["flag"]) == ("grant_revoked", "recomputable", "underivable", "derivation_unavailable")
    row = f["journal"]["decisions"][flag["row"]]
    manifest = next(i for i in row["resolution_inputs"] if i["input_type"] == "manifest")
    assert manifest["observed"] == {} and rr.derive_recomputability(row) == "underivable"
    assert all(rr.derive_recomputability(d) == "underivable" for d in f["journal"]["decisions"])
    assert not any(x["flag"] == "declared_overclaim" for x in f["document"]["recomputability_reports"][0]["flags"])


def test_declared_overclaim_is_reserved_for_rows_with_operands_present():
    """Operands present and the derivation shows the declared kind cannot hold: declared_overclaim is accepted against the run record;
    the same flag on an operand-absent row is refused (the false overclaim)."""
    f = fx("recomputability-derivation-unavailable")
    d, j = copy.deepcopy(f["document"]), copy.deepcopy(f["journal"])
    (flag,) = d["recomputability_reports"][0]["flags"]
    row = j["decisions"][flag["row"]]
    for x in row["resolution_inputs"]:  # synthetic: operands present, every recorded expectation met
        x["observed"] = {"status": "active"}; x["expected"] = {"status": "active"}; x["record_commitment"] = "sha256:" + "1" * 64
    assert rr.derive_recomputability(row) == "typed_only"
    flag.update(derived="typed_only", flag="declared_overclaim")
    assert [v.code for v in rr.validate(d, j, f["signers"])] == []
    row["resolution_inputs"][0]["observed"] = {}  # operand removed: the same flag is now false
    assert [v.code for v in rr.validate(d, j, f["signers"])] == ["derived_recomputability_mismatch"]
    assert [v.code for v in rr.validate(d, None, f["signers"])] == []  # no run record: only the pair is checked
    flag.update(derived="underivable")
    assert [v.code for v in rr.validate(d, None, f["signers"])] == ["recomputability_flag_inconsistent"]


def test_derive_recomputability_reference_cases():
    full = {"resolution_inputs": [{"input_type": "grant", "observed": {"status": "revoked"}, "record_commitment": "sha256:" + "1" * 64}]}
    assert rr.derive_recomputability(full) == "recomputable"
    assert rr.derive_recomputability({"resolution_inputs": []}) == "underivable"
    assert rr.derive_recomputability({}) == "underivable"
    assert rr.derive_recomputability({"resolution_inputs": [{"missing": True}]}) == "recomputable"
    assert rr.derive_recomputability({"resolution_inputs": [{"observed": {"a": 1}}]}) == "underivable"
    met = {"resolution_inputs": [{"observed": {"a": 1}, "expected": {"a": 1}, "record_commitment": "sha256:" + "1" * 64}]}
    assert rr.derive_recomputability(met) == "typed_only"
    assert rr.derive_recomputability({"resolution_inputs": [{"observed": {}, "expected": {"a": 1}, "record_commitment": "sha256:" + "1" * 64}]}) == "underivable"


def test_adoption_times_take_the_earliest_source_per_label():
    revs = [_row("1", "sha256:" + "a" * 64, kind="reason_registry", ref="v1", at="2026-10-05T19:00:05+00:00"),
            _row("2", "sha256:" + "b" * 64, kind="policy", ref="v1", at="2026-10-05T19:00:01+00:00")]
    changes = [{"version": "v1", "acknowledged_at": "2026-10-05T19:00:03+00:00"}, {"version": "v2", "acknowledged_at": "2026-10-05T19:00:09+00:00"}]
    got = rr.adoption_times(revs, changes)
    assert str(got["v1"]) == "2026-10-05 19:00:03+00:00" and set(got) == {"v1", "v2"}


def test_refusal_rows_carry_reasons_in_producer_order_and_unsigned_rows_are_never_refused_for_signer():
    f = fx("refused-revision-attempts-kept-as-rows")
    got = [(x["revision"]["revision_id"], x["reasons"]) for x in f["document"]["rule_revision_refusals"]]
    assert got == [("rev-1", ["self_signed_revision_row"]), ("rev-2", ["signer_not_configured"]), ("rev-4", ["rule_revision_from_digest_mismatch"]),
                   ("rev-3", ["rule_revision_duplicate"]), ("rev-5", ["rule_revision_supersedes_unknown"])]
    assert [r["revision_id"] for r in f["document"]["rule_revisions"]] == ["rev-3"]


def test_without_a_signer_set_the_configured_check_is_skipped_not_assumed():
    f = fx("refused-revision-attempts-kept-as-rows")
    assert codes(f, signers=False) == []
    f["document"]["rule_revision_refusals"][1]["revision"]["signer"] = "synthetic-principal:signer"
    assert codes(f, signers=False) == []  # cannot tell without the set
    assert codes(f, signers=True) == ["refusal_reason_mismatch"]


def test_revision_rows_are_append_only_across_exports():
    earlier = fx("policy-edited-in-place-held-then-readopted")["document"]
    later = copy.deepcopy(earlier)
    later["rule_revisions"].append({**later["rule_revisions"][0], "revision_id": "rev-3", "from_digest": later["rule_revisions"][1]["to_digest"],
                                    "to_digest": "sha256:" + "e" * 64, "recorded_at": "2026-10-05T19:00:30+00:00"})
    assert rr.check_succession(earlier, later) == []
    assert [v.code for v in rr.check_succession(later, earlier)] == ["not_append_only"]
    changed = copy.deepcopy(earlier)
    changed["rule_revisions"][0]["signer"] = "other"
    assert [v.code for v in rr.check_succession(earlier, changed)] == ["not_append_only"]


def test_every_profile_shape_is_exercised_by_a_valid_fixture():
    docs = [f["document"] for f in VALID]
    assert any(d["rule_revisions"] for d in docs) and any(d["rule_revision_refusals"] for d in docs)
    assert {r for d in docs for x in d["rule_revision_refusals"] for r in x["reasons"]} == {
        "self_signed_revision_row", "signer_not_configured", "rule_revision_duplicate", "rule_revision_supersedes_unknown",
        "rule_revision_from_digest_mismatch"}
    states = {(s["state"], s["verified_through"]) for d in docs for row in d["identity_rows"] for s in row["rule_identity"]["rules"].values()}
    assert {x[1] for x in states} == set(rr.LEVELS)
    assert any(d["trend_reports"] for d in docs) and any(d["arity_reports"] for d in docs) and any(d["recomputability_reports"] for d in docs)
    assert {t for d in docs for r in d["trend_reports"] for s in r["report"]["series"] for t in s.get("taint_reasons", [])} == {"pre_split_count", "row_predates_adoption"}
