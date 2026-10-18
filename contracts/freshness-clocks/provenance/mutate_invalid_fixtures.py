"""Mutate the valid freshness-clocks fixtures into the invalid ones (single-defect mutations; each fixture's `provenance` names its base).

    python mutate_invalid_fixtures.py <contracts/freshness-clocks dir>

Reads contracts/freshness-clocks/fixtures/valid and validate.py, rewrites fixtures/invalid, and stops if a mutation does not yield exactly
its one expected code. Rules that join the sidecar to the run record are mutated on the run record (or on both sides, consistently)
and written with `journal`; document rules are written without it.
"""
import copy, json, sys, importlib.util
from pathlib import Path

CDIR = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("fc", CDIR / "validate.py")
fc = importlib.util.module_from_spec(spec)
sys.modules["fc"] = fc
spec.loader.exec_module(fc)
V = {p.stem: json.loads(p.read_text()) for p in (CDIR / "fixtures" / "valid").glob("*.json")}
out_dir = CDIR / "fixtures" / "invalid"
out_dir.mkdir(exist_ok=True)
for p in out_dir.glob("*.json"):
    p.unlink()
CP = "3f6a7668"
results = []
KEEP = object()


def write(fixture):
    (out_dir / f"{fixture['fixture_id']}.json").write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def make(fid, base, code, why, fn=None, journal=False, host=KEEP):
    b = copy.deepcopy(V[base])
    doc, jr = b["document"], b["journal"]
    hs = b.get("host") if host is KEEP else host
    if fn:
        fn(doc, jr)
    fx = {"fixture_id": fid, "synthetic": True, "expected_outcome": "reject", "expected_refusal": code, "reason": why,
          "provenance": {"source": f"mutation of captured fixture {base}", "control_plane_commit": CP}, "document": doc}
    if journal:
        fx["journal"] = jr
    if hs is not None or (host is not KEEP):
        fx["host"] = hs
    got = [v.code for v in fc.validate(doc, jr if journal else None, hs)]
    results.append((fid, code, got))
    write(fx)


DEF, CLK, OPR, WITHIN = "default-path-carries-no-clock-members", "clocks-follow-the-service-clock", "operation-rows-carry-the-clocks", "deadline-at-opening-within-bound"
EXP, EXJ, RETRY, OBS = "expired-before-dispatch", "expired-with-operation-join", "expired-then-retry-dispatches", "observation-clock-decoupled"
OVD, RPR = "overdue-reported-not-closed", "reaper-closes-the-dead-and-reports-the-late"
EXT, EREF, EWD, NOA = "extension-recorded-and-applied", "extension-refusals-kept", "extension-withdrawn-at-use", "extension-without-authority-or-limit"
NB, SA, NR, LEASE, REP = "nonce-bound-reads", "source-asserted-without-capability", "nonce-replay-rejected", "lease-unavailable-holds", "freshness-counts-next-to-refusal-counts"


def events(doc, cid, phase=None):
    return [e for e in doc["check_events"] if e["check_id"] == cid and (phase is None or e["phase"] == phase)]


def first(doc, phase, stage=None):
    return next(e for e in doc["check_events"] if e["phase"] == phase and (stage is None or e["stage"] == stage))


def set_all(doc, cid, **kw):
    for e in events(doc, cid):
        e.update(kw)


def drop_all(doc, cid, member):
    for e in events(doc, cid):
        e.pop(member, None)


def detach_extension(doc):
    """Remove the extension reference from the check that used it, so an extension-row rule is the only one in play."""
    for e in doc["check_events"]:
        e.pop("extension_id", None)


def shift(ts, seconds):
    from datetime import datetime, timedelta
    return (datetime.fromisoformat(ts) + timedelta(seconds=seconds)).isoformat()


