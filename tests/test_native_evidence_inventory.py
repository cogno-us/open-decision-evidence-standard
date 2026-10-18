"""Native evidence inventory: opaque artifacts, byte preserving, digest over the original bytes."""
import base64
import builtins
import hashlib
import json
import socket
import urllib.request
from copy import deepcopy
from pathlib import Path

import pytest

from odes.evidence_inventory import (
    INVENTORY_TYPE,
    INVENTORY_VERSION,
    InventoryLimits,
    build_inventory,
    build_inventory_entry,
    evaluate_native_evidence_inventory,
    extract_artifact,
)
from odes.recipient_validator import _evaluate_package_content_integrity, evaluate_recipient_package

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = sorted((ROOT / "examples" / "producer-v2").glob("*.package.json"))

# Deliberately not canonical: odd whitespace, key order, a duplicate member, an escaped non-ASCII character, a trailing newline.
RAW_JSON = b'{ "z" : 1,\n  "a":[1.0,  2e0],\r\n "a" : "\\u00e9" , "sig":"abc"}\n'
RAW_BIN = bytes(range(256)) * 3


def _entry(artifact_id="receipt-1", data=RAW_JSON, **kw):
    kw.setdefault("source_format", "example-receipt")
    kw.setdefault("source_format_version", "1")
    kw.setdefault("relation", "execution_evidence")
    kw.setdefault("media_type", "application/json")
    return build_inventory_entry(artifact_id, data=data, **kw)


def _inv(*entries):
    return build_inventory(list(entries))


def _report(entry, status="pass", **kw):
    base = {"artifact_id": entry["artifact_id"], "artifact_digest_value": entry["digest_value"], "verifier_id": "example-native-verifier",
            "verifier_version": "9.9.9", "recipient_policy_id": "recipient-policy-1", "status": status}
    base.update(kw)
    return base


def _policy(**kw):
    return {"native_evidence": kw}


# ---------------------------------------------------------------- byte preservation and digest

def test_embedded_bytes_round_trip_exactly_and_digest_covers_original_bytes():
    entry = _entry()
    assert extract_artifact(entry) == RAW_JSON
    assert entry["byte_length"] == len(RAW_JSON)
    assert entry["digest_algorithm"] == "sha256"
    assert entry["digest_value"] == hashlib.sha256(RAW_JSON).hexdigest()
    result = evaluate_native_evidence_inventory(_inv(entry))
    assert result["status"] == "pass", result["reasons"]
    assert result["evidence"]["artifacts"]["receipt-1"]["bytes_digest"] == "pass"


def test_binary_bytes_round_trip():
    entry = _entry("blob", RAW_BIN, media_type="application/octet-stream")
    assert extract_artifact(entry) == RAW_BIN


def test_parse_and_reserialize_is_not_byte_preservation():
    reparsed = json.dumps(json.loads(RAW_JSON), sort_keys=True, separators=(",", ":")).encode()
    assert reparsed != RAW_JSON
    entry = _entry()
    entry["bytes_base64"] = base64.b64encode(reparsed).decode()
    result = evaluate_native_evidence_inventory(_inv(entry))
    assert result["status"] == "fail"


def test_digest_does_not_depend_on_any_json_canonicalization_module(monkeypatch):
    import odes.canonicalization as canon
    import odes.common as common

    def boom(*a, **k):
        raise AssertionError("canonicalization used")
    monkeypatch.setattr(canon, "jcs_bytes", boom)
    monkeypatch.setattr(common, "canonical_bytes", boom)
    entry = _entry()
    assert evaluate_native_evidence_inventory(_inv(entry))["status"] == "pass"


# ---------------------------------------------------------------- integrity outcomes

def test_digest_mismatch_fails():
    entry = _entry()
    entry["digest_value"] = hashlib.sha256(b"other").hexdigest()
    result = evaluate_native_evidence_inventory(_inv(entry))
    assert result["status"] == "fail"
    assert result["evidence"]["artifacts"]["receipt-1"]["bytes_digest"] == "fail"


def test_byte_length_mismatch_fails():
    entry = _entry()
    entry["byte_length"] += 1
    assert evaluate_native_evidence_inventory(_inv(entry))["status"] == "fail"


