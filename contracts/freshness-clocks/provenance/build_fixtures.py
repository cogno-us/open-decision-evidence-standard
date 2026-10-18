"""Build the valid freshness-clocks fixtures from captured run records (step 2 of 2; step 1 is capture_fixtures.py).

    python build_fixtures.py <raw-dir> <fixtures/valid dir> <control-plane-commit>

Normalises random uuids, nonces and the process owner to synthetic ones (stable order of first appearance), projects each run record
onto the sidecar document, and writes one fixture per scenario. Re-running it on a second capture of the same code reproduces the
fixtures byte for byte. Nothing is hand-written except the `x-` members of `extension-namespace-members-preserved`.
"""
import copy, json, re, sys
from pathlib import Path

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
NONCE = re.compile(r"[0-9a-f]{32}")
BARE_NONCE = re.compile(r"(?<![0-9a-f:])[0-9a-f]{32}(?![0-9a-f])")
KINDS = {"decision_id": "decision", "attempt_id": "attempt", "check_id": "check", "join_id": "join", "renewal_id": "renewal",
         "refusal_id": "refusal", "extension_id": "extension", "run_id": "recovery-run"}


def normalise(doc):
    text = json.dumps(doc, ensure_ascii=False)
    counters, mapping = {}, {}

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if isinstance(v, str) and UUID.fullmatch(v) and v not in mapping:
                    kind = KINDS.get(k, "id")
                    counters[kind] = counters.get(kind, 0) + 1
                    mapping[v] = f"syn-{kind}-{counters[kind]}"
                elif k == "nonce" and isinstance(v, str) and NONCE.fullmatch(v) and v not in mapping:
                    counters["nonce"] = counters.get("nonce", 0) + 1
                    mapping[v] = f"syn-nonce-{counters['nonce']:02d}"
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(doc)
    for old, new in mapping.items():
        text = text.replace(old, new)
    out = json.loads(text)
    n = [0]

    def owners(x):
        if isinstance(x, dict):
            if set(x) == {"pid", "token"}:
                key = x["token"]
                if key not in mapping:
                    n[0] += 1
                    mapping[key] = f"syn-owner-token-{n[0]}"
                x["pid"] = "1001"
                x["token"] = mapping[key]
            else:
                for v in x.values():
                    owners(v)
        elif isinstance(x, list):
            for v in x:
                owners(v)
    owners(out)
    left = UUID.findall(json.dumps(out)) + BARE_NONCE.findall(json.dumps(out))
    assert not left, left
    return out


def write(dirpath, fixture):
    (Path(dirpath) / f"{fixture['fixture_id']}.json").write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


RAW, DEST, CP = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
EVENT_KEYS = ("check_id", "phase", "stage", "recorded_at", "evaluated_at", "deadline", "age_bound_seconds", "extension_id", "nonce", "reasons")


def clock_rows(run):
    rows = []

    def add(kind, row_id, seq, evaluated_at, recorded_at, deadline=None):
        row = {"row_type": kind, "row_id": row_id, "seq": seq}
        if evaluated_at is not None:
            row["evaluated_at"] = evaluated_at
        row["recorded_at"] = recorded_at
        if deadline is not None:
            row["deadline"] = deadline
        rows.append(row)
    for d in run["decisions"]:
        if "recorded_at" in d:
            add("decision", d["decision_id"], 0, d.get("evaluated_at"), d["recorded_at"])
    seen = {}
    for a in run["attempts"]:
        seq = seen.get(a["attempt_id"], 0)
        seen[a["attempt_id"]] = seq + 1
        if "recorded_at" in a:
            add("attempt", a["attempt_id"], seq, a.get("evaluated_at"), a["recorded_at"])
    for x in run["refusals"]:
        if "evaluated_at" in x or "deadline" in x:
            add("refusal", x["refusal_id"], 0, x.get("evaluated_at"), x["recorded_at"], x.get("deadline"))
    for c in run["resolution_checks"]:
        if "recorded_at" in c:
            add("resolution_check", c["check_id"], 0, c["evaluated_at"], c["recorded_at"])
    for j in run.get("attempt_joins", []):
        if "evaluated_at" in j:
            add("attempt_join", j["join_id"], 0, j["evaluated_at"], j["recorded_at"])
    for o in run.get("operations", []):
        if "evaluated_at" in o:
            add("operation", o["operation_id"], 0, o["evaluated_at"], o["admitted_at"])
    for r in run.get("operation_renewals", []):
        if "evaluated_at" in r:
            add("operation_renewal", r["renewal_id"], 0, r["evaluated_at"], r["recorded_at"])
    return rows


