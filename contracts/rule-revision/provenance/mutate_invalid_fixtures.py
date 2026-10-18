"""Mutate the valid rule-revision fixtures into the invalid ones (single-defect mutations; each fixture's `provenance` names its base).

    python mutate_invalid_fixtures.py <contracts/rule-revision dir>

Reads contracts/rule-revision/fixtures/valid and validate.py, rewrites fixtures/invalid, and stops if a mutation does not yield exactly
its one expected code.
"""
import copy, json, sys, importlib.util
from pathlib import Path
def write(dirpath, fixture):
    (Path(dirpath) / f"{fixture['fixture_id']}.json").write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
CDIR = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("rr", CDIR / "validate.py"); rr = importlib.util.module_from_spec(spec)
sys.modules["rr"] = rr; spec.loader.exec_module(rr)
V = {p.stem: json.loads(p.read_text()) for p in (CDIR / "fixtures" / "valid").glob("*.json")}
out_dir = CDIR / "fixtures" / "invalid"
for p in out_dir.glob("*.json"): p.unlink()
CP = "83b49b5"
results = []
FUTURE = "2027-01-01T00:00:00+00:00"
D1 = V["adopted-policy-decision-and-refusal-rows"]["document"]["rule_revisions"][0]["to_digest"]
D2 = "sha256:" + "d" * 64

def make(fid, base, code, why, fn=None, journal=False, signers=None):
    b = copy.deepcopy(V[base])
    doc, jr = b["document"], b["journal"]
    sg = b["signers"] if signers is None else signers
    if fn: fn(doc, jr)
    fx = {"fixture_id": fid, "synthetic": True, "expected_outcome": "reject", "expected_refusal": code, "reason": why,
          "provenance": {"source": f"mutation of captured fixture {base}", "control_plane_commit": CP}, "document": doc, "signers": sg}
    if journal: fx["journal"] = jr
    got = [v.code for v in rr.validate(doc, jr if journal else None, sg)]
    results.append((fid, code, got))
    write(out_dir, fx)

A, U, RF, E_, S_ = ("adopted-policy-decision-and-refusal-rows", "unsigned-row-resolves-unknown-and-holds", "refused-revision-attempts-kept-as-rows",
                    "policy-edited-in-place-held-then-readopted", "unsigned-then-resigned-by-supersession")
T1, T2, AR, AW, RC = ("trend-flags-from-registry-adoption-row", "trend-pre-split-tainted-from-vocabulary-change", "arity-measured-exceeds-declared-and-undeclared",
                      "arity-within-declaration", "recomputability-derivation-unavailable")
POLICY = "urn:cognous:policy:refund-policy"
def extra_row(d, **kw):
    base = {**copy.deepcopy(d["rule_revisions"][0]), "revision_id": "rev-9", "from_digest": D1, "to_digest": D2, "recorded_at": FUTURE}
    base.update(kw); d["rule_revisions"].append(base); return base

# ---- structure
make("undeclared-member-outside-extensions", A, "undeclared_member", "A member neither declared nor inside extensions is refused, never dropped.", lambda d, j: d["rule_revisions"][0].update(injected=1))
make("extension-key-without-x-prefix", A, "invalid_extension_key", "Extension members use the reserved x- form.", lambda d, j: d.update(extensions={"note": 1}))
make("unsupported-contract-version", A, "unsupported_contract_version", "A different contract version is refused typed.", lambda d, j: d.update(contract_version="9.0.0"))
make("profile-marker-wrong", A, "schema_violation", "The profile marker is exact.", lambda d, j: d.update(profile="rule-revision/0.2"))
make("unknown-rule-kind", A, "unknown_enum_value", "The four rule kinds are closed.", lambda d, j: d["rule_revisions"][0].update(rule_kind="schema"))
make("unknown-refusal-reason", RF, "unknown_enum_value", "The five refusal reasons are closed; unsigned_revision_row is a finding, never a refusal.", lambda d, j: d["rule_revision_refusals"][0].update(reasons=["unsigned_revision_row"]))
make("unknown-verified-through-level", A, "unknown_enum_value", "The four verification levels are closed.", lambda d, j: d["identity_rows"][0]["rule_identity"]["rules"][POLICY].update(verified_through="partially_verified"))
make("unknown-finding", U, "unknown_enum_value", "The six findings are closed.", lambda d, j: d["identity_rows"][0]["rule_identity"]["rules"][POLICY]["findings"].append("tampered"))
make("unknown-arity-flag", AR, "unknown_enum_value", "The two arity flags are closed.", lambda d, j: d["arity_reports"][0]["flags"][0].update(flag="arity_unmeasured"))
make("unknown-rows-from", RC, "unknown_enum_value", "Recomputability rows come from decisions or refusals.", lambda d, j: d["recomputability_reports"][0].update(rows_from="attempts"))
make("unknown-taint-reason", T1, "unknown_enum_value", "The two taint reasons are closed.", lambda d, j: d["trend_reports"][0]["report"]["series"][0].update(taint_reasons=["row_is_old"]))
make("digest-not-a-commitment", A, "schema_violation", "to_digest is a sha256 commitment (a contract-only tightening of the producer's non-empty string).", lambda d, j: d["rule_revisions"][0].update(to_digest="v1"))
make("missing-reviser", A, "schema_violation", "A revision row carries every member.", lambda d, j: d["rule_revisions"][0].pop("reviser"))
make("empty-refusal-reasons", RF, "schema_violation", "A refusal row states at least one reason.", lambda d, j: d["rule_revision_refusals"][0].update(reasons=[]))
make("measurement-period-zero", AR, "schema_violation", "period_seconds is at least 1.", lambda d, j: d["arity_reports"][0]["measured"].update(period_seconds=0))
make("negative-series-count", T1, "schema_violation", "Counts are non-negative integers.", lambda d, j: d["trend_reports"][0]["report"]["series"][0].update(count=-1))

