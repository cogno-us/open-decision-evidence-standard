# Detached Package Authentication (draft 0.1.0-draft)

An optional way for a recipient to check who produced the exact bytes of a package. It uses a DSSE envelope with an Ed25519 signature, kept outside the package. The package format, its digests and its labels are unchanged.

## What a pass means

A signature that verifies under a key the recipient policy trusts shows that the holder of that key signed these package bytes. That authenticates origin only. It does not make the content true, does not establish authority at decision time or now, and says nothing about when the signature was made: there is no trusted timestamp. It is one layer (`integrity_authentication_checks`); the other layers still decide reliance, and a signature alone never produces `recipient_reliance_decision: pass`.

## Optional dependency

Verification needs the `cryptography` package: `pip install 'open-decision-evidence-standard[signatures]'`. It is imported only when a signature must be checked. Without it the result is `unavailable` (`signature_library_unavailable`), never `pass`. Nothing else in the package depends on it. There is no network access, no key fetching and no key discovery from the package.

## Signed bytes

The payload is the exact canonical byte string of the whole package, every top-level member including `package_digest`, `created_by` and `created_at`, under the canonicalization profile declared in `integrity.canonicalization_profile` (`json-sort-keys-compact-utf8-no-nan` or `rfc8785-jcs`). The signature is over the DSSE v1 pre-authentication encoding:

```
"DSSEv1" SP LEN(payloadType) SP payloadType SP LEN(payload) SP payload
```

`LEN` is the decimal byte length, `SP` is one space. The payload type is `application/vnd.odes.package+json`. A package signed under one canonicalization and relabelled with the other has different bytes and fails.

## Envelope

```
{ "payloadType": "application/vnd.odes.package+json",
  "signatures": [ { "keyid": "<recipient-known key id>", "sig": "<base64, 64 bytes>" } ] }
```

The envelope is detached: it has no `payload`, because the verifier recomputes the bytes from the package. An envelope that carries `payload` (base64 of the canonical bytes) is accepted only if it equals the recomputed bytes, and is then an ordinary DSSE envelope for any DSSE tool. Unknown members, an empty or oversized signature list (at most 8), a missing `keyid` and non-canonical base64 are refused.

## Trusted keys

Keys come only from the recipient policy. Each entry has `keyid`, `algorithm` (`ed25519`), `public_key` (base64, raw 32 bytes) and optionally `issuer` (the name the recipient attaches to the key) and `revoked`. The algorithm belongs to the trusted key, so an envelope cannot select one. Anything inside the package that names or carries a key is ignored. Rotation and revocation are the recipient's: remove a key or set `revoked`, and signatures from it stop passing. A key that is trusted today does not prove authority at a past decision time.

Recipient policy section:

```
"detached_authentication": { "envelope": <envelope>, "trusted_keys": [ ... ], "allowed_algorithms": ["ed25519"] }
```

`allowed_algorithms` is optional and can only narrow the supported set. Unknown members are refused. Without this section the validator behaves as before.

## Results

| Status | Typed reason (`evidence.reason_codes`) |
| --- | --- |
| `pass` | none; `evidence.keyid` and `evidence.issuer` name the verified key. A signature by an untrusted key id is listed in `ignored_keyids` and does not change the result. |
| `unavailable` | `envelope_missing`, `signature_library_unavailable` |
| `unsupported` | `algorithm_unsupported` (a trusted key's algorithm is unknown, or outside `allowed_algorithms`) |
| `fail` | `envelope_malformed`, `payload_type_mismatch`, `payload_mismatch`, `canonicalization_unsupported`, `package_not_canonicalizable`, `trusted_keys_malformed`, `key_not_trusted`, `key_revoked`, `signature_invalid` |

When several signatures are present the worst outcome among signatures by trusted keys wins; a failing signature by a trusted key is not hidden by a valid one.

## Limits of this profile

No trusted timestamp, no transparency log, no key distribution, and no statement about the signer's authority. Test keys in the repository are synthetic.
