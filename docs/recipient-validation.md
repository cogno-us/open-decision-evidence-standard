# Recipient Validation Reference Path

Status: Informative reference behavior for exported ODES packages.

The recipient validator consumes only an exported package and explicit recipient policy/status inputs. It does not access producer databases, call private runtime services, execute workflows, renew authority or mutate destination state.

## Validation layers

The reference validator returns separate results for:

1. `schema_validity` — validates the embedded `record` against `pder-v0.1`.
2. `declared_profile_conformance` — checks package version, implementation-profile version and the profile declared by the package and record.
3. `package_content_integrity` — validates supported content-digest metadata, canonicalization profile and the complete material package digest over record, profile, integrity metadata and provenance.
4. `integrity_authentication_checks` — evaluates issuer-authentication evidence separately from content integrity. A public hash is not issuer authentication.
5. `historical_authority_assertions` — distinguishes record self-assertions from externally configured evidence about authority at decision time.
6. `authority_status_and_freshness` — evaluates present authority, revocation, supersession, freshness and expiry against recipient policy inputs and an explicit recipient evaluation time.
7. `consumption_conditions` — checks relying party and purpose.
8. `recipient_reliance_decision` — recipient policy result.

Each layer may return `pass`, `fail`, `unavailable`, `unsupported` or `not_evaluated`. A schema-valid record cannot automatically become verified, trusted, authorized or suitable for reliance.

## Integrity boundary

Hashes establish content binding, not issuer identity. The reference package carries two digest surfaces:

- `integrity.value` binds the exported ODES record and profile metadata.
- `package_digest` binds the material exported package content: record, profile, integrity metadata and provenance, including execution facts, source references, limitations and redaction lineage.

A recipient may configure a digest as trusted for inspection, but that still does not authenticate the issuer, prove signing time, establish institutional authority, verify successful delivery or create reliance. Recomputing hashes after changing package content can restore content self-consistency but still cannot create issuer authentication.

HMAC, where a future profile defines it, establishes shared-secret integrity. Synthetic signature profiles must bind the complete relevant record and profile metadata and require explicit recipient trust configuration. BitRep verification and Index inclusion can provide optional evidence signals but cannot create authority, adoption or recipient reliance by themselves.

## Time and status evidence

Time-dependent acceptance requires a valid recipient evaluation time. Missing or malformed `now` prevents acceptance for the affected purpose.

Decision-critical status evidence must be explicitly configured by the recipient and bound to the relevant record/authority identity and evaluation scope. The reference status input contract requires, at minimum:

- `record_id` matching `record.decision_id`;
- `authority_basis` matching `record.authority.authority_basis`;
- `evaluation_scope` in the supported recipient scopes;
- `evaluated_at` as a valid timestamp;
- `evidence_freshness` that is current or recent;
- present `freshness`, `revoked` and `superseded` status;
- `authority_valid_at_decision_verified` when historical authority verification is required.

Missing, stale, unsupported or mismatched status evidence prevents acceptance for the affected purpose.

## Historical and present validity

Historical admission, present validity, issuer authentication and proven signing time are separate. This reference implementation does not invent historical authority verification. The record's own `authority_valid_at_decision=true` is treated as an issuer assertion, not recipient-verified authority.

If recipient policy permits inspection of unauthenticated material, the validator reports `recipient_reliance_decision.status = informational_only`. That disposition permits review of the exported material only; it is not reliance, authorization, institutional approval, deployment approval or independent verification.
