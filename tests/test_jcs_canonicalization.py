"""RFC 8785 (JCS) as a separately identified canonicalization profile; the legacy canonicalizer is retained byte for byte."""
import json
import random
import struct
from copy import deepcopy
from pathlib import Path

import pytest

from odes.canonicalization import (
    JCS_CANONICALIZATION_PROFILE,
    LEGACY_CANONICALIZATION_PROFILE,
    SUPPORTED_CANONICALIZATION_PROFILES,
    UnsupportedCanonicalization,
    canonical_bytes_for,
    digest_for,
    jcs_bytes,
    jcs_loads,
)
from odes.common import CANONICALIZATION_PROFILE, canonical_bytes, sha256
from odes.recipient_validator import _evaluate_package_content_integrity, evaluate_recipient_package

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "data"
PACKAGES = sorted((ROOT / "examples" / "producer-v2").glob("*.package.json"))
VECTORS = json.loads((DATA / "jcs_vectors.json").read_text(encoding="utf-8"))
GOLDEN = json.loads((DATA / "legacy_canonical_golden.json").read_text(encoding="utf-8"))["cases"]


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _as_jcs(package, *, redigest=True, repackage=True):
    package = deepcopy(package)
    package["integrity"]["canonicalization_profile"] = JCS_CANONICALIZATION_PROFILE
    if redigest:
        package["integrity"]["value"] = digest_for(JCS_CANONICALIZATION_PROFILE, {"record": package["record"], "profile": package["profile"]})
    if repackage:
        package["package_digest"] = digest_for(JCS_CANONICALIZATION_PROFILE, {k: package[k] for k in ("record", "profile", "integrity", "provenance")})
    return package


# ---------------------------------------------------------------- identifiers and dispatch

def test_identifiers_are_distinct_and_legacy_label_is_unchanged():
    assert LEGACY_CANONICALIZATION_PROFILE == CANONICALIZATION_PROFILE == "json-sort-keys-compact-utf8-no-nan"
    assert JCS_CANONICALIZATION_PROFILE == "rfc8785-jcs"
    assert SUPPORTED_CANONICALIZATION_PROFILES == (LEGACY_CANONICALIZATION_PROFILE, JCS_CANONICALIZATION_PROFILE)


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_legacy_outputs_and_digests_are_unchanged(name):
    cases = {
        "plain": {"b": 1, "a": [1, 2, {"z": None, "y": True}], "c": "x"},
        "float_int": {"v": 5.0},
        "exp": {"v": 1e-7},
        "negzero": {"v": -0.0},
        "nonbmp": {"\U0001F600": 1, "￿": 2, "a": 3},
        "unicode": {"k": "café   \u007f"},
        "big": {"v": 1e21, "w": 123456789012345678},
    }
    value = cases[name]
    assert canonical_bytes(value).hex() == GOLDEN[name]["legacy_bytes_hex"]
    assert sha256(value) == GOLDEN[name]["legacy_digest"]
    assert canonical_bytes_for(LEGACY_CANONICALIZATION_PROFILE, value) == canonical_bytes(value)
    assert digest_for(LEGACY_CANONICALIZATION_PROFILE, value) == sha256(value)


@pytest.mark.parametrize("path", PACKAGES, ids=lambda p: p.name)
def test_every_valid_fixture_keeps_its_historical_digests(path):
    package = _load(path)
    assert package["integrity"]["canonicalization_profile"] == LEGACY_CANONICALIZATION_PROFILE
    core = {"record": package["record"], "profile": package["profile"]}
    assert digest_for(LEGACY_CANONICALIZATION_PROFILE, core) == package["integrity"]["value"]
    material = {k: package[k] for k in ("record", "profile", "integrity", "provenance")}
    assert digest_for(LEGACY_CANONICALIZATION_PROFILE, material) == package["package_digest"]
    assert _evaluate_package_content_integrity(package, [])["status"] == "pass"


@pytest.mark.parametrize("identifier", ["", None, "rfc8785", "RFC8785-JCS", "rfc8785-jcs ", "json-sort-keys", 8785, ["rfc8785-jcs"]])
def test_unsupported_identifier_is_refused(identifier):
    with pytest.raises(UnsupportedCanonicalization):
        canonical_bytes_for(identifier, {"a": 1})
    with pytest.raises(UnsupportedCanonicalization):
        digest_for(identifier, {"a": 1})


