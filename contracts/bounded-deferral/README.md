# Bounded deferral extension profile

Version: `0.1.0-draft`. Status: draft, proposal only, optional. Not frozen (the first freeze is deferred by the owner), not part of `pder-v0.1`, not referenced by any `odes` code path, not a qualification input. See `docs/engineering/ODES-INTERCOMPONENT-CONTRACTS.md` (Appendix C, section 12 item 19) for the design context and `contracts/control-plane-journal/` for the contract this one is layered on. Nothing here edits the journal contract, the lifecycle contract, the core schema or `pder-v0.1`.

## Contract statement

A deferral is a **bounded hold**. Today the Control Plane returns `hold`, never `deny` (`decide()` produces `authorized` or `hold`; the journal enum is closed to those two, decision 18-J4). This profile adds a third *verdict*, DEFER, without adding a decision result: DEFER is a held decision plus a deferral record that names a deadline and what may end it.

Mapping onto the core, which stays as it is:

| Profile term | In the run record |
|---|---|
| DEFER (open deferral) | a decision with result `hold` and no binding, plus a deferral with outcome `deferred` |
| REFUSE (deferral outcome `refused`) | the same `hold` decision, now terminal: it stays a hold, no authorized decision, no attempt, no observation of an effect |
| RELEASE (outcome `released`) | not a verdict that authorizes anything: a later, separate `authorized` decision for the same proposal commitment, named by `released_decision_id`. Its `effect_id` differs from the held decision's, because `effect_id` commits `{proposal, grant_id, grant_revision}` and a held decision has no binding |

Producer: whatever component runs the deferral policy and the resolver (in the stack, the Control Plane bounded workflow once it implements the profile; it does not today). Consumers: Replay and the Evidence pack after the journal, and anyone checking that no effect preceded a release. The profile is a sidecar document, `contract: "bounded-deferral"`, that names the run record's `run_id` and its held decisions. It can be checked alone, or with the journal document as context (`validate(doc, journal)`); the journal is assumed to conform on its own and is not re-validated.