# ---- revision rows
make("duplicate-revision-id", A, "duplicate_revision_id", "Revision ids are unique; rows are appended, never edited.", lambda d, j: extra_row(d, revision_id="rev-1"))
make("naive-revision-recorded-at", A, "timestamp_invalid", "A revision row's recorded_at carries a UTC offset.", lambda d, j: d["rule_revisions"][0].update(recorded_at="2026-10-05T17:00:00"))
make("self-signed-revision-accepted", A, "self_signed_row_accepted", "A self-signed row is refused and kept as a refusal row; it never appears among accepted rows.", lambda d, j: extra_row(d, signer="synthetic-principal:reviser"))
make("signer-not-in-configured-set", A, "signer_not_configured", "With the configured signer set supplied, an accepted row's signer is in it.", lambda d, j: extra_row(d, signer="synthetic-principal:stranger"))
make("declared-arity-on-a-policy-row", A, "declared_arity_on_non_registry_row", "Arity is declared at signing on reason registry rows only.", lambda d, j: d["rule_revisions"][0].update(declared_arity={"policy_status_unknown": 1}))
make("supersedes-a-row-that-does-not-exist", A, "supersedes_unknown", "A row supersedes an earlier row of the same rule.", lambda d, j: extra_row(d, supersedes="rev-none"))
make("supersedes-a-row-of-another-rule", A, "supersedes_unknown", "Supersession stays within one rule_ref.", lambda d, j: extra_row(d, rule_ref="urn:cognous:policy:other", from_digest=None, supersedes="rev-1"))
make("from-digest-is-not-the-adopted-digest", A, "from_digest_mismatch", "A signed row's from_digest is the digest currently adopted for the rule.", lambda d, j: extra_row(d, from_digest="sha256:" + "0" * 64))
make("adoption-row-with-a-from-digest", A, "from_digest_mismatch", "An adoption row (nothing adopted yet) has a null from_digest.", lambda d, j: d["rule_revisions"][0].update(from_digest=D2))

