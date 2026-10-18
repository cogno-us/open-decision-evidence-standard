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

Decided by the owner, second batch (2026-10-17; contract draft changes 2, still `0.1.0-draft`). Items 14 and 15 differ from the recommendations:

13. DECIDED (recommendation accepted). Empty observation: `observation` is null or a typed observation; `{}` is never valid. Pinned by invalid fixture `empty-object-observation` (`schema_violation`) and a README sentence.
14. DECIDED (the owner overrode the recommendation, which had been to keep result `unknown` with a null observation after an ambiguous dispatch; the owner asked for a contract status that carries the reading, then accepted the recommended shape, a narrow rule relaxation). Narrow rule relaxation: result `unknown` may carry a validated observation only when its `state` is `absent` or `unknown`, so the validated follow-up reading after an ambiguous dispatch (timeout, lost acknowledgement) is carryable. `unknown` with validated `applied`/`partial` stays invalid (`unknown_with_validated_observation`, item 8 unchanged). `observed_state` equals `observation.state`. No new enum value. This closes the route C gap. Fixtures: valid `executor-unknown-validated-absent-after-ambiguous-dispatch`, `executor-unknown-validated-unknown-after-ambiguous-dispatch`; invalid `executor-unknown-with-validated-observation` (applied), `executor-unknown-with-validated-partial-observation`, `executor-unknown-validated-absent-state-mismatch` (`unknown_state_mismatch`).
15. DECIDED (the owner overrode the recommendation, which had been to relax Replay's old rule so a denied or failed result with no observation may report `absent`). Strict null-observation rule, the old Replay rule kept: whenever observation is null, `observed_state` is `unknown` for every result status. New code `null_observation_state_mismatch` (clearer than reusing `unknown_state_mismatch`, which now covers only non-null observations). Valid fixture `executor-denied-attempt-event` changed to `unknown`; invalid `null-observation-state-absent`, `null-observation-state-applied-failed-result`.
16. DECIDED (recommendation accepted). `x-` extension members are accepted and preserved on resolution journal events, journal inputs, resolution checks, check inputs and Control Plane attempt rows (closed sets, extras only via `extensions`, otherwise `undeclared_member`/`invalid_extension_key`). Fixtures: valid `resolution-journal-checks-extensions-preserved`, `control-plane-attempt-extensions-preserved`; invalid `resolution-journal-extension-key-without-x-prefix`, `resolution-check-undeclared-member`, `control-plane-attempt-undeclared-member`, `control-plane-attempt-extension-key-without-x-prefix`.
17. DECIDED (recommendation accepted). Mixed layout is refused: `observations` lists only the validated observation the result carries (`observations_mismatch`), and a recovery report in `observations` is `schema_violation`. Pinned by `mixed-layout-observations-disagree-with-result` and the existing `recovery-report-in-observations-member`.

Decided by delegation, third batch (2026-10-17). The owner supplied the next engineering addenda and said, "I don't want to answer 40 questions." Claude answered the 13 journal questions, GX-1 to GX-14, IX-1 to IX-14 and the route C naming question with the most conservative default: keep the draft as written unless the code shows the draft is wrong. Every answer is reversible while the contracts stay `0.1.0-draft`, and none freezes anything. The owner reviews them at the end. The six marked REVIEW matter most.

18. DECIDED (default, owner review pending).
- 18-J1 REVIEW. Document identity: a wrapper or sidecar supplies `contract` and `contract_version`. The producer and Replay do not change before the freeze review.
- 18-J2. Journal mode stays optional in the contract. Replay's refusal of a record without a runtime-authority profile stays a recorded divergence.
- 18-J3. Extensions stay allowed on every declared object (decision 1). Replay's fixed-set refusals stay recorded divergences. The six-member `runtime_authority` stays closed.
- 18-J4. DONE. Decision result `deny` and reconciliation result `safe_to_retry` are removed from the closed enums. Both were declared and never produced. A record carrying either is `unknown_enum_value`. Fixtures: invalid `deny-decision-result`; `safe-to-retry-result` now expects `unknown_enum_value`.
- 18-J5. `reason_vocabulary_version` stays closed to `runtime-authority-reasons/0.1`. A real version change is a major bump (decision 6).
- 18-J6. `observations` equality stays per effect in acceptance order. Replay's global order stays a recorded divergence.
- 18-J7. The five single-producer rules stay in the contract.
- 18-J8. Opaque members stay opaque until their own boundary contracts exist.
- 18-J9. DONE. `decided_at` and attempt `started_at` must be timezone-aware (`timestamp_invalid`). Fixtures: invalid `naive-decided-at`, `naive-attempt-started-at`.
- 18-J10. No integrity member. Integrity stays with the ODES export package and the consumer's digest.
- 18-J11. The commitment canonical form stays the one used for `effect_id`.
- 18-J12. A run is identified by `run_id` only. File layout is out of scope.
- 18-J13. Held decisions do not carry the proposal commitment. Their `effect_id` stays unverifiable inside this boundary, and the contract says so.
- 18-GX. Governed exchange: GX-1 scope confirmed as drafted. GX-2 `content` stays an object. GX-3 time zone required. GX-4 closed message set. GX-5 `assess_message` (18 members) is the source of truth, and `profile.md` is corrected in the end docs cleanup. GX-6 both `denied` and `deny` stay accepted, with no normalisation. GX-7 the lineage and derivative-result invariants are intended. GX-8 the transport envelope stays open. GX-9 `complete` stays as the default state with no export. GX-10 `state-<n>` stays stricter than the consumer. GX-11 no store model. GX-12 no validation context for now (revisit if an `ocs validate` command needs one). GX-13 the `execution` summary stays a union. GX-14 the first-failure order stays and is documented as part of the contract.
- 18-IX. Index registry: IX-1 scope confirmed. IX-2 REVIEW. `x-` extensions stay permitted on submission, stored link and epistemic status, but the link digest does not cover them and the Index drops them, so they are neither signed nor preserved. A later link profile (`index.link.v2`) may commit to them. IX-3 the statement strings stay fixed, owned by the Governor as `chain/PROTOCOL.md` says. IX-4 REVIEW. No single canonicalisation is chosen. Each boundary names its own. IX-5 an unattested stored link stays refused. No migration is needed because the old store was in memory only. IX-6 time zone optional, a naive value is read as UTC. IX-7 body-validation 422s stay out of the contract. IX-8 stricter than the Index, confirmed. IX-9 REVIEW. The Index thresholds stay in the draft and are re-judged at the Index freeze. IX-10 no rename. The F-19 limit stays documented. IX-11 the status and reason table is confirmed, and 200 and 201 stay indistinguishable in the body. IX-12 the `chain_attestation_check` shape stays as drafted. A zero `statementSHA256` is not modelled. IX-13 no relation pairing constraint. IX-14 ODES references BitRep's snapshot contract and does not carry its own.
- 18-C. Route C stays the qualification term for the Control Plane adapter path (runtime `docs/execution-boundary.md`). The contract itself names routes A and B by class and does not name C.

19. DECIDED (default, owner review pending). Programme 2, stream X1 (2026-10-17): two optional extension-profile contract drafts, each `0.1.0-draft`, not frozen, layered on the journal and lifecycle contracts by reference, editing none of them and adding nothing to the core schema or `pder-v0.1`. The questions each draft would have asked are recorded as numbered defaults in its README; every one is reversible while the draft stays `0.1.0-draft`. Code check (control plane #42) is authoritative where an addendum differs.
- 19-C1. `bounded-deferral`. DEFER is a bounded `hold`, not a new decision result (the control plane returns `hold`, never `deny`; the journal enum stays `authorized`/`hold`). Deadline is `opened_at` plus the action class `max_status_age_seconds`. Expiry, resolver timeout, garbage or error resolve to REFUSE (a terminal `hold`), never RELEASE; a resolver releases only what policy deferred and never overrides a refusal; the first response decides; RELEASE is not authority (a later authorized decision with its own `effect_id` is); no effect is observable before RELEASE and a refused effect never is. Optional structured refusal notice (closed, extension-free). README defaults 1 to 14.
- 19-C2. `effect-reversibility`. Two optional `x-` members on an action class, `x-effect-class` (`stageable | stallable | blocking`) and `x-reversibility` (`irreversible | reversible_until | reversible_at_cost`), carried in the journal's open `action_class` object with no journal change. The code's `irreversible` flag is kept and equals reversibility `irreversible`. Reads of protected data are irreversible; a cached `open` snapshot is accepted only for reversible classes inside the reversal window and the class `max_status_age_seconds`; a recorded closure overrides any snapshot; an unobservable counterparty takes the stricter value (`irreversible`, strict default `closed`). A blocking effect is never sent while a DEFER is open, and stageable and stallable effects only stage or start stalled; lost acknowledgements (D04) are classified by phase and never retry eligible. README defaults 1 to 16.

20. DECIDED (default, owner review pending). Programme 2, stream X2 (2026-10-17): four optional extension-profile contract drafts, each `0.1.0-draft`, not frozen, layered on existing contracts by reference, editing none of them and adding nothing to the core or `pder-v0.1`. The questions each draft would have asked are recorded as numbered defaults in its README; every one is reversible while the draft stays `0.1.0-draft`.
- 20-C7. `non-broadening-delegation`. Code fact: the Control Plane refuses any grant with `parent_grant_id` (`delegation_profile_unsupported`), so the contract defines the profile that would replace the refusal and claims no current support. Defaults: parent by id, non-strict subset, no pooling across parent permissions, no sibling aggregate budget, depth strictly decreasing, child issuer is the parent's grantee, status and revocation out of scope (README questions 1 to 12).
- 20-C8. `authority-lineage`. Defaults: one previous hop per hop (chain, not DAG); hop hash is the Control Plane commitment form over six members; a broken link is a flagged state, not a violation, except a self-inconsistent hop (`hop_hash_mismatch`), which is always refused; the flag names the first break walking toward the origin; the effect hop is not bound to `effect_id` here. A flagged effect is never read as authorized (README questions 1 to 10).
- 20-C10. `two-party-reconciliation`. Defaults: where the comparison runs is unspecified; one opaque `event_digest` per side; a mismatch is held or escalated, never accepted; no authoritative side; a missing peer is `awaiting_peer` and never ages into a commit; one row per event per document; two parties only (README questions 1 to 11).
- 20-C11. `source-family-counting`. Defaults: the producer declares families, nothing is inferred; family ids are opaque; inheritance goes through the direct source and so is transitive; two originals of one family count once; derived records inherit; no weights; correlated families are declared as one; a satisfied claim authorizes nothing here (README questions 1 to 11).

21. DECIDED (default, owner review pending). Programme 2, stream X3 (2026-10-18): two optional extension-profile contract drafts for component changes that merged opt-in and had no contract, each `0.1.0-draft`, not frozen, layered on the journal and lifecycle contracts by reference, editing none of them and adding nothing to the core or `pder-v0.1`. Unlike the X1 and X2 drafts, producers now exist: the valid fixtures are captures of real runs of the Control Plane (main `83b49b5`, which contains #44 and #45), not hand-written documents, and each README states which rules the producer enforces and which exist only in the contract. The questions each draft would have asked are recorded as numbered defaults in its README; every one is reversible while the draft stays `0.1.0-draft`. Code is authoritative where a PR body or the addendum differs.
- 21-A. `operation-identity`. Journal check on records produced by the Control Plane at `9d00f38` and `83b49b5`: every default-path run still conforms to the journal contract, so no journal change was made. A run record produced with the profile on is refused by the journal contract (`undeclared_member` for the three new lists, `check_id` on refusals; `schema_violation` for `operation_id` and `operation_issuer` in the binding extension), and nothing else. Default: the profile is carried as a sidecar projection with the run record as optional context, and the journal contract is not edited; declaring the members as optional journal members is a possible minor bump, left for the owner. Other defaults: renewal rows are replayed in append order with the producer's check order (not admitted, not the issuer, not a new revision); an operation is licensed for its first revision and each accepted renewal; `merged_into` must name an admitted operation (the Control Plane writes null, the runtime sidecar checks admission, so the rule is contract-only on the Control Plane path); the destination capability `operation-identity/0.1` and the definitive rejection `operation_already_committed` are stated as behaviours D1 to D6, with only D5 and D6 visible in a record; the runtime sidecar's `operation_superseded` refusal is not admitted (README defaults 1 to 16).

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

## Appendix C. Boundary contract drafts (index)

All drafts stay `0.1.0-draft`; none is frozen (item 5). Each directory holds `README.md`, `schema.json`, `validate.py` and golden fixtures, and a test file `tests/test_contract_<name>.py`.

| Contract | Boundary | Producer | Consumers | Notes |
|---|---|---|---|---|
| `contracts/execution-attempt-lifecycle/` | B2 and B3 attempt rows and journal protocol | Runtime executor, Control Plane | Replay | The first draft; its attempt and journal rules are delegated to by the journal contract. |
| `contracts/control-plane-journal/` | B3 Control Plane run record (`BoundedRunRecord`): decisions, attempts, observations, reconciliations, refusals, checks, closeouts, input time floors, journal, vocabulary changes | Control Plane bounded workflow | Replay (and through it the Evidence pack), Exchange reference runtime (append-only reliance) | Modelled on 26a7e659 and Replay 7c6888f; 13 valid (10 real producer runs) and 64 invalid fixtures; its 13 questions resolved by decision 18; records which components currently diverge. |
| `contracts/governed-exchange/` | Exchange transport (plan P1) and what the exchange's consumers rely on: governed message, transport envelope, acknowledgements, delivery result, recipient result, GAX retained-artifact export with lineage, IMX successor packet and acceptance, transport evidence summary | Governed Exchange reference runtime and transport (`gax_ref.py`, `gax_ref_runtime.py`, `transport.py`) | Qualification suites, the two ends of a delivery | Modelled on cognous-governed-exchange main ec6ba5b; 37 valid (most captured from the real producer code with stub peers) and 86 invalid fixtures; GX-1 to GX-14 resolved by decision 18 (Appendix D); records where the exchange diverges. |
| `contracts/index-evidence-registry/` | Index evidence API (plan P1): link submission with its BitRep v1 attestation, stored link, link outcome (200/201/401/409/422/503), the BitRep verification result, epistemic status, and the chain profile's attestation binding | Index (`app/api/evidence.py`, `app/evidence/*`), vendored BitRep verifier, chain adapter | Qualification suites (SCN-C03, SCN-C04, v1-probes), BitRep link profile, chain readers | Modelled on Index main d17b8ac (carries #25); 33 valid (most captured from the Index's own code with a throwaway key) and 63 invalid fixtures; IX-1 to IX-14 resolved by decision 18 (Appendix E); records where the Index diverges. |
| `contracts/non-broadening-delegation/` | Optional extension profile: a delegated grant is a subset of its parent in amount, time window and scope; the delegation record (`parent_grant_id`, `may_delegate`, `remaining_depth`) | Grant issuer (Authority Context) | Control Plane resolution (would replace the `delegation_profile_unsupported` refusal; today it refuses every delegated grant), Replay, Evidence pack | Draft only (catalog scenario C18); 7 valid and 23 invalid synthetic fixtures; no component implements it; 12 questions answered as defaults by decision 20. |
| `contracts/authority-lineage/` | Optional extension profile: hash-linked record grant -> delegation -> terminal effect; every terminal effect resolves to a grant or is flagged `lineage_discontinuity` | Whatever assembles a run's lineage (no producer today) | Replay, Evidence pack, auditors | Draft only; layers by reference on `non-broadening-delegation` and the journal `effect_id`; 10 valid and 22 invalid synthetic fixtures; 10 questions answered as defaults by decision 20. |
| `contracts/two-party-reconciliation/` | Optional extension profile: where sender and receiver both record an event, a mismatch is detected before commit and surfaces as a mismatch, never two valid records (catalog D04 ambiguous delivery) | Whichever party or third place compares (no producer today) | Replay, Evidence pack, the two ends of a delivery | Draft only; layers by reference on the exchange and lifecycle contracts; 7 valid and 26 invalid synthetic fixtures; 11 questions answered as defaults by decision 20. |
| `contracts/source-family-counting/` | Optional extension profile: confirmations and evidence counted by source family, not by record; retries, re-sends and derived records inherit the original's family (N retries of one message are one confirmation) | Whatever collects confirmations (no producer today) | Replay, Evidence pack, auditors | Draft only; layers by reference on the exchange and journal contracts; 8 valid and 21 invalid synthetic fixtures; 11 questions answered as defaults by decision 20. |
| `contracts/bounded-deferral/` | Optional extension profile: DEFER as a bounded `hold` with a deadline from the action class `max_status_age_seconds`; fail-closed resolution (expiry, timeout, garbage, error refuse); a resolver never releases a policy refusal; no effect before RELEASE; optional structured refusal notice | Deferral policy and resolver (no component implements it today; the Control Plane returns `hold`) | Replay, Evidence pack, any checker that no effect preceded a release | Draft only (C1, C3 of the 101726_B consolidation); 13 valid and 39 invalid synthetic fixtures including resolver fault injection; optional journal context for cross-document rules; 14 questions answered as defaults by decision 19. |
| `contracts/effect-reversibility/` | Optional extension profile: action-class members `x-effect-class` (stageable, stallable, blocking) and `x-reversibility` (irreversible, reversible_until, reversible_at_cost); cached-snapshot acceptance, recorded-closure override, strict default for an unobservable counterparty; dispatch phases against open DEFERs; lost-acknowledgement classification | Control Plane action class and run (no component implements it today) | Replay, Evidence pack, any checker of dispatch order and lost-ack handling | Draft only (C2, KAIROS effect classes and the L4 reversibility item of 101726_B); 18 valid and 40 invalid synthetic fixtures; optional journal and bounded-deferral context; 16 questions answered as defaults by decision 19. |
| `contracts/operation-identity/` | Optional extension profile: operation ledger (`operation`), `operation_renewal` and per-attempt `attempt_join` rows; shared `check_id` across journal events, resolution rows and refusals; destination capability `operation-identity/0.1` and definitive rejection `operation_already_committed`; operation id stable across grant revisions; issuer-only renewal; seven reason codes | Control Plane bounded workflow with `RuntimeAuthorityProfile.operation_identity` set (#45); destinations `LocalRefundDestination` and runtime `OperationIdentityDestination` (#109) | Replay, Evidence pack, any checker that one operation committed one effect | Draft only; sidecar projection over the journal run record; 12 valid (10 captured from real Control Plane runs at `83b49b5`) and 61 invalid fixtures; consumer-conformance note says what the producer enforces; 16 defaults by decision 21. |

## Appendix D. Governed exchange draft: open questions (P1, 2026-10-17)

Every item is a guess or a choice the draft made that the exchange owner or the doctrine owner should confirm. Nothing here changes a decision on record. The draft is `0.1.0-draft`, not frozen.

- GX-1. Scope. The boundary is taken as the plan's P1 wording ("Exchange transport") plus the P0 `produces` list for the exchange. Generation-fence refusal records (local SQLite, no cross-component consumer), the historical legacy store and the recovery artifact files are left out. The exchange's in-process use of the Control Plane, runtime, Replay and ODES is another boundary. Confirm.
- GX-2. The message `content` is declared an object. The code accepts any JSON value (it digests whatever it is given). Guess; the alternative is any JSON value.
- GX-3. Timestamps require a time zone offset on every message member. `assess_message` parses only `expires_at`, so a naive `created_at` is accepted today. The draft follows the transport's rule (`parse_time` refuses naive times) and the profile's "timezone-aware" statement.
- GX-4. The message is a closed set (undeclared member refused, extras only in `extensions`). The exchange accepts any extra member as long as the digest covers it. Confirm the closed set is wanted at the message layer, which makes extra members a contract change.
- GX-5. Required message members: the draft follows `assess_message` (18 members), not `profile.md` (15). Which is the source of truth, and should `profile.md` be corrected?
- GX-6. `execution.attempt_status` mixes vocabularies: the lifecycle contract's result statuses (`denied`), the Control Plane decision results (`deny`, `hold`) and the exchange's own (`interrupted_after_dispatch`, `evidence_export_failed`, `unresolved_duplicate`). Both `denied` and `deny` are accepted. Should the exchange normalise to the lifecycle vocabulary?
- GX-7. Lineage rules (state and relationship pairing, `effect_reexecution` false, denied-recovery flags) and the derivative-result rule (attempted and newly_executed false) are inferred from how the exchange constructs exports and results. The exchange's own validator checks none of the lineage ones. Confirm they are intended invariants.
- GX-8. The transport envelope's `governed_message` is open (only the members transport reads are pinned) because transport carries messages the profile refuses. Confirm that layering, or require profile conformance at the transport. `acknowledgement_for_attempt_id` is always null today; the draft allows a string or null.
- GX-9. `result_state: complete` is the default of `RecipientOutcome` for informational and not-eligible outcomes, while the interface document says the state mirrors the export state. The draft lists `complete` as a state with no export. Confirm, or give those outcomes a name of their own.
- GX-10. The successor `state_version` is `state-<n>` in the draft. The consumer accepts anything whose last dash-separated segment is an integer. Stricter than the consumer; confirm.
- GX-11. Successor head, lineage and rollback rules are stateful (store content). The draft states the status vocabulary and two invariants but does not model the store. Add a reference store model to the validator?
- GX-12. Rules that need peer artifacts (operation and proposal commitments, replay bundle digest equality, authority reference, route and registry claims, trusted time) are listed in the README as not checkable from one document. Should `validate()` accept an optional context so they become checkable?
- GX-13. The `execution` summary is the union of the shapes returned on several code paths; only `attempted` is required. Which members belong to which path is not pinned. Should the paths become separate members?
- GX-14. Retained-export digest checks stop at the first failure in the exchange's own order, so the refusal code depends on that order. Report all failures instead?

## Appendix E. Index evidence-registry draft: open questions (P1, 2026-10-17)

Every item is a guess or a choice the draft made that the Index owner or the doctrine owner should confirm. Nothing here changes a decision on record. The draft is `0.1.0-draft`, not frozen.

- IX-1. Scope. The boundary is the plan's "what the Index exposes and consumes, link attestation, BitRep attestation mapping": links, link outcomes, epistemic status, the verification result and the chain attestation binding. Claims, governance and evidence-submission routes, the legacy `api/` and `protocol/` layers and the on-chain claim and lifecycle records are left out. Confirm.
- IX-2. Extensions. The draft allows `x-` `extensions` on a submission, a stored link and an epistemic status, as in the other drafts. The Index drops them (no `extensions` member, undeclared members ignored) and the link content digest covers only five members, so an extension cannot be signed. Should a later link profile (for example `index.link.v2`) commit to extensions, or should they be removed from this contract?
- IX-3. Statement vocabulary. `index.link.v1` is described in the Index as provisional and Index-side. The chain strings (audience, subject form, `index-support/1`, `index-challenge/1`) are listed in `chain/PROTOCOL.md` as awaiting Governor approval. The draft treats all of them as fixed. Confirm, or name the owner.
- IX-4. Canonicalisation. The link content bytes are sorted compact JSON with non-ASCII escaped (`ensure_ascii` true) and `strength` as a float; the exchange uses a different canonicalisation (`json-sort-keys-compact-v1`). Should the stack have one, and which?
- IX-5. Unattested stored links. `EvidenceService.create_link` can store a link with no attestation; the route never does. The draft refuses such a link (`link_without_attestation`). Confirm, and say how data that predates #23 (the old store was in memory only) is to be treated.
- IX-6. Timestamps. `Link.timestamp` and `last_computed_at` are naive UTC `datetime` values. The draft accepts them with or without a zone. Should the contract require a zone?
- IX-7. Body-validation refusals. A malformed link body (both or neither target, strength above 1, unknown relation) is a FastAPI 422 with a list `detail`, not the `{reason, message}` object. The draft models only the attestation refusals and has no code for these. Should there be a `reason` for them?
- IX-8. Strictness. The draft refuses a string or boolean `strength` that the Index coerces. Confirm that the contract is stricter than the implementation here.
- IX-9. Epistemic rules. The draft states the Index's own thresholds (supported above 2.0, refuted above 3.0, robustness total/10, independence distinct sources/5) as contract rules. These may be implementation detail that should be free to change; if so only ranges and the closed status set belong in the contract. `deprecated` is never computed and is not judged.
- IX-10. Independence naming. `independence_score` counts distinct source identifiers, not independence of origin (F-19). Should the contract rename it or add a basis member so a consumer cannot read it as independence of evidence?
- IX-11. Outcome shapes. The 409 `attestation_id_conflict` fixture is written from the route code, not captured against a store, and the idempotent 200 returning the same link is store state and not checked. Confirm the status and reason table, including whether 200 and 201 should be distinguishable in the body.
- IX-12. Chain check document. `chain_attestation_check` is an input shape this draft invented around the adapter's expected values (the adapter takes files and arguments). Chain identifiers in fixtures are synthetic bytes32 values; keccak was not computed. A zero `statementSHA256` (no statement) is not modelled. Confirm the shape.
- IX-13. Relation vocabulary. Relation types are one closed set of seven for both evidence links and claim-to-claim links; the Index applies no pairing (a claim-to-claim link can be `contradicts`, an evidence link `depends_on`), and only the first three affect weights. Should the contract constrain the pairing?
- IX-14. Trust snapshot. The operator trust snapshot (`bitrep-trust/1`) decides every verification and belongs to BitRep's contract. Should ODES carry its own contract for snapshot publication, currency and anti-rollback, or only reference BitRep's?
