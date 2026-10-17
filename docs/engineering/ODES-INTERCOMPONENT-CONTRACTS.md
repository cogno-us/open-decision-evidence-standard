# ODES inter-component contracts

Status: engineering proposal for team review. Post-V1 work. Nothing in this document changes `src/odes` behaviour, any existing test, or any pinned tuple, and none of it applies until V1 closes.

Direction owner: André de Lima (owner directive, 2026-10-17). Document revision: 0.2 (draft). Spike: `contracts/execution-attempt-lifecycle/` (contract `0.1.0-draft`).

Owner decisions recorded 2026-10-17 (section 12): the extension namespace form (section 6) and the placement of behavioural contracts as optional extensions of the ODES core (sections 3, 4.1, 9). One owner item (status `unknown` and observation) was explored and refined (section 10, section 12 item 3). Document revision 0.2.

## 1. Purpose and problem

The directive: the stack is alpha. From here ODES establishes and governs all communication between components. Contracts are frozen per boundary (not per component), and then one component changes at a time. Additional fields become optional by extension of ODES. Hard-coded peer sha pins are replaced, after V1, by "conforms to contract vN".

The evidence for why, from V1 validation `v1-2026-10-16-a` (failure register in `cognous-stack-qualification/process/v1-validation/v1-2026-10-16-a/failure-register.json`):

- F-20: Replay #33 `_validate_v2_executor_rows` rejected result status `unknown` with terminal event `executed`, which the runtime route C adapter (`engine/control_plane_adapter.py`) legitimately emits when the Control Plane observation is unavailable.
- F-21: Replay #33 `_validate_repaired_run` required an `attempted` start row, but the Control Plane (`bounded.py`, around lines 1020-1043) mints single-row `acknowledged` or `partial` attempts marked `acknowledgement = {"reconciled_existing": true}` that have none.
- F-22: Replay #33 `refusal_evidence.py` journal-order rule failed under concurrent resolution checks.
- F-23: the same Replay change added two `pytest.skip` cases that made two matched requirement rows INCONCLUSIVE. The register classifies this as test-only, not a product defect. It is listed for completeness: it was repaired in the same PR as F-20 to F-22, but it is not itself a boundary mismatch.

F-20 to F-22 share one shape. A consumer's validator encoded an assumption about what a producer emits, the producer legitimately emitted something else, and nobody could say which side was right because the rule was written down in neither place. The fix was made in the consumer (Replay #36, merged `def0ee0f`), which is the correct side here, but it was found by running the whole stack, not by testing either side alone.

The second problem is cost. One logic change took 10+ pull requests across 6 repositories, because about four repositories hard-code peer commit shas (for example `PINNED_REVISIONS`, `F5B_REVISIONS` and the supported-revision tuples in `src/odes/common.py`, `ODES_REVISION` and sibling constants in the Evidence Pack importer, and `component-lock.json` in the hub). A pin says "this exact commit of the peer". The only way to move one side is to repin every side that names it, so a change to one component fans out to all of its neighbours even when the boundary did not change.

What we want instead is for each boundary to have an explicit, versioned, testable statement of what may cross it. Then a component change that keeps every boundary it touches conformant needs no other repository to move.

## 2. Principles

1. Boundaries, not components, are the unit of agreement. A component is qualified as "produces boundary B at contract vN" and "consumes boundary C at contract vM".
2. A contract is written down once, in machine-checkable form, with its status semantics. Prose alone is not a contract.
3. Both valid and invalid cases are golden. A contract that only lists accepted examples cannot catch an over-lenient consumer or a producer drifting into a gap.
4. Each side is tested alone against the fixtures. Neither side needs the other's code to know whether it conforms.
5. Unknown content is never silently dropped (V1 finding F-10). Evolution happens through declared optional members and a declared extension namespace, not through leniency.
6. A frozen contract version is immutable. Change means a new version with a stated bump class and a deprecation path.
7. Change one component at a time. A change that needs two components to move at once means the boundary was changed, which is a contract bump, which is reviewed as such.
8. What the contract does not say is not a contract. The honest limits (what ODES does not establish: external truth, authentication, authority) carry over unchanged.

## 3. Boundaries

This section states real producers and consumers as read from the checkouts in the working environment (runtime `e20f92e1`, Replay `def0ee0f`, ODES `5675f1b9`, Control Plane checkout in `comp-2a`, Evidence Pack `d162889`, Governed Exchange `059f84f`, Evidence Registry `d17b8ac`). Checkout revisions differ from some qualified tuples; treat names and shapes as indicative and confirm against the owning repository before freezing anything.