# ---- structure
make("undeclared-member-outside-extensions", EXP, "undeclared_member", "A member neither declared nor inside extensions is refused, never dropped.", lambda d, j: d["check_events"][0].update(injected=1))
make("extension-key-without-x-prefix", EXP, "invalid_extension_key", "Extension members use the reserved x- form.", lambda d, j: d.update(extensions={"note": 1}))
make("unsupported-contract-version", EXP, "unsupported_contract_version", "A different contract version is refused typed.", lambda d, j: d.update(contract_version="9.0.0"))
make("profile-marker-wrong", EXP, "schema_violation", "The profile marker is exact.", lambda d, j: d.update(profile="freshness/0.2"))
make("unknown-check-phase", EXP, "unknown_enum_value", "The six phases are closed; a new phase is a major bump.", lambda d, j: d["check_events"][0].update(phase="paused"))
make("unknown-age-basis", NB, "unknown_enum_value", "The two age bases are closed.", lambda d, j: d["input_reads"][0].update(age_basis="verified"))
make("unknown-read-state", NR, "unknown_enum_value", "read_state is unreadable, cached_positive or nonce_mismatch (or null).", lambda d, j: d["input_reads"][0].update(read_state="stale"))
make("unknown-extension-refusal-reason", EREF, "unknown_enum_value", "The six extension reasons are closed.", lambda d, j: d["age_extension_refusals"][0].update(reasons=["age_extension_expired"]))
make("unknown-recovery-trigger", RPR, "unknown_enum_value", "A recovery pass is triggered at startup, on the interval or manually.", lambda d, j: d["recovery_runs"][0].update(trigger="cron"))
make("unknown-clock-row-type", CLK, "unknown_enum_value", "The seven row types are closed.", lambda d, j: d["clock_rows"][0].update(row_type="closeout"))
make("negative-age-bound", WITHIN, "schema_violation", "age_bound_seconds is an integer of at least 0.", lambda d, j: first(d, "opened").update(age_bound_seconds=-1))
make("missing-recorded-at", EXP, "schema_violation", "Every check event and clock row carries recorded_at.", lambda d, j: d["clock_rows"][0].pop("recorded_at"))
make("empty-extension-refusal-reasons", EREF, "schema_violation", "A refusal row states at least one reason.", lambda d, j: d["age_extension_refusals"][0].update(reasons=[]))
make("empty-nonce", NB, "schema_violation", "A nonce, when present, is a non-empty string.", lambda d, j: first(d, "opened").update(nonce=""))
make("freshness-block-with-extra-member", REP, "undeclared_member", "A verbatim producer report carries no extensions and no extra members.", lambda d, j: d["freshness_reports"][0]["report"].update(extra=1))

# ---- times
make("naive-recorded-at", EXP, "timestamp_invalid", "recorded_at carries a UTC offset.", lambda d, j: d["check_events"][1].update(recorded_at="2026-10-05T19:00:00"))
make("naive-deadline", EXP, "timestamp_invalid", "deadline carries a UTC offset.", lambda d, j: first(d, "opened").update(deadline="2026-10-05T19:01:00"))
make("recorded-before-evaluated", CLK, "recorded_before_evaluated", "recorded_at is the service clock at the write and never precedes the evaluation pass that made the row (contract-only).",
     lambda d, j: d["clock_rows"][0].update(evaluated_at=shift(d["clock_rows"][0]["recorded_at"], 3600)))

# ---- ids
def dup_ext(d, j):
    d["age_extensions"].append(copy.deepcopy(d["age_extensions"][0]))
make("duplicate-extension-id", EXT, "duplicate_extension_id", "Extension ids are unique; the producer refuses a reused id as invalid.", dup_ext)
make("duplicate-extension-refusal-id", EREF, "duplicate_extension_refusal_id", "Refusal ids are unique.", lambda d, j: d["age_extension_refusals"][1].update(refusal_id=d["age_extension_refusals"][0]["refusal_id"]))
make("duplicate-recovery-run-id", RPR, "duplicate_recovery_run_id", "Recovery run ids are unique.", lambda d, j: d["recovery_runs"][1].update(run_id=d["recovery_runs"][0]["run_id"]))
make("duplicate-report-id", REP, "duplicate_report_id", "Report ids are unique.", lambda d, j: d["freshness_reports"].append(copy.deepcopy(d["freshness_reports"][0])))
make("duplicate-clock-row", CLK, "duplicate_clock_row", "One clock row per row type, id and sequence.", lambda d, j: d["clock_rows"].append(copy.deepcopy(d["clock_rows"][0])))
make("duplicate-input-read", NB, "duplicate_input_read", "One input read per row and input.", lambda d, j: d["input_reads"].append(copy.deepcopy(d["input_reads"][0])))