# ---- refusal rows
make("duplicate-refusal-id", RF, "duplicate_refusal_id", "Refusal ids are unique.", lambda d, j: d["rule_revision_refusals"][1].update(refusal_id=d["rule_revision_refusals"][0]["refusal_id"]))
make("naive-refusal-recorded-at", RF, "timestamp_invalid", "A refusal row's recorded_at carries a UTC offset.", lambda d, j: d["rule_revision_refusals"][0].update(recorded_at="2026-10-05T17:00:00"))
make("refusal-reasons-not-sorted", RF, "refusal_reasons_not_canonical", "Reasons are sorted and unique, as the producer writes them.", lambda d, j: d["rule_revision_refusals"][3].update(reasons=["rule_revision_from_digest_mismatch", "rule_revision_duplicate"]))
make("self-signed-reason-for-a-distinct-signer", RF, "refusal_reason_mismatch", "self_signed_revision_row is listed only when the signer is the reviser.", lambda d, j: d["rule_revision_refusals"][0]["revision"].update(signer="synthetic-principal:signer"))
make("self-signed-row-without-the-reason", RF, "refusal_reason_mismatch", "A self-signed revision is refused for being self-signed.", lambda d, j: d["rule_revision_refusals"][2]["revision"].update(signer="synthetic-principal:reviser"))
make("duplicate-reason-for-an-unused-id", RF, "refusal_reason_mismatch", "rule_revision_duplicate needs an accepted row with the same revision id.", lambda d, j: d["rule_revision_refusals"][3]["revision"].update(revision_id="rev-99"))
make("supersedes-reason-without-supersedes", RF, "refusal_reason_mismatch", "rule_revision_supersedes_unknown needs a supersedes member.", lambda d, j: d["rule_revision_refusals"][4]["revision"].update(supersedes=None))
make("from-digest-reason-for-an-unsigned-row", RF, "refusal_reason_mismatch", "The from_digest chain is checked only for signed rows (an unsigned row never counts).", lambda d, j: d["rule_revision_refusals"][2]["revision"].update(signer=None))
make("configured-signer-listed-as-not-configured", RF, "refusal_reason_mismatch", "With the signer set supplied, signer_not_configured names a signer outside it.", lambda d, j: d["rule_revision_refusals"][1]["revision"].update(signer="synthetic-principal:signer"))

# ---- identity rows (document alone)
make("duplicate-identity-row", A, "duplicate_identity_row", "One identity row per decision or refusal.", lambda d, j: d["identity_rows"].append(copy.deepcopy(d["identity_rows"][0])))
make("naive-identity-row-time", A, "timestamp_invalid", "An identity row's recorded_at carries a UTC offset.", lambda d, j: d["identity_rows"][0].update(recorded_at="2026-10-05T19:00:00"))
make("unknown-list-misses-an-unadopted-rule", U, "rule_identity_unknown_mismatch", "unknown lists, sorted, exactly the rules whose state is not adopted.", lambda d, j: d["identity_rows"][0]["rule_identity"].update(unknown=[]))
make("finding-listed-twice", U, "duplicate_finding", "A finding is listed once.", lambda d, j: d["identity_rows"][0]["rule_identity"]["rules"][POLICY]["findings"].append("unsigned_revision_row"))
def unknown_through_match(d, j):
    ri = d["identity_rows"][0]["rule_identity"]; ri["rules"][POLICY]["state"] = "unknown"; ri["unknown"] = [POLICY]
make("adopted-verification-level-with-unknown-state", A, "verified_through_state_mismatch", "adopted if and only if verification reached digest_matches_signed_revision.", unknown_through_match)
make("no-signed-revision-finding-missing", U, "finding_level_mismatch", "no_signed_revision if and only if no signed independent row was found.", lambda d, j: d["identity_rows"][0]["rule_identity"]["rules"][POLICY]["findings"].remove("no_signed_revision"))
make("null-digest-without-the-absent-finding", U, "observed_digest_finding_mismatch", "observed_digest_absent if and only if the observed digest is null.", lambda d, j: d["identity_rows"][0]["rule_identity"]["rules"][POLICY].update(digest=None))
def recomputed(d, j):
    ri = d["identity_rows"][0]["rule_identity"]
    ri["rules"][POLICY].update(state="unknown", verified_through="signer_independent_and_configured", findings=["digest_mismatch_with_adopted"]); ri["unknown"] = [POLICY]
make("identity-contradicts-the-revision-rows", A, "rule_identity_recomputed_mismatch", "The identity row says unknown through level 2 but the signed row recorded before the decision adopts the digest.", recomputed)
make("findings-miss-the-unsigned-superseded-row", S_, "rule_identity_findings_mismatch", "The unsigned superseded row is still a finding on the adopted rule.", lambda d, j: [x["rule_identity"]["rules"][POLICY].update(findings=[]) for x in d["identity_rows"]])

# ---- trend reports
def one_flag(d):
    rep = d["trend_reports"][0]["report"]; rep["rows_predating_adoption"] = rep["rows_predating_adoption"][:1]; rep["flagged_row_count"] = 1