| # | Boundary | Producer | Consumer | What crosses today | Present coupling |
|---|---|---|---|---|---|
| B1 | Runtime and Control Plane | Runtime `engine/control_plane_adapter.py` (`PinnedControlPlaneExecutor`, destination adapter) calls the Control Plane bounded workflow | Control Plane `bounded.py` (`BoundedAuthorizedEffectWorkflow.execute`, `EffectAttempt`, reconciliation) and runtime reading results back | In-process Python calls plus the bounded run record. Runtime passes an execution snapshot and observation clock; Control Plane returns `(EffectAttempt, observation)`; the adapter maps these into `ExecutionResult` (`status`, `attempt_id`, `observed_state`, `observation`, `control_plane_evidence`). | Imports Control Plane classes directly; pinned by sha. |
| B2 | Runtime and Replay | Runtime `engine/producer_contract.py` (executor export 2.0.0: `producer_profile`, `execution_result`, `effects`, `attempts`, `attempt_events`, `attempt_identity`, `control_plane_attempts`, `observations`, `control_plane_evidence`) | Replay `importers.py` `_import_moltbot`, `_validate_v2_export`, `_validate_v2_executor_rows` | JSON export. Replay rejects unsupported members in some typed records (`_reject_unknown_members`) and validates lifecycle rows. | Replay encodes lifecycle rules (F-20); runtime pins Replay. |
| B3 | Control Plane and Replay | Control Plane bounded run record (`attempts`, `reconciliations`, `observations`, `decisions`, `refusals`, `resolution_checks`, `closeouts`, `check_events`, `input_time_floors`) | Replay `_validate_repaired_run`, `refusal_evidence.validate_run`, `import_bounded_workflow` | JSON run record. Replay re-derives consistency rules (F-21, F-22). | Replay encodes lifecycle and ordering rules; pinned by sha. |
| B4 | Replay and ODES | Replay `ReconstructionBundle` (`bundle_version`, records, links, commitments, producer profiles, status, import reports, semantics) | ODES `exporter.export_cognous_stack_package`, which also invokes Replay `import_bounded_workflow` and `extend_retained_inputs` in process | Bundle JSON, plus an in-process call into Replay. ODES rejects an unsupported bundle version explicitly (`tests/test_bundle_version.py`). | ODES pins Replay and Control Plane revisions and selects a profile by revision. |
| B5 | ODES and Evidence Pack | ODES export package (`odes_decision_evidence_export_package`, profile `odes-cognous-stack-export-*`, `integrity`, `package_digest`, `provenance`) and `recipient_validator` | Evidence Pack importer (`agent_governance_evidence_pack/importer.py`), which also runs the Replay semantic validator and records `ODES_REVISION` | Package JSON plus a validated Replay bundle. | Pack pins ODES, Replay, Control Plane and runtime revisions. |
| B6 | Evidence Pack and Exchange | Evidence Pack documents and retained digests | Governed Exchange (GAX/IMX) `assess_message`, which verifies an `evidence_refs` replay-bundle digest | Digest-bearing references inside exchange messages. | Hub `component-lock.json` pins the accepted exchange sha. |
| B7 | Attestation (Index and BitRep), where applicable | Evidence Registry link attestations (BitRep v1, `POST /evidence/links`), and ODES `verification` key references | ODES verification metadata and Registry readers | Attestation over evidence commitments. ODES today states that no BitRep or Index dependency is implied and that a content digest is integrity metadata, not authentication. | ODES `PINNED_REVISIONS` names `bitrep` and `index` shas. |

Two observations that shape the plan:

- The riskiest boundaries (B1 to B3) are not ODES boundaries today. They carry behaviour (lifecycle rows, status semantics, journal ordering) rather than decision evidence. By owner decision (2026-10-17) ODES carries those behavioural contracts itself, as optional extension profiles of the ODES core, one per boundary. See section 4.1.
- Several boundaries have an in-process Python call as well as a JSON artifact. A contract must cover the artifact first. The in-process call is a coupling to remove, not to standardise.

## 4. Contract anatomy

A contract for one boundary consists of:

1. Identity and version: `contract` name and `contract_version` (semver) in every conforming document. Pre-1.0 versions carry a `-draft` suffix and promise nothing.
2. Versioned schema: JSON Schema draft 2020-12 for members, types and enumerations, with closed member sets (`additionalProperties: false`) and one reserved extension member (section 6).
3. Status semantics: the meaning of each status value and the cross-record rules that schema cannot express (for example "result `unknown` never carries a validated observation, though it may carry a typed recovery observation"; "a lifecycle starts with `attempted` unless it is a single reconciled row"). Each rule has a stable refusal code.
4. Golden fixtures: `fixtures/valid/*.json` and `fixtures/invalid/*.json`. Each fixture states `expected_outcome`, a `reason`, and for invalid fixtures the `expected_refusal` code. Fixtures are small and synthetic.
5. Conformance levels:
   - Level S (structural): schema valid.
   - Level L (lifecycle): schema valid and all stated cross-record rules hold.
   - Level P (preservation): consumers additionally preserve extension members and bind them into digests.
   A producer claims the level it tests; a consumer claims the level at which it refuses invalid fixtures.