# ---- check journal
make("check-opening-missing", DEF, "check_opening_missing", "The first event of a check is its opening (the producer refuses an event of an unopened check).", lambda d, j: d["check_events"].pop(0))
make("check-opened-twice", DEF, "duplicate_check_opening", "A check is opened once (the producer refuses 'check already opened').", lambda d, j: d["check_events"].insert(1, copy.deepcopy(d["check_events"][0])))
make("event-after-completed", DEF, "check_event_after_close", "No event follows a terminal event, except expired after completed.", lambda d, j: d["check_events"].append({**copy.deepcopy(d["check_events"][11]), "phase": "input"}))


def expire_interrupted(d, j):
    opening = next(e for e in d["check_events"] if e["check_id"] == "orphan" and e["phase"] == "opened")
    d["check_events"].append({**copy.deepcopy(opening), "phase": "expired", "recorded_at": shift(opening["deadline"], 5), "reasons": ["check_expired_before_dispatch"]})
make("expired-after-interrupted", RPR, "expired_after_closed_check", "expired is allowed after completed, never after interrupted (the producer refuses 'check already closed').", expire_interrupted)
make("expired-twice", EXP, "expired_after_closed_check", "expired is written once.", lambda d, j: d["check_events"].append(copy.deepcopy(d["check_events"][-1])))
make("overdue-reported-twice", OVD, "overdue_repeated", "A check is reported overdue once (the producer refuses 'check already reported overdue').",
     lambda d, j: d["check_events"].insert(next(i for i, e in enumerate(d["check_events"]) if e["phase"] == "overdue") + 1, copy.deepcopy(next(e for e in d["check_events"] if e["phase"] == "overdue"))))
make("event-time-moves-backwards", DEF, "check_event_time_regression", "recorded_at does not move backwards within a check (contract-only).", lambda d, j: d["check_events"][11].update(recorded_at="2026-10-05T18:00:00+00:00"))
make("later-event-deadline-differs-from-opening", EXP, "check_event_clock_drift", "Every later event of a check carries the opening's deadline, age bound, extension and nonce (the producer copies the opening).", lambda d, j: d["check_events"][1].update(deadline="2026-10-05T19:05:00+00:00"))
make("expired-event-with-the-wrong-reason", EXP, "phase_reasons_mismatch", "An expired event carries exactly check_expired_before_dispatch.", lambda d, j: first(d, "expired").update(reasons=["check_overdue"]))
make("overdue-event-with-the-wrong-reason", OVD, "phase_reasons_mismatch", "An overdue event carries exactly check_overdue.", lambda d, j: first(d, "overdue").update(reasons=["check_interrupted"]))


def overdue_no_deadline(d, j):
    opening = d["check_events"][0]
    d["check_events"].insert(1, {**copy.deepcopy(opening), "phase": "overdue", "recorded_at": shift(opening["recorded_at"], 100), "reasons": ["check_overdue"]})
    for e in d["check_events"][2:]:
        if e["check_id"] == opening["check_id"]:
            e["recorded_at"] = shift(opening["recorded_at"], 100)
make("overdue-on-a-check-without-a-deadline", DEF, "overdue_without_deadline", "A check opened without a deadline is open but never overdue.", overdue_no_deadline)
make("expired-on-a-check-without-a-deadline", DEF, "expired_without_deadline", "An expired event needs a check opened with a deadline.",
     lambda d, j: d["check_events"].append({**copy.deepcopy(d["check_events"][11]), "phase": "expired", "reasons": ["check_expired_before_dispatch"], "recorded_at": shift(d["check_events"][11]["recorded_at"], 100)}))
make("overdue-before-the-deadline", OVD, "overdue_before_deadline", "The recovery pass reports a live check overdue only after its deadline.", lambda d, j: first(d, "overdue").update(recorded_at=shift(first(d, "opened")["deadline"], -30)))
make("expired-not-past-the-deadline", EXP, "expired_not_past_deadline", "The dispatch gate expires a check only after its deadline.", lambda d, j: first(d, "expired").update(recorded_at=shift(first(d, "expired")["deadline"], -1)))


