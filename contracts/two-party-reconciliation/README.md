# Two-party reconciliation contract (optional ODES extension profile)

Version: `0.1.0-draft`. Status: draft, proposal only, OPTIONAL extension profile. Not frozen (the first freeze is deferred by the owner), not part of the ODES core or `pder-v0.1`, not referenced by any `odes` code path, and not a qualification input. See `docs/engineering/ODES-INTERCOMPONENT-CONTRACTS.md` (Appendix C, decision 20).

## Contract statement

Where both a sender and a receiver record the same event, the two records are compared before anything is committed. A disagreement is detected before commit and surfaces as a mismatch (with the differing members and a hold or escalate disposition); it is never stored as two valid records. A missing peer is stated as `awaiting_peer`, never as agreement.

Catalog scenario D04 is ambiguous delivery: the sender cannot tell whether the receiver got and recorded the event. In this profile that state is `awaiting_peer` (sender record only) or, once the receiver's record appears and differs, `mismatch`. Neither commits.

- Producer: whichever party or third place performs the comparison (not implemented anywhere today as a record; the Governed Exchange keeps its own per-message and duplicate state in the exchange store, and the Control Plane journal records one side's attempts and observations).
- Consumers: Replay, the Evidence pack and the two ends of a delivery.
- Layering: layers by reference on the exchange delivery vocabulary (`contracts/governed-exchange/`) and the attempt and observation rows (`contracts/execution-attempt-lifecycle/`, `contracts/control-plane-journal/`). It edits none of them and adds nothing to the core or `pder-v0.1`.

## Document model

`contract: "two-party-reconciliation"`, `contract_version: "0.1.0-draft"`, `profile: "two-party-reconciliation/0.1"`, `reconciliations` (list), optional `extensions`.

A reconciliation row: `reconciliation_id`, `event_ref` (the event both parties name), `sender` and `receiver` (a record or null), `outcome` (`matched`, `mismatch`, `awaiting_peer`), `compared_at` (time or null), `mismatch` (object or null: `differing_members` non-empty, `disposition` `hold` or `escalate`), `commit` (object or null: `committed_at`, `record_ids`).

A record: `record_id`, `event_ref`, `party_id`, `event_digest` (`sha256:` plus 64 lowercase hex, computed by the recording party over its own view of the event), `recorded_at`.

## Member model

Same model as the other drafts: required members present; closed member sets (`undeclared_member`, never dropped); `x-` `extensions` accepted, ignored for contract logic, preserved and digested (`invalid_extension_key` otherwise); closed enumerations (`unknown_enum_value`, decision 6); `schema_violation` and `unsupported_contract_version` are structural.

## Rules

Per row:

- Ids: reconciliation ids and record ids are unique across the document (`duplicate_reconciliation_id`, `duplicate_record_id`). One row per event (`duplicate_event_reconciliation`): a second row for the same event would be a second verdict on it.
- Records: each names the row's event (`event_ref_mismatch`); sender and receiver are different parties (`same_party`); times are timezone-aware (`timestamp_invalid`); a compared record is recorded no later than the comparison (`record_after_comparison`).
- Outcome and records: `awaiting_peer` has exactly one record and no `compared_at`; `matched` and `mismatch` have both records (`outcome_records_inconsistent`) and a `compared_at` (`comparison_missing`).
- Outcome and digests: `matched` if and only if the two `event_digest` values are equal (`outcome_digest_inconsistent`).
- Mismatch: a `mismatch` outcome carries the mismatch member (`mismatch_not_surfaced`); no other outcome does (`mismatch_unexpected`). The disposition is `hold` or `escalate`; `accept` is not a value.
- Commit: records whose digests differ are never committed (`mismatch_committed`, the failure this contract exists to prevent); only a `matched` outcome commits (`commit_without_match`); the comparison is no later than the commit (`commit_before_comparison`); the commit names exactly the two compared records (`commit_records_mismatch`).

`committed_events(doc)` lists events with an agreed, committed pair; `open_events(doc)` lists the rest (surfaced mismatches and missing peers).

## Not checked here

- That `event_digest` was computed correctly or over a canonical form (question 2). Each party's digest is its own claim.
- Which party's record is right on a mismatch (question 5), timeouts for a missing peer (question 6), and atomicity of the commit itself (question 7). The contract states what the record must show, not how the comparison is run.

## Questions asked as defaults (owner asked not to be asked; each is reversible while the draft stays `0.1.0-draft`)

1. Where does the comparison run? Default: unspecified. The row records only that it happened (`compared_at`), not who ran it.
2. What is compared? Default: one `event_digest` per side, canonicalisation chosen by each party and opaque here; `differing_members` are free strings.
3. Disposition of a mismatch. Default: `hold` or `escalate`, never `accept`.
4. A late peer. Default: one row per event per document; resolving an `awaiting_peer` row is a later document (append-only succession is not modelled here).
5. Which record is authoritative on a mismatch. Default: neither; the event stays open.
6. Timeout for a missing peer. Default: none. An `awaiting_peer` row never ages into a commit.
7. Commit atomicity. Default: not modelled; `commit` states that both records were committed together after the comparison.
8. Time order. Default: both `recorded_at` at or before `compared_at`, which is at or before `committed_at`.
9. More than two parties. Default: two only (sender and receiver).
10. D04 mapping. Default: ambiguous delivery is `awaiting_peer` or `mismatch`, never a commit.
11. Digest form. Default: `sha256:` plus 64 lowercase hex, as in the other drafts.

## Fixtures

Each fixture file is `{fixture_id, synthetic, expected_outcome, reason, [expected_refusal], document}`. `fixtures/valid/` must be accepted. `fixtures/invalid/` must be refused with `expected_refusal` as the only violation. All are synthetic; no component produces this record today.

Valid (7): `matched-and-committed`, `mismatch-surfaced-not-committed`, `ambiguous-delivery-sender-only`, `receiver-only-awaiting-sender`, `mismatch-escalated`, `several-events-mixed`, `extension-namespace-members-preserved`.

Invalid (26): one per code above, named for the defect. The headline case is `mismatch-committed-as-two-valid-records`.

## Run

```
python contracts/two-party-reconciliation/validate.py <document.json>...   # prints violations; fixtures wrap the document
PYTHONPATH=src python -m pytest -q tests/test_contract_two_party_reconciliation.py
```

`validate.py` is stdlib only. The test suite also cross-checks `schema.json` against the `jsonschema` package when it is installed.

## Versioning and change rules (0.x)

While the version is `0.x-draft` nothing is frozen and any change may break.

## Current conformance (2026-10-17, local runs, not a qualification)

- Producer: none. Consumer: none. No component emits or reads a two-party reconciliation record today.

## Input hardening (decision 32, 2026-10-18)

The reference validator never raises: any parsed JSON value gets a list of typed violations. Non-finite numbers (NaN, Infinity) and text that is not valid Unicode are refused as `schema_violation`; `main()` reads files with a strict loader (duplicate members, NaN, Infinity, overflowing numbers and non-UTF-8 input are refused, exit status 2, line `input_refused`); schema patterns match the whole string (`(?!\n)$` in `schema.json`) and times are ISO-8601 with ASCII digits and a UTC offset. No code, member or accepted form changed meaning; no code was added.

Invalid fixtures added: `non-ascii-digit-time`, `trailing-line-break-digest`, `trailing-line-break-time`, `unpaired-surrogate-text`.
