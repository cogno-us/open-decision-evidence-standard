"""Mutate the valid operation-identity fixtures into the invalid ones (single-defect mutations; each fixture's `provenance` names its base).

    python mutate_invalid_fixtures.py <contracts/operation-identity dir> <raw-dir>

Needs build_fixtures.py next to it for normalise, trim and project (importing it reads its own argv, so run it from this directory
with the build arguments, or copy the three helpers) and the captured raw runs for the one captured collision case.
"""
import copy, json, sys, importlib.util
from pathlib import Path
from build_fixtures import write, normalise, project, trim
CDIR = Path(sys.argv[1])           # contracts/operation-identity
RAW = Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("oi", CDIR / "validate.py"); oi = importlib.util.module_from_spec(spec)
sys.modules["oi"] = oi; spec.loader.exec_module(oi)
V = {p.stem: json.loads(p.read_text()) for p in (CDIR / "fixtures" / "valid").glob("*.json")}
out_dir = CDIR / "fixtures" / "invalid"
for p in out_dir.glob("*.json"): p.unlink()
CP = "83b49b5"
results = []

def make(fid, base, code, why, fn, journal=False):
    b = copy.deepcopy(V[base])
    doc, jr = b["document"], b["journal"]
    fn(doc, jr)
    fx = {"fixture_id": fid, "synthetic": True, "expected_outcome": "reject", "expected_refusal": code,
          "reason": why, "provenance": {"source": f"mutation of captured fixture {base}", "control_plane_commit": CP},
          "document": doc}
    if journal: fx["journal"] = jr
    got = [v.code for v in oi.validate(doc, jr if journal else None)]
    results.append((fid, code, got))
    write(out_dir, fx)

def op(doc, i=0): return doc["operations"][i]
def join(doc, i=0): return doc["attempt_joins"][i]
def dec(jr, i=0): return jr["decisions"][i]
def renewal(doc, i=0): return doc["operation_renewals"][i]
N, R, D, E_, RF, W = ("normal-attempted-acknowledged", "renewal-accepted-second-revision", "delayed-first-attempt-rejected-after-renewal",
                      "effect-time-refusal-carries-check-id", "renewal-refused-not-admitted-and-not-new", "worker-self-renewal-refused-then-unrecorded-hold")

# ---- structure
make("undeclared-member-outside-extensions", N, "undeclared_member", "A member neither declared nor inside extensions is refused, never dropped.", lambda d, j: d.update(injected_member=1))
make("extension-key-without-x-prefix", N, "invalid_extension_key", "Extension members use the reserved x- form.", lambda d, j: d.update(extensions={"note": 1}))
make("unsupported-contract-version", N, "unsupported_contract_version", "A different contract version is refused typed.", lambda d, j: d.update(contract_version="9.0.0"))
make("unknown-renewal-outcome", R, "unknown_enum_value", "The renewal outcome set is closed (accepted, refused).", lambda d, j: renewal(d).update(outcome="pending"))
make("unknown-refusal-code", RF, "unknown_enum_value", "The renewal refusal code set is closed to the three codes the producer writes.", lambda d, j: renewal(d).update(refusal_code="renewal_expired"))
make("unknown-time-source", N, "unknown_enum_value", "time_source is control_plane or test_override.", lambda d, j: join(d).update(time_source="wall_clock"))
make("operation-id-malformed", N, "schema_violation", "An operation id has 1 to 128 characters from [A-Za-z0-9._:/#-] and starts alphanumeric (the producer's operation_id_invalid shape).", lambda d, j: op(d).update(operation_id="has space"))
make("join-missing-check-id", N, "schema_violation", "A join row carries every member, check_id included.", lambda d, j: join(d).pop("check_id"))
make("class-max-age-negative", N, "schema_violation", "class_max_age is a non-negative integer.", lambda d, j: join(d).update(class_max_age=-1))
make("effect-id-not-a-commitment", N, "schema_violation", "effect_id is a sha256 commitment.", lambda d, j: join(d).update(effect_id="effect-1"))
make("profile-marker-wrong", N, "schema_violation", "The profile marker is exact.", lambda d, j: d.update(profile="operation-identity/0.2"))
make("empty-resolver-id", N, "schema_violation", "resolver_id comes from host configuration and is never empty.", lambda d, j: join(d).update(resolver_id=""))
make("effective-grant-digest-not-a-commitment", N, "schema_violation", "expected_effective_grant_digest is null or a sha256 commitment.", lambda d, j: join(d).update(expected_effective_grant_digest="digest"))