def drop_bound(d, j):
    cid = first(d, "opened")["check_id"]
    drop_all(d, cid, "age_bound_seconds")
make("deadline-without-age-bound", WITHIN, "deadline_members_incomplete", "deadline and age_bound_seconds are carried together or not at all.", drop_bound)


def move_deadline(d, j):
    cid = first(d, "opened")["check_id"]
    for e in events(d, cid):
        e["deadline"] = shift(e["deadline"], 5)
make("deadline-is-not-opening-plus-bound", WITHIN, "deadline_mismatch", "deadline is the opening's recorded_at plus age_bound_seconds.", move_deadline)


def reuse_nonce(d, j):
    opened = [e for e in d["check_events"] if e["phase"] == "opened"]
    for e in events(d, opened[1]["check_id"]):
        e["nonce"] = opened[0]["nonce"]
make("nonce-reused-across-checks", NB, "nonce_reused_across_checks", "A nonce belongs to one check (the producer draws a fresh one per check; contract-only).", reuse_nonce)


def ghost_extension(d, j):
    set_all(d, [e for e in d["check_events"] if e.get("extension_id")][0]["check_id"], extension_id="syn-extension-9")
make("extension-id-names-no-row", EXT, "extension_unknown", "An extension_id on an opening names an age_extensions row.", ghost_extension)


def wrong_bound(d, j):
    cid = [e for e in d["check_events"] if e.get("extension_id")][0]["check_id"]
    for e in events(d, cid):
        e["age_bound_seconds"] = 300
        e["deadline"] = shift(first(d, "opened")["recorded_at"] if False else next(x for x in events(d, cid, "opened"))["recorded_at"], 300)
make("age-bound-is-not-the-extension-bound", EXT, "extension_bound_mismatch", "With an extension the age bound is its to_max_age_seconds.", wrong_bound)
make("extension-window-does-not-cover-the-pass", EXT, "extension_outside_window", "The extension window covers the evaluation pass of the check it raised.",
     lambda d, j: d["age_extensions"][0].update(not_before=shift(d["age_extensions"][0]["not_before"], 36000), expires_at=shift(d["age_extensions"][0]["expires_at"], 36000)))
make("extension-recorded-after-the-check-it-raised", EXT, "extension_recorded_after_use", "An extension recorded after the opening cannot have raised its bound.", lambda d, j: d["age_extensions"][0].update(recorded_at=shift(d["age_extensions"][0]["recorded_at"], 7200), evaluated_at=shift(d["age_extensions"][0]["evaluated_at"], 7200)))


def ext_mut(**kw):
    def fn(d, j):
        detach_extension(d)
        d["age_extensions"][0].update(kw)
    return fn
make("accepted-extension-unsigned", EXT, "accepted_extension_unsigned", "An unsigned extension never counts; it is refused and kept as a refusal row, never accepted.", ext_mut(signer=None))
make("accepted-extension-self-signed", EXT, "accepted_extension_self_signed", "The signer is not the requester.", lambda d, j: (detach_extension(d), d["age_extensions"][0].update(signer=d["age_extensions"][0]["requested_by"])))
make("accepted-extension-bound-does-not-rise", EXT, "accepted_extension_invalid", "An accepted extension raises the bound.", ext_mut(to_max_age_seconds=60))
make("accepted-extension-exceeds-the-declared-limit", EXT, "accepted_extension_exceeds_limit", "With the declared limit supplied, an accepted extension does not exceed it.", ext_mut(to_max_age_seconds=1000))
make("accepted-extension-without-configured-authority", EXT, "accepted_extension_authority_unconfigured", "No extension is accepted when no rule-revision signer set is configured.",
     lambda d, j: detach_extension(d), host={"signers": None, "max_age_extension_seconds": 300})
make("nonce-bound-from-a-resolver-without-the-capability", NB, "nonce_bound_without_capability", "nonce_bound needs a resolver that declares status-nonce/0.1.", host={"resolver_capability": None})

