"""Detached package authentication (DSSE, Ed25519): optional extra, recipient-owned keys, fail closed."""
import base64
import builtins
import hashlib
import json
import socket
import tomllib
from copy import deepcopy
from pathlib import Path

import pytest

from odes import signatures
from odes.canonicalization import JCS_CANONICALIZATION_PROFILE, canonical_bytes_for, digest_for
from odes.common import CANONICALIZATION_PROFILE
from odes.recipient_validator import evaluate_recipient_package

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = json.loads((ROOT / "examples" / "producer-v2" / "lost_ack.package.json").read_text(encoding="utf-8"))
SEED = bytes(range(32))  # synthetic test key material only
OTHER_SEED = bytes(range(32, 64))


def _crypto():
    return pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519", exc_type=ImportError)


def _private(seed=SEED):
    return _crypto().Ed25519PrivateKey.from_private_bytes(seed)


def _public_b64(seed=SEED):
    _crypto()
    from cryptography.hazmat.primitives import serialization
    raw = _private(seed).public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def _trusted(keyid="issuer-key-1", seed=SEED, **kw):
    entry = {"keyid": keyid, "algorithm": "ed25519", "public_key": _public_b64(seed), "issuer": "example-issuer/example-system"}
    entry.update(kw)
    return [entry]


def _jcs_package():
    package = deepcopy(PACKAGE)
    package["integrity"]["canonicalization_profile"] = JCS_CANONICALIZATION_PROFILE
    core = {"record": package["record"], "profile": package["profile"]}
    package["integrity"]["value"] = digest_for(JCS_CANONICALIZATION_PROFILE, core)
    material = {k: package[k] for k in ("record", "profile", "integrity", "provenance")}
    package["package_digest"] = digest_for(JCS_CANONICALIZATION_PROFILE, material)
    return package


def _sign(package, keyid="issuer-key-1", seed=SEED, **kw):
    return signatures.sign_package(package, _private(seed), keyid, **kw)


def _codes(result):
    return result["evidence"]["reason_codes"]


# ---------------------------------------------------------------- valid producer controls

@pytest.mark.parametrize("package", [PACKAGE, "jcs"], ids=["legacy", "rfc8785-jcs"])
def test_valid_signature_under_the_declared_canonicalization_passes(package):
    package = _jcs_package() if package == "jcs" else deepcopy(package)
    envelope = _sign(package)
    result = signatures.verify_detached_signature(package, envelope, _trusted())
    assert result["status"] == "pass", result
    assert result["evidence"]["keyid"] == "issuer-key-1"
    assert result["evidence"]["issuer"] == "example-issuer/example-system"
    text = " ".join(result["reasons"])
    assert "origin" in text and "does not" in text  # authenticates origin, does not make the content true


def test_payload_is_the_exact_canonical_package_bytes_and_envelope_is_dsse_shaped():
    for package, name in ((deepcopy(PACKAGE), CANONICALIZATION_PROFILE), (_jcs_package(), JCS_CANONICALIZATION_PROFILE)):
        envelope = _sign(package)
        assert set(envelope) == {"payloadType", "signatures"}  # detached: the payload is recomputed, not carried
        assert envelope["payloadType"] == signatures.PAYLOAD_TYPE
        assert signatures.package_payload(package) == canonical_bytes_for(name, package)
        assert set(envelope["signatures"][0]) == {"keyid", "sig"}


def test_embedded_payload_equal_to_the_package_bytes_is_accepted_and_standard_dsse_can_verify_it():
    package = deepcopy(PACKAGE)
    envelope = _sign(package, embed_payload=True)
    assert base64.b64decode(envelope["payload"], validate=True) == signatures.package_payload(package)
    assert signatures.verify_detached_signature(package, envelope, _trusted())["status"] == "pass"


