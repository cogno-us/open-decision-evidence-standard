# Authority lineage contract (optional ODES extension profile)

Version: `0.1.0-draft`. Status: draft, proposal only, OPTIONAL extension profile. Not frozen (the first freeze is deferred by the owner), not part of the ODES core or `pder-v0.1`, not referenced by any `odes` code path, and not a qualification input. See `docs/engineering/ODES-INTERCOMPONENT-CONTRACTS.md` (Appendix C, decision 20).

## Contract statement

A record linking grant -> delegation -> terminal effect. Each hop references the previous hop by hash. Every terminal effect resolves to a grant through intact links, or is flagged `lineage_discontinuity`. An effect that resolves to nothing and carries no flag is refused, so an unexplained effect can never read as authorized.

- Producer: whatever assembles the lineage for a run (not implemented anywhere today; the Control Plane records `grant_id` and `grant_revision` in the binding and derives `effect_id` from them, but keeps no hash-linked chain and, today, no delegation: see `contracts/non-broadening-delegation/`).
- Consumers: Replay, the Evidence pack and auditors reading why an effect was allowed.
- Layering: layers by reference on the grant and delegation shapes (`contracts/non-broadening-delegation/`) and on the Control Plane `effect_id` (`contracts/control-plane-journal/`). It edits neither, and nothing here is required by the core or `pder-v0.1`. `content_digest` is the producer's digest of the record a hop stands for (a grant, a delegation record, an effect) and is not verifiable at this boundary.

## Document model

`contract: "authority-lineage"`, `contract_version: "0.1.0-draft"`, `profile: "authority-lineage/0.1"`, `hops` (list, may be empty), `lineage_discontinuities` (list, may be empty), optional `extensions`.

A hop: `hop_id`, `kind` (`grant`, `delegation`, `effect`), `subject_ref` (grant id, delegated grant id, or effect id), `previous_hop_id` and `previous_hash` (both null on a lineage origin), `content_digest` and `hop_hash`.

`hop_hash` is `sha256:` plus the SHA-256 of the sorted compact UTF-8 JSON (`ensure_ascii` false) of `{hop_id, kind, subject_ref, previous_hop_id, previous_hash, content_digest}` (the same commitment form as `effect_id`). `previous_hash` equals the previous hop's `hop_hash`, so changing any earlier hop invalidates every later link. Extension members are not covered by `hop_hash` (as for producer commitments in the journal contract); only a consumer digest of the whole document covers them.

A flag in `lineage_discontinuities`: `flag` (`lineage_discontinuity`), `effect_hop_id`, `break_hop_id`, `reason` (`previous_missing`, `previous_hash_mismatch`, `no_origin`).

## Member model

Same model as the other drafts: required members present; closed member sets (`undeclared_member`, never dropped); `x-` `extensions` accepted, ignored for contract logic, preserved and digested (`invalid_extension_key` otherwise); closed enumerations (`unknown_enum_value`, decision 6); `schema_violation`, `unsupported_contract_version` are structural.

## Rules

Hops:

- Hop ids are unique (`duplicate_hop_id`). `previous_hop_id` and `previous_hash` are both null or both set (`previous_incomplete`). `hop_hash` is recomputed and must match (`hop_hash_mismatch`: a hop altered after hashing, which is tampering and is never excused by a flag).
- A grant hop is an origin and links to nothing (`grant_has_previous`). A hop links to a hop listed earlier (`previous_not_earlier`; append-only order, which also rules out cycles). An effect is terminal: nothing links to an effect hop (`previous_kind_invalid`).

Continuity (what resolving means). Walk the previous links from an effect hop. The walk resolves when it reaches a grant hop through intact links. It breaks at the first hop where: the named previous hop is not in the document (`previous_missing`), the previous hop exists but its `hop_hash` differs from the recorded `previous_hash` (`previous_hash_mismatch`), or a delegation or effect hop has no previous hop (`no_origin`).

- An effect that does not resolve carries exactly one flag, whose `break_hop_id` and `reason` name that first break (`lineage_discontinuity_unflagged` when no flag; `discontinuity_flag_mismatch` when it names another break or reason; `duplicate_discontinuity_flag`).
- A flag names an effect hop in the document (`discontinuity_flag_dangling`) and that effect really does not resolve (`discontinuity_flag_false`).
- A delegation that does not resolve and has no effect below it needs no flag (there is no terminal effect to explain); it is reported by `find_break`.