def test_single_changed_byte_fails():
    entry = _entry()
    data = bytearray(RAW_JSON)
    data[5] ^= 1
    entry["bytes_base64"] = base64.b64encode(bytes(data)).decode()
    assert evaluate_native_evidence_inventory(_inv(entry))["status"] == "fail"


def test_required_artifact_with_locator_only_is_unavailable_and_blocks():
    entry = _entry(locator={"kind": "opaque-reference", "reference": "store://example/receipt-1"}, embed=False, required=True)
    result = evaluate_native_evidence_inventory(_inv(entry))
    assert result["status"] == "unavailable"
    assert result["evidence"]["artifacts"]["receipt-1"]["bytes_digest"] == "unavailable"


def test_optional_unavailable_artifact_is_reported_not_hidden():
    present = _entry("a")
    absent = _entry("b", locator={"kind": "opaque-reference", "reference": "x"}, embed=False, required=False)
    result = evaluate_native_evidence_inventory(_inv(present, absent))
    assert result["status"] == "pass"
    assert result["evidence"]["unavailable_optional"] == ["b"]


def test_recipient_policy_can_require_an_artifact_the_producer_marked_optional():
    absent = _entry("b", locator={"kind": "opaque-reference", "reference": "x"}, embed=False, required=False)
    result = evaluate_native_evidence_inventory(_inv(absent), _policy(required_artifacts=[{"artifact_id": "b", "relation": "execution_evidence"}]))
    assert result["status"] == "unavailable"


def test_required_artifact_missing_from_inventory_is_unavailable():
    result = evaluate_native_evidence_inventory(_inv(_entry("a")), _policy(required_artifacts=[{"artifact_id": "missing", "relation": "execution_evidence"}]))
    assert result["status"] == "unavailable"


def test_required_artifact_with_changed_relation_fails():
    entry = _entry("a", relation="supporting_context")
    result = evaluate_native_evidence_inventory(_inv(entry), _policy(required_artifacts=[{"artifact_id": "a", "relation": "execution_evidence"}]))
    assert result["status"] == "fail"


def test_recipient_supplied_bytes_for_a_locator_entry_are_checked_against_the_digest():
    entry = _entry(locator={"kind": "opaque-reference", "reference": "x"}, embed=False, required=True)
    ok = evaluate_native_evidence_inventory(_inv(entry), supplied_artifacts={"receipt-1": RAW_JSON})
    assert ok["status"] == "pass"
    bad = evaluate_native_evidence_inventory(_inv(entry), supplied_artifacts={"receipt-1": RAW_JSON + b" "})
    assert bad["status"] == "fail"


def test_supplied_bytes_that_differ_from_embedded_bytes_fail():
    entry = _entry()
    result = evaluate_native_evidence_inventory(_inv(entry), supplied_artifacts={"receipt-1": b"different"})
    assert result["status"] == "fail"


def test_duplicate_artifact_ids_fail():
    result = evaluate_native_evidence_inventory(_inv(_entry("a"), _entry("a", RAW_BIN)))
    assert result["status"] == "fail"
    assert any("duplicate" in r for r in result["reasons"])


# ---------------------------------------------------------------- closed shape, unsupported values

@pytest.mark.parametrize("mutate", [
    lambda e: e.update(verified=True),
    lambda e: e.update(native_verification={"status": "pass"}),
    lambda e: e.update(overall_status="Verified"),
    lambda e: e.update(relation="invented"),
    lambda e: e.update(artifact_id=""),
    lambda e: e.update(artifact_id="has space"),
    lambda e: e.update(artifact_id=5),
    lambda e: e.update(media_type="JSON"),
    lambda e: e.update(media_type=None),
    lambda e: e.update(byte_length=-1),
    lambda e: e.update(byte_length=True),
    lambda e: e.update(byte_length="5"),
    lambda e: e.update(digest_value="ABC"),
    lambda e: e.update(digest_value=hashlib.sha256(b"x").hexdigest().upper()),
    lambda e: e.update(required="yes"),
    lambda e: e.update(producer_assertions=["verified"]),
    lambda e: e.update(limitations="none"),
    lambda e: e.update(bytes_base64="@@@@"),
    lambda e: e.update(bytes_base64=base64.b64encode(RAW_JSON).decode() + "\n"),
    lambda e: e.update(locator={"kind": "opaque-reference", "reference": "x"}),
    lambda e: e.pop("bytes_base64"),
    lambda e: e.pop("source_format"),
])
def test_malformed_entries_fail(mutate):
    entry = _entry()
    mutate(entry)
    assert evaluate_native_evidence_inventory(_inv(entry))["status"] == "fail"


