"""Mutate the valid profile-on journal fixtures into the invalid ones (single-defect mutations; each fixture's `provenance` names its base).

    python mutate_invalid_fixtures.py <contracts/control-plane-journal dir>

Reads fixtures/valid/profile-*.json and validate.py, rewrites fixtures/invalid/profile-*.json (the older invalid fixtures are not touched),
and stops if a mutation does not yield exactly its one expected code. Nothing here weakens a verdict: every mutation breaks a rule the
Control Plane producer itself keeps (see the README section "Optional profile members").
"""
import copy, importlib.util, json, sys
from pathlib import Path

CDIR = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("cpj", CDIR / "validate.py")
cpj = importlib.util.module_from_spec(spec)
sys.modules["cpj"] = cpj
spec.loader.exec_module(cpj)
V = {p.stem[len("profile-"):]: json.loads(p.read_text()) for p in (CDIR / "fixtures" / "valid").glob("profile-*.json")}
OUT = CDIR / "fixtures" / "invalid"
for old in OUT.glob("profile-*.json"):
    old.unlink()
CP = next(iter(V.values()))["provenance"]["control_plane_commit"]
bad = []


def make(fid, base, code, why, fn):
    doc = copy.deepcopy(V[base]["document"])
    fn(doc)
    got = list(dict.fromkeys(v.code for v in cpj.validate(doc)))   # one defect recorded in several places reports in each
    if got != [code]:
        bad.append((fid, code, got))
    fx = {"fixture_id": f"profile-{fid}", "synthetic": True, "expected_outcome": "reject", "expected_refusal": code, "reason": why,
          "provenance": {"source": f"single-defect mutation of the captured fixture profile-{base}", "control_plane_commit": CP},
          "document": doc}
    (OUT / f"profile-{fid}.json").write_text(json.dumps(fx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def inputs(doc, **match):
    """Every copy of an input read that has these members (one read is recorded in the check, the refusal/decision and the journal)."""
    found = []

    def walk(x):
        if isinstance(x, dict):
            if "input_type" in x and all(x.get(k) == v for k, v in match.items()):
                found.append(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(doc)
    assert found, match
    return found


def event(doc, phase):
    return next(e for e in doc["check_events"] if e["phase"] == phase)


# ------------------------------------------------------------------------------ declared members stay closed and typed
make("freshness-member-on-the-wrong-object", "clocks-follow-the-service-clock", "undeclared_member",
     "`deadline` is declared on refusals and journal events only; a decision carrying it is refused (the optional members are declared per object, not as a free-for-all).",
     lambda d: d["decisions"][0].update(deadline=d["decisions"][0]["recorded_at"]))
make("profile-list-is-not-an-array", "op-normal", "schema_violation",
     "`operations` is declared as an array of rows.", lambda d: d.update(operations={}))
make("profile-list-row-is-not-an-object", "op-normal", "schema_violation",
     "Each `attempt_joins` row is an object.", lambda d: d["attempt_joins"].append("syn-join-extra"))
make("unknown-profile-phase", "overdue-reported-not-closed", "unknown_enum_value",
     "The phase set is closed: opened, input, completed, interrupted and the freshness values overdue and expired; 'stalled' is none of them.",
     lambda d: event(d, "overdue").update(phase="stalled"))
make("unknown-profile-read-state", "nonce-replay-rejected", "unknown_enum_value",
     "The read-state set is closed: unreadable, cached_positive and the freshness value nonce_mismatch.",
     lambda d: inputs(d, read_state="nonce_mismatch")[0].update(read_state="nonce_stale"))
make("unknown-age-basis", "nonce-bound-reads", "unknown_enum_value",
     "`age_basis` is nonce_bound or source_asserted.",
     lambda d: inputs(d, age_basis="nonce_bound")[0].update(age_basis="asserted"))
make("age-bound-seconds-is-text", "extension-recorded-and-applied", "schema_violation",
     "`age_bound_seconds` on a journal event is an integer.",
     lambda d: next(e for e in d["check_events"] if "age_bound_seconds" in e).update(age_bound_seconds="200"))
make("operation-id-is-empty", "op-normal", "schema_violation",
     "`operation_id` on the runtime-authority block is a non-empty string.",
     lambda d: next(x for x in d["decisions"] if x["binding"])["binding"]["runtime_authority"].update(operation_id=""))

# ------------------------------------------------------------------------------ profile value needs its member
make("overdue-event-without-deadline", "overdue-reported-not-closed", "profile_value_without_member",
     "An `overdue` event belongs to freshness/0.1 and carries the profile's deadline; without it the phase is not the profile's.",
     lambda d: event(d, "overdue").pop("deadline"))
make("expired-event-without-deadline", "expired-before-dispatch", "profile_value_without_member",
     "An `expired` event belongs to freshness/0.1 and carries the profile's deadline.",
     lambda d: event(d, "expired").pop("deadline"))
make("nonce-mismatch-without-age-basis", "nonce-replay-rejected", "profile_value_without_member",
     "A `nonce_mismatch` read belongs to freshness/0.1 and its input carries age_basis.",
     lambda d: inputs(d, read_state="nonce_mismatch")[0].pop("age_basis"))
make("overdue-event-without-an-open-check", "overdue-reported-not-closed", "journal_protocol",
     "An `overdue` event reports a live check; with no `opened` event for that check there is nothing live to report.",
     lambda d: event(d, "overdue").update(check_id="syn-check-ghost"))

# ------------------------------------------------------------------------------ profile times are evidence times
make("profile-time-without-offset", "clocks-follow-the-service-clock", "timestamp_invalid",
     "`recorded_at` (freshness/0.1) is timezone-aware like every other time in the record.",
     lambda d: d["decisions"][0].update(recorded_at=d["decisions"][0]["recorded_at"].replace("+00:00", "")))
make("refusal-deadline-without-offset", "expired-before-dispatch", "timestamp_invalid",
     "The refusal's `deadline` is timezone-aware.",
     lambda d: d["refusals"][0].update(deadline=d["refusals"][0]["deadline"].replace("+00:00", "")))

# ------------------------------------------------------------------------------ rule 1 made profile-aware: one lifecycle per effect
make("retry-without-the-expiry-refusal", "expired-then-retry-dispatches", "second_attempt_for_effect",
     "The retry is allowed only because the first attempt failed with check_expired_before_dispatch AND a refusal of the same effect carries that reason and the profile's deadline. Remove the deadline and the failed attempt is no longer excused: two lifecycles start for one effect.",
     lambda d: d["refusals"][0].pop("deadline"))
make("retry-after-an-ordinary-failure", "expired-then-retry-dispatches", "second_attempt_for_effect",
     "Only the expiry excuses a failed start. The first attempt failed for another bounded reason (and the refusal row is the profile's expiry refusal), so the second start is a second lifecycle.",
     lambda d: [a.update(error="grant_revoked") for a in d["attempts"] if a["status"] == "failed"])

# ------------------------------------------------------------------------------ rule 2 made profile-aware: observation clock
make("observation-from-the-future-under-the-profile", "observation-clock-decoupled", "observation_time_future",
     "freshness/0.1 judges 'future' against the service clock re-read at reconciliation (reconciled_at), not against the evaluation pass; an observation later than reconciled_at plus the tolerance is still from the future.",
     lambda d: (d["reconciliations"][0]["observation"].update(observed_at="2026-10-06T19:00:00+00:00")))

# ------------------------------------------------------------------------------ rule 3 made profile-aware: no journal on a lease hold
make("lease-hold-with-another-reason", "lease-unavailable-holds", "journal_missing",
     "The lease hold may omit the journal only when check_lease_unavailable is its sole reason (the lease is refused before a check is journalled). A second reason means a check ran, so the journal must exist.",
     lambda d: (d["decisions"][0].update(reasons=["check_lease_unavailable", "grant_revoked"])))
make("lease-hold-without-the-profile-clock", "lease-unavailable-holds", "journal_missing",
     "The exemption belongs to freshness/0.1 and is recognised by its `evaluated_at` member on the decision; the same hold without it is a default-path record, which has a journal or no vocabulary version.",
     lambda d: d["decisions"][0].pop("evaluated_at"))

if bad:
    sys.exit("mutations that did not give exactly the expected code:\n" + "\n".join(map(str, bad)))
print(len(list(OUT.glob("profile-*.json"))), "invalid fixtures written")
