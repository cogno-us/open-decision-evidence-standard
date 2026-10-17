# Control Plane journal contract

Version: `0.1.0-draft`. Status: draft, proposal only. Not frozen (the first freeze is deferred by the owner), not part of `pder-v0.1`, not referenced by any `odes` code path, and not a qualification input. See `docs/engineering/ODES-INTERCOMPONENT-CONTRACTS.md` for the design and `contracts/execution-attempt-lifecycle/` for the sibling contract this one is modelled on and delegates to.

## Contract statement

This contract governs the boundary between the Control Plane run record and the components that read it:

- Producer: the Control Plane bounded workflow (`BoundedAuthorizationWorkflow` and `BoundedRecordStore` in `src/agent_control_plane/bounded.py`), which writes `BoundedRunRecord` (decisions, attempts, observations, reconciliations, refusals, resolution checks, closeouts, input time floors, and in journal mode the resolution journal `check_events` and `vocabulary_changes`).
- Consumers: the Replay bundle importer (`importers.py` `import_bounded_workflow`, `_validate_repaired_run`, `_effect_observation_history`; `refusal_evidence.py` `validate_run`, `extend_retained_inputs`) and, through Replay, the Evidence pack importer. The Governed Exchange reference runtime also reads the store (in-process today); this contract states the append-only property it relies on (`check_succession`). The runtime adapter (`engine/control_plane_adapter.py`) reads the workflow's results and records in process; that call is a coupling to remove, not a rule here.

Shapes and rules were read from Control Plane `26a7e659` (main) and Replay `7c6888f` (main), and checked against ten real runs captured from the Control Plane's own test helpers (synthetic proposals, deterministic clock). The pre-refusal Control Plane generations (the first bounded run record, which lacks `refusals`, `resolution_checks`, `closeouts` and `input_time_floors`) are not covered.

A conforming document states `contract: "control-plane-journal"` and `contract_version: "0.1.0-draft"` and carries the run record members. `schema.json` (JSON Schema draft 2020-12) defines members, types and enumerations. The rules below are the cross-record half, implemented by `validate.py`.

## Member model

Same model as the lifecycle contract.

1. Declared required members must be present: `contract`, `contract_version`, `run_id`, `decisions`, `attempts`, `observations`, `reconciliations`, `refusals`, `resolution_checks`, `closeouts`, `input_time_floors` (the producer always emits the last nine). `check_events` and `vocabulary_changes` are optional because the producer omits them when empty. Inside records, members the producer always writes are required; members it omits when unset (`reason_vocabulary_version`, `reopen_conditions`, `runtime_authority`, `read_state`, `generation`, `tenant_id`, `error`, `observed_at`, `destination_state` on an observation) are optional.
2. Every declared object has a closed member set. A member neither declared nor inside `extensions` is refused with `undeclared_member`, never dropped (V1 finding F-10).
3. Every declared object may carry `extensions`, an object whose member names match `^x-[a-z0-9][a-z0-9._-]*$` (`invalid_extension_key` otherwise). Consumers ignore extension members for contract logic, preserve them when re-emitting, and include them in any digest. Producer commitments (`effect_id`, binding digests) do not cover extension members; only a consumer digest of the whole export does.
4. Adding an optional declared member is a minor bump. Adding a required member, or changing the meaning of a status, is a major bump.
5. Enumerations are closed (decision item 6): a value outside them is `unknown_enum_value`, never coerced. Closed here: decision `result` (`authorized`, `hold`, `deny`), `time_source`, attempt `status`, reconciliation `result` (`applied`, `observed_absent`, `safe_to_retry`, `hold`), observation `state`, closeout `original_status` (`attempted`, `unknown`, `failed`) and `observed_state` (`applied`, `partial`), resolution input `input_type` and `read_state`, check `stage`, journal `phase`, vocabulary change `kind`, and `reason_vocabulary_version` (`runtime-authority-reasons/0.1`).

## Delegation to the lifecycle contract

Attempt lifecycle rows and journal protocol are the `execution-attempt-lifecycle` contract's rules (`missing_start_record`, `invalid_reconciled_marker`, `attempt_started_at_changed`, `repeated_record`, `journal_protocol`, `journal_unbound_completion`, `journal_check_reused`, `resolution_checks_out_of_order`). They are not restated: `validate.py` projects `attempts` to `control_plane_attempts` and `check_events` to `resolution_journal` and calls the lifecycle validator, re-emitting its codes with this document's paths. The member definitions shared with the lifecycle contract (`extensions`, `resolution_input`, `resolution_check`, `control_plane_attempt`; `journal_event` narrowed to the one vocabulary version) are identical, and a test pins that, and pins the lifecycle version this was reviewed against. `duplicate_check_id` is reported by this contract for every run. A vendored copy needs the lifecycle contract vendored beside it (same parent directory).

