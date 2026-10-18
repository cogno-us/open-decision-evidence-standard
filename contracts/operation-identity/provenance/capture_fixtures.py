"""Capture the valid operation-identity fixtures from real Control Plane runs (step 1 of 2; step 2 is build_fixtures.py).

Not a test and not vendored. Run from a checkout of cogno-us/cognous-control-plane (main 83b49b5 or later) with its dev
dependencies installed:

    PYTHONPATH=src:. python capture_fixtures.py <raw-dir>

It runs the Control Plane's own flows (the helpers of tests/test_operation_identity.py: synthetic proposals, fixed clock,
throwaway stores) and writes each run record unchanged. Nothing is hand-written.
"""
import json
import sys
import tempfile
from pathlib import Path

import pytest

import agent_control_plane.bounded as bounded
from tests.test_bounded_authorization import ISSUER, NOW, PROFILE
from tests.test_runtime_authority import setup_flow
import tests.test_operation_identity as oi

bounded._now = lambda: NOW
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)


def tmp():
    return Path(tempfile.mkdtemp(prefix="cap-"))


def run_doc(f):
    return json.loads(f.records.path.read_text(encoding="utf-8"))


def save(name, f, extra=None):
    (OUT / f"{name}.json").write_text(json.dumps({"run": run_doc(f), "extra": extra or {}}, indent=1, ensure_ascii=False), encoding="utf-8")


# ----------------------------------------------------------------------------------------------- operation identity
def op_normal():
    p, r, f, c = setup_flow(tmp())
    oi.enable(r, f, c)
    d = f.decide(p, now=NOW)
    f.execute(p, d, adapter_id=p.adapter_id, now=NOW)
    save("op-normal", f)


def op_renewal_accepted():
    p, r, f, c = setup_flow(tmp())
    cfg = oi.enable(r, f, c)
    d1 = f.decide(p, now=NOW)
    oi.renew(r, cfg, "2")
    f.record_renewal(oi.OPERATION, to_revision="2", written_by=ISSUER, now=NOW)
    d2 = f.decide(p, now=NOW)
    f.execute(p, d2, adapter_id=p.adapter_id, now=NOW)
    save("op-renewal-accepted", f)


def op_worker_self_renewal():
    p, r, f, c = setup_flow(tmp())
    cfg = oi.enable(r, f, c)
    f.decide(p, now=NOW)
    try:
        f.record_renewal(oi.OPERATION, to_revision="2", written_by=p.actor, now=NOW)
    except PermissionError:
        pass
    oi.renew(r, cfg, "2")
    d2 = f.decide(p, now=NOW)
    assert d2.result == "hold" and "operation_renewal_unrecorded" in d2.reasons
    save("op-worker-self-renewal-then-unrecorded-hold", f)


def op_renewal_refusals():
    p, r, f, c = setup_flow(tmp())
    oi.enable(r, f, c)
    f.decide(p, now=NOW)
    for op, rev in (("unknown-op", "2"), (oi.OPERATION, "1")):
        try:
            f.record_renewal(op, to_revision=rev, written_by=ISSUER, now=NOW)
        except PermissionError:
            pass
    save("op-renewal-refused-not-admitted-and-not-new", f)


def op_refusal_check_id():
    p, r, f, c = setup_flow(tmp())
    oi.enable(r, f, c)
    d = f.decide(p, now=NOW)
    next(iter(r.statuses.values())).status = "revoked"
    try:
        f.execute(p, d, adapter_id=p.adapter_id, now=NOW)
    except PermissionError:
        pass
    save("op-effect-time-refusal-carries-check-id", f)


def op_duplicate_submission():
    p, r, f, c = setup_flow(tmp())
    oi.enable(r, f, c)
    d = f.decide(p, now=NOW)
    f.execute(p, d, adapter_id=p.adapter_id, now=NOW)
    f.execute(p, d, adapter_id=p.adapter_id, now=NOW)
    save("op-duplicate-submission-reconciled-existing", f)


def op_lost_ack():
    p, r, f, c = setup_flow(tmp())
    oi.enable(r, f, c)
    d = f.decide(p, now=NOW)
    f.execute(p, d, adapter_id=p.adapter_id, now=NOW, lose_ack=True)
    f.reconcile(d.effect_id, now=NOW)
    f.execute(p, d, adapter_id=p.adapter_id, now=NOW)
    save("op-lost-ack-then-reconciled-existing", f)


def op_delayed():
    with pytest.MonkeyPatch.context() as mp:
        f, d1, d2, outcome = oi.delayed_renewal_flow(tmp(), identity=True, monkeypatch=mp)
    save("op-delayed-first-attempt-rejected-after-renewal", f, {"d1_effect": d1.effect_id, "d2_effect": d2.effect_id,
                                                                  "destination": f.destination.snapshot()})


def op_wrong_operation_grant():
    p, r, f, c = setup_flow(tmp())
    oi.enable(r, f, c)
    f.decide(p, now=NOW)
    document = run_doc(f)
    document["operations"][0]["grant_id"] = "urn:cognous:grant:other"
    f.records._write(document)
    d = f.decide(p, now=NOW)
    assert "operation_grant_mismatch" in d.reasons
    save("op-grant-mismatch-held", f)


def op_missing_invalid():
    for tag, value in (("missing", None), ("invalid", "has space")):
        p, r, f, c = setup_flow(tmp())
        oi.enable(r, f, c, operation_id=None)
        if value:
            r.contexts[PROFILE]["runtime_authority"]["operation_id"] = value
            from tests.test_runtime_authority import bind_approval
            bind_approval(r, f.runtime_authority_profile)
        d = f.decide(p, now=NOW)
        save(f"op-operation-id-{tag}-held", f, {"reasons": d.reasons})



for fn in (op_normal, op_renewal_accepted, op_worker_self_renewal, op_renewal_refusals, op_refusal_check_id, op_duplicate_submission,
           op_lost_ack, op_delayed, op_wrong_operation_grant, op_missing_invalid):
    fn()
    print("captured", fn.__name__)
