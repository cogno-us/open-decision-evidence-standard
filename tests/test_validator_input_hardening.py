"""Validator input hardening across every contract draft (0.1.0-draft, unchanged).

Every ``contracts/*/validate.py`` must answer any parsed JSON value with a list of typed violations and never raise; refuse
non-finite numbers wherever a number is accepted; read files with a strict loader; and match digest and time forms over the whole
string with ASCII digits only. The golden fixtures for the refused forms live next to each contract.
"""
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NAMES = sorted(p.parent.name for p in (ROOT / "contracts").glob("*/validate.py"))
EXTRA_KEYS = {"destination-ledger": ["observations"], "freshness-clocks": ["journal", "host"], "operation-identity": ["journal"],
              "rule-revision": ["journal", "signers"], "witness-digest": ["record"]}
MODS = {}


def _mod(name):
    if name not in MODS:
        spec = importlib.util.spec_from_file_location("hard_" + name.replace("-", "_"), ROOT / "contracts" / name / "validate.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        MODS[name] = module
    return MODS[name]


def _first_valid(name):
    path = sorted((ROOT / "contracts" / name / "fixtures" / "valid").glob("*.json"))[0]
    return json.loads(path.read_text(encoding="utf-8"))


def _run(name, fx, doc):
    return _mod(name).validate(doc, *[fx.get(k) for k in EXTRA_KEYS.get(name, [])])


def _leaves(value, path=()):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _leaves(v, path + (k,))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _leaves(v, path + (i,))
    else:
        yield path, value


def _set(doc, path, value):
    doc = copy.deepcopy(doc)
    cur = doc
    for p in path[:-1]:
        cur = cur[p]
    cur[path[-1]] = value
    return doc


def _with_extension(doc, value):
    doc = copy.deepcopy(doc)
    target = doc[0] if isinstance(doc, list) else doc
    target["extensions"] = {"x-hardening": {"deep": [value]}}
    return doc


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")], ids=["nan", "inf", "neg-inf"])
def test_non_finite_numbers_are_refused_not_raised(name, value):
    fx = _first_valid(name)
    out = _run(name, fx, _with_extension(fx["document"], value))
    assert out and {v.code for v in out} == {"schema_violation"}


@pytest.mark.parametrize("name", NAMES)
def test_unpaired_surrogates_are_refused_in_values_and_member_names(name):
    fx = _first_valid(name)
    out = _run(name, fx, _with_extension(fx["document"], "a\ud800b"))
    assert out and {v.code for v in out} == {"schema_violation"}
    doc = copy.deepcopy(fx["document"])
    target = doc[0] if isinstance(doc, list) else doc
    target["extensions"] = {"x-ok": 1, "x-\ud800": 2}
    out = _run(name, fx, doc)
    assert out and {v.code for v in out} == {"schema_violation"}


@pytest.mark.parametrize("name,key", [("control-plane-journal", "amount"), ("destination-ledger", "amount"),
                                      ("non-broadening-delegation", "max_amount")])
def test_amount_members_refuse_non_finite_numbers(name, key):
    fx = _first_valid(name)
    paths = [p for p, v in _leaves(fx["document"]) if p and p[-1] == key and isinstance(v, (int, float)) and not isinstance(v, bool)]
    assert paths, "fixture without a numeric amount"
    for bad in (float("nan"), float("inf")):
        out = _run(name, fx, _set(fx["document"], paths[0], bad))
        assert out and all(v.code == "schema_violation" for v in out)


@pytest.mark.parametrize("name", NAMES)
def test_integer_members_out_of_range_never_raise(name):
    fx = _first_valid(name)
    ints = [p for p, v in _leaves(fx["document"]) if isinstance(v, int) and not isinstance(v, bool)][:25]
    for path in ints:
        for bad in (10 ** 20, 10 ** 400, -(10 ** 20), 2 ** 63):
            out = _run(name, fx, _set(fx["document"], path, bad))
            assert isinstance(out, list)


@pytest.mark.parametrize("name", NAMES)
def test_time_members_with_odd_forms_never_raise(name):
    fx = _first_valid(name)
    times = [p for p, v in _leaves(fx["document"]) if isinstance(v, str) and len(v) >= 20 and v[4:5] == "-" and "T" in v][:10]
    for path in times:
        for bad in ("2026-13-45T00:00:00+99:99", "9999-12-31T23:59:59-23:59", "0001-01-01T00:00:00+23:59", "٢026-10-18T10:00:00Z",
                    "2026-10-18T10:00:00Z\n", "20261018T100000Z", "2026-10-18 10:00:00Z"):
            assert isinstance(_run(name, fx, _set(fx["document"], path, bad)), list)


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("text", [b'{"a": 1, "a": 2}', b'{"a": NaN}', b'{"a": Infinity}', b'{"a": -Infinity}', b'{"a": 1e999}',
                                  b'\xff\xfe{"a": 1}', b'\xef\xbb\xbf{"a": 1}', b'{"a": 1', b'[' * 20000],
                         ids=["duplicate", "nan", "inf", "neg-inf", "overflow", "not-utf8", "bom", "truncated", "deep"])
def test_command_line_reads_files_with_the_strict_loader(name, text, tmp_path, capsys):
    path = tmp_path / "input.json"
    path.write_bytes(text)
    assert _mod(name).main([str(path)]) == 2
    assert "input_refused" in capsys.readouterr().out


@pytest.mark.parametrize("name", NAMES)
def test_command_line_refuses_duplicates_nested_in_a_fixture_and_still_reads_valid_ones(name, tmp_path, capsys):
    good = sorted((ROOT / "contracts" / name / "fixtures" / "valid").glob("*.json"))[0]
    assert _mod(name).main([str(good)]) == 0
    dup = tmp_path / "dup.json"
    dup.write_text(good.read_text(encoding="utf-8").replace('"synthetic": true', '"synthetic": true, "synthetic": true', 1), encoding="utf-8")
    assert _mod(name).main([str(dup)]) == 2
    assert "duplicate" in capsys.readouterr().out


@pytest.mark.parametrize("name", NAMES)
def test_command_line_reports_a_missing_file_without_raising(name, tmp_path, capsys):
    assert _mod(name).main([str(tmp_path / "absent.json")]) == 2


def test_witness_digest_line_files_use_the_strict_loader(tmp_path, capsys):
    path = tmp_path / "witness.jsonl"
    path.write_text('{"a": 1}\n{"a": 1, "a": 2}\n', encoding="utf-8")
    assert _mod("witness-digest").main([str(path)]) == 2
    assert "duplicate" in capsys.readouterr().out


@pytest.mark.parametrize("name", NAMES)
def test_schema_patterns_match_the_whole_string(name):
    mod = _mod(name)
    assert mod._pattern_ok("^sha256:[0-9a-f]{64}(?!\\n)$", "sha256:" + "a" * 64)
    assert not mod._pattern_ok("^sha256:[0-9a-f]{64}(?!\\n)$", "sha256:" + "a" * 64 + "\n")
    assert not mod._pattern_ok("^sha256:[0-9a-f]{64}$", "sha256:" + "a" * 64 + "\n")
    assert not mod._pattern_ok("^[0-9]+$", "١٢")
    assert mod._pattern_ok("^x-[a-z0-9]+$", "x-ok") and not mod._pattern_ok("^x-[a-z0-9]+$", "x-ok\n")


@pytest.mark.parametrize("name", NAMES)
def test_schema_patterns_end_with_a_guard_against_a_trailing_line_break(name):
    raw = (ROOT / "contracts" / name / "schema.json").read_text(encoding="utf-8")
    found = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "pattern" and isinstance(value, str):
                    found.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(json.loads(raw))
    for pattern in found:
        assert pattern.startswith("^") and pattern.endswith("(?!\\n)$"), pattern
        assert "\\d" not in pattern and "\\w" not in pattern
    assert "\\\\d" not in raw


@pytest.mark.parametrize("name", [n for n in NAMES if hasattr(_mod(n), "aware")])
def test_aware_accepts_only_the_ascii_iso_form(name):
    aware = _mod(name).aware
    assert aware("2026-10-18T10:00:00Z") is not None and aware("2026-10-18T10:00:00.5+02:00") is not None
    for bad in ("2026-10-18T10:00:00Z\n", "٢026-10-18T10:00:00Z", "2026-10-18T10:00:00", "20261018T100000Z", "2026-10-18 10:00:00Z", None, 5):
        assert aware(bad) is None


def test_package_loader_and_time_parser_are_strict(tmp_path):
    sys.path.insert(0, str(ROOT / "src"))
    try:
        from odes.common import load_json, parse_time
    finally:
        sys.path.pop(0)
    for text in ('{"a": 1, "a": 2}', '{"a": NaN}', '{"a": 1e999}'):
        path = tmp_path / "x.json"
        path.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError):
            load_json(path)
    assert parse_time("2026-10-18T10:00:00Z") is not None
    for bad in ("٢026-10-18T10:00:00Z", "2026-10-18T10:00:00Z\n"):
        with pytest.raises(ValueError):
            parse_time(bad)