6. Reference validator: a small stdlib-only implementation used to generate and check fixtures. It is a test aid, not a runtime dependency.
7. Change and bump rules (section 6.4) and a deprecation policy: a version is supported for at least one subsequent minor line, with a dated deprecation notice in the contract README and a fixture set retained for each supported version.

Where a contract lives: `contracts/<boundary>/` in this repository for the spike. Whether contracts live here permanently or in a dedicated repository is an open question (section 12).

### 4.1 Behavioural contracts as optional extension profiles of ODES

Owner decision (André de Lima, 2026-10-17): ODES carries the behavioural contracts (lifecycle rows, status semantics, journal ordering) itself, as optional extensions of the ODES core. There is no companion interface spec.

What this means for the design:

- The ODES core stays what it is: the decision-evidence record, export package and recipient validation. It does not change and does not require any behavioural profile. A core-only implementation remains conformant to the core.
- A behavioural contract is a declared optional extension profile, one per boundary (for example the execution-attempt lifecycle profile for B2 and B3). A profile is versioned on its own line, has its own schema, status semantics, valid and invalid fixtures and reference validator, and is declared by a document that opts in (the `contract` and `contract_version` members in the spike). A consumer or producer claims the profiles it supports and the conformance level (S, L, P) per profile.
- The extension model of section 6 applies to the profile and to the core alike: closed member sets, one reserved `extensions` object with `x-` names, preserve and digest, undeclared members refused.
- Profiles are optional for the core, mandatory for the boundary they describe. Once two components agree to exchange boundary B under profile P at version vN, P is the contract between them, and a change to either component that keeps its documents conformant at vN does not need the other to move.
- Profile versions are independent of the core version, so a behavioural change (for example refining the `unknown` rule) bumps the profile, not the core. A profile may not weaken a core refusal.
- Consequence for scope: ODES remit grows from decision evidence to decision evidence plus declared behavioural profiles. The decision-evidence standard is protected by keeping profiles strictly optional extensions, in separate directories and documents, with no profile content in the core schema.
- This remains post-V1 work (section 10). The spike lives in `contracts/` and does not touch `src/odes`.

## 5. What "frozen per boundary" means

Freezing a contract version freezes its schema, its rules and its fixtures. It does not freeze either component. A component may change in any way that keeps its produced and consumed documents conformant at the contract versions it declares. Breaking a boundary means releasing a new contract version first, then changing producers and consumers one at a time, consumers first for additive changes (they accept both versions), producers first for none.

## 6. Optional-field extension model

DECIDED (André de Lima, 2026-10-17): the extension namespace is a reserved `extensions` object, with `x-` prefixed member names matching `^x-[a-z0-9][a-z0-9._-]*$`, which any declared object may carry. Consumers must preserve extension members and include them in digests. Undeclared members elsewhere stay refused. The rest of this section states how that decision works.

### 6.1 The tension

