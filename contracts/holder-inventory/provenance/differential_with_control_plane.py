"""Run the fixtures through the Control Plane's own ``HolderInventory`` model and list where it and this contract differ (not a test,
not vendored).

    <venv>/bin/python differential_with_control_plane.py <control-plane-checkout>

The expected differences (README, Divergences) are named below; anything else is a mismatch and fails the run.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTRACT_DIR = HERE.parent
sys.path.insert(0, str(Path(sys.argv[1]).resolve() / "src"))
from agent_control_plane.holder_inventory import HolderInventory  # noqa: E402

# The model refuses these valid fixtures (it forbids extra members everywhere; the contract allows `extensions`)...
MODEL_REFUSES_VALID = {"extension-namespace-members-preserved"}
# ...and accepts these invalid ones (the contract is stricter: the producer always writes `credential_ref` and `holders`, so both are
# required here although the model defaults them, and `recorded_at` must be a time with an offset where the model takes any string).
MODEL_ACCEPTS_INVALID = {"credential-ref-member-missing", "holders-member-missing", "recorded-at-naive", "recorded-at-not-a-time"}


def accepted(doc) -> bool:
    try:
        HolderInventory.model_validate(doc)
        return True
    except Exception:
        return False


def main() -> int:
    bad = 0
    for kind in ("valid", "invalid"):
        for path in sorted((CONTRACT_DIR / "fixtures" / kind).glob("*.json")):
            fx = json.loads(path.read_text(encoding="utf-8"))
            ok = accepted(fx["document"])
            expected = (kind == "valid") != (fx["fixture_id"] in (MODEL_REFUSES_VALID if kind == "valid" else MODEL_ACCEPTS_INVALID))
            if ok != expected:
                bad += 1
                print("MISMATCH", kind, fx["fixture_id"], "model accepts:", ok)
    print(f"mismatches {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
