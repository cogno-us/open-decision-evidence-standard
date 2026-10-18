"""Typed schema constants and the hour-24 guard, over every contract validator.

A schema ``const`` matches only the same JSON type with an equal value (``1`` is not ``true``, ``0`` is not ``false``,
``1.0`` is not ``1``), as ``enum`` already did. The instant shape refuses an hour of 24 before any parser sees it, so the
outcome does not depend on how the running Python reads ``T24:00:00``.
"""
import importlib.util
import re
import sys
from pathlib import Path

import pytest

from odes import common as c

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
PATHS = {p.parent.name: p for p in sorted(CONTRACTS.glob("*/validate.py"))}


def _load(contract):
    spec = importlib.util.spec_from_file_location("te_" + contract.replace("-", "_"), PATHS[contract])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# destination-ledger has an interpreter but its schema declares no const; the others interpret it.
WITH_CHECK = [n for n, p in PATHS.items() if '"const" in schema' in p.read_text(encoding="utf-8")]
WITH_SHAPE = [n for n, p in PATHS.items() if "_TIME_SHAPE = " in p.read_text(encoding="utf-8")]


def _refused(module, value, const):
    out = []
    module._check(value, {"const": const}, {}, "$", out)
    return bool(out)


def test_every_validator_with_a_schema_interpreter_is_covered():
    assert len(WITH_CHECK) >= 16 and len(WITH_SHAPE) >= 16


@pytest.mark.parametrize("contract", WITH_CHECK)
def test_const_is_type_strict(contract):
    m = _load(contract)
    assert _refused(m, 1, True) and _refused(m, 0, False) and _refused(m, 1.0, 1) and _refused(m, True, 1)
    assert _refused(m, "1", 1) and _refused(m, None, False)
    assert not _refused(m, True, True) and not _refused(m, False, False) and not _refused(m, 1, 1) and not _refused(m, "a", "a")


HOUR_24 = ["2026-10-18T24:00:00Z", "2026-10-18T24:00:00+00:00", "2026-10-18T24:59:59Z", "2026-10-18T25:00:00Z"]


@pytest.mark.parametrize("contract", WITH_SHAPE)
def test_instant_shape_refuses_hour_24(contract):
    m = _load(contract)
    for value in HOUR_24:
        assert m._TIME_SHAPE.fullmatch(value) is None, value
    assert m._TIME_SHAPE.fullmatch("2026-10-18T23:59:59Z") is not None
    assert m._TIME_SHAPE.fullmatch("2026-10-18T00:00:00+05:30") is not None


def test_common_instant_pattern_refuses_hour_24():
    for value in HOUR_24:
        assert re.fullmatch(c.INSTANT_PATTERN, value) is None and c.parse_instant(value) is None
    assert c.parse_instant("2026-10-18T23:59:59Z") is not None


def test_governed_exchange_timestamp_pattern_refuses_hour_24():
    import json
    gx = _load("governed-exchange")
    pattern = json.loads((CONTRACTS / "governed-exchange" / "schema.json").read_text(encoding="utf-8"))["$defs"]["timestamp"]["pattern"]
    for value in HOUR_24:
        assert not gx._pattern_ok(pattern, value), value
    assert gx._pattern_ok(pattern, "2026-10-18T23:59:59Z")