make("trend-annotation-incomplete", T1, "trend_annotation_incomplete", "The annotation members are all present or all absent.", lambda d, j: d["trend_reports"][0]["report"].pop("flagged_row_count"))
make("duplicate-flagged-row", T1, "duplicate_flagged_row", "A row is flagged once.", lambda d, j: d["trend_reports"][0]["report"]["rows_predating_adoption"].append(copy.deepcopy(d["trend_reports"][0]["report"]["rows_predating_adoption"][0])))
make("naive-flagged-row-time", T1, "timestamp_invalid", "Flagged times carry a UTC offset.", lambda d, j: (one_flag(d), d["trend_reports"][0]["report"]["rows_predating_adoption"][0].update(row_time="2026-10-05T19:00:00")))
make("flagged-row-not-before-adoption", T1, "row_not_before_adoption", "A flagged row predates its version's adoption instant.", lambda d, j: (one_flag(d), d["trend_reports"][0]["report"]["rows_predating_adoption"][0].update(row_time="2026-10-05T19:00:09+00:00")))
make("adoption-time-is-not-the-adoption-row", T1, "adoption_time_mismatch", "adoption_time is the earliest adoption row for the version.", lambda d, j: (one_flag(d), d["trend_reports"][0]["report"]["rows_predating_adoption"][0].update(adoption_time="2026-10-05T19:00:04+00:00")))
def no_source(d, j):
    one_flag(d); row = d["rule_revisions"][0]; row["rule_kind"] = "gate_implementation"; row.pop("declared_arity", None)
make("flagged-version-has-no-adoption-row", T1, "adoption_source_missing", "With the run record supplied, a flagged version has a reason_registry revision row or a vocabulary change adopting it.", no_source, journal=True)
make("flagged-count-wrong", T1, "flagged_count_mismatch", "flagged_row_count is the number of distinct flagged rows.", lambda d, j: d["trend_reports"][0]["report"].update(flagged_row_count=3))
make("tainted-flag-contradicts-reasons", T1, "taint_flag_inconsistent", "tainted_for_trend if and only if taint_reasons is non-empty.", lambda d, j: d["trend_reports"][0]["report"]["series"][0].update(tainted_for_trend=False))
make("row-predates-adoption-taint-without-a-flagged-row", T2, "taint_without_flagged_row", "row_predates_adoption needs a flagged row of the series' version.", lambda d, j: d["trend_reports"][0]["report"]["series"][1].update(taint_reasons=["row_predates_adoption"]))
make("pre-split-taint-without-a-split", T2, "pre_split_without_change", "With the run record supplied, pre_split_count needs a split of the version that retires the code.", lambda d, j: j.update(vocabulary_changes=[]), journal=True)
def untaint(d, j):
    for s in d["trend_reports"][0]["report"]["series"]: s.update(tainted_for_trend=False, taint_reasons=[])
make("flagged-rows-without-any-taint", T1, "flagged_row_without_taint", "Flagged rows of a version mark a series of that version.", untaint)
make("duplicate-trend-report-id", T1, "duplicate_report_id", "Report ids are unique within a list.", lambda d, j: d["trend_reports"].append(copy.deepcopy(d["trend_reports"][0])))

# ---- arity reports
def naive_asof(d, j):
    r = d["arity_reports"][0]; r["measured"]["as_of"] = "2026-10-05T19:00:10"
    for f in r["flags"]: f["as_of"] = "2026-10-05T19:00:10"
make("naive-arity-as-of", AR, "timestamp_invalid", "as_of carries a UTC offset.", naive_asof)
make("measured-count-is-not-the-shape-count", AW, "measured_count_mismatch", "measured is the number of distinct operand shapes.", lambda d, j: d["arity_reports"][0]["measured"]["codes"]["policy_status_unknown"].update(measured=1))
def swap_shapes(d, j): s = d["arity_reports"][0]["measured"]["codes"]["policy_status_unknown"]["shapes"]; s.reverse()
make("arity-shapes-not-sorted", AW, "arity_shapes_invalid", "Shapes are sorted lists of distinct input types, themselves sorted and distinct.", swap_shapes)
make("declared-from-names-no-row", AR, "declared_from_unknown", "declared_from names a reason_registry revision row of the document.", lambda d, j: d["arity_reports"][0].update(declared_from="rev-none"))
make("declared-arity-differs-from-the-signed-row", AR, "declared_arity_mismatch", "declared is the declared_arity of the row it names.", lambda d, j: d["rule_revisions"][0].update(declared_arity={"policy_status_unknown": 1, "grant_revoked": 1}))
make("exceeds-flag-missing", AR, "arity_flags_mismatch", "Flags are exactly those derived from declared and measured arity.", lambda d, j: d["arity_reports"][0].update(flags=d["arity_reports"][0]["flags"][:1]))
make("duplicate-arity-report-id", AR, "duplicate_report_id", "Report ids are unique within a list.", lambda d, j: d["arity_reports"].append(copy.deepcopy(d["arity_reports"][0])))