# ---------------------------------------------------------------- vectors (produced by an independent implementation)

@pytest.mark.parametrize("name", sorted(VECTORS["documents"]))
def test_document_vectors(name):
    case = VECTORS["documents"][name]
    assert jcs_bytes(jcs_loads(case["input_json"])).hex() == case["jcs_hex"]


@pytest.mark.parametrize("entry", VECTORS["numbers"], ids=lambda e: e["ieee754_hex"])
def test_number_vectors(entry):
    number = struct.unpack(">d", bytes.fromhex(entry["ieee754_hex"]))[0]
    assert jcs_bytes(number).decode("ascii") == entry["text"]


def test_utf16_property_order_differs_from_legacy_order():
    value = {"￿": 2, "\U0001F600": 1, "a": 3}
    assert jcs_bytes(value) == '{"a":3,"\U0001F600":1,"￿":2}'.encode()
    assert canonical_bytes(value) == '{"a":3,"￿":2,"\U0001F600":1}'.encode()


def test_integral_float_exponent_and_negative_zero():
    assert jcs_bytes({"v": 5.0, "w": 1e-7, "x": -0.0, "y": 1e21}) == b'{"v":5,"w":1e-7,"x":0,"y":1e+21}'
    assert canonical_bytes({"v": 5.0}) == b'{"v":5.0}'


def test_independent_implementation_agrees_on_random_values():
    rfc8785 = pytest.importorskip("rfc8785")
    rng = random.Random(8785)
    alphabet = ["a", "b", "é", "€", "￿", "\U0001F600", "\U00010000", "", "\n", '"', "\\", "\x00", "\x7f", " "]

    def text():
        return "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 4)))

    def number():
        kind = rng.randint(0, 3)
        if kind == 0:
            return rng.randint(-(2**53 - 1), 2**53 - 1)
        if kind == 1:
            return struct.unpack(">d", rng.getrandbits(64).to_bytes(8, "big"))[0]
        if kind == 2:
            return float(rng.randint(-10**6, 10**6))
        return rng.uniform(-1, 1) * 10 ** rng.randint(-30, 30)

    def value(depth=0):
        kind = rng.randint(0, 6 if depth < 3 else 3)
        if kind == 0:
            return None
        if kind == 1:
            return rng.choice([True, False])
        if kind == 2:
            return text()
        if kind == 3:
            return number()
        if kind == 4:
            return [value(depth + 1) for _ in range(rng.randint(0, 3))]
        return {text(): value(depth + 1) for _ in range(rng.randint(0, 4))}

    checked = 0
    for _ in range(2000):
        candidate = value()
        try:
            expected = rfc8785.dumps(candidate)
        except Exception:
            with pytest.raises(ValueError):
                jcs_bytes(candidate)
            continue
        assert jcs_bytes(candidate) == expected
        checked += 1
    assert checked > 1500


# ---------------------------------------------------------------- refusals

@pytest.mark.parametrize("text", ['{"a":1,"a":2}', '{"a":1,"b":{"c":1,"c":1}}', '{"\\u0061":1,"a":2}'])
def test_duplicate_members_are_refused(text):
    with pytest.raises(ValueError):
        jcs_loads(text)


@pytest.mark.parametrize("value", ["\ud800", {"\udfff": 1}, ["ok", "x\ud83d"], {"a": {"b": "\udc00\ud800"}}])
def test_invalid_unicode_is_refused(value):
    with pytest.raises(ValueError):
        jcs_bytes(value)


@pytest.mark.parametrize("text", ['"\\ud800"', '{"\\udc00":1}'])
def test_lone_surrogate_escape_in_text_is_refused(text):
    with pytest.raises(ValueError):
        jcs_bytes(jcs_loads(text))


@pytest.mark.parametrize("data", [b'{"a":"\xff"}', b"\xef\xbb\xbf{}", b'{"a":"\xed\xa0\x80"}', "﻿{}"])
def test_invalid_or_bom_input_bytes_are_refused(data):
    with pytest.raises(ValueError):
        jcs_loads(data)


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf"), 2**53, -(2**53), 10**30, -(10**30)])
def test_numbers_outside_the_permitted_domain_are_refused(number):
    with pytest.raises(ValueError):
        jcs_bytes({"v": number})


