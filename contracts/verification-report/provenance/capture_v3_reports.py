"""Capture REAL verifier output over witnessed runs and move its tier V3 section into the draft-revision shape (step 1 of 2 for
the ``v3-*`` fixtures; step 2 is ``build_v3_fixtures.py``).

Not a test and not vendored. What is real and what is not, stated plainly:

* Real: the run records, witness files and holder inventories are the unchanged output of the Control Plane (captured by
  ``contracts/witness-digest/provenance/capture_fixtures.py`` at control plane ``128eaa5``); the reports are the unchanged JSON
  output of ``cognous-verify`` at verifier main ``05afab8`` (tier V3, PR #10), run with ``--witness`` and, where the scenario has
  one, ``--holder-inventory``. The ``damaged`` scenario is the same verifier over a record from which one covered row was removed
  (the damage is applied to a copy; the verifier output is again unchanged).
* Moved, not emitted: that verifier build predates this draft revision, so it reports tier V3 in ``extensions["x-tier-v3"]``. This
  script moves that section into the places the revised contract defines and changes nothing else: V3 checks join ``checks`` (V3
  last, in the verifier's order), the witness and inventory inputs join ``subject.inputs`` (re-sorted), ``V3`` joins
  ``scope.tiers_run``, ``subject.inputs_digest`` and ``summary`` are recomputed, ``x-tier-v3`` is removed, and the non-claim
  ``witness_is_not_publication`` is appended with a statement taken from the verifier's own ``limits`` text. ``report_id`` is the
  verifier's, not recomputed. A verifier that has made the change (README, Divergences) emits this shape directly and this step
  becomes a plain copy.

    python capture_v3_reports.py <cognous-verify executable> <raw-dir from the witness-digest capture> <reports-dir>
"""
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("vr_validate", HERE.parent / "validate.py")
vr = importlib.util.module_from_spec(_spec)
sys.modules["vr_validate"] = vr
_spec.loader.exec_module(vr)

VERIFIER_REVISION = "05afab84"
CONTROL_PLANE_REVISION = "128eaa5e"
NOW = "2026-10-18T12:00:00+00:00"

SCENARIOS = {
    # name: (raw scenario, record file, witness file, inventory file or None, damage)
    "witnessed-complete": ("staged-journal-applied", "record.json", "witness.jsonl", None, None),
    "witnessed-first-only": ("staged-journal-applied", "record.json", "witness-first-only.jsonl", None, None),
    "witnessed-with-inventory": ("holder-inventory-enumerated", "record.json", "witness.jsonl", "holder-inventory.json", None),
    "witnessed-held-without-inventory": ("holder-inventory-missing-held", "record.json", "witness.jsonl", None, None),
    "witnessed-damaged-record": ("staged-journal-applied", "record.json", "witness.jsonl", None, "drop-last-attempt"),
}


def run(verify: Path, raw: Path, scenario: tuple, work: Path) -> dict:
    sub, record, witness, inventory, damage = scenario
    record_path = raw / sub / record
    if damage == "drop-last-attempt":
        doc = json.loads(record_path.read_text(encoding="utf-8"))
        doc["attempts"].pop()
        record_path = work / "record.json"
        record_path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    out = work / "report.json"
    cmd = [str(verify), str(record_path), "--witness", str(raw / sub / witness), "--controller-revision", CONTROL_PLANE_REVISION,
           "--source-revision", VERIFIER_REVISION, "--generated-at", NOW, "--out", str(out)]
    if inventory:
        cmd += ["--holder-inventory", str(raw / sub / inventory)]
    done = subprocess.run(cmd, capture_output=True, text=True)
    assert done.returncode in (0, 1, 3), (cmd, done.returncode, done.stderr)   # 2 usage error, 4 crash: no report
    return json.loads(out.read_text(encoding="utf-8"))


def move_v3(report: dict) -> dict:
    doc = copy.deepcopy(report)
    v3 = doc["extensions"].pop("x-tier-v3")
    assert v3["requested"] is True
    doc["subject"]["inputs"] = sorted(doc["subject"]["inputs"] + v3["inputs"], key=lambda i: (i["role"], i["name"], i["digest"]))
    doc["subject"]["inputs_digest"] = vr.commitment(doc["subject"]["inputs"])
    doc["checks"] = doc["checks"] + v3["checks"]
    doc["scope"]["tiers_run"] = sorted(set(doc["scope"]["tiers_run"]) | {"V3"})
    counts = {"confirmed": 0, "could_not_check": 0, "refuted": 0}
    for c in doc["checks"]:
        counts[c["verdict"]] += 1
    doc["summary"] = {"checks": len(doc["checks"]), **counts}
    statement = "; ".join(v3["limits"][:3])
    doc["does_not_prove"].append({"id": "witness_is_not_publication", "statement": statement[0].upper() + statement[1:] + "."})
    doc["extensions"]["x-not-applicable"] = list(doc["extensions"].get("x-not-applicable", [])) + v3["not_applicable"]
    return doc


def main(verify: Path, raw: Path, reports: Path) -> int:
    reports.mkdir(parents=True, exist_ok=True)
    for name, scenario in SCENARIOS.items():
        with tempfile.TemporaryDirectory(prefix="v3-report-") as tmp:
            original = run(verify, raw, scenario, Path(tmp))
        moved = move_v3(original)
        problems = vr.validate(moved)
        assert not problems, (name, problems)
        (reports / f"{name}.json").write_text(json.dumps(moved, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        v3 = [c for c in moved["checks"] if c["tier"] == "V3"]
        print(name, "V3 checks", len(v3), {c["check_id"]: c["verdict"] for c in v3})
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()))