# ---- extension refusals
make("refusal-reasons-not-sorted", NOA, "extension_refusal_reasons_not_canonical", "Reasons are sorted and unique, as the producer writes them.", lambda d, j: d["age_extension_refusals"][0].update(reasons=list(reversed(d["age_extension_refusals"][0]["reasons"]))))
make("refusal-recorded-at-another-time", EREF, "extension_refusal_time_mismatch", "A refusal is recorded at the extension's own recorded_at.", lambda d, j: d["age_extension_refusals"][0].update(recorded_at=shift(d["age_extension_refusals"][0]["recorded_at"], 9)))
make("unsigned-reason-for-a-signed-extension", EREF, "extension_refusal_reason_mismatch", "age_extension_unsigned is listed if and only if there is no signer.", lambda d, j: d["age_extension_refusals"][0].update(reasons=["age_extension_self_signed"]))
make("exceeds-limit-reason-for-a-small-extension", EREF, "extension_refusal_reason_mismatch", "With the declared limit supplied, age_extension_exceeds_limit is listed if and only if the raise is above it.", lambda d, j: d["age_extension_refusals"][2].update(reasons=["age_extension_exceeds_limit"]))
make("signer-not-configured-reason-without-host-set", EREF, "extension_refusal_reason_mismatch", "With the signer set supplied, age_extension_signer_not_configured is listed if and only if the signer is outside it.", lambda d, j: d["age_extension_refusals"][2].update(reasons=["age_extension_unsigned"]))
make("authority-unconfigured-reason-with-a-configured-set", EREF, "extension_refusal_reason_mismatch", "age_extension_authority_unconfigured is listed only when no rule-revision profile is configured.", lambda d, j: d["age_extension_refusals"][0].update(reasons=["age_extension_authority_unconfigured", "age_extension_unsigned"]))

# ---- recovery runs
make("open-count-below-the-overdue-checks", OVD, "recovery_run_open_count_below_overdue", "open_count includes every overdue check.", lambda d, j: d["recovery_runs"][0].update(open_count=0, oldest_open_age_seconds=None))
make("oldest-age-with-nothing-open", RPR, "recovery_run_oldest_age_inconsistent", "oldest_open_age_seconds is null if and only if no check is open.", lambda d, j: d["recovery_runs"][0].update(oldest_open_age_seconds=5.0))
make("interrupted-check-without-an-interrupted-event", RPR, "recovery_interrupted_without_event", "Each interrupted check has an interrupted event stamped with the pass time.", lambda d, j: d["recovery_runs"][1].update(interrupted=["orphan"]))
make("overdue-check-without-an-overdue-event", RPR, "recovery_overdue_without_event", "Each overdue check has an overdue event written at or before the pass.", lambda d, j: d["recovery_runs"][1].update(overdue=["ghost"], open_count=1, oldest_open_age_seconds=3.0))

# ---- age basis
make("nonce-mismatch-read-marked-nonce-bound", NR, "nonce_mismatch_basis", "A read whose echoed nonce differs is never nonce_bound.", lambda d, j: next(x for x in d["input_reads"] if x["read_state"]).update(age_basis="nonce_bound"))
make("nonce-mismatch-with-equal-nonces", NR, "nonce_members_inconsistent", "nonce_mismatch carries two different nonces.", lambda d, j: (lambda x: x.update(observed_nonce=x["expected_nonce"]))(next(x for x in d["input_reads"] if x["read_state"])))
make("nonces-on-a-read-that-matched", NB, "nonce_members_inconsistent", "Any other read carries no nonces.", lambda d, j: d["input_reads"][0].update(expected_nonce="syn-nonce-01", observed_nonce="syn-nonce-01"))
make("input-read-names-an-unopened-check", NB, "input_read_check_unknown", "check_id names a check opened in check_events.", lambda d, j: next(x for x in d["input_reads"] if x["check_id"]).update(check_id="no-such-check"))


def bound_without_nonce(d, j):
    bound = next(x for x in d["input_reads"] if x["check_id"] and x["age_basis"] == "nonce_bound")
    drop_all(d, bound["check_id"], "nonce")
make("nonce-bound-read-in-a-check-without-a-nonce", NB, "nonce_bound_without_nonce", "A nonce_bound read belongs to a check that sent a nonce.", bound_without_nonce)
make("expected-nonce-is-not-the-checks-nonce", NR, "nonce_expected_not_check_nonce", "The expected nonce of a mismatch is the nonce the check sent.", lambda d, j: next(x for x in d["input_reads"] if x["read_state"]).update(expected_nonce="syn-nonce-99"))