@pytest.mark.parametrize("text", ["NaN", "Infinity", "-Infinity", "1e400", "-1e400", "9007199254740992", "-9007199254740993", "100000000000000000000000"])
def test_number_literals_outside_the_permitted_domain_are_refused(text):
    with pytest.raises(ValueError):
        jcs_loads(text)


def test_exact_integer_boundary_is_accepted():
    assert jcs_bytes([2**53 - 1, -(2**53 - 1)]) == b"[9007199254740991,-9007199254740991]"


@pytest.mark.parametrize("value", [{1: "a"}, {None: 1}, {("a",): 1}, (1, 2), {"a": b"x"}, {"a": {1, 2}}, object()])
def test_unsupported_value_types_are_refused(value):
    with pytest.raises(ValueError):
        jcs_bytes(value)


def test_excessive_nesting_is_refused():
    deep = current = []
    for _ in range(200):
        nxt = []
        current.append(nxt)
        current = nxt
    with pytest.raises(ValueError):
        jcs_bytes(deep)
    text = "[" * 5000 + "]" * 5000
    with pytest.raises(ValueError):
        jcs_loads(text)


# ---------------------------------------------------------------- recipient validator dispatch

@pytest.mark.parametrize("path", PACKAGES, ids=lambda p: p.name)
def test_package_digested_under_jcs_passes_integrity(path):
    package = _as_jcs(_load(path))
    result = _evaluate_package_content_integrity(package, [])
    assert result["status"] == "pass", result["reasons"]


@pytest.mark.parametrize("path", PACKAGES, ids=lambda p: p.name)
def test_relabelling_a_legacy_package_as_jcs_fails(path):
    legacy = _load(path)
    relabelled = deepcopy(legacy)
    relabelled["integrity"]["canonicalization_profile"] = JCS_CANONICALIZATION_PROFILE
    assert _evaluate_package_content_integrity(relabelled, [])["status"] == "fail"
    assert evaluate_recipient_package(relabelled, {})["recipient_reliance_decision"]["status"] == "fail"
    # relabel with only the record digest recomputed: the package digest still binds the old material
    partial = _as_jcs(legacy, redigest=True, repackage=False)
    assert _evaluate_package_content_integrity(partial, [])["status"] == "fail"
    # a complete re-digest under JCS is a different package; the Cognous export profiles are legacy-canonicalization only
    complete = _as_jcs(legacy)
    result = evaluate_recipient_package(complete, {"supported_profiles": [legacy["profile"]["implementation_profile"]]})
    assert result["declared_profile_conformance"]["status"] == "fail"
    assert result["recipient_reliance_decision"]["status"] == "fail"


def test_relabelling_a_jcs_package_as_legacy_fails():
    package = _as_jcs(_load(PACKAGES[0]))
    package["integrity"]["canonicalization_profile"] = LEGACY_CANONICALIZATION_PROFILE
    assert _evaluate_package_content_integrity(package, [])["status"] == "fail"


@pytest.mark.parametrize("identifier", ["rfc8785", "jcs", "RFC8785-JCS", "", None, 7, ["rfc8785-jcs"]])
def test_unsupported_declared_identifier_is_unsupported_not_pass(identifier):
    package = _load(PACKAGES[0])
    package["integrity"]["canonicalization_profile"] = identifier
    assert _evaluate_package_content_integrity(package, [])["status"] == "unsupported"


def test_jcs_package_with_unsupported_number_does_not_pass_integrity():
    package = _as_jcs(_load(PACKAGES[0]), redigest=False, repackage=False)
    package["record"]["x_probe"] = 2**60
    result = _evaluate_package_content_integrity(package, [])
    assert result["status"] in {"fail", "unsupported"}


def test_jcs_package_tamper_is_detected():
    package = _as_jcs(_load(PACKAGES[0]))
    package["record"]["decision_id"] = package["record"]["decision_id"] + "-x"
    assert _evaluate_package_content_integrity(package, [])["status"] == "fail"
