"""Capture the raw destination ledgers the valid destination-ledger fixtures are built from (step 1 of 2; step 2 is build_fixtures.py).

Not a test and not vendored. Nothing is hand-written: every ledger is the unchanged output of a producer.

Control Plane side (checkout of cogno-us/cognous-control-plane, installed with ``pip install -e .``):

    python capture_fixtures.py control-plane <control-plane-checkout> <raw-dir>

  runs ``acp run`` on the repository's own ``examples/acp_run`` authorized and held inputs (fixed ``--now``, throwaway store)
  and copies ``destination.json``, then drives ``LocalRefundDestination`` directly for a partial effect and for an operation id
  (the opt-in ``operations`` member).

Orchestrator side (checkout of cogno-us/cognous-stack-orchestrator with the candidate component checkouts named as in
``tests/overlay/README.md``): run

    python -m pytest -q -p no:cacheprovider tests/overlay/test_overlay_verifier.py -k "runtime_route or adapter_route"

  with ``COGNOUS_OVERLAY_REPORT_DIR=<overlay-dir>`` set, then

    python capture_fixtures.py orchestrator <overlay-dir> <raw-dir>

  which copies the ledgers the overlay projected from the runtime SQLite effect rows (projection A without
  ``operation_digest``, projection B with it, and the atomic-route projection) and the accepted reconciliation observations of the
  matching run record.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def control_plane(checkout: Path, raw: Path) -> None:
    sys.path.insert(0, str(checkout / "src"))
    from agent_control_plane.bounded import LocalRefundDestination  # noqa: E402

    ex = checkout / "examples" / "acp_run"
    for name in ("authorized", "held"):
        tmp = Path(tempfile.mkdtemp(prefix="cap-"))
        subprocess.run(
            ["acp", "run", "--manifest", str(ex / "manifest.json"), "--proposal", str(ex / name / "proposal.json"),
             "--authority-context", str(ex / name / "authority-context.json"),
             "--resolver-state", str(ex / name / "resolver-state.json"),
             "--store-dir", str(tmp / "store"), "--out-dir", str(tmp / "out"), "--now", "2026-10-05T19:00:00Z"],
            check=False, capture_output=True)
        shutil.copy(tmp / "store" / "destination.json", raw / f"cp-acp-run-{name}.json")
    common = dict(grant_id="urn:cognous:grant:routine-1", max_effects=2, target="urn:cognous:synthetic-account:customer-001",
                  amount=50.0, unit="USD", payload={"customer_id": "customer-001", "refund_reason": "duplicate"})
    tmp = Path(tempfile.mkdtemp(prefix="cap-"))
    LocalRefundDestination(tmp / "partial.json").apply(effect_id="sha256:" + "a" * 64, partial=True, **common)
    shutil.copy(tmp / "partial.json", raw / "cp-partial.json")
    dest = LocalRefundDestination(tmp / "ops.json")
    dest.apply(effect_id="sha256:" + "b" * 64, operation_id="op-order-100/refund-1", **common)
    shutil.copy(tmp / "ops.json", raw / "cp-operations.json")


def orchestrator(overlay: Path, raw: Path) -> None:
    pairs = {
        "orch-a-applied": ("candidate-journal/off/applied", "ledger-A_without_operation_digest.json"),
        "orch-b-applied": ("candidate-journal/off/applied", "ledger-B_with_operation_digest.json"),
        "orch-a-held": ("candidate-journal/off/held", "ledger-A_without_operation_digest.json"),
        "orch-b-renewal-race": ("candidate-destinations/renewal_race_identity_off", "ledger-B_with_operation_digest.json"),
        "orch-atomic-applied": ("candidate-handoff/applied", "ledger-projection.json"),
    }
    for name, (bundle, ledger) in pairs.items():
        shutil.copy(overlay / bundle / ledger, raw / f"{name}.json")
    rec = json.loads((overlay / "candidate-journal/off/applied/run-record.json").read_text(encoding="utf-8"))
    keep = [r for r in rec["reconciliations"] if r["observation_accepted"] is True and r["observation"]["state"] == "applied"]
    (raw / "orch-b-applied.observations.json").write_text(json.dumps(keep, indent=1), encoding="utf-8")


if __name__ == "__main__":
    side, src, dst = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    dst.mkdir(parents=True, exist_ok=True)
    {"control-plane": control_plane, "orchestrator": orchestrator}[side](src, dst)
