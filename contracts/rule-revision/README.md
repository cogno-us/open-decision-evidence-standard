# Rule revision extension profile

Version: `0.1.0-draft`. Status: draft, proposal only, OPTIONAL extension profile. Not frozen (the first freeze is deferred by the owner), not part of the ODES core or `pder-v0.1`, not referenced by any `odes` code path, and not a qualification input. See `docs/engineering/ODES-INTERCOMPONENT-CONTRACTS.md` (Appendix C, section 12 item 21) for the index and the decisions. Nothing here edits the journal contract, the lifecycle contract, the core schema or `pder-v0.1`.

## Contract statement

A rule that gates or classifies a decision (a policy, the reason registry, a gate implementation, a merge-equivalence rule) is identified by a digest. This profile records how a digest becomes adopted: an append-only list of signed revision rows, a resolution of each rule a decision read to `adopted` or `unknown` with the evidence level reached (`verified_through`), the `rule_identity` stamped on decision and refusal rows, and three derived reports (refusal trend, reason arity, recomputability) whose annotations let a reader see when a number is not comparable. The profile is optional and opt-in: it is selected by the host-governed `RuleRevisionProfile` of the Control Plane. With it unset nothing here applies, no run record member appears, and no stored or hashed byte changes.

An unadopted rule is never silently adopted. A policy digest that does not resolve to `adopted` holds the decision with `policy_status_unknown`. Host rules (the reason registry, the gate implementation, the merge-equivalence rule) get a state in `rule_identity` but do not gate the decision.

Shapes and rules were read from merged code, not from the proposal:

- Control Plane `src/agent_control_plane/rule_revision.py`, `reason_vocabulary.py` (`refusal_trends`, `measured_arity`, `arity_flags`, `derive_recomputability`) and `runtime_authority.py` at main `83b49b5` (the profile merged in #44 at `87f0233`) and `docs/rule-revision-profile.md`. Qualification #95 (the N2 probes) was read for intent; where it differs from the code, the code wins.
- The valid fixtures are captures of real runs and real outputs of the producer functions (see Fixtures), not hand-written documents, except `no-rows`.

## Document model

A sidecar projection of one run, `contract: "rule-revision"`, `contract_version: "0.1.0-draft"`, `profile: "rule-revision/0.1"`, `run_id`, optional `producer`, and these lists (required, possibly empty):

| List | Row | Written |
|---|---|---|
| `rule_revisions` | `revision_id`, `rule_kind` (`reason_registry`, `policy`, `gate_implementation`, `merge_equivalence_rule`), `rule_ref`, `from_digest`, `to_digest`, `reviser`, `signer`, `authority_ref`, `reason`, `supersedes`, `recorded_at`, optional `declared_arity` (registry rows only) | by `append_rule_revision`; unsigned rows are kept |
| `rule_revision_refusals` | `refusal_id`, `revision` (the refused row), `reasons`, `recorded_at` | a `rule_revision_refusal` row per refused attempt |
| `identity_rows` | `row_type` (`decision`, `refusal`), `row_id`, `recorded_at`, `rule_identity` | one per decision or refusal row carrying the `rule_identity` member |
| `trend_reports` | `report_id`, `report` | envelope around the verbatim output of `refusal_trends` |
| `arity_reports` | `report_id`, `declared`, `declared_from`, `measured`, `flags` | envelope: `measured_arity` and `arity_flags` output plus the declaration it was compared with |
| `recomputability_reports` | `report_id`, `rows_from`, `declared_kinds`, `flags` | envelope around `derive_recomputability` (`recomputable`, `typed_only`, `underivable`) compared with the registry's declared kinds |

`rule_identity` is `{rules: {rule_ref: {digest, state, verified_through, findings}}, unknown: [rule_refs]}`. `verified_through` is one of `none`, `revision_row_present`, `signer_independent_and_configured`, `digest_matches_signed_revision`. `findings` are drawn from `no_signed_revision`, `unsigned_revision_row`, `self_signed_revision_row`, `signer_not_configured`, `digest_mismatch_with_adopted`, `observed_digest_absent`.

Why a projection: the journal contract is closed and declares none of these members. A raw run record produced with the profile on is refused by it with `undeclared_member` for `rule_revisions` and `rule_revision_refusals` and for `rule_identity` on decision and refusal rows (checked on records produced by Control Plane `83b49b5`; with those members stripped every capture conforms, and every default-path run still conforms). This contract carries the rows and states the journal-side additions as cross-document rules over the run record. Making the journal contract declare them as optional members is a possible minor bump (recommended, not done here).

## Member model

Same model as the journal contract.

1. All declared members of a row are required, except `producer`, `extensions`, `declared_arity` and the trend annotation members (all present or all absent, `trend_annotation_incomplete`).
2. Closed member sets. An undeclared member outside `extensions` is `undeclared_member`, never dropped. A verbatim producer report carries no `extensions`; its envelope may.
3. `extensions` (names `^x-[a-z0-9][a-z0-9._-]*$`, else `invalid_extension_key`) on the document and on each row and envelope. Consumers ignore them for contract logic, preserve them, and include them in any digest.
4. Closed enumerations (`unknown_enum_value`), listed above plus trend `taint_reasons` (`pre_split_count`, `row_predates_adoption`), arity flags (`measured_exceeds_declared`, `arity_undeclared`) and recomputability flags (`declared_overclaim`, `declared_underclaim`, `derivation_unavailable`). A new value is a major bump.
5. Times are ISO-8601 with a UTC offset (`timestamp_invalid`). Digests are `sha256:` plus 64 lower-case hex.

## Resolution

Revision rows are append-only. A row counts toward adoption only if it is signed by a signer distinct from the reviser and, when the configured signer set is supplied, a member of it (`revision_defects`: `unsigned_revision_row`, `self_signed_revision_row`, `signer_not_configured`). Of the counting rows of one rule, a row named by a later counting row's `supersedes` stops counting; the last remaining row's `to_digest` is the adopted digest. A signed row's `from_digest` is the digest adopted at the time (or the superseded row's `from_digest`), else `from_digest_mismatch`.

