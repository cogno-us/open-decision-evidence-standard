# Source-family counting contract (optional ODES extension profile)

Version: `0.1.0-draft`. Status: draft, proposal only, OPTIONAL extension profile. Not frozen (the first freeze is deferred by the owner), not part of the ODES core or `pder-v0.1`, not referenced by any `odes` code path, and not a qualification input. See `docs/engineering/ODES-INTERCOMPONENT-CONTRACTS.md` (Appendix C, decision 20).

## Contract statement

Confirmations and evidence are counted by source family, not by record. Retries, re-sends and derived records inherit the family of the record they came from. N retries of one message are one confirmation. A claim that says it has N independent confirmations states the number of distinct families, and that number is checkable from the document.

- Producer: whatever collects confirmations or evidence and decides whether a requirement is met (not implemented as a record anywhere today; the Governed Exchange tracks duplicate messages by `message_id` and digest in its own store, which dedupes a re-send but does not say which family a confirmation belongs to).
- Consumers: Replay, the Evidence pack and auditors checking a claimed count.
- Layering: layers by reference on the exchange delivery records (`contracts/governed-exchange/`) and the journal (`contracts/control-plane-journal/`). It edits neither and adds nothing to the core or `pder-v0.1`.
- Which sources belong to one family is declared by the producer. This contract never infers a family.

## Document model

`contract: "source-family-counting"`, `contract_version: "0.1.0-draft"`, `profile: "source-family-counting/0.1"`, `records`, `claims`, optional `extensions`.

A record: `record_id`, `kind` (`original`, `retry`, `resend`, `derived`), `family_id`, `derived_from` (null for an original, else the id of the record it came from).

A claim: `claim_id`, `required_families` (at least 1), `confirmations` (record ids put forward), `counted_families`, `satisfied`.

## Member model

Same model as the other drafts: required members present; closed member sets (`undeclared_member`, never dropped); `x-` `extensions` accepted, ignored for contract logic, preserved and digested (`invalid_extension_key` otherwise); closed enumerations (`unknown_enum_value`, decision 6); `schema_violation` and `unsupported_contract_version` are structural.

## Rules

Records:

- Record ids are unique (`duplicate_record_id`). An original names no source and every other kind names one (`origin_inconsistent`). The source is in the document (`origin_missing`) and listed earlier (`origin_not_earlier`; append-only order, which also rules out cycles).
- A retry, re-send or derived record carries its source record's `family_id` (`family_not_inherited`). Inheritance is transitive through the chain of sources.

Claims:

- Claim ids are unique (`duplicate_claim_id`); a record is confirmed once per claim (`duplicate_confirmation`); every confirmation names a record (`confirmation_dangling`).
- `counted_families` is the number of distinct `family_id` values among the confirmations (`family_count_mismatch`). Counting by record fails here: six sends of one message stated as six confirmations is refused.
- `satisfied` is true if and only if `counted_families` is at least `required_families` (`satisfied_inconsistent`).

`family_of(doc, record_id)` and `count_families(doc, record_ids)` expose the count.

## Not checked here

- That the declared families are the right ones (question 1) or that two families share no upstream (question 8).
- That a satisfied claim authorizes anything. The contract only makes the count honest (question 10).

## Questions asked as defaults (owner asked not to be asked; each is reversible while the draft stays `0.1.0-draft`)

1. Who assigns families? Default: the producer declares `family_id`; the contract does not infer it from content, sender or channel.
2. Family granularity. Default: an opaque string id, no hierarchy.
3. Inheritance. Default: a record takes its direct source's family, which makes it transitive; a record with two sources is not modelled (one `derived_from`).
4. Two originals from one source family. Default: still one family (the unit is the source, not the message).
5. Derived records (copies, forwards, summaries, translations). Default: they inherit. An independent re-observation of the same fact by another source is an original in its own family.
6. The requirement. Default: a count of families at or above a threshold; no weights.
7. Several claims over one record set. Default: independent; each is counted on its own confirmations.
8. Correlated families (two sources that share an upstream). Default: not modelled; the producer declares them one family.
9. Time windows for retries. Default: none; a retry of any age inherits.
10. Effect of a satisfied claim. Default: none in this contract; it states the count, not an authorization.
11. A confirmation naming an unknown record. Default: refused (`confirmation_dangling`), not ignored.

## Fixtures

Each fixture file is `{fixture_id, synthetic, expected_outcome, reason, [expected_refusal], document}`. `fixtures/valid/` must be accepted. `fixtures/invalid/` must be refused with `expected_refusal` as the only violation. All are synthetic; no component produces this record today.

Valid (8): `one-original-satisfies-one`, `six-sends-of-one-message-count-one`, `retries-plus-second-family-satisfies-two`, `resend-and-derived-inherit-the-family`, `two-originals-of-one-family-count-one`, `claim-with-no-confirmations`, `two-claims-over-one-record-set`, `extension-namespace-members-preserved`.

Invalid (22): one per code above (21), named for the defect, plus the one added by decision 32 (`unpaired-surrogate-text`). Headline: `six-retries-counted-as-six`.

## Run

```
python contracts/source-family-counting/validate.py <document.json>...   # prints violations; fixtures wrap the document
PYTHONPATH=src python -m pytest -q tests/test_contract_source_family_counting.py
```

`validate.py` is stdlib only. The test suite also cross-checks `schema.json` against the `jsonschema` package when it is installed.

## Versioning and change rules (0.x)

While the version is `0.x-draft` nothing is frozen and any change may break.

## Current conformance (2026-10-17, local runs, not a qualification)

- Producer: none. Consumer: none. No component counts confirmations by source family today.

## Input hardening (decision 32, 2026-10-18)

The reference validator never raises: any parsed JSON value gets a list of typed violations. Non-finite numbers (NaN, Infinity) and text that is not valid Unicode are refused as `schema_violation`; `main()` reads files with a strict loader (duplicate members, NaN, Infinity, overflowing numbers and non-UTF-8 input are refused, exit status 2, line `input_refused`); schema patterns match the whole string (`(?!\n)$` in `schema.json`) and times are ISO-8601 with ASCII digits and a UTC offset. No code, member or accepted form changed meaning; no code was added.

Invalid fixtures added: `unpaired-surrogate-text`.