def test_non_canonical_base64_padding_is_refused():
    entry = _entry("a", b"ab")  # 'YWI=' ; flip the unused low bits of the last quantum
    encoded = entry["bytes_base64"]
    assert encoded.endswith("=")
    alt = encoded[:-2] + "J="
    assert alt != encoded and base64.b64decode(alt) == b"ab"
    entry["bytes_base64"] = alt
    assert evaluate_native_evidence_inventory(_inv(entry))["status"] == "fail"


def test_unsupported_digest_algorithm_is_unsupported_not_pass():
    entry = _entry()
    entry["digest_algorithm"] = "sha3-256"
    assert evaluate_native_evidence_inventory(_inv(entry))["status"] == "unsupported"


def test_unsupported_inventory_version_or_type():
    inv = _inv(_entry())
    inv["inventory_version"] = "9.0.0"
    assert evaluate_native_evidence_inventory(inv)["status"] == "unsupported"
    inv = _inv(_entry())
    inv["inventory_type"] = "other"
    assert evaluate_native_evidence_inventory(inv)["status"] in {"unsupported", "fail"}
    inv = _inv(_entry())
    inv["extra"] = 1
    assert evaluate_native_evidence_inventory(inv)["status"] == "fail"


@pytest.mark.parametrize("value", [None, [], "x", 5, {}, {"inventory_type": INVENTORY_TYPE}])
def test_malformed_inventories_do_not_pass(value):
    assert evaluate_native_evidence_inventory(value)["status"] in {"fail", "unsupported", "unavailable"}


def test_absent_inventory_is_unavailable_when_required():
    assert evaluate_native_evidence_inventory(None, _policy(required_artifacts=[{"artifact_id": "a", "relation": "execution_evidence"}]))["status"] == "unavailable"


def test_empty_inventory_cannot_satisfy_a_requirement():
    inv = {"inventory_type": INVENTORY_TYPE, "inventory_version": INVENTORY_VERSION, "artifacts": []}
    result = evaluate_native_evidence_inventory(inv, _policy(required_artifacts=[{"artifact_id": "a", "relation": "execution_evidence"}]))
    assert result["status"] == "unavailable"


# ---------------------------------------------------------------- producer assertions versus recipient-generated reports

def test_producer_assertions_are_kept_separate_and_never_a_pass():
    entry = _entry(producer_assertions={"verified": True, "overall_status": "Verified", "native_result": "pass"})
    result = evaluate_native_evidence_inventory(_inv(entry), _policy(required_native_verification=["receipt-1"]))
    assert result["status"] == "unavailable"
    art = result["evidence"]["artifacts"]["receipt-1"]
    assert art["producer_assertions"] == {"verified": True, "overall_status": "Verified", "native_result": "pass"}
    assert art["producer_assertions_status"] == "not_evaluated"
    assert art["native_verification"]["status"] == "unavailable"


def test_producer_assertions_do_not_change_the_integrity_outcome():
    entry = _entry(producer_assertions={"verified": True})
    entry["digest_value"] = hashlib.sha256(b"other").hexdigest()
    assert evaluate_native_evidence_inventory(_inv(entry))["status"] == "fail"


def test_recipient_report_is_recorded_with_verifier_identity_and_policy():
    entry = _entry()
    result = evaluate_native_evidence_inventory(_inv(entry), _policy(required_native_verification=["receipt-1"], verification_reports=[_report(entry)]))
    assert result["status"] == "pass", result["reasons"]
    native = result["evidence"]["artifacts"]["receipt-1"]["native_verification"]
    assert native["status"] == "pass"
    assert native["verifier_id"] == "example-native-verifier" and native["verifier_version"] == "9.9.9"
    assert native["recipient_policy_id"] == "recipient-policy-1"
    assert "not a decision authority" in result["evidence"]["boundary"]