def test_independent_second_implementation_reproduces_bytes_and_signature():
    """Pre-authentication encoding and verification written out here, not imported from odes."""
    _crypto()
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    package = deepcopy(PACKAGE)
    envelope = _sign(package)
    body = json.dumps(package, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    kind = envelope["payloadType"].encode("ascii")
    pae = b"DSSEv1 " + str(len(kind)).encode() + b" " + kind + b" " + str(len(body)).encode() + b" " + body
    public = Ed25519PublicKey.from_public_bytes(base64.b64decode(_trusted()[0]["public_key"]))
    public.verify(base64.b64decode(envelope["signatures"][0]["sig"]), pae)  # raises if different
    assert signatures.pae(envelope["payloadType"], body) == pae


# ---------------------------------------------------------------- fail closed

def test_wrong_key_fails():
    package = deepcopy(PACKAGE)
    result = signatures.verify_detached_signature(package, _sign(package, seed=OTHER_SEED), _trusted())
    assert result["status"] == "fail" and "signature_invalid" in _codes(result)


def test_key_not_in_recipient_trust_set_fails_and_package_cannot_supply_trust():
    package = deepcopy(PACKAGE)
    envelope = _sign(package, keyid="package-chosen-key")
    result = signatures.verify_detached_signature(package, envelope, _trusted())
    assert result["status"] == "fail" and "key_not_trusted" in _codes(result)
    assert signatures.verify_detached_signature(package, envelope, [])["status"] == "fail"
    package["record"]["verification"]["issuer_key_reference"] = "package-chosen-key"
    package["provenance"]["trusted_keys"] = _trusted("package-chosen-key")
    result = signatures.verify_detached_signature(package, _sign(package, keyid="package-chosen-key"), _trusted())
    assert result["status"] == "fail" and "key_not_trusted" in _codes(result)


def test_wrong_payload_type_fails_including_a_relabelled_envelope():
    package = deepcopy(PACKAGE)
    envelope = _sign(package, payload_type="application/vnd.example.other+json")
    result = signatures.verify_detached_signature(package, envelope, _trusted())
    assert result["status"] == "fail" and "payload_type_mismatch" in _codes(result)
    envelope["payloadType"] = signatures.PAYLOAD_TYPE  # relabel: the signed pre-authentication encoding differs
    result = signatures.verify_detached_signature(package, envelope, _trusted())
    assert result["status"] == "fail" and "signature_invalid" in _codes(result)


@pytest.mark.parametrize("path", [("created_by",), ("created_at",), ("package_digest",), ("record", "decision_id"),
                                  ("profile", "implementation_profile_version"), ("provenance", "limits"),
                                  ("integrity", "value")])
def test_any_changed_package_byte_fails(path):
    package = deepcopy(PACKAGE)
    envelope = _sign(package)
    target = package
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = "changed" if not isinstance(target[path[-1]], list) else target[path[-1]] + ["changed"]
    result = signatures.verify_detached_signature(package, envelope, _trusted())
    assert result["status"] == "fail" and "signature_invalid" in _codes(result)


def test_an_added_top_level_member_fails():
    package = deepcopy(PACKAGE)
    envelope = _sign(package)
    package["extra"] = 1
    assert signatures.verify_detached_signature(package, envelope, _trusted())["status"] == "fail"


def test_relabelling_the_canonicalization_fails():
    package = deepcopy(PACKAGE)
    envelope = _sign(package)
    relabelled = _jcs_package()
    result = signatures.verify_detached_signature(relabelled, envelope, _trusted())
    assert result["status"] == "fail" and "signature_invalid" in _codes(result)


def test_embedded_payload_that_differs_from_the_package_fails():
    package = deepcopy(PACKAGE)
    envelope = _sign(package, embed_payload=True)
    envelope["payload"] = base64.b64encode(b"{}").decode()
    result = signatures.verify_detached_signature(package, envelope, _trusted())
    assert result["status"] == "fail" and "payload_mismatch" in _codes(result)


@pytest.mark.parametrize("algorithm", ["rsa-pss-sha256", "ecdsa-p256-sha256", "ed448", "none", "", None, 7])
def test_unknown_algorithm_in_the_trust_configuration_is_unsupported(algorithm):
    package = deepcopy(PACKAGE)
    result = signatures.verify_detached_signature(package, _sign(package), _trusted(algorithm=algorithm))
    assert result["status"] == "unsupported" and "algorithm_unsupported" in _codes(result)


def test_algorithm_outside_the_recipient_allow_list_is_unsupported():
    package = deepcopy(PACKAGE)
    result = signatures.verify_detached_signature(package, _sign(package), _trusted(), allowed_algorithms=[])
    assert result["status"] == "unsupported" and "algorithm_unsupported" in _codes(result)


def test_revoked_key_fails_even_with_a_valid_signature():
    package = deepcopy(PACKAGE)
    result = signatures.verify_detached_signature(package, _sign(package), _trusted(revoked=True))
    assert result["status"] == "fail" and "key_revoked" in _codes(result)


def test_missing_envelope_is_unavailable():
    assert signatures.verify_detached_signature(deepcopy(PACKAGE), None, [])["status"] == "unavailable"
    assert signatures.verify_detached_signature(deepcopy(PACKAGE), {}, [])["status"] == "fail"


@pytest.mark.parametrize("mutate", [
    lambda e: e.update(unknown_member=1),
    lambda e: e.update(signatures=[]),
    lambda e: e.update(signatures="x"),
    lambda e: e["signatures"][0].pop("keyid"),
    lambda e: e["signatures"][0].update(sig="not base64!"),
    lambda e: e["signatures"][0].update(sig=base64.b64encode(b"short").decode()),
    lambda e: e["signatures"][0].update(extra=1),
    lambda e: e["signatures"].extend(deepcopy(e["signatures"]) * 9),
    lambda e: e.pop("payloadType"),
])
def test_malformed_envelope_fails(mutate):
    package = deepcopy(PACKAGE)
    envelope = _sign(package)
    mutate(envelope)
    result = signatures.verify_detached_signature(package, envelope, _trusted())
    assert result["status"] == "fail"


@pytest.mark.parametrize("keys", [[{"keyid": "issuer-key-1", "algorithm": "ed25519", "public_key": "AAAA"}],
                                  [{"keyid": "issuer-key-1", "algorithm": "ed25519"}],
                                  "not a list", [{"keyid": "k", "algorithm": "ed25519", "public_key": "x", "unknown": 1}]])
def test_malformed_trust_configuration_fails(keys):
    package = deepcopy(PACKAGE)
    result = signatures.verify_detached_signature(package, _sign(package), keys)
    assert result["status"] == "fail" and result["status"] != "pass"


def test_duplicate_keyid_in_the_trust_set_fails():
    package = deepcopy(PACKAGE)
    keys = _trusted() + _trusted(seed=OTHER_SEED)
    assert signatures.verify_detached_signature(package, _sign(package), keys)["status"] == "fail"


def test_additional_signature_from_an_untrusted_key_is_recorded_but_does_not_change_a_valid_result():
    package = deepcopy(PACKAGE)
    envelope = _sign(package)
    envelope["signatures"].append(_sign(package, keyid="someone-else", seed=OTHER_SEED)["signatures"][0])
    result = signatures.verify_detached_signature(package, envelope, _trusted())
    assert result["status"] == "pass"
    assert "someone-else" in result["evidence"]["ignored_keyids"]


def test_a_failing_signature_from_a_trusted_key_is_not_masked_by_a_valid_one():
    package = deepcopy(PACKAGE)
    envelope = _sign(package)
    bad = _sign(package, keyid="issuer-key-2", seed=OTHER_SEED)["signatures"][0]
    envelope["signatures"].append(bad)
    keys = _trusted() + _trusted("issuer-key-2", seed=SEED)  # key 2 is trusted with a key that did not sign
    assert signatures.verify_detached_signature(package, envelope, keys)["status"] == "fail"


def test_unsupported_canonicalization_declaration_fails():
    package = deepcopy(PACKAGE)
    envelope = _sign(package)
    package["integrity"]["canonicalization_profile"] = "unknown-profile"
    result = signatures.verify_detached_signature(package, envelope, _trusted())
    assert result["status"] in {"fail", "unsupported"} and "canonicalization_unsupported" in _codes(result)


# ---------------------------------------------------------------- optional extra

def _block_cryptography(monkeypatch):
    real = builtins.__import__

    def guard(name, *args, **kwargs):
        if name == "cryptography" or name.startswith("cryptography."):
            raise ImportError("cryptography is not installed")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guard)


