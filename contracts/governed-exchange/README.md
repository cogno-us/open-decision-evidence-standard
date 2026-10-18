# Governed exchange contract

Version: `0.1.0-draft`. Status: draft, proposal only, not frozen (the owner deferred the first freeze, 2026-10-17). Not part of `pder-v0.1`, not referenced by any `odes` code path, and not a qualification input. See `docs/engineering/ODES-INTERCOMPONENT-CONTRACTS.md` for the design this contract follows and the P1 plan in cogno-us/cognous-control-plane#38.

## Contract statement

The plan's P1 list names this boundary "Exchange transport", and the P0 inventory (`docs/engineering/p0-inventory/exchange.json`, `produces`) lists what the Governed Exchange emits. This contract governs those emitted objects and what the exchange's consumers rely on:

| Member | Object | Produced by (cognous-governed-exchange `main`, ec6ba5b) |
|---|---|---|
| `message` | ODEX-GAX/IMX refund-exchange governed message (`PROPOSE`, `REQUEST`, `REPORT`, `REFUSE`, `NOT_UNDERSTOOD`) | `experiments/odex_gax_imx_reference/gax_ref.py` `make_message`, checked by `assess_message` |
| `transport_envelope` | transport envelope around a message | `experiments/governed_message_transport/transport.py` `make_transport_envelope` |
| `acknowledgement` | `DURABLE_RECEIPT`, `DURABLE_RECEIPT_UNRESOLVED`, `TERMINAL_REJECTION` | `transport.py` `_ack`, `_recipient_reject`, `_unresolved_receipt_ack` |
| `delivery_result` | sender-side summary, including `transport_state` | `transport.py` `LocalDurableTransport.deliver` |
| `recipient_result` | versioned recipient result and the explicit `unavailable` state | `transport.py` `RecipientOutcome.as_dict`, `retained_artifacts` |
| `retained_artifact_export` | GAX retained-artifact export (`original_complete` and three derivative states, with lineage) | `gax_ref_runtime.py` `_retained_artifact_export` |
| `successor_packet`, `successor_acceptance` | IMX successor packet and the result of loading it | `gax_ref_runtime.py` `make_successor_packet`, `TransactionalExchangeStore.accept_successor` |
| `transport_evidence` | transport evidence summary with the honest-limits list | `transport.py` `LocalDurableTransport.evidence` |

A conforming document states `contract: "governed-exchange"` and `contract_version: "0.1.0-draft"` and carries at least one member. `schema.json` (JSON Schema draft 2020-12) defines members and types; the rules below are the cross-record half, implemented by `validate.py`.

Consumers, as read from the checkouts: the qualification suites (`cognous-stack-qualification/suites/cognous-governed-exchange/`, which read the retained export, the recipient result, the acknowledgement and `deliver` results) and the two ends of a delivery (a recipient handler, a sender). The exchange itself consumes the Control Plane, the runtime, Replay, ODES and the manifest; those are other boundaries and are not specified here. The in-process imports the exchange uses to reach them are a coupling to remove, not something to standardise.

Not covered: lineage generation-fence refusal records (local SQLite, no cross-component consumer found), the historical legacy store in `gax_ref.py` (marked unsupported), the legacy hand-built reconstruction bundle in `gax_ref.py`, and the recovery artifact files (they hold the same export).

## Differences from the sources the exchange documents

The contract follows the code, because the code is what consumers meet. Three places where the exchange's own documents say less:

- `experiments/odex_gax_imx_reference/profile.md` lists 15 required message members. `assess_message` requires 18: it also needs `proposal_commitment`, `content` and `message_digest`. The schema requires the 18. `acknowledgement_requested` is emitted but required by neither; it is optional here.
- `requested_action` is described only as "requested_action" in `profile.md`. The code compares it to a fixed nine-member projection of the Control Plane proposal; the schema closes it to those nine members.
- `docs/gax-runtime-artifact-interface.md` names `engine.control_plane_adapter.PinnedControlPlaneExecutor` while the code imports it from `engine.producer_contract` (inventory note). Not a contract matter; recorded for the exchange owner.

## Member model (optional-members proposal)

1. Declared required members must be present. Declared optional members may be absent.
2. Every declared object has a closed member set. A member that is neither declared nor inside `extensions` is refused with `undeclared_member`, never silently dropped (V1 finding F-10).
3. Every declared object may carry `extensions`, an object whose member names match `^x-[a-z0-9][a-z0-9._-]*$`. Consumers ignore them for exchange logic, must preserve them when re-emitting, and must include them in every digest. Here the digest of a message covers every member, so stripping an extension breaks `message_digest`.
4. Adding an optional declared member is a minor bump. Adding a required member or changing the meaning of a status is a major bump.