@pytest.mark.parametrize("status,expected", [("fail", "fail"), ("unsupported", "unsupported"), ("unavailable", "unavailable"), ("not_evaluated", "unavailable")])
def test_native_non_pass_results_are_carried_through(status, expected):
    entry = _entry()
    result = evaluate_native_evidence_inventory(_inv(entry), _policy(required_native_verification=["receipt-1"], verification_reports=[_report(entry, status)]))
    assert result["status"] == expected


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(artifact_digest_value="0" * 64),
    lambda r: r.update(artifact_id="other"),
    lambda r: r.update(status="verified"),
    lambda r: r.update(status=True),
    lambda r: r.pop("verifier_version"),
    lambda r: r.update(verifier_id=""),
    lambda r: r.pop("recipient_policy_id"),
    lambda r: r.update(unexpected=1),
])
def test_malformed_or_unbound_reports_do_not_pass(mutate):
    entry = _entry()
    report = _report(entry)
    mutate(report)
    result = evaluate_native_evidence_inventory(_inv(entry), _policy(required_native_verification=["receipt-1"], verification_reports=[report]))
    assert result["status"] in {"fail", "unavailable"}


def test_report_cannot_rescue_a_digest_mismatch():
    entry = _entry()
    entry["digest_value"] = hashlib.sha256(b"other").hexdigest()
    result = evaluate_native_evidence_inventory(_inv(entry), _policy(required_native_verification=["receipt-1"], verification_reports=[_report(entry)]))
    assert result["status"] == "fail"


def test_two_reports_for_one_artifact_are_refused():
    entry = _entry()
    reports = [_report(entry), _report(entry, "fail")]
    result = evaluate_native_evidence_inventory(_inv(entry), _policy(required_native_verification=["receipt-1"], verification_reports=reports))
    assert result["status"] == "fail"


def test_required_native_verification_of_an_artifact_missing_from_the_inventory_is_unavailable():
    result = evaluate_native_evidence_inventory(_inv(_entry("a")), _policy(required_native_verification=["missing"]))
    assert result["status"] == "unavailable"


# ---------------------------------------------------------------- resource limits

def test_over_limit_inputs_fail_before_decoding(monkeypatch):
    decoded = []
    real = base64.b64decode
    monkeypatch.setattr(base64, "b64decode", lambda *a, **k: decoded.append(1) or real(*a, **k))
    limits = InventoryLimits(max_entries=2, max_artifact_bytes=64, max_total_bytes=100)
    too_many = _inv(_entry("a", b"1"), _entry("b", b"2"), _entry("c", b"3"))
    assert evaluate_native_evidence_inventory(too_many, limits=limits)["status"] == "fail"
    big = _entry("big", b"x" * 65)
    assert evaluate_native_evidence_inventory(_inv(big), limits=limits)["status"] == "fail"
    total = _inv(_entry("a", b"x" * 60), _entry("b", b"y" * 60))
    assert evaluate_native_evidence_inventory(total, limits=limits)["status"] == "fail"
    assert decoded == []


def test_declared_length_over_the_limit_is_refused_even_for_a_locator_entry():
    entry = _entry(locator={"kind": "opaque-reference", "reference": "x"}, embed=False, byte_length=10**12, digest_value="0" * 64)
    assert evaluate_native_evidence_inventory(_inv(entry))["status"] == "fail"


def test_default_limits_are_bounded_and_policy_cannot_raise_them():
    default = InventoryLimits()
    assert default.max_artifact_bytes <= 8 * 1024 * 1024 and default.max_entries <= 1000
    entry = _entry("big", b"x" * (default.max_artifact_bytes + 1))
    result = evaluate_native_evidence_inventory(_inv(entry), _policy(max_artifact_bytes=10**12))
    assert result["status"] == "fail"


def test_over_long_strings_and_deep_producer_assertions_are_refused():
    assert evaluate_native_evidence_inventory(_inv(_entry(source_format="x" * 1000)))["status"] == "fail"
    deep = current = {}
    for _ in range(100):
        nxt = {}
        current["k"] = nxt
        current = nxt
    assert evaluate_native_evidence_inventory(_inv(_entry(producer_assertions=deep)))["status"] == "fail"
    assert evaluate_native_evidence_inventory(_inv(_entry(limitations=["x"] * 10000)))["status"] == "fail"


# ---------------------------------------------------------------- no retrieval, no local reads, no plugin loading

