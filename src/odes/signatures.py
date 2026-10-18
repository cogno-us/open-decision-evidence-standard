"""Detached package authentication: DSSE envelope, Ed25519, keys owned by the recipient.

An optional capability. It needs the ``cryptography`` package (``pip install 'open-decision-evidence-standard[signatures]'``), imported
only when a signature has to be checked. Without it the result is ``unavailable``, never ``pass``. Nothing is fetched: no network, no key
retrieval, no key discovery from the package.

Signed bytes. The payload is the exact canonical byte string of the whole package (every top-level member, including ``package_digest``,
``created_by`` and ``created_at``) under the canonicalization profile the package declares in ``integrity.canonicalization_profile``
(``json-sort-keys-compact-utf8-no-nan`` or ``rfc8785-jcs``). The signature is over the DSSE pre-authentication encoding of the payload type
and those bytes::

    "DSSEv1" SP LEN(payloadType) SP payloadType SP LEN(payload) SP payload

The envelope is detached: it carries ``payloadType`` and ``signatures`` (``keyid``, base64 ``sig``) and no payload, because the verifier
recomputes the payload from the package. An envelope that does carry a ``payload`` is accepted only if it equals the recomputed bytes;
inserting ``payload`` (base64 of the canonical bytes) makes it an ordinary DSSE envelope for any DSSE tool.

Trust. Keys come only from the recipient's ``trusted_keys`` list: ``keyid``, ``algorithm`` (``ed25519``), ``public_key`` (base64, raw 32
bytes) and optionally ``issuer`` (a name the recipient attaches to the key) and ``revoked``. The algorithm belongs to the trusted key, not to
the envelope, so an envelope cannot select a weaker one. Anything in the package that names a key is ignored here.

What a pass means. The package bytes were signed by a key the recipient policy trusts. That authenticates origin only. It does not make the
content true, does not establish authority at decision time or now, and says nothing about when the signature was made (there is no trusted
timestamp). Rotation and revocation are the recipient's: remove or mark a key, and signatures from it stop passing; a key that is trusted
today does not prove authority at a past decision time.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
from typing import Any, Iterable, Mapping

from .canonicalization import UnsupportedCanonicalization, canonical_bytes_for

PAYLOAD_TYPE = "application/vnd.odes.package+json"
SIGNATURE_PROFILE = "odes-dsse-ed25519/0.1.0-draft"
SUPPORTED_ALGORITHMS = ("ed25519",)
MAX_SIGNATURES = 8

LIBRARY_UNAVAILABLE = "signature_library_unavailable"
ENVELOPE_MISSING = "envelope_missing"
ENVELOPE_MALFORMED = "envelope_malformed"
PAYLOAD_TYPE_MISMATCH = "payload_type_mismatch"
PAYLOAD_MISMATCH = "payload_mismatch"
CANONICALIZATION_UNSUPPORTED = "canonicalization_unsupported"
PACKAGE_NOT_CANONICALIZABLE = "package_not_canonicalizable"
TRUSTED_KEYS_MALFORMED = "trusted_keys_malformed"
KEY_NOT_TRUSTED = "key_not_trusted"
KEY_REVOKED = "key_revoked"
ALGORITHM_UNSUPPORTED = "algorithm_unsupported"
SIGNATURE_INVALID = "signature_invalid"
REASON_CODES = frozenset({LIBRARY_UNAVAILABLE, ENVELOPE_MISSING, ENVELOPE_MALFORMED, PAYLOAD_TYPE_MISMATCH, PAYLOAD_MISMATCH,
                          CANONICALIZATION_UNSUPPORTED, PACKAGE_NOT_CANONICALIZABLE, TRUSTED_KEYS_MALFORMED, KEY_NOT_TRUSTED,
                          KEY_REVOKED, ALGORITHM_UNSUPPORTED, SIGNATURE_INVALID})

BOUNDARY = ("A valid signature authenticates the origin of the package bytes under a key the recipient policy trusts. It does not make the "
            "content true, does not establish authority at decision time or now, and carries no trusted signing time.")

_ENVELOPE_MEMBERS = frozenset({"payloadType", "payload", "signatures"})
_SIGNATURE_MEMBERS = frozenset({"keyid", "sig"})
_KEY_REQUIRED = frozenset({"keyid", "algorithm", "public_key"})
_KEY_OPTIONAL = frozenset({"issuer", "revoked"})
_CONFIG_MEMBERS = frozenset({"envelope", "trusted_keys", "allowed_algorithms"})
_TEXT_LIMIT = 256


def _load_ed25519():
    """The ``cryptography`` Ed25519 public key class, or ``None`` when the optional extra is not installed."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except ImportError:
        return None
    return Ed25519PublicKey, InvalidSignature


def ed25519_available() -> bool:
    return _load_ed25519() is not None


def pae(payload_type: str, payload: bytes) -> bytes:
    """DSSE v1 pre-authentication encoding."""
    kind = payload_type.encode("utf-8")
    return b"DSSEv1 " + str(len(kind)).encode("ascii") + b" " + kind + b" " + str(len(payload)).encode("ascii") + b" " + payload