`resolve_rule(rows, rule_ref, observed_digest)` gives `adopted` only when a counting row's `to_digest` equals the observed digest (`digest_matches_signed_revision`). Otherwise `unknown` with `findings` stating why (`no_signed_revision`, `digest_mismatch_with_adopted`, `observed_digest_absent`, plus any row defect). An identity row is recomputed over the revision rows recorded at or before the row's own time (`rule_identity_recomputed_mismatch`), so a revision written after a decision never retroactively adopts it.

## Rules

Document rules need only the document. Cross-document rules need the optional run record (`journal`) and the configured signer set (`signers`, host configuration, in no record); a rule whose context is absent is skipped, not assumed.

| Code | Rule |
|---|---|
| `adoption_source_missing` | no reason_registry revision row or vocabulary change adopts this version |
| `adoption_time_mismatch` | adoption_time is the earliest adoption row for the version |
| `arity_flags_mismatch` | lags are exactly measured_exceeds_declared and arity_undeclared derived from declared and measured |
| `arity_shapes_invalid` | each shape is a sorted list of distinct input types; the shapes are sorted and distinct |
| `declared_arity_mismatch` | declared is the declared_arity of the row it names |
| `declared_arity_on_non_registry_row` | arity is declared at signing on reason registry rows only |
| `declared_from_unknown` | declared_from names a reason_registry revision row of the document |
| `declared_kind_mismatch` | declared is the registry's reason_kind for the code, listed in declared_kinds |
| `derived_recomputability_mismatch` | derived is recomputed from the row's retained inputs |
| `duplicate_finding` | a finding is listed once |
| `duplicate_flagged_row` | a row is flagged once |
| `duplicate_identity_row` | one identity row per decision or refusal |
| `duplicate_refusal_id` | refusal ids are unique |
| `duplicate_report_id` | report ids are unique within a list |
| `duplicate_revision_id` | revision ids are unique; rows are appended, never edited |
| `finding_level_mismatch` | no_signed_revision if and only if no signed independent revision row was found (level none or revision_row_present) |
| `flagged_count_mismatch` | lagged_row_count is the number of distinct flagged rows |
| `flagged_row_without_taint` | rows of version {v} are flagged but no series of it is marked row_predates_adoption |
| `from_digest_mismatch` | rom_digest is the digest currently adopted for the rule (or the superseded row's from_digest) |
| `identity_row_mismatch` | the identity row is the row's rule_identity, member for member |
| `identity_row_time_mismatch` | recorded_at is the row's decided_at (decision) or recorded_at (refusal) |
| `identity_row_unknown_row` | an identity row names a decision or refusal of the run record |
| `invalid_extension_key` | an `extensions` name not matching `^x-[a-z0-9][a-z0-9._-]*$` |
| `journal_run_mismatch` | the profile document and the run record describe the same run |
| `measured_count_mismatch` | measured is the number of distinct operand shapes |
| `not_append_only` | successive exports describe one run |
| `observed_digest_finding_mismatch` | observed_digest_absent if and only if the digest is null; digest_mismatch_with_adopted names an observed digest that differs from the adopted one |
| `policy_input_without_rule_identity` | every policy the row read has a rule identity entry |
| `pre_split_without_change` | pre_split_count needs a split of this version that retires this code |
| `recomputability_code_not_in_row` | the flagged code is one of the row's reasons |
| `recomputability_flag_inconsistent` | a flag is raised only where declared and derived differ and names that pair: declared_overclaim is recomputable declared, typed_only derived (operands present); derivation_unavailable is recomputable declared, underivable derived; declared_underclaim is typed_only declared, recomputable derived |
| `recomputability_row_missing` | the flag names a row of the run record's list |
| `refusal_reason_mismatch` | each reason names a defect the embedded revision shows (an unsigned row is never refused for its signer) |
| `refusal_reasons_not_canonical` | reasons are sorted and unique |
| `row_not_before_adoption` | a flagged row predates its version's adoption instant |
| `rule_identity_findings_mismatch` | the revision rows recorded by then give findings {res['findings']} |
| `rule_identity_recomputed_mismatch` | the revision rows recorded by then give {res['state']} through {res['verified_through']} |
| `rule_identity_unknown_mismatch` | unknown lists, sorted, exactly the rules whose state is not adopted |
| `schema_violation` | a missing required member, wrong type, pattern or range (digests are `sha256:` and 64 lower-case hex) |
| `self_signed_row_accepted` | a self-signed revision is refused and kept as a refusal row, never accepted |
| `signer_not_configured` | the signer is not in the configured signer set |
| `supersedes_unknown` | a row supersedes an earlier row of the same rule |
| `taint_flag_inconsistent` | tainted_for_trend if and only if taint_reasons is non-empty; each reason once |
| `taint_without_flagged_row` | row_predates_adoption needs a flagged row of this version |
| `timestamp_invalid` | times are timezone-aware |
| `trend_annotation_incomplete` | rows_predating_adoption, flagged_row_count and every series' tainted_for_trend and taint_reasons are all present or all absent |
| `unadopted_policy_not_held` | a policy that does not resolve to adopted holds with {POLICY_UNKNOWN} |
| `undeclared_member` | a member that is not declared, outside `extensions`; never dropped |
| `unknown_enum_value` | a value outside a closed enumeration |
| `unsupported_contract_version` | `contract_version` is not `0.1.0-draft` |
| `verified_through_state_mismatch` | adopted if and only if verification reached digest_matches_signed_revision |

Terms the rules use: `tainted_for_trend` (a trend series is not comparable with its predecessor because `row_predates_adoption`, the row's time is before its version's adoption instant, or `pre_split_count`, the code was counted before a vocabulary split retired it); `declared_arity` (declared at signing, in `rule_revisions`) versus measured arity (`measured_exceeds_declared` and `arity_undeclared`); `declared_overclaim` (declared `recomputable`, derived `typed_only`) and `declared_underclaim` (the reverse).

## Consumer-conformance note: enforced by the producer versus only in this contract

Checked against Control Plane `83b49b5` by reading the code and by capturing the valid fixtures from it.

Enforced by the Control Plane producer:

- Revision admission: self-signed, unconfigured signer, duplicate id, unknown `supersedes`, `from_digest` mismatch are refused, a `rule_revision_refusal` row is persisted and `RuleRevisionRefused` raised; unsigned rows are kept and never count.
- Resolution (`resolve_rule`, `rule_identity`), stamping of `rule_identity` on decision and refusal rows, and the `policy_status_unknown` hold for an unadopted policy digest.
- The trend, arity and recomputability computations, and the annotation members of the trend report when the profile is on.

Only in this contract (no producer re-check of a stored row; a producer bug would not be caught by the producer):

- Uniqueness of revision, refusal, identity-row and report ids, `timestamp_invalid`, the canonical order of refusal reasons, `refusal_reason_mismatch`, and the whole append-only succession check (`not_append_only`).
- Re-derivation of every identity row from the revision rows (`rule_identity_recomputed_mismatch` and the `finding` and `verified_through` consistency rules), and the join between the identity rows and the run record.
- Cross-checks of reports against their sources: adoption times against revision rows and vocabulary changes, flag counts, arity flags against declared and measured, recomputability flags against the row's retained inputs.

Divergences noted, none edited:

- Finding, fixed at the producer (Control Plane `fd0d5e0`, N2b): `derive_recomputability` first derived `typed_only` for every real decision row because the retained manifest input has `observed` equal to `{}` (operands are absent), so a real `grant_revoked` hold, whose registry kind is `recomputable`, was flagged `declared_overclaim`, a false alarm. Now operands not retained derive `underivable` and the flag is `derivation_unavailable` (declared `recomputable`, derived `underivable`); `declared_overclaim` is reserved for rows whose operands are present and show the declared kind cannot hold (`recomputable` declared, `typed_only` derived). `typed_only` with operands present means every recorded expectation is met and none is missing. Captured as the valid fixture `recomputability-derivation-unavailable` (replaces `recomputability-declared-overclaim`); the false overclaim is the invalid fixture `false-overclaim-where-operands-are-absent`. A flag set from the earlier producer (`typed_only` derived for operand-absent rows) is now refused, by design.
- Host rules do not gate: only a policy digest that is not adopted holds. A host rule with state `unknown` is recorded in `rule_identity.unknown` and the decision still authorizes (fixture `host-rule-unadopted-does-not-gate`).
- The journal contract refuses a raw run record with the profile on (see Document model).
- The contract is stricter than the producer on digests (`sha256:` plus 64 hex) and on timestamps (aware, ISO-8601).

## Fixtures

Each fixture file is `{fixture_id, synthetic, expected_outcome, reason, provenance, [expected_refusal], document, [journal], [signers]}`. `fixtures/valid/` must be accepted alone and with `journal` and `signers` when present. `fixtures/invalid/` must be refused with `expected_refusal` as the only violation. `journal` holds the run record members the contract reads (`run_id`, `decisions`, `refusals`, `vocabulary_changes`); `signers` is the configured signer set.

Valid (15): fourteen are captures of real runs and real producer function outputs of Control Plane `83b49b5` (synthetic proposals, fixed clock, throwaway stores, ids replaced by synthetic ones): `adopted-policy-decision-and-refusal-rows`, `unsigned-row-resolves-unknown-and-holds`, `refused-revision-attempts-kept-as-rows`, `policy-edited-in-place-held-then-readopted`, `unsigned-then-resigned-by-supersession`, `host-rule-unadopted-does-not-gate`, `identity-rows-across-a-registry-adoption`, `trend-flags-from-registry-adoption-row`, `trend-pre-split-tainted-from-vocabulary-change`, `trend-plain-without-adoption-annotation`, `arity-measured-exceeds-declared-and-undeclared`, `arity-within-declaration`, `recomputability-derivation-unavailable`, `extension-namespace-members-preserved` (a capture plus `x-` members). `no-rows` is hand-built. `provenance` names the source of each. Scripts are in `provenance/`: `capture_fixtures.py` (needs a Control Plane checkout) writes the raw runs, `build_fixtures.py` normalises and projects them into the valid fixtures, `mutate_invalid_fixtures.py` regenerates the invalid ones. They are not tests and are not vendored.

Invalid (76): one or more per code above, single-defect mutations of the valid fixtures (each `provenance` names its base).

## Run

```
python contracts/rule-revision/validate.py <fixture-or-document.json>...
PYTHONPATH=src python -m pytest -q tests/test_contract_rule_revision.py
```

`validate.py` is stdlib only and self-contained; the run record and signer set are passed in by the caller when wanted. The test suite cross-checks `schema.json` against the `jsonschema` package when it is installed.

## What this does and does not show

A passing run shows the document's structure and these rules over the rows given. It does not show tamper evidence (a holder of the record store key can rewrite rows; `not_append_only` needs the earlier export), who the signers really are (the signer set is host configuration), or that a rule file's bytes hash to the digest (no rule content is carried). It records no behaviour the code lacks.

## Defaults taken (questions not asked, owner review at the end; every one is reversible while the contract is `0.1.0-draft`)

1. Carrier. Default: a sidecar projection document, not new members of the journal contract's run record (the journal contract stays unedited and closed). Reversible: a minor journal bump declaring the members as optional.
2. The six lists are required in the sidecar though empty in a run that wrote none. Reversible: make them optional.
3. Reports are envelopes around the verbatim producer output; the contract adds `report_id` and, for arity and recomputability, the declaration and source named alongside.
4. The configured signer set is an optional validator argument, not a document member; without it the configured-signer rules are skipped, not assumed.
5. The run record is an optional validator argument and is not re-validated by this contract; members it does not read are ignored.
6. A revision row is judged "as of" the row it licenses: identity rows are recomputed over revision rows with `recorded_at` at or before the row's time.
7. Revision rows are append-only. Order of the list is the order of writing; `check_succession` compares successive exports.
8. Unsigned rows are kept in `rule_revisions`, never count, and are exempt from the `from_digest` chain check and from signer refusals.
9. Findings are compared as sets; the producer's order is preserved in fixtures but not required.
10. Digests are `sha256:` plus 64 lower-case hex, stricter than the producer.
11. Only policy rules gate (`policy_status_unknown`); host rules carry state but do not gate. This states the producer's behaviour, it does not recommend it.
12. The producer's `derive_recomputability` is stated as it is (Control Plane `fd0d5e0`: `underivable` where operands are not retained); no fixture was adjusted to avoid it. The earlier empty-`observed` quirk is fixed upstream (see Findings).
13. Adoption time of a version is the earliest of a `reason_registry` revision row's `recorded_at` and a vocabulary change's `acknowledged_at`; a flagged row must be strictly before it.
14. The trend annotation members are all present or all absent; a plain trend report is valid.
15. `declared_arity` is allowed on `reason_registry` rows only.
16. `merge_equivalence_rule` is in the closed `rule_kind` set because the producer accepts it; no merge rule is modelled here (a later stream).
17. Valid fixtures are captures from main, not hand-written, except `no-rows`.
18. The profile adds no signature or integrity member. Integrity stays with the ODES export package and the consumer's digest.

## Versioning and change rules (0.x)

While the version is `0.x-draft` nothing is frozen and any change may break. Enumerations, when added, are closed (decision 6).

## Current conformance (2026-10-18, local runs, not a qualification)

- Producer, Control Plane `83b49b5`: all captured real runs and function outputs pass every rule alone and with their run record and signer set. Gap: the raw run record is refused by the journal contract (see Document model); the sidecar is produced by projection, not by the Control Plane. Finding: the recomputability quirk above, fixed in `fd0d5e0`; the `recomputability-derivation-unavailable` fixture is captured at that commit, the other captures remain at `83b49b5`.
- Consumer: none. No consumer reads the sidecar.