def input_reads(run):
    rows = []
    sources = [("decision", d["decision_id"], None, d["resolution_inputs"]) for d in run["decisions"]]
    sources += [("refusal", x["refusal_id"], x.get("check_id"), x["resolution_inputs"]) for x in run["refusals"]]
    sources += [("resolution_check", c["check_id"], c["check_id"], c["inputs"]) for c in run["resolution_checks"]]
    for kind, row_id, check_id, inputs in sources:
        for i in inputs:
            if "age_basis" not in i:
                continue
            mm = i.get("read_state") == "nonce_mismatch"
            rows.append({"row_type": kind, "row_id": row_id, "check_id": check_id, "input_type": i["input_type"], "input_id": i["input_id"],
                         "age_basis": i["age_basis"], "read_state": i.get("read_state"),
                         "expected_nonce": i["expected"]["nonce"] if mm else None, "observed_nonce": i["observed"]["nonce"] if mm else None})
    return rows


def project(run, report=None):
    return {"contract": "freshness-clocks", "contract_version": "0.1.0-draft", "profile": "freshness/0.1", "producer": "control-plane",
            "run_id": run["run_id"],
            "check_events": [{k: e[k] for k in EVENT_KEYS if k in e} for e in run.get("check_events", [])],
            "clock_rows": clock_rows(run), "input_reads": input_reads(run),
            "age_extensions": run.get("age_extensions", []), "age_extension_refusals": run.get("age_extension_refusals", []),
            "recovery_runs": run.get("recovery_runs", []),
            "freshness_reports": [{"report_id": "freshness-1", "report": report}] if report else []}


JOURNAL_KEYS = ("run_id", "decisions", "attempts", "refusals", "resolution_checks", "check_events", "operations", "operation_renewals",
                "attempt_joins", "age_extensions", "age_extension_refusals", "recovery_runs")