The owner wants additional fields to be optional so the stack can evolve forward and backward compatibly. V1 finding F-10 (runtime executor export; remediated in Replay #34, merged `6076fade`) required the opposite for unknown content: injected unknown members at the top level, producer profile and repository record must not be silently dropped. A rule of "ignore unknown fields" would reopen F-10. A rule of "reject all unknown fields" makes every addition a breaking change.

### 6.2 Resolution

The two requirements apply to different things. Optionality applies to declared members. The F-10 protection applies to undeclared members. The design separates them:

- (a) Declared optional members may be absent. A consumer must not require them. Absence has a defined meaning stated in the contract (usually "not asserted", never "false" or "zero").
- (b) New optional members enter only by a contract minor-version bump (they become declared members of the next minor), or inside the reserved, declared extension namespace, which exists in every version of the contract. Consumers MUST preserve extension members when they re-emit a document and MUST include them in every digest and signature input. They may ignore them for logic.
- (c) Unknown members outside the declared fields and the extension namespace remain rejected with a typed refusal (`undeclared_member` in the spike). This is the F-10 protection, unchanged.
- (d) Adding a required member is a major-version bump.
- (e) Consumers ignore-but-preserve unknown extension members. Producers never emit undeclared members; anything new goes in a declared member (after a bump) or in `extensions`.

So an "additional field" is optional in exactly one of two ways: it is declared optional in a published version, or it is carried in the extension namespace. In neither case is anything dropped.

### 6.3 Compatibility matrix

Let producer P emit contract version `vP` and consumer C implement `vC`. "Bump" classes: patch (clarification, fixtures), minor (declared optional member added, or new status value only where the contract says consumers must treat unknown values as typed refusal), major (required member added, member removed, meaning changed).

| Producer emits | Consumer implements | Outcome |
|---|---|---|
| v1.0 | v1.0 | Accept. |
| v1.0 | v1.1 | Accept. The new optional members are absent, which is valid. |
| v1.1, uses new optional member | v1.0 | Typed refusal (`undeclared_member`). A v1.0 consumer cannot know the member. It is refused, not dropped. |
| v1.1, new data carried in `extensions` | v1.0 | Accept. The consumer ignores the extension content for logic, preserves it, and includes it in digests. |
| v1.1, uses new optional member | v1.1 | Accept. |
| v2.0 | v1.x | Typed refusal (`unsupported_contract_version`). |
| v1.x | v2.0 | Accept only if the v2 consumer declares it still supports v1.x; otherwise `unsupported_contract_version`. |

The third row is the cost of F-10. A producer that wants a new field to flow to old consumers without a refusal must put it in `extensions`. A producer that wants consumers to act on it declares it in a minor bump and waits for consumers to adopt that minor. This is deliberate: the contract version a document claims tells the consumer exactly what to expect, and a consumer never has to guess.

An extension member is promoted to a declared optional member in a later minor by publishing its name and meaning. A document that carried it in `extensions` stays valid; producers move it when they adopt the new minor.

### 6.4 Bump rules

- Patch: wording, fixtures added, no change to what is accepted or refused.
- Minor: a declared optional member is added; a rule is relaxed so documents valid under the old minor remain valid. Fixtures are added; no existing valid fixture becomes invalid.
- Major: a required member is added or removed; a member's type or meaning changes; a status meaning changes; a rule is tightened so a previously valid document becomes invalid.

### 6.5 Digests and signatures

Extension members are part of the document, so they are part of any digest or signature over the document. A consumer that re-serialises must do so without loss. Consequences:

- A consumer that strips extensions and then verifies a digest will fail verification. That is the intended outcome: stripping is tampering with signed content.
- A declared optional member that is absent is simply not in the digest input. Adding it later in a minor bump changes the digest of documents that include it and nothing else.
- The canonicalisation profile used for digests is part of the boundary contract (the spike's `canonical_bytes` is sorted-key compact JSON over the whole document, as a placeholder). The real boundary must name the canonicalisation it uses. ODES already carries `integrity` and `package_digest`; extension members under the ODES package must be covered by `package_digest`. Whether that requires a new ODES profile version is an open question.
- A signature over a v1.1 document that uses a new declared member is not verifiable by a v1.0 consumer, because the document is refused before verification. A signature over a document whose new data is in `extensions` is verifiable by both.

## 7. Producer and consumer conformance testing

Each side is tested alone against the fixtures. Neither test imports the other component.

- Producer conformance: the producer generates documents (from its own scenarios, with synthetic data) and the contract's reference validator (or a port of it) checks them at the claimed level. Producers also run the invalid fixtures through their serialiser guard where one exists, to show they cannot emit those shapes.
- Consumer conformance: the consumer's real entry point is fed every valid fixture (must accept) and every invalid fixture (must refuse, and ideally with the stated refusal code or an agreed mapping to it).
- Consumer-driven contract tests: when a consumer relies on a property that the contract does not yet state (for example, "result status is one of these values"), it adds a fixture to the contract through a pull request to the contract repository. That PR is reviewed by the producer owner. Merging it is the moment the producer is on notice. This replaces the pattern in which the consumer silently encoded the assumption in its own validator (F-20 to F-22).
- Failures are findings against the side that diverges from the contract, not fixed in the contract repository. If the contract is wrong, the contract changes through the bump rules.

The spike (appendix B) shows the first consumer-conformance run of this kind.

## 8. How qualification changes

Today qualification uses exact-commit pins: a tuple of peer shas that must all move together (the "F5b" tuple, `component-lock.json`, per-repository pin tables). Under this model:

- Each component declares the contract versions it produces and consumes, in a small manifest in its own repository (for example `contracts.json`: boundary, role, version, conformance level).
- Qualification becomes a matrix: components by contract version, filled from those manifests, plus per-component fixture results. A cell is green when the component passes the fixtures for that version in its own CI.
- A small end-to-end smoke (one or two scenarios) runs the stack as assembled. It is a sanity check on assembly, not the place where boundary agreement is discovered.
- What remains frozen is contract versions. A release names "boundary B at v1.2" instead of "peer at `abc123`".
- Pins are kept as a record of what was actually run (provenance), not as the compatibility mechanism.

Nothing about the V1 validation changes. The V1 tuple, its pins and its evidence stay as they are. This is the plan for what follows V1.

## 9. Migration plan

No hard-coded pin is removed before V1 closes. Phases are sequential, one boundary and one repository at a time.

| Phase | Work | Exit criteria |
|---|---|---|
| P0 Contract freeze for one boundary | Choose one boundary (proposed: the execution-attempt lifecycle, B2 and B3 into Replay). Resolve the open decisions in section 12 for it. Freeze the contract at `1.0.0` as an optional ODES extension profile: schema, rules, valid and invalid fixtures, reference validator, owner sign-off. Declare the profile identifier and its relation to the ODES core (optional, no core change). | Profile `1.0.0` published as an optional extension of ODES; every rule has a valid and an invalid fixture; all producers and the consumer have read it; no code changed. |
| P1 Conformance suites | Add a producer conformance test in each producer repository and a consumer conformance test in the consumer repository, one repository per pull request. Each test declares the contract version it targets. Findings are filed against the diverging side. | Each side passes fixtures alone in its own CI; known divergences are recorded as findings with owners; no pin removed. |
| P2 Remove hard pins repo by repo | After V1 closes: in one repository, replace its hard-coded pins of that boundary's peer by "conforms to contract vN" (a contract-version check plus the fixture suite). One component changes per pull request and each is qualified before the next. | The repository builds and qualifies with no peer sha for that boundary; the V1 tuple remains reproducible from retained history; the next repository starts only after this one is green. |
| P3 Qualification switches | Qualification consumes component contract manifests and the matrix; the e2e smoke replaces the exact-tuple run for that boundary. The hub lock records contract versions alongside shas. | A release candidate is described by a contract matrix; a change to one component qualifies without repinning others; the e2e smoke passes. |

Repeat P0 to P3 for the next boundary only after the first completes. Starting order by risk: B2/B3 (lifecycle), then B4, then B5/B6, with B7 last.

## 10. Risks and open questions

- Scope of ODES. Decided 2026-10-17: ODES carries behavioural contracts itself as optional extension profiles (section 4.1). The risk that remains is dilution of the decision-evidence standard. Mitigation: profiles are optional, versioned separately, kept in separate documents and directories, and add nothing to the core schema or to `pder-v0.1`.
- V1 decision D4, "no extension families in V1". This proposal is post-V1 and is not an extension family in the V1 sense. It adds no V1 behaviour. It must not be started or merged into any V1 path until V1 closes. The spike lives in `contracts/` and `tests/` only.
- No hard-coded pin removal until V1 closes. P2 and P3 are blocked on that, by design.
- Consumers that validate more than the contract states. Today Replay validators check rules nobody wrote down. The first conformance runs will surface these. Each is a decision: add it to the contract, or remove it from the consumer.
- The contract may encode a producer's current accident. The spike takes the shapes from today's code. A frozen contract should be reviewed for whether each rule is intended, not merely observed. The first case is the `unknown` rule. The first draft said status `unknown` requires observation null. That was an accident of route C and was wrong for route B. Findings, verified by reading the code and by running it (2026-10-17):
  - Route B (`AtomicLocalControlPlaneExecutor`, post-commit timeout, runtime PR #101, runtime `4a83b175`) returns status `unknown`, `attempted` true, `acknowledged` false, `observed_state` `applied` or `partial` when recovery reports it (else `unknown`), and `observation` set to the `reconcile_claim` record, or to the placeholder `{status: unknown, retry_eligible: false, reason: reconciliation_unavailable}` when reconciliation fails. The observation is never null on this path. The real export is in the golden fixture `executor-unknown-recovery-observation-route-b` (shape captured from the SCN-C06 route B scenario components).
  - Route C (`control_plane_adapter.py`) sets `unknown` with observation null only when the Control Plane observation is None. When an observation exists it takes `status = local.status`, which can itself be `unknown`.
  - Refined rule (0.1.0-draft, this revision): `unknown` means no validated observation exists. It may carry observation null or a typed recovery observation (a different record from a validated Control Plane observation: it has `status` and `retry_eligible`, no `state`). It must not carry a validated observation. A consumer must never treat an observation attached to an `unknown` result as validated evidence of effect. `observed_state` may be `unknown`, `applied` or `partial` on an `unknown` result, where `applied`/`partial` means "recovery reports", not "validated", and must equal the recovery record's own status.
  - Residual uncertainty is listed in section 12 (items 7 to 9).
- Content-based binding. Journal check ids and resolution check ids are separate producer UUIDs, so Replay binds them by content. A contract should probably add an explicit reference. That is a producer change and therefore a contract version.
- Digest canonicalisation must be named per boundary and tested.
- Fixture maintenance cost. Fixtures are the contract. Treat them as reviewed code.
- Pre-1.0 churn. A `-draft` contract can change freely; do not let a component depend on one in qualification.
- False assurance. A passing conformance suite shows structure and stated rules only. It does not establish external truth, delivery authentication or authority, and the contract documents must repeat that.

## 11. Ownership

Proposed, for owner confirmation:

- The doctrine and direction owner (André de Lima) approves the principles, the extension model decision and each boundary freeze.
- Each contract has one owning component (normally its producer) responsible for the contract text and fixtures, and named consumer reviewers who sign off changes.
- ODES maintainers own the contract anatomy, the reference validator pattern and the extension model.
- Each component repository owns its own conformance tests and its `contracts.json` manifest.
- The qualification repository owns the matrix assembly and the e2e smoke.

## 12. Owner decisions and open items

Decided:

1. DECIDED 2026-10-17 (André de Lima). Extension namespace form: adopt the proposal. A reserved `extensions` object with `x-` prefixed member names on every declared object. Consumers must preserve extension members and include them in digests. Undeclared members elsewhere stay refused with a typed refusal (F-10 protection unchanged).
2. DECIDED 2026-10-17 (André de Lima). Where behavioural contracts live: ODES carries them itself (lifecycle rows, status semantics, journal ordering), as optional extensions of the ODES core. It is not a companion interface spec. A behavioural contract is a declared optional extension profile per boundary, versioned, with its own fixtures (section 4.1).

Explored and refined (owner asked 2026-10-17 to confirm that `unknown` requires observation null unless this breaks something; if so, explore more):

3. It breaks something. Runtime route B emits status `unknown` with a non-null recovery observation. The rule was refined as described in section 10 and encoded in the schema, the reference validator, the README and the fixtures (`executor-unknown-recovery-observation-route-b` and `executor-unknown-recovery-unavailable-route-b` valid; `executor-unknown-with-validated-observation` and `executor-unknown-recovery-state-contradiction` invalid). Confirmed in item 3a.

Decided by delegation (owner said "decide items" on 2026-10-17; the decisions below were made by Claude on that instruction; the owner accepted all except item 5, which is deferred):

3a. DECIDED. The refined `unknown` rule stands: `unknown` means no validated observation exists. It may carry observation null or a typed recovery observation, never a validated one. Observation null remains the default and the recovery observation is the only exception.
4. DECIDED. Contracts stay in this repository, one directory per boundary under `contracts/<boundary>/`, permanently while ODES carries behavioural profiles itself (item 2). Revisit only if more than three boundaries exist or a boundary needs a release cadence independent of the ODES core.
5. DEFERRED by the owner (2026-10-17: "let's wait until more engineering"). No boundary freezes yet, and no freeze date or conditions are committed. The execution-attempt lifecycle remains the proposed first boundary and stays `0.1.0-draft`. Revisit after more engineering. Pin removal still happens at the end, before release, and the earlier ordering (freeze before pin removal) is kept as a proposal only.
6. DECIDED. Enumerations are closed. A new value in any status or state enumeration (result status, observation status, attempt event status, recovery status) is a major bump, because a new status changes what every consumer must do. Consumers refuse an unknown value with a typed refusal (`unknown_enum_value`) and never coerce it. An enumeration may be declared open only by an explicit `x-open-enum` marker in the schema; none is today. Optional members may still be added in a minor bump.
7. DECIDED. Recovery observations get their own export member. A new optional member `recovery_observations` (list of typed recovery records, closed member set, no `state`) carries them, and the export member `observations` carries validated observations only. The runtime moves the route B recovery record out of `observations`. The result still carries it in `execution_result.observation` as today. During alpha, Replay accepts both layouts (it now accepts the recovery record in `observations`, retained as `executor_recovery_report`). At freeze, the legacy layout is refused. This is a minor bump (optional member) followed by a tightening at freeze. Implementation is a runtime PR plus a Replay PR, and is not started.
8. DECIDED, then settled by the owner on 2026-10-17 after the P0 inventory (finding N-1: the OpenShell timeout path can return `unknown` with a validated observation). Owner chose to change the runtime, not the contract. The contract position stands: `unknown` with a validated observation is invalid. The runtime reports `reconciled` or `partial` when a validated observation exists. Implementation is a runtime change in P3 of the decoupling plan (cogno-us/cognous-control-plane#38), preceded by a probe that reproduces the path; not started.

9. DECIDED (owner confirmed 2026-10-17). Recovery status `hold` (the destination refuses to resolve a claim: binding mismatch, claim unavailable, no durable effect): result `unknown` (post-commit) or `observed` (effect-free reconcile), `observed_state` `unknown`, `retry_eligible` false, a non-empty `reason`, and no destination state established. Golden fixture `executor-unknown-recovery-hold-route-b` (planted from the runtime recovery module; no live scenario reaches it).

Decided by the owner after the P2 conformance run (2026-10-17, asked one at a time; the first and third differ from the recommendations):

10. DECIDED. Legacy recovery layout: new layout only. Replay refuses a recovery report inside `observations` (the contract draft already does). Sequencing in P3: the runtime moves to `recovery_observations` first, then Replay tightens, so the runtime's real exports are never rejected in between. Recommendation had been to accept both during alpha.
11. DECIDED (recommendation). Replay's extra checks: immutable `started_at` per attempt, refusal of result `observed` with `attempted` true, and refusal of result `executed` with a null observation are written into the contract (draft changes, one PR). Replay stops requiring members the contract leaves optional, and the contract requires the members that are always present. Replay tightens the `reconciled_existing` marker to acknowledged or partial rows.
12. DECIDED. Replay emits the contract's refusal codes (a `code` field on its import errors) instead of tests mapping message patterns. Recommendation had been to keep test-only patterns for now. This is a Replay interface change in P3.

## Appendix A. F-20 to F-23 as the first golden cases

| Finding | Mismatch | Golden fixture(s) in `contracts/execution-attempt-lifecycle/fixtures/` |
|---|---|---|
| F-20 | Result `unknown` with terminal `executed`, observation null and `observed_state` `unknown`, emitted by runtime route C when the observation is unavailable. Consumer rejected it. | valid: `executor-unknown-ack-unobserved`, `executor-unknown-recovery-observation-route-b`, `executor-unknown-recovery-unavailable-route-b` (the route B shapes, added 2026-10-17). invalid (guard against over-correction): `executor-unknown-with-validated-observation`, `executor-unknown-recovery-state-contradiction`, `executor-terminal-failed-vs-status`, `executor-dropped-terminal-event`. |
| F-21 | Control Plane single-row `acknowledged` or `partial` attempt with `acknowledgement = {reconciled_existing: true}` and no `attempted` row. Consumer required a start row. | valid: `control-plane-reconciled-existing-acknowledged`, `control-plane-reconciled-existing-partial`, `control-plane-normal-attempted-acknowledged`. invalid: `control-plane-dropped-start-record`, `control-plane-start-row-reconciled-existing-false`, `executor-dropped-start-event`. |
| F-22 | Overlapping resolution checks may complete in either order; consumer's journal-order rule assumed one. | valid: `resolution-checks-overlap-a-completes-first`, `resolution-checks-overlap-b-completes-first-listed-open-order`, `resolution-checks-overlap-b-completes-first-listed-completion-order`. invalid: `resolution-checks-sequential-reorder`. |
| F-23 | Test-only: two skipped tests made two requirement rows inconclusive. Not a boundary mismatch; no fixture. | none |
| F-10 (related) | Unknown members must not be silently dropped. | invalid: `undeclared-member-outside-extensions`. valid: `extension-namespace-member-preserved`. |

The valid fixtures show what the consumer must accept so the F-20 to F-22 regressions cannot recur silently. The invalid fixtures show the consumer's correct strictness was retained.

## Appendix B. Initial local consumer-conformance run (not a qualification)

This appendix records local runs on 2026-10-17 (the first, then a re-run after the `unknown` rule was refined; both against Replay `def0ee0f`). It is a first finding, not qualification evidence, and it has not been repeated in CI. No Replay code was modified or committed; the run used a throwaway adapter script kept outside every repository.

Method. Replay at `def0ee0f` (main, `src/agent_replay_bundle`) was called through the functions that map onto the contract: `importers._validate_v2_executor_rows` for executor rows and results, `importers._validate_repaired_run` for Control Plane attempts, and `refusal_evidence.validate_run(..., runtime_authority=True)` for the journal and checks. Fixture documents were translated to those call shapes with no content changes (empty reconciliations and observations, an `executor` attempt-identity namespace, empty decisions and refusals). These are private helper functions, not Replay's public import entry point, so this tests Replay's lifecycle rules but not the full import path.

Result at `def0ee0f` (re-run after the refinement of the `unknown` rule; 11 valid and 11 invalid fixtures):

| Fixture | Expected | Replay |
|---|---|---|
| the 9 original valid fixtures | accept | accepted (9 of 9) |
| `executor-unknown-recovery-observation-route-b` (new, real route B shape) | accept | rejected (mismatch): "execution result status 'unknown' contradicts the terminal attempt event 'executed'" |
| `executor-unknown-recovery-unavailable-route-b` (new, real route B shape) | accept | rejected (mismatch): same message |
| `control-plane-dropped-start-record` | reject | rejected ("lifecycle lacks its attempted start record") |
| `executor-dropped-start-event` | reject | rejected ("events do not start with attempted") |
| `executor-unknown-with-validated-observation` (replaces `executor-unknown-with-observation`) | reject | rejected, but by the terminal-event rule, not for the observation: Replay's exemption for `unknown` after `executed` requires observation null, so it refuses every non-null observation alike |
| `executor-unknown-recovery-state-contradiction` (new) | reject | rejected, same reason |
| `executor-terminal-failed-vs-status` | reject | rejected |
| `executor-dropped-terminal-event` | reject | rejected |
| `resolution-checks-sequential-reorder` | reject | rejected ("out of journal order") |
| `control-plane-start-row-reconciled-existing-false` | reject | accepted (mismatch) |
| `undeclared-member-outside-extensions` | reject | accepted (mismatch) |
| `extension-key-without-x-prefix` | reject | accepted (mismatch; Replay has no extension-namespace concept) |

Findings:

0. New finding from the refinement. Replay `_validate_v2_executor_rows` accepts result `unknown` after terminal `executed` only when `observation is None` and `observed_state == 'unknown'` (the F-20 fix in #36 covered route C only). Runtime route B legitimately emits `unknown` with a recovery observation and `observed_state` `applied` (or an `unknown` placeholder observation), so Replay at `def0ee0f` refuses legitimate route B output at the helper level, the same class of failure as F-20. This is a finding against the consumer (or a contract decision if the owners disagree with the refined rule), not fixed here. The two invalid `unknown` fixtures are refused by the same rule, so Replay currently cannot tell them apart from the valid route B shapes. Whether the full public import path refuses the real route B export (the producer export also copies the recovery record into `observations`) was not tested here and should be.
   Resolved (F-24, replay #37): the full public import path did refuse the real route B export, for three stacked reasons (observed-state key, failure evidence members, attempt/reconciliation requirement). Replay now accepts route B recovery reports (post-commit `unknown` and effect-free `observed`) under the rules in the contract README, retaining them as `executor_recovery_report`, never as a validated observation.

1. A start row (`attempted`) carrying `acknowledgement = {reconciled_existing: false}` is accepted. Replay only checks the marker to excuse a missing start row, so a wrong marker value on a normal row is never examined. Whether this is a consumer gap or a contract over-reach (the contract rule is a proposal) is a decision for the Control Plane and Replay owners.
2. An undeclared member inside `execution_result` is accepted by the helper function. These helper functions read specific fields and do not check member sets. F-10 protection in Replay lives in other checks (`_reject_unknown_members` for the top-level, producer profile and repository records); whether the full public import path refuses an undeclared member inside `execution_result` or a lifecycle row was not tested here and should be.
3. Replay has no extension namespace, so `extensions` members are neither preserved nor refused at this layer, and the key-form refusal does not exist. Consumer-side preservation (level P) is entirely unimplemented there and is untested.

Regression check. The same adapter was run against Replay `0cfe7a63` (the revision before #36), also outside the repository. It rejected `executor-unknown-ack-unobserved` (F-20), `control-plane-reconciled-existing-acknowledged` and `-partial` (F-21), and `resolution-checks-overlap-b-completes-first-listed-open-order` (F-22), and accepted everything else that `def0ee0f` accepts. So the golden fixtures reproduce the three V1 boundary failures at the old revision and pass at the fixed one. The two other overlap fixtures pass at both revisions, so only one fixture exercises the F-22 regression.

Route B capture. The route B shape in the new fixtures was captured by running the runtime's own component test (`tests/test_atomic_post_commit_unresolved.py`, 5 passed) and the qualification scenarios SCN-C06 route B (2 passed) against pristine pinned components (runtime `4a83b175`, Control Plane `a34c3dc2`, Replay `def0ee0f`, ODES `5675f1b9`), then calling the runtime `export_execution_artifacts` on the real post-commit failure. The real result was status `unknown`, `attempted` true, `acknowledged` false, `newly_executed` false, `observed_state` `applied`, `observation` `{claim_state: consumed, effect_id, operation_digest, retry_eligible: false, status: applied}`, with attempt events `attempted` then `executed`; the export's `observations` list carried the same recovery record. Fixture ids, digests and times are synthetic.

Update 2026-10-17 (replay #37 and #38, main 8eaf3a42). The three helper-level conformance mismatches recorded above are closed in Replay: an undeclared member inside the execution result is refused, a start row marked `reconciled_existing: false` is refused, and the reserved `extensions` object (`x-` names) is accepted at the export top level, in the result and in the observation, and retained in the record. Route B recovery reports (post-commit `unknown`, effect-free `observed`, statuses `applied|partial|hold|unknown`) import on the public path. Qualification keeps the old Replay pin until the end-of-alpha pin refresh, so qualification results still reflect `def0ee0f`.

Limits. Local runs, helper-level functions only, fixtures synthetic, shapes read from the working checkouts, which may not be the revisions of any qualified tuple.