def package_payload(package: Mapping[str, Any]) -> bytes:
    """The exact bytes that are signed. Raises ``UnsupportedCanonicalization`` or ``ValueError``."""
    integrity = package.get("integrity") if isinstance(package, Mapping) else None
    identifier = integrity.get("canonicalization_profile") if isinstance(integrity, Mapping) else None
    return canonical_bytes_for(identifier, package)


def _b64(text: Any) -> bytes | None:
    if not isinstance(text, str) or not text.isascii():
        return None
    try:
        data = base64.b64decode(text, validate=True)
    except (ValueError, binascii.Error):
        return None
    return data if base64.b64encode(data).decode("ascii") == text else None


def sign_package(package: Mapping[str, Any], private_key: Any, keyid: str, *, payload_type: str = PAYLOAD_TYPE, embed_payload: bool = False) -> dict[str, Any]:
    """A detached DSSE envelope over the package. ``private_key`` is any object with ``sign(bytes) -> bytes`` (for example a
    ``cryptography`` Ed25519 private key); this module never reads, stores or derives key material."""
    payload = package_payload(package)
    envelope: dict[str, Any] = {"payloadType": payload_type,
                                "signatures": [{"keyid": keyid, "sig": base64.b64encode(private_key.sign(pae(payload_type, payload))).decode("ascii")}]}
    if embed_payload:
        envelope["payload"] = base64.b64encode(payload).decode("ascii")
    return envelope


