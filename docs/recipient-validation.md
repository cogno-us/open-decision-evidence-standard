# Recipient Validation Reference Path

Status: Informative reference behavior for exported ODES packages.

The recipient validator consumes only an exported package and explicit recipient policy/status inputs. It does not access producer databases, call private runtime services, execute workflows, renew authority or mutate destination state.

## Validation layers

The reference validator returns separate results for:

1. `schema_validity` — validates the embedded `record` against `pder-v0.1`.
2. `declared_profile_conformance` — checks the implementation profile declared by the package and record.
3. `integrity_authentication_checks` — checks content digest binding or reports unsupported/unavailable verification methods.
4. `authority_status_and_freshness` — evaluates authority, revocation, supersession, freshness and expiry against recipient policy inputs.
5. `consumption_conditions` — checks relying party and purpose.
6. `recipient_reliance_decision` — recipient policy result.

Each layer may return `pass`, `fail`, `unavailable`, `unsupported` or `not_evaluated`. A schema-valid record cannot automatically become verified, trusted, authorized or suitable for reliance.

## Integrity boundary

Hashes establish content binding. HMAC, where a profile later defines it, establishes shared-secret integrity. Neither establishes public issuer identity or institutional authority. BitRep verification and Index inclusion can provide optional evidence signals but cannot create authority, adoption or recipient reliance by themselves.

## Historical and present validity

Historical admission, present validity and proven signing time are separate. This reference implementation does not invent historical authority verification. Missing decision-critical recipient inputs prevent acceptance for the affected purpose.