A document is valid with unresolved effects when they are flagged. Validity here means the record is honest about its own gaps; it never means the effect was authorized. A consumer treats a flagged effect as unauthorized-until-explained. An effective authority is derived from a single lineage, never from the union of two independent principals' scopes; this contract defines no merging of lineages.

`find_break(doc, hop_id)` and `unresolved_effects(doc)` expose the walk.

## Not checked here

- That a delegation hop's content is a non-broadening child of the previous hop's grant (that is `contracts/non-broadening-delegation/`; the hops carry digests, not the grants).
- That an effect hop's `subject_ref` equals `commitment({proposal, grant_id, grant_revision})` of the grant it resolves to (question 5).
- Signatures, time and the status of any grant.

## Questions asked as defaults (owner asked not to be asked; each is reversible while the draft stays `0.1.0-draft`)

1. A single chain per effect (each hop has one previous), not a DAG. Default: one previous. Reversible: a `previous` list in a later minor bump.
2. Hash input. Default: the Control Plane commitment form over six members; extensions excluded.
3. Is a broken link a violation or a flagged state? Default: a flagged state (the flag is the contract's honest representation of a gap), except `hop_hash_mismatch`, a self-inconsistent hop, which is always a violation.
4. Where is the break reported when several fail? Default: the first break walking from the effect toward the origin.
5. Does the contract bind the effect hop to `effect_id`? Default: no; `subject_ref` is an opaque effect reference here. The binding is a later optional member.
6. Delegation hops with no effect below them. Default: not flagged, not an error.
7. Order. Default: a hop's previous appears earlier in the list.
8. May a lineage hold several grant origins and several effects? Default: yes, one document may hold a forest.
9. Verification of `content_digest` against the record. Default: out of scope (no record is carried).
10. Name of the state. Default: `lineage_discontinuity`, as the request states it.

## Fixtures

Each fixture file is `{fixture_id, synthetic, expected_outcome, reason, [expected_refusal], document}`. `fixtures/valid/` must be accepted. `fixtures/invalid/` must be refused with `expected_refusal` as the only violation. All are synthetic (no component produces this record today); hashes are computed with the commitment form above.

Valid (10): `grant-only`, `grant-to-effect`, `grant-delegation-delegation-effect`, `two-effects-share-a-delegation`, `effect-without-origin-flagged`, `previous-missing-flagged`, `previous-hash-mismatch-flagged`, `break-deeper-in-the-chain-flagged-at-the-break`, `mixed-resolved-and-flagged`, `extension-namespace-members-preserved`.

Invalid (24): one per code above (22), named for the defect (for example `orphan-effect-unflagged`, `tampered-hop-content`, `flag-on-resolved-effect`, `link-to-an-effect`), plus the two added by decision 32 (`trailing-line-break-digest`, `unpaired-surrogate-text`).

## Run

```
python contracts/authority-lineage/validate.py <document.json>...   # prints violations; fixtures wrap the document
PYTHONPATH=src python -m pytest -q tests/test_contract_authority_lineage.py
```

`validate.py` is stdlib only. The test suite also cross-checks `schema.json` against the `jsonschema` package when it is installed.

## Versioning and change rules (0.x)

While the version is `0.x-draft` nothing is frozen and any change may break.

## Current conformance (2026-10-17, local runs, not a qualification)

- Producer: none. Consumer: none. The Control Plane keeps no delegation and no hash-linked authority chain; its binding carries `grant_id`, `grant_revision` and `effect_id` only.

## Input hardening (decision 32, 2026-10-18)

The reference validator never raises: any parsed JSON value gets a list of typed violations. Non-finite numbers (NaN, Infinity) and text that is not valid Unicode are refused as `schema_violation`; `main()` reads files with a strict loader (duplicate members, NaN, Infinity, overflowing numbers and non-UTF-8 input are refused, exit status 2, line `input_refused`); schema patterns match the whole string (`(?!\n)$` in `schema.json`) and times are ISO-8601 with ASCII digits and a UTC offset. No code, member or accepted form changed meaning; no code was added.

Invalid fixtures added: `trailing-line-break-digest`, `unpaired-surrogate-text`.