# ---- report
make("freshness-count-differs-from-the-events", REP, "freshness_counts_mismatch", "The counts are derived from the check events of the document as of as_of.", lambda d, j: d["freshness_reports"][0]["report"].update(overdue_count=d["freshness_reports"][0]["report"]["overdue_count"] + 1))

# ---- journal context
make("journal-of-another-run", EXP, "journal_run_mismatch", "The sidecar and the run record describe the same run.", lambda d, j: j.update(run_id="other-run"), journal=True)
make("journal-check-event-differs", EXP, "check_events_mismatch", "The sidecar's check events are the run record's, member for member, in order.", lambda d, j: j["check_events"][0].update(deadline="2026-10-05T19:09:00+00:00"), journal=True)
make("journal-extension-row-differs", EXT, "profile_rows_mismatch", "The sidecar's extension rows are the run record's rows.", lambda d, j: j["age_extensions"][0].update(outage_ref="outage-2"), journal=True)
make("clock-row-names-no-row", CLK, "clock_row_unknown_row", "A clock row names a row of the run record that carries the profile's members.", lambda d, j: d["clock_rows"].append({"row_type": "decision", "row_id": "ghost", "seq": 0, "recorded_at": "2026-10-05T19:00:00+00:00"}), journal=True)
make("clock-row-differs-from-the-row", CLK, "clock_row_mismatch", "The clock row is the row's evaluated_at, recorded_at and deadline.", lambda d, j: j["decisions"][0].update(recorded_at="2026-10-05T19:00:09+00:00"), journal=True)
make("row-with-clock-members-has-no-clock-row", CLK, "clock_row_missing", "Every row that carries the profile's members has a clock row.", lambda d, j: d["clock_rows"].pop(0), journal=True)
make("operation-row-without-its-clock-row", OPR, "clock_row_missing", "The operation, renewal and join rows carry clock rows too.", lambda d, j: d["clock_rows"].pop(next(i for i, r in enumerate(d["clock_rows"]) if r["row_type"] == "operation_renewal")), journal=True)
make("input-read-names-no-input", NB, "input_read_unknown_input", "An input read names an input of a row of the run record that carries age_basis.", lambda d, j: d["input_reads"].append({**copy.deepcopy(d["input_reads"][0]), "input_id": "ghost-input"}), journal=True)
make("input-read-differs-from-the-input", NB, "input_read_mismatch", "The input read is the input's age_basis, read_state and nonces.", lambda d, j: next(x for x in d["input_reads"] if x["age_basis"] == "nonce_bound").update(age_basis="source_asserted"), journal=True)
make("input-with-an-age-basis-has-no-input-read", NB, "input_read_missing", "Every input that carries an age_basis has an input read.", lambda d, j: d["input_reads"].pop(0), journal=True)
make("decided-at-is-not-the-evaluation-time", CLK, "evaluation_alias_mismatch", "decided_at keeps its evaluation-time meaning: it equals evaluated_at.", lambda d, j: j["decisions"][0].update(decided_at="2026-10-05T19:00:03+00:00"), journal=True)
make("nonce-mismatch-refusal-without-the-reason", NR, "nonce_reason_mismatch", "status_nonce_mismatch is a reason if and only if an input read ended in nonce_mismatch.", lambda d, j: j["refusals"][0].update(reasons=["grant_status_stale_or_future"]), journal=True)
make("lease-hold-with-another-reason", LEASE, "lease_unavailable_with_other_reasons", "check_lease_unavailable is the only reason: no read happened.", lambda d, j: j["decisions"][0]["reasons"].append("grant_revoked"), journal=True)
make("lease-hold-with-an-attempt", LEASE, "lease_unavailable_dispatched", "A decision held for check_lease_unavailable has no attempt.",
     lambda d, j: j["attempts"].append({"attempt_id": "ghost-attempt", "effect_id": j["decisions"][0]["effect_id"], "decision_id": j["decisions"][0]["decision_id"],
                                        "started_at": "2026-10-05T19:00:00+00:00", "time_source": "test_override", "status": "attempted", "acknowledgement": {}, "error": None}), journal=True)


