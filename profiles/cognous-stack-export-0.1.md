# ODES Cognous Stack Export Profile 0.1

Status: Informative implementation profile proposal. This profile is not part of the base `pder-v0.1` schema and is not required for generic ODES conformance.

Profile identifier: `odes_cognous_stack_export_0_1`

Document version: ODES narrative `0.2`
Schema version: `pder-v0.1`
Implementation-profile version: `odes-cognous-stack-export-0.1.0`

## Purpose

This profile defines a bounded, vendor-neutral export package for translating semantically validated Cognous synthetic-stack records into an ODES Portable Decision Evidence Record without changing the base schema.

The base ODES record remains the interoperable object. Cognous-specific execution details that cannot be represented in `pder-v0.1` are carried outside the record in package provenance.

## Required package boundary

A conforming package under this profile contains:

- `record`: a schema-valid `pder-v0.1` Portable Decision Evidence Record;
- `profile`: document, schema and implementation-profile version metadata;
- `integrity`: a content digest binding the exported record and profile metadata;
- `package_digest`: a content digest binding the material package content, including record, profile, integrity metadata and provenance;
- `provenance`: source artifact hashes, pinned revisions, source-record references, Replay validation result, mapped decision facts, execution facts, redaction lineage and explicit limitations.

The package is not itself the `pder-v0.1` record. Consumers must not silently treat profile provenance fields as base-schema fields or as adopted ODES conformance fields.

## Integrity, authentication and authority boundary

The reference implementation uses content digests. They bind exported content. They do not establish public issuer identity, production key custody, signing time, institutional authority, present validity, independent review, deployment approval or successful delivery.

Recipient validation separates:

- schema validity;
- declared-profile conformance;
- package content integrity;
- issuer authentication;
- historical authority assertions;
- present authority/status/freshness;
- consumption conditions;
- recipient reliance.

A record self-assertion such as `authority_valid_at_decision=true` is not recipient-verified authority. Missing authentication or authority evidence remains `unavailable`. If recipient policy permits inspection of unauthenticated material, the validator reports `informational_only`; it does not report reliance, authorization or verified authority.

BitRep and The Index remain optional related evidence interfaces. They are not mandatory for ODES adoption and do not create institutional authority merely by verifying a signature or inclusion event.

## Time and status evidence

Time-dependent recipient acceptance requires a valid recipient evaluation time. Missing or malformed evaluation time prevents acceptance for the affected purpose.

Decision-critical status evidence must be explicitly supplied by recipient policy and must bind to the record/authority identity and evaluation scope. Missing, stale, unsupported or mismatched status evidence prevents acceptance. The exporter does not default missing freshness to current.

## Unsupported base-schema semantics

The following source semantics are not native to `pder-v0.1` and therefore remain profile provenance:

- `effect_id`;
- separate Control Plane and executor attempt namespaces;
- execution-result attempt references;
- acknowledgement source records;
- destination-effect records;
- effect observations;
- reconciliation and restart recovery;
- partial delivery and unresolved delivery detail;
- Replay import findings and value-state limitations;
- original versus redacted derivative lineage;
- external status evidence;
- unknown decision time, because `pder-v0.1` requires `decision_timestamp`.

## Source-fact discipline

The exporter does not manufacture human approval, human escalation, human rejection, model identity, production issuer identity, institutional legitimacy, current validity or successful delivery.

- Machine hold/deny does not become a human disposition. It exports as `human_disposition.status=unknown` unless explicit retained human evidence supports another status.
- Authorization alone does not establish machine execution. The machine role is `execution` only when retained execution evidence is present.
- Revocation time, supersession linkage and decision time are copied only when evidenced. Export fails rather than substituting generation or export time for unknown required temporal facts.

## Scope limits

Export and recipient validation create no external effect and renew no authorization. A schema-valid record cannot automatically become verified, trusted, authorized or suitable for recipient reliance.