Three members are open by design, because the exchange carries them opaquely: the message `content` (untrusted narrative, never read for authority), the transport envelope's `governed_message` (validated by the recipient's assessment, not by transport; the schema pins only the members transport itself reads) and the Replay and ODES artifacts retained inside an export (`reconstruction_bundle`, `odes.odes_package`, `odes.recipient_validation`), which belong to those components' contracts.

## Canonicalisation and digests (named, as the design requires)

Canonicalisation is the exchange's `json-sort-keys-compact-v1`: JSON with sorted keys, compact separators, UTF-8, no non-ASCII escaping, `NaN` and infinities refused. A digest is `sha256:` plus 64 lowercase hex digits of those bytes. The reference validator's `canonical_bytes` and `digest` implement it and a test pins a vector.

## Closed enumerations

Message type, acknowledgement kind, handling, result state, export state, lineage relationship, attempt status, transport state and outbox state, delivery attempt state, successor acceptance status and the honest-limits names are closed. A value outside them is refused with `unknown_enum_value` and never coerced. Adding a value is a major bump. Where the exchange answers an unknown message type with `NOT_UNDERSTOOD`, that is the recipient's protocol response; a document carrying the unknown type is not conformant.

## Rules

Version gates, refused with their own codes before structure is judged: `unsupported_contract_version`; `unsupported_profile` (message `profile` or `protocol_version`); `unsupported_transport_profile`, `unsupported_transport_version`, `unsupported_canonicalization`; `unsupported_result_profile`; `unsupported_artifact_export_profile`, `unsupported_artifact_export_version` (1.0.0 and 1.1.0 are readable); `unsupported_profile_or_schema` (successor packet).

Message:

- `message_id` matches `[A-Za-z0-9][A-Za-z0-9._-]{0,127}` and contains no `..` (identifiers become store file names). Violation: `schema_violation`.
- Timestamps carry a time zone offset (`schema_violation` otherwise); `expires_at` is after `created_at` (`message_expiry_not_after_creation`).
- `message_digest` is the digest of every other member (`message_digest_mismatch`); `content_digest` is the digest of `content` (`content_digest_mismatch`).
- A `replay_bundle` evidence reference carries `digest` (`replay_bundle_ref_without_digest`).

Transport envelope:

- `message_id` and `conversation_id` equal the carried message's (`message_identity_mismatch`, `conversation_identity_mismatch`).
- The envelope is created no earlier than the message (`envelope_created_before_message`) and expires with it (`envelope_message_expiry_mismatch`); the carried message expires after it was created (`message_expiry_not_after_creation`).
- The carried message's digests recompute (`message_digest_mismatch`, `content_digest_mismatch` when `content_digest` is present), and `content_commitment` equals its `message_digest` (`content_commitment_mismatch`).
- When a document carries both a message and an envelope, the envelope carries the message verbatim (`envelope_message_mismatch`).

Acknowledgement:

- The detail is fixed per kind. A receipt says `not_implied_by_acknowledgement` for authorization, execution, destination observation and independent verification; an unresolved receipt says `not_established`; a rejection says authorization `not_evaluated_by_transport` and external effect `not_established`. Any other value is `schema_violation`: an acknowledgement never claims an effect, an authorization or a governance decision.
- The echoed `message_id`, `delivery_attempt_id`, `content_commitment` and `recipient_endpoint_ref` are null only on `TERMINAL_REJECTION` (`acknowledgement_binding_incomplete`) and equal the envelope's when it is present (`acknowledgement_envelope_mismatch`). The same binding applies to an acknowledgement nested in a `delivery_result` (decision 37): a nested acknowledgement is compared with the document's envelope when one is present.
- A `DURABLE_RECEIPT` is never issued for a result in `recovery_required` or `historical_artifacts_unavailable` (`receipt_for_unretained_result`); that case is `DURABLE_RECEIPT_UNRESOLVED`.

Delivery result:

- `DELIVERED` requires a received `DURABLE_RECEIPT`; `TERMINAL_REJECTED` a `TERMINAL_REJECTION`; an unresolved receipt gives `PENDING_RETRY` or `UNRESOLVED` (`delivery_state_ack_mismatch`).
- `acknowledgement_received` is true exactly when the acknowledgement is carried; a result with `attempted` false names no attempt id and no acknowledgement; `BACKOFF` is never attempted and names `next_attempt_at`; the acknowledgement answers the attempt the result names (`delivery_result_inconsistent`).

Recipient result:

