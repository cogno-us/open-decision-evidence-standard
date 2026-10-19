"""Capture the valid freshness-clocks fixtures from real Control Plane runs (step 1 of 2; step 2 is build_fixtures.py).

Not a test and not vendored. Run from a checkout of cogno-us/cognous-control-plane at 3f6a7668 (main after N3, #47) with its dev
dependencies installed:

    PYTHONPATH=src:. python capture_fixtures.py <raw-dir>

It drives the Control Plane's own flows (the helpers of tests/test_freshness.py: synthetic proposals, a settable service clock,
throwaway stores in temporary directories, the opt-in `freshness` profile) and writes each run record unchanged, with the facts the
build step needs (the configured signer set, the profile limit, the class bound). Nothing is hand-written. Random ids (uuid4, nonces)
are replaced by build_fixtures.py, so two captures build the same fixtures byte for byte.
"""
import json
import sys
import tempfile
import threading
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import agent_control_plane.bounded as bounded
from agent_control_plane.bounded import CheckEvent, _process_owner, commitment
from agent_control_plane.freshness import AgeExtensionRefused, CheckLeaseUnavailable
from agent_control_plane.operation_identity import OperationIdentityProfile
from agent_control_plane.reason_vocabulary import refusal_trends
from agent_control_plane.rule_revision import RuleRevisionProfile
from tests.test_bounded_authorization import ISSUER, NOW, PROFILE
from tests.test_freshness import (Clock, OTHER, POLICY_SIGNER, SIGNER, authority, enable, execute, request, stale_grant,
                                  stall_before_dispatch)
from tests.test_runtime_authority import setup_flow, sign_evidence

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
CLOCK = Clock()
bounded._now = CLOCK


def fresh_dir():
    CLOCK.now = NOW
    return Path(tempfile.mkdtemp(prefix="cap-"))


def run_doc(f):
    return json.loads(f.records.path.read_text(encoding="utf-8"))


def save(name, f, **facts):
    (OUT / f"{name}.json").write_text(json.dumps({"run": run_doc(f), "facts": facts}, indent=1, ensure_ascii=False), encoding="utf-8")


def refresh_inputs(r):
    for collection in (r.statuses, r.identities, r.mandates, r.approvals, r.policies, r.conflicts, r.evidence):
        for item in collection.values():
            item.observed_at = CLOCK.now.isoformat()
    for status in r.evidence.values():
        sign_evidence(status)


def start(**options):
    p, r, f, c = setup_flow(fresh_dir())
    return p, r, f, enable(r, f, c, **options)


def with_identity(r, f, c, operation_id="op-order-100/refund-1"):
    cfg = c.model_copy(update={"operation_identity": OperationIdentityProfile(resolver_id="synthetic-resolver", resolver_version="1")})
    r.contexts[PROFILE]["runtime_authority"]["operation_id"] = operation_id
    from tests.test_runtime_authority import bind_approval
    bind_approval(r, cfg)
    f.runtime_authority_profile = cfg.snapshot()
    return cfg


def default_path():
    """Profile unset: the legacy shape, no freshness member anywhere."""
    p, r, f, c = setup_flow(fresh_dir())
    d = f.decide(p, now=NOW)
    execute(f, p, d)
    save("default-path", f)


def clocks_follow_the_service_clock():
    """Reads take wall time: decision and effect passes with slow reads; every journal event stamped at its own write."""
    p, r, f, c = start()
    original = r.identity_status

    def slow(*a):
        CLOCK.tick(7)
        return original(*a)
    r.identity_status = slow
    d = f.decide(p, now=NOW)
    CLOCK.tick(3)
    execute(f, p, d)
    save("clocks-follow-the-service-clock", f)


def operation_rows_carry_the_clocks():
    """operation-identity/0.1 and freshness/0.1 together: operation, renewal and join rows carry evaluated_at; admitted_at / recorded_at are the write time."""
    p, r, f, c = start()
    with_identity(r, f, c)
    d = f.decide(p, now=NOW)
    CLOCK.tick(2)
    execute(f, p, d)
    CLOCK.tick(4)
    f.record_renewal("op-order-100/refund-1", to_revision="2", written_by=ISSUER, now=NOW)
    save("operation-rows-carry-the-clocks", f)