# ---- document rules
make("duplicate-operation-id", N, "duplicate_operation_id", "An operation is admitted once.", lambda d, j: d["operations"].append(copy.deepcopy(op(d))))
make("naive-admitted-at", N, "timestamp_invalid", "admitted_at carries a UTC offset.", lambda d, j: op(d).update(admitted_at="2026-10-05T19:00:00"))
make("naive-renewal-recorded-at", R, "timestamp_invalid", "A renewal's recorded_at carries a UTC offset.", lambda d, j: renewal(d).update(recorded_at="2026-10-05T19:00:00"))
make("naive-join-recorded-at", N, "timestamp_invalid", "A join's recorded_at carries a UTC offset.", lambda d, j: join(d).update(recorded_at="2026-10-05T19:00:00"))
def dup_renewal(d, j): d["operation_renewals"][1]["renewal_id"] = d["operation_renewals"][0]["renewal_id"]
make("duplicate-renewal-id", RF, "duplicate_renewal_id", "Renewal ids are unique, refused rows included.", dup_renewal)
make("renewal-accepted-with-refusal-code", R, "renewal_outcome_inconsistent", "outcome accepted if and only if refusal_code is null.", lambda d, j: renewal(d).update(refusal_code="renewal_revision_not_new"))
make("renewal-refused-without-refusal-code", RF, "renewal_outcome_inconsistent", "A refused renewal states its code.", lambda d, j: renewal(d).update(refusal_code=None))
make("renewal-from-revision-wrong", R, "renewal_context_mismatch", "from_revision is the last accepted revision, else the first.", lambda d, j: renewal(d).update(from_revision="9"))
make("renewal-of-unadmitted-operation-names-a-grant", RF, "renewal_context_mismatch", "A renewal of an unadmitted operation carries null grant_id and from_revision.", lambda d, j: renewal(d).update(grant_id="urn:cognous:grant:routine-1"))
def acc_unadmitted(d, j):
    d["operation_renewals"].append({"renewal_id": "syn-renewal-9", "operation_id": "op-other", "grant_id": None, "from_revision": None, "to_revision": "2",
        "written_by": op(d)["issuer"], "outcome": "accepted", "refusal_code": None, "recorded_at": op(d)["admitted_at"]})
make("renewal-accepted-for-unadmitted-operation", N, "renewal_accepted_unadmitted_operation", "An accepted renewal names an admitted operation.", acc_unadmitted)
make("renewal-accepted-not-by-issuer", R, "renewal_accepted_not_by_issuer", "Only the issuer recorded at admission writes an accepted renewal (the worker's self-extension).", lambda d, j: renewal(d).update(written_by="urn:cognous:identity:refund-agent-1"))
def acc_not_new(d, j):
    d["operation_renewals"].append({"renewal_id": "syn-renewal-9", "operation_id": op(d)["operation_id"], "grant_id": op(d)["grant_id"], "from_revision": "1",
        "to_revision": "1", "written_by": op(d)["issuer"], "outcome": "accepted", "refusal_code": None, "recorded_at": op(d)["admitted_at"]})
make("renewal-accepted-revision-not-new", N, "renewal_accepted_revision_not_new", "A renewal to a revision the operation already holds is refused, not accepted.", acc_not_new)
def unjustified(d, j):
    d["operation_renewals"].append({"renewal_id": "syn-renewal-9", "operation_id": op(d)["operation_id"], "grant_id": op(d)["grant_id"], "from_revision": "1",
        "to_revision": "2", "written_by": op(d)["issuer"], "outcome": "refused", "refusal_code": "renewal_revision_not_new", "recorded_at": op(d)["admitted_at"]})
make("renewal-refusal-unjustified", N, "renewal_refusal_unjustified", "A refusal must state a defect the ledger shows.", unjustified)
make("renewal-refusal-code-mismatch", W, "renewal_refusal_code_mismatch", "A worker's renewal of a new revision is refused for the writer, not for the revision.", lambda d, j: renewal(d).update(refusal_code="renewal_revision_not_new"))
def dup_join(d, j): d["attempt_joins"][1]["join_id"] = d["attempt_joins"][0]["join_id"]
make("duplicate-join-id", D, "duplicate_join_id", "Join ids are unique.", dup_join)
def dup_attempt(d, j):
    x = copy.deepcopy(join(d)); x["join_id"] = "syn-join-9"; x["check_id"] = "syn-check-9"; d["attempt_joins"].append(x)