def test_no_network_file_or_plugin_access(monkeypatch):
    calls = []

    def guard(name):
        def inner(*a, **k):
            calls.append(name)
            raise AssertionError(name)
        return inner

    monkeypatch.setattr(socket.socket, "connect", guard("connect"))
    monkeypatch.setattr(socket, "getaddrinfo", guard("getaddrinfo"))
    monkeypatch.setattr(urllib.request, "urlopen", guard("urlopen"))
    monkeypatch.setattr(Path, "read_bytes", guard("read_bytes"))
    monkeypatch.setattr(Path, "read_text", guard("read_text"))
    monkeypatch.setattr(Path, "open", guard("Path.open"))
    real_open = builtins.open
    monkeypatch.setattr(builtins, "open", lambda *a, **k: guard("open")(*a, **k))
    import importlib
    monkeypatch.setattr(importlib, "import_module", guard("import_module"))
    entries = [_entry(f"l{i}", locator={"kind": "opaque-reference", "reference": ref}, embed=False, required=True)
               for i, ref in enumerate(["http://127.0.0.1:1/a", "https://example.invalid/b", "file:///etc/hostname", "/etc/hostname", "../../x", "plugin:evil.module"])]
    result = evaluate_native_evidence_inventory(_inv(*entries), _policy(required_native_verification=["l0"]))
    assert result["status"] == "unavailable"
    assert calls == []
    monkeypatch.setattr(builtins, "open", real_open)


def test_module_does_not_import_network_or_dynamic_loading_modules():
    source = (ROOT / "src" / "odes" / "evidence_inventory.py").read_text(encoding="utf-8")
    for name in ("urllib", "http", "socket", "requests", "importlib", "subprocess", "pkg_resources", "ftplib"):
        assert f"import {name}" not in source and f"from {name}" not in source


# ---------------------------------------------------------------- package level

def _package_with_inventory(inventory):
    package = json.loads(PACKAGES[0].read_text(encoding="utf-8"))
    package["provenance"]["native_evidence_inventory"] = inventory
    from odes.common import sha256
    package["package_digest"] = sha256({k: package[k] for k in ("record", "profile", "integrity", "provenance")})
    return package


def test_package_digest_binds_the_inventory():
    entry = _entry()
    package = _package_with_inventory(_inv(entry))
    assert _evaluate_package_content_integrity(package, [])["status"] == "pass"
    tampered = deepcopy(package)
    tampered["provenance"]["native_evidence_inventory"]["artifacts"][0]["relation"] = "supporting_context"
    assert _evaluate_package_content_integrity(tampered, [])["status"] == "fail"
    tampered = deepcopy(package)
    tampered["provenance"]["native_evidence_inventory"]["artifacts"][0]["bytes_base64"] = base64.b64encode(b"x").decode()
    assert _evaluate_package_content_integrity(tampered, [])["status"] == "fail"


def test_recipient_validator_reports_the_inventory_layer_and_blocks_reliance():
    entry = _entry(locator={"kind": "opaque-reference", "reference": "x"}, embed=False, required=True)
    package = _package_with_inventory(_inv(entry))
    layers = evaluate_recipient_package(package, {"supported_profiles": [package["profile"]["implementation_profile"]]})
    assert layers["native_evidence_inventory"]["status"] == "unavailable"
    assert layers["recipient_reliance_decision"]["status"] == "fail"


def test_recipient_validator_requires_the_inventory_when_policy_asks():
    package = json.loads(PACKAGES[0].read_text(encoding="utf-8"))
    layers = evaluate_recipient_package(package, {"native_evidence": {"required_artifacts": [{"artifact_id": "a", "relation": "execution_evidence"}]}})
    assert layers["native_evidence_inventory"]["status"] == "unavailable"
    assert layers["recipient_reliance_decision"]["status"] == "fail"


def test_inventory_pass_alone_is_not_reliance():
    package = _package_with_inventory(_inv(_entry()))
    layers = evaluate_recipient_package(package, {})
    assert layers["native_evidence_inventory"]["status"] == "pass"
    assert layers["recipient_reliance_decision"]["status"] != "pass"


@pytest.mark.parametrize("path", PACKAGES, ids=lambda p: p.name)
def test_packages_without_an_inventory_are_unchanged(path):
    package = json.loads(path.read_text(encoding="utf-8"))
    layers = evaluate_recipient_package(package, {})
    assert "native_evidence_inventory" not in layers
