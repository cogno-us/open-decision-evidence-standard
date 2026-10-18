# Freshness clocks extension profile

Version: `0.1.0-draft`. Status: draft, proposal only, OPTIONAL extension profile. Not frozen (the first freeze is deferred by the owner), not part of the ODES core or `pder-v0.1`, not referenced by any `odes` code path, and not a qualification input. See `docs/engineering/ODES-INTERCOMPONENT-CONTRACTS.md` (Appendix C, section 12 item 22) for the index and the decisions. Nothing here edits the journal contract, the lifecycle contract, the operation-identity contract, the core schema or `pder-v0.1`.

## Contract statement

A status read licenses an effect only while it is fresh, and "fresh" needs three clocks that the legacy record collapses into one. This profile records them (`evaluated_at`, the one evaluation pass; `recorded_at`, the service clock re-read at each write; `observed_at`, the source's own stamp), fixes a deadline for each check at its opening (`opened.recorded_at + age_bound_seconds`), withdraws the licence of a check that outlives its deadline before dispatch (the terminal `expired` phase, with the refusal `check_expired_before_dispatch`), reports a live check past its deadline once without closing it (the non-terminal `overdue` phase), records how the age of each read is known (`age_basis`: `nonce_bound` where the resolver echoes a per-check nonce, otherwise `source_asserted`), and records an outage extension of an age bound as a signed, independent, limited decision (`age_extension`, with `age_extension_refusal` rows kept). A recovery pass leaves a `recovery_run` row. Ten reason codes belong to the profile.

The profile is optional and opt-in. It is selected only by the host-governed `RuntimeAuthorityProfile.freshness` setting (`FreshnessProfile`) in the Control Plane; with it unset nothing in this contract applies, no run record member appears and no stored or hashed byte changes (the default path is the journal contract as it stands). Once set, the profile is covered by the approval commitment.

Shapes and rules were read from the merged code, not from the proposal:

- Control Plane `src/agent_control_plane/freshness.py`, `bounded.py` (`append_check_event`, `recovery_pass`, `record_age_extension`, the dispatch gate `_refuse_expired_before_dispatch`, `execute`) and `reason_vocabulary.py` at main `3f6a7668` (N3 merged in #47). Control Plane #47 and qualification #99 bodies (the "Proposed ODES contract delta" is the spec of this draft) and runtime #110 were read for intent; where they differ from the code, the code wins (see Divergences).
- Runtime `engine/delayed_commit_destination.py` at main `6bfb77ee` (#110), for the destination capability only.

The valid fixtures are captures of real runs of the Control Plane's own flows (see Fixtures), not hand-written documents.

## Document model

A sidecar projection of one run, `contract: "freshness-clocks"`, `contract_version: "0.1.0-draft"`, `profile: "freshness/0.1"`, `run_id`, optional `producer`, and seven lists (required here, possibly empty; the producer omits the three record lists while empty):

| List | Row | Written |
|---|---|---|
| `check_events` | one row per journal event, in order: `check_id`, `phase` (`opened`, `input`, `completed`, `interrupted`, `overdue`, `expired`), `stage`, `recorded_at`, `reasons`; optional `evaluated_at`, `deadline`, `age_bound_seconds`, `extension_id`, `nonce` | by the check journal; `overdue` by `recovery_pass`, `expired` at the dispatch gate |
| `clock_rows` | `row_type` (`decision`, `attempt`, `refusal`, `resolution_check`, `attempt_join`, `operation`, `operation_renewal`), `row_id`, `seq`, `recorded_at`, optional `evaluated_at`, and (refusal only) `deadline` | one per run record row that carries the profile's clock members |
| `input_reads` | `row_type` (`decision`, `refusal`, `resolution_check`), `row_id`, `check_id` (null for a decision), `input_type`, `input_id`, `age_basis`, `read_state`, `expected_nonce`, `observed_nonce` | one per non-manifest read that carries an `age_basis` |
| `age_extensions` | `extension_id`, `class_id`, `from_max_age_seconds`, `to_max_age_seconds`, `not_before`, `expires_at`, `outage_ref`, `requested_by`, `signer`, `authority_ref`, `recorded_at`, optional `evaluated_at` | by `record_age_extension` when the extension counts |
| `age_extension_refusals` | `refusal_id`, `extension` (the refused row), `reasons`, `recorded_at` | by `record_age_extension` for every refused attempt |
| `recovery_runs` | `run_id`, `trigger` (`startup`, `interval`, `manual`), `recorded_at`, `interrupted`, `overdue`, `open_count`, `oldest_open_age_seconds` | by the reaper, one per pass |
| `freshness_reports` | `report_id`, `report` (`as_of`, `open_count`, `abandoned_open_count`, `overdue_count`, `expired_before_dispatch_count`, `oldest_open_age_seconds`) | an envelope around the verbatim `freshness` block of `refusal_trends(..., check_events=, as_of=)` |

Why a projection: the journal contract is closed (`additionalProperties` false) and, at `0.1.0-draft`, declares none of the profile's members. See Journal divergence. This contract carries the profile's rows and states the journal-side additions as cross-document rules over the run record. Making the journal contract declare them as optional members is a possible minor bump (recommended, not done here; it is the owner's call).

Update (2026-10-18, journal draft revision 2, decision 23): the journal contract now declares this profile's members as optional, so a raw run record produced with the profile on is accepted by it; this contract stays the owner of their semantics. Statements below that the journal contract declares none of the members or refuses the record describe draft revision 1 and are kept as the record of why the sidecar form was chosen.

Journal-side additions, described here and checked through the optional journal context: (a) `evaluated_at` and `recorded_at` on decisions, attempt rows and resolution checks (`recorded_at` only on a resolution check, which already carries `evaluated_at`), `evaluated_at` and `deadline` on effect-time refusal rows, `evaluated_at` on operation, renewal and join rows (a join and a renewal also carry their own `recorded_at`; an operation row's write time is its existing `admitted_at`); (b) `evaluated_at`, `deadline`, `age_bound_seconds`, `extension_id` and `nonce` on check events, and the phases `overdue` and `expired`; (c) `age_basis` on resolution inputs and the `read_state` value `nonce_mismatch`; (d) the records `age_extensions`, `age_extension_refusals`, `recovery_runs`.

## Member model

Same model as the journal contract.

1. All declared members of a row are required, except `producer`, `extensions`, and on a check event, a clock row and an extension row the optional members named in the table. A verbatim producer report (`report` of a `freshness_reports` row) carries no `extensions`; its envelope may.
2. Closed member sets. An undeclared member outside `extensions` is `undeclared_member`, never dropped.
3. `extensions` (names `^x-[a-z0-9][a-z0-9._-]*$`, else `invalid_extension_key`) on the document and on each row and envelope. Consumers ignore them for contract logic, preserve them, and include them in any digest.
4. Closed enumerations (`unknown_enum_value`): check `phase` (six values), `stage` (`decision`, `effect`, `claim`), clock `row_type` (seven), input-read `row_type` (three), `age_basis` (`nonce_bound`, `source_asserted`), `read_state` (null, `unreadable`, `cached_positive`, `nonce_mismatch`), recovery `trigger` (three), and the six extension refusal reasons. A new value is a major bump.
5. Times are ISO-8601 with a UTC offset (`timestamp_invalid`) and are compared as instants. `age_bound_seconds` is an integer of at least 0. Nonces are non-empty strings (the producer draws 32 hex characters).
6. Adding an optional member is a minor bump; adding a required member or an enumeration value is a major bump.

## Reason codes

Ten codes of the Control Plane reason registry (138 codes at main after N3, 128 before; all `typed_only`) belong to the profile. They are producer reason codes, not validator codes; the validator's own codes are listed under Rules.

| Code | Where it appears | Meaning |
|---|---|---|
| `check_expired_before_dispatch` | refusal row reasons, `expired` event reasons, attempt `error` of a `failed` row | the service clock, re-read immediately before dispatch, is past the check's deadline: nothing reached the destination |
| `check_overdue` | `overdue` event reasons, the recovery report | a live check is past its deadline; reported once, never closed |
| `check_lease_unavailable` | decision reasons (hold), resolution check reasons | the per-check lease could not be taken before `lease_acquire_timeout_seconds`; no read happened |
| `status_nonce_mismatch` | decision, refusal and resolution check reasons | a read echoed a nonce other than the check's (a replay); the read is rejected and both nonces are kept |
| `age_extension_unsigned` | extension refusal reasons; decision reasons (re-check at use) | no signer: never counts |
| `age_extension_self_signed` | same | the signer is the requester |
| `age_extension_signer_not_configured` | same | the signer is outside the rule-revision signer set now configured |
| `age_extension_exceeds_limit` | same | the raise is above `max_age_extension_seconds` (default 0: no extension is possible) |
| `age_extension_invalid` | same | the bound does not rise, the window is empty, or the id was already used |
| `age_extension_authority_unconfigured` | same | no rule-revision profile (N2) is configured, so there is no signer set |

`check_overdue` is a recovery report state and a journal marker, not a refusal reason of a decision; it is registered because the journal carries it.

## Capabilities

Descriptions only; neither is a document member and neither is checked by a rule beyond what a record shows.

- `status-nonce/0.1` (resolver). A resolver that declares it implements `nonce_read(nonce, method_name, *args) -> (record, echoed_nonce)`. The reader sends one nonce per check with each read and compares the echo. An equal echo makes the read `age_basis: nonce_bound` (proof only that the response was produced after the reader issued its nonce); a different echo is `read_state: nonce_mismatch`, `age_basis: source_asserted`, both nonces retained in `expected` and `observed`, and the reason `status_nonce_mismatch`; a resolver without the capability, or a profile with `nonce` off, gives `source_asserted` (the age is what the source asserts). A purpose-status read is `source_asserted` today.
- `delayed-commit/0.1` (destination; CI and local aid only, runtime #110). A destination that declares it offers three controls: `pause_at` (called with `"observe"` or `"commit"` and a callback) runs a one-shot callback at that point of the next call; `defer_next_commit` makes the next commit go into an in-flight set with its acknowledgement lost (a `TimeoutError`; nothing is durable, so an observation says `absent`); `land` lands a deferred commit through the real commit path, under every guard of the base destination (operation dedupe, effective grant, cumulative cap). There is deliberately no committed-but-invisible state. It adds no record member: a deferred commit shows as an attempt with status `unknown`, and a landed one as the destination's normal acknowledgement. Legacy destinations are untouched.

## Rules

Document rules need only the document. Cross-document rules need the optional run record (`journal`) or host configuration (`host`: `signers`, the rule-revision signer set or null when that profile is not configured; `max_age_extension_seconds`; `resolver_capability`, the declared capability or null); a rule whose context is absent is skipped, not assumed.

| Code | Rule |
|---|---|
| `accepted_extension_authority_unconfigured` | with host `signers` null, no extension is accepted |
| `accepted_extension_exceeds_limit` | with the host limit supplied, an accepted extension does not raise the bound above it |
| `accepted_extension_invalid` | an accepted extension raises the bound and has a non-empty window |
| `accepted_extension_self_signed` | an accepted extension's signer is not its requester |
| `accepted_extension_unsigned` | an unsigned extension is refused and kept as a refusal row, never accepted |
| `check_event_after_close` | no event follows a terminal event (`completed`, `interrupted`, `expired`), except `expired` after `completed` |
| `check_event_clock_drift` | every later event of a check carries the opening's `deadline`, `age_bound_seconds`, `extension_id` and `nonce`, and its `evaluated_at` when present |
| `check_event_time_regression` | `recorded_at` does not move backwards within a check |
| `check_events_mismatch` | the sidecar's check events are the run record's, member for member, in order |
| `check_opening_missing` | the first event of a check is its opening |
| `clock_row_mismatch` | a clock row is the row's `evaluated_at`, `recorded_at` and `deadline` |
| `clock_row_missing` | every run record row that carries the profile's clock members has a clock row |
| `clock_row_unknown_row` | a clock row names a run record row that carries them |
| `deadline_members_incomplete` | `deadline` and `age_bound_seconds` are carried together on the opening or not at all |
| `deadline_mismatch` | `deadline` is the opening's `recorded_at` plus `age_bound_seconds` |
| `duplicate_check_opening` | a check is opened once |
| `duplicate_clock_row` | one clock row per row type, id and sequence |
| `duplicate_extension_id` | accepted extension ids are unique (a reused id is refused as invalid) |
| `duplicate_extension_refusal_id` | extension refusal ids are unique |
| `duplicate_input_read` | one input read per row and input |
| `duplicate_recovery_run_id` | recovery run ids are unique |
| `duplicate_report_id` | report ids are unique |
| `evaluation_alias_mismatch` | `decided_at` and `started_at` keep their evaluation-time meaning: they equal `evaluated_at` |
| `expired_after_closed_check` | `expired` is allowed after `completed`, never after `interrupted` or `expired` |
| `expired_attempt_not_failed` | `check_expired_before_dispatch` is only the error of a `failed` attempt row |
| `expired_attempt_without_refusal` | an attempt failed with it has a refusal row with that reason for its effect |
| `expired_check_dispatched` | a join row whose check expired names a `failed` attempt: an expired check licensed no dispatch |
| `expired_not_past_deadline` | an `expired` event is written after the check's deadline |
| `expired_refusal_deadline_mismatch` | the refusal's `deadline` is the check's deadline |
| `expired_refusal_mismatch` | a check has an `expired` event if and only if a refusal with the reason names it by `check_id` |
| `expired_without_deadline` | an `expired` event needs a check opened with a deadline |
| `expired_without_failed_attempt` | the refusal's effect has an attempt `failed` with the reason |
| `extension_bound_mismatch` | with an `extension_id`, `age_bound_seconds` is the extension's `to_max_age_seconds` |
| `extension_outside_window` | the extension window covers the check's evaluation pass |
| `extension_reason_unexplained` | with host context, an extension reason on a decision needs an extension, active at the evaluation pass, that shows that defect under the host configuration |
| `extension_recorded_after_use` | an extension recorded after a check's opening cannot have raised its bound |
| `extension_refusal_reason_mismatch` | each reason names a defect the embedded extension shows (reasons that need host configuration are checked when it is supplied) |
| `extension_refusal_reasons_not_canonical` | reasons are sorted and unique |
| `extension_refusal_time_mismatch` | a refusal is recorded at the extension's own `recorded_at` |
| `extension_unknown` | an `extension_id` names an `age_extensions` row |
| `freshness_counts_mismatch` | the counts are derived from the document's check events as of `as_of` (`freshness_counts`) |
| `input_read_check_unknown` | an input read's `check_id` names a check opened in `check_events` |
| `input_read_mismatch` | an input read is the input's `age_basis`, `read_state` and nonces |
| `input_read_missing` | every non-manifest input that carries an `age_basis` has an input read |
| `input_read_unknown_input` | an input read names such an input of a run record row |
| `invalid_extension_key` | an `extensions` name not matching `^x-[a-z0-9][a-z0-9._-]*$` |
| `journal_run_mismatch` | the sidecar and the run record describe the same run |
| `lease_unavailable_dispatched` | a decision held for `check_lease_unavailable` has no attempt |
| `lease_unavailable_with_other_reasons` | `check_lease_unavailable` is the only reason of its decision |
| `nonce_bound_without_capability` | `nonce_bound` needs a resolver that declares `status-nonce/0.1` (host context; one finding per document) |
| `nonce_bound_without_nonce` | a `nonce_bound` read belongs to a check that sent a nonce (one finding per check) |
| `nonce_expected_not_check_nonce` | the expected nonce of a mismatch is the nonce the check sent |
| `nonce_members_inconsistent` | `nonce_mismatch` carries two different nonces; any other read carries none |
| `nonce_mismatch_basis` | a mismatched read is never `nonce_bound` |
| `nonce_reason_mismatch` | `status_nonce_mismatch` is a reason of a decision, refusal or resolution check if and only if an input ended in `nonce_mismatch` |
| `nonce_reused_across_checks` | a nonce belongs to one check |
| `not_append_only` | successive exports describe one run and the six row lists only grow (`check_succession`) |
| `overdue_before_deadline` | an `overdue` event is written after the check's deadline |
| `overdue_repeated` | a check is reported overdue once |
| `overdue_without_deadline` | a check opened without a deadline is open but never overdue |
| `phase_reasons_mismatch` | an `overdue` event carries exactly `check_overdue`, an `expired` event exactly `check_expired_before_dispatch` |
| `prior_attempt_not_excluded` | the journal contract's one-lifecycle rule with the profile's exclusion: an effect has at most one attempt lifecycle starting `attempted`, not counting one whose latest row is `failed` with `check_expired_before_dispatch` |
| `profile_rows_mismatch` | the sidecar's extension, refusal and recovery rows are the run record's rows |
| `recorded_before_evaluated` | `recorded_at` does not precede `evaluated_at` |
| `recovery_interrupted_without_event` | each interrupted check has an `interrupted` event stamped with the pass time |
| `recovery_overdue_without_event` | each overdue check has an `overdue` event written at or before the pass |
| `recovery_run_oldest_age_inconsistent` | `oldest_open_age_seconds` is null if and only if `open_count` is 0 |
| `recovery_run_open_count_below_overdue` | `open_count` includes every overdue check |
| `schema_violation` | a missing required member, wrong type, pattern or range |
| `timestamp_invalid` | times are timezone-aware |
| `undeclared_member` | a member that is not declared, outside `extensions`; never dropped |
| `unknown_enum_value` | a value outside a closed enumeration |
| `unsupported_contract_version` | `contract_version` is not `0.1.0-draft` |

Terms the rules use: an *expired* check is terminal: its licence was withdrawn at the dispatch gate and its failed attempt is excluded from the prior-attempt rule, so a retry opens a new check with a new deadline and nonce; an *overdue* check is alive: it is reported once, never closed by the pass, and its owner may still complete it; a check opened without a deadline (the legacy shape) is open but can never be overdue; `freshness_counts` counts a check open when it has no terminal event, abandoned when it has an `interrupted` event, expired when it has an `expired` event.

## Consumer-conformance note: enforced by the producer versus only in this contract

Checked against Control Plane `3f6a7668` by reading the code and by capturing the valid fixtures from it.

Enforced by the Control Plane producer (a refused write or a gate; the rule is what a stored row must also satisfy):

- `append_check_event`: opening first, one opening, no event after a terminal event, `expired` once and never after recovery closed the check, `overdue` once, owner match (the owner is not modelled here). Rules `check_opening_missing`, `duplicate_check_opening`, `check_event_after_close`, `expired_after_closed_check`, `overdue_repeated`.
- The dispatch gate (`_expired_before_dispatch`, strict `now > deadline` against the service clock re-read immediately before `destination.apply`) and the recovery pass (`at > deadline`): `expired_not_past_deadline`, `overdue_before_deadline`; the recovery pass never closes a live lease past its deadline.
- `record_age_extension`: a refusal row is persisted and `AgeExtensionRefused` raised for each defect (`extension_defects`), and authority is re-checked at every use (`effective_age_bound`): `accepted_extension_*`, `extension_refusal_reason_mismatch`, `extension_refusal_reasons_not_canonical`.
- The read path: a nonce is sent only to a resolver that declares the capability; an unequal echo is `nonce_mismatch` and never `nonce_bound`. The prior-attempt filter in `execute` excludes a `failed` attempt whose error is `check_expired_before_dispatch` (`prior_attempt_not_excluded` mirrors it).

Only in this contract (the producer writes these by construction, with no re-check of a stored row; a producer bug would not be caught by the producer):

- `deadline_mismatch`, `deadline_members_incomplete`, `check_event_clock_drift`, `phase_reasons_mismatch`, `extension_*` reference rules, `extension_refusal_time_mismatch`, `nonce_*` coupling rules, `input_read_*`, `clock_row_*`, `evaluation_alias_mismatch`, `profile_rows_mismatch`, `check_events_mismatch`.
- Contract-only by design: `recorded_before_evaluated` and `check_event_time_regression` (the producer reads the service clock at each write but compares it with nothing, so a clock that steps backwards produces a record these rules refuse), `nonce_reused_across_checks`, uniqueness of ids, `freshness_counts_mismatch`, `recovery_run_*` consistency, `not_append_only`.
- The three writes of a gate refusal (the failed attempt row, the refusal row, the `expired` event) are separate transactions: a crash between them leaves a record the coupling rules (`expired_attempt_without_refusal`, `expired_refusal_mismatch`, `expired_without_failed_attempt`) refuse. The producer does not repair it.

## Divergences (code against the PR bodies and the proposed delta; the code wins)

- Operation rows have no `recorded_at` member: the producer stamps `admitted_at` with the service clock under the profile and adds `evaluated_at`. A renewal row and a join row add `evaluated_at` next to their existing `recorded_at`. The clock row for an operation uses `admitted_at` as `recorded_at`.
- A resolution check already carried `evaluated_at`; the profile adds `recorded_at` only.
- `overdue` and `interrupted` events written by the recovery pass copy the opening event and drop its `evaluated_at`; every other member is the opening's.
- Every event of a check, not only the opening, carries `deadline`, `age_bound_seconds`, `extension_id` and `nonce`; `input` events also carry `age_basis` on the input.
- A held decision for `check_lease_unavailable` writes a resolution check row (no inputs) and no check events: the lease is taken before the check is journalled.
- `evaluated_at` is on decisions, attempts and refusals as well as the check events; `decided_at` and `started_at` keep their meaning and equal it.
- The lease covers only the resolver reads (the check is `completed` before `observe` and `apply`), so a stall between check and dispatch is caught by the deadline gate and a stall inside the reads by the overdue report, as the PR bodies state.

## Fixtures

Each fixture file is `{fixture_id, synthetic, expected_outcome, reason, provenance, [expected_refusal], document, [journal], [host]}`. `fixtures/valid/` must be accepted alone, with `journal` and with `host` when present. `fixtures/invalid/` must be refused with `expected_refusal` as the only violation. `journal` holds the run record members the contract reads (`run_id`, `decisions`, `attempts`, `refusals`, `resolution_checks`, `check_events`, `operations`, `operation_renewals`, `attempt_joins`, `age_extensions`, `age_extension_refusals`, `recovery_runs`); `host` is the host configuration the fixture's rules need.

Valid (20): all are captures of real runs and one real function output of Control Plane `3f6a7668` (synthetic proposals, a settable service clock, throwaway stores in temporary directories, random ids, nonces and the process owner replaced by synthetic ones), except that `extension-namespace-members-preserved` adds `x-` members to a capture. They cover the default path with no profile members, the three clocks, operation rows, a deadline at opening, expiry (alone, with a join row, with a retry, and with a decoupled observation clock), an overdue live check with two recovery passes, the reaper, an accepted extension, all six extension refusals, an extension without authority or limit, an extension withdrawn at use, nonce-bound and source-asserted reads, a replayed nonce, a lease hold and the freshness counts. `provenance` names the scenario of each. Scripts are in `provenance/`: `capture_fixtures.py` (needs a Control Plane checkout at `3f6a7668`) writes the raw runs, `build_fixtures.py` normalises and projects them into the valid fixtures, `mutate_invalid_fixtures.py` regenerates the invalid ones, `journal_divergence.py` runs the journal contract validator over the raw captures. Two independent captures built the valid fixtures byte for byte. The scripts are not tests and are not vendored.

Invalid (91): one or more per rule above, single-defect mutations of the valid fixtures (each `provenance` names its base). A rule that joins the sidecar to the run record is mutated on the run record, or on both sides consistently, and carries `journal`.

## Run

```
python contracts/freshness-clocks/validate.py <fixture-or-document.json>...
PYTHONPATH=src python -m pytest -q tests/test_contract_freshness_clocks.py
```

`validate.py` is stdlib only and self-contained; the run record and the host configuration are passed in by the caller when wanted. The test suite cross-checks `schema.json` against the `jsonschema` package when it is installed.

## What this does and does not show

A passing run shows the document's structure and these rules over the rows given. It does not show tamper evidence (everything here is a join over rows that a holder of the record-store key can rewrite; `not_append_only` needs the earlier export), that the deadline closes the window between the check and the commit (the gate narrows it; what remains is the interval between the clock re-read and the destination commit), cross-host fencing (the lease is a same-host `flock`), who the signers really are (the signer set is host configuration), or anything for a resolver that cannot echo a nonce (its reads are labelled `source_asserted`). A `nonce_bound` read proves only that the response was produced after the reader issued its nonce. It records no behaviour the code lacks.

## Defaults taken (questions not asked, owner review at the end; every one is reversible while the contract is `0.1.0-draft`)

1. Carrier. Default: a sidecar projection document, not new members of the journal contract's run record (the journal contract stays unedited and closed). Reversible: a minor journal bump declaring the members as optional.
2. The seven lists are required in the sidecar though empty in a run that wrote none. Reversible: make them optional.
3. `check_events` mirrors every journal event in order (identifying members, `recorded_at`, `reasons` and the profile's members); a row has no id of its own, position and `check_id` identify it.
4. A clock row is keyed `(row_type, row_id, seq)`; `seq` is the occurrence among run record rows with that id (an attempt is written twice, write-ahead and final, so it has `seq` 0 and 1).
5. An operation row's `recorded_at` in a clock row is its `admitted_at` (the code stamps no `recorded_at` member there).
6. `input_reads` lists only reads that carry an `age_basis` (never the manifest read) for decision, refusal and resolution check rows; `check_id` is null for a decision row, which has no check id.
7. Nonce values appear in the sidecar (on check events and, for a mismatch, in `input_reads`). They are per-check challenge values, not secrets; the producer itself retains both nonces of a mismatch in the refusal row.
8. Host configuration (`signers`, `max_age_extension_seconds`, `resolver_capability`) is an optional validator argument, not a document member. Absent key: the rule is skipped. `signers: null` means the rule-revision profile is not configured, which is itself a fact (`age_extension_authority_unconfigured`).
9. An accepted extension is not required to be in the signer set supplied with the export: authority is re-checked at every use and withdrawal does not delete the row. A decision that holds with `age_extension_signer_not_configured` is explained by an active accepted extension whose signer is outside the supplied set (`extension_reason_unexplained`). Refusal reasons are derived with the set supplied (the set in force when the refusal was written).
10. `recorded_at` must not precede `evaluated_at` on a check event, clock row or extension row: contract-only (the producer compares neither).
11. `recorded_at` does not decrease within a check: contract-only; a backwards-stepping service clock produces a record this contract refuses, by design (the producer has no monotonic guard).
12. `overdue` and `expired` events must be strictly after the check's deadline, as the recovery pass and the gate write them.
13. `freshness_reports` is an envelope around the verbatim `freshness` block; the counts are recomputed from the document's own `check_events` as of `as_of`, so a report over a partial journal is refused.
14. The prior-attempt exclusion mirrors the producer's filter exactly: an attempt id whose latest row is `failed` with error `check_expired_before_dispatch`; no other failed attempt is excluded. The journal contract's own `second_attempt_for_effect` is not edited and fires on the real retry capture (see Journal divergence).
15. An `overdue` event carries the reasons `["check_overdue"]` although the code is not a decision refusal reason; the code is registered because the journal carries it.
16. `check_lease_unavailable` is not modelled as check events (none exist); the rules tie it to its decision (sole reason, no attempt).
17. The two capabilities are descriptions, not document members; no destination or resolver conformance is claimed. `delayed-commit/0.1` is a CI and local aid.
18. The profile adds no signature or integrity member. Integrity stays with the ODES export package and the consumer's digest.
19. Valid fixtures are captures from the merged branch; two captures from the same code build byte-identical fixtures. Two events of the freshness-counts and reaper fixtures (`orphan`, `stuck`) are appended through the record store's own API, as the producer's own tests do, because a real abandoned check cannot be produced inside one process.
20. The profile does not model the owner of a check or its lease file; the producer enforces owner match, the contract does not read it.

## Versioning and change rules (0.x)

While the version is `0.x-draft` nothing is frozen and any change may break. Enumerations, when added, are closed (decision 6).

## Journal divergence (journal contract validator over the profile-on captures, 2026-10-18; reported, nothing edited)

Run by `provenance/journal_divergence.py` over the 19 raw captures (the run record with the two contract markers added, as a raw export carries none): the default-path capture conforms (0 violations); every capture with the profile on is refused. Findings:

1. Undeclared members (the cause of nearly every violation): `evaluated_at` and `recorded_at` on decisions and attempts, `evaluated_at`, `deadline` and `check_id` on refusals, `recorded_at` on resolution checks, `evaluated_at`, `deadline`, `age_bound_seconds`, `extension_id` and `nonce` on check events, `age_basis` on resolution inputs (also nested in check events, where it surfaces as a `schema_violation` of the `input` alternative), and the top-level `age_extensions`, `age_extension_refusals` and `recovery_runs`. Captures that also enable N1 or N2 add `operation_id` in the binding extension, `operations`, `attempt_joins`, `operation_renewals`, `rule_identity` and `rule_revisions` (those belong to the operation-identity and rule-revision profiles).
2. Unknown enumeration values: check `phase` `expired` and `overdue`, and `read_state` `nonce_mismatch`. These stop the cross-record rules, so a record with them is not checked further until they are declared.
3. With all of those stripped, what remains is behavioural, not declarative:
   - `second_attempt_for_effect` on `expired-then-retry-dispatches`: the retry after an expired attempt starts a second lifecycle, which the journal contract refuses; the profile excludes the expired attempt from the prior-attempt rule (this contract's `prior_attempt_not_excluded` states the exclusion).
   - `observation_time_future` on `clocks-follow-the-service-clock` (2 reconciliations) and `observation-clock-decoupled` (1): under the profile an observation is "future" only against the service clock re-read at reconciliation, while the journal contract judges it against `evaluation_time`.
   - `journal_missing` on `lease-unavailable-holds`: a decision under the runtime authority profile with no `check_events`, because the lease was refused before the check was journalled.
   - `journal_stage_binding` (3) on `freshness-report`: an artefact of the two check events appended directly through the store API for that capture (no decision or effect behind them), not of a producer flow.
4. A minor bump declaring the optional members, the two phases and the read state would remove 1 and 2; items under 3 need rule changes in the journal contract (relax `second_attempt_for_effect` for the excluded attempt, judge observation time against the service clock when `freshness` is on, allow a hold with no journal for `check_lease_unavailable`). That is the owner's call; none is done here.

## Current conformance (2026-10-18, local runs, not a qualification)

- Producer, Control Plane `3f6a7668`: all captured real runs pass every rule alone, with their run record and with host configuration. Gaps: the raw run record is refused by the journal contract (see Journal divergence); the sidecar is produced by projection, not by the Control Plane. The deadline gate narrows the check-to-commit window and does not close it.
- Consumer: none. No consumer reads the sidecar. The Evidence Pack would need: check events with `overdue` and `expired`, the members `deadline` and `recorded_at`, `recovery_runs`, refusal rows with `check_expired_before_dispatch` and `deadline`, and a `freshness` block next to the refusal counts (derivable from `freshness_counts` here).

## Input hardening (decision 32, 2026-10-18)

The reference validator never raises: any parsed JSON value gets a list of typed violations. Non-finite numbers (NaN, Infinity) and text that is not valid Unicode are refused as `schema_violation`; `main()` reads files with a strict loader (duplicate members, NaN, Infinity, overflowing numbers and non-UTF-8 input are refused, exit status 2, line `input_refused`); schema patterns match the whole string (`(?!\n)$` in `schema.json`) and times are ISO-8601 with ASCII digits and a UTC offset. No code, member or accepted form changed meaning; no code was added.

Invalid fixtures added: `non-ascii-digit-time`, `trailing-line-break-time`, `unpaired-surrogate-text`.
