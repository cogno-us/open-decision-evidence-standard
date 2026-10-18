# Operation identity extension profile

Version: `0.1.0-draft`. Status: draft, proposal only, OPTIONAL extension profile. Not frozen (the first freeze is deferred by the owner), not part of the ODES core or `pder-v0.1`, not referenced by any `odes` code path, and not a qualification input. See `docs/engineering/ODES-INTERCOMPONENT-CONTRACTS.md` (Appendix C, section 12 item 21) for the index and the decisions. Nothing here edits the journal contract, the lifecycle contract, the core schema or `pder-v0.1`.

## Contract statement

A business operation has one stable identity, `operation_id`, supplied by the grant issuer. The legacy `effect_id` is the commitment of `{proposal, grant_id, grant_revision}` and so changes when a grant is renewed; an attempt stalled on revision 1 and a fresh attempt on revision 2 are two effects of one operation. This profile records the identity facts that let a reader join the operation, its renewals, each attempt and the journal check that licensed it by id, and states what a destination must do so that one operation commits one effect.

The profile is optional and opt-in. It is selected only by the host-governed `RuntimeAuthorityProfile.operation_identity` setting in the Control Plane; with it unset nothing in this contract applies, no run record member appears and no stored or hashed byte changes (the default path is the journal contract as it stands).

Shapes and rules were read from the merged code, not from the proposal:

- Control Plane `src/agent_control_plane/operation_identity.py`, `bounded.py` and `runtime_authority.py` at main `83b49b5` (the profile merged in #45 at `9d00f38`; `83b49b5` adds `acp run`, which does not touch these paths). Control Plane PR #45 body, qualification #98 body (N1's proposed contract delta) and runtime #109 were read for intent; where they differ from the code, the code wins.
- Runtime `engine/operation_admission.py` (sidecar, unwired) and `engine/operation_identity_destination.py` at main `63a7c0fe2` (#109).

The valid fixtures are captures of real runs of the Control Plane's own flows (see Fixtures), not hand-written documents.

## Document model

A sidecar projection of one run, `contract: "operation-identity"`, `contract_version: "0.1.0-draft"`, `profile: "operation-identity/0.1"`, `run_id`, optional `producer`, and the three lists the producer writes as optional members of `BoundedRunRecord` (omitted there while empty; required here, possibly empty):

| List | Row | Written |
|---|---|---|
| `operations` | `operation_id`, `principal_id`, `authority_domain`, `issuer`, `grant_id`, `first_grant_revision`, `admitted_at` | once, on the first authorized decision for the id |
| `operation_renewals` | `renewal_id`, `operation_id`, `grant_id`, `from_revision`, `to_revision`, `written_by`, `outcome` (`accepted`, `refused`), `refusal_code`, `recorded_at` | by `record_renewal`; refused rows are kept |
| `attempt_joins` | `join_id`, `operation_id`, `attempt_id`, `check_id`, `effect_id`, `decision_id`, `grant_id`, `grant_revision`, `resolver_id`, `resolver_version`, `class_max_age`, `expected_effective_grant_digest`, `merged_into`, `recorded_at`, `time_source` | one per attempt, before the attempt row |

Why a projection: the journal contract is closed (`additionalProperties` false) and, at `0.1.0-draft`, declares none of the profile's members. A raw run record produced with the profile on is refused by it with `undeclared_member` for `operations`, `operation_renewals`, `attempt_joins`, for `check_id` on refusal rows and, reported as `schema_violation` at the binding, for `operation_id`/`operation_issuer` inside its closed `runtime_authority` (checked on records produced by Control Plane `9d00f38` and `83b49b5`: those are the only violations, and every default-path run still conforms). This contract carries the new rows and describes the journal-side additions as cross-document rules over the run record. Making the journal contract declare them as optional members is a possible minor bump (recommended, not done here).

Update (2026-10-18, journal draft revision 2, decision 23): the journal contract now declares this profile's members as optional, so a raw run record produced with the profile on is accepted by it; this contract stays the owner of their semantics. Statements below that the journal contract declares none of the members or refuses the record describe draft revision 1 and are kept as the record of why the sidecar form was chosen.

Journal-side additions, described here and checked only through the optional journal context: (a) `check_id` on effect-time refusal rows; (b) `operation_id` and `operation_issuer` in the `runtime_authority` extension of an authorized binding (issuer-supplied: the approval commitment covers them, so a planner or worker cannot add or change them); (c) the journal check id is shared by the journal `check_events`, the `resolution_checks` row and the join row (in the legacy path the resolution check mints its own id).

## Member model

Same model as the journal contract.

1. All declared members of a row are required. `producer` and `extensions` are the only optional document members.
2. Closed member sets. An undeclared member outside `extensions` is `undeclared_member`, never dropped.
3. `extensions` (names `^x-[a-z0-9][a-z0-9._-]*$`, else `invalid_extension_key`) on the document and on each row. Consumers ignore them for contract logic, preserve them, and include them in any digest.
4. Closed enumerations (`unknown_enum_value`): renewal `outcome` (`accepted`, `refused`), renewal `refusal_code` (`operation_not_admitted`, `renewal_not_written_by_grant_issuer`, `renewal_revision_not_new`, or null), join `time_source` (`control_plane`, `test_override`). A new value is a major bump.
5. Times are ISO-8601 with a UTC offset (`timestamp_invalid`). `operation_id` is 1 to 128 characters from `[A-Za-z0-9._:/#-]`, first character alphanumeric (`schema_violation`; the producer's `operation_id_invalid`). `effect_id` is a `sha256:` commitment. `class_max_age` is an integer of at least 0.
6. Adding an optional member is a minor bump; adding a required member or an enumeration value is a major bump.

## Reason codes

Seven codes of the Control Plane reason registry (121 codes in `runtime-authority-reasons/0.1`, 158 in the superset `/0.2`; the seven are among the 37 codes only 0.2 registers) belong to the profile. They are producer reason codes, not validator codes; the validator's own codes are listed under Rules.

| Code | Where it appears | Meaning |
|---|---|---|
| `operation_id_missing` | decision reasons (hold) | the issuer-approved extension carries no `operation_id` |
| `operation_id_invalid` | decision reasons (hold) | the id is not a string of the pattern above |
| `operation_grant_mismatch` | decision or refusal reasons | the id is bound to another principal, authority domain, issuer or grant (a collision, never a silent continuation) |
| `operation_renewal_unrecorded` | decision or refusal reasons | a new grant revision that no accepted renewal row names |
| `operation_not_admitted` | refusal reasons; renewal `refusal_code` | effect time: no ledger row for the id; renewal: the operation is unknown |
| `renewal_not_written_by_grant_issuer` | renewal `refusal_code` (and the `PermissionError` message) | a renewal written by anyone but the issuer recorded at admission (the worker extending its own envelope) |
| `renewal_revision_not_new` | renewal `refusal_code` | the revision is the operation's first or one already renewed to |

A decision that carries any of the first four is a `hold` with no binding, no attempt and no join. The journal contract's own rules already say that.

## Rules

Structural codes (level S): `schema_violation`, `undeclared_member`, `unknown_enum_value`, `invalid_extension_key`, `unsupported_contract_version`. The rest are rule codes (level L). Rules marked J need the run record (journal context); the others need the document alone.

Ledger:

- Operation ids are unique (`duplicate_operation_id`); renewal ids (`duplicate_renewal_id`) and join ids (`duplicate_join_id`) are unique; times are timezone-aware (`timestamp_invalid`).
- Renewals are replayed in list (append) order. For each, the ledger fixes the outcome in the producer's check order: the operation is not admitted, else the writer is not the issuer recorded at admission, else the revision is the first or already renewed to, else accepted. Pairing: `outcome` is `accepted` if and only if `refusal_code` is null (`renewal_outcome_inconsistent`). A refused row carries the code the ledger gives (`renewal_refusal_code_mismatch`) and only when the ledger shows a defect (`renewal_refusal_unjustified`). An accepted row must not be one the ledger refuses: `renewal_accepted_unadmitted_operation`, `renewal_accepted_not_by_issuer` (only the grant issuer writes a renewal), `renewal_accepted_revision_not_new`. Context members: a renewal of an unadmitted operation has null `grant_id` and `from_revision`; otherwise `grant_id` is the operation's and `from_revision` is the last accepted revision, else the first (`renewal_context_mismatch`).
- An operation is licensed for its `first_grant_revision` and for each accepted renewal's `to_revision` (`licensed_revisions`). A refused renewal licenses nothing. `operation_status` reproduces the producer's read-only judgement (`ok`, `not_admitted`, `collision`, `renewal_unrecorded`, mapped by `STATUS_REASON` to the reason codes).

Join rows (one per attempt, written before the attempt row):

- A join names an admitted operation (`join_operation_not_admitted`), of the same grant (`join_grant_mismatch`: the operation id is stable across revisions of one grant, not across grants) at a licensed revision (`join_revision_unlicensed`). One join per attempt (`duplicate_attempt_join`); a journal check licenses at most one attempt (`duplicate_join_check_id`).
- `merged_into` is null or names an admitted operation other than the join's own (`merged_into_not_admitted`, `merged_into_self`); it holds an operation id, never an attempt id. The field exists for a later merge stream; the Control Plane always writes null.

Journal context (J; the run record is not re-validated here, only the members read below):

- `journal_run_mismatch`: the run record is the document's run.
- Decisions: an authorized binding carries the issuer's `operation_id` once the ledger is non-empty (`decision_operation_id_missing`), names an admitted operation (`decision_operation_unadmitted`), the issuer recorded at admission (`operation_issuer_mismatch`), the principal and grant it was admitted under (`decision_operation_binding_mismatch`) and a licensed revision (`decision_revision_unlicensed`). The operation's `first_grant_revision` is the revision of its first authorized decision (`first_revision_mismatch`).
- Joins: the attempt exists with the join's effect and decision (`join_attempt_missing`, `join_attempt_mismatch`); the decision exists (`join_decision_missing`), is authorized (`join_decision_unauthorized`), carries the join's operation (`join_operation_mismatch`), grant and revision (`join_binding_mismatch`) and effect id (`join_effect_mismatch`). The join's `check_id` opens an effect-stage journal check (`join_check_missing`) naming the join's effect and decision (`join_check_lineage`) and completed (`join_check_not_completed`), and the same id names the effect-stage resolution check (`join_resolution_check_missing`).
- Shared ids, once the ledger is non-empty: every attempt has its join (`attempt_without_join`); every resolution check carries the id of a journal check of the same stage (`resolution_check_not_in_journal`); every refusal carries `check_id` (`refusal_check_id_missing`) naming an effect-stage resolution check (`refusal_check_missing`) whose journal check names the refusal's effect and decision (`refusal_check_lineage`). A refusal row that carries `check_id` is checked whether or not the ledger is non-empty.
- One effect per operation: two different effect ids both `acknowledged` or `partial` for one operation is `operation_committed_twice` (the destination dedupe failed). A last attempt row `failed` with error `operation_already_committed` needs another effect of the same operation that was `acknowledged`, `partial` or `unknown` (`rejection_without_committed_peer`).

Optional context (decision 39-L): a run record whose shape does not let the cross-document rules run is refused with the typed violation `context_malformed` instead of raising.

Succession (two exports of one run, `check_succession`, code `not_append_only`): every ledger list of the earlier export is a prefix of the same list in the later one.

## Destination capability

Where an operation id is dispatched, the destination is part of the contract even though its state is not in the run record. A conforming destination:

- D1. Declares the capability `operation-identity/0.1` (the Control Plane reads the attribute `operation_identity_capability`).
- D2. Receives the operation id with each `apply`/`commit`. A call without one behaves exactly as before.
- D3. For the same `effect_id` returns the legacy duplicate result. For a different `effect_id` under an operation that already has an effect, refuses with the definitive rejection `operation_already_committed` and records no effect, atomically with the effect write (the runtime destination uses one `BEGIN IMMEDIATE` transaction; the Control Plane's `LocalRefundDestination` its file lock).
- D4. A destination that cannot store the operation id refuses it (`operation_identity_capability_unavailable`) instead of dropping the dedupe.
- D5. The workflow, with the profile on and a destination lacking the capability, refuses dispatch before writing any attempt or join row (`operation_identity_capability_unavailable` as a `PermissionError`).
- D6. A definitive rejection is a `failed` attempt row whose `error` is the code, and the operation then has exactly one effect.

Only D5 and D6 leave rows. D1 to D4 are behaviours of the destination; they are stated, covered by the components' own tests, and not checkable from a record.

## Consumer-conformance note: enforced by the producer versus only in this contract

Checked against Control Plane `83b49b5` and runtime `63a7c0fe2` by reading the code and by capturing the valid fixtures from it.

Enforced by the Control Plane producer:

- `operation_id` presence and shape (hold with `operation_id_missing`, `operation_id_invalid`); admission on the first authorized decision with the issuer from the grant; collision and unrecorded-revision holds at decision time and again at effect time (`operation_grant_mismatch`, `operation_renewal_unrecorded`, `operation_not_admitted`).
- Renewal: not admitted, not by the issuer, not new; the refused row is persisted and `PermissionError` raised; `from_revision` and `grant_id` as above.
- One join per attempt (`ValueError` "attempt already joined"), written before the attempt row, including the single-row `reconciled_existing` rows; `check_id` shared across journal events, resolution checks, the join and refusal rows (decision stage and effect stage); dispatch refused without the destination capability; the destination's `operation_already_committed` becomes a `failed` row.
- The ledger/join/check lineage rules above hold by construction in every captured run (all valid fixtures pass them).

Only in this contract (no producer check; a producer bug would not be caught by the producer):

- Uniqueness of renewal, join and operation ids inside a document (ids are uuid4 or ledger-keyed; nothing re-checks), `duplicate_join_check_id`, `join_grant_mismatch`, `join_revision_unlicensed`, `first_revision_mismatch`, the renewal replay codes as a whole (the producer computes them but nothing re-verifies a stored row), `timestamp_invalid` on ledger rows (the producer writes aware times).
- `merged_into`: the Control Plane writes null and does not check the target. The runtime sidecar `OperationAdmissionRegistry.join_attempt` does refuse a merge that does not name an admitted operation, but the sidecar is unwired. Contract-only for the Control Plane path.
- `operation_committed_twice` and `rejection_without_committed_peer`: the Control Plane records what the destination said and never checks that two effects did not commit; the destination dedupe is the control.
- D1 to D4 live in destination code (`LocalRefundDestination`, `OperationIdentityDestination`); the Control Plane checks only the capability attribute (D5).

Divergences noted, none edited:

- The runtime sidecar `OperationAdmissionRegistry.record_renewal` refuses with `operation_not_admitted`, `operation_superseded` and `renewal_not_written_by_grant_issuer`; it has no revision check (it holds no revisions) so no `renewal_revision_not_new`, and `operation_superseded` (replan supersession) is not in this contract's closed set because the Control Plane never writes it. The sidecar is unwired; if it is wired in, either the contract or the sidecar changes first.
- The runtime destination keys the dedupe on `(principal, authority domain, operation id)`; the Control Plane's `LocalRefundDestination` keys on `operation_id` alone, and the Control Plane ledger binds an id to one principal, domain, issuer and grant. This contract treats `operation_id` as unique within a run's ledger and does not claim cross-principal collisions are detected by every destination.
- The journal contract refuses a raw run record with the profile on (see Document model).

## Fixtures

Each fixture file is `{fixture_id, synthetic, expected_outcome, reason, provenance, [expected_refusal], document, [journal]}`. `fixtures/valid/` must be accepted, alone and with `journal` when present. `fixtures/invalid/` must be refused with `expected_refusal` as the only violation (with `journal` when present: those pin the J rules). `journal` is the run record's members this contract reads (`run_id`, `decisions`, `attempts`, `check_events`, `resolution_checks`, `refusals`) with resolution inputs trimmed to the manifest and grant reads, as the journal fixtures do.

Valid (12): ten are captures of real runs of Control Plane `83b49b5` (the Control Plane's own `tests/test_operation_identity.py` helpers, synthetic proposals, fixed clock, throwaway stores, ids and process owner replaced by synthetic ones): `normal-attempted-acknowledged`, `renewal-accepted-second-revision`, `worker-self-renewal-refused-then-unrecorded-hold`, `renewal-refused-not-admitted-and-not-new`, `effect-time-refusal-carries-check-id`, `duplicate-submission-reconciled-existing`, `lost-ack-then-reconciled-existing`, `delayed-first-attempt-rejected-after-renewal` (the stalled first attempt, a renewal, a committed second effect and the definitive rejection), `operation-id-missing-held`, `operation-id-invalid-held`. Two are derived: `extension-namespace-members-preserved` (the normal capture plus `x-` members) and `merged-into-names-admitted-operation` (hand-built; no producer writes a non-null `merged_into`). `provenance` names the source of each. The scripts are in `provenance/`: `capture_fixtures.py` (needs a Control Plane checkout) writes the raw runs, `build_fixtures.py` normalises and projects them into the valid fixtures (re-running it on the same capture reproduces them byte for byte), `mutate_invalid_fixtures.py` regenerates the invalid ones. They are not tests and are not vendored.

Invalid (61): one or more per code above, single-defect mutations of the valid fixtures (each `provenance` names its base); `decision-operation-binding-mismatch` is the captured collision case. The cases the brief required are all present: unknown and non-issuer renewal writers, non-new revision, missing and invalid `operation_id`, a join for an unadmitted or foreign operation, `merged_into` naming an attempt id, a second effect for one operation, a refusal and a resolution check without the shared id.

## Run

```
python contracts/operation-identity/validate.py <document.json>...   # prints violations; fixtures wrap the document and an optional journal
PYTHONPATH=src python -m pytest -q tests/test_contract_operation_identity.py
```

`validate.py` is stdlib only and self-contained: a vendored copy (`contracts/tools/vendor_contract.py copy --contract operation-identity ...`) needs no sibling contract; the run record is passed in by the caller when wanted. The test suite also cross-checks `schema.json` against the `jsonschema` package when it is installed.

## What this does and does not show

A passing run shows the document's structure and these rules over the rows given. It does not show tamper evidence (a holder of the record store key can rewrite rows; the profile gives visibility to an honest reader), cross-host fencing, that the destination dedupe held (only that the record is consistent with it), or the N3 deadline and clock rules (a later stream). It records no behaviour the code lacks.

## Defaults taken (questions not asked, owner review at the end; every one is reversible while the contract is `0.1.0-draft`)

1. Carrier. Default: a sidecar projection document, not new members of the journal contract's run record (the journal contract stays unedited and closed). Reversible: a minor journal bump declaring the members as optional.
2. The three ledger lists are required in the sidecar though empty in a run that wrote none. Reversible: make them optional.
3. Journal-side additions (`check_id` on refusals, `operation_id` and `operation_issuer` in the binding extension, shared check ids) are checked only through the optional run-record context, never required of the document alone.
4. Ledger replay order is list (append) order. The single evaluation `now` of the producer means timestamps cannot order rows, so no rule compares `recorded_at` across lists.
5. Licensed revisions are judged on the end state of the ledger (first plus every accepted renewal), not as of each join's time.
6. The ledger counts as "on" (profile active) when `operations` is non-empty, unless the consumer passes `require_profile=True` (decision 37), which states that the host selected the profile and so keeps the ledger-dependent rules on for an empty ledger. A run with the profile on whose every decision held writes no ledger row and is outside the rules that need it (`attempt_without_join` and the others).
7. `merged_into` must name an admitted operation and not the join's own; it need not share the principal or authority domain (the runtime sidecar checks admission only).
8. Rejection and dedupe rules count `acknowledged` and `partial` as committed, and accept `unknown` (a lost acknowledgement) as a possible committer for a rejection. Absence of a committed peer is a violation, not a proof of a bug in the destination.
9. The closed reason-code set is the seven above; the validator's codes are separate strings and are not reason codes. `operation_superseded` (runtime sidecar) is not admitted.
10. `operation_id` is unique within a ledger. Cross-principal scoping of a destination's key is not modelled (see divergences).
11. The destination capability is a behavioural contract (D1 to D6), not a document member: the run record carries no destination state, and no destination state export was invented.
12. The profile adds no signature or integrity member. Integrity stays with the ODES export package and the consumer's digest.
13. Valid fixtures are captures from main, not hand-written; expected-today statements in them are from runs, not from reading.
14. The legacy `effect_id` keeps its meaning (owner decision 1 of the 101726_B consolidation): it still commits `{proposal, grant_id, grant_revision}` and changes on renewal; `operation_id` lives in this opt-in profile only.
15. No supersession (replan) record, merge record, delayed-commit clock or deadline rule is modelled; those are later streams.
16. Resolver identity (`resolver_id`, `resolver_version`) comes from host configuration and is an opaque non-empty string here.

## Versioning and change rules (0.x)

While the version is `0.x-draft` nothing is frozen and any change may break. Enumerations, when added, are closed (decision 6).

## Current conformance (2026-10-18, local runs, not a qualification)

- Producer, Control Plane `83b49b5`: all ten captured real runs pass every rule alone and with their run record. Gap: the raw run record is refused by the journal contract (see Document model); the sidecar is produced by projection, not by the Control Plane.
- Producer, runtime: the sidecar `OperationAdmissionRegistry` is unwired and differs as listed above; `OperationIdentityDestination` implements D1 to D4 (its 13 tests in `tests/test_n1_operation_identity.py` were run here: 13 passed).
- Consumer: none. No consumer reads the sidecar.

## Input hardening (decision 32, 2026-10-18)

The reference validator never raises: any parsed JSON value gets a list of typed violations. Non-finite numbers (NaN, Infinity) and text that is not valid Unicode are refused as `schema_violation`; `main()` reads files with a strict loader (duplicate members, NaN, Infinity, overflowing numbers and non-UTF-8 input are refused, exit status 2, line `input_refused`); schema patterns match the whole string (`(?!\n)$` in `schema.json`) and times are ISO-8601 with ASCII digits and a UTC offset. No code, member or accepted form changed meaning; no code was added.

Invalid fixtures added: `non-ascii-digit-time`, `trailing-line-break-digest`, `trailing-line-break-time`, `unpaired-surrogate-text`.
