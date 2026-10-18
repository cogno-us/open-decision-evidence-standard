"""Capture the valid rule-revision fixtures from real Control Plane runs and producer functions (step 1 of 2; step 2 is build_fixtures.py).

Not a test and not vendored. Run from a checkout of cogno-us/cognous-control-plane (main 83b49b5 or later) with its dev
dependencies installed:

    PYTHONPATH=src:. python capture_fixtures.py <raw-dir>

It runs the Control Plane's own flows (the helpers of tests/test_rule_revision.py: synthetic proposals, fixed clock, throwaway
stores) and calls refusal_trends, measured_arity, arity_flags and recomputability_flags on the captured rows. It writes each run record
and each function output unchanged. Nothing is hand-written.
"""
import json
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

import pytest

import agent_control_plane.bounded as bounded
from agent_control_plane.bounded import commitment
from agent_control_plane.reason_vocabulary import (VocabularyChange, arity_flags, measured_arity, recomputability_flags,
                                                   refusal_trends)
from agent_control_plane.rule_revision import RuleRevision, RuleRevisionProfile, RuleRevisionRefused, append_rule_revision
from tests.test_bounded_authorization import ISSUER, NOW, POLICY_REF, PROFILE
from tests.test_runtime_authority import held, setup_flow
import tests.test_rule_revision as rr

bounded._now = lambda: NOW
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
REGISTRY = json.loads((Path("schemas") / "runtime_authority_reasons_0_1.json").read_text())


def tmp():
    return Path(tempfile.mkdtemp(prefix="cap-"))


def run_doc(f):
    return json.loads(f.records.path.read_text(encoding="utf-8"))


def save(name, f, extra=None):
    (OUT / f"{name}.json").write_text(json.dumps({"run": run_doc(f), "extra": extra or {}}, indent=1, ensure_ascii=False), encoding="utf-8")



# ----------------------------------------------------------------------------------------------- rule revision
REVISER, SIGNER = rr.REVISER, rr.SIGNER
D1, D2 = rr.D1, rr.D2


def t(seconds):
    return (NOW + timedelta(seconds=seconds)).isoformat()


def rev(rid, to, frm=None, at=-100, **kw):
    row = rr.rev(rid, to, frm, **kw)
    return row.model_copy(update={"recorded_at": t(at)})


def rule_flow(host=False):
    p, r, f, c = setup_flow(tmp())
    f.rule_revision_profile = RuleRevisionProfile(
        signers=[SIGNER], host_digests={"runtime-authority-reasons/0.1": commitment(REGISTRY)} if host else {},
        host_rule_kinds={"runtime-authority-reasons/0.1": "reason_registry"} if host else {})
    r.policies[POLICY_REF].digest = D1
    return p, r, f


def rule_adopted():
    p, r, f = rule_flow()
    append_rule_revision(f.records, f.rule_revision_profile, rev("rev-1", D1))
    d = f.decide(p, now=NOW)
    next(iter(r.statuses.values())).status = "revoked"
    try:
        f.execute(p, d, adapter_id=p.adapter_id, now=NOW)
    except PermissionError:
        pass
    save("rule-adopted-decision-and-refusal-rows", f)


def rule_unsigned():
    p, r, f = rule_flow()
    append_rule_revision(f.records, f.rule_revision_profile, rev("rev-1", D1, signer=None))
    held(f, p, "policy_status_unknown")
    save("rule-unsigned-row-resolves-unknown", f)


def rule_refused_rows():
    p, r, f = rule_flow()
    for rid, signer in (("rev-1", REVISER), ("rev-2", "synthetic-principal:stranger")):
        try:
            append_rule_revision(f.records, f.rule_revision_profile, rev(rid, D1, signer=signer))
        except RuleRevisionRefused:
            pass
    append_rule_revision(f.records, f.rule_revision_profile, rev("rev-3", D1))
    for row in (rev("rev-4", D2, "sha256:" + "0" * 64),              # from_digest is not the adopted digest
                rev("rev-3", D2, D1),                                   # revision id already used
                rev("rev-5", D2, D1, supersedes="no-such-revision")):   # supersedes a row that does not exist
        try:
            append_rule_revision(f.records, f.rule_revision_profile, row)
        except RuleRevisionRefused:
            pass
    save("rule-refused-revision-attempts-kept", f)