def test_absent_library_is_unavailable_never_pass(monkeypatch):
    package = deepcopy(PACKAGE)
    envelope = _sign(package)  # signed while the library is present
    keys = _trusted()
    _block_cryptography(monkeypatch)
    assert signatures.ed25519_available() is False
    result = signatures.verify_detached_signature(package, envelope, keys)
    assert result["status"] == "unavailable" and "signature_library_unavailable" in _codes(result)


def test_absent_library_does_not_break_the_rest_of_the_package(monkeypatch):
    _block_cryptography(monkeypatch)
    layers = evaluate_recipient_package(deepcopy(PACKAGE), {})
    assert "schema_validity" in layers and layers["recipient_reliance_decision"]["status"] != "pass"


def test_signature_support_is_an_optional_extra_not_a_dependency():
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert not any("cryptography" in dep for dep in meta["dependencies"])
    assert any("cryptography" in dep for dep in meta["optional-dependencies"]["signatures"])


# ---------------------------------------------------------------- no network, no key fetching

def test_verification_opens_no_network_connection(monkeypatch):
    package = deepcopy(PACKAGE)
    envelope = _sign(package)

    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    assert signatures.verify_detached_signature(package, envelope, _trusted())["status"] == "pass"
    package["record"]["verification"]["issuer_key_reference"] = "https://keys.example.invalid/key"
    assert signatures.verify_detached_signature(package, envelope, _trusted())["status"] == "fail"