SCENARIOS = {
 "default-path": ("default-path-carries-no-clock-members", "Profile unset (runtime-authority only): the legacy shape. Journal events carry no deadline, nonce or clock members, so the sidecar carries the events and nothing else; a check without a deadline is open but never overdue."),
 "clocks-follow-the-service-clock": ("clocks-follow-the-service-clock", "Identity reads take 7 s of wall time: evaluated_at is the one evaluation pass, recorded_at follows the service clock write by write (the events of one check are stamped at different instants), decisions, attempts and resolution checks carry both clocks. Every non-manifest read is source_asserted (the resolver declares no nonce capability)."),
 "operation-rows-carry-the-clocks": ("operation-rows-carry-the-clocks", "freshness/0.1 with operation-identity/0.1: the operation row (admitted_at is its write time), the join row and an accepted renewal row carry evaluated_at, and the join and renewal rows carry their own recorded_at."),
 "deadline-at-opening-within-bound": ("deadline-at-opening-within-bound", "The check opens at +2 s with deadline = recorded_at + 60 s class bound; a 59 s stall before dispatch is inside the bound and the effect is acknowledged."),
 "expired-before-dispatch": ("expired-before-dispatch", "A 61 s stall before dispatch passes the deadline: the attempt row is failed with check_expired_before_dispatch, a refusal row carries the deadline, the completed check gets a terminal expired event, nothing reaches the destination."),
 "expired-with-operation-join": ("expired-with-operation-join", "The same expiry with operation-identity/0.1: the join row is written before the attempt row, so a join exists whose attempt is failed; the check is expired."),
 "expired-then-retry-dispatches": ("expired-then-retry-dispatches", "After the expiry a later pass on fresh inputs opens a new check and dispatches: two attempt lifecycles start with attempted for one effect. The failed attempt of the expired check is excluded from the prior-attempt rule, so the retry is allowed."),
 "observation-clock-decoupled": ("observation-clock-decoupled", "A live destination observation clock stamps the observation after the evaluation pass. Under the profile that is not a future timestamp (the legacy path holds for observation_time_future): the deadline decides and the check expires."),
 "overdue-reported-not-closed": ("overdue-reported-not-closed", "A live check is blocked inside a resolver read past its deadline: two recovery passes report it overdue (two recovery_run rows), the journal carries one non-terminal overdue event, and the owner later finishes the check (completed after overdue)."),
 "reaper-closes-the-dead-and-reports-the-late": ("reaper-closes-the-dead-and-reports-the-late", "The reaper's start-up pass closes an abandoned check (dead lease) as interrupted and records it; the interval pass 35 s later finds nothing open."),
 "extension-recorded-and-applied": ("extension-recorded-and-applied", "A grant status 70 s old holds against the 60 s class bound; a signer in the rule-revision signer set, distinct from the requester, records a 200 s extension; the next check opens with age_bound_seconds 200 and the extension_id and is authorized."),
 "extension-refusals-kept": ("extension-refusals-kept", "Six refused extension attempts kept as rows, one per defect the producer derives (unsigned, self-signed, signer not configured, exceeds the 300 s limit, bound does not rise, empty window); none is accepted."),
 "extension-without-authority-or-limit": ("extension-without-authority-or-limit", "No rule-revision profile and the default limit 0: an extension is refused for age_extension_authority_unconfigured and age_extension_exceeds_limit together."),
 "extension-withdrawn-at-use": ("extension-withdrawn-at-use", "An accepted extension is used once; the signer is then withdrawn from the configured set and the next decision holds with age_extension_signer_not_configured (authority is re-checked at every use). The accepted row stays in the record."),
 "nonce-bound-reads": ("nonce-bound-reads", "The resolver declares status-nonce/0.1 and echoes the nonce: every non-manifest read of a check is nonce_bound and the opening carries the nonce."),
 "source-asserted-without-capability": ("source-asserted-without-capability", "A resolver without the capability: the check still carries a nonce but every read is source_asserted."),
 "nonce-replay-rejected": ("nonce-replay-rejected", "A replayed earlier response (its old record and old echoed nonce) for the grant read: the read is nonce_mismatch, both nonces retained, the effect is refused with status_nonce_mismatch and nothing is dispatched."),
 "lease-unavailable-holds": ("lease-unavailable-holds", "The per-check lease cannot be taken before the acquisition deadline: the decision holds with check_lease_unavailable alone; no check is opened, no read happens, no attempt exists."),
}
for raw, (fid, why) in SCENARIOS.items():
    cap = json.load(open(RAW / f"{raw}.json"))
    run, facts = normalise(cap["run"]), cap["facts"]
    host = {k: facts[k] for k in ("signers", "max_age_extension_seconds", "resolver_capability") if k in facts}
    fx = {"fixture_id": fid, "synthetic": True, "expected_outcome": "accept",
          "reason": f"Real producer run (Control Plane {CP}, opt-in freshness/0.1, synthetic proposals, settable service clock, throwaway store). {why} Ids, nonces and the process owner are synthetic.",
          "provenance": {"source": "control-plane-capture", "control_plane_commit": CP, "scenario": raw},
          "document": project(run), "journal": {k: run[k] for k in JOURNAL_KEYS if k in run}}
    if host:
        fx["host"] = host
    write(DEST, fx)
    if raw == "extension-recorded-and-applied":
        ext = copy.deepcopy(fx)
        ext["fixture_id"] = "extension-namespace-members-preserved"
        ext["reason"] = "x- members on the document, a check event, a clock row, an input read, an extension row and an envelope are accepted and preserved (decision 1). Derived from the real extension run by adding the extension members."
        ext["provenance"] = {"source": "control-plane-capture plus hand-added x- members", "control_plane_commit": CP, "scenario": raw}
        d = ext["document"]
        d["extensions"] = {"x-trace-note": "synthetic"}
        d["check_events"][0]["extensions"] = {"x-ticket": {"id": 1}}
        d["clock_rows"][0]["extensions"] = {"x-note": ["a", 1]}
        d["input_reads"][0]["extensions"] = {"x-source": "synthetic"}
        d["age_extensions"][0]["extensions"] = {"x-outage-ticket": "synthetic"}
        write(DEST, ext)

# the freshness block of refusal_trends (verbatim) over the same journal
cap = json.load(open(RAW / "freshness-report.json"))
run, block = normalise(cap["run"]), cap["facts"]["trend_report"]["freshness"]
fx = {"fixture_id": "freshness-counts-next-to-refusal-counts", "synthetic": True, "expected_outcome": "accept",
      "reason": f"Real producer run and the real output of refusal_trends with check_events and as_of (Control Plane {CP}): one expired check, one abandoned check closed interrupted, one live check 30 s past its deadline. The envelope member report_id is added around the verbatim freshness block.",
      "provenance": {"source": "control-plane-capture", "control_plane_commit": CP, "scenario": "freshness-report"},
      "document": project(run, block), "journal": {k: run[k] for k in JOURNAL_KEYS if k in run}}
write(DEST, fx)