make("duplicate-attempt-join", N, "duplicate_attempt_join", "One join row per attempt.", dup_attempt)
make("duplicate-join-check-id", D, "duplicate_join_check_id", "A journal check licenses one attempt.", lambda d, j: join(d, 1).update(check_id=join(d, 0)["check_id"]))
make("join-operation-not-admitted", N, "join_operation_not_admitted", "A join names an admitted operation.", lambda d, j: join(d).update(operation_id="op-other"))
make("join-grant-mismatch", N, "join_grant_mismatch", "The operation id is stable across revisions of one grant, not across grants.", lambda d, j: join(d).update(grant_id="urn:cognous:grant:other"))
make("join-revision-unlicensed", N, "join_revision_unlicensed", "A join's revision is the first or an accepted renewal's.", lambda d, j: join(d).update(grant_revision="7"))
make("merged-into-self", N, "merged_into_self", "An operation is not merged into itself.", lambda d, j: join(d).update(merged_into=op(d)["operation_id"]))
make("merged-into-not-admitted", N, "merged_into_not_admitted", "merged_into names an admitted operation.", lambda d, j: join(d).update(merged_into="op-other"))
make("merged-into-an-attempt-id", N, "merged_into_not_admitted", "merged_into holds an operation id, never an attempt id.", lambda d, j: join(d).update(merged_into=join(d)["attempt_id"]))

# ---- journal context
J = True
make("journal-run-mismatch", N, "journal_run_mismatch", "The document and the run record describe one run.", lambda d, j: j.update(run_id="run-2"), J)
def no_opid(d, j):
    x = copy.deepcopy(dec(j)); x["decision_id"] = "syn-decision-9"; x["binding"]["runtime_authority"].pop("operation_id"); j["decisions"].append(x)
make("decision-operation-id-missing", N, "decision_operation_id_missing", "Under the profile an authorized binding carries the issuer's operation id.", no_opid, J)
def extra_decision(j, **ra):
    x = copy.deepcopy(dec(j)); x["decision_id"] = "syn-decision-9"; x["binding"]["runtime_authority"].update(ra.get("ra", {}))
    x["binding"].update(ra.get("binding", {})); j["decisions"].append(x)
make("decision-operation-unadmitted", N, "decision_operation_unadmitted", "An authorized decision's operation id is in the ledger.", lambda d, j: extra_decision(j, ra={"operation_id": "op-other"}), J)
make("operation-issuer-mismatch", N, "operation_issuer_mismatch", "The binding names the issuer recorded at admission.", lambda d, j: dec(j)["binding"]["runtime_authority"].update(operation_issuer="urn:cognous:principal:someone-else"), J)
make("decision-revision-unlicensed", N, "decision_revision_unlicensed", "A decision at revision 5 with no accepted renewal is not licensed by the ledger.", lambda d, j: extra_decision(j, binding={"grant_revision": "5"}), J)
def first_rev(d, j):
    op(d)["first_grant_revision"] = "0"
    d["operation_renewals"].append({"renewal_id": "syn-renewal-9", "operation_id": op(d)["operation_id"], "grant_id": op(d)["grant_id"], "from_revision": "0",
        "to_revision": "1", "written_by": op(d)["issuer"], "outcome": "accepted", "refusal_code": None, "recorded_at": op(d)["admitted_at"]})
make("first-revision-mismatch", N, "first_revision_mismatch", "An operation is admitted at the revision of its first authorized decision.", first_rev, J)
make("join-attempt-missing", N, "join_attempt_missing", "A join names an attempt of the run record.", lambda d, j: j.update(attempts=[]), J)
def attempt_effect(d, j):
    for a in j["attempts"]: a["effect_id"] = "sha256:" + "1" * 64
make("join-attempt-mismatch", N, "join_attempt_mismatch", "The join's effect is the attempt's.", attempt_effect, J)
make("join-decision-missing", N, "join_decision_missing", "A join names a decision of the run record.", lambda d, j: j.update(decisions=[]), J)
def unauth(d, j): dec(j).update(result="hold", binding=None, reasons=["status_unreadable"])
make("join-decision-unauthorized", N, "join_decision_unauthorized", "An attempt follows an authorized decision.", unauth, J)
def other_op(d, j):
    d["operations"].append({**copy.deepcopy(op(d)), "operation_id": "op-other"}); join(d).update(operation_id="op-other")
