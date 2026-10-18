"""Time semantics (docs/engineering/ODES-TIME-SEMANTICS.md): instants, windows, deadlines, and the field table.

The contract validators are standalone single files (they are vendored), so they cannot import odes.common. This file runs each of them
against the shared helper on a corpus of boundary instants and refuses any difference.
"""
import importlib.util
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from odes import common as c

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
DOCS = ROOT / "docs" / "engineering"
FIELDS = json.loads((DOCS / "odes-time-fields.json").read_text(encoding="utf-8"))

CORPUS = [
    "2026-10-18T12:00:00Z", "2026-10-18T12:00:00+00:00", "2026-10-18T14:00:00+02:00", "2026-10-18T12:00:00-00:00",
    "2026-10-18T12:00:00.1Z", "2026-10-18T12:00:00.123456Z", "2026-10-18T12:00:00.000000+00:00",
    "2026-10-18T12:00:00.1234567Z", "2026-10-18T12:00:00.0000001Z", "2026-10-18T12:00:00.123456789+01:00",
    "2026-10-18T12:00:00", "2026-10-18T12:00:00.5", "2026-10-18 12:00:00Z", "2026-10-18t12:00:00Z", "2026-10-18T12:00:00z",
    "2026-10-18T12:00Z", "2026-10-18T12:00:60Z", "2026-10-18T23:59:60Z", "2026-10-18T24:00:00Z", "2026-10-18T12:00:00+24:00",
    "2026-10-18T12:00:00+23:59", "2026-10-18T12:00:00+00:60", "2026-10-18T12:00:00+0000", "2026-10-18T12:00:00+00",
    "2026-02-30T12:00:00Z", "0000-01-01T00:00:00Z", "0001-01-01T00:00:00Z", "9999-12-31T23:59:59Z", "9999-12-31T23:59:59.999999Z",
    "٢026-10-18T12:00:00Z", "2026-10-18T12:00:00Z\n", " 2026-10-18T12:00:00Z", "2026-10-18T12:00:00.Z", "", "Z", "not a time",
    None, 5, 1.5, True, [], {},
]


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


VALIDATORS = {p.parent.name: p for p in sorted(CONTRACTS.glob("*/validate.py"))}
WITH_AWARE = [n for n, p in VALIDATORS.items() if "def aware(" in p.read_text(encoding="utf-8")]


@pytest.mark.parametrize("contract", WITH_AWARE)
def test_every_contract_validator_reads_instants_like_the_helper(contract):
    module = _load(VALIDATORS[contract], "ts_" + contract.replace("-", "_"))
    for value in CORPUS:
        mine, theirs = c.parse_instant(value), module.aware(value)
        assert (mine is None) == (theirs is None), (contract, value)
        if mine is not None:
            assert mine == theirs, (contract, value)


def test_governed_exchange_reads_instants_like_the_helper():
    gx = _load(VALIDATORS["governed-exchange"], "ts_governed_exchange")
    schema = json.loads((CONTRACTS / "governed-exchange" / "schema.json").read_text(encoding="utf-8"))
    pattern = schema["$defs"]["timestamp"]["pattern"]
    for value in CORPUS:
        if not isinstance(value, str):
            continue
        accepted = gx._pattern_ok(pattern, value) and gx._real_time(value) is not None
        assert accepted == (c.parse_instant(value) is not None), value


def test_corpus_rejects_what_the_rules_say_it_rejects():
    refused = ["2026-10-18T12:00:00", "2026-10-18T12:00:00.1234567Z", "2026-10-18T12:00:60Z", "2026-10-18T12:00:00+00:60",
               "2026-10-18T12:00:00+24:00", "2026-10-18T12:00Z", "2026-10-18t12:00:00Z", "٢026-10-18T12:00:00Z", "2026-10-18T12:00:00Z\n",
               "2026-02-30T12:00:00Z", "0000-01-01T00:00:00Z"]
    assert all(c.parse_instant(v) is None for v in refused)
    accepted = ["2026-10-18T12:00:00Z", "2026-10-18T12:00:00.123456+05:30", "2026-10-18T12:00:00-00:00", "9999-12-31T23:59:59.999999Z"]
    assert all(c.parse_instant(v) is not None for v in accepted)


def test_an_offset_never_changes_the_instant_and_fractions_compare_exactly():
    utc = c.parse_instant("2026-10-18T12:00:00Z")
    assert c.parse_instant("2026-10-18T14:00:00+02:00") == utc == c.parse_instant("2026-10-18T07:00:00-05:00")
    assert c.parse_instant("2026-10-18T12:00:00.000001Z") > utc
    assert c.parse_instant("2026-10-18T12:00:00.5Z") == c.parse_instant("2026-10-18T12:00:00.500000Z")
    assert c.MAX_FRACTION_DIGITS == 6


