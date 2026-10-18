"""Build the valid rule-revision fixtures from captured run records (step 2 of 2; step 1 is capture_fixtures.py).

    python build_fixtures.py <raw-dir> <fixtures/valid dir> <control-plane-commit>

Normalises random uuids to synthetic ids, projects each run record onto the sidecar document, wraps the producer function outputs
in their envelopes, and writes one fixture per scenario (`no-rows` is hand-built). Re-running it on the same capture reproduces the
fixtures byte for byte.
"""
import copy, json, re, sys
from pathlib import Path
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
KINDS = {"decision_id": "decision", "attempt_id": "attempt", "check_id": "check", "join_id": "join", "renewal_id": "renewal",
         "refusal_id": "refusal", "change_id": "change"}

def normalise(doc):
    """Replace random uuids by readable synthetic ids (stable order of first appearance) and the process owner."""
    text = json.dumps(doc, ensure_ascii=False)
    counters, mapping = {}, {}
    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if isinstance(v, str) and UUID.fullmatch(v) and k in KINDS and v not in mapping:
                    kind = KINDS[k]; counters[kind] = counters.get(kind, 0) + 1
                    mapping[v] = f"syn-{kind}-{counters[kind]}"
                walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(doc)
    for old, new in mapping.items(): text = text.replace(old, new)
    out = json.loads(text)
    n = [0]
    def owners(x):
        if isinstance(x, dict):
            if set(x) == {"pid", "token"}:
                key = x["token"]
                if key not in mapping:
                    n[0] += 1; mapping[key] = f"syn-owner-token-{n[0]}"
                x["pid"] = "1001"; x["token"] = mapping[key]
            else:
                for v in x.values(): owners(v)
        elif isinstance(x, list):
            for v in x: owners(v)
    owners(out)
    left = UUID.findall(json.dumps(out))
    assert not left, left
    return out

def write(dirpath, fixture):
    p = Path(dirpath) / f"{fixture['fixture_id']}.json"
    p.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

RAW, DEST, CP = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
SIGNERS = ["synthetic-principal:signer"]

def identity_rows(run):
    rows = []
    for d in run["decisions"]:
        if d.get("rule_identity"):
            rows.append({"row_type": "decision", "row_id": d["decision_id"], "recorded_at": d["decided_at"], "rule_identity": d["rule_identity"]})
    for x in run["refusals"]:
        if x.get("rule_identity"):
            rows.append({"row_type": "refusal", "row_id": x["refusal_id"], "recorded_at": x["recorded_at"], "rule_identity": x["rule_identity"]})
    return rows

def project(run, **reports):
    return {"contract": "rule-revision", "contract_version": "0.1.0-draft", "profile": "rule-revision/0.1", "producer": "control-plane",
            "run_id": run["run_id"], "rule_revisions": run.get("rule_revisions", []), "rule_revision_refusals": run.get("rule_revision_refusals", []),
            "identity_rows": identity_rows(run), "trend_reports": reports.get("trend", []), "arity_reports": reports.get("arity", []),
            "recomputability_reports": reports.get("recompute", [])}

def journal(run):
    return {"run_id": run["run_id"], "decisions": run["decisions"], "refusals": run["refusals"], "vocabulary_changes": run.get("vocabulary_changes", [])}

RUNS = {
 "rule-adopted-decision-and-refusal-rows": ("adopted-policy-decision-and-refusal-rows", "A signed adoption row for the policy digest; the decision and then the effect-time refusal (grant revoked) both carry rule_identity: adopted, verified through digest_matches_signed_revision."),
 "rule-unsigned-row-resolves-unknown": ("unsigned-row-resolves-unknown-and-holds", "An unsigned revision row is kept but never counts: the policy resolves unknown (verified through revision_row_present, finding unsigned_revision_row) and the decision holds with policy_status_unknown."),
 "rule-refused-revision-attempts-kept": ("refused-revision-attempts-kept-as-rows", "Five refused attempts kept as rule_revision_refusals rows, one per reason the producer writes (self-signed, signer not configured, from_digest not the adopted digest, revision id reused, supersedes a row that does not exist) and one accepted signed adoption row; no decision is made."),
 "rule-edit-in-place-held-then-readopted": ("policy-edited-in-place-held-then-readopted", "The policy content digest changes under the same version label: the decision holds (digest_mismatch_with_adopted, verified through signer_independent_and_configured); a new signed row from the old digest to the new one re-adopts it and the next decision is authorized. Three decisions at increasing times, each identity row recomputable from the revision rows recorded by then."),
 "rule-unsigned-then-resigned-by-supersession": ("unsigned-then-resigned-by-supersession", "An unsigned row is superseded by a signed row for the same digest; the policy is adopted, the superseded unsigned row still shows as the finding unsigned_revision_row."),
 "rule-host-rule-unadopted-does-not-gate": ("host-rule-unadopted-does-not-gate", "The host-supplied reason registry digest has no adoption row: it is listed in unknown with state unknown, but only a policy rule holds a decision, so the decision is authorized."),
}
for raw, (fid, why) in RUNS.items():
    run = normalise(json.load(open(RAW / f"{raw}.json"))["run"])
    fx = {"fixture_id": fid, "synthetic": True, "expected_outcome": "accept",
          "reason": f"Real producer run (Control Plane {CP}, opt-in rule-revision/0.1, synthetic proposals, fixed clock, throwaway store). {why} Ids and the process owner are synthetic.",
          "provenance": {"source": "control-plane-capture", "control_plane_commit": CP, "scenario": raw},
          "document": project(run), "journal": journal(run), "signers": SIGNERS}
    write(DEST, fx)
    if raw == "rule-adopted-decision-and-refusal-rows":
        ext = copy.deepcopy(fx); ext["fixture_id"] = "extension-namespace-members-preserved"
        ext["reason"] = "x- members on the document, a revision row, an identity row and nested report envelopes are accepted and preserved (decision 1). Derived from the real adopted run by adding the extension members."
        ext["provenance"] = {"source": "control-plane-capture plus hand-added x- members", "control_plane_commit": CP, "scenario": raw}
        ext["document"]["extensions"] = {"x-trace-note": "synthetic"}
        ext["document"]["rule_revisions"][0]["extensions"] = {"x-ticket": {"id": 1}}
        ext["document"]["identity_rows"][0]["extensions"] = {"x-note": ["a", 1]}
        write(DEST, ext)

