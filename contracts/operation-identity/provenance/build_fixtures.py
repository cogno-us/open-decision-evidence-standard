"""Build the valid operation-identity fixtures from captured run records (step 2 of 2; step 1 is capture_fixtures.py).

    python build_fixtures.py <raw-dir> <fixtures/valid dir> <control-plane-commit>

Normalises random uuids to synthetic ids and the process owner, projects the run record onto the sidecar document, trims the
journal context's resolution inputs to the manifest and grant reads, and writes one fixture per captured scenario.
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

KEEP = {"manifest", "grant"}
def trim(run):
    r = copy.deepcopy(run)
    keep = lambda i: i["input_type"] in KEEP
    for d in r["decisions"]: d["resolution_inputs"] = [i for i in d["resolution_inputs"] if keep(i)]
    for x in r["refusals"]: x["resolution_inputs"] = [i for i in x["resolution_inputs"] if keep(i)]
    for c in r["resolution_checks"]: c["inputs"] = [i for i in c["inputs"] if keep(i)]
    r["check_events"] = [e for e in r["check_events"] if e["phase"] != "input" or keep(e["input"])]
    return {k: r[k] for k in ("run_id", "decisions", "attempts", "check_events", "resolution_checks", "refusals")}
def project(run):
    return {"contract": "operation-identity", "contract_version": "0.1.0-draft", "profile": "operation-identity/0.1",
            "producer": "control-plane", "run_id": run["run_id"], "operations": run.get("operations", []),
            "operation_renewals": run.get("operation_renewals", []), "attempt_joins": run.get("attempt_joins", [])}


def main(argv):
    RAW, DEST, CP = Path(argv[0]), Path(argv[1]), argv[2]
    CASES = {
     "op-normal": ("normal-attempted-acknowledged", "One authorized decision, one attempt: ledger row, join row and shared check ids. Decide, then execute under the opt-in profile."),
     "op-renewal-accepted": ("renewal-accepted-second-revision", "The authority publishes revision 2 of the grant; the issuer records an accepted renewal; the second decision is authorized under the same operation id and only that effect is executed (its legacy effect_id differs from revision 1's)."),
     "op-worker-self-renewal-then-unrecorded-hold": ("worker-self-renewal-refused-then-unrecorded-hold", "The worker (not the issuer) tries to renew: a refused row with renewal_not_written_by_grant_issuer is persisted. Revision 2 then arrives with no accepted renewal and the decision holds with operation_renewal_unrecorded: no attempt, no join."),
     "op-renewal-refused-not-admitted-and-not-new": ("renewal-refused-not-admitted-and-not-new", "Two refused renewals kept as rows: an unknown operation (operation_not_admitted, null grant and from revision) and the operation's own first revision (renewal_revision_not_new)."),
     "op-effect-time-refusal-carries-check-id": ("effect-time-refusal-carries-check-id", "The grant is revoked between decision and execute: the effect-time refusal row carries the check_id of the effect-stage check that refused, shared with the journal event and the resolution check. No attempt, no join."),
     "op-duplicate-submission-reconciled-existing": ("duplicate-submission-reconciled-existing", "The same decision is executed twice: the second attempt is the single-row reconciled_existing acknowledgement with its own join row and its own effect-stage check, under the same effect id and operation."),
     "op-lost-ack-then-reconciled-existing": ("lost-ack-then-reconciled-existing", "A lost acknowledgement (attempt unknown), a reconcile that observes the applied effect, then a retry that reconciles the existing effect: two attempts, two joins, one effect."),
     "op-delayed-first-attempt-rejected-after-renewal": ("delayed-first-attempt-rejected-after-renewal", "The case the profile exists for: attempt 1 passes its check on revision 1 and stalls inside the destination; the issuer renews to revision 2; attempt 2 commits; attempt 1 resumes and the destination definitively rejects it with operation_already_committed (a failed row). One effect for the operation."),
     "op-grant-mismatch-held": ("operation-grant-mismatch-held", "The ledger row for the operation id is bound to another grant; the next decision holds with operation_grant_mismatch and writes no attempt. (The ledger row was altered in the throwaway store to model a collision.)"),
     "op-operation-id-missing-held": ("operation-id-missing-held", "The profile is on and the issuer-approved extension carries no operation_id: the decision holds with operation_id_missing and no ledger row is written."),
     "op-operation-id-invalid-held": ("operation-id-invalid-held", "The operation id contains a space: the decision holds with operation_id_invalid and no ledger row is written."),
    }
    GRANT_MISMATCH = CASES.pop("op-grant-mismatch-held")
    for raw, (fid, why) in CASES.items():
        d = json.load(open(RAW / f"{raw}.json"))
        run = normalise(d["run"])
        fx = {"fixture_id": fid, "synthetic": True, "expected_outcome": "accept",
              "reason": f"Real producer run (Control Plane {CP}, opt-in operation-identity/0.1, synthetic proposals, fixed clock, throwaway store). {why} Ids and the process owner are synthetic; resolution inputs in the journal context are trimmed to the manifest and grant reads.",
              "provenance": {"source": "control-plane-capture", "control_plane_commit": CP, "scenario": raw},
              "document": project(run), "journal": trim(run)}
        write(DEST, fx)
        if raw == "op-normal":
            ext = copy.deepcopy(fx); ext["fixture_id"] = "extension-namespace-members-preserved"
            ext["reason"] = "x- members on the document, an operation, a renewal-free join and nested rows are accepted and preserved (decision 1). Derived from the real normal run by adding the extension members; the added members are the only hand-written content."
            ext["provenance"] = {"source": "control-plane-capture plus hand-added x- members", "control_plane_commit": CP, "scenario": raw}
            ext["document"]["extensions"] = {"x-trace-note": "synthetic"}
            ext["document"]["operations"][0]["extensions"] = {"x-origin": {"ticket": 1}}
            ext["document"]["attempt_joins"][0]["extensions"] = {"x-note": ["a", 1]}
            write(DEST, ext)
    # hand-built: the merged_into field naming an admitted operation (no producer writes a non-null value; merge logic is a later stream)
    base = json.load(open(DEST / "normal-attempted-acknowledged.json"))
    merged = copy.deepcopy(base); merged["fixture_id"] = "merged-into-names-admitted-operation"; merged.pop("journal")
    merged["synthetic"] = True
    merged["reason"] = ("Hand-built from the real normal run: a second operation is admitted and the first operation's join row names it in merged_into. "
                        "The Control Plane always writes merged_into null (merge logic is a later stream) and the runtime sidecar enforces only that the target is an admitted operation, so this shape is contract-only.")
    merged["provenance"] = {"source": "hand-built from captured fixture normal-attempted-acknowledged", "control_plane_commit": CP}
    second = copy.deepcopy(merged["document"]["operations"][0]); second["operation_id"] = "op-order-200/refund-1"
    merged["document"]["operations"].append(second)
    merged["document"]["attempt_joins"][0]["merged_into"] = "op-order-200/refund-1"
    write(DEST, merged)
    print("ok")


if __name__ == "__main__":
    main(sys.argv[1:])
