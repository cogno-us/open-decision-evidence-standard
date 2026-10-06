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
- `provenance`: source artifact hashes, pinned revisions, source-record references, Replay validation result, mapped decision facts, execution facts and explicit limitations.

The package is not itself the `pder-v0.1` record. Consumers must not silently treat profile provenance fields as base-schema fields.

## Integrity boundary

The reference implementation uses a content digest. It binds exported content. It does not establish public issuer identity, production key custody, institutional authority, independent review, deployment approval or successful delivery.

BitRep and The Index remain optional related evidence interfaces. They are not mandatory for ODES adoption and do not create institutional authority merely by verifying a signature or inclusion event.

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
- original versus redacted derivative lineage.

## Scope limits

Export and recipient validation create no external effect and renew no authorization. A schema-valid record cannot automatically become verified, trusted, authorized or suitable for recipient reliance.
