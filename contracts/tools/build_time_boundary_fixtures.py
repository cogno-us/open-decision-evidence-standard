#!/usr/bin/env python3
"""Rebuild the time-boundary fixtures of docs/engineering/ODES-TIME-SEMANTICS.md (decision 35).

Each fixture is a single mutation of an existing golden fixture. The script runs the contract's own validator on the result and
refuses to write a fixture whose verdict is not the one declared here. Stdlib only. Run from anywhere: ``build_time_boundary_fixtures.py``.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

CONTRACTS = Path(__file__).resolve().parents[1]
_cache: dict[str, object] = {}


def validator(name: str):
    if name not in _cache:
        spec = importlib.util.spec_from_file_location("v_" + name.replace("-", "_"), CONTRACTS / name / "validate.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _cache[name] = module
    return _cache[name]


def load(contract: str, kind: str, fixture_id: str) -> dict:
    return json.loads((CONTRACTS / contract / "fixtures" / kind / f"{fixture_id}.json").read_text(encoding="utf-8"))


def verdict(contract: str, fx: dict) -> list[str]:
    v = validator(contract)
    if contract == "freshness-clocks":
        return [x.code for x in v.validate(fx["document"], fx.get("journal"), fx.get("host"))]
    return [x.code for x in v.validate(fx["document"])]


def write(contract: str, kind: str, base: dict, base_id: str, fixture_id: str, reason: str, mutate, refusal: str | None = None):
    fx = copy.deepcopy(base)
    mutate(fx)
    fx["fixture_id"], fx["reason"] = fixture_id, reason
    fx["expected_outcome"] = "accept" if kind == "valid" else "reject"
    fx.pop("expected_refusal", None)
    if refusal:
        fx["expected_refusal"] = refusal
    fx["provenance"] = {"source": f"single-defect mutation of fixture {base_id}" if kind == "invalid" else f"boundary mutation of fixture {base_id}",
                        "rule": "docs/engineering/ODES-TIME-SEMANTICS.md"}
    got = verdict(contract, fx)
    want = [refusal] if refusal else []
    if got != want:
        raise SystemExit(f"{contract}/{fixture_id}: expected {want}, validator says {got}")
    order = ["fixture_id", "synthetic", "expected_outcome", "reason", "expected_refusal", "provenance"]
    out = {k: fx[k] for k in order if k in fx}
    out.update({k: v for k, v in fx.items() if k not in out})
    path = CONTRACTS / contract / "fixtures" / kind / f"{fixture_id}.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print("wrote", path.relative_to(CONTRACTS.parent))


def walk_replace(node, old, new):
    """Replace one string everywhere in a JSON tree (the mutation of a time that is repeated across rows)."""
    if isinstance(node, dict):
        return {k: walk_replace(v, old, new) for k, v in node.items()}
    if isinstance(node, list):
        return [walk_replace(v, old, new) for v in node]
    return new if node == old else node


def seven_digit_fixtures():
    reason = "A time with seven fractional digits is refused: at most six are accepted, so no instant is ever silently truncated."
    for fixture in sorted(CONTRACTS.glob("*/fixtures/invalid/non-ascii-digit-time.json")):
        contract = fixture.parts[-4]
        base = json.loads(fixture.read_text(encoding="utf-8"))

        def find(node):
            if isinstance(node, dict):
                for v in node.values():
                    r = find(v)
                    if r:
                        return r
            elif isinstance(node, list):
                for v in node:
                    r = find(v)
                    if r:
                        return r
            elif isinstance(node, str) and node[:1] == "٢":
                return node
            return None
        bad = find(base)
        good = "2" + bad[1:]
        seven = good.replace("+00:00", ".0000001+00:00") if "+00:00" in good else good.replace("Z", ".0000001Z")

        def mutate(fx, bad=bad, seven=seven):
            fx["document"] = walk_replace(fx["document"], bad, seven)
            for key in ("journal",):
                if key in fx:
                    fx[key] = walk_replace(fx[key], bad, seven)
        write(contract, "invalid", base, "non-ascii-digit-time", "time-seven-fraction-digits", reason, mutate, base["expected_refusal"])


def boundaries():
    # freshness-clocks: a deadline is inclusive (expired / overdue only strictly after it); an extension window is half-open.
    for kind_id, phase in (("expired-not-past-the-deadline", "expired"), ("overdue-before-the-deadline", "overdue")):
        base = load("freshness-clocks", "invalid", kind_id)

        def mutate(fx, phase=phase):
            opening = next(e for e in fx["document"]["check_events"] if e["phase"] == "opened" and e.get("deadline"))
            for e in fx["document"]["check_events"]:
                if e["phase"] == phase:
                    e["recorded_at"] = opening["deadline"]
        write("freshness-clocks", "invalid", base, kind_id, f"{phase}-event-at-the-deadline",
              f"A deadline is inclusive: an {phase} event written at exactly the deadline is refused; only a later instant is past it.", mutate,
              "expired_not_past_deadline" if phase == "expired" else "overdue_before_deadline")

    # effect-reversibility: reversible_until is a window end (exclusive); the class age bound is inclusive.
    base = load("effect-reversibility", "valid", "cached-snapshot-reversible-class-within-age")

    def until_at_use(fx):
        fx["document"]["class_profiles"][0]["x-reversibility"]["reversible_until"] = fx["document"]["snapshot_uses"][0]["evaluated_at"]

    def age_at_bound(fx):
        fx["document"]["snapshot_uses"][0]["snapshot"]["observed_at"] = "2026-10-05T19:00:00+00:00"  # 30 s before use
        fx["document"]["class_profiles"][0]["max_status_age_seconds"] = 30
    write("effect-reversibility", "invalid", base, "cached-snapshot-reversible-class-within-age", "cached-snapshot-used-at-the-window-end",
          "The reversal window is half-open: a use at exactly reversible_until is after the window, so no cached snapshot.", until_at_use,
          "cache_after_reversal_window")
    write("effect-reversibility", "valid", base, "cached-snapshot-reversible-class-within-age", "cached-snapshot-at-exactly-the-age-bound",
          "The class age bound is inclusive: a snapshot exactly max_status_age_seconds old is still accepted.", age_at_bound)

    # bounded-deferral: a response at the deadline counts; an evaluation at the deadline is still open.
    base = load("bounded-deferral", "valid", "released-by-resolver-before-deadline")

    def response_at_deadline(fx):
        d = fx["document"]["deferrals"][0]
        d["responses"][0]["received_at"] = d["deadline"]
        d["resolved_at"] = d["deadline"]
        d["effect"]["first_observable_at"] = d["deadline"]
    write("bounded-deferral", "valid", base, "released-by-resolver-before-deadline", "release-response-at-exactly-the-deadline",
          "A deadline is inclusive: a response received at exactly the deadline counts and the release stands.", response_at_deadline)
    base = load("bounded-deferral", "valid", "open-deferral-within-deadline")

    def open_at_deadline(fx):
        fx["document"]["evaluated_at"] = fx["document"]["deferrals"][0]["deadline"]

    def expired_at_deadline(fx):
        open_at_deadline(fx)
        d = fx["document"]["deferrals"][0]
        d["outcome"], d["refusal_reason"], d["resolved_at"] = "refused", "deadline_expired", d["deadline"]
    write("bounded-deferral", "valid", base, "open-deferral-within-deadline", "open-deferral-evaluated-at-exactly-the-deadline",
          "A deadline is inclusive: evaluation at exactly the deadline leaves the deferral open.", open_at_deadline)
    write("bounded-deferral", "invalid", base, "open-deferral-within-deadline", "expiry-declared-at-exactly-the-deadline",
          "A deferral is expired only strictly after its deadline: refusing for deadline_expired at evaluation == deadline contradicts the rules.",
          expired_at_deadline, "outcome_mismatch")

    # non-broadening-delegation: an empty window is invalid (expires_at must be after not_before).
    base = load("non-broadening-delegation", "valid", "root-grant-no-delegation")

    def empty(fx):
        g = fx["document"]["grants"][0]
        g["expires_at"] = g["not_before"]
    write("non-broadening-delegation", "invalid", base, "root-grant-no-delegation", "window-empty-equal-bounds",
          "A validity window is [not_before, expires_at): equal bounds make it empty, which is refused.", empty, "window_invalid")


if __name__ == "__main__":
    seven_digit_fixtures()
    boundaries()