def test_module_has_no_network_or_key_fetching_imports():
    source = (ROOT / "src" / "odes" / "signatures.py").read_text(encoding="utf-8")
    for name in ("urllib", "http", "socket", "requests", "ssl", "subprocess", "ftplib"):
        assert f"import {name}" not in source and f"from {name}" not in source


# ---------------------------------------------------------------- recipient validator integration

def test_validator_without_the_policy_section_is_unchanged():
    layers = evaluate_recipient_package(deepcopy(PACKAGE), {})
    assert layers["integrity_authentication_checks"]["status"] == "unavailable"


def test_validator_reports_a_valid_detached_signature_as_origin_authentication_only():
    package = deepcopy(PACKAGE)
    policy = {"detached_authentication": {"envelope": _sign(package), "trusted_keys": _trusted()}}
    layers = evaluate_recipient_package(package, policy)
    assert layers["integrity_authentication_checks"]["status"] == "pass"
    assert layers["integrity_authentication_checks"]["evidence"]["keyid"] == "issuer-key-1"
    # A signature alone is never reliance: authority, status, consumption and the other layers still decide.
    assert layers["recipient_reliance_decision"]["status"] == "fail"
    assert "integrity_authentication_checks" not in layers["recipient_reliance_decision"]["evidence"]["blocking_layers"]


@pytest.mark.parametrize("mutate", [
    lambda p, pol: pol["detached_authentication"].update(trusted_keys=_trusted(seed=OTHER_SEED)),
    lambda p, pol: p.update(created_by="someone-else"),
    lambda p, pol: pol["detached_authentication"].update(envelope=None),
    lambda p, pol: pol["detached_authentication"].update(unknown_member=1),
    lambda p, pol: pol.update(detached_authentication="not an object"),
])
def test_validator_does_not_pass_authentication_on_any_failure(mutate):
    package = deepcopy(PACKAGE)
    policy = {"detached_authentication": {"envelope": _sign(package), "trusted_keys": _trusted()}}
    mutate(package, policy)
    layers = evaluate_recipient_package(package, policy)
    assert layers["integrity_authentication_checks"]["status"] != "pass"
    assert layers["recipient_reliance_decision"]["status"] != "pass"


# ---------------------------------------------------------------- documentation

def test_documentation_lists_every_reason_code_and_the_register_names_the_profile():
    doc = (ROOT / "docs" / "detached-authentication.md").read_text(encoding="utf-8")
    for code in signatures.REASON_CODES:
        assert f"`{code}`" in doc, code
    assert signatures.PAYLOAD_TYPE in doc and "origin only" in doc
    assert signatures.SIGNATURE_PROFILE in (ROOT / "docs" / "capabilities-and-versions.md").read_text(encoding="utf-8")
