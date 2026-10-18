# Native Evidence Inventory (draft 0.1.0-draft)

A package-level inventory of opaque artifacts that other systems produced in their own formats. ODES carries and checks the bytes. It does not interpret, normalize or re-serialize them, so a native signature over those bytes stays checkable by its own verifier.

The inventory is separately versioned (`inventory_version`), is optional, and changes no existing profile. Packages exported under the existing profiles carry none. Where a package carries one, it sits at `provenance.native_evidence_inventory`, so the package digest binds it: changing an entry, its relation or its bytes changes the package digest.

## Format

```
{
  "inventory_type": "odes_native_evidence_inventory",
  "inventory_version": "0.1.0-draft",
  "artifacts": [ <entry>, ... ]
}
```

Entry members (all others are refused):

| Member | Meaning |
|---|---|
| `artifact_id` | Unique within the inventory; `[A-Za-z0-9._:-]`, 1 to 128 characters. |
| `source_format`, `source_format_version` | The artifact's own format and version, as the producer names them. |
| `relation` | One of `decision_evidence`, `authority_evidence`, `execution_evidence`, `status_evidence`, `attestation`, `supporting_context`. |
| `media_type` | Lower-case `type/subtype`. |
| `byte_length` | Length of the original bytes. |
| `digest_algorithm`, `digest_value` | `sha256` and 64 lower-case hex digits, computed over the original bytes with no canonicalization. Other algorithms are `unsupported`. |
| `bytes_base64` or `locator` | Exactly one. Canonical base64 of the exact bytes, or an opaque `{kind, reference}` that is never dereferenced. |
| `required` (optional) | Producer's statement that the artifact is required. The recipient policy can also require it. |
| `producer_assertions` (optional) | A bounded object of the producer's own claims (for example a "verified" field in the artifact's ecosystem). Kept apart and reported as `not_evaluated`. |
| `limitations`, `native_signature_scope`, `lineage` (optional) | Descriptive fields preserved with the entry. |

## Outcomes

- Bytes present and matching length and digest: `pass` for that entry (content binding only).
- Digest or length mismatch, malformed entry, duplicate ids, unknown members, over-limit input: `fail`.
- Required artifact with a locator only, or absent: `unavailable`. Reliance is blocked. An optional artifact that is unavailable is listed under `unavailable_optional` and does not hide.
- Digest algorithm not supported: `unsupported`.
- Bytes for a locator entry can only be handed in by the recipient (the `supplied_artifacts` argument, or `native_evidence.supplied_artifacts` in the policy as base64). They are checked against the digest. If both an embedded copy and a supplied copy exist they must be identical.

## Native verification

Native verification is recipient-generated. The recipient policy supplies reports under `native_evidence.verification_reports`; each names the artifact, the artifact digest it verified, the verifier id and version, the recipient policy id and a status (`pass`, `fail`, `unavailable`, `unsupported`, `not_evaluated`). A report whose digest differs from the entry digest fails. `native_evidence.required_native_verification` lists artifacts that need a passing report: no report is `unavailable`, and `unsupported` stays `unsupported`. A producer's own "verified" field is never read as a result. A failing report is kept as a failure even when the recipient did not require it. A native verdict concerns the artifact's own format and keys; it is not a decision authority verdict.

## Recipient policy section

`native_evidence`: `required_artifacts` (list of `{artifact_id, relation}`), `required_native_verification` (list of ids), `verification_reports`, `supplied_artifacts`, and optional lower limits `max_entries`, `max_artifact_bytes`, `max_total_bytes`. Unknown members are refused.

## Boundaries and limits

- No URL fetching or redirects, no local file reads, no plugin or code loading, no trust-store changes. A later retrieval adapter needs its own network and size policy.
- Defaults: 256 entries, 8 MiB per artifact, 32 MiB declared total, string and producer-assertion bounds. Policy can only lower them. Limits are checked before base64 decoding.
- A passing inventory layer shows that the carried bytes match their digests. It does not authenticate the issuer of the package or of an artifact, does not make the artifact's content true, and is never reliance by itself.
- The inventory does not use the JCS canonicalization profile, and nothing in it depends on one.
