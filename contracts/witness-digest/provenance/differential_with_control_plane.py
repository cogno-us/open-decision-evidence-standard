"""Run the fixtures through the Control Plane's own ``verify_against_witness`` and compare (not a test, not vendored).

    <venv>/bin/python differential_with_control_plane.py <control-plane-checkout>

For every valid fixture: the Control Plane accepts it (or, without a run record, finds no chain defect) and its ``witnessed_through`` and
``unwitnessed_rows`` equal this contract's ``coverage``. For every invalid fixture whose refusal is one of the Control Plane's verdict
codes (``witness_chain_invalid``, ``witness_run_mismatch``, ``witness_ledger_shrunk``, ``witness_ledger_head_mismatch``,
``witness_holds_no_digest``): the Control Plane rejects it with the same code. Structure-level refusals (a closed member set, a
version, a type) have no Control Plane counterpart (it reads a record with ``get`` and does not refuse extra members), so they are
not compared.
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTRACT_DIR = HERE.parent
sys.path.insert(0, str(Path(sys.argv[1]).resolve() / "src"))
import agent_control_plane.witness as W  # noqa: E402

_spec = importlib.util.spec_from_file_location("wd_validate", CONTRACT_DIR / "validate.py")
wd = importlib.util.module_from_spec(_spec)
sys.modules["wd_validate"] = wd
_spec.loader.exec_module(wd)

CP_CODES = {"witness_chain_invalid", "witness_run_mismatch", "witness_ledger_shrunk", "witness_ledger_head_mismatch", "witness_holds_no_digest"}


class Held:
    def __init__(self, records):
        self.records = records

    def history(self):
        return self.records

    def latest(self):
        return self.records[-1] if self.records else None


def main() -> int:
    compared = mismatches = 0
    for kind in ("valid", "invalid"):
        for path in sorted((CONTRACT_DIR / "fixtures" / kind).glob("*.json")):
            fx = json.loads(path.read_text(encoding="utf-8"))
            records, run_record = fx["document"], fx.get("record")
            if kind == "invalid" and fx["expected_refusal"] not in CP_CODES:
                continue
            compared += 1
            if run_record is None:
                got = ({"witness_chain_invalid"} if W.check_witness_chain(records) else set()) if records else {"witness_holds_no_digest"}
                want = set() if kind == "valid" else {fx["expected_refusal"]}
                cov_ok = True
            else:
                verdict = W.verify_against_witness(run_record, Held(records))
                got = set(verdict.reasons)
                want = set() if kind == "valid" else {fx["expected_refusal"]}
                cov_ok = True
                if kind == "valid" and "expected_coverage" in fx:
                    cov_ok = {"witnessed_through": verdict.witnessed_through, "unwitnessed_rows": verdict.unwitnessed_rows} == wd.coverage(records, run_record)
            if got != want or not cov_ok:
                mismatches += 1
                print("MISMATCH", path.name, "control plane:", sorted(got), "contract:", sorted(want), "coverage agrees:", cov_ok)
    print(f"compared {compared} fixtures, mismatches {mismatches}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
