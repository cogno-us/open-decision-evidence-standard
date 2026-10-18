"""Run the control-plane-journal contract validator over the raw profile-on run records (the capture_fixtures.py output) and report
where it diverges from the freshness/0.1 producer. Reports only; edits nothing.

    python journal_divergence.py <raw-dir> <contracts/control-plane-journal dir>

For each captured run it prints (1) the violations of the raw record (with the contract markers added, as a raw export lacks them),
grouped by code and member path; and (2) the violations that remain when the profile's own optional members, the `overdue` and `expired`
events and the `nonce_mismatch` read state are stripped, which are the behavioural divergences rather than undeclared members.
"""
import collections, copy, glob, importlib.util, json, re, sys
from pathlib import Path

RAW, JDIR = Path(sys.argv[1]), Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("cpj", JDIR / "validate.py")
cpj = importlib.util.module_from_spec(spec)
sys.modules["cpj"] = cpj
spec.loader.exec_module(cpj)
PROFILE_ROW_MEMBERS = {"decisions": ("evaluated_at", "recorded_at"), "attempts": ("evaluated_at", "recorded_at"),
                       "refusals": ("evaluated_at", "deadline", "check_id"), "resolution_checks": ("recorded_at",),
                       "check_events": ("evaluated_at", "deadline", "age_bound_seconds", "extension_id", "nonce")}
PROFILE_LISTS = ("age_extensions", "age_extension_refusals", "recovery_runs", "rule_revisions", "rule_revision_refusals",
                 "operations", "operation_renewals", "attempt_joins")


def strip(run):
    run = copy.deepcopy(run)
    for name in PROFILE_LISTS:
        run.pop(name, None)
    for name, members in PROFILE_ROW_MEMBERS.items():
        for row in run.get(name, []):
            for m in members:
                row.pop(m, None)
    for name, key in (("decisions", "resolution_inputs"), ("refusals", "resolution_inputs"), ("resolution_checks", "inputs")):
        for row in run.get(name, []):
            for item in row[key]:
                item.pop("age_basis", None)
    for e in run.get("check_events", []):
        if e.get("input"):
            e["input"].pop("age_basis", None)
            if e["input"].get("read_state") == "nonce_mismatch":
                e["input"].pop("read_state")
    # the two phases the journal contract does not declare (overdue, expired) are dropped last, so the rules behind the enum are reached
    run["check_events"] = [e for e in run.get("check_events", []) if e["phase"] not in {"overdue", "expired"}]
    if not run["check_events"]:
        run.pop("check_events")
    for name in ("decisions", "refusals", "resolution_checks"):
        for row in run.get(name, []):
            for item in row.get("resolution_inputs", row.get("inputs", [])):
                if item.get("read_state") == "nonce_mismatch":
                    item.pop("read_state")
    return run


def group(violations):
    c = collections.Counter((v.code, re.sub(r"\[\d+\]", "[]", v.path)) for v in violations)
    return sorted(c.items())


for path in sorted(glob.glob(str(RAW / "*.json"))):
    run = json.load(open(path))["run"]
    name = Path(path).stem
    raw = cpj.validate({"contract": "control-plane-journal", "contract_version": "0.1.0-draft", **run})
    left = cpj.validate({"contract": "control-plane-journal", "contract_version": "0.1.0-draft", **strip(run)})
    codes = collections.Counter(v.code for v in raw)
    print(f"{name}: raw {len(raw)} violations {dict(codes)}; after stripping the profile members: {len(left)}")
    for (code, p), n in group(left):
        print(f"    remains: {code} {p} x{n}")
