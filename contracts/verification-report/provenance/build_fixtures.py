"""Write the fixtures of the verification-report contract.

The valid fixtures are HAND-WRITTEN (synthetic): no producer existed when this draft was written. Digests are SHA-256 over
labelled placeholder strings, not over real files. When the verifier (cogno-us/cognous-open-control-stack-verifier,
command ``cognous-verify``) emits reports, captures replace or join these; see README, Divergences.
The invalid fixtures are single-defect mutations of the valid ones. Run from the repository root:

    python contracts/verification-report/provenance/build_fixtures.py
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTRACT_DIR = HERE.parent
_spec = importlib.util.spec_from_file_location("vr_validate", CONTRACT_DIR / "validate.py")
vr = importlib.util.module_from_spec(_spec)
sys.modules["vr_validate"] = vr
_spec.loader.exec_module(vr)

PROFILE = vr.CANONICALIZATION_PROFILE


def d(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode()).hexdigest()


def inputs(*items):
    rows = [{"role": r, "name": n, "digest": d(n), "size_bytes": 1000 + len(n)} for r, n in items]
    return sorted(rows, key=lambda i: (i["role"], i["name"], i["digest"]))


def subject(*items):
    rows = inputs(*items)
    return {
        "canonicalization_profile": PROFILE, "inputs": rows, "inputs_digest": vr.commitment(rows),
        "pinned": {"controller_revision": "87f02336", "reason_registry_digest": d("reason-registry"),
                   "contract_versions": {"control-plane-journal": "0.1.0-draft", "execution-attempt-lifecycle": "0.1.0-draft"}},
    }


def tally(c, n_cnc, r):
    return {"confirmed": c, "could_not_check": n_cnc, "refuted": r, "n": c + n_cnc + r}


def check(cid, tier, c=1, cnc=0, r=0, reason=None, findings=()):
    t = tally(c, cnc, r)
    return {"check_id": cid, "tier": tier, "verdict": vr.derived_check_verdict(t), "tally": t,
            "could_not_check_reason": reason, "findings": list(findings)}


def summary(checks):
    out = {"checks": len(checks), "confirmed": 0, "could_not_check": 0, "refuted": 0}
    for c in checks:
        out[c["verdict"]] += 1
    return out


NON_CLAIM_TEXT = {
    "relative_to_pinned_controller": "The result is relative to the controller revision, contract draft versions and reason registry named in subject.pinned; it does not carry to any other revision.",
    "semantic_quality_not_certified": "No claim that a decision was correct, that a policy was adequate or that a grant was lawfully issued.",
    "receipt_source_bounded": "Destination ledger rows are executor-written, unsequenced and unsigned: no claim that the ledger is complete or unforged, or that an effect occurred in the world.",
    "self_consistent_forgery_not_detected": "A record rewritten with every affected commitment recomputed is accepted; no external anchor exists.",
    "not_an_attestation": "This is a verification report. It is not an attestation, not an Index or BitRep signature and not an authorization; it grants and denies nothing and is never an input to a grant or decision.",
    "parse_strictness_is_refusal_not_repair": "An input refused at the wire level is reported as refused; the verifier does not normalize it and re-run.",
    "no_v1_scope_claim": "Nothing here changes the V1 scope, the failure register or any qualified row.",
    "differential_agreement_is_not_equivalence": "Agreement between verifier and controller on a corpus is not equivalence outside that corpus.",
    "no_imported_headline_numbers": "No figure from any paper is a target, baseline or expectation; the only numbers are counts from the corpora named here.",
    "seeds_are_regression_not_detection": "Seed corpora are regression checks; detection figures come only from the generated held-out corpus.",
    "witness_is_not_publication": "A witness file that matches the records shows only that match: not that it was published, that it was published in time, or that any party independent of the record keeper held it.",
}


def non_claims(mutation=False):
    ids = list(vr.CORE_NON_CLAIMS) + (list(vr.MUTATION_NON_CLAIMS) if mutation else [])
    return [{"id": i, "statement": NON_CLAIM_TEXT[i]} for i in ids]


def verifier():
    return {"name": "cognous-open-control-stack-verifier", "version": "0.0.0-handwritten-fixture", "command": "cognous-verify",
            "source_revision": "0000000", "canonicalization_profile": PROFILE}


def report(rid, subj, checks, tiers=("V1", "V2"), mutation=None):
    return {
        "contract": "verification-report", "contract_version": "0.1.0-draft", "profile": "verification-report/0.1",
        "report_kind": "verification_report", "report_id": rid, "generated_at": "2026-10-18T12:00:00+00:00",
        "verifier": verifier(), "subject": subj, "scope": {"semantic_quality": "not_assessed", "tiers_run": list(tiers)},
        "checks": checks, "summary": summary(checks), "does_not_prove": non_claims(mutation is not None),
        "mutation_report": mutation,
    }


def trow(cat, gen, rej, acc, abst=0, err=0, noop=0, na=0, intended=None, expected="reject", impact=None, seed=False):
    n_eff = gen - noop - na
    assert rej + acc + abst + err == n_eff, cat
    row = {"category": cat, "expected_verdict": expected, "n_gen": gen, "n_noop": noop, "n_na": na, "n_eff": n_eff,
           "verdicts": {"reject": rej, "accept": acc, "abstain": abst, "error": err},
           "detection": None, "regression": None, "false_acceptance": None, "abstained": None, "errored": None, "metric_impact": None}
    if seed:
        row["regression"] = {"refused_with_intended_code": {"k": rej if intended is None else intended, "n": n_eff}}
        return row
    row["detection"] = {"any_code": {"k": rej, "n": n_eff}, "intended_code": {"k": rej if intended is None else intended, "n": n_eff}}
    row["false_acceptance"] = {"k": acc, "n": n_eff}
    row["abstained"] = {"k": abst, "n": n_eff}
    row["errored"] = {"k": err, "n": n_eff}
    if impact is None:
        row["metric_impact"] = {"conditioned_on": "false_acceptance", "changed": {"k": None if acc == 0 else 0, "n": acc}, "deltas": []}
    else:
        row["metric_impact"] = impact
    return row


def qrow():
    return {"category": "Q", "expected_verdict": "not_applicable", "n_gen": 0, "n_noop": 0, "n_na": 0, "n_eff": 0,
            "verdicts": {"reject": 0, "accept": 0, "abstain": 0, "error": 0}, "detection": None, "regression": None,
            "false_acceptance": None, "abstained": None, "errored": None, "metric_impact": None}


def mutation_report(extra_scenarios=False):
    impact = {"conditioned_on": "false_acceptance", "changed": {"k": 3, "n": 4},
              "deltas": [{"measure": "unauthorized_effects", "nonzero_mutants": 3, "min": 0, "max": 1},
                         {"measure": "held_count", "nonzero_mutants": 1, "min": -1, "max": 0}]}
    generated = [
        trow("W1", 20, 20, 0), trow("D1", 20, 19, 0, abst=1, intended=18),
        trow("R4", 12, 8, 4, impact=impact), trow("R5", 10, 9, 0, err=1),
        trow("B", 8, 0, 8, expected="accept", impact={"conditioned_on": "false_acceptance", "changed": {"k": 0, "n": 8}, "deltas": []}),
        trow("R6", 5, 0, 5, expected="accept", impact={"conditioned_on": "false_acceptance", "changed": {"k": 0, "n": 5}, "deltas": []}),
        trow("F", 6, 0, 6, expected="accept", impact={"conditioned_on": "false_acceptance", "changed": {"k": 0, "n": 6}, "deltas": []}),
        qrow(),
        trow("I5", 10, 7, 0, noop=2, na=1),
    ]
    scenarios = None
    if extra_scenarios:
        scenarios = [{"scenario_id": "SCN-refund-1", "categories": [trow("W1", 5, 5, 0), trow("D1", 5, 5, 0)]},
                     {"scenario_id": "SCN-refund-2", "categories": [trow("W1", 15, 15, 0)]}]
    return {
        "report_only": True, "operator_set_digest": d("operators.json"), "seed": 20261018, "frozen_revision": "qual-0000000",
        "family_t": [
            {"corpus_id": "t-seed-ODES", "provenance": "seed", "corpus_digest": d("odes-fixtures"),
             "categories": [trow("S1", 6, 6, 0, seed=True), trow("D1", 4, 4, 0, seed=True, intended=3), trow("J2", 5, 5, 0, seed=True)], "scenarios": None},
            {"corpus_id": "t-generated-heldout", "provenance": "generated", "corpus_digest": d("generated-corpus"),
             "categories": generated, "scenarios": scenarios},
        ],
        "family_s": [{"corpus_id": "s-context", "context_only": True, "rows": [
            {"source_id": "cp-adversarial-mutations", "n_cases": 3, "detected": 3, "survived": 0, "errored": 0},
            {"source_id": "hub-destination-admission-mutations", "n_cases": 13, "detected": 13, "survived": 0, "errored": 0}]}],
        "clean": [
            {"corpus_id": "clean-generated", "provenance": "generated", "corpus_digest": d("clean-generated"),
             "rows": [{"category": "W1", "false_rejection": {"k": 0, "n": 30}}, {"category": "B", "false_rejection": {"k": 1, "n": 30}}]},
            {"corpus_id": "clean-odes-valid", "provenance": "seed_valid_fixtures", "corpus_digest": d("odes-valid"),
             "rows": [{"category": "W1", "false_rejection": {"k": 0, "n": 33}}]},
        ],
    }


def mutation_subject():
    return subject(("operator_set", "operators.json"), ("corpus", "odes-fixtures"), ("corpus", "generated-corpus"),
                   ("corpus", "clean-generated"), ("corpus", "odes-valid"))


def valid():
    out = {}
    base_inputs = (("run_record", "run-record.json"), ("proposal_export", "proposal.json"))
    chk = [check("v1.wire.strict-parse", "V1", c=3), check("v1.wire.closed-members", "V1", c=3),
           check("v2.identity.effect-id", "V2", c=2), check("v2.decision.result-matches-reasons", "V2", c=2)]
    out["trace-all-confirmed"] = ("Every check confirmed over its tally; no mutation report.", report("rep-1", subject(*base_inputs), chk))
    f = [{"code": "wire_duplicate_member", "locator": "$.decisions[0].result", "detail": "member result appears twice in the raw text"}]
    chk = [check("v1.wire.strict-parse", "V1", c=2, r=1, findings=f), check("v2.identity.effect-id", "V2", c=2)]
    out["trace-refuted-with-findings"] = ("A wire-level refusal is a refuted check with a finding; other checks stay confirmed.", report("rep-2", subject(*base_inputs), chk))
    chk = [check("v1.wire.strict-parse", "V1", c=3),
           check("v2.decision.operands-declared", "V2", c=1, cnc=2, reason="input_absent"),
           check("v2.identity.effect-id", "V2", c=2, cnc=0)]
    out["trace-could-not-check"] = ("Where the record does not retain operands the item is could_not_check, never confirmed; the verdict is abstain.", report("rep-3", subject(*base_inputs), chk))
    chk = [check("v1.wire.strict-parse", "V1", c=3), check("v2.journal.protocol", "V2", c=1, cnc=1, r=1, reason="input_absent", findings=f),
           check("v4.ledger.effects-have-decisions", "V4", c=4)]
    out["trace-three-verdicts"] = ("One check holding confirmed, could_not_check and refuted items; refuted wins, so the derived outcome is reject.",
        report("rep-4", subject(*base_inputs, ("destination_ledger", "ledger.json")), chk, tiers=("V1", "V2", "V4")))
    out["mutation-report-full"] = ("A mutation report: seed (regression) and generated (held-out) family T corpora, family S context, two clean corpora, F/R6/Q/B rows.",
        report("rep-5", mutation_subject(), [], mutation=mutation_report()))
    out["mutation-report-with-per-scenario-tables"] = ("The same with per-scenario tables on the generated corpus.",
        report("rep-6", mutation_subject(), [], mutation=mutation_report(True)))
    out["trace-with-mutation-report"] = ("A trace report that also carries the mutation tables as the optional member.",
        report("rep-7", mutation_subject(), [check("v1.wire.strict-parse", "V1", c=3)], mutation=mutation_report()))
    ext = report("rep-8", subject(*base_inputs), [check("v1.wire.strict-parse", "V1", c=3)])
    ext["extensions"] = {"x-run-label": "nightly"}
    ext["checks"][0]["extensions"] = {"x-note": "preserved"}
    out["extension-namespace-members-preserved"] = ("x- members on the document and on a check are accepted, ignored for contract logic and preserved.", ext)
    return out


def bad(base, fn):
    doc = copy.deepcopy(base)
    fn(doc)
    return doc


def refresh_subject(doc):
    doc["subject"]["inputs_digest"] = vr.commitment(doc["subject"]["inputs"])


def invalid(v):
    t = v["trace-three-verdicts"][1]
    a = v["trace-all-confirmed"][1]
    m = v["mutation-report-full"][1]
    out = {}

    def add(fid, code, base, fn, reason):
        out[fid] = (code, reason, bad(base, fn))

    def gen(doc):
        return doc["mutation_report"]["family_t"][1]

    def gen_row(doc, cat):
        return next(r for r in gen(doc)["categories"] if r["category"] == cat)

    def seed_row(doc, cat):
        return next(r for r in doc["mutation_report"]["family_t"][0]["categories"] if r["category"] == cat)

    # structure
    add("attestation-member", "undeclared_member", a, lambda x: x.update({"attestation": {"issuer": "verifier"}}), "A report carries no attestation member: it is a verification report.")
    add("report-kind-attestation", "schema_violation", a, lambda x: x.update({"report_kind": "attestation"}), "report_kind is verification_report and nothing else.")
    add("composite-score-member", "undeclared_member", a, lambda x: x["summary"].update({"score": 0.97}), "There is no composite score member.")
    add("semantic-quality-certified", "unknown_enum_value", a, lambda x: x["scope"].update({"semantic_quality": "certified"}), "Semantic quality is not_assessed; certified is not a value.")
    def claim_v3(x):
        x["scope"]["tiers_run"].append("V3")
        x["does_not_prove"].append({"id": "witness_is_not_publication", "statement": NON_CLAIM_TEXT["witness_is_not_publication"]})
    add("tier-v3-claimed-without-input", "v3_input_missing", a, claim_v3, "Tier V3 re-derives from a witness file or a holder inventory; a report that says it ran V3 names one of them as an input (draft revision 2026-10-18: this fixture was `tier-v3-claimed`, refused as an unknown tier before V3 was admitted).")
    add("tier-v5-claimed", "unknown_enum_value", a, lambda x: x["scope"]["tiers_run"].append("V5"), "The tier set is closed (V1, V2, V3, V4); another tier is a major bump.")
    add("v3-check-tier-not-run", "check_tier_not_run", a, lambda x: (x["checks"].append(check("v3.witness.records", "V3", c=1)), x.update({"summary": summary(x["checks"])})), "A V3 check in a report whose scope does not list V3 (and with no witness input) is refused like any check of a tier not run.")
    add("rate-without-denominator", "schema_violation", m, lambda x: gen_row(x["mutation_report"] and x, "W1").update({"false_acceptance": 0.0}), "A rate is a k/n object; a bare number is refused.")
    add("pinned-controller-revision-missing", "schema_violation", a, lambda x: x["subject"]["pinned"].pop("controller_revision"), "A report names the controller revision it is relative to.")
    add("extension-key-without-x-prefix", "invalid_extension_key", a, lambda x: x.update({"extensions": {"note": 1}}), "Extension names start with x-.")
    add("unsupported-contract-version", "unsupported_contract_version", a, lambda x: x.update({"contract_version": "9.0.0"}), "Only 0.1.0-draft is implemented.")
    add("unknown-canonicalization-profile", "unknown_enum_value", a, lambda x: x["subject"].update({"canonicalization_profile": "rfc8785-jcs"}), "The pinned profile is a closed set of one; another profile is a major bump.")
    add("empty-tally-denominator", "schema_violation", a, lambda x: x["checks"][0]["tally"].update({"confirmed": 0, "n": 0}), "A check is over at least one item.")
    # document rules
    add("naive-generated-at", "timestamp_invalid", a, lambda x: x.update({"generated_at": "2026-10-18T12:00:00"}), "Times carry an offset.")
    def dup_in(x):
        x["subject"]["inputs"].append(copy.deepcopy(x["subject"]["inputs"][0]))
        refresh_subject(x)
    add("duplicate-input", "duplicate_input", a, dup_in, "One input per role and name.")
    def reorder(x):
        x["subject"]["inputs"].reverse(); refresh_subject(x)
    add("inputs-not-in-canonical-order", "inputs_not_canonical_order", a, reorder, "Inputs are listed in sorted order so the subject digest is reproducible.")
    add("subject-digest-mismatch", "subject_digest_mismatch", a, lambda x: x["subject"].update({"inputs_digest": d("other")}), "inputs_digest is the commitment over the inputs as written.")
    add("input-altered-after-digest", "subject_digest_mismatch", a, lambda x: x["subject"]["inputs"][0].update({"digest": d("tampered")}), "An input changed without recomputing the subject digest.")
    add("pinned-contract-versions-empty", "pinned_contract_versions_empty", a, lambda x: x["subject"]["pinned"].update({"contract_versions": {}}), "A report names the contract draft versions it used.")
    add("duplicate-check-id", "duplicate_check_id", a, lambda x: (x["checks"].append(copy.deepcopy(x["checks"][0])), x.update({"summary": summary(x["checks"])})), "Check ids are unique.")
    add("check-tier-not-run", "check_tier_not_run", a, lambda x: x["checks"][0].update({"tier": "V4"}), "A check belongs to a tier the scope says ran.")
    add("tally-does-not-sum", "tally_sum_mismatch", a, lambda x: x["checks"][0]["tally"].update({"n": 9}), "confirmed + could_not_check + refuted equals n.")
    add("confirmed-verdict-over-a-refuted-item", "check_verdict_inconsistent", t, lambda x: (x["checks"][1].update({"verdict": "confirmed"}), x.update({"summary": summary(x["checks"])})), "One refuted item makes the check refuted.")
    add("could-not-check-without-reason", "could_not_check_unexplained", t, lambda x: x["checks"][1].update({"could_not_check_reason": None}), "An item that could not be checked says why.")
    add("reason-without-could-not-check", "could_not_check_reason_unexpected", a, lambda x: x["checks"][0].update({"could_not_check_reason": "input_absent"}), "A reason with nothing that could not be checked.")
    add("refuted-without-finding", "refuted_without_finding", t, lambda x: x["checks"][1].update({"findings": []}), "A refuted check names what refuted it.")
    add("finding-on-a-confirmed-check", "finding_without_refutation", a, lambda x: x["checks"][0].update({"findings": [{"code": "wire_duplicate_member", "locator": "$", "detail": "x"}]}), "Findings belong to a refuted check.")
    add("summary-counts-disagree", "summary_mismatch", t, lambda x: x["summary"].update({"confirmed": 3}), "The summary counts the checks as written.")
    add("report-states-nothing", "empty_report", a, lambda x: x.update({"checks": [], "summary": summary([])}), "No check and no mutation report is an empty report.")
    add("duplicate-non-claim", "duplicate_non_claim", a, lambda x: x["does_not_prove"].append(copy.deepcopy(x["does_not_prove"][0])), "Each non-claim appears once.")
    add("not-an-attestation-non-claim-missing", "non_claim_missing", a, lambda x: x.update({"does_not_prove": [n for n in x["does_not_prove"] if n["id"] != "not_an_attestation"]}), "The not-an-attestation non-claim is mandatory.")
    add("semantic-quality-non-claim-missing", "non_claim_missing", a, lambda x: x.update({"does_not_prove": [n for n in x["does_not_prove"] if n["id"] != "semantic_quality_not_certified"]}), "The semantic-quality non-claim is mandatory.")
    add("does-not-prove-empty", "schema_violation", a, lambda x: x.update({"does_not_prove": []}), "The does_not_prove block cannot be empty.")
    add("seeds-non-claim-missing-with-mutation-report", "non_claim_missing", m, lambda x: x.update({"does_not_prove": [n for n in x["does_not_prove"] if n["id"] != "seeds_are_regression_not_detection"]}), "A mutation report carries the seeds-are-regression non-claim.")
    add("headline-numbers-non-claim-missing", "non_claim_missing", m, lambda x: x.update({"does_not_prove": [n for n in x["does_not_prove"] if n["id"] != "no_imported_headline_numbers"]}), "A mutation report carries the no-imported-numbers non-claim.")
    # mutation report
    add("fraction-k-above-n", "fraction_out_of_range", m, lambda x: x["mutation_report"]["clean"][0]["rows"][0].update({"false_rejection": {"k": 31, "n": 30}}), "k cannot exceed n.")
    add("effective-count-mismatch", "effective_count_mismatch", m, lambda x: gen_row(x, "I5").update({"n_eff": 9}), "n_eff = n_gen - n_noop - n_na.")
    add("verdict-counts-do-not-sum", "verdict_sum_mismatch", m, lambda x: gen_row(x, "W1")["verdicts"].update({"accept": 1}), "reject + accept + abstain + error equals n_eff.")
    add("semantic-category-reports-a-rate", "not_applicable_reports_a_rate", m, lambda x: gen_row(x, "Q").update({"false_acceptance": {"k": 0, "n": 0}}), "Q shows n/a, never a rate.")
    add("seed-corpus-reports-detection", "seed_corpus_reports_detection", m, lambda x: seed_row(x, "S1").update({"detection": {"any_code": {"k": 6, "n": 6}, "intended_code": {"k": 6, "n": 6}}}), "Seeds are regression, not detection.")
    add("seed-corpus-reports-metric-impact", "seed_corpus_reports_metric_impact", m, lambda x: seed_row(x, "S1").update({"metric_impact": {"conditioned_on": "false_acceptance", "changed": {"k": None, "n": 0}, "deltas": []}}), "Metric impact is on the generated corpus only.")
    add("seed-regression-denominator-wrong", "regression_mismatch", m, lambda x: seed_row(x, "S1")["regression"]["refused_with_intended_code"].update({"n": 7}), "Regression is over n_eff.")
    add("seed-regression-above-rejected", "localized_exceeds_detected", m, lambda x: (seed_row(x, "S1")["verdicts"].update({"reject": 5, "accept": 1}), seed_row(x, "S1")["regression"]["refused_with_intended_code"].update({"k": 6})), "Intended-code refusals cannot exceed rejections.")
    add("generated-corpus-reports-regression", "generated_corpus_reports_regression", m, lambda x: gen_row(x, "W1").update({"regression": {"refused_with_intended_code": {"k": 20, "n": 20}}}), "Regression figures belong to the seed corpus.")
    add("generated-detection-missing", "rate_missing", m, lambda x: gen_row(x, "W1").update({"detection": None}), "An applicable generated category reports detection.")
    add("metric-impact-missing", "rate_missing", m, lambda x: gen_row(x, "W1").update({"metric_impact": None}), "Metric impact is n/a (k null) when nothing was accepted, not absent.")
    add("detection-counts-abstain", "detection_mismatch", m, lambda x: gen_row(x, "D1")["detection"].update({"any_code": {"k": 20, "n": 20}}), "Abstain is not credited as detection.")
    add("localized-detection-above-detection", "localized_exceeds_detected", m, lambda x: gen_row(x, "D1")["detection"].update({"intended_code": {"k": 20, "n": 20}}), "Intended-code detection cannot exceed detection.")
    add("false-acceptance-as-one-minus-detection", "false_acceptance_mismatch", m, lambda x: gen_row(x, "D1").update({"false_acceptance": {"k": 1, "n": 20}}), "False acceptance is accept over n_eff, not 1 - detection.")
    add("abstain-hidden", "abstained_mismatch", m, lambda x: gen_row(x, "D1").update({"abstained": {"k": 0, "n": 20}}), "Abstain is reported on its own line.")
    add("error-counted-elsewhere", "errored_mismatch", m, lambda x: gen_row(x, "R5").update({"errored": {"k": 0, "n": 10}}), "Error is reported on its own line.")
    add("metric-impact-denominator-is-n-eff", "metric_impact_denominator_mismatch", m, lambda x: gen_row(x, "R4")["metric_impact"]["changed"].update({"n": 12}), "Metric impact is conditioned on false acceptance.")
    add("metric-impact-zero-accepted-reads-zero", "metric_impact_na_inconsistent", m, lambda x: gen_row(x, "W1")["metric_impact"]["changed"].update({"k": 0}), "With 0 accepted the field is n/a, never 0.")
    add("metric-impact-null-with-accepted", "metric_impact_na_inconsistent", m, lambda x: gen_row(x, "R4")["metric_impact"]["changed"].update({"k": None}), "With accepted mutants k is a count.")
    add("delta-above-changed-count", "delta_inconsistent", m, lambda x: gen_row(x, "R4")["metric_impact"]["deltas"][0].update({"nonzero_mutants": 4}), "Deltas describe accepted mutants whose measures changed.")
    add("duplicate-category-in-corpus", "duplicate_category", m, lambda x: gen(x)["categories"].append(copy.deepcopy(gen_row(x, "W1"))), "One row per category in a corpus.")
    add("duplicate-category-in-clean-corpus", "duplicate_category", m, lambda x: x["mutation_report"]["clean"][0]["rows"].append(copy.deepcopy(x["mutation_report"]["clean"][0]["rows"][0])), "One row per category in a clean corpus.")
    sc = v["mutation-report-with-per-scenario-tables"][1]
    add("duplicate-scenario-id", "duplicate_scenario_id", sc, lambda x: gen(x)["scenarios"].append(copy.deepcopy(gen(x)["scenarios"][0])), "One table per scenario.")
    add("duplicate-corpus-id-across-families", "duplicate_corpus_id", m, lambda x: x["mutation_report"]["family_s"][0].update({"corpus_id": "t-seed-ODES"}), "Corpus ids are unique across family S, family T and clean lists, so denominators cannot be pooled by name.")
    add("duplicate-source-id", "duplicate_source_id", m, lambda x: x["mutation_report"]["family_s"][0]["rows"].append(copy.deepcopy(x["mutation_report"]["family_s"][0]["rows"][0])), "One row per source.")
    add("family-s-cases-do-not-sum", "case_sum_mismatch", m, lambda x: x["mutation_report"]["family_s"][0]["rows"][0].update({"detected": 2}), "detected + survived + errored equals n_cases.")
    add("family-s-without-context-only", "schema_violation", m, lambda x: x["mutation_report"]["family_s"][0].update({"context_only": False}), "Family S is context only, never merged into family T rates.")
    add("operator-set-not-a-subject-input", "operator_set_input_missing", m, lambda x: x["mutation_report"].update({"operator_set_digest": d("other-operators")}), "The operator set is an input of the subject.")
    def drop_corpus(x):
        x["subject"]["inputs"] = [i for i in x["subject"]["inputs"] if i["name"] != "generated-corpus"]
        refresh_subject(x)
    add("corpus-not-a-subject-input", "corpus_input_missing", m, drop_corpus, "Every corpus digest is an input of the subject.")
    add("report-only-false", "schema_violation", m, lambda x: x["mutation_report"].update({"report_only": False}), "The mutation report gates nothing.")
    return out


def write(kind, fid, payload):
    path = CONTRACT_DIR / "fixtures" / kind / f"{fid}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    for kind in ("valid", "invalid"):
        for old in (CONTRACT_DIR / "fixtures" / kind).glob("*.json"):
            if not old.name.startswith("v3-"):   # the v3-* fixtures are written by build_v3_fixtures.py
                old.unlink()
    v = valid()
    for fid, (reason, doc) in v.items():
        assert vr.validate(doc) == [], (fid, vr.validate(doc))
        write("valid", fid, {"fixture_id": fid, "synthetic": True, "expected_outcome": "accept", "reason": reason,
                             "expected_refusal": None, "document": doc})
    bad_docs = invalid(v)
    failures = []
    for fid, (code, reason, doc) in bad_docs.items():
        got = [x.code for x in vr.validate(doc)]
        if got != [code]:
            failures.append((fid, code, got))
            continue
        write("invalid", fid, {"fixture_id": fid, "synthetic": True, "expected_outcome": "reject", "reason": reason,
                               "expected_refusal": code, "document": doc})
    for f in failures:
        print("FAIL", f)
    print(f"valid {len(v)} invalid {len(bad_docs)} failures {len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
