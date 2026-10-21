# Capabilities and Version Register

Status: informative. ODES is a draft. The reference tooling is not production-qualified: no deployment, certification or conformance programme rests on it. This page separates what each layer is, and collects every version coordinate in one place.

Recorded at repository commit `1ed3bb4` (main). Each row names where its value is defined, so a change in code or profile text shows up as a mismatch here (a test compares the register with the code and the schema file).

## Capability layers

| Layer | What it is | What it is not |
| --- | --- | --- |
| Base schema | `pder-v0.1`: a closed JSON schema for one decision-evidence record (`schema/pder-v0.1.schema.json`). Every substantive field is an issuer assertion. Draft. | Not a verification result. A schema-valid record is not verified, trusted or suitable for reliance. It has no signature value and no unknown value for boolean fields. |
| Package envelope | `odes_decision_evidence_export_package` `0.1.0`: the record plus `profile`, `integrity`, `provenance` and `package_digest`. Integrity is a content digest over the canonical bytes of the covered members. | A digest binds content; it does not authenticate an issuer. Top-level members outside the digest are listed in [recipient validation](recipient-validation.md). |
| Cognous profile | `odes_cognous_stack_export_*`: export from retained Cognous Manifest, Control Plane and Replay material, and the recipient checks that re-derive the summary from the retained sources. | Not part of the base ODES schema. Source-content consistency is not authentication of the producer data. The reference validator evaluates these profiles and the generic recipient profile below: a package under any other profile gets profile conformance `unsupported`. |
| Generic recipient profile | `odes_generic_recipient_0_1`: a package profile with a closed provenance (limits, unsupported semantics, explicit restriction semantics, optional native evidence inventory). Needs no Cognous component, and carries the native evidence inventory that Cognous profile 0.2 cannot. | Not a Cognous check: no Replay reconstruction runs or is claimed. Not authentication: a detached signature is a separate optional layer, and neither is reliance. |
| Accepted source qualification | Exact producer tuples (Manifest, Control Plane, runtime, Replay) accepted per profile generation, recorded in `odes.common` and in the qualification repository. Components never mix across generations. | Not a selection. A generation that is accepted is retained evidence; it is not the selected release. |
| Selected release | The integration selected by the [hub component lock](https://github.com/cogno-us/cognous-open-control-stack/blob/main/component-lock.json). | A merge here does not change the selection and no release is declared by this repository. |

## Version coordinates

| Coordinate | Value | Defined in |
| --- | --- | --- |
| Narrative document | `0.2` (draft) | `odes.common.DOCUMENT_VERSION`, [profile 0.2](../profiles/cognous-stack-export-0.2.md) |
| Base schema | `pder-v0.1` (schema version `0.1`) | `schema/pder-v0.1.schema.json`, `odes.common.SCHEMA_NAME` |
| Package envelope | `0.1.0` | `odes.common.PACKAGE_VERSION` |
| Profile identifier, historical | `odes_cognous_stack_export_0_1`, version `odes-cognous-stack-export-0.1.0` | `odes.common.PROFILE_ID`, `PROFILE_VERSION` |
| Profile identifier, producer 2.0.0 | `odes_cognous_stack_export_0_2` | `odes.common.PROFILE_V2_ID` |
| Profile identifier, explicit restrictions | `odes_cognous_stack_export_0_2_restrictions`; version is the generation's version plus `+restriction-semantics-1` | `odes.common.PROFILE_V2_RESTRICTIONS_ID`, `RESTRICTION_VERSION_SUFFIX`, [profile](../profiles/cognous-stack-export-0.2-restrictions.md) |
| Profile identifier, generic recipient | `odes_generic_recipient_0_1`, version `odes-generic-recipient-0.1.0-draft`; not a Cognous profile | `odes.generic_profile.GENERIC_PROFILE_ID`, `GENERIC_PROFILE_VERSION`, [profile](../profiles/generic-recipient-0.1.md) |
| Transformation / profile version for `odes_cognous_stack_export_0_2` | `odes-cognous-stack-export-0.2.0`, with later generations below | `odes.common.PROFILE_V2_VERSION` |
| Python package | `0.2.0` | `pyproject.toml` |
| Producer interface | `2.0.0` (historical producers `1.0.0` and legacy unversioned) | [profile 0.2 compatibility table](../profiles/cognous-stack-export-0.2.md) |
| Canonicalization, legacy | `json-sort-keys-compact-utf8-no-nan` (every historical digest uses it) | `odes.canonicalization.LEGACY_CANONICALIZATION_PROFILE` |
| Canonicalization, interoperable | `rfc8785-jcs` (a separate identifier; the legacy one is never relabelled) | `odes.canonicalization.JCS_CANONICALIZATION_PROFILE` |
| Native evidence inventory | `0.1.0-draft` | [native evidence inventory](native-evidence-inventory.md) |
| Detached package authentication | `odes-dsse-ed25519/0.1.0-draft` (optional extra `signatures`) | [detached authentication](detached-authentication.md), `odes.signatures.SIGNATURE_PROFILE` |
| Contract drafts | `0.1.0-draft` for every contract | `contracts/*/README.md` |

Seven coordinates identify a package in practice (narrative, base schema, package envelope, profile identifier, transformation or profile version, Python package, producer interface); the canonicalization label is an eighth that decides how a digest is computed. A narrative version alone does not identify what a recipient will evaluate.

## Profile generations accepted for producer 2.0.0

All of these use `odes_cognous_stack_export_0_2`. Each version string selects one exact tuple, keyed by its Control Plane revision. The later versions are candidate generations that stay accepted as retained evidence; none is selected by being listed.

| Profile version | Control Plane | Replay | Notes |
| --- | --- | --- | --- |
| `odes-cognous-stack-export-0.2.0` | `248d8996`, `2ea9528e` | `043830b5`, `274543f1` | Producer 2.0.0 baseline. |
| `odes-cognous-stack-export-0.2.1` | `d3dadee7` | `459e4ba6` | Merged producer pair. |
| `odes-cognous-stack-export-0.2.2-refusal-candidate` | `c7f122ba` | `83fbaf2a` | Typed refusal evidence. |
| `odes-cognous-stack-export-0.2.3-security-runtime-candidate` | `996baeb4` | `3601fb21` | |
| `odes-cognous-stack-export-0.2.4-security-runtime-f5b-candidate` | `a34c3dc2` | `def0ee0f` | |
| `odes-cognous-stack-export-0.2.5-security-runtime-p4-candidate` | `26a7e659` | `9aab3f6c` | |
| `odes-cognous-stack-export-0.2.6-security-runtime-p2-candidate` | `0a41faa9` | `028f63d1` | |

## Content digests

| Artifact | SHA-256 |
| --- | --- |
| `schema/pder-v0.1.schema.json` | `7d29c793f6cb16b574a156ed80d77f3817ab7eb33988ed469e4b7d5e14f60771` |

A version label alone is not proof of identical content. The repository's decisions record reports that draft contract content can differ across repositories under an unchanged `0.1.0-draft` label. Compare digests, not labels, when a consumer vendors a contract or the schema; the content and pin hashes are reconciled for all consumers at the first contract freeze. This register does not re-vendor or freeze anything.

## Recipient policies

A recipient policy lists the exact profile identifiers it accepts in `supported_profiles`. The default is the historical profile only. A policy that lists only one id does not accept a newer one: see `examples/policies/recipient-audit-policy.json` (historical) and `examples/policies/recipient-audit-policy-producer-v2.json` (`odes_cognous_stack_export_0_2`, for the `examples/producer-v2` packages).