- `result_state` equals the export's `state` for the four export states; any other state (`complete`, `recovery_required`, `historical_artifacts_unavailable`, `unavailable`) carries no export (`result_state_export_mismatch`). `unavailable` carries no assessment, execution or producer references (`unavailable_result_carries_content`).
- An effect is attempted only after an assessment with handling `ACCEPT_FOR_ASSESSMENT` (`execution_without_eligible_assessment`). `attempt_status` `deny`, `hold` or `unresolved_duplicate` means nothing was dispatched; `interrupted_after_dispatch` or `evidence_export_failed` means an effect was (`attempt_status_attempted_mismatch`). A derivative result is evidence only: `attempted` and `newly_executed` are false (`derivative_result_claims_execution`).
- A refusal (`REFUSE`, `NOT_UNDERSTOOD`) carries an error and a failed stage (`refusal_without_failure`); `NOT_UNDERSTOOD` is the handling exactly when the structure or profile stage failed (`not_understood_stage_mismatch`); informational handling means stage `communicative_act` is `informational_no_effect` (`informational_stage_mismatch`).
- The export references a result repeats (`reconstruction_bundle_id`, the digests, the successor references) equal the export's (`result_producer_refs_mismatch`); a result's export equals a retained export in the same document (`artifact_export_mismatch`).
- `execution.observation` and `control_plane_evidence` are opaque here. Executor-level status and observation semantics are the `execution-attempt-lifecycle` contract's. `attempt_status` mixes that contract's result statuses with the Control Plane's decision results (`deny`, `hold`) and the exchange's own (`interrupted_after_dispatch`, `evidence_export_failed`, `unresolved_duplicate`); the lifecycle contract's `denied` and the exchange's `deny` are both accepted here and are an open question.

Retained export (checks run in the exchange's own order and the first failing check is the refusal, with the exchange's own strings as codes): `retained_reconstruction_identity_mismatch`, `retained_reconstruction_digest_mismatch`, `retained_reconstruction_commitment_mismatch`, `retained_odes_package_digest_mismatch`, `retained_odes_package_commitment_mismatch`, `retained_odes_validation_digest_mismatch`, `retained_odes_validation_commitment_mismatch`, `retained_successor_identity_mismatch`, `retained_successor_digest_mismatch`, `retained_successor_content_digest_mismatch`, `retained_successor_commitment_mismatch`. Then lineage rules the exchange does not check today but its constructors always satisfy:

- State and lineage relationship pair up: `original_complete` with `original`, `regenerated_derivative` with `regenerated_derivative`, `recovery_denied_derivative` with `recovery_denial_derivative`, `reconciled_derivative` with `observation_reconciliation_derivative` (`lineage_state_mismatch`).
- `effect_reexecution`, when present, is false (`lineage_effect_reexecution`).
- A denied recovery records `recovery_status` `denied` and that no destination observation, replacement dispatch or renewed authorization happened (`recovery_denial_lineage_invalid`).

Successor packet and acceptance:

- `packet_digest` is the digest of every other member (`packet_digest_mismatch`); `state_version` has the form `state-<n>`.
- Loading a packet never creates an effect or a grant (`successor_creates_effect`); `loaded` is true exactly for `loaded_for_reconciliation` (`successor_loaded_status_mismatch`).

Transport evidence:

- `unsupported` names all three honest limits: authenticated network identity, distributed exactly-once delivery and independent effect verification (`unsupported_limits_missing`).
- Transport attempt ids never appear among executor or Control Plane attempt ids in the producer references (`attempt_namespace_collision`).

## Rules that need peer artifacts (stated, not checkable from one document)

These are real exchange rules; the reference validator cannot decide them without the peer's input, so they are listed rather than faked:

- `requested_action` equals the nine-member projection of the Control Plane proposal, and `proposal_commitment` / `operation_commitment` equal the Control Plane `commitment` of it (`GAX-REFERENCE-OPERATION-BINDING-MISMATCH`).
- A `replay_bundle` reference digest equals the digest of the recipient's bundle (`GAX-EVIDENCE-DIGEST-MISMATCH`), and `authority_refs` contains the proposal's authority context reference (`GAX-AUTHORITY-REFERENCE-MISMATCH`).
- Sender and recipient claims against the registry or the trusted route table, route resolution, and the trusted delivery instant (a message expired or created in the future relative to trusted time).
- `message_id` reuse with a different digest (store state), successor head, lineage and rollback rules (`divergent_branch`, `stale_or_rollback` and the rest of the status vocabulary depend on the store), effect ownership across messages.
- Whether the retained Replay bundle and ODES package are themselves valid (Replay and ODES contracts).

## Consumer reliance (what the qualification suites read)