make("join-operation-mismatch", N, "join_operation_mismatch", "The join's operation is the one the decision's binding carries.", other_op, J)
make("join-binding-mismatch", R, "join_binding_mismatch", "The join's revision is the binding's (revision 2 was dispatched, the join says 1).", lambda d, j: join(d).update(grant_revision="1"), J)
make("join-effect-mismatch", N, "join_effect_mismatch", "The join's effect id is the decision's.", lambda d, j: dec(j).update(effect_id="sha256:" + "2" * 64), J)
def drop_opened(d, j):
    cid = join(d)["check_id"]; j["check_events"] = [e for e in j["check_events"] if not (e["check_id"] == cid and e["phase"] == "opened")]
make("join-check-missing", N, "join_check_missing", "The join's check id opens an effect-stage check in the journal.", drop_opened, J)
def lineage(d, j):
    cid = join(d)["check_id"]
    for e in j["check_events"]:
        if e["check_id"] == cid and e["phase"] == "opened": e["effect_id"] = "sha256:" + "3" * 64
make("join-check-lineage", N, "join_check_lineage", "The journal check names the join's effect and decision.", lineage, J)
def not_completed(d, j):
    cid = join(d)["check_id"]; j["check_events"] = [e for e in j["check_events"] if not (e["check_id"] == cid and e["phase"] == "completed")]
make("join-check-not-completed", N, "join_check_not_completed", "A check that did not complete licenses no dispatch.", not_completed, J)
def drop_rc(d, j):
    cid = join(d)["check_id"]; j["resolution_checks"] = [c for c in j["resolution_checks"] if c["check_id"] != cid]
make("join-resolution-check-missing", N, "join_resolution_check_missing", "The same id names the effect-stage resolution check.", drop_rc, J)
make("attempt-without-join", N, "attempt_without_join", "Under the profile every attempt has its join row.", lambda d, j: d.update(attempt_joins=[]), J)
def rc_unjournalled(d, j): j["resolution_checks"][0]["check_id"] = "syn-check-9"
make("resolution-check-not-in-journal", N, "resolution_check_not_in_journal", "Under the profile a resolution check carries the id of the journal check it was read in (the legacy path mints its own).", rc_unjournalled, J)
make("refusal-check-id-missing", E_, "refusal_check_id_missing", "Under the profile a refusal names the check that refused.", lambda d, j: j["refusals"][0].pop("check_id"), J)
make("refusal-check-missing", E_, "refusal_check_missing", "The refusal's check id names an effect-stage resolution check.", lambda d, j: j["refusals"][0].update(check_id="syn-check-9"), J)
make("refusal-check-lineage", E_, "refusal_check_lineage", "The journal check names the refusal's effect and decision.", lambda d, j: j["refusals"][0].update(effect_id="sha256:" + "4" * 64), J)
def twice(d, j):
    last = [a for a in j["attempts"] if a["status"] == "failed"][0]; last.update(status="acknowledged", error=None, acknowledgement={})
make("operation-committed-twice", D, "operation_committed_twice", "Two effect ids both acknowledged for one operation: the destination dedupe failed.", twice, J)
def no_peer(d, j):
    for a in j["attempts"]:
        if a["status"] == "acknowledged": a.update(status="failed", error="cumulative_grant_max_effects_exhausted", acknowledgement={})
make("rejection-without-committed-peer", D, "rejection_without_committed_peer", "operation_already_committed needs another effect of the operation that was acknowledged, partial or unknown.", no_peer, J)

# grant mismatch: the held decision capture (ledger bound to another grant)
raw = json.loads((RAW / "op-grant-mismatch-held.json").read_text())
run = normalise(raw["run"])
fx = {"fixture_id": "decision-operation-binding-mismatch", "synthetic": True, "expected_outcome": "reject", "expected_refusal": "decision_operation_binding_mismatch",
      "reason": "Capture of the collision case (the throwaway store's ledger row was rebound to another grant, as the producer's own test does): the producer then holds the next decision with operation_grant_mismatch, but the ledger row no longer matches the earlier authorized decision's grant, which a consumer must refuse.",
      "provenance": {"source": "control-plane-capture with the ledger row altered", "control_plane_commit": CP, "scenario": "op-grant-mismatch-held"},
      "document": project(run), "journal": trim(run)}
write(out_dir, fx)
results.append((fx["fixture_id"], fx["expected_refusal"], [v.code for v in oi.validate(fx["document"], fx["journal"])]))
bad = [r for r in results if r[2] != [r[1]]]
for r in bad: print("MISMATCH", r)
print(len(results), "invalid fixtures,", len(bad), "mismatches")
