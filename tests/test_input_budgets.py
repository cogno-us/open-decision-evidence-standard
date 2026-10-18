"""Input budgets for the validator and the command line.

Limits are checked before parsing, copying or schema traversal. Refusal is a structured ``fail`` carrying the closed reason code
``budget_exceeded`` (distinct from malformed input). Tests stay small: the over-limit inputs are just over a limit, not large.
"""
import copy
import json
import sys
import time
import types
from pathlib import Path

import pytest

from odes import common, exporter, recipient_validator
from odes.cli import main
from odes.common import BudgetExceeded, INPUT_LIMITS, MAX_REPORTED_ERRORS, check_budget, load_json
from odes.recipient_validator import evaluate_recipient_package
from odes.schema_validation import schema_errors

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = json.loads((ROOT / "examples" / "producer-v2" / "lost_ack.package.json").read_text())
POLICY = {"supported_profiles": ["odes_cognous_stack_export_0_2"], "now": "2026-01-01T00:00:00Z", "relying_party": "recipient.example.org", "purpose": "audit"}


def nest(depth):
    value = 1
    for _ in range(depth):
        value = [value]
    return value


def exactly_nodes(n):
    """A value with exactly n nodes that is within every other budget."""
    chunks, remaining = [], n - 1
    while remaining:
        size = min(remaining, 1001)
        chunks.append(0 if size == 1 else [0] * (size - 1))
        remaining -= size
    return chunks


CASES = {
    "max_depth": lambda n: nest(n),
    "max_nodes": exactly_nodes,
    "max_items": lambda n: [0] * n,
    "max_fields": lambda n: {f"k{i}": 0 for i in range(n)},
    "max_string": lambda n: "x" * n,
}


@pytest.mark.parametrize("dimension", sorted(CASES))
def test_budget_at_just_under_and_just_over_each_limit(dimension):
    limit = INPUT_LIMITS[dimension]
    check_budget(CASES[dimension](limit - 1))
    check_budget(CASES[dimension](limit))
    with pytest.raises(BudgetExceeded) as caught:
        check_budget(CASES[dimension](limit + 1))
    assert caught.value.code == "budget_exceeded"
    assert caught.value.dimension == dimension


def test_aggregate_string_budget():
    chunk = "y" * INPUT_LIMITS["max_string"]
    count = INPUT_LIMITS["max_bytes"] // len(chunk)
    check_budget([chunk] * count)
    with pytest.raises(BudgetExceeded) as caught:
        check_budget([chunk] * (count + 1))
    assert caught.value.dimension == "max_bytes"


def test_cyclic_value_is_refused_not_looped():
    cyclic = []
    cyclic.append(cyclic)
    with pytest.raises(BudgetExceeded):
        check_budget(cyclic)


def _write(tmp_path, text, name="in.json"):
    path = tmp_path / name
    path.write_bytes(text if isinstance(text, bytes) else text.encode())
    return path


def test_load_json_byte_limit_is_checked_before_parsing(tmp_path, monkeypatch):
    limit = INPUT_LIMITS["max_bytes"]
    at = _write(tmp_path, '"a"' + " " * (limit - 3), "at.json")
    assert load_json(at, limits=INPUT_LIMITS) == "a"
    over = _write(tmp_path, '"a"' + " " * (limit - 2), "over.json")

    def boom(*a, **k):
        raise AssertionError("parser must not run")
    monkeypatch.setattr(common.json, "loads", boom)
    monkeypatch.setattr(common.json, "load", boom)
    with pytest.raises(BudgetExceeded) as caught:
        load_json(over, limits=INPUT_LIMITS)
    assert caught.value.dimension == "max_bytes"


def test_load_json_depth_is_checked_before_parsing(tmp_path, monkeypatch):
    deep = _write(tmp_path, "[" * 5000 + "]" * 5000)
    monkeypatch.setattr(common.json, "loads", lambda *a, **k: pytest.fail("parser must not run"))
    with pytest.raises(BudgetExceeded) as caught:
        load_json(deep, limits=INPUT_LIMITS)
    assert caught.value.dimension == "max_depth"


def test_brackets_inside_strings_do_not_count_as_depth(tmp_path):
    path = _write(tmp_path, json.dumps({"s": "[" * 1000}))
    assert load_json(path, limits=INPUT_LIMITS) == {"s": "[" * 1000}


def test_load_json_without_limits_is_unchanged(tmp_path):
    assert load_json(_write(tmp_path, json.dumps(nest(40)))) == nest(40)


def test_malformed_input_is_not_a_budget_refusal(tmp_path):
    with pytest.raises(ValueError) as caught:
        load_json(_write(tmp_path, "{"), limits=INPUT_LIMITS)
    assert not isinstance(caught.value, BudgetExceeded)


def test_recipient_refuses_oversized_package_before_copying(monkeypatch):
    package = copy.deepcopy(EXAMPLE)
    package["provenance"]["padding"] = [0] * INPUT_LIMITS["max_items"]
    package["provenance"]["more"] = [0] * INPUT_LIMITS["max_items"]
    package["provenance"]["more2"] = [0] * INPUT_LIMITS["max_items"]
    package["provenance"]["more3"] = [0] * INPUT_LIMITS["max_items"]
    monkeypatch.setattr(recipient_validator, "deepcopy", lambda *a: pytest.fail("copy must not run"))
    monkeypatch.setattr(recipient_validator, "schema_errors", lambda *a: pytest.fail("schema must not run"))
    result = evaluate_recipient_package(package, POLICY)
    reliance = result["recipient_reliance_decision"]
    assert reliance["status"] == "fail"
    assert reliance["evidence"]["reason_code"] == "budget_exceeded"
    assert reliance["evidence"]["input"] == "package"
    assert result["schema_validity"]["status"] == "not_evaluated"