def rule_edit_in_place():
    p, r, f = rule_flow()
    append_rule_revision(f.records, f.rule_revision_profile, rev("rev-1", D1))
    assert f.decide(p, now=NOW).result == "authorized"
    r.policies[POLICY_REF].digest = D2
    d2 = f.decide(p, now=NOW + timedelta(seconds=5))
    assert d2.result == "hold"
    append_rule_revision(f.records, f.rule_revision_profile, rev("rev-2", D2, D1, at=10))
    assert f.decide(p, now=NOW + timedelta(seconds=20)).result == "authorized"
    save("rule-edit-in-place-held-then-readopted", f)


def rule_supersession():
    p, r, f = rule_flow()
    append_rule_revision(f.records, f.rule_revision_profile, rev("rev-1", D1, signer=None))
    append_rule_revision(f.records, f.rule_revision_profile, rev("rev-1b", D1, supersedes="rev-1", at=-50))
    assert f.decide(p, now=NOW).result == "authorized"
    save("rule-unsigned-then-resigned-by-supersession", f)


def rule_host_unadopted():
    p, r, f = rule_flow(host=True)
    append_rule_revision(f.records, f.rule_revision_profile, rev("rev-1", D1))
    d = f.decide(p, now=NOW)
    assert d.result == "authorized" and d.rule_identity["unknown"] == ["runtime-authority-reasons/0.1"], d.rule_identity
    save("rule-host-rule-unadopted-does-not-gate", f)


def rule_reports():
    """Held decisions before and after a reason_registry adoption row; trend, arity and recomputability outputs from the real functions."""
    p, r, f = rule_flow(host=True)
    v = "runtime-authority-reasons/0.1"
    held_a = f.decide(p, now=NOW)                                         # unadopted policy, nothing else wrong
    assert "policy_status_unknown" in held_a.reasons
    next(iter(r.statuses.values())).status = "revoked"
    held_b = f.decide(p, now=NOW + timedelta(seconds=2))                  # unadopted policy and revoked grant
    next(iter(r.statuses.values())).status = "active"
    append_rule_revision(f.records, f.rule_revision_profile,
                         rev("rev-reg-1", commitment(REGISTRY), None, at=3, kind="reason_registry", ref=v,
                             declared_arity={"policy_status_unknown": 1}))
    held_c = f.decide(p, now=NOW + timedelta(seconds=5))
    split = VocabularyChange(change_id="change-1", previous_version=v, version="runtime-authority-reasons/0.2-synthetic",
                             registry_digest=D1, kind="split", previous_codes=["policy_status_unknown"],
                             codes=["policy_status_unknown_a", "policy_status_unknown_b"], acknowledged_by=SIGNER,
                             acknowledged_at=t(4))
    f.records.append_vocabulary_change(split)
    doc = run_doc(f)
    decisions = [x for x in doc["decisions"] if x["result"] == "hold"]
    assert len(decisions) == 3
    row_prev, rows_cur = decisions[:1], decisions[1:]
    trend_registry = refusal_trends(row_prev, rows_cur, previous_exposure=3, current_exposure=3, rule_revisions=doc["rule_revisions"])
    trend_split = refusal_trends(row_prev, rows_cur, previous_exposure=3, current_exposure=3, vocabulary_changes=doc["vocabulary_changes"])
    measured = measured_arity(decisions, as_of=t(10), period_seconds=3600)
    declared = {"policy_status_unknown": 1}
    flags = arity_flags(declared, measured)
    recompute_rows = decisions
    recompute = recomputability_flags(recompute_rows, REGISTRY["codes"])
    trend_plain = refusal_trends(row_prev, rows_cur, previous_exposure=3, current_exposure=3)
    arity_ok = arity_flags({"policy_status_unknown": 2, "grant_revoked": 1}, measured)
    save("rule-reports", f, {
        "trend_plain": trend_plain, "arity_ok_flags": arity_ok, "arity_ok_declared": {"policy_status_unknown": 2, "grant_revoked": 1},
        "trend_registry": trend_registry, "trend_split": trend_split, "measured": measured, "declared": declared,
        "arity_flags": flags, "recomputability_flags": recompute,
        "registry_kinds": {c: v_["reason_kind"] for c, v_ in REGISTRY["codes"].items()}})



for fn in (rule_adopted, rule_unsigned, rule_refused_rows, rule_edit_in_place, rule_supersession, rule_host_unadopted, rule_reports):
    fn()
    print("captured", fn.__name__)