## Journal mode and the plain record

The resolution journal is on only under a runtime-authority profile. Then `check_events` is present and non-empty, every decision and refusal records `reason_vocabulary_version`, and every authorized binding carries `runtime_authority` (profile `runtime-authority/0.1`, with its six digest members). Without a profile none of those members appear (the producer omits them). The contract allows both; mixing is refused (`vocabulary_version_missing`, `runtime_authority_binding_missing`, `journal_missing`). Tenant bindings (`bounded-authorization-effect/0.2`) carry `generation` and `tenant_id` together or not at all (`tenant_binding_incomplete`); the generation is chosen by the producer's class, not by a proposal field.

An evaluation that never completed is valid evidence: a journal check that is opened only, or `interrupted` (closed by `recover_interrupted_checks` after the process died), means the authority evaluation did not complete. `unfinished_checks` lists them. A consumer reports such an evaluation as incomplete and never reads it as an authorization.

## Attestation-adjacent fields

- `effect_id` is the commitment (SHA-256, sorted compact UTF-8 JSON, `ensure_ascii` false, prefix `sha256:`) of `{proposal, grant_id, grant_revision}` taken from the binding (`invalid_effect_identity`). A held decision has no binding; its effect id commits the proposal alone and cannot be checked without the proposal, which is outside this boundary.
- Commitment members (`proposal_commitment`, `manifest_digest`, `payload_commitment`, `requirement_commitment`, `role_mapping_digest`, `record_commitment`, the `runtime_authority` digests) are `sha256:` plus 64 lowercase hex. They are producer-declared and unverified at this boundary (Replay records them as `attributed_claim`). A rejected observation is retained as attributed content, never as evidence of effect.
- The run record carries no signature, digest or attestation member. Its integrity is not asserted here. (The Control Plane's HMAC-signed replay bundle belongs to the generic policy-gate path and is a different artifact.)
- `input_time_floors` keys are commitments of `[input_type, input_id]`; values are timezone-aware times.

## Rules

Structural codes (schema, level S): `schema_violation` (type, required member, pattern), `undeclared_member`, `unknown_enum_value`, `invalid_extension_key`, `unsupported_contract_version`. The rest need the cross-record view (level L).

Decisions and references:

- Decision ids are unique, including verbatim repeats (`duplicate_decision_id`). Result `authorized` if and only if `reasons` is empty and a binding is present (`decision_result_inconsistent`). The operation horizon commits to the binding's proposal (`horizon_binding_mismatch`).
- An attempt or refusal names an existing decision (`dangling_decision_reference`), carries that decision's `effect_id` (`effect_id_mismatch`), and the decision is authorized with a binding (`attempt_on_unauthorized_decision`, `refusal_requires_authorized_decision`). Observations and reconciliations name an effect some decision has (`dangling_effect_reference`).

Attempts (beyond the lifecycle contract):

- Rows `attempted`, `failed`, `unknown` carry an empty acknowledgement (`attempt_acknowledgement_inconsistent`; the `reconciled_existing` marker is the lifecycle contract's). `error` is null on `attempted`/`acknowledged`/`partial`, a bounded reason code (`^[a-z][a-z0-9_]{0,63}$`) on `failed`, and `destination_outcome_unknown:<ExceptionName>` on `unknown` (`attempt_error_inconsistent`).
- An effect has at most one attempt lifecycle that starts with `attempted`. Observed absence never establishes retry eligibility after a prior attempt (`second_attempt_for_effect`); the single-row `reconciled_existing` shape is not a second lifecycle.

Observations and reconciliations:

- `retry_eligible` is always false (`reconciliation_retry_eligible`). A rejected or unavailable observation is recorded with result `hold` and non-empty reasons (`rejected_observation_not_held`); it may carry malformed content and never appears in `observations`.
- An accepted observation (`observation_accepted` true) has no reasons (`accepted_observation_has_reasons`), carries its observation (`accepted_observation_missing`) naming the reconciled effect (`observation_effect_id_mismatch`), is never in state `unknown` (`observation_state_unknown`); `applied`/`partial` carry `destination_state` naming the same effect (`destination_effect_id_mismatch`) and state (`destination_state_contradiction`); `absent` carries an empty one (`absence_has_destination_state`). These are the reasons the producer rejects an observation with, so an accepted record that violates one is not something the producer could have written.
- An accepted observation records the policy it was accepted under, max age above zero and tolerance not below zero (`observation_policy_missing`), has timezone-aware `observed_at` and `evaluation_time` (`observation_time_invalid`), is not later than `evaluation_time` plus the tolerance (`observation_time_future`) and not older than the maximum age (`observation_stale`).
- An accepted `applied` observation is result `applied`, `absent` is `observed_absent`, `partial` is `hold` (`reconciliation_result_mismatch`). `safe_to_retry` is declared by the producer type and never emitted, so no accepted observation maps to it.
- `observations` lists exactly the accepted reconciliation observations, per effect, in acceptance order (`observations_mismatch`).

Closeouts (append-only; they never rewrite attempt rows):

- One per attempt and observed state (`duplicate_closeout`); it names an attempt row with the same effect and original status (`closeout_lineage_missing`) and an accepted observation of that effect, state and `observed_at` (`closeout_observation_missing`). An attempt whose last row is still `attempted`, `unknown` or `failed` has a closeout for every accepted `applied`/`partial` observation of its effect (`closeout_missing`).

Refusals:

- Refusal ids are unique (`duplicate_refusal_id`), carry reasons (`refusal_without_reasons`), the original horizon equals the refused decision's horizon (`refusal_horizon_mismatch`), and every changed input is attributed to an actual read in `resolution_inputs` (`changed_input_unattributed`).

Inputs, times, journal, vocabulary:

- A missing input claims no record commitment (`missing_input_commitment`). The times Replay checks, and `reconciled_at` and `evaluation_time`, are timezone-aware (`timestamp_invalid`).
- A journal event naming a decision names an existing decision and its effect (`journal_lineage_mismatch`); a decision-stage check has no decision yet (null), an effect-stage check names its decision (`journal_stage_binding`). Resolution check ids are unique (`duplicate_check_id`).
- A vocabulary change is recorded once (`duplicate_vocabulary_change`), changes the version, and a split yields at least two codes (`invalid_vocabulary_transition`).

Succession (two exports of one run, `check_succession`, code `not_append_only`): every record list of the earlier export is a prefix of the same list in the later one, and `input_time_floors` never move backwards or lose a key. The Exchange reference runtime relies on this for its `attempts`, `observations` and `reconciliations` prefix check.

## Fixtures

Each fixture file is `{fixture_id, synthetic, expected_outcome, reason, [expected_refusal], document}`. `fixtures/valid/` must be accepted. `fixtures/invalid/` must be refused with `expected_refusal` as the only violation. The valid fixtures other than the extension, tenant and vocabulary ones are real producer runs (Control Plane `26a7e659`, synthetic proposals, fixed clock), with resolution inputs trimmed to a manifest and a grant read consistently across decisions, checks and journal, and ids, process owner and timestamps synthetic.

Valid: `normal-attempted-acknowledged-applied`, `partial-dispatch-partial-observation`, `lost-ack-unknown-then-closeout`, `reconciled-existing-single-row`, `effect-time-refusal`, `held-decision-journal-mode`, `observation-unavailable-rejected-reconciliation`, `interrupted-check-is-unfinished-evidence`, `failed-definitive-rejection`, `no-journal-mode-normal`, `extension-namespace-members-preserved`, `tenant-binding-generation-0.2`, `vocabulary-change-recorded`.

Invalid: one per code above, named for the defect (64 fixtures). Delegated lifecycle rules are pinned by the `delegated-*` fixtures.

## Run

```
python contracts/control-plane-journal/validate.py <document.json>...   # prints violations; fixtures wrap the document
PYTHONPATH=src python -m pytest -q tests/test_contract_control_plane_journal.py
```

`validate.py` is stdlib only. The test suite also cross-checks `schema.json` against the `jsonschema` package when it is installed.

## Versioning and change rules (0.x)

While the version is `0.x-draft` nothing is frozen and any change may break. The freeze rules in the engineering document apply from `1.0.0`.

## Current conformance (2026-10-17, local runs, not a qualification)

- Producer, Control Plane `26a7e659`: all ten captured real runs (normal, partial, lost acknowledgement with closeout, reconciled existing, effect-time refusal, held decision, observation unavailable, interrupted check, definitive rejection, no-journal run) pass every rule. Gap: the run record carries no `contract` or `contract_version`, so a raw export is not a conforming document until those two members are added or supplied by a wrapper (open question 1).
- Consumer, Replay `7c6888f` (P4 generation), run on the fixtures through `import_bounded_workflow` with the three contract members removed: refuses valid `no-journal-mode-normal` ("resolution journal missing"); refuses extension members on `operation_horizon`, refusals, changed inputs, closeouts and `runtime_authority` (it accepts them on decisions, bindings, attempts, reconciliations, checks, journal events and inputs); accepts 14 of the 64 invalid fixtures: an attempt on a held decision, a verbatim duplicate decision, an `authorized` decision with reasons, an unknown decision result, an undeclared member on a decision, an undeclared top-level member (reported as finding `B001`, bundle status partial, not refused), an acknowledgement on an `attempted` row, a `failed` row without a reason code, a second attempt lifecycle for one effect, a tenant id without generation, a malformed `input_time_floors` key, a split into one code, a duplicate vocabulary change, and an extension key without `x-` (finding `B001`). The Replay global-order equality of `observations` was not exercised.
- Evidence pack: reads the run record only through Replay and its validator, so it inherits Replay's result. Exchange reference runtime and runtime adapter: not exercised.

## Open questions (section 12 style)

1. Document identity. The producer writes no `contract`/`contract_version` (the run record has no format field). They are required here by convention. Adding them to the record is an optional member (minor) but Replay reports unknown top-level members as `B001` and marks the bundle partial, so Replay would need to accept them first; a wrapper or sidecar is the alternative. Which?
2. Journal mode is optional here, required by Replay's P4 generation. Is a record without a runtime-authority profile a supported production output (then Replay should accept it), or is journal mode the only supported mode (then it becomes required and `no-journal-mode-normal` moves to invalid)?
3. Extensions on every object follows the model, but Replay treats `operation_horizon`, refusals, changed inputs, closeouts and the exact six-member `runtime_authority` as fixed sets. Should extension members be refused on binding objects that carry commitments?
4. Declared but never produced: decision result `deny`, reconciliation result `safe_to_retry`. They stay in the closed enums here (removal later is a major bump). Remove them while the contract is a draft?
5. `reason_vocabulary_version` is closed to `runtime-authority-reasons/0.1` (the producer constant and Replay's literal), but the record also carries `vocabulary_changes` for later versions. A real version change would be a contract major bump. Is that intended, or should the version be an open string?
6. `observations` equality is per effect in acceptance order here. Replay compares the whole list in global order. The producer appends an observation and its reconciliation in separate transactions, so two concurrent reconciles can interleave across effects. Per effect (this draft) or global (Replay)?
7. Five rules come from a single producer code path and are enforced by no consumer: `second_attempt_for_effect`, `attempt_error_inconsistent`, `attempt_acknowledgement_inconsistent`, closeout `original_status` closed to three values, and `journal_stage_binding`. Keep them in the contract or leave them as producer behaviour?
8. Opaque members, owned by other boundaries: `policy_versions` items (only `ref`, `version` required), `action_class`, `owner`, `reopen_conditions`, `destination_state` (beyond the keys the rules read), `acknowledgement`. The Authority Context and destination interface have no schema yet (P0 finding N-4).
9. Timestamps: `decided_at` and attempt `started_at` are not required to be timezone-aware because neither side checks them. The producer always writes timezone-aware values. Require it?
10. Attestation. The run record has no integrity member. Does the journal boundary need a digest or signature member (an optional addition), or is integrity left to the export package (ODES) and the consumer's own digest?
11. Two canonical JSON forms exist in the Control Plane (`signing.py` escapes non-ASCII, `bounded.commitment` does not). This contract uses the commitment form for `effect_id`. Confirm.
12. Exchange finds the store file by globbing a file name and matching `run_id`. The contract identifies a run only by `run_id`; file layout is out of scope. Confirm.
13. Hold decisions: `effect_id` commits the proposal alone and is unverifiable here because the proposal is not part of this boundary. Should the proposal commitment be carried on held decisions?

## Known gaps

- Authority Context, grant, approval and validation-record inputs are carried only as the minimized `resolution_input` rows; their own contracts are separate boundaries.
- The destination `apply` acknowledgement is stored unvalidated by the producer and is opaque here.
- Behaviour outside the record (locking, file system support, write-ahead failure refusing dispatch) is not a record rule.