def drop_refusal_link(d, j):
    j["refusals"][0].pop("check_id")
    for x in d["input_reads"]:
        if x["row_type"] == "refusal":
            x["check_id"] = None
make("expired-check-without-a-refusal-naming-it", EXP, "expired_refusal_mismatch", "A check has an expired event if and only if a refusal row with check_expired_before_dispatch names it (check_id).", drop_refusal_link, journal=True)


def drop_expired_event(d, j):
    cid = first(d, "expired")["check_id"]
    for doc in (d, j):
        doc["check_events"] = [e for e in doc["check_events"] if not (e["check_id"] == cid and e["phase"] == "expired")]
make("expired-refusal-without-an-expired-event", EXP, "expired_refusal_mismatch", "A refusal with check_expired_before_dispatch names a check with an expired event.", drop_expired_event, journal=True)


def refusal_deadline(d, j):
    j["refusals"][0]["deadline"] = "2026-10-05T19:00:30+00:00"
    next(r for r in d["clock_rows"] if r["row_type"] == "refusal")["deadline"] = "2026-10-05T19:00:30+00:00"
make("refusal-deadline-is-not-the-checks-deadline", EXP, "expired_refusal_deadline_mismatch", "The refusal's deadline is the check's deadline.", refusal_deadline, journal=True)
make("expired-check-with-no-failed-attempt", EXP, "expired_without_failed_attempt", "The attempt of an expired check is failed with check_expired_before_dispatch.", lambda d, j: j["attempts"][-1].update(error="destination_timeout"), journal=True)
make("expired-error-on-an-attempted-row", EXP, "expired_attempt_not_failed", "check_expired_before_dispatch is only the error of a failed attempt.", lambda d, j: j["attempts"][0].update(error="check_expired_before_dispatch"), journal=True)
make("expired-attempt-without-a-refusal-for-its-effect", EXP, "expired_attempt_without_refusal", "An attempt failed with check_expired_before_dispatch has a refusal row for its effect.",
     lambda d, j: j["attempts"].append({"attempt_id": "ghost-attempt", "effect_id": "sha256:" + "0" * 64, "decision_id": j["decisions"][0]["decision_id"], "started_at": "2026-10-05T19:00:00+00:00",
                                        "time_source": "test_override", "status": "failed", "acknowledgement": {}, "error": "check_expired_before_dispatch"}), journal=True)
make("extension-reason-no-active-extension-explains", EXT, "extension_reason_unexplained", "An extension reason on a decision needs an extension, active at the evaluation pass, that shows it.", lambda d, j: j["decisions"][-1]["reasons"].append("age_extension_exceeds_limit"), journal=True)
make("expired-check-licensed-a-dispatch", EXJ, "expired_check_dispatched", "A check whose licence expired at the gate licensed no dispatch.",
     lambda d, j: (j["attempts"].append({"attempt_id": "ghost-attempt", "effect_id": j["attempts"][0]["effect_id"], "decision_id": j["attempts"][0]["decision_id"], "started_at": "2026-10-05T19:00:00+00:00",
                                         "time_source": "test_override", "status": "acknowledged", "acknowledgement": {"reconciled_existing": True}, "error": None}),
                   j["attempt_joins"].append({**copy.deepcopy(j["attempt_joins"][0]), "join_id": "ghost-join", "attempt_id": "ghost-attempt"}),
                   [j["attempt_joins"][-1].pop(k) for k in ("evaluated_at",)]), journal=True)
make("retry-after-a-second-lifecycle", RETRY, "prior_attempt_not_excluded", "Only attempts refused at the gate are excluded from the prior-attempt rule: another lifecycle for the effect is a second attempt.",
     lambda d, j: j["attempts"].append({"attempt_id": "ghost-attempt", "effect_id": j["attempts"][0]["effect_id"], "decision_id": j["attempts"][0]["decision_id"], "started_at": "2026-10-05T19:02:00+00:00",
                                        "time_source": "test_override", "status": "attempted", "acknowledgement": {}, "error": None}), journal=True)

bad = [(f, c, g) for f, c, g in results if g != [c]]
for f, c, g in bad:
    print("MISMATCH", f, "expected", c, "got", g)
print(len(results), "invalid fixtures,", len(bad), "mismatches")
if bad:
    sys.exit(1)