# ---- recomputability reports
make("flag-where-declared-equals-derived", RC, "recomputability_flag_inconsistent", "A flag is raised only where declared and derived differ.", lambda d, j: d["recomputability_reports"][0]["flags"][0].update(derived="recomputable"))
make("declared-kind-differs-from-the-registry-kind", RC, "declared_kind_mismatch", "declared is the registry's reason_kind for the code, listed in declared_kinds.", lambda d, j: d["recomputability_reports"][0]["declared_kinds"].update(grant_revoked="typed_only"))
make("flag-names-a-row-that-does-not-exist", RC, "recomputability_row_missing", "The flag names a row of the run record's list.", lambda d, j: d["recomputability_reports"][0]["flags"][0].update(row=9), journal=True)
def code_not_in_row(d, j):
    rep = d["recomputability_reports"][0]; rep["declared_kinds"] = {"status_unreadable": "typed_only"}
    rep["flags"] = [{"row": 1, "code": "status_unreadable", "declared": "typed_only", "derived": "recomputable", "flag": "declared_underclaim"}]
make("flagged-code-is-not-a-reason-of-the-row", RC, "recomputability_code_not_in_row", "The flagged code is one of the row's reasons.", code_not_in_row, journal=True)
def recomputable_row(d, j):
    for x in j["decisions"][1]["resolution_inputs"]:
        if not x.get("observed"): x["observed"] = {"manifest_id": "synthetic"}
make("derived-kind-differs-from-the-retained-inputs", RC, "derived_recomputability_mismatch", "derived is recomputed from the row's retained inputs: every input here carries its operands, so the row is recomputable, not typed_only.", recomputable_row, journal=True)
make("false-overclaim-where-operands-are-absent", RC, "recomputability_flag_inconsistent", "declared_overclaim is reserved for rows whose operands are present and show the declared kind cannot hold; operands absent is derivation_unavailable (declared recomputable, derived underivable).", lambda d, j: d["recomputability_reports"][0]["flags"][0].update(flag="declared_overclaim"))
make("duplicate-recomputability-report-id", RC, "duplicate_report_id", "Report ids are unique within a list.", lambda d, j: d["recomputability_reports"].append(copy.deepcopy(d["recomputability_reports"][0])))

# ---- run record context
make("journal-run-mismatch", A, "journal_run_mismatch", "The document and the run record describe one run.", lambda d, j: j.update(run_id="run-2"), journal=True)
make("identity-row-names-no-decision", A, "identity_row_unknown_row", "An identity row names a decision or refusal of the run record.", lambda d, j: d["identity_rows"][0].update(row_id="syn-decision-9"), journal=True)
make("identity-row-time-differs-from-the-decision", A, "identity_row_time_mismatch", "recorded_at is the row's decided_at (decision) or recorded_at (refusal).", lambda d, j: d["identity_rows"][0].update(recorded_at="2026-10-05T19:00:01+00:00"), journal=True)
make("identity-row-differs-from-the-decision", A, "identity_row_mismatch", "The identity row is the decision's rule_identity, member for member.", lambda d, j: j["decisions"][0]["rule_identity"]["rules"][POLICY].update(digest="sha256:" + "9" * 64), journal=True)
make("policy-read-without-a-rule-identity", A, "policy_input_without_rule_identity", "Every policy the row read has a rule identity entry.", lambda d, j: [x.update(input_id="urn:cognous:policy:other") for x in j["decisions"][0]["resolution_inputs"] if x["input_type"] == "policy"], journal=True)
def drop_reason(d, j): j["decisions"][0]["reasons"].remove("policy_status_unknown")
make("unadopted-policy-without-the-hold-reason", U, "unadopted_policy_not_held", "A policy that does not resolve to adopted holds with policy_status_unknown.", drop_reason, journal=True)
make("unadopted-policy-decision-authorized", E_, "unadopted_policy_not_held", "A decision on a policy digest that is not adopted is a hold, never authorized.", lambda d, j: j["decisions"][1].update(result="authorized"), journal=True)

bad = [r for r in results if r[2] != [r[1]]]
for r in bad: print("MISMATCH", r)
print(len(results), "invalid fixtures,", len(bad), "mismatches")