def test_instant_problem_tells_naive_from_malformed():
    assert c.instant_problem("2026-10-18T12:00:00Z") is None
    assert c.instant_problem("2026-10-18T12:00:00") == "naive"
    assert c.instant_problem("2026-10-18T12:00:00.1234567") == "malformed"
    assert c.instant_problem("garbage") == "malformed" and c.instant_problem("") == "unavailable" and c.instant_problem(None) == "unavailable"


def test_parse_time_keeps_its_error_contract():
    assert c.parse_time(None) is None and c.parse_time("") is None
    assert c.parse_time("2026-10-18T10:00:00Z") is not None
    for bad in ("2026-10-18T10:00:00", "garbage", "٢026-10-18T10:00:00Z"):
        with pytest.raises(ValueError):
            c.parse_time(bad)


# ---------------------------------------------------------------- windows and deadlines

T = c.parse_instant("2026-10-18T12:00:00Z")
SEC = timedelta(seconds=1)


def test_window_is_half_open():
    start, end = T - 10 * SEC, T
    assert c.in_window(start, start, end)                  # evaluation == not_before: valid
    assert not c.in_window(end, start, end)                # evaluation == expires_at: expired
    assert c.window_expired(end, end) and not c.window_expired(end - SEC, end)
    assert c.window_not_yet_open(start - SEC, start) and not c.window_not_yet_open(start, start)
    assert c.in_window(end - timedelta(microseconds=1), start, end)


def test_empty_window_is_invalid():
    assert c.window_is_empty(T, T) and c.window_is_empty(T, T - SEC) and not c.window_is_empty(T, T + SEC)


def test_deadline_is_inclusive():
    assert c.deadline_open(T, T) and not c.deadline_passed(T, T)
    assert c.deadline_passed(T + timedelta(microseconds=1), T) and c.deadline_open(T - SEC, T)


def test_after_seconds_bounds():
    assert c.after_seconds(T, 60) == T + 60 * SEC
    for bad in (float("nan"), float("inf"), -float("inf"), True, "60", None, 10 ** 30):
        assert c.after_seconds(T, bad) is None
    assert c.after_seconds(datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone.utc), 10) is None


# ---------------------------------------------------------------- the field table

_TIME_NAME = re.compile(r"(_at$|_at_|^not_before$|^expires_at$|deadline|_until$|_seconds$|^as_of$|^evaluation_time$|^time$|_time$|^timestamp$)")


def _property_names(node, out):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                out.update(name for name in value if _TIME_NAME.search(name))
            _property_names(value, out)
    elif isinstance(node, list):
        for value in node:
            _property_names(value, out)


def test_every_time_member_of_every_schema_is_classed():
    by_contract = {}
    for field in FIELDS["fields"]:
        by_contract.setdefault(field["contract"], set()).add(field["member"])
    ignore = {"operation_horizon", "original_operation_horizon"}  # objects holding a window, classed through not_before / expires_at
    for schema_path in sorted(CONTRACTS.glob("*/schema.json")):
        names = set()
        _property_names(json.loads(schema_path.read_text(encoding="utf-8")), names)
        names -= ignore
        missing = names - by_contract.get(schema_path.parent.name, set())
        assert not missing, (schema_path.parent.name, sorted(missing))


def test_table_names_only_members_that_exist_and_known_classes():
    classes = set(FIELDS["classes"])
    assert classes == {"window", "deadline", "instant", "duration"}
    for field in FIELDS["fields"]:
        assert field["class"] in classes, field
        if field["class"] == "window":
            assert field["role"] in {"start", "end"}, field
        contract = field["contract"]
        schema_path = CONTRACTS / contract / "schema.json"
        if schema_path.exists():
            assert f'"{field["member"]}"' in schema_path.read_text(encoding="utf-8"), field
    seen = {(f["contract"], f["member"]) for f in FIELDS["fields"]}
    assert len(seen) == len(FIELDS["fields"])


def test_windows_and_deadlines_are_never_both():
    for contract, member in {(f["contract"], f["member"]) for f in FIELDS["fields"]}:
        classes = {f["class"] for f in FIELDS["fields"] if f["contract"] == contract and f["member"] == member}
        assert len(classes) == 1, (contract, member)


def test_documents_refer_to_each_other():
    semantics = (DOCS / "ODES-TIME-SEMANTICS.md").read_text(encoding="utf-8")
    conformance = (DOCS / "ODES-TIME-CONFORMANCE.md").read_text(encoding="utf-8")
    index = (DOCS / "ODES-INTERCOMPONENT-CONTRACTS.md").read_text(encoding="utf-8")
    assert "odes-time-fields.json" in semantics and "ODES-TIME-CONFORMANCE.md" in semantics
    assert "ODES-TIME-SEMANTICS.md" in conformance and "MISMATCH" in conformance and "MATCH" in conformance
    assert "ODES-TIME-SEMANTICS.md" in index and "ODES-TIME-CONFORMANCE.md" in index
    assert re.search(r"^35\. DECIDED", index, flags=re.M)