def test_recipient_refuses_oversized_policy():
    policy = {**POLICY, "trusted_digests": ["sha256:" + "0" * 64] * (INPUT_LIMITS["max_items"] + 1)}
    result = evaluate_recipient_package(copy.deepcopy(EXAMPLE), policy)
    assert result["recipient_reliance_decision"]["evidence"]["reason_code"] == "budget_exceeded"
    assert result["recipient_reliance_decision"]["evidence"]["input"] == "policy"


def test_programmatic_deep_package_is_refused_not_raised():
    package = copy.deepcopy(EXAMPLE)
    package["provenance"]["deep"] = nest(INPUT_LIMITS["max_depth"] + 5)
    result = evaluate_recipient_package(package, POLICY)
    assert result["recipient_reliance_decision"]["evidence"]["reason_code"] == "budget_exceeded"


def test_schema_error_flood_is_truncated_with_a_marker():
    record = copy.deepcopy(EXAMPLE["record"])
    record["policy_basis"] = [5] * 1000
    errors = schema_errors(record)
    assert len(errors) <= MAX_REPORTED_ERRORS + 1
    assert "truncated" in errors[-1]
    assert str(MAX_REPORTED_ERRORS) in errors[-1]


def test_few_schema_errors_are_not_truncated():
    record = copy.deepcopy(EXAMPLE["record"])
    record["policy_basis"] = [5] * 3
    errors = schema_errors(record)
    assert errors and not any("truncated" in e for e in errors)


def test_schema_errors_refuse_an_over_budget_record():
    record = copy.deepcopy(EXAMPLE["record"])
    record["extra"] = nest(INPUT_LIMITS["max_depth"] + 2)
    errors = schema_errors(record)
    assert errors[0].startswith("budget_exceeded")


def test_cli_refuses_oversized_and_deep_files(tmp_path, capsys):
    policy = _write(tmp_path, json.dumps(POLICY), "policy.json")
    for name, text in {"big.json": " " * (INPUT_LIMITS["max_bytes"] + 1), "deep.json": "[" * 3000 + "]" * 3000}.items():
        package = _write(tmp_path, text, name)
        assert main(["recipient-validate", str(package), "--policy", str(policy)]) == 1
        out = json.loads(capsys.readouterr().out)
        assert out["recipient_reliance_decision"]["status"] == "fail"
        assert out["recipient_reliance_decision"]["evidence"]["reason_code"] == "budget_exceeded"


def test_cli_validate_record_reports_budget(tmp_path, capsys):
    path = _write(tmp_path, "[" * 3000 + "]" * 3000)
    assert main(["validate-record", str(path)]) == 1
    assert "budget_exceeded" in capsys.readouterr().err


def test_deadline_helper_returns_raises_and_times_out():
    run = recipient_validator._run_with_deadline
    assert run(lambda: {"ok": 1}, 5) == {"ok": 1}
    with pytest.raises(recipient_validator.WorkerFailed):
        run(lambda: (_ for _ in ()).throw(RuntimeError("boom")), 5)
    started = time.monotonic()
    with pytest.raises(recipient_validator.DeadlineExceeded):
        run(lambda: time.sleep(30), 0.3)
    assert time.monotonic() - started < 5


def test_semantic_deadline_returns_structured_non_acceptance(monkeypatch):
    package = types.ModuleType("agent_replay_bundle")
    module = types.ModuleType("agent_replay_bundle.importers")

    class ImportContractError(ValueError):
        pass

    module.ImportContractError = ImportContractError
    module.import_bounded_workflow = lambda *a, **k: time.sleep(30)
    package.importers = module
    monkeypatch.setitem(sys.modules, "agent_replay_bundle", package)
    monkeypatch.setitem(sys.modules, "agent_replay_bundle.importers", module)
    monkeypatch.setattr(exporter, "installed_replay_revision", lambda: None)
    monkeypatch.setenv("ODES_ALLOW_UNVERIFIED_REPLAY", "1")
    monkeypatch.setattr(recipient_validator, "SEMANTIC_DEADLINE_SECONDS", 0.5)
    started = time.monotonic()
    result = evaluate_recipient_package(copy.deepcopy(EXAMPLE), POLICY)
    assert time.monotonic() - started < 10
    layer = result["replay_semantic_consistency"]
    assert layer["status"] == "fail"
    assert layer["evidence"]["reason_code"] == "budget_exceeded"
    assert layer["evidence"]["dimension"] == "semantic_deadline"
    assert result["recipient_reliance_decision"]["status"] == "fail"


def _valid_inputs():
    paths = list((ROOT / "contracts").glob("*/fixtures/valid/*.json")) + list((ROOT / "examples").rglob("*.json")) + list((ROOT / "conformance").rglob("*.json"))
    return sorted(paths)


@pytest.mark.parametrize("path", _valid_inputs(), ids=lambda p: str(p.relative_to(ROOT)))
def test_control_every_valid_fixture_and_example_is_within_budget(path):
    assert path.stat().st_size <= INPUT_LIMITS["max_bytes"]
    check_budget(load_json(path, limits=INPUT_LIMITS))


def test_control_valid_package_evaluates_as_before():
    result = evaluate_recipient_package(copy.deepcopy(EXAMPLE), {**POLICY, "supported_profiles": ["odes_cognous_stack_export_0_2"]})
    assert result["package_content_integrity"]["status"] == "pass"
    assert result["schema_validity"]["status"] == "pass"