# derived reports: outputs of the real functions (refusal_trends, measured_arity, arity_flags, recomputability_flags) over the real rows
cap = json.load(open(RAW / "rule-reports.json"))
run, extra = normalise(cap["run"]), cap["extra"]
base = dict(provenance={"source": "control-plane-capture", "control_plane_commit": CP, "scenario": "rule-reports"}, journal=journal(run), signers=SIGNERS)
def fixture(fid, why, **reports):
    fx = {"fixture_id": fid, "synthetic": True, "expected_outcome": "accept",
          "reason": f"Real producer run and real function outputs (Control Plane {CP}, rule-revision/0.1; three held decisions before and after a reason_registry adoption row and a vocabulary split, synthetic ids). {why} The report envelope members (report_id, declared_from, declared_kinds, rows_from) are contract members added around the verbatim function output.",
          **copy.deepcopy(base), "document": project(run, **reports)}
    write(DEST, fx)
fixture("identity-rows-across-a-registry-adoption", "Identity rows of three held decisions: the host registry digest is unknown before the adoption row and adopted after it; the policy stays unadopted and every decision holds with policy_status_unknown.")
fixture("trend-flags-from-registry-adoption-row", "refusal_trends with the revision rows: two rows predate the registry's adoption row and their series are tainted_for_trend (row_predates_adoption).",
        trend=[{"report_id": "trend-1", "report": extra["trend_registry"]}])
fixture("trend-pre-split-tainted-from-vocabulary-change", "refusal_trends with the vocabulary change (a split): the retired code's count is tainted_for_trend (pre_split_count); no row predates an adoption.",
        trend=[{"report_id": "trend-1", "report": extra["trend_split"]}])
fixture("trend-plain-without-adoption-annotation", "refusal_trends without the new arguments: output unchanged from the legacy shape, no annotation members.",
        trend=[{"report_id": "trend-1", "report": extra["trend_plain"]}])
fixture("arity-measured-exceeds-declared-and-undeclared", "Arity declared at signing on the adopted reason_registry row (policy_status_unknown: 1) and measured over the period (2 operand shapes): measured_exceeds_declared; grant_revoked is not declared: arity_undeclared. Both numbers are kept.",
        arity=[{"report_id": "arity-1", "declared": extra["declared"], "declared_from": "rev-reg-1", "measured": extra["measured"], "flags": extra["arity_flags"]}])
fixture("arity-within-declaration", "A declaration that covers the measured shapes: no flags (declared and measured still both kept).",
        arity=[{"report_id": "arity-1", "declared": extra["arity_ok_declared"], "declared_from": None, "measured": extra["measured"], "flags": extra["arity_ok_flags"]}])
rk = {k: v for k, v in extra["registry_kinds"].items() if k in {f["code"] for f in extra["recomputability_flags"]}}
fixture("recomputability-derivation-unavailable", "recomputability_flags over the held decisions: grant_revoked is declared recomputable and recomputable in principle, but the retained row keeps no operands (its manifest input records an empty observed value), so the real row derives underivable and the real producer output carries a derivation_unavailable flag, not a declared_overclaim.",
        recompute=[{"report_id": "recompute-1", "rows_from": "decisions", "declared_kinds": rk, "flags": extra["recomputability_flags"]}])
# hand-built minimal document
empty = {"fixture_id": "no-rows", "synthetic": True, "expected_outcome": "accept",
         "reason": "Hand-built: the profile document of a run that wrote no revision rows, refusals, identity rows or reports (all lists present and empty).",
         "provenance": {"source": "hand-built", "control_plane_commit": CP}, "document": project({"run_id": "run-1", "decisions": [], "refusals": []})}
write(DEST, empty)
print("ok")
