# ODES Generic Recipient Profile 0.1

Status: draft implementation profile. Contract labels are unchanged (`0.1.0-draft`). The base schema `pder-v0.1` and the package envelope `0.1.0` are unchanged.

Profile identifier: `odes_generic_recipient_0_1`. Profile version: `odes-generic-recipient-0.1.0-draft`.

This is a package profile that is not tied to the Cognous export profiles. A producer that is not part of the Cognous stack can use it, and a recipient can evaluate such a package with nothing but this repository: the Cognous Replay distribution is neither needed nor consulted. Recipients must list the identifier in `supported_profiles`; a policy that lists only another profile does not accept it, and relabelling a package between this profile and a Cognous profile fails profile conformance.

The existing profiles are not changed. Profile 0.2 and its restrictions variant keep their members, digests and checks; a Cognous 0.2 package cannot carry a native evidence inventory (its Replay re-export comparison would see an extra provenance member), and that stays so. The inventory is carried by this profile instead.

## Package

The ordinary package envelope: `package_type`, `package_version`, `created_by`, `created_at`, `record`, `profile`, `integrity`, `provenance`, `package_digest`. No other top-level member is accepted.

- `profile`: `implementation_profile` = the identifier, `implementation_profile_version` = the version above, `schema_name` = `pder-v0.1`, `schema_version` = `0.1`. The record's `verification.conformance_profile` must equal the identifier.
- `integrity`: a SHA-256 content digest under either canonicalization profile, `json-sort-keys-compact-utf8-no-nan` (legacy) or `rfc8785-jcs`. The package declares which; the digest is meaningful only together with it.
- `provenance` is closed. Required: `limits` (list of text), `unsupported_semantics` (list of text), `restriction_semantics`. Optional: `native_evidence_inventory`. Any other member is refused, because nothing defines its meaning.

## Restriction semantics

The profile always uses the explicit restriction semantics of [profile 0.2 restrictions](cognous-stack-export-0.2-restrictions.md): `restriction_semantics` records the state of `restricted_use_flag`, `prohibited_use_flag` and `jurisdiction`. An unknown value is recorded as the conservative base boolean `true` (or the text `unknown`) and is never `false`; the mandatory limitation text (`odes.common.RESTRICTION_UNKNOWN_LIMIT`) must then be in `limits`. An explicit `false` needs a source record (`record_id`, `record_hash`). The consumption layer fails on a missing or unsupported `restriction_semantics`, a base boolean that does not match its state, an unknown value, a missing limitation or an unattributable `false`. The builder (`odes.generic_profile.build_generic_package`) adds the limitation and refuses an unattributable `false`.

## Native evidence inventory

`provenance.native_evidence_inventory` follows [native evidence inventory](../docs/native-evidence-inventory.md) rules unchanged (separate version, byte-preserving entries, nothing fetched). The package digest binds it. The inventory does not use the JCS profile. Input budgets apply to the whole package: with the default budgets an embedded artifact is limited by the string budget (65,536 characters of base64) and the package by 1 MiB; a larger artifact is referenced by locator and handed to the recipient out of band. Over-budget input is refused with `budget_exceeded`.

## Recipient evaluation

Layers: schema validity, declared profile conformance, package content integrity, integrity and authentication (optionally a [detached signature](../docs/detached-authentication.md)), historical authority, authority status and freshness, consumption conditions and, when present, the native evidence inventory. There is no `replay_semantic_consistency` layer: the profile carries no Cognous retained sources, so that check does not apply, is not run and is not reported as passed. `declared_profile_conformance.evidence.cognous_replay_reconstruction` records `not_applicable`, and a boundary note says so. A package under a Cognous profile whose Replay check cannot run still gets `unavailable` or `unsupported` for that layer, as before.

`recipient_reliance_decision` is `pass` only when every evaluated layer passes. A valid signature authenticates origin only; it never produces reliance by itself.

## Reproducing the bytes in another language

`conformance/generic-profile-vectors.json` lists, for each canonicalization profile, a synthetic package, the SHA-256 of its canonical bytes, the SHA-256 of the DSSE pre-authentication encoding, the public key and a detached envelope. An independent implementation needs only JSON serialization (legacy: sorted keys, compact separators, UTF-8 without ASCII escaping; or RFC 8785), SHA-256, base64 and Ed25519.
