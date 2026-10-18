"""Optional context arguments (run record, host configuration, signers, deferrals, observations, record) that do not have the expected
shape are refused with a typed violation; no validator raises on them (decision 39-H).

A deterministic mutation sweep over every contract validator that takes optional context: each fixture's context is changed at every
member to a value of the wrong shape (null, text, number, boolean, empty or odd array and object) and with the member removed.
"""
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
CONTEXT = {"bounded-deferral": ["journal"], "effect-reversibility": ["journal", "deferrals"], "freshness-clocks": ["journal", "host"],
           "operation-identity": ["journal"], "rule-revision": ["journal", "signers"], "destination-ledger": ["observations"],
           "witness-digest": ["record"]}
WRONG = [None, "x", 0, [], {}, True, 1.5, [None], {"a": 1}]


def _load(contract):
    spec = importlib.util.spec_from_file_location("rn_" + contract.replace("-", "_"), CONTRACTS / contract / "validate.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _paths(value, prefix=()):
    yield prefix
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _paths(v, prefix + (k,))
    elif isinstance(value, list):
        for i, v in enumerate(value[:2]):
            yield from _paths(v, prefix + (i,))


def _mutations(context):
    for path in _paths(context):
        if len(path) > 3:
            continue
        for wrong in WRONG:
            if not path:
                yield wrong
                continue
            copy_ = copy.deepcopy(context)
            parent = copy_
            for key in path[:-1]:
                parent = parent[key]
            parent[path[-1]] = copy.deepcopy(wrong)
            yield copy_
        if path:
            copy_ = copy.deepcopy(context)
            parent = copy_
            for key in path[:-1]:
                parent = parent[key]
            del parent[path[-1]]
            yield copy_


def _cases():
    for contract, names in CONTEXT.items():
        fixtures = sorted((CONTRACTS / contract / "fixtures" / "valid").glob("*.json"))
        for path in fixtures[:2]:
            yield contract, path.stem, names


@pytest.mark.parametrize("contract,name,names", list(_cases()), ids=lambda v: v if isinstance(v, str) else None)
def test_malformed_optional_context_is_refused_not_raised(contract, name, names):
    module = _load(contract)
    fx = json.loads((CONTRACTS / contract / "fixtures" / "valid" / f"{name}.json").read_text(encoding="utf-8"))
    context = {n: fx[n] for n in names if n in fx}
    raised = []
    for member, value in context.items():
        for mutated in _mutations(value):
            try:
                module.validate(fx["document"], **{**context, member: mutated})
            except Exception as exc:  # the property under test: nothing escapes
                raised.append((member, type(exc).__name__, str(exc)[:60]))
                if len(raised) > 3:
                    break
    assert raised == []


def test_a_malformed_journal_gets_the_typed_violation():
    module = _load("freshness-clocks")
    fx = json.loads((CONTRACTS / "freshness-clocks" / "fixtures" / "valid" / "clocks-follow-the-service-clock.json").read_text(encoding="utf-8"))
    for bad in ("x", {"run_id": fx["journal"]["run_id"], "decisions": None}):
        found = {v.code for v in module.validate(fx["document"], bad, fx.get("host"))}
        assert "context_malformed" in found or "journal_run_mismatch" in found


@pytest.mark.parametrize("contract", ["freshness-clocks", "operation-identity", "rule-revision"])
def test_valid_context_still_passes(contract):
    module = _load(contract)
    for path in sorted((CONTRACTS / contract / "fixtures" / "valid").glob("*.json")):
        fx = json.loads(path.read_text(encoding="utf-8"))
        kwargs = {n: fx[n] for n in CONTEXT[contract] if n in fx}
        assert module.validate(fx["document"], **kwargs) == [], path.name
