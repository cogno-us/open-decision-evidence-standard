# Effect reversibility extension profile

Version: `0.1.0-draft`. Status: draft, proposal only, optional. Not frozen (the first freeze is deferred by the owner), not part of `pder-v0.1`, not referenced by any `odes` code path, not a qualification input. See `docs/engineering/ODES-INTERCOMPONENT-CONTRACTS.md` (Appendix C, section 12 item 19) for the design context, `contracts/control-plane-journal/` for the contract this one is layered on, and `contracts/bounded-deferral/` for the DEFER rule it reuses. Nothing here edits those contracts, the lifecycle contract, the core schema or `pder-v0.1`.

## Contract statement

Two ideas, one optional extension on action classes:

- **Effect class** `x-effect-class`: `stageable | stallable | blocking` (the KAIROS-paper idea, as the owner's brief summarised it). It says what may be done with an effect while a decision is still open (a DEFER, see `bounded-deferral`).
  - `stageable`: prepared without being observable (phase `stage`), made observable by a later `commit`.
  - `stallable`: started but held at a stall point (phase `start_stalled`, not observable), made observable by `release_stalled`.
  - `blocking`: no preparatory phase; the only phase is `send`, and it is observable at once.
- **Reversibility** `x-reversibility.reversibility`: `irreversible | reversible_until | reversible_at_cost` (the L4 item of addendum 101726_B, as summarised in the brief). Reads of protected data are irreversible. A cached "open" snapshot is accepted only for reversible classes within the age bound. A recorded closure overrides the cache. Where the counterparty condition is unobservable the stricter value applies.

Mapping onto the core, which stays as it is: the Control Plane action class is `{class_id, irreversible, max_status_age_seconds, on_unreadable}` and appears in the journal as an open object (`check_events[].action_class`). A producer that implements this profile adds the two members `x-effect-class` and `x-reversibility` to that object; the journal contract accepts them as it stands (a test pins this). The profile document `effect-reversibility` is a sidecar that restates the class profiles it relies on and records the decisions taken against them: snapshot uses, dispatches, and lost acknowledgements. It can be checked alone or with the journal run record and a conforming `bounded-deferral` document as context (`validate(doc, journal, deferrals)`); neither is re-validated.

What the code did when this draft was written (cogno-us/cognous-control-plane #42, authoritative then; see the update paragraph below for the Control Plane at `3cd17ead`): the action class carries a boolean `irreversible` and the delay bound `max_status_age_seconds` (default 60, failing closed to `hold`); it has no effect class, no `reversible_until`, no reversal cost and no snapshot cache with a recorded-closure override; `safe_to_retry` is a type literal only and never emitted; the check lease is a blocking flock; no operation-level id exists outside the unwired `OperationAdmission` sidecar. This profile describes what a producer would record; when it was written no component implemented it, and it records no behaviour the code lacked. `irreversible` (the code's field) is kept and tied to `reversibility` (below). An authority tier table is not used (the code has none).

Update 2026-10-18 (docs only, read from the Control Plane at `3cd17ead`): the Control Plane now implements the reversibility part as an opt-in profile (`reversibility/0.1`, `src/agent_control_plane/reversibility.py`, selected only by `RuntimeAuthorityProfile.reversibility`; with it unset nothing changes). It takes `x-reversibility` on the action class (the legacy `irreversible` boolean stays derived), accepts a cached "open" purpose snapshot only for a reversible class within its age bound and while no recorded closure exists, and appends a `snapshot_use` row for each use. It does not implement `x-effect-class`, the dispatch records or the lost-acknowledgement records of this profile, and it does not read or write the `effect-reversibility` sidecar document. Operation identity (the `OperationAdmission` sidecar) is also implemented there as an opt-in profile. The statements above about the code of that time are history, not the present state.

A conforming document states `contract: "effect-reversibility"` and `contract_version: "0.1.0-draft"`. `schema.json` (JSON Schema draft 2020-12) defines members, types and enumerations; the rules below are implemented by `validate.py`.

## Member model

Same model as the journal contract.

1. Required: `contract`, `contract_version`, `class_profiles`. Optional: `producer`, `run_id`, `snapshot_uses`, `dispatches`, `lost_acks`, `extensions`. A class profile carries all its members; the two `x-` members `x-effect-class` and `x-reversibility` are declared members (they are the `x-` members a producer adds to the action class), and `x-reversibility` carries all five of its members (null where not applicable).
2. Closed member sets. An undeclared member outside `extensions` is `undeclared_member`, never dropped.
3. `extensions` (names `^x-[a-z0-9][a-z0-9._-]*$`, else `invalid_extension_key`) on the document, a class profile, and each record; consumers ignore them for contract logic, preserve them, and include them in any digest. Snapshots, closures and the reversal cost carry none.
4. Closed enumerations (`unknown_enum_value`): effect class, reversibility, phase, snapshot status, snapshot basis, effective status, lost-ack classification and required action. A new value is a major bump.
5. Times are ISO-8601 with a UTC offset (`timestamp_invalid`).
6. Adding an optional member is a minor bump; adding a required member or an enumeration value is a major bump.

## Rules

Structural codes (level S): `schema_violation`, `undeclared_member`, `unknown_enum_value`, `invalid_extension_key`, `unsupported_contract_version`. The rest are rule codes (level L).

Identity: class ids are unique (`duplicate_class_id`); ids within `snapshot_uses`, `dispatches` and `lost_acks` are unique (`duplicate_record_id`); a record's `class_id` names a class profile in the document (`dangling_class_reference`) and its `effect_class` is that profile's (`class_profile_mismatch`).

Class profile:

- `reversible_until` is set if and only if reversibility is `reversible_until`; `reversal_cost` is set if and only if `reversible_at_cost` (`reversibility_member_mismatch`).
- The action class's `irreversible` flag is true if and only if reversibility is `irreversible` (`irreversible_flag_mismatch`). The flag stays the code's own field; the profile adds precision for the two reversible values.
- A class that reads protected data is `irreversible` (`protected_read_not_irreversible`). A read cannot be taken back.
- Where `counterparty_observable` is false the stricter value applies, `irreversible` (`unobservable_not_strict`). Order of strictness: `irreversible` over `reversible_at_cost` over `reversible_until`.

Snapshot use (what a decision relied on for "is the counterparty still open"). `basis` is `live_read`, `cached_snapshot` or `strict_default`; `effective_status` is `open` or `closed`:

- A live read or cached snapshot carries a snapshot, the strict default none (`snapshot_basis_mismatch`). The strict default is `closed` (`strict_default_not_closed`): when the status cannot be read, or the counterparty is unobservable, the use fails closed.
- A snapshot is not observed after it is used (`snapshot_time_invalid`).
- A cached snapshot is accepted only for a reversible class (`cache_on_irreversible_class`; irreversible effects, protected reads and unobservable counterparties need a live read), before `reversible_until` for a `reversible_until` class (`cache_after_reversal_window`: after the window the class is treated as irreversible), and not older than the class `max_status_age_seconds`, inclusive (`snapshot_stale`).
- A recorded closure whose `recorded_at` is not after the use overrides the snapshot, cached or live: the effective status is `closed` (`recorded_closure_overridden`).
- Effective `open` needs a snapshot that says `open`; a `closed` or `unknown` snapshot gives `closed` (`effective_status_unsupported`).

Dispatch (a step taken for an effect). `open_deferral_ids` lists the deferrals open at `dispatched_at` for the same proposal commitment (see `bounded-deferral`):

- The phase belongs to the effect class: stageable `stage`, `commit`; stallable `start_stalled`, `release_stalled`; blocking `send` (`phase_class_mismatch`).
- A blocking effect is never sent while a DEFER is open (`blocking_sent_while_deferred`). While a DEFER is open a stageable effect may only be staged and a stallable one only started stalled; `commit` and `release_stalled`, which make the effect observable, wait for the release (`observable_while_deferred`). This is the reversibility side of "no effect is observable before RELEASE".
- With the deferral document as context, the open set is computed (same proposal commitment, `opened_at` not after the dispatch, not yet resolved; resolution instant exclusive) and must equal `open_deferral_ids` (`open_deferral_mismatch`).

Lost acknowledgement (the journal's lost-ack shape: an attempt whose last row is `unknown`; case D04 of the addendum numbering). The lost phase fixes the classification:

| Lost phase | classification | required action |
|---|---|---|
| `stage` | `no_external_effect` | `discard_staged` |
| `start_stalled` | `no_external_effect` | `cancel_or_resume_stalled` |
| `commit`, `release_stalled`, `send` | `external_effect_possible` | `reconcile_by_observation` |

A record that differs is `lost_ack_misclassified`; a phase outside the class is `phase_class_mismatch`. `retry_eligible` is always false (schema constant, the journal's own rule: observed absence never establishes retry eligibility after an attempt). `reversal_available` is never true for an irreversible class (`reversal_claimed_for_irreversible`).

Context (optional; each needs another document):

- Journal: `journal_run_mismatch`; `class_profile_journal_mismatch` (`irreversible` and `max_status_age_seconds` equal the action class recorded for that `class_id`); `lost_ack_attempt_mismatch` (a lost ack names an attempt of that effect whose last row is `unknown`).
- Deferrals: `open_deferral_mismatch` (above).

## Fixtures

Each fixture file is `{fixture_id, synthetic, expected_outcome, reason, [expected_refusal], document}`. `fixtures/valid/` must be accepted; `fixtures/invalid/` must be refused with `expected_refusal` as the only violation. All fixtures are synthetic and hand-built (no producer implements the profile). The valid lost-ack fixture reuses the identifiers of the journal fixture `lost-ack-unknown-then-closeout`, and the deferral context tests use `bounded-deferral` fixtures.

Valid (19): class profiles for the three effect classes plus protected-read and unobservable classes; cached snapshots accepted within bounds; live read on an irreversible class; recorded closure overriding a cached open; unobservable counterparty defaulting strict; stage and stalled start allowed while deferred; commit after release; blocking send with no open deferral; lost-ack classified for stage, stalled start, commit and send; extensions preserved; a class catalog alone, and a cached snapshot at exactly the age bound (decision 35). Invalid (47): one or more per code above, plus the five added by decision 32 (`non-ascii-digit-time`, `seconds-bound-out-of-range-class`, `trailing-line-break-digest`, `trailing-line-break-time`, `unpaired-surrogate-text`) and two by decision 35 (`time-seven-fraction-digits`, `cached-snapshot-used-at-the-window-end`). Context rules are pinned in `tests/test_contract_effect_reversibility.py`.

## Run

```
python contracts/effect-reversibility/validate.py <document.json>...   # prints violations; fixtures wrap the document
PYTHONPATH=src python -m pytest -q tests/test_contract_effect_reversibility.py
```

`validate.py` is stdlib only and self-contained: a vendored copy (`contracts/tools/vendor_contract.py copy --contract effect-reversibility ...`) needs no sibling contract; the journal and deferral documents are passed in by the caller when wanted. `CONTRACT.json` is not generated here (no component vendors it yet). The test suite cross-checks `schema.json` against the `jsonschema` package when installed.

## What this does and does not show

A passing run shows structure and these rules. It does not show that a producer classified an effect correctly, that a counterparty is in fact open or closed, that a snapshot is authentic, that a cached value was fresh when stated, or that the destination honoured a stall. It adds no field to the core schema or `pder-v0.1`. The Control Plane implements only the opt-in reversibility part (see the update above), not the effect class, dispatch or lost-acknowledgement parts.

## Defaults taken (questions not asked, owner review at the end; every one is reversible while the contract is `0.1.0-draft`)

1. Where the fields live. Default: two `x-` members on the action class (`x-effect-class`, `x-reversibility`) plus a sidecar document; nothing in the core schema, the journal contract or `pder-v0.1`. Reversible: promote to core members in a major bump.
2. Effect class meaning. Default: defined by which phases are allowed and which are observable (stageable `stage`/`commit`, stallable `start_stalled`/`release_stalled`, blocking `send`). The KAIROS wording was not available to the worker; this follows the owner's one-line description.
3. Order of strictness. Default: `irreversible` over `reversible_at_cost` over `reversible_until`.
4. The code's boolean `irreversible` is kept and equals "reversibility is `irreversible`". `reversible_at_cost` therefore has `irreversible` false. Reversible: map `reversible_at_cost` to true.
5. "Unobservable counterparty condition" defaults to `irreversible` for the class, and to the strict default (`closed`) for a snapshot use. The profile has no separate unknown value for reversibility.
6. Reads of protected data are `irreversible`, and `reads_protected_data` is a producer assertion, not derived. A protected read needs a live read, never a cache.
7. Cached snapshot bound: the class `max_status_age_seconds`, inclusive. A deployment cannot set a longer cache age than the class bound in this profile.
8. After `reversible_until` passes the class is treated as irreversible for cache purposes (no cache). The window itself is a producer-declared time.
9. A recorded closure overrides any snapshot, live or cached, once recorded (its `recorded_at` is not after the use). A reopening is not modelled.
10. `reversal_cost` is opaque text; no amount, currency or bound is modelled.
11. "A blocking effect is never sent while a DEFER is open" is scoped by proposal commitment: deferrals open for the same proposal. Cross-proposal ordering and dependency groups are not modelled. For stageable and stallable effects, only staging and a stalled start may precede the release.
12. The open set at dispatch is a producer assertion (`open_deferral_ids`), checked against the `bounded-deferral` document only when supplied. Resolution instant is exclusive.
13. Lost-ack (D04) classification is by lost phase only. A lost acknowledgement of a stage or stalled start leaves no external effect; of a commit, a release or a send it never allows a retry and requires reconciliation by observation, consistent with the journal's single-lifecycle rule. The identifier "D04" is taken from the brief's addendum numbering and could not be checked against the addendum text.
14. `reversal_available` is a producer assertion, only forbidden for irreversible classes. Whether a reversal is correct after the window or cost is not modelled.
15. Snapshot status vocabulary is `open | closed | unknown`; `unknown` can never support an effective `open`.
16. No `deny`, no `safe_to_retry`, no core change, no edit of any existing contract; the profile is not wired into any code path.

Source of the design: the owner's programme brief of 2026-10-17 (the KAIROS-paper effect classes and the L4 item of 101726_B as summarised to the worker). The addendum and paper text were not available to the worker, so their exact wording is not quoted.

## Input hardening (decision 32, 2026-10-18)

The reference validator never raises: any parsed JSON value gets a list of typed violations. Non-finite numbers (NaN, Infinity) and text that is not valid Unicode are refused as `schema_violation`; `main()` reads files with a strict loader (duplicate members, NaN, Infinity, overflowing numbers and non-UTF-8 input are refused, exit status 2, line `input_refused`); schema patterns match the whole string (`(?!\n)$` in `schema.json`) and times are ISO-8601 with ASCII digits and a UTC offset. No code, member or accepted form changed meaning; no code was added.

Invalid fixtures added: `non-ascii-digit-time`, `seconds-bound-out-of-range-class`, `trailing-line-break-digest`, `trailing-line-break-time`, `unpaired-surrogate-text`.

- `context_malformed`: an optional context argument (the run record, or for effect-reversibility also the deferral document) whose shape does not let the cross-document rules run is refused with this typed violation instead of raising. The context is not re-validated against its own schema here.
