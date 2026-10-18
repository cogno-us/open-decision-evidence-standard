"""Differential: the Control Plane's own run-record model against this contract's verdict on every profile fixture.

Not a test and not vendored. Run from a checkout of cogno-us/cognous-control-plane at 128eaa5e with its dev dependencies installed:

    PYTHONPATH=src python differential_control_plane.py <contracts/control-plane-journal dir>

For each fixture it removes the three contract markers, loads the run record through `BoundedRunRecord.model_validate` (what
`BoundedRecordStore.load` does on every read: closed models, enumerations, types) and compares with the contract's verdict:

* valid fixtures: the model must accept (an unexpected difference otherwise);
* invalid fixtures: the contract refuses all of them by construction, so a model refusal agrees. A model acceptance is classed
  `contract stricter` (not an unexpected difference): the producer model has no cross-record rules and is lax on some member values
  (it coerces "200" to an integer, takes an empty operation id, tolerates an extra member on a row), and the contract is closed and
  typed where the producer is not. Direction matters: nothing the model refuses is accepted by the contract.

Prints the table and exits 1 on any unexpected difference. The Control Plane's `validate-run` is the validator of a different document
(the projected RunRecord that `acp run` writes), so it is not applicable to a bounded run record.
"""
import json
import sys
from pathlib import Path

from agent_control_plane.bounded import BoundedRunRecord

CDIR = Path(sys.argv[1])
MARKERS = ("contract", "contract_version", "producer")
unexpected, rows = [], []
for kind in ("valid", "invalid"):
    for path in sorted((CDIR / "fixtures" / kind).glob("profile-*.json")):
        fx = json.loads(path.read_text(encoding="utf-8"))
        run = {k: v for k, v in fx["document"].items() if k not in MARKERS}
        try:
            BoundedRunRecord.model_validate(run)
            model = "accepts"
        except Exception as exc:  # noqa: BLE001 - any refusal counts
            model = "refuses"
        if kind == "valid":
            verdict = "agree" if model == "accepts" else "UNEXPECTED"
        else:
            verdict = "agree" if model == "refuses" else "contract stricter"
        rows.append((kind, fx["fixture_id"], fx.get("expected_refusal", "-"), "model " + model, verdict))
        if verdict == "UNEXPECTED":
            unexpected.append(rows[-1])
for r in rows:
    print(" | ".join(r))
print(f"{len(rows)} fixtures; unexpected differences: {len(unexpected)}; contract stricter than the model: {sum(r[4] == 'contract stricter' for r in rows)}")
sys.exit(1 if unexpected else 0)
