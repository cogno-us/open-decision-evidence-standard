"""Capture run records with all programme-2 opt-in profiles on at once (step 1b of 3; step 1a is the three existing capture scripts).

Not a test and not vendored. Run from a checkout of cogno-us/cognous-control-plane at 3755c71a (main after N4 and J3; first captured at 128eaa5e, #49) with its dev
dependencies installed:

    PYTHONPATH=src:. python capture_profile_stack.py <raw-dir>

Profiles switched on together (host configuration, the approval commitment covers it): freshness/0.1 (N3), operation-identity/0.1 (N1),
rule-revision/0.1 (N2, with an adopted policy row) and, for the holder-inventory scenarios, holder-inventory/0.1 (N5: the
`requires_revocation_assurance` class flag plus an inventory). It drives the Control Plane's own flows (helpers of tests/test_freshness.py
and tests/test_holder_inventory.py: synthetic proposals, settable service clock, throwaway stores) and writes each run record unchanged.
Nothing is hand-written. `acp run` takes no profile options, so the profiles are enabled through the library, as the Control Plane's own
tests do.
"""
import json
import sys
import tempfile
from pathlib import Path

import agent_control_plane.bounded as bounded
from agent_control_plane.holder_inventory import AuthorityHolder, HolderInventory
from agent_control_plane.operation_identity import OperationIdentityProfile
from tests.test_bounded_authorization import ISSUER, NOW, PROFILE
from tests.test_freshness import Clock, authority, enable, execute, stall_before_dispatch
from tests.test_runtime_authority import bind_approval, setup_flow

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
CLOCK = Clock()
bounded._now = CLOCK
OPERATION = "op-order-100/refund-1"


def save(name, f):
    (OUT / f"{name}.json").write_text(json.dumps({"run": json.loads(f.records.path.read_text(encoding="utf-8")), "facts": {}},
                                                 indent=1, ensure_ascii=False), encoding="utf-8")


def inventory():
    return HolderInventory(inventory_id="inv-1", recorded_by="urn:cognous:principal:inventory-owner", recorded_at=NOW.isoformat(),
                           holders=[AuthorityHolder(holder_id="h-routed", kind="routed", enforcement_point="control plane effect check")])


def stack(*, flag=True, with_inventory=True):
    CLOCK.now = NOW
    p, r, f, c = setup_flow(Path(tempfile.mkdtemp(prefix="cap-")))
    c = enable(r, f, c)                               # freshness/0.1
    authority(f, r)                                   # rule-revision/0.1 with an adopted policy row
    update = {"operation_identity": OperationIdentityProfile(resolver_id="synthetic-resolver", resolver_version="1"),   # N1
              "actions": {k: v.model_copy(update={"requires_revocation_assurance": flag}) for k, v in c.actions.items()}}
    if with_inventory:
        update["holder_inventory"] = inventory()      # N5
    cfg = c.model_copy(update=update)
    r.contexts[PROFILE]["runtime_authority"]["operation_id"] = OPERATION
    bind_approval(r, cfg)
    f.runtime_authority_profile = cfg.snapshot()
    return p, r, f


def all_profiles_applied():
    p, r, f = stack()
    d = f.decide(p, now=NOW)
    assert d.result == "authorized", d.reasons
    CLOCK.tick(2)
    execute(f, p, d)
    CLOCK.tick(4)
    f.record_renewal(OPERATION, to_revision="2", written_by=ISSUER, now=NOW)
    save("all-profiles-applied", f)


def all_profiles_expired():
    p, r, f = stack()
    d = f.decide(p, now=NOW)
    assert d.result == "authorized", d.reasons
    stall_before_dispatch(f, CLOCK, 61, pin_observation=True)
    try:
        execute(f, p, d)
    except PermissionError:
        pass
    assert f.destination.snapshot()["effects"] == {}
    save("all-profiles-expired-before-dispatch", f)


def holder_inventory_missing():
    p, r, f = stack(with_inventory=False)
    d = f.decide(p, now=NOW)
    assert d.result == "hold" and "holder_inventory_missing" in d.reasons
    save("all-profiles-holder-inventory-missing", f)


for scenario in (all_profiles_applied, all_profiles_expired, holder_inventory_missing):
    scenario()
    print("captured", scenario.__name__)
