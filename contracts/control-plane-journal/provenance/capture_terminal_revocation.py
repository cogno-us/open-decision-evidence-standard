"""Capture run records with the opt-in terminal-revocation/0.1 profile on (an addition to the capture scripts of this directory).

Not a test and not vendored. Run from a checkout of cogno-us/cognous-control-plane at 6b8fb627 (main after #58) with its dev dependencies
installed:

    PYTHONPATH=src:. python capture_terminal_revocation.py <raw-dir>

It drives the Control Plane's own flow with the helpers of tests/test_terminal_revocation.py (synthetic proposals, throwaway stores, a
fixed clock) and writes each run record unchanged. Nothing is hand-written. The profile adds one reason code
(`grant_revocation_recorded`, registry label runtime-authority-reasons/0.2 only) and no record member: the refusal and hold rows use the
members the journal contract already declares, including `reopen_conditions` with a `successor_grant_revision` entry.
"""
import json
import sys
import tempfile
from pathlib import Path

import agent_control_plane.bounded as bounded
from tests.test_bounded_authorization import NOW
from tests.test_terminal_revocation import _refused_once_then_status_back, flow

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
bounded._now = lambda: NOW


def save(name, f):
    (OUT / f"{name}.json").write_text(json.dumps({"run": json.loads(f.records.path.read_text(encoding="utf-8")), "facts": {}},
                                                 indent=1, ensure_ascii=False), encoding="utf-8")


def tmp():
    return Path(tempfile.mkdtemp(prefix="cap-"))


def refused_after_recorded_revocation():
    p, r, f = flow(tmp(), enabled=True)
    d = _refused_once_then_status_back(f, p, r, "revoked")   # first refusal: grant_revoked; status then reads active again
    try:
        f.execute(p, d, adapter_id=p.adapter_id, now=NOW)
    except PermissionError:
        pass
    assert f.records.load().refusals[-1].reasons == ["grant_revocation_recorded"]
    save("terminal-revocation-refused-after-recorded-revocation", f)


def decision_holds_after_recorded_revocation():
    p, r, f = flow(tmp(), enabled=True)
    _refused_once_then_status_back(f, p, r, "revoked")
    again = f.decide(p, now=NOW)
    assert again.result == "hold" and again.reasons == ["grant_revocation_recorded"]
    save("terminal-revocation-decision-holds-after-recorded-revocation", f)


def suspension_stays_reversible():
    p, r, f = flow(tmp(), enabled=True)
    d = _refused_once_then_status_back(f, p, r, "suspended")
    attempt, observation = f.execute(p, d, adapter_id=p.adapter_id, now=NOW)
    assert attempt.status == "acknowledged" and observation.state == "applied"
    save("terminal-revocation-suspension-stays-reversible", f)


refused_after_recorded_revocation()
decision_holds_after_recorded_revocation()
suspension_stays_reversible()