def deadline_at_opening_within_bound():
    p, r, f, c = start()
    CLOCK.tick(2)
    d = f.decide(p, now=NOW)
    stall_before_dispatch(f, CLOCK, 59, pin_observation=True)
    attempt, _ = execute(f, p, d)
    assert attempt.status == "acknowledged"
    save("deadline-at-opening-within-bound", f)


def expired_before_dispatch():
    p, r, f, c = start()
    d = f.decide(p, now=NOW)
    stall_before_dispatch(f, CLOCK, 61, pin_observation=True)
    try:
        execute(f, p, d)
    except PermissionError:
        pass
    assert f.destination.snapshot()["effects"] == {}
    save("expired-before-dispatch", f)


def expired_with_operation_join():
    """operation-identity/0.1 and freshness/0.1 together: the join row is written before the attempt row, so an expired check has a join whose attempt is failed."""
    p, r, f, c = start()
    with_identity(r, f, c)
    d = f.decide(p, now=NOW)
    stall_before_dispatch(f, CLOCK, 61, pin_observation=True)
    try:
        execute(f, p, d)
    except PermissionError:
        pass
    assert f.destination.snapshot()["effects"] == {}
    save("expired-with-operation-join", f)


def expired_then_retry_dispatches():
    """The expired check's failed attempt does not poison a later retry: a fresh check, a fresh deadline, an acknowledged attempt."""
    p, r, f, c = start()
    d = f.decide(p, now=NOW)
    original = stall_before_dispatch(f, CLOCK, 61, pin_observation=True)
    try:
        execute(f, p, d)
    except PermissionError:
        pass
    f.destination.observe = original
    refresh_inputs(r)
    attempt, _ = execute(f, p, d, now=CLOCK.now)
    assert attempt.status == "acknowledged"
    save("expired-then-retry-dispatches", f)


def observation_clock_decoupled():
    """A live observation clock stamps the observation after the evaluation pass: not 'future' under the profile; the deadline decides."""
    p, r, f, c = start()
    d = f.decide(p, now=NOW)
    stall_before_dispatch(f, CLOCK, 61)
    try:
        execute(f, p, d)
    except PermissionError:
        pass
    save("observation-clock-decoupled", f)


def overdue_reported_not_closed():
    p, r, f, c = start()
    release, started = threading.Event(), threading.Event()
    original = r.grant_status

    def blocked(ref):
        started.set()
        release.wait(20)
        return original(ref)
    r.grant_status = blocked
    thread = threading.Thread(target=lambda: f.decide(p, now=NOW))
    thread.start()
    assert started.wait(10)
    CLOCK.tick(61)
    first = f.records.recovery_pass(trigger="manual", record_run=True)
    assert len(first.overdue) == 1
    CLOCK.tick(5)
    second = f.records.recovery_pass(trigger="manual", record_run=True)
    assert len(second.overdue) == 1
    release.set()
    thread.join(20)
    save("overdue-reported-not-closed", f)


def reaper_closes_the_dead_and_reports_the_late():
    p, r, f, c = start(reaper_interval_seconds=30)
    f.records.append_check_event(CheckEvent(check_id="orphan", phase="opened", stage="decision", recorded_at=NOW.isoformat(),
                                            owner=_process_owner(), proposal_commitment=commitment({}),
                                            deadline=(NOW + timedelta(seconds=60)).isoformat(), age_bound_seconds=60))
    reaper = f.reaper(clock=CLOCK)
    reaper.run_due()
    CLOCK.tick(35)
    reaper.run_due()
    save("reaper-closes-the-dead-and-reports-the-late", f)


def extension_applies():
    p, r, f, c = start(max_age_extension_seconds=300)
    authority(f, r)
    stale_grant(r, 70)
    held = f.decide(p, now=NOW)
    assert held.result == "hold"
    request(f)
    ok = f.decide(p, now=NOW)
    assert ok.result == "authorized"
    save("extension-recorded-and-applied", f, signers=[SIGNER, POLICY_SIGNER], max_age_extension_seconds=300)


def extension_refusals():
    p, r, f, c = start(max_age_extension_seconds=300)
    authority(f, r)
    for override in ({"signer": None}, {"signer": OTHER}, {"signer": "urn:cognous:principal:nobody"}, {"to_max_age_seconds": 1000},
                     {"to_max_age_seconds": 60}, {"outage_ref": "x", "expires_at": NOW.isoformat()}):
        try:
            request(f, **override)
        except AgeExtensionRefused:
            pass
    save("extension-refusals-kept", f, signers=[SIGNER, POLICY_SIGNER], max_age_extension_seconds=300)