What the code does today (cogno-us/cognous-control-plane #42, authoritative): the delay bound is per action class, `ActionClass.max_status_age_seconds` (default 60), failing closed to `hold`; `tier` is an equality tag, not a bound table; refusals are typed (121 codes) with outcome `hold`; there is no Control Plane re-read of the grant before `destination.apply` (the in-transaction digest check exists only with the opt-in `sqlite-effective-grant/0.1` destination). This profile does not claim a re-read, does not add a resolver to the Control Plane, and records no behaviour the code lacks. An addendum claim of an authority tier table is not used (the code has none).

A conforming document states `contract: "bounded-deferral"` and `contract_version: "0.1.0-draft"`. `schema.json` (JSON Schema draft 2020-12) defines members, types and enumerations; the rules below are the cross-record half, implemented by `validate.py`.

## Member model

Same model as the journal contract.

1. Required: `contract`, `contract_version`, `run_id`, `evaluated_at`, `deferrals` (may be empty). `producer` is optional. Every deferral carries all of its members; `refusal_notice` is the only optional deferral member (besides `extensions`).
2. Closed member sets. An undeclared member outside `extensions` is `undeclared_member`, never dropped.
3. `extensions` (names `^x-[a-z0-9][a-z0-9._-]*$`, else `invalid_extension_key`) on the document, a deferral, a policy and a response. Consumers ignore them for contract logic, preserve them, and include them in any digest. The refusal notice and its parts carry **no** `extensions`, so nothing private can ride along.
4. Closed enumerations (`unknown_enum_value`): `outcome` (`deferred`, `released`, `refused`), `policy_verdict` (`defer`, `refuse`), response `kind` (`release`, `refuse`, `timeout`, `unparseable`, `error`), `refusal_reason` (`policy_refused`, `resolver_refused`, `deadline_expired`, `resolver_timeout`, `resolver_unparseable`, `resolver_error`). No `deny` anywhere.
5. Times are ISO-8601 with a UTC offset (`timestamp_invalid`). `max_age_seconds` is an integer of at least 1.
6. The document is a snapshot at `evaluated_at`. Adding an optional member is a minor bump; adding a required member or an enumeration value is a major bump.

## Rules

Structural codes (level S): `schema_violation`, `undeclared_member`, `unknown_enum_value`, `invalid_extension_key`, `unsupported_contract_version`. The rest are rule codes (level L).

Identity and policy:

- Deferral ids are unique (`duplicate_deferral_id`); a held decision has at most one deferral (`duplicate_deferral_for_decision`).
- `policy_verdict` is `defer` if and only if `refusal_reasons` is empty, and a deferral names at least one deferred reason (`policy_verdict_inconsistent`). Policy has already decided which reasons a resolver may release (`deferred_reasons`) and which it may not (`refusal_reasons`).

Deadline (bounded):

- `deadline = opened_at + max_age_seconds` (`deadline_mismatch`). The bound is the action class's `max_status_age_seconds`; no deferral is open-ended. A response cannot precede `opened_at` (`response_before_opening`).

Fail-closed resolution. `derive_outcome` in `validate.py` is the single rule:

- Policy verdict `refuse` wins over any resolver: outcome `refused`, reason `policy_refused`. A resolver may release only what policy deferred and can never override a refusal; a `release` answer to a policy-refused effect is recorded and ignored (`release_overrides_refusal` if the document says released).
- Otherwise the **first** response by `received_at` decides, provided it arrived by the deadline (inclusive): `release` releases; `refuse` refuses (`resolver_refused`); `timeout`, `unparseable` and `error` refuse (`resolver_timeout`, `resolver_unparseable`, `resolver_error`). Later responses are recorded and never change the outcome (`refusal_overridden` when a refusal is recorded as released; a release after a failure is likewise ignored).
- No response by the deadline, or a first response after it, is `refused` with `deadline_expired`. A deferral still open past its deadline at `evaluated_at`, or released after it, is `expired_deferral_not_refused`.
- A failure of any kind recorded as released is `resolver_failure_released`. Any other disagreement between the recorded outcome and the derived one is `outcome_mismatch`. The refusal reason must be the derived one, null unless refused (`refusal_reason_mismatch`). `released_decision_id` is set if and only if released (`release_decision_inconsistent`). `resolved_at` is null while deferred, the deciding response time when a response decided, not before the deadline on expiry, not before `opened_at` on a policy refusal (`resolved_at_inconsistent`).
- There is no path from failure, silence, garbage or expiry to a release.

Effects:

- `effect.observable` is true if and only if `first_observable_at` is set (`effect_observability_inconsistent`). No effect is observable while deferred or before the release is resolved (`effect_observable_before_release`). A refused effect never becomes observable (`refused_effect_observable`).
- An unparseable resolver reply is retained as `payload_commitment` only, never as content.

Refusal notice (optional member `refusal_notice`, only on a refused deferral, `refusal_notice_on_non_refusal`). Closed set: `effect_withheld` (always true), `effect_id`, `constraint_failed` (`code`, `description`), `admissible_alternatives` (list of `alternative_id`, `description`; may be empty), `effect_did_not_occur` (always true), `statement`. A notice that claims the effect occurred or was not withheld is `schema_violation`. The notice names the deferral's effect (`refusal_notice_effect_mismatch`); the failed constraint is the refusal reason or a reason the policy recorded (`refusal_notice_constraint_mismatch`); it carries no commitments, grant or tenant identifiers or other private state (`refusal_notice_private_state`: a heuristic over the text for commitments and identifier shapes, plus, when the journal is given, the grant and tenant ids of its bindings). This is a shape and leak check, not a guarantee of wording.

Journal context (optional second argument; each needs the run record):

- `journal_run_mismatch`; `deferral_dangling_decision`; `deferral_decision_not_held` (only a `hold` with no binding is deferrable); `deferral_effect_mismatch`; `deferral_proposal_mismatch` (the held decision's `operation_horizon.proposal_commitment`); `deferral_reasons_not_held` (deferred plus refusal reasons are exactly the decision's reasons); `deferral_before_decision`; `deferral_max_age_mismatch` (the journal check event's action class `class_id` and `max_status_age_seconds`, when the run has a journal).
- Released: names an authorized decision for the same proposal commitment (`release_decision_unauthorized`) decided at or after the release (`release_decision_before_release`); no attempt on it starts before the release (`effect_attempted_before_release`).
- Not released (deferred or refused): no attempt exists on any authorized decision for that proposal (`effect_attempted_without_release`); refused: no accepted observation of `applied` or `partial` for it (`refused_effect_observed`).

## Fixtures

Each fixture file is `{fixture_id, synthetic, expected_outcome, reason, [expected_refusal], document}`. `fixtures/valid/` must be accepted; `fixtures/invalid/` must be refused with `expected_refusal` as the only violation. All fixtures are synthetic and hand-built (no producer implements the profile); they use the identifiers of the journal fixture `held-decision-journal-mode` so the journal context tests can run against it.

Valid: `open-deferral-within-deadline`, `released-by-resolver-before-deadline`, `refused-by-resolver`, `expired-deferral-refused-with-notice`, `resolver-timeout-refused`, `resolver-garbage-refused`, `resolver-error-refused`, `policy-refused-release-attempt-ignored`, `late-release-after-deadline-refused`, `release-after-failure-ignored`, `refusal-after-release-attempt-sequence-order-free`, `extension-namespace-members-preserved`, `no-deferrals`.

Resolver fault injection (valid shapes, resolving to refused): timeout, garbage (`unparseable`), error, an attempt to release a policy-refused effect, an expired deferral, a late release, a failure followed by a release. Their invalid mirror images (the same facts recorded as released or left open) pin `resolver_failure_released`, `release_overrides_refusal`, `expired_deferral_not_refused`, `refusal_overridden`. Invalid: one or more per code above (39 fixtures). Journal-context rules are pinned in `tests/test_contract_bounded_deferral.py`.

## Run

```
python contracts/bounded-deferral/validate.py <document.json>...   # prints violations; fixtures wrap the document
PYTHONPATH=src python -m pytest -q tests/test_contract_bounded_deferral.py
```

`validate.py` is stdlib only and self-contained: a vendored copy (`contracts/tools/vendor_contract.py copy --contract bounded-deferral ...`) needs no sibling contract; the journal document is passed in by the caller when wanted. `CONTRACT.json` is not generated here (no component vendors it yet). The test suite cross-checks `schema.json` against the `jsonschema` package when installed.

## What this does and does not show

A passing run shows the document's structure and these rules. It does not show that a resolver is authentic or authorised (`resolver_id` is an opaque string), that the clock is trustworthy, that the destination honoured a withhold, or that the Control Plane implements the profile (it does not). It claims no re-read of the grant before apply, and adds no field to the core schema or `pder-v0.1`.

## Defaults taken (questions not asked, owner review at the end; every one is reversible while the contract is `0.1.0-draft`)

1. Where DEFER lives. Default: a sidecar document and a deferral record, not a new decision result or a core member. The core enum stays `authorized`/`hold` (18-J4). Reversible: promote to a core member in a major bump.
2. Meaning of REFUSE. Default: a terminal `hold` (the brief's "`hold` outcome refused"), never `deny`; the control plane never produces `deny`.
3. Meaning of RELEASE. Default: not authority. It permits a fresh `authorized` decision for the same proposal; the control plane still decides. The release decision has a different `effect_id` (code check: `effect_id` commits proposal, grant id and revision).
4. Deadline origin. Default: `opened_at` (not `decided_at`), plus the action class `max_status_age_seconds` (default 60). Equality with the class bound is required when the journal shows the class; a deferral may not be longer or shorter. Reversible: allow a shorter bound.
5. Deadline boundary. Default: a response at exactly the deadline counts; evaluation at exactly the deadline is still open.
6. First response decides; later ones are recorded and ignored (fail-closed ordering by `received_at`, ties broken by list order).
7. Resolver identity and authentication are out of scope (`resolver_id` opaque). Whether a resolver is allowed to release a given deferral is policy's job, expressed by `deferred_reasons` versus `refusal_reasons`.
8. Garbage is kept as a commitment only. The profile does not carry the raw reply.
9. Which reasons are deferrable. Default: the policy records them per deferral; the profile does not define a global list of deferrable reason codes. The union must equal the held decision's reasons.
10. Refusal notice is optional, closed, extension-free, and its private-state check is a heuristic plus the journal's own identifiers. The brief's "no private state" is enforced by shape, not by semantics.
11. Open deferrals are valid snapshots. The snapshot time `evaluated_at` is a required document member so expiry is checkable offline.
12. One deferral per held decision. Renewal or a second hold on the same proposal is a new held decision.
13. Observability of effects is a producer assertion (`effect`), cross-checked against attempts and observations only when the journal is supplied. Replay's global view of those records is unchanged.
14. No `deny`, no `safe_to_retry`, no core or `pder-v0.1` change, no edit of any existing contract; the profile is not wired into any code path.

Source of the design: the owner's programme brief of 2026-10-17 (items C1 and C3 of the 101726_B consolidation as summarised to the worker). The addendum text itself was not available to the worker, so its exact wording is not quoted here.

## Input hardening (decision 32, 2026-10-18)

The reference validator never raises: any parsed JSON value gets a list of typed violations. Non-finite numbers (NaN, Infinity) and text that is not valid Unicode are refused as `schema_violation`; `main()` reads files with a strict loader (duplicate members, NaN, Infinity, overflowing numbers and non-UTF-8 input are refused, exit status 2, line `input_refused`); schema patterns match the whole string (`(?!\n)$` in `schema.json`) and times are ISO-8601 with ASCII digits and a UTC offset. No code, member or accepted form changed meaning; no code was added.

Invalid fixtures added: `non-ascii-digit-time`, `seconds-bound-out-of-range-deferral`, `trailing-line-break-digest`, `trailing-line-break-time`, `unpaired-surrogate-text`.

- `context_malformed`: an optional context argument (the run record, or for effect-reversibility also the deferral document) whose shape does not let the cross-document rules run is refused with this typed violation instead of raising. The context is not re-validated against its own schema here.

## Typed constants (decision 39-B, 2026-10-18)

A schema `const` matches only the same JSON type with an equal value, as `enum` already did: the integer `1` is not `true`, `0` is not `false`, `1.0` is not `1`. The constants that were compared by value alone are now typed: `effect_withheld` and `effect_did_not_occur` (the constant `true`). Invalid fixtures `effect-withheld-written-as-integer` and `effect-did-not-occur-written-as-integer`. Same `0.1.0-draft` label; every valid fixture is unchanged.
