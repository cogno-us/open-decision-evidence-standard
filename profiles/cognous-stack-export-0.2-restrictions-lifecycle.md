# Cognous Stack Export 0.2, explicit restrictions with an attributed lifecycle assertion

Status: **PROPOSED, DEVELOPMENT ONLY, UNQUALIFIED, NOT ADOPTED.** Opt-in. Not part of any default policy, not selected by any lock, and not approved for integration. Contract labels are unchanged (`0.1.0-draft`); the base schema `pder-v0.1` is unchanged.

Profile id: `odes_cognous_stack_export_0_2_restrictions_lifecycle_0_1`. Profile version: the generation's profile version of [profile 0.2](cognous-stack-export-0.2.md), then `+restriction-semantics-1`, then `+lifecycle-semantics-1`. Recipients must list this exact id in `supported_profiles`; the default list stays the historical profile only. A policy listing `odes_cognous_stack_export_0_2` or `odes_cognous_stack_export_0_2_restrictions` does not accept it, and relabelling a package between ids fails profile conformance.

Every existing profile id is unchanged. Calling the exporter without `lifecycle_assertion` produces the same package content and digests as before (`record.status.freshness` stays `unknown` for the Cognous CP-2 generation). The exporter selects this profile only when called with `restriction_semantics="explicit"` **and** `lifecycle_assertion=...`, and only for producer-2.0.0 generations.

## What the lifecycle value is, and is not

`record.status.freshness` is defined by the base schema as **issuer-reported**. This profile lets the exporter's caller (the issuer) state it, with attribution, instead of leaving it `unknown`. The value is an **attributed issuer assertion bound to the record and the retained sources**. It is not recipient status evidence, does not establish present validity, and does not replace the independently supplied recipient `status_inputs`. Copying the assertion into the Replay-semantic re-export proves reconstruction consistency only; it is not independent evidence that the assertion is true.

## Input

`lifecycle_assertion` is a closed object, never defaulted:

| Member | Rule |
| --- | --- |
| `freshness` | one of `current`, `stale`, `expired`, `pending_revalidation` (`unknown` is not an assertion; `revoked` and `superseded` are not expressible here because they require evidence members) |
| `asserted_by` | `{organization_id, system_id, actor_id}`, non-empty strings; `organization_id` and `system_id` must equal the record `issuer` |
| `asserted_at` | RFC 3339 instant with an offset; not before the retained decision time; not in the future at export |
| `source` | `{reference}`, a non-empty string naming the assertion's source |

The exporter refuses a missing or malformed member, a combination with lifecycle state already carried in the bundle metadata, and use without explicit restriction semantics. `status` is exported as `{freshness: <value>, superseded: false, revoked: false}`.

## Package material

`provenance.lifecycle_semantics` (covered by `package_digest`; `record.status` is covered by both digests) carries `semantics_version` (`lifecycle-semantics-1`), the four input members, and `bound_to` = `{decision_id, reconstruction_bundle_digest, manifest_digest}` computed by the exporter from the record and the retained sources. `provenance.limits` must contain the limitation text `odes.common.LIFECYCLE_ISSUER_ASSERTED_LIMIT`.

## Recipient evaluation

`declared_profile_conformance` fails when `lifecycle_semantics` is missing or unsupported, has unexpected members, is unattributed or malformed, names someone other than the record issuer, predates the decision, differs from `record.status`, is not bound to the record decision and retained source digests, or the mandatory limitation is missing. The restriction checks of [the restrictions profile](cognous-stack-export-0.2-restrictions.md) apply unchanged. `replay_semantic_consistency` re-exports the retained sources under explicit restriction semantics **with the package's own lifecycle assertion** and compares the full material, so a record or provenance edited out of step with the assertion mismatches.

The `authority_status_and_freshness` layer is unchanged: a record-side `unknown`, `stale`, `expired` or `pending_revalidation` freshness always fails it, and a record-side `current` is never sufficient. Independently supplied recipient `status_inputs`, a trusted issuer, a recipient clock and authentication remain mandatory for any `pass`.

## Known limits

An issuer who rewrites the assertion and the record consistently and reseals the package is not detected by the Replay layer; that is caught only by a recipient-held trusted digest anchor or detached signature. Who may assert `current` for a real deployment is **unassigned**; the first proof uses a labelled synthetic test authority. No Replay, Control Plane, Pack or Governed Exchange change is part of this profile.