def extension_without_authority_or_limit():
    p, r, f, c = start()  # limit 0 and no rule-revision profile
    try:
        request(f)
    except AgeExtensionRefused:
        pass
    save("extension-without-authority-or-limit", f, signers=None, max_age_extension_seconds=0)


def extension_withdrawn_at_use():
    p, r, f, c = start(max_age_extension_seconds=300)
    authority(f, r)
    request(f)
    stale_grant(r, 70)
    assert f.decide(p, now=NOW).result == "authorized"
    f.rule_revision_profile = RuleRevisionProfile(signers=[POLICY_SIGNER])
    d = f.decide(p, now=NOW)
    assert d.result == "hold" and "age_extension_signer_not_configured" in d.reasons
    save("extension-withdrawn-at-use", f, signers=[POLICY_SIGNER], max_age_extension_seconds=300)


def nonce_bound():
    p, r, f, c = start()
    r.echo_nonce = True
    d = f.decide(p, now=NOW)
    assert d.result == "authorized"
    execute(f, p, d)
    save("nonce-bound-reads", f, resolver_capability="status-nonce/0.1")


def source_asserted():
    p, r, f, c = start()
    d = f.decide(p, now=NOW)
    assert d.result == "authorized"
    save("source-asserted-without-capability", f, resolver_capability=None)


def nonce_replay_rejected():
    p, r, f, c = start()
    r.echo_nonce = True
    d = f.decide(p, now=NOW)
    recorded = {}
    original = r.nonce_read

    def recording(nonce, method, *args):
        recorded[method] = original(nonce, method, *args)
        return recorded[method]
    r.nonce_read = recording
    f.decide(p, now=NOW)

    def replaying(nonce, method, *args):
        if method == "grant_status":
            return recorded["grant_status"][0], recorded["grant_status"][1]
        return original(nonce, method, *args)
    r.nonce_read = replaying
    try:
        execute(f, p, d)
    except PermissionError:
        pass
    save("nonce-replay-rejected", f, resolver_capability="status-nonce/0.1")


def lease_unavailable():
    p, r, f, c = start(lease_acquire_timeout_seconds=0.05)

    @contextmanager
    def unavailable(check_id, *, acquire_timeout=None):
        raise CheckLeaseUnavailable("check_lease_unavailable")
        yield
    f.records.check_lease = unavailable
    d = f.decide(p, now=NOW)
    assert d.reasons == ["check_lease_unavailable"]
    save("lease-unavailable-holds", f)


def freshness_report():
    """refusal_trends with check_events and as_of: the freshness block next to the refusal counts (the real function output)."""
    p, r, f, c = start()
    d = f.decide(p, now=NOW)
    stall_before_dispatch(f, CLOCK, 61, pin_observation=True)
    try:
        execute(f, p, d)
    except PermissionError:
        pass
    f.records.append_check_event(CheckEvent(check_id="orphan", phase="opened", stage="effect", recorded_at=NOW.isoformat(),
                                            owner=_process_owner(), proposal_commitment=commitment({})))
    f.records.recover_interrupted_checks()
    f.records.append_check_event(CheckEvent(check_id="stuck", phase="opened", stage="effect",
                                            recorded_at=(CLOCK.now - timedelta(seconds=90)).isoformat(),
                                            owner=_process_owner(), proposal_commitment=commitment({}),
                                            deadline=(CLOCK.now - timedelta(seconds=30)).isoformat(), age_bound_seconds=60))
    rec = f.records.load()
    refusals = [x.model_dump(mode="json") for x in rec.refusals]
    report = refusal_trends([], refusals, previous_exposure=0, current_exposure=1,
                            check_events=[e.model_dump(mode="json") for e in rec.check_events], as_of=CLOCK.now.isoformat())
    save("freshness-report", f, trend_report=report)


for fn in (default_path, clocks_follow_the_service_clock, operation_rows_carry_the_clocks, deadline_at_opening_within_bound,
           expired_before_dispatch, expired_with_operation_join, expired_then_retry_dispatches, observation_clock_decoupled, overdue_reported_not_closed,
           reaper_closes_the_dead_and_reports_the_late, extension_applies, extension_refusals, extension_without_authority_or_limit,
           extension_withdrawn_at_use, nonce_bound, source_asserted, nonce_replay_rejected, lease_unavailable, freshness_report):
    fn()
    print("captured", fn.__name__)
