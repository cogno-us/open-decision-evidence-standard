# Verification report contract (optional ODES extension profile)

Version: `0.1.0-draft`. Status: draft, proposal only, OPTIONAL extension profile. Not frozen (the first freeze is deferred by the owner), not part of the ODES core or `pder-v0.1`, not referenced by any `odes` code path, and not a qualification input. See `docs/engineering/ODES-INTERCOMPONENT-CONTRACTS.md` (Appendix C, section 12 item 24) for the index and the decisions. Nothing here edits another contract, the core schema or `pder-v0.1`.

## Contract statement

An independent verifier reads the records a run exported (run record, proposal export, optionally a manifest and a destination ledger export), parses them with its own strict parser, canonicalizes them with its own implementation of one pinned profile, and states what it could and could not check. This contract is the shape of that statement. It is a **verification report**, not an attestation: nothing in it signs, attests or authorizes anything, and the stack has no attestation of Control Plane decisions (the Index verifies only externally issued BitRep link attestations). The design is `docs/engineering/INDEPENDENT-VERIFIER-DESIGN.md` (stage S1, sections 3.6, 4.4 and 5); where this README and the design differ, this README records the difference.

- Producer: the independent verifier (`cogno-us/cognous-open-control-stack-verifier`, command `cognous-verify`, built by stream V2a) for trace reports; the qualification repository's mutation harness (design stage S5) for the mutation tables.
- Consumers: the qualification repository (reads `mutation_report`; joins outcome labels only against a frozen `subject.inputs_digest`, design stage S6), reviewers.
- Layering: by reference only on the journal and lifecycle contracts (check ids and finding codes may be their refusal codes or the verifier's own `wire_*` codes). It reads none of them.

## Document model

`contract: "verification-report"`, `contract_version: "0.1.0-draft"`, `profile: "verification-report/0.1"`, `report_kind: "verification_report"` (the only value), `report_id`, `generated_at`, `verifier`, `subject`, `scope`, `checks`, `summary`, `does_not_prove`, `mutation_report` (an object or null), optional `extensions`.

| Member | Content |
|---|---|
| `verifier` | `name`, `version`, `command` (`cognous-verify`), `source_revision`, `canonicalization_profile` (the profile the verifier implements) |
| `subject` | `canonicalization_profile`, `inputs` (`role`, `name`, `digest`, `size_bytes`), `inputs_digest`, `pinned` (`controller_revision`, `contract_versions` name to version, `reason_registry_digest`) |
| `scope` | `semantic_quality` (only `not_assessed`), `tiers_run` (subset of `V1` wire and structure, `V2` identity and internal consistency, `V4` receipt completeness; `V3` witness re-derivation is deferred, not a value) |
| `checks[]` | `check_id`, `tier`, `verdict` (`confirmed`, `could_not_check`, `refuted`), `tally` (`confirmed`, `could_not_check`, `refuted`, `n`), `could_not_check_reason` (null or `input_absent`, `tier_unavailable`, `profile_ambiguous`, `not_applicable_to_input`), `findings[]` (`code`, `locator`, `detail`) |
| `summary` | `checks`, `confirmed`, `could_not_check`, `refuted`: counts of checks by verdict, never a score |
| `does_not_prove[]` | `id` (closed set of ten) and `statement` |
| `mutation_report` | see below |

Verdicts. A check is over `n` items (at least one) and every figure is a count over that denominator: `confirmed`, `could_not_check` and `refuted` sum to `n`. The check's verdict is derived: `refuted` if any item is refuted, else `could_not_check` if any item could not be checked, else `confirmed`. `could_not_check` is not a pass: it says the input did not carry what the check needs (for example operands the record does not retain) and it never counts toward `confirmed`. A verifier crash is not a verdict and produces no report; the mutation harness counts it as `error` and never as detection. `overall_verdict(doc)` in `validate.py` derives the per-trace outcome the harness uses (`reject` if any check is refuted, `abstain` if none is refuted and some could not be checked or there is no check, `accept` if every check is confirmed). It is derived, not a member, and not a score.

No composite score. There is no overall number, grade, average or rate member anywhere. Every figure is an integer count or a `{k, n}` pair. A bare number where a `{k, n}` is expected is `schema_violation`. A zero denominator is `{k: 0, n: 0}` and renders `n/a`, never a percentage (`render_fraction`).

Subject identity. `inputs` lists every file the verifier read, sorted by role, name and digest, with its SHA-256 (`sha256:` plus 64 lowercase hex) computed over the file's bytes. `inputs_digest` is the commitment over the `inputs` list exactly as written, under the pinned profile `json-sort-keys-compact-utf8-no-nan-python-semantics-v0.1`: `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)` to UTF-8, then SHA-256. The profile claims no JCS (RFC 8785) or cross-language equivalence; any other profile is a major bump. `pinned` names the controller revision, the contract draft versions and the reason registry digest the result is relative to; a report is scope-bound to them and is not carried to another revision.

## The mutation report

`mutation_report` is null for a plain trace report. When present it is report-only (`report_only: true`, the only value) and carries `operator_set_digest`, `seed` and `frozen_revision` (the repository revision at which the operator set and seed were fixed, before the verifier ran), and three lists that are never mixed:

- `family_t`: trace mutants (the independent verifier under test). One corpus per entry: `corpus_id`, `provenance` (`seed`, the ODES fixtures as a regression check, or `generated`, the held-out operator-generated corpus), `corpus_digest`, `categories[]` and optional `scenarios[]` (the same rows per named scenario id; null when not reported).
- `family_s`: source (control-removal) mutants. Context only (`context_only: true`): rows `source_id`, `n_cases`, `detected`, `survived`, `errored` with their own case denominators. They answer "do our tests notice a missing control", not "does the verifier notice a damaged record", and share no member, denominator or list with family T.
- `clean`: unmutated traces on which a category's checks are active, per clean corpus (`seed_valid_fixtures` or `generated`), rows `category` and `false_rejection` as `{k, n}`.

A family T row (`categories[]`), per category from the closed catalogue of the design (W1 to W5, B, S1 to S4, I1 to I5, D1 to D5, J1 to J3, T1, A1, A2, R1 to R6, X1, L1, F, Q; 36 values):

- `expected_verdict`: `reject`, `accept` (F forgery bound, R6 truncated ledger tail, B benign) or `not_applicable` (Q, semantic quality: listed so the report shows n/a, not a rate).
- Counts: `n_gen`, `n_noop` (byte-equal to the clean trace after canonicalization, excluded), `n_na` (precondition not met, excluded, counted), `n_eff = n_gen - n_noop - n_na`, and `verdicts` (`reject`, `accept`, `abstain`, `error`) summing to `n_eff`.
- On a `generated` corpus: `detection` (`any_code` and `intended_code`, both `{k, n}` over `n_eff`; `k` is `reject` only: abstain and error are not credited), `false_acceptance` (`accept` over `n_eff`; not `1 - detection`), `abstained`, `errored` (each on its own line), and `metric_impact`: conditioned on false acceptance, `changed` is `{k, n}` with `n` equal to the accepted count (`k` null, never 0, when nothing was accepted) plus `deltas[]` (`measure` among `unauthorized_effects`, `excess_duplicate_effects`, `authorized_count`, `held_count`, `nonzero_mutants`, `min`, `max`). `regression` is null.
- On a `seed` corpus: `regression` (`refused_with_intended_code` as `{k, n}` over `n_eff`); `detection` and `metric_impact` are null (seeds are regression, not detection).
- `not_applicable` rows have zero counts and all rates null.

## Non-claims (`does_not_prove`)

Mandatory. Ten identifiers, a closed set; `statement` is the producer's wording. The first eight are required in every report, the last two additionally when `mutation_report` is present.

| Id | What the report does not claim |
|---|---|
| `relative_to_pinned_controller` | consistency with the named controller revision, drafts and registry only; not carried to another revision |
| `semantic_quality_not_certified` | decision correctness, policy adequacy, lawful issue of a grant |
| `receipt_source_bounded` | the destination ledger is executor-written, unsequenced and unsigned: no claim it is complete or unforged, or that an effect occurred in the world |
| `self_consistent_forgery_not_detected` | a record rewritten with every commitment recomputed is accepted (category F) |
| `not_an_attestation` | not an attestation, not an Index or BitRep signature, not an authorization; never an input to a grant or decision |
| `parse_strictness_is_refusal_not_repair` | a wire-level refusal is reported, not normalized and re-run |
| `no_v1_scope_claim` | nothing changes the V1 scope, the failure register or any qualified row |
| `differential_agreement_is_not_equivalence` | agreement with the controller on a corpus is not equivalence elsewhere |
| `no_imported_headline_numbers` | no figure from a paper is a target, baseline or expectation |
| `seeds_are_regression_not_detection` | detection figures come only from the generated held-out corpus |

An `x-` extension is ignored for contract logic. A consumer must not read any extension as an attestation, a signature or a score.

## Member model

Same model as the other drafts.

1. All declared members of an object are required, except `extensions`. Optional-in-spirit members that can be empty are explicit nulls (`mutation_report`, `scenarios`, `could_not_check_reason`).
2. Closed member sets. An undeclared member outside `extensions` is `undeclared_member`, never dropped (an `attestation` member, a `score` member).
3. `extensions` (names `^x-[a-z0-9][a-z0-9._-]*$`, else `invalid_extension_key`) on the document and on every object; consumers ignore them for logic, preserve them, and include them in any digest.
4. Closed enumerations (`unknown_enum_value`): the pinned profile name, tiers, input roles, check verdicts, `could_not_check_reason`, the non-claim ids, the 36 categories, expected verdicts, corpus provenance, delta measures. A new value is a major bump.
5. Times are ISO-8601 with a UTC offset (`timestamp_invalid`).
6. Adding an optional member is a minor bump; adding a required member or an enumeration value is a major bump.

## Rules

| Code | Rule |
|---|---|
| `schema_violation` | a missing required member, wrong type, pattern, range, a constant that differs (`report_kind`, `report_only`, `context_only`), an empty `does_not_prove`, a bare number where a `{k, n}` is required |
| `undeclared_member` | a member that is not declared, outside `extensions` |
| `invalid_extension_key` | an `extensions` name not matching `^x-[a-z0-9][a-z0-9._-]*$` |
| `unknown_enum_value` | a value outside a closed enumeration (`semantic_quality: certified`, tier `V3`, another canonicalization profile) |
| `unsupported_contract_version` | `contract_version` is not `0.1.0-draft` |
| `timestamp_invalid` | `generated_at` is naive or malformed |
| `duplicate_input` | one input per role and name |
| `inputs_not_canonical_order` | inputs are sorted by role, name, digest |
| `subject_digest_mismatch` | `inputs_digest` is the commitment over the inputs as written |
| `pinned_contract_versions_empty` | a report names the contract draft versions it used |
| `duplicate_check_id` | check ids are unique |
| `check_tier_not_run` | a check's tier is in `scope.tiers_run` |
| `tally_sum_mismatch` | `confirmed + could_not_check + refuted = n` |
| `check_verdict_inconsistent` | the verdict is the derived one |
| `could_not_check_unexplained` | an item that could not be checked has a reason |
| `could_not_check_reason_unexpected` | a reason needs such an item |
| `refuted_without_finding` | a refuted check has at least one finding |
| `finding_without_refutation` | findings belong to a refuted check |
| `summary_mismatch` | the summary counts the checks as written |
| `empty_report` | no check and no mutation report states nothing |
| `duplicate_non_claim` | each non-claim id appears once |
| `non_claim_missing` | the eight core non-claims, plus the two mutation non-claims with a mutation report |
| `duplicate_corpus_id` | corpus ids are unique across `family_t`, `family_s` and `clean` |
| `duplicate_category` | one row per category in a corpus (also in a scenario table and a clean corpus) |
| `duplicate_scenario_id` | one table per scenario in a corpus |
| `duplicate_source_id` | one family S row per source |
| `fraction_out_of_range` | `k` does not exceed `n` in any `{k, n}` |
| `effective_count_mismatch` | `n_eff = n_gen - n_noop - n_na` |
| `verdict_sum_mismatch` | `reject + accept + abstain + error = n_eff` |
| `not_applicable_reports_a_rate` | a `not_applicable` row has zero counts and null rates |
| `rate_missing` | an applicable generated row reports detection and metric impact |
| `detection_mismatch` | `detection.any_code` is `{reject, n_eff}` |
| `localized_exceeds_detected` | intended-code figures do not exceed rejections and share `n_eff` |
| `false_acceptance_mismatch` | `false_acceptance` is `{accept, n_eff}` |
| `abstained_mismatch` | `abstained` is `{abstain, n_eff}` |
| `errored_mismatch` | `errored` is `{error, n_eff}` |
| `metric_impact_denominator_mismatch` | the metric impact denominator is the accepted count |
| `metric_impact_na_inconsistent` | `k` is null if and only if the denominator is 0 |
| `delta_inconsistent` | a delta describes at most `k` changed mutants and `min <= max` |
| `seed_corpus_reports_detection` | a seed corpus has no detection |
| `seed_corpus_reports_metric_impact` | a seed corpus has no metric impact |
| `regression_mismatch` | a seed row's regression is over `n_eff` |
| `generated_corpus_reports_regression` | regression belongs to the seed corpus |
| `case_sum_mismatch` | family S: `detected + survived + errored = n_cases` |
| `operator_set_input_missing` | the operator set digest is a `operator_set` input of the subject |
| `corpus_input_missing` | every family T and clean corpus digest is a `corpus` input of the subject |

## Not checked here

- That any digest was computed over the real file, that any count is true, or that the verifier did what it says. The contract checks the report's internal arithmetic and its linkage to its own subject, not the facts behind it (a hand-written report with consistent numbers validates).
- That the pinned revision exists, that findings match the input, or that a corpus digest names a particular corpus.
- That `scenarios` tables add up to the corpus table (a scenario table covers only traces that came from a named scenario).
- Signing: reports are unsigned. Signing, if wanted, is a separate issuer decision through BitRep and not part of this contract.
- Cross-report rules (a report digest frozen before outcome labels are joined, design stage S6) belong to the qualification join, not to this document.

## Fixtures

Each fixture file is `{fixture_id, synthetic, expected_outcome, reason, expected_refusal, document}`. `fixtures/valid/` must be accepted. `fixtures/invalid/` must be refused with `expected_refusal` as the only violation.

Valid (8) and invalid (63) are HAND-WRITTEN and synthetic: no producer existed when this draft was written. Digests are SHA-256 over placeholder labels, not over real files; the verifier `version` is `0.0.0-handwritten-fixture`. `provenance/build_fixtures.py` regenerates all of them (invalid ones are single-defect mutations of the valid ones) and asserts each outcome. The script is not a test and is not vendored.

## Run

```
python contracts/verification-report/validate.py <fixture-or-document.json>...
PYTHONPATH=src python -m pytest -q tests/test_contract_verification_report.py
```

`validate.py` is stdlib only. The test suite also cross-checks `schema.json` against the `jsonschema` package when it is installed.

## What this does and does not show

A passing run shows that a report is well formed, that its verdicts and tallies are arithmetically consistent, that its mutation tables keep their denominators apart, and that it carries the mandatory non-claims. It does not show that the verifier is correct or independent, that a corpus is representative, or that the result transfers to another controller revision. It records no behaviour the verifier lacks.

## Divergences

- Producer: none at the time of writing. Every fixture is hand-written. When `cognous-verify` merges and emits reports, valid fixtures are captured from it and this section lists any member it emits that this draft does not declare (or the reverse). Status: see the hand-back of stream V2b and the PR description; nothing is claimed here beyond the hand-written state.
- The design lists four verdicts for a trace (`reject`, `accept`, `abstain`, `error`). The report has three per check (`confirmed`, `could_not_check`, `refuted`) as requested by the stream brief; the four-valued per-trace outcome is derived by `overall_verdict`, and `error` exists only in the harness's counts (a crash has no report).
- The design's tier `V3` and stage S4b/S7 items are not representable (deferred; a new tier is a major bump).

## Defaults taken (questions not asked, owner review at the end; every one is reversible while the contract is `0.1.0-draft`)

1. One document type for trace reports and mutation reports. `mutation_report` is an explicit null for a trace report; a mutation-only report has `checks: []` and a `subject` whose inputs are the operator set and corpora. Reversible: split into two contracts.
2. Verdict vocabulary per check is `confirmed`, `could_not_check`, `refuted`; the harness vocabulary (`reject`, `accept`, `abstain`, `error`) is used only for mutants and derived from the check verdicts.
3. A check is over at least one item; a check that could not run at all is one item with `could_not_check`.
4. No overall verdict member. It is derived (`overall_verdict`) to avoid a field that reads as a score.
5. The canonicalization profile is a closed enum of one value, in both `verifier` and `subject`; they cannot differ.
6. `subject.inputs_digest` is the commitment over the inputs list as written (including any `extensions` on an input), not over the file contents together.
7. `pinned.reason_registry_digest` and `contract_versions` are required: a report without a pinned scope is refused.
8. Tiers are `V1`, `V2`, `V4`; a check names its tier and the tier must be in `scope.tiers_run`.
9. `could_not_check_reason` is a closed set of four values, one per check (not per item).
10. `findings` carry a code, a locator (for example a JSON path) and a detail; the code is free (the verifier's `wire_*` codes or a contract's refusal code) and is not validated against any registry.
11. The categories are the design's catalogue (36 values) as a closed set, including the expected-accept ones (B, F, R6) and Q.
12. Detection has two figures (any code, intended code) in one object; metric impact deltas are summarised per measure (`nonzero_mutants`, `min`, `max`), not listed per mutant.
13. `seed` corpora report `regression` only; `generated` corpora report detection, false acceptance, abstain, error and metric impact. A generated corpus never carries `regression`.
14. Family S rows are `n_cases`, `detected`, `survived`, `errored`: a surviving source mutant is a test gap, not "false acceptance", and has no metric impact.
15. Per-scenario tables are optional and reuse the family T row; they are not required to sum to the corpus row.
16. Clean-trace false rejection is a per-corpus, per-category `{k, n}`, including the benign category B.
17. No interval, percentage or rate member at any size (the design allows an interval only at n >= 30; none is declared here).
18. The report is unsigned and carries no signature, integrity or attestation member; integrity is the consumer's digest of the report bytes.
19. `report_only` is a constant `true`: a mutation report never gates a scenario verdict, a profile or a pin.
20. The non-claim `statement` text is the producer's; the contract fixes the identifiers and their presence, not the words (the design's section 5 text is a candidate wording, not applied by this contract).

## Versioning and change rules (0.x)

While the version is `0.x-draft` nothing is frozen and any change may break. Enumerations, when added, are closed (decision 6).

## Current conformance (2026-10-18, local runs, not a qualification)

- Producer: none validated. The hand-written fixtures pass this validator; no real `cognous-verify` output has been checked against it (see Divergences).
- Consumer: none. The qualification repository does not read the mutation report yet (design stages S5 and S6 are not built).
