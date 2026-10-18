"""Rewrite reason_vocabulary_version on captured fixtures to the label the current Control Plane producer writes (decision 31).

Control Plane N4 (main 3755c71a) split the reason registry into runtime-authority-reasons/0.1 (121 codes) and /0.2 (157 codes, a
superset). `runtime_authority.vocabulary_for(reasons)` labels a row 0.2 only when a reason is one of the 36 codes only 0.2
registers, else 0.1. The profile fixtures were captured at 128eaa5e, before the split, and carry 0.1 on rows with such codes.
This script applies the producer's rule to each decision, refusal and check event in the fixture files and records the rewrite in
the fixture's provenance. Idempotent. Usage: python relabel_vocabulary.py <fixtures dir>...
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("cpj_validate", HERE.parent / "validate.py")
cpj = importlib.util.module_from_spec(spec)
sys.modules["cpj_validate"] = cpj
spec.loader.exec_module(cpj)

NOTE = "reason_vocabulary_version rewritten from runtime-authority-reasons/0.1 to /0.2 on rows holding a 0.2-only code (decision 31); reasons unchanged"


def main(dirs):
    changed = 0
    for d in dirs:
        for path in sorted(Path(d).glob("*.json")):
            fx = json.loads(path.read_text(encoding="utf-8"))
            doc = fx.get("document")
            if not isinstance(doc, dict):
                continue
            hit = False
            for section in ("decisions", "refusals", "check_events"):
                for row in doc.get(section, []):
                    if isinstance(row, dict) and row.get("reason_vocabulary_version") == cpj.VOCABULARY_0_1 \
                            and set(row.get("reasons", [])) & cpj.CODES_ADDED_IN_0_2:
                        row["reason_vocabulary_version"] = cpj.VOCABULARY_0_2
                        hit = True
            if hit:
                if "provenance" in fx:
                    fx["provenance"]["vocabulary_label"] = NOTE
                path.write_text(json.dumps(fx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                changed += 1
    print(f"relabelled {changed} fixture files")


if __name__ == "__main__":
    main(sys.argv[1:])