def _result(status: str, codes: list[str], texts: list[str], evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    reasons = [f"{code}: {text}" for code, text in zip(codes, texts)] if codes else list(texts)
    return {"status": status, "reasons": reasons, "evidence": {"signature_profile": SIGNATURE_PROFILE, "reason_codes": list(codes), **(evidence or {})}}


def _short(value: Any) -> str:
    return repr(value)[:_TEXT_LIMIT]


def _check_envelope(envelope: Any) -> tuple[list[dict[str, str]], bytes | None] | str:
    """Parsed signature entries and the embedded payload (or ``None``), or a problem text."""
    if not isinstance(envelope, dict):
        return "envelope must be an object"
    unknown = set(envelope) - _ENVELOPE_MEMBERS
    if unknown:
        return f"envelope has unsupported members {sorted(map(str, unknown))}"
    entries = envelope.get("signatures")
    if not isinstance(entries, list) or not entries:
        return "envelope signatures must be a non-empty list"
    if len(entries) > MAX_SIGNATURES:
        return f"envelope carries more than {MAX_SIGNATURES} signatures"
    parsed = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != _SIGNATURE_MEMBERS:
            return "each signature must have exactly keyid and sig"
        keyid = entry["keyid"]
        if not isinstance(keyid, str) or not 0 < len(keyid) <= _TEXT_LIMIT:
            return "signature keyid must be a non-empty string"
        raw = _b64(entry["sig"])
        if raw is None or len(raw) != 64:
            return "signature value must be canonical base64 of 64 bytes"
        parsed.append({"keyid": keyid, "raw": raw})
    embedded = None
    if "payload" in envelope:
        embedded = _b64(envelope["payload"])
        if embedded is None:
            return "embedded payload must be canonical base64"
    return parsed, embedded


def _check_keys(trusted_keys: Any) -> dict[str, dict[str, Any]] | str:
    if not isinstance(trusted_keys, (list, tuple)):
        return "trusted_keys must be a list"
    keys: dict[str, dict[str, Any]] = {}
    for entry in trusted_keys:
        if not isinstance(entry, dict) or not _KEY_REQUIRED <= set(entry) or set(entry) - _KEY_REQUIRED - _KEY_OPTIONAL:
            return "each trusted key needs keyid, algorithm and public_key, and nothing outside keyid, algorithm, public_key, issuer, revoked"
        keyid = entry["keyid"]
        if not isinstance(keyid, str) or not 0 < len(keyid) <= _TEXT_LIMIT:
            return "trusted key keyid must be a non-empty string"
        if keyid in keys:
            return f"trusted key {keyid!r} is listed more than once"
        if "issuer" in entry and not (isinstance(entry["issuer"], str) and 0 < len(entry["issuer"]) <= _TEXT_LIMIT):
            return "trusted key issuer must be a non-empty string"
        if "revoked" in entry and not isinstance(entry["revoked"], bool):
            return "trusted key revoked must be a boolean"
        if entry["algorithm"] in SUPPORTED_ALGORITHMS:
            raw = _b64(entry["public_key"])
            if raw is None or len(raw) != 32:
                return f"trusted key {keyid!r} public_key must be canonical base64 of 32 bytes"
        keys[keyid] = entry
    return keys


def verify_detached_signature(package: Mapping[str, Any], envelope: Any, trusted_keys: Any, *, allowed_algorithms: Iterable[str] | None = None) -> dict[str, Any]:
    """Check a detached DSSE envelope over ``package`` against the recipient's ``trusted_keys``.

    ``pass``: a signature from a trusted, unrevoked key with an allowed algorithm verifies, and no signature from a trusted key fails.
    ``unavailable``: no envelope, or the optional library is not installed. ``unsupported``: a trusted key uses an algorithm that is not
    supported or not allowed. ``fail``: everything else that is wrong, with typed reason codes in ``evidence.reason_codes``.
    """
    if envelope is None:
        return _result("unavailable", [ENVELOPE_MISSING], ["no detached signature envelope was supplied"])
    parsed = _check_envelope(envelope)
    if isinstance(parsed, str):
        return _result("fail", [ENVELOPE_MALFORMED], [parsed])
    entries, embedded = parsed
    if envelope.get("payloadType") != PAYLOAD_TYPE:
        return _result("fail", [PAYLOAD_TYPE_MISMATCH], [f"payload type {_short(envelope.get('payloadType'))} is not {PAYLOAD_TYPE}"])
    try:
        payload = package_payload(package)
    except UnsupportedCanonicalization as exc:
        return _result("fail", [CANONICALIZATION_UNSUPPORTED], [str(exc)])
    except (ValueError, TypeError) as exc:
        return _result("fail", [PACKAGE_NOT_CANONICALIZABLE], [f"package cannot be canonicalized: {exc}"])
    payload_digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    evidence: dict[str, Any] = {"payload_type": PAYLOAD_TYPE, "payload_digest": payload_digest}
    if embedded is not None and embedded != payload:
        return _result("fail", [PAYLOAD_MISMATCH], ["embedded payload is not the canonical package bytes"], evidence)
    keys = _check_keys(trusted_keys)
    if isinstance(keys, str):
        return _result("fail", [TRUSTED_KEYS_MALFORMED], [keys], evidence)
    if allowed_algorithms is None:
        allowed = set(SUPPORTED_ALGORITHMS)
    elif isinstance(allowed_algorithms, (list, tuple, set, frozenset)) and all(isinstance(a, str) for a in allowed_algorithms):
        allowed = set(allowed_algorithms) & set(SUPPORTED_ALGORITHMS)
    else:
        return _result("fail", [TRUSTED_KEYS_MALFORMED], ["allowed_algorithms must be a list of algorithm names"], evidence)

    message = pae(PAYLOAD_TYPE, payload)
    codes: list[str] = []
    texts: list[str] = []
    verified: list[dict[str, Any]] = []
    ignored: list[str] = []
    worst = "pass"
    rank = {"pass": 0, "unavailable": 1, "unsupported": 2, "fail": 3}

    def note(status: str, code: str, text: str) -> None:
        nonlocal worst
        codes.append(code)
        texts.append(text)
        if rank[status] > rank[worst]:
            worst = status

    library = None
    for entry in entries:
        keyid = entry["keyid"]
        key = keys.get(keyid)
        if key is None:
            ignored.append(keyid)
            continue
        if key.get("revoked") is True:
            note("fail", KEY_REVOKED, f"key {keyid!r} is marked revoked by the recipient")
            continue
        algorithm = key["algorithm"]
        if not isinstance(algorithm, str) or algorithm not in SUPPORTED_ALGORITHMS or algorithm not in allowed:
            note("unsupported", ALGORITHM_UNSUPPORTED, f"algorithm {_short(algorithm)} of key {keyid!r} is not supported or not allowed")
            continue
        if library is None:
            library = _load_ed25519() or False
        if library is False:
            note("unavailable", LIBRARY_UNAVAILABLE, "the optional signature library is not installed; install the 'signatures' extra")
            continue
        public_class, invalid_signature = library
        try:
            public_class.from_public_bytes(_b64(key["public_key"])).verify(entry["raw"], message)
        except (invalid_signature, ValueError):
            note("fail", SIGNATURE_INVALID, f"signature by key {keyid!r} does not verify over the package bytes")
            continue
        verified.append({"keyid": keyid, "issuer": key.get("issuer")})

    evidence["ignored_keyids"] = ignored
    if worst == "pass" and not verified:
        known = ", ".join(sorted(ignored)) or "none"
        return _result("fail", [KEY_NOT_TRUSTED], [f"no signature is by a key the recipient policy trusts (signature key ids: {known})"], evidence)
    if worst != "pass":
        return _result(worst, codes, texts, evidence)
    first = verified[0]
    evidence.update({"keyid": first["keyid"], "issuer": first["issuer"], "verified_keyids": [v["keyid"] for v in verified]})
    return {"status": "pass", "reasons": ["package bytes verify under a key the recipient trusts; this authenticates origin only. " + BOUNDARY],
            "evidence": {"signature_profile": SIGNATURE_PROFILE, "reason_codes": [], **evidence}}


def evaluate_detached_authentication(package: Mapping[str, Any], config: Any) -> dict[str, Any]:
    """Recipient policy section ``detached_authentication``: ``envelope``, ``trusted_keys`` and optional ``allowed_algorithms``."""
    if not isinstance(config, dict) or set(config) - _CONFIG_MEMBERS:
        return _result("fail", [TRUSTED_KEYS_MALFORMED], ["policy detached_authentication must be an object with envelope, trusted_keys and allowed_algorithms only"])
    return verify_detached_signature(package, config.get("envelope"), config.get("trusted_keys", []), allowed_algorithms=config.get("allowed_algorithms"))
