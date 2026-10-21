"""Derive the two fixtures for the five reason codes Control Plane 5c474ba8 added to the 0.2 registry (CP #79).

    python build_reason_label_fixtures.py <contracts/control-plane-journal dir>

Base: fixtures/valid/reasons-0-2-label-with-a-0-2-code.json (a held decision, its resolution check and completion event). The five
codes (action_blocked, missing_effect_limits, missing_amount_limit, effect_limit_malformed, authority_limit_malformed) are added to the
decision, the resolution check and the completion event, keeping the sorted order. The valid fixture keeps the 0.2 label on every row
that carries them; the invalid one relabels the decision 0.1 (one defect, one row). Written under names that do not start with
``profile-``, so mutate_invalid_fixtures.py (which rewrites only ``profile-*.json``) neither deletes nor rewrites them.
Stops if a document does not give exactly the expected verdict.
"""
import copy, importlib.util, json, sys
from pathlib import Path

CDIR = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("cpj", CDIR / "validate.py")
cpj = importlib.util.module_from_spec(spec)
sys.modules["cpj"] = cpj
spec.loader.exec_module(cpj)
BASE = "reasons-0-2-label-with-a-0-2-code"
NEW = ["action_blocked", "authority_limit_malformed", "effect_limit_malformed", "missing_amount_limit", "missing_effect_limits"]
base = json.loads((CDIR / "fixtures" / "valid" / f"{BASE}.json").read_text(encoding="utf-8"))["document"]


def with_codes():
    d = copy.deepcopy(base)
    rows = [d["decisions"][0], d["resolution_checks"][0], d["check_events"][-1]]
    for r in rows:
        r["reasons"] = sorted(set(r["reasons"]) | set(NEW))
    return d


def write(kind, fid, outcome, why, doc, refusal=None):
    got = list(dict.fromkeys(v.code for v in cpj.validate(doc)))
    if got != ([refusal] if refusal else []):
        sys.exit(f"{fid}: expected {refusal}, got {got}")
    fx = {"fixture_id": fid, "synthetic": True, "expected_outcome": outcome}
    if refusal:
        fx["expected_refusal"] = refusal
    fx["reason"] = why
    fx["document"] = doc
    (CDIR / "fixtures" / kind / f"{fid}.json").write_text(json.dumps(fx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


ok = with_codes()
write("valid", "reasons-0-2-label-with-the-manifest-gate-codes", "accept",
      "Held decision whose reasons also carry the five codes Control Plane 5c474ba8 added to runtime-authority-reasons/0.2 (action_blocked, "
      "missing_effect_limits, missing_amount_limit, effect_limit_malformed, authority_limit_malformed); the decision and the completion "
      "event are labelled 0.2, as the Control Plane labels a row by its own reasons. Synthetic, derived from reasons-0-2-label-with-a-0-2-code.",
      ok)
bad = copy.deepcopy(ok)
bad["decisions"][0]["reason_vocabulary_version"] = cpj.VOCABULARY_0_1
write("invalid", "reasons-0-2-manifest-gate-codes-under-a-0-1-label", "reject",
      "The decision of reasons-0-2-label-with-the-manifest-gate-codes relabelled runtime-authority-reasons/0.1 although its reasons carry the five codes "
      "Control Plane 5c474ba8 added to 0.2 (CP #79), which 0.1 does not register. Only the decision label is wrong.",
      bad, "reason_label_mismatch")
print("2 fixtures written")