Read from `cognous-stack-qualification/suites/cognous-governed-exchange/`: `transport_state` (delivery result), `acknowledgement.detail`, `result_state`, `producer_refs`, `artifact_export` with `content_commitments`, `lineage.relationship`, `lineage.effect_reexecution`, `successor_packet`, `reconstruction_bundle` and `odes.recipient_validation`. The rules above are what protects those reads. Qualification also relies on `transport_evidence.unsupported`.

## Known producer non-conformance (found by running the exchange's pure producer paths against this draft, 2026-10-17)

Run against cognous-governed-exchange `main` with stub peers; each item is a finding against the exchange (P2/P3 work), not a fix:

- `assess_message` accepts an undeclared message member and a malformed `extensions` key (the message digest covers every member), so F-10 does not hold at the message layer. It also accepts an `expires_at` earlier than `created_at`, a timezone-naive `created_at`, and a non-object `content`.
- `_validate_retained_artifact_export` checks version, profile and digests only. It accepts an unknown `state`, an undeclared export member, a lineage relationship that disagrees with the state, `effect_reexecution` true and a denied-recovery lineage that records an observation.
- `accept_successor` accepts a packet with an undeclared member and a `state_version` such as `v-1`.
- The transport accepts an envelope with an undeclared member.
- The transport carries a message the profile refuses (the exchange's own transport tests use a one-member `requested_action` and empty `authority_refs`); the refusal happens in the recipient's assessment. That is by design and is why the envelope's `governed_message` is open.

Conformant as exercised: digest computation and verification, envelope identity, temporal and commitment checks, acknowledgement details and kinds, recipient result and `unavailable` shapes, export digests and commitments, successor packet digest, `effect_created` always false, and the evidence summary's honest-limits list.

## Fixtures

Each fixture file is `{fixture_id, synthetic, expected_outcome, reason, [expected_refusal], document}`. `fixtures/valid/` must be accepted. `fixtures/invalid/` must be refused with `expected_refusal` as the only violation. Most valid documents were captured by running the exchange's own producer code (`make_message`, `make_transport_envelope`, `LocalDurableTransport` with a stub recipient, `_retained_artifact_export`, `make_successor_packet`, `accept_successor`) with synthetic inputs, then wrapped; ids, digests and times are synthetic. The `delivery_result` shapes for ack-lost, interrupted, backoff and retry-exhausted were written from the code paths in `LocalDurableTransport.deliver`, not captured.

Valid fixtures cover every member and each export state, `unavailable`, `recovery_required`, the null echo on a malformed-envelope rejection, `1.0.0` exports, extension preservation, and an envelope carrying a message the profile would refuse. Invalid fixtures cover every refusal code above.

## Run

```
python contracts/governed-exchange/validate.py <document.json>...   # prints violations; fixtures wrap the document
PYTHONPATH=src python -m pytest -q tests/test_contract_governed_exchange.py
```

`validate.py` is stdlib only. The test suite also cross-checks `schema.json` against the `jsonschema` package when it is installed.

## Conformance levels

Level S: `schema.json` valid. Level L: schema valid and every rule above holds. Level P: a consumer additionally preserves `extensions` and includes them in digests. A producer claims the level it tests; a consumer claims the level at which it refuses the invalid fixtures.

## Versioning and change rules (0.x)

While the version is `0.x-draft` nothing is frozen and any change may break. The freeze rules in the engineering document apply from `1.0.0`: patch for clarifications and added fixtures, minor for optional additions, major for required additions or semantic change, with a published deprecation window.

## Known gaps in this draft

- Producer-side conformance was exercised only on pure code paths with stub peers. No end-to-end run with the real Control Plane, runtime, Replay and ODES was made, and none of this is qualification evidence.
- The execution summary shape (`execution`) is the union of the shapes the code returns on its several paths; which members are required on which path is not pinned beyond `attempted`.
- Successor store rules (head, lineage, rollback) are stateful and are not modelled by a one-document validator.
- Honest limits carry over unchanged: conformance shows structure and the stated rules. It does not establish that a message is true, that a sender is authentic (configured transport identity is not cryptographically authenticated), that exactly-once delivery happened, or that an effect occurred.

## Input hardening (decision 32, 2026-10-18)

The reference validator never raises: any parsed JSON value gets a list of typed violations. Non-finite numbers (NaN, Infinity) and text that is not valid Unicode are refused as `schema_violation`; `main()` reads files with a strict loader (duplicate members, NaN, Infinity, overflowing numbers and non-UTF-8 input are refused, exit status 2, line `input_refused`); schema patterns match the whole string (`(?!\n)$` in `schema.json`) and times are ISO-8601 with ASCII digits and a UTC offset. No code, member or accepted form changed meaning; no code was added.

Invalid fixtures added: `non-ascii-digit-time`, `trailing-line-break-digest`, `trailing-line-break-time`, `unpaired-surrogate-text`.
