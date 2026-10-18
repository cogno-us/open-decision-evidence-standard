"""Capture the raw witness files, run records and holder inventories the valid fixtures are built from (step 1 of 2; step 2 is
``build_fixtures.py`` in this directory).

Not a test and not vendored. Nothing is hand-written: every witness record is the unchanged output of the Control Plane's
``acp witness publish`` (or of ``publish_head``, the function behind it), and every run record is the unchanged output of the
Control Plane's own bounded workflow.

Needs a checkout of cogno-us/cognous-control-plane (main ``128eaa5``, which carries N5) installed with ``pip install -e .``; run with
that environment's Python so that ``acp`` is next to it:

    <venv>/bin/python capture_fixtures.py <control-plane-checkout> <raw-dir>

Scenarios (one directory each under ``<raw-dir>``):

* ``acp-run-authorized``, ``acp-run-held``: ``acp run`` on the repository's own ``examples/acp_run`` inputs (fixed ``--now``,
  throwaway store), then the public commands ``acp witness publish``, ``digest`` and ``verify`` over the stored record.
* ``staged-journal-applied``: a journal-mode run (test helpers, fixed clock); the digest is published after the decision and again
  after execution. ``witness.jsonl`` holds both records, ``witness-first-only.jsonl`` holds the first (so the later rows are
  unwitnessed).
* ``holder-inventory-enumerated``, ``holder-inventory-empty-held`` and ``holder-inventory-missing-held``: a journal-mode run whose
  action class requires revocation assurance, with an inventory that enumerates two holders (authorized, applied), with an
  inventory that enumerates none and with no inventory (both held with ``holder_inventory_missing``). Where there is an inventory,
  ``holder-inventory.json`` is the inventory the profile carries, dumped unchanged; ``decision.json`` is the run's first decision
  (result and reasons).

No qualification controller and no ``tools/v1_validation.py`` mode is run; nothing is published anywhere.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main(checkout: Path, raw: Path) -> int:
    sys.path.insert(0, str(checkout))
    sys.path.insert(0, str(checkout / "src"))
    import agent_control_plane.bounded as bounded
    from agent_control_plane.witness import LocalFileWitness, publish_head
    from tests.test_bounded_authorization import NOW
    from tests.test_holder_inventory import ROUTED, SELF, configure, inventory
    from tests.test_runtime_authority import setup_flow

    bounded._now = lambda: NOW
    acp = Path(sys.executable).parent / "acp"
    revision = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    raw.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="capture-witness-digest-"))
    meta = {"control_plane_revision": revision, "scenarios": {}}

    def out(name: str) -> Path:
        d = raw / name
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        return d

    # acp run, then the public witness commands
    ex = checkout / "examples" / "acp_run"
    for name in ("authorized", "held"):
        d = out(f"acp-run-{name}")
        tmp = work / f"acp-{name}"
        tmp.mkdir()
        ran = subprocess.run([str(acp), "run", "--manifest", str(ex / "manifest.json"), "--proposal", str(ex / name / "proposal.json"),
                        "--authority-context", str(ex / name / "authority-context.json"),
                        "--resolver-state", str(ex / name / "resolver-state.json"), "--store-dir", str(tmp / "store"),
                        "--out-dir", str(tmp / "out"), "--now", "2026-10-05T19:00:00Z"], capture_output=True, text=True)
        assert (tmp / "store" / "bounded-run-record.json").exists(), ran.stderr or ran.stdout
        record = d / "record.json"
        shutil.copy(tmp / "store" / "bounded-run-record.json", record)
        wf = d / "witness.jsonl"
        pub = subprocess.run([str(acp), "witness", "publish", str(record), "--witness", str(wf)], capture_output=True, text=True, check=True)
        (d / "publish-output.json").write_text(pub.stdout, encoding="utf-8")
        dig = subprocess.run([str(acp), "witness", "digest", str(record)], capture_output=True, text=True, check=True)
        (d / "digest-output.json").write_text(dig.stdout, encoding="utf-8")
        ver = subprocess.run([str(acp), "witness", "verify", str(record), "--witness", str(wf)], capture_output=True, text=True, check=True)
        (d / "verify-output.json").write_text(ver.stdout, encoding="utf-8")
        meta["scenarios"][d.name] = {"producer": "acp run; acp witness publish|digest|verify"}

    # staged: publish after the decision, then again after execution
    p, r, f, cfg = setup_flow(work / "staged")
    w = LocalFileWitness(work / "staged-witness.jsonl")
    decision = f.decide(p, now=NOW)
    publish_head(f.records.path, w)
    first = work / "staged-first.jsonl"
    shutil.copyfile(w.path, first)
    f.execute(p, decision, adapter_id=p.adapter_id, now=NOW)
    mid_record = work / "staged-mid-record.json"
    publish_head(f.records.path, w)
    d = out("staged-journal-applied")
    shutil.copyfile(f.records.path, d / "record.json")
    shutil.copyfile(w.path, d / "witness.jsonl")
    shutil.copyfile(first, d / "witness-first-only.jsonl")
    for fname in ("witness.jsonl", "witness-first-only.jsonl"):
        ver = subprocess.run([str(acp), "witness", "verify", str(d / "record.json"), "--witness", str(d / fname)], capture_output=True, text=True, check=True)
        (d / f"verify-output-{fname.replace('.jsonl', '')}.json").write_text(ver.stdout, encoding="utf-8")
    meta["scenarios"][d.name] = {"producer": "bounded workflow (test helpers, fixed clock); publish_head twice"}

    def decision_excerpt(directory: Path) -> None:
        doc = json.loads((directory / "record.json").read_text(encoding="utf-8"))
        row = doc["decisions"][0]
        (directory / "decision.json").write_text(json.dumps({"class_requires_revocation_assurance": True, "result": row["result"],
                                                             "reasons": row["reasons"]}, indent=1) + "\n", encoding="utf-8")

    # holder inventory enumerated, an empty one, and none: the class requires revocation assurance in all three
    for scenario, flag_inventory, holders_note in (("holder-inventory-enumerated", inventory(ROUTED, SELF), "an inventory of two holders (authorized, applied)"),
                                                   ("holder-inventory-empty-held", inventory(), "an inventory that enumerates no holder (held)"),
                                                   ("holder-inventory-missing-held", None, "no inventory (held with holder_inventory_missing)")):
        p, r, f, cfg = setup_flow(work / scenario)
        configure(r, f, cfg, flag=True, inv=flag_inventory)
        decision = f.decide(p, now=NOW)
        if decision.result == "authorized":
            f.execute(p, decision, adapter_id=p.adapter_id, now=NOW)
        w = LocalFileWitness(work / f"{scenario}-witness.jsonl")
        publish_head(f.records.path, w)
        d = out(scenario)
        shutil.copyfile(f.records.path, d / "record.json")
        shutil.copyfile(w.path, d / "witness.jsonl")
        if flag_inventory is not None:
            (d / "holder-inventory.json").write_text(json.dumps(flag_inventory.model_dump(mode="json"), indent=1) + "\n", encoding="utf-8")
        decision_excerpt(d)
        meta["scenarios"][d.name] = {"producer": f"bounded workflow, requires_revocation_assurance with {holders_note}"}

    (raw / "capture.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    shutil.rmtree(work)
    print(f"captured {len(meta['scenarios'])} scenarios at control plane {revision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()))
