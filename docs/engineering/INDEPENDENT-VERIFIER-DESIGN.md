# Independent verifier and mutation suite: design (C5, C6)

Status: design only, 2026-10-18. Programme 2, stream V1 (tracker cogno-us/cognous-control-plane#43, backlog #42). No production code, no contract, no pin, no profile and no verdict is changed by this document. Nothing here is frozen, nothing is a qualification input, and nothing is a release or publication claim.

Revised 2026-10-18 (decision 28 of `ODES-INTERCOMPONENT-CONTRACTS.md`, after the first mutation measurement): the taxonomy gains a family H for damage to the outside-held witness and holder-inventory artifacts, and the tier named V3 below is now the verifier's witness re-derivation (built, verifier PR #10) rather than the deferred decision re-derivation. See section 4.3 ("Revision of 2026-10-18, family H") and the stage table in section 7. The revision is post-hoc: it was written after the first measurement and does not change what catalogue v2 measured.

Status update 2026-10-18 (docs only): the stage table in section 7 now records what merged afterwards (verifier PRs #10 to #17, qualification #103 to #111, decisions 26 to 31); the design text elsewhere is unchanged, apart from the H8 row, which follows decision 30-A. The verifier is `cogno-us/cognous-open-control-stack-verifier` (command `cognous-verify`). All contracts stay `0.1.0-draft`.

Source: addendum "Post-V1 Candidates from Six arXiv Papers" (2026-10-17), sections 3.3 (what an attestation can claim), C4, C5, C6 and section 5 (evidence limits). Where the addendum and the code disagree, the code wins and the disagreement is listed in section 8.

Revisions read (read-only clones, main): Control Plane `87f02336`, Replay `d0e7b368`, Evidence Pack `76f5280a`, Index (`cogno-us/the-index`) `d17b8ac2`, ODES `321bd404`, Execution runtime `10a11d03`, Qualification `33609746`, Hub (`cogno-us/cognous-open-control-stack`) `afca5bbd`. Statements below about code were read from those revisions. Where a statement was not checked by running code it says so.

## 1. Summary

1. **No attestation of Control Plane decisions exists today.** The Index only verifies externally issued BitRep v1 link attestations (issuer signature under an operator trust snapshot) and signs nothing. The addendum's assumption of "mandatory Index attestation" for decisions does not match the code. What exists for decisions is: producer-declared commitments, a cross-record validator in ODES (`control-plane-journal`, `execution-attempt-lifecycle`; draft, not wired into any component runtime path), commitment recomputation in Replay and the Evidence Pack, and an HMAC export signature (shared secret, integrity only).
2. **Decisions are consumed, not re-derived, everywhere downstream of the Control Plane.** Replay and the Pack recompute identities (`effect_id`, proposal commitment, payload commitment) with their own copy of the canonical-bytes recipe, but they take `result` and `reasons` as given. The Pack counts authorizations from the `result` label. Only the ODES journal validator checks `result == authorized` iff `reasons` is empty and a binding is present, and it is not called by Replay or the Pack.
3. **Decisions cannot be re-derived from the retained record.** Each `ResolutionInput` keeps an allow-listed set of scalars and a `record_commitment`, not the record. Only 1 of 121 reason codes (`grant_revoked`) is declared `recomputable` in the registry. A verifier can therefore check consistency of what the record says (tier V1 to V2 below). It cannot establish "this decision is what the pinned controller computes" without a decision witness the stack does not produce (decision re-derivation, deferred, no tier assigned; the tier named V3 is a different thing, see section 3.3).
4. **"Receipts from a trusted monitor" do not exist as such.** The nearest real artifacts are destination ledger rows (executor-written, effect side) and the Control Plane journal `check_events` (controller-written, same process, so not a receipt). This design uses the destination ledger as the V1 receipt source and says plainly that its trust is by deployment, not by cryptography.
5. **Existing "mutation" work is a different thing from what C6 asks for.** `tools/adversarial_mutations.py` (3 cases), the hub `tools/*_mutations.py` (41 cases in five tools) and the seven preview negative controls remove or bypass a control in code and check that tests fail. C6 mutates the trace and checks that a verifier rejects it. Both are kept; their denominators are never mixed.
6. **Proposal:** one verifier in its own repository (own parser, own canonicalization, standard library only, no component imports), an ODES draft contract for its report, and a mutation harness plus corpus in the qualification repository that reports per category and is report-only. Five stages, section 7.

## 2. What an attestation can claim today (question 1)

The three ActiveEvidence properties, applied to what the stack has:

- **P1 decision consistency with the pinned controller**: the retained decision is the one the pinned controller code would produce from its inputs.
- **P2 completeness of the committed record against receipts from a trusted monitor**: nothing the monitor saw is missing from the committed record, and nothing in the record lacks a receipt.
- **P3 semantic quality**: the decision was the right one. Measured separately, never certified.

### 2.1 Claim table, by artifact

| Artifact (code path) | What it does today | P1 | P2 | P3 |
|---|---|---|---|---|
| Control Plane `BoundedAuthorizationWorkflow.decide/execute` (`bounded.py`) | Derives decisions from live resolver reads; re-derives again at effect time with the same code (`execute` re-runs `_resolve` and compares the binding) | It is the pinned controller; it attests nothing about itself | Journal `check_events` are its own write-ahead record | none |
| Control Plane journal (`check_events`, `resolution_checks`) | Append-only local records, transaction-protected; no signature, no hash chain, no external custody (the contract says so) | none | The journal shows evaluations that opened and did not complete (`interrupted`); it is a record, not a receipt | none |
| Replay `import_bounded_workflow`, `refusal_evidence.validate_run` | Recomputes `effect_id`, proposal commitment and binding fields, payload commitment, manifest digest (own `canonical_bytes` copy); checks journal protocol and binds each completed journal check to an actual resolution check by content | Identity consistency only; does not recompute `result` or `reasons` | Record-internal completeness (closeouts, journal order); no external receipts | none |
| Evidence Pack importer | Runs the pinned Replay validator, recomputes local record commitments, reports `independent_verification: unavailable` and `U_INDEPENDENT_VERIFICATION_UNAVAILABLE` | Same as Replay | none | none; states "does not establish operational effectiveness" |
| ODES `control-plane-journal` and `execution-attempt-lifecycle` validators (`contracts/*/validate.py`) | Closed member sets, cross-record rules (71 distinct refusal codes across the two contracts; `decision_result_inconsistent`, `invalid_effect_identity`, `journal_unbound_completion`, ...) | Cross-record consistency of the document; commitments are producer-declared and unverified at this boundary (journal README) | Record-internal only | none |
| Replay HMAC signing (`signing.py`) | HMAC-SHA256 over the bundle with a shared secret | none | none | none; export integrity under a shared secret, not issuer identity |
| Control Plane `decision_input_profile.py` | Standalone non-authorizing verifier of a proposed Decision Input Commitment Record: commitments, evidence classification, reason precedence | Candidate witness shape (see 3.5) | none | none; not wired into the live workflow |
| Index (`app/evidence/link_attestation.py`) | Verifies an externally issued BitRep v1 envelope for a link: issuer signature, trust snapshot, statement bound to the link's content digest | none: not about decisions | none | none: "says nothing about whether the link is true or the issuer is authoritative" (module docstring) |

Three things follow.

- No component signs or attests a Control Plane decision. A statement of the form "the Index attests decision D" is false today. Section 5 therefore words the scope statement for a **verification report** from the proposed verifier, and avoids the word "attestation" (default 11).
- P1 is claimable today only for the part the record retains: identity consistency (commitments recomputed by Replay, Pack) and internal consistency (ODES validator). It is not claimable as consistency with the pinned controller, because the controller's inputs are not retained (3.3).
- P2 has no external receipt source in the record export. The ODES journal contract says the same: the run record "carries no signature, digest or attestation member".

### 2.2 Evidence for the claims above

- Index: `app/evidence/link_attestation.py` (profile `index.link.v1`, "Verified means issuer signature only"), `app/api/evidence.py`, `app/evidence/service.py` (the attestation index is an in-memory dict). No code path in the Index reads a Control Plane record.
- Control Plane decision: `decide()` builds `RuntimeDecision` with `result = "authorized" if not reasons else "hold"`; `deny` is never produced (the `RuntimeDecision.result` type still lists it; ODES #69 removed it from the journal contract).
- Replay: `importers.py` `_validate_proposal_binding`, `import_bounded_workflow` (effect-id recomputation), `refusal_evidence.py` `validate_run` (journal protocol, check binding). A search of Replay source for the string literal `authorized` finds only the refusal rule "refusal requires original authorized decision"; no rule ties `result` to `reasons`.
- Pack: `importer.py` `_decision_result` reads `result`, falling back to `decision`, `authorization` or `status` (a lenient label read); `_authorization_summary` counts those labels.

## 3. Derive or consume, and where a verifier sits (question 2)

### 3.1 Map of code paths

| Path | Derives | Consumes as given |
|---|---|---|
| CP `decide()` | `result`, `reasons`, `binding`, `effect_id` from resolver reads and the proposal | nothing from a prior decision |
| CP `execute()` | re-derives at effect time with the same code, compares to the persisted binding, writes `EffectTimeRefusal` on change | the persisted decision (equality-checked) |
| CP `_observe_and_reconcile` / `_reconcile_observation` | reconciliation `result` from the destination observation and an `ObservationPolicy` | destination `observe()` output |
| CP `decision_input_profile.verify_record` | commitments, evidence status, precedence over a closed record | declarations (it says so) |
| Runtime `DurableRefundDestination` (sqlite: `effects`, `attempts`, `attempt_events`, failure history) | nothing about authorization | operation digest, grant, target, amount from the caller |
| Replay | effect ids, proposal and payload commitments, journal protocol | `result`, `reasons`, `resolution_inputs` values, destination state |
| Pack | local commitments over records; counts of authorized, held, denied | everything Replay accepted |
| ODES validators | cross-record rules over a mapped document | commitments (producer-declared) |
| Qualification harness (`_c_2b_helpers.py`, D5 gate) | `unauthorized_effects`, `excess_duplicate_effects` as returned by each trial; per-scenario outcomes (JUnit) | trial-returned counters |

The hard gate (zero unauthorized, zero excess duplicates) is asserted on counters the trial itself returns. No stage recomputes them from the retained record and the destination ledger with separate code. That recomputation is the highest-value first job for an independent verifier (tier V4 below).

### 3.2 Duplicated canonicalization is copying, not independence

The canonical-bytes recipe (`json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False, allow_nan=False)` to UTF-8) appears as separate copies in Control Plane `bounded.py` and `decision_input_profile.py`, Replay `reconstruction.py`, Runtime `safe_executor.py` and Pack `importer.py`. The Index uses a different one (ASCII-escaped) for link content and BitRep statements. The copies agree because they were copied. A bug in the recipe (for example float formatting, which is Python `repr` semantics) is shared by all of them. An independent verifier must have its own implementation **of the same pinned profile** (byte-compatible with the committed digests), proven by conformance vectors, and must reject inputs on which the profile is ambiguous.

Parsing is a separate gap. Strict JSON handling (reject duplicate object members and non-JSON constants such as `NaN`) exists in two places only: Pack `admission.py` and Index `app/bitrep_verify/trust.py` (`strict_json`). The Control Plane record store, the Replay loader and CLI, and every ODES `validate.py` use plain `json.load(s)`. Python's parser keeps the last duplicate and accepts `NaN`; the check run for this document:

```
python -I -c 'import json; print(json.loads("{\"result\":\"hold\",\"result\":\"authorized\"}"))'   ->  {'result': 'authorized'}
python -I -c 'import json; print(json.loads("{\"x\":NaN}"))'                                         ->  {'x': nan}
```

So a document whose raw text carries both `"hold"` and `"authorized"` for one member is read as `authorized` by those consumers, and no later stage can see the first value. The verifier's parser closes this class (category W1, W2 in section 4).

A further hidden coupling to carry into the design: the proposal commitment is `commitment(proposal.model_dump(mode="json", exclude_none=False))`, a commitment over the Pydantic model dump, not over a wire document. A verifier can recompute it only from a proposal exported exactly as that dump (all fields, including nulls). Adding a defaulted field to `RuntimeProposal` changes commitments. The verifier input spec must say that (risk R3).

### 3.3 Why re-derivation is not available today

`decide()` records `ResolutionInput` rows with `observed` limited to an explicit scalar allow-list (`revision`, `status`, `version`, `state`, `observed_at`, `schema_version`, `interface_status`, `digest`, `grant_revision`, `runtime_authority_commitment`, `epoch`, `epoch_capability`), plus `record_commitment` over the full record. The record itself, the manifest body and the policy bodies are not retained ("no payload, identity chain, approver, mandate body, policy body, or evidence contents"). That is deliberate privacy minimization. Consequence: the full set of authorization rules in `_resolve_inputs` (about 330 lines of checks over `context`, `mapping`, `grant`, approvals, policy, conflict, evidence) cannot be replayed from the export. The registry marks 120 of 121 reason codes `typed_only` and one (`grant_revoked`, operands `input_type: grant`, `observed.status: revoked`) `recomputable` (`schemas/runtime_authority_reasons_0_1.json`; `derive_recomputability` in `reason_vocabulary.py`).

What a verifier can do, in tiers:

| Tier | Checks | Needs | Exists today |
|---|---|---|---|
| V1 wire and structure | strict parse; closed members; enums; extension names; times with offsets | the exported run record | Partly (ODES schema + validators; Pack admission for strict parse) |
| V2 identity and internal consistency | recompute `effect_id`, proposal, payload, manifest, horizon commitments; `result` iff no reasons and binding present; expected vs observed vs reasons for operands the registry declares; journal protocol; attempt and closeout lineage | run record + proposal export (+ manifest) | Pieces, in different components, none checking `result` vs `reasons` outside ODES |
| V3 witness re-derivation (revised 2026-10-18) | recompute, with the verifier's own canonical form, the per-ledger counts and chain heads and the witness's own digest chain that an outside-held witness (`witness-digest/0.1`) holds, from the retained record; check a holder inventory's closed shape (`holder-inventory/0.1`) | a witness file the Control Plane writes (`acp witness publish`), optionally a holder inventory | Yes: verifier PR #10, ODES contracts `witness-digest`, `holder-inventory` and the `verification-report` revision of decision 27 |
| (deferred, no tier) decision re-derivation | recompute the decision from a retained closed input record | a decision witness (not produced) | No. Candidate: the Decision Input Commitment Record (`decision_input_profile.py`), which lacks a `decision_id` link. Earlier text of this design called this tier V3; the name now belongs to the row above, and this one is stage S7 |
| V4 receipt completeness | ledger rows vs decisions and attempts, both directions; recompute the hard-gate counters | destination ledger export | Runtime exports ledger rows (`destination_effect`, `destination_attempt`, `destination_attempt_event`) with `operation_digest`; no sequence number, no chain |

V1, V2 and V4 are buildable without touching any component. Decision re-derivation needs a Control Plane change and is deferred (default 16). The witness tier V3 reads a file the Control Plane already writes and needed none. "Consistency with the pinned controller" (P1) is then measured, not certified: a differential run of the controller and the verifier over the same synthetic corpus reports agreement per category as counts with denominators (stage S5), and the report states that agreement on a corpus is not equivalence.

### 3.4 Receipts, precisely

| Candidate | Written by | Independent of the controller | Hash-chained or signed | Verdict |
|---|---|---|---|---|
| Journal `check_events` (opened, input, completed, interrupted) | the controller process, before and after each resolution | No (same process, same store) | No | A write-ahead record. It can show an evaluation never completed. It cannot show a decision was not omitted. Not a receipt. |
| `resolution_checks` | the controller | No | No | Same. Replay binds journal to checks by content, which shows the two controller-written records agree. |
| Destination ledger rows (`effects`, `attempts`, `attempt_events`); CP test destination `effects` and `grant_effect_counts` | the destination adapter, in its own sqlite file (runtime) or JSON file (CP test destination) | Separate code and store, same deployment trust | No sequence, no chain, no signature | The only effect-side record. It supports V4: every effect row maps to an authorized decision with a matching operation digest; no `effect_id` appears twice (the table keys `effect_id` as primary key, so duplicates show as refused or deduped, not as two rows). |
| BitRep link attestations (Index) | external issuers | Yes, for links | Signed | Not about decisions. |
| Replay HMAC | whoever holds the shared secret | No | HMAC | Export integrity only. |

Ledger row member `operation_digest` (ODES decision 25-A). The runtime's destination observation carries `operation_digest` inside `destination_state`; the verifier's ledger row (`effect_id`, `grant_id`, `target`, `amount`, `unit`, `payload`, `state`) is closed and has no place for it, so a row that keeps it is refused at `ledger_shape` (programme-2 gap report, F-1). Decision: the ledger row gains `operation_digest` as an optional string member, the same type as the member of that name in `destination_state` and in the execution-attempt-lifecycle contract. A row without it stays valid and a default record is byte-identical. If a row and the matching accepted observation's `destination_state` both carry it they must be equal; the verifier may enforce this inside `v4.ledger.observations-agree`. No ODES contract defines this ledger row today (the shape lives only in the verifier's `ledger.py` and `docs/tiers.md`; the journal contract treats `destination_state` as an opaque object), so there is no schema, validator or fixture to change here and no ODES rule is added. The verifier owner changes the shape; the contract home for the row is `contracts/destination-ledger/` (decision 26).

There is therefore **no monitor** in the ActiveEvidence sense (a separately implemented component that emits a receipt for each decision it saw). This design does not invent one. It defines what the V1 verifier treats as the receipt source (the destination ledger), what that supports (completeness in both directions between ledger effects and authorized decisions and attempts), and what it cannot support (a dropped tail of the ledger, a forged ledger, an omitted decision that never reached the ledger). Monitor-signed receipts with a sequence number and previous-row digest (stage S4b, owner runtime) are what would turn P2 from "ledger agrees with record" into a claim about completeness. They are deferred behind the runtime stream (N1 identity join, N3 delayed-commit destination), which are outside this stream. Revision 2026-10-18: an outside-held witness of ledger counts and chain heads now exists (tier V3). It gives P2 a bounded additional check, not the monitor: see section 4.3, family H, for what it detects and section 5 for what it cannot prove.

### 3.5 Placement

```
                         pinned controller (CP bounded.py)         destination (runtime ledger)
                                   |  decide / execute / reconcile            |  effects, attempts, events
                                   v                                          v
                         BoundedRunRecord (JSON)  + proposal export     ledger export
                                   \                    |                    /
                                    \                   |                   /
                                     v                  v                  v
                      +------------------------------------------------------------+
                      |  INDEPENDENT VERIFIER (own repo, stdlib only)              |
                      |  own strict parser -> own canonicalization -> V1..V4       |
                      |  imports no controller, Replay, Pack, ODES or Index object |
                      |  emits: verification report (input digest, verdicts)       |
                      +-------------------------------+----------------------------+
                                                      | report digest
                       FROZEN HERE -------------------+-----------------------------
                                                      v
        Replay importer -> Evidence Pack -> qualification harness (outcome labels, scenario
        expected outcomes, hard gate counters)  <- joins labels only against a frozen report digest
```

- The verifier reads the same bytes Replay would read. It does not sit inside Replay or the Pack: they are consumers that already import the controller's profile constants and each other (the Pack imports the pinned Replay validator), and they attach outcome summaries (`destination_observed`, authorization counts). It runs before those summaries and before the harness joins expected outcomes.
- "Before labels are joined" is made checkable, not assumed: the report carries a digest of its exact inputs (own canonicalization) and the qualification harness, behind an opt-in flag, refuses to join outcome labels to a trace whose report digest is absent or differs (stage S6, mutation category L1).
- It does not replace the ODES validators. They remain the contract's reference. The verifier is a second implementation of the same rules written from the contract text, and the two are differentially tested on the ODES fixtures (stage S2). Disagreements are findings, either way.

### 3.6 Independence requirements (acceptance-testable)

1. No import of `agent_control_plane`, `agent_replay_bundle`, `agent_governance_evidence_pack`, `odes`, `engine` (runtime), or any Index module. An AST test over the verifier source fails on any such import, direct or via `importlib`.
2. Standard library only at runtime (no Pydantic, no `jsonschema`): the controller's models and a shared schema library are the common-mode failure being avoided.
3. Own strict parser: duplicate members, non-JSON constants, lone surrogates, trailing data, byte-order mark, nesting beyond a stated depth, and numbers outside a stated range are refused with `wire_*` codes before any model is built.
4. Own canonicalization implementing the pinned profile name (`json-sort-keys-compact-utf8-no-nan-python-semantics-v0.1`), proven byte-equal on the vectors in the Control Plane `conformance/decision-input-commitment-vectors.json` and on a verifier-owned vector set that includes non-ASCII text and float forms (`1`, `1.0`, `1e2`). Float and integer forms that Python serializes differently are inputs the verifier reports, not normalizes.
5. Verdicts are three-valued: `reject`, `accept`, `abstain` (the input lacks what a tier needs). A verifier crash is `error` and is never counted as detection.

## 4. Mutation suite with explicit denominators (question 3)

### 4.1 Two meanings of "mutation", kept apart

| Family | What is mutated | Unit under test | Existing | Denominator unit |
|---|---|---|---|---|
| S (source, control removal) | production source in a disposable copy | the project's tests | CP `tools/adversarial_mutations.py` (3 cases: delegation, independence, unknown-context; run in CP `tests.yml`); hub `tools/destination_admission_mutations.py` 13, `federated_governance_mutations.py` 8, `integrated_assurance_mutations.py` 9, `operational_state_mutations.py` 7, `research_assurance_mutations.py` 4 (41 total); hub `tests/test_preview_negative_controls.py` (7: missing local file, invalid anchor, repository escape, operational HOLD note, C0, C1, C2/C3 disclaimers; checker-mutant evades fixture) | The existing gates stay exactly as they are | control-removal cases |
| T (trace, C6) | an exported trace (record, proposal, ledger) | the independent verifier | none; the ODES invalid fixtures are the nearest seed | trace mutants |

Family S answers "do our tests notice a missing control". Family T answers "does the verifier notice a damaged record". The seven preview negative controls mutate a documentation link checker; they are family S and are not a seed for T. The family-S counts above are reported in the C6 report as context only, with their own denominators (cases), never merged into family-T rates.

The lifecycle contract's own negative controls (`tests/test_contract_lifecycle_conformance.py` in the Control Plane: dropped start record, `reconciled_existing: false` on a start row, sequential reorder) are the closest existing trace mutations: they plant a defect in a document built from a real run and require the vendored validator to refuse it with a named code. They are family T seeds.

### 4.2 Seeds, and why they cannot be the measurement

ODES journal contract: 67 invalid fixtures over 58 distinct codes, 13 valid. Lifecycle: 31 invalid over 22 codes, 20 valid. The union is 71 distinct codes (9 shared, because the journal contract delegates). All fixtures are synthetic and hand-built, and the valid ones are marked `synthetic: true`.

These are **regression seeds**, not a detection measurement: each invalid fixture was written for a rule the validator already implements, so a validator that passes its own fixtures says only that it has not regressed. The report therefore keeps two corpora apart:

- **seed corpus**: the ODES fixtures (and, for family H, the `witness-digest` and `holder-inventory` fixtures), reported as "k of n seeds refused with the intended code", labelled regression;
- **generated corpus**: mutants produced by operators (4.3) from real synthetic runs (the Control Plane test helpers already produce them; the lifecycle conformance suite maps ten real runs). These are held out from the verifier's development, with the operator set and random seed fixed in the repository before the verifier is run against them.

### 4.3 Catalogue

Each category names the operator, the seed where one exists, and the expected verifier tier. "Benign" operators must be accepted and form their own control family.

| Cat | Operator | Seed | Tier |
|---|---|---|---|
| W1 | duplicate a decision member in raw text (`result`, `effect_id`, `binding`) | none (Python parser accepts) | V1 |
| W2 | non-JSON constant (`NaN`, `Infinity`) in a numeric member | none | V1 |
| W3 | number-form drift: `1` vs `1.0` for `amount`, `strength`, `max_age_seconds` (an integer where a float was changes the canonical bytes; spellings of the same float do not, those are B) | none | V1/V2 |
| W4 | Unicode: NFC vs NFD, escaped vs literal non-ASCII, lone surrogate | none | V1/V2 |
| W5 | byte-order mark, trailing data, excessive nesting | none | V1 |
| B (benign) | key reorder, insignificant whitespace, equal-value escape forms that the pinned profile defines equal, float spellings of one float (`50.0`, `50.00`, `5e1`, `50.0e0` have one canonical form), a resolution-check id renamed (see J2) | none | accept |
| S1 | undeclared member outside `extensions` | `undeclared_member` fixtures | V1 |
| S2 | enum value outside closed set (`deny`, `safe_to_retry`) | `unknown_enum_value`, `deny-decision-result`, `safe-to-retry-result` | V1 |
| S3 | required member removed | `required-collection-missing` | V1 |
| S4 | extension key without `x-` | `extension-key-without-x-prefix` | V1 |
| I1 | `effect_id` substituted | `effect-identity-substituted` | V2 |
| I2 | proposal swapped or edited, binding unchanged | none | V2 |
| I3 | horizon commits to another proposal | `horizon-commits-to-another-proposal` | V2 |
| I4 | `record_commitment` of an input altered, or claimed on a missing input | `missing-input-claims-commitment` | V2 |
| I5 | payload or manifest digest altered | none | V2 |
| D1 | `result` flipped to `authorized` while reasons non-empty | `authorized-decision-with-reasons` | V2 |
| D2 | authorized with binding stripped, or hold with binding | `held-decision-with-binding` | V2 |
| D3 | an input whose `observed` contradicts its `expected` under an authorized result | none | V2 where operands are declared |
| D4 | reason code outside the registry, or vocabulary version removed | `journal-mode-decision-without-vocabulary-version` | V2 |
| D5 | `grant_revoked` observed in the grant input, result `authorized` | none | V2 (the one recomputable code) |
| J1 | journal opening dropped or duplicated | `delegated-duplicate-journal-opening` | V2 |
| J2 | completed check matches no resolution check by content (stage, inputs, reasons; renaming only a check id is not this, those ids are separate producer ids and that change is B); check reused; sequential order reversed | `delegated-completed-journal-matches-no-check`, `...-checks-reuse-one-resolution-check`, `delegated-sequential-checks-reordered` | V2 |
| J3 | `interrupted` or opened-only check rewritten as `completed` | none | V2 |
| T1 | naive timestamps; observation from the future; stale accepted observation; time floor regressed | `naive-decided-at`, `accepted-observation-from-the-future`, `accepted-observation-stale`, `input-time-floor-without-offset` | V2 |
| A1 | attempt start record dropped; second attempt after observed absence; attempt on a held decision | `delegated-dropped-start-record`, `second-attempt-lifecycle-for-effect`, `attempt-on-held-decision` | V2 |
| A2 | uncertain attempt without closeout; closeout without accepted observation | `uncertain-attempt-without-closeout`, `closeout-names-no-accepted-observation` | V2 |
| R1 | ledger effect with no decision (injected unauthorized effect) | none | V4 |
| R2 | ledger effect whose decision is `hold` | none | V4 |
| R3 | ledger row differing from the binding in grant, target, amount, unit or operation digest | none | V4 |
| R4 | second ledger row for one `effect_id` (excess duplicate), or a duplicate attempt acknowledgement | none | V4 |
| R5 | acknowledged attempt with no ledger row (dropped receipt); also a row dropped for an `unknown` attempt whose accepted `applied` or `partial` observation the record holds | none | V4 |
| R6 | ledger row dropped that nothing in the record corroborates (an `unknown` attempt and no accepted `applied` or `partial` observation of the effect; the tail of the ledger, since there is no sequence) | none | not detectable without sequence and chain (S4b) or an outside-held witness; expected `accept`, reported as such, and R6 keeps this definition. Revised 2026-10-18, see below: a dropped row that the record does corroborate is an R5 case, not R6; the same drop in a trace that comes with a witness is still not detected (correction 2026-10-18, decision 30-A: the current witness profile covers the run record's lists, not the destination snapshot) |
| X1 | decision, proposal or ledger row transplanted from another run | none | V2/V4 |
| L1 | outcome label or report digest altered after the freeze | none | S6 join step |
| F (forgery bound) | mutate, then recompute every affected commitment so the document is self-consistent; in a witnessed population this includes rewriting the record and the witness together so that they agree | none | expected `accept`; defines the certificate's limit |
| Q (semantic) | policy weakened with consistent digests; misleading but valid reason | none | not applicable (P3); listed so the report shows "n/a", not a rate |
| H1 | witness chain break: a witness record's `previous_digest`, `sequence` or `digest` altered, a record removed from or inserted into the witness chain | `witness-digest` `previous-digest-does-not-link`, `digest-does-not-recompute` | V3, `reject` (`witness_chain_invalid`) |
| H2 | witness run-id mismatch: the witness covers another run than the record | none (run-id mismatch is a record rule, not a file rule) | V3, `reject` (`witness_run_mismatch`) |
| H3 | witness version or shape damage: unsupported `version`, undeclared or missing member, wrong type, malformed `ledgers` entry | `witness-digest` `ledger-entry-extra-member`, `ledgers-not-an-object` | V3, `reject` (`witness_version_unsupported`, `witness_record_shape`) |
| H4 | ledger shrink against a witness: rows removed from a witnessed run-record list so the count falls below the witnessed count. The destination snapshot (`destination.json`) is not a witnessed list, so a destination-row drop is not H4 (see R6 and non-claim 4) | `witness-digest` `covered-row-dropped`, `ledger-count-decreases` | V3, `reject` (`witness_ledger_shrunk`) |
| H5 | ledger rewrite or reorder against a witness: a witnessed row changed or two swapped, count unchanged, chain head different | `witness-digest` `covered-row-replaced`, `covered-row-rewritten`, `covered-rows-reordered` | V3, `reject` (`witness_ledger_head_mismatch`) |
| H6 | holder-inventory damage: closed-shape damage, or a record naming an inventory the supplied document is not | `holder-inventory` `kind-expired`, `holders-member-missing`, `version-is-another-profile` | V3, `reject` (`holder_inventory_shape`) |
| H7 | rows appended after the latest witness digest (control) | none | V3, expected `abstain`: `could_not_check` (`input_absent`); never `confirmed` |
| H8 | witness holding no digest (control); an absent witness file at an explicit path is an input-error control, not H8 (decision 30-A) | `witness-digest` `empty-witness-file` | V3, expected `abstain`: no V3 confirmation (`could_not_check`, `witness_holds_no_digest`; a run given no witness argument runs no V3) |

Categories F, R6, Q, H7 and H8 are in the catalogue on purpose. They are the cases where an accepted trace (for H7 and H8, an unconfirmed one) is expected, and printing them keeps the aggregate from implying a coverage the design does not have.

**Revision of 2026-10-18 (programme 2, stream V3b; written after the first mutation run and the verifier follow-up were read, so it is post-hoc).** Three catalogue entries were wrong about what is damage and what is expected, and are corrected here. Each is reversible: restoring the old text restores the old expectation, and nothing else in the design depends on it.

- R6. The design said "ledger tail truncated: expected `accept`". The first run dropped the ledger row of an effect whose acknowledgement was lost and refused it, and the refusal is correct: in every such trace the record also held an accepted `applied` observation of the effect, so the record itself says the row exists and the snapshot contradicts it (`observation_without_ledger_row`, with `acknowledged_attempt_without_ledger_row` for acknowledged attempts). That case is a dropped receipt, R5. The case that stays undetectable is a row nothing in the record corroborates: an `unknown` attempt and no accepted `applied` or `partial` observation, where the ledger has no sequence or chain from which the drop could be seen. R6 now means only that case, and its expected verdict is `accept`. The first corpus had no trace of that shape (the control plane observes right after dispatch), so one was captured from the control plane's own path with the follow-up observation failing (`observation_unavailable`). Measured on that single trace the verifier accepted the drop (n_eff 1; an anecdote, not a rate).
- W3. Only an integer written where a float was changes the canonical bytes. `50.00`, `5e1` and `50.0e0` are one float with one canonical text under the pinned profile (Python `repr`), so they are value-equal forms and belong to B. A stricter reading of lexical forms would be a different profile, not a check.
- J2. "Completed check matches no resolution check" cannot be produced by renaming one resolution-check id: the contract treats resolution-check ids and journal-check ids as separate producer ids and a completed check binds by stage, inputs and reasons. Renaming an id leaves the record consistent by content (B); an operator for this category has to change inputs or reasons.

Results and the change log are in `suites/verifier-mutation/README.md` of `cogno-us/cognous-stack-qualification`.

**Revision of 2026-10-18, family H (design revision after the first measurement; post-hoc; decision 28).** The first catalogue (36 categories, 81 operators in qualification catalogue v2) deliberately had no witness damage: no design category covered it, so adding operators for it would have measured something the design had not stated. The owner agreed to bring witness-file damage into the measured design now that the verifier has tier V3. The new family is H (damage to the outside-**H**eld witness and holder-inventory artifacts), categories H1 to H8 in the table above, in the existing letter-and-number scheme and with the same fields (operator, seed, tier, expected verdict). Consequences, each reversible by deleting the family:

- Family H is measured only on a witnessed population: traces that come with a witness file (and, for H6, an inventory). Its rows, and the `B` and `F` controls measured on the same traces, form their own corpus with their own witnessed clean corpus (`false_rejection` of the V3 checks on unmutated witnessed traces). The denominators of a witnessed population are never pooled with those of the unwitnessed corpora (section 4.4); the report contract refuses a report that mixes them (`witnessed_corpus_mixed`, `witnessed_clean_corpus_missing`).
- Expected outcomes are `reject` for H1 to H6, and `abstain` for the controls H7 (rows appended after the latest digest are not covered: `could_not_check`, `input_absent`) and H8 (witness holding no digest; an absent witness file at an explicit path is an input error, decision 30-A). A confirmation of H7 or H8 is a false acceptance; a rejection is a false rejection.
- R5 and R6 keep their definitions. R6 (a destination row dropped that nothing in the record corroborates) is undetectable and expected `accept`, with or without a witness. Correction (decision 30-A): this section first said that with a witness the same drop is H4. Qualification run 4 showed a witnessed trace accepting it (1/1), because the `witness-digest/0.1` profile digests only the lists of the run record, not `destination.json`. The current witness profile does not cover the destination snapshot, so V3 does not detect an uncorroborated destination-row drop; it is a known limit and a candidate for a future witness-profile revision (a new profile version, not made here). R5 is the dropped row the record corroborates and does not need a witness.
- What a witness cannot prove stays in the non-claims (section 5, item 11): not that it was published, not that it was timely, not that it was independently held, not who published it (the record has no signer or proof member). A record and a witness rewritten together so that they agree are accepted; that is F, not a gap in family H.
- Nothing already measured is re-read. Catalogue v2 and its first run did not include family H and say nothing about it. Operators, the witnessed clean corpus and a catalogue v3 are later qualification work and are labelled post-hoc when written (stage S5b).

### 4.4 Metrics and denominators

For each category c, over a stated corpus (seed or generated, never pooled):

- `n_gen(c)`: mutants the operator produced. `n_noop(c)`: mutants byte-equal to the clean trace after canonicalization (excluded). `n_na(c)`: mutants whose precondition was not met (excluded, counted). `n_eff(c) = n_gen - n_noop - n_na`.
- Verdict counts over `n_eff(c)`: `n_reject`, `n_accept`, `n_abstain`, `n_error`. The report validator refuses a report where they do not sum to `n_eff`.
- **Detection**: `n_reject / n_eff`. Two figures: with any code, and with the intended code (localized).
- **False acceptance**: `n_accept / n_eff`. It is not `1 - detection`: abstain and error are reported on their own line and a verifier that abstains is not credited with detection.
- **Metric impact**: conditioned on false acceptance. For each accepted mutant, recompute the downstream measures from the mutated trace with the verifier's own derivation (hard-gate counters `unauthorized_effects` and `excess_duplicate_effects`, authorized/held counts, per-scenario outcome) and report `n_accept_with_change / n_accept` plus the signed deltas. Denominator is `n_accept(c)`. When `n_accept = 0` the field reads `n/a (0 accepted)`, never `0%`.
- **Clean-trace false rejection**: `n_clean_reject / n_clean_applicable(c)`, where the clean traces are unmutated traces on which category c's checks are active. Reported per clean corpus (generated real-run traces; ODES valid fixtures; for family H, a witnessed generated corpus and the witness fixtures), never pooled: a witnessed clean corpus is not the unwitnessed clean corpus with a witness added, and its figures are not averaged into it. Benign operators (B) are counted here as well: a rejected benign mutant is a false rejection.
- Every figure is printed as `k/n`. No composite score, no cross-category average, no interval on a denominator below 30 (counts only below that).
- Per scenario (C13): where a trace comes from a named scenario, the same table is emitted per scenario id. Per principal is emitted only where a principal was recorded (the existing `unrecorded` convention in `tools/scenario_report.py`).

### 4.5 Report-only, and the gates that stay

The mutation report never gates anything. The two existing hard gates are untouched: the D5 gate in the qualification scenarios (zero unauthorized effects, zero excess duplicate effects per trial) and the Control Plane `tools/adversarial_mutations.py` step in `tests.yml`. The report is produced by a workflow that is not a required check and cannot change a scenario verdict, a profile or a pin. If the owner later wants any category to gate, that is a separate decision recorded in the failure register, with the denominator the report shows at that time.

## 5. Explicit non-claims (question 4)

Candidate scope statement for a verification report (the C4 text, adapted: it is about the verifier's report, not an Index attestation, which does not exist for decisions). Proposed only; not applied anywhere (default 13):

> This report states that the supplied records, parsed by this verifier's own parser and canonicalized by its own implementation of pinned profile P, satisfy checks X1..Xn, and that the supplied destination ledger rows correspond to the authorized decisions in the record, each row to one decision and each acknowledged attempt to one row. The result is relative to the pinned controller revision C, the pinned contract drafts D and the pinned reason registry R named in this report. It does not state that the decision is correct, that the policy was adequate, that the grant was lawfully issued, that the destination ledger is complete or unforged, that an effect occurred in the world, or that any record was not omitted before export. It does not certify semantic quality.

Non-claims, enumerated:

1. **No imported headline numbers.** None of the papers' figures (attack success, agreement, mutation detection, resolver accuracy) is used as a target, benchmark, baseline or expectation. Those results come from their own benchmarks, simulated executors, small test sets and self-defined checkers (addendum section 5). The only numbers this programme reports are counts from its own corpora with denominators.
2. **The certificate is relative to the pinned controller.** A passing report does not mean the controller is correct, only that records are consistent with the pinned contract and recomputed identities. A change of the controller revision, the contract drafts or the registry invalidates the report's scope; it is not carried over.
3. **P3 is not certified.** No semantic quality claim, no claim that a policy is adequate.
4. **P2 is bounded by the receipt source.** Destination ledger rows are executor-written and carry no sequence, chain or signature. Without a witness the report cannot show that a ledger tail was not dropped (R6), that the ledger was not rewritten consistently, or that a decision never recorded did not happen. With a witness (tier V3) it can show that the run record's witnessed lists match the witness's counts and chain heads for the rows the witness covers (H4, H5); it cannot show it for the destination snapshot, which the current witness profile does not cover (an uncorroborated destination-row drop stays R6, undetected); it cannot show anything about rows appended after the latest witness digest (H7).
5. **Self-consistent forgery is not detected** (category F). Anyone who can rewrite records and recompute every commitment produces a trace the verifier accepts. Only an external anchor (not present: D07 records "no external anchor exists") would change that. A witness is not that anchor unless it was published and held outside the record keeper's control: a record and a witness rewritten together to agree are accepted.
6. **Not an attestation, not an Index signature, not an authorization.** The verifier does not issue BitRep attestations, does not touch the Index, and its report grants and denies nothing. A passing report is never an input to a grant or a decision.
7. **Parse strictness is a refusal rule, not a repair.** An input that the verifier rejects at the wire level is reported as rejected; the verifier does not normalize it and re-run.
8. **No claim about V1 scope.** Nothing here changes the D15 narrowing, the failure register, or any qualified row. The mutation report is a post-V1 measurement.
9. **Seeds are regression, not detection.** Detection figures come only from the generated, held-out corpus.
10. **Differential agreement is not equivalence.** Agreement between verifier and controller on a synthetic corpus does not establish that they agree elsewhere.
11. **A witness that matches is not a publication.** A V3 check that confirms shows that the witness file matches the records it was given. It does not show that the witness was published, that it was published in time, that any party independent of the record keeper held it, or who published it (the record has no signer or proof member); a witness supplied by whoever supplied the records vouches for nothing that party could rewrite. Rows appended after the latest witness digest are `could_not_check`, never `confirmed`. Only list-valued ledgers are covered. The report states this as the non-claim `witness_is_not_publication`.

## 6. Failure modes of this design

- R1. The verifier and the ODES validators are written by the same team from the same contract text. Common-mode misreading of a rule is possible. Mitigation: differential run on every fixture (S2), disagreements recorded as findings.
- R2. Strict parsing will reject inputs the current consumers accept (any record with a duplicate member or `NaN`). That is intended, and it will surface as a clean-trace false rejection if the controller's own store can emit such text. S2 measures it on real runs before anything depends on it.
- R3. The proposal commitment couples to the Pydantic model dump (3.2). The verifier input spec requires a proposal export that is that dump; a model change breaks recomputation by design, and the conformance vectors catch it.
- R4. `ObservationPolicy`, tolerance and the controller's single evaluation `now` mean time checks use values the record states. The verifier checks internal consistency of stated times, not that the clock was right (journal timestamps reuse the one evaluation `now`).
- R5. A report-only suite invites being read as a score. Mitigation: no composite figure, `n/a` rendering, F/R6/Q printed, section 5 wording embedded in every report.

## 7. Staged build plan (question 5)

Ownership defaults: spec and fixtures in ODES; verifier in a new repository (built as `cogno-us/cognous-open-control-stack-verifier`, command `cognous-verify`; the design's working name was `cogno-us/cognous-decision-verifier`; default 2); corpus, operators and report in the qualification repository; ledger sequence and chain, if ever, in the execution runtime; nothing in the Control Plane, Replay, Pack or Index except the deferred S7. Any stage that does change a component carries the pin-bump rule of the brief: suite first, then component PR, bump listed for the coordinator.

| Stage | Content | Owner repo | Acceptance tests | Depends on |
|---|---|---|---|---|
| S0 | this design | ODES | PR merged, CI green | none |
| S1 | ODES draft contract `verification-report/0.1.0-draft`: report members (input digest, verifier id and version, pinned controller revision, contract versions, registry digest, per-check verdicts, per-category mutation tables as an optional member), closed members, `x-` extensions, a mandatory `non_claims` member | ODES | standard contract tests: valid and invalid fixtures; a report asserting `semantic_quality: certified`, a verdict summing wrongly, a rate without `k/n`, a missing pinned revision, or an `attestation` member is refused with stable codes | S0 |
| S2 | verifier core, tiers V1 and V2 (strict parser, own canonicalization, rules written from the journal and lifecycle contract text) | verifier repo | (a) AST import-ban test passes; (b) stdlib-only install in a clean venv; (c) on all ODES fixtures of the two contracts the verifier's refusal code equals the validator's for every invalid fixture and accepts every valid one, or the difference is a recorded finding; (d) all Control Plane decision-input commitment vectors (`conformance/decision-input-commitment-vectors.json`) reproduce byte-for-byte; (e) W1 to W5 refuse with `wire_*` codes; (f) benign operator B accepted | S1 |
| S3 | tier V2 identity recomputation over real synthetic runs: proposal export spec, `effect_id`, horizon, payload, manifest | verifier repo | recomputed identities equal the records on the ten lifecycle-conformance runs and on a generated set; I1 to I5 and D1 to D5 refused; the one recomputable code (`grant_revoked`) re-derived | S2 |
| S4 | tier V4: destination ledger input spec; ledger vs decisions and attempts, both directions; recomputed `unauthorized_effects` and `excess_duplicate_effects` | verifier repo | recomputed counters equal the harness's counters on the D5 gate trials' real runs; R1 to R5 refused; R6 reported as `accept` with its note (a drop nothing in the record corroborates; with a witness it is still accepted, because the witness does not cover the destination snapshot, decision 30-A) | S3 |
| S4b (optional, deferred) | ledger `seq` and `prev_digest` columns, export of them | runtime | out of this programme's order (needs N1, N3); an R6 mutant becomes detectable | N1, N3 |
| S4c (built, added 2026-10-18) | tier V3: witness re-derivation and holder-inventory shape (`--witness`, `--holder-inventory`); ODES drafts `witness-digest`, `holder-inventory`; `verification-report` admits V3 (decision 27). Later fixes: V3 moved into `checks` (verifier #12); V3 runs on a raw record that lost decisions or attempts when a witness is supplied (verifier #16, closes the open point of decision 30-B) | verifier repo, ODES | verifier PR #10 merged; ODES decision 27; five captured V3 reports validate; a record with a covered row removed is refused with `witness_ledger_shrunk` | S4 |
| S5 (built: qualification #103, catalogue v2 #104) | mutation operators, held-out generated corpus, report generator, differential run against the controller | qualification | report regenerates byte-identically from a fixed seed; per category `k/n` lines satisfy the sum identity; F, R6, Q present with their expected verdicts; clean-trace false rejection reported per corpus; the workflow is not a required check and a deliberately failing detection does not change any scenario verdict | S4 |
| S5b (added 2026-10-18; built post-hoc: qualification #109 catalogue v3, #110, #111) | family H: operators H1 to H8 over a witnessed generated corpus, a witnessed clean corpus separate from the unwitnessed clean corpora (denominators never pooled), catalogue v3 labelled post-hoc; the verifier's report builder emits the V3-in-`checks` shape and the harness reads `abstain` for H7 and for H8 with a witness holding no digest (an absent witness file at an explicit path is an input-error control, exit 2, decision 30-A) | qualification, verifier repo | the report validates against `verification-report` with family H rows (decision 28: `witnessed_corpus_mixed`, `witnessed_clean_corpus_missing`); H1 to H6 refused with the named `witness_*` and `holder_inventory_*` codes; H7 and the empty-witness H8 neither confirmed nor rejected; F and R6 keep their expected `accept`; catalogue v2 results are not re-labelled | S5, S4c |
| S4d (built, added 2026-10-18) | profile sidecar semantics: `v2.profile.operation-identity`, `v2.profile.rule-revision`, `v2.profile.freshness` re-derived from the record alone (verifier #14, decision 29-B non-claim `profile_sidecar_semantics_only`); profile-on records accepted by the journal schema (verifier #13, decision 23); registry labels 0.1 and 0.2 resolved per row with `reason_label_mismatch` (verifier #15, #17, decision 31) | verifier repo | profile fixtures accepted by both validator and verifier except the one sidecar-only tamper; every default-path verdict unchanged | S4c |
| S6 | outcome-label join precondition: harness joins labels only against a frozen report digest (opt-in flag; default path unchanged) | qualification | L1 mutant (digest altered, or report absent) makes the join refuse; with the flag off nothing changes | S5 |
| S7 (deferred) | decision witness linked to `decision_id` (candidate: the Decision Input Commitment Record) for decision re-derivation (formerly named tier V3; that name now belongs to S4c) | Control Plane, then qualification | gated on an owner decision and the N-stream order | none now |

Pin bumps: S1 to S6 (including S4c and S5b) need none. S4b and S7 would, and are not scheduled.

## 8. Where the addendum and the code disagree

The code wins in each case.

| Addendum statement | Code |
|---|---|
| "mandatory Index attestation" (section 1) and "For Index attestation this gives a precise scope statement" (3.3) | The Index verifies externally issued BitRep link attestations (issuer signature only) and signs nothing; it has no path from Control Plane decisions. There is no decision attestation to scope. |
| C5: "separate parser and canonicalization" as something to build | Separate copies of canonicalization already exist in five components (3.2); they are copies of one recipe, and plain `json.load` is used outside the Pack and the Index. The gap is independence of implementation and strictness, not the absence of a second copy. |
| C6 "starting from existing mutation work" implied reuse | Existing mutations are control removals in code (family S). No trace mutation harness exists; the ODES fixtures are the nearest seed. |
| 3.3 "rebuilds the trace from receipts" | No receipts exist. The destination ledger is the only effect-side record, it is not chained, and the journal is controller-written. |
| "decision consistency with the pinned controller" as a verifiable property | Not verifiable from the retained record (3.3); 1 of 121 reason codes is recomputable. |
| Section 6 item 3 (open): "Is Index attestation produced by the same code path as the decisions it attests?" | Answered: no, there is no Index attestation of decisions. |

## 9. Decisions taken by default (all reversible; for end review)

1. Design only; no prototype, no code under `docs/engineering/prototypes/`. Every claim that needed a check was proven by a command recorded in Appendix B.
2. The verifier lives in a new repository (working name `cogno-us/cognous-decision-verifier`; built as `cogno-us/cognous-open-control-stack-verifier`). ODES holds the report contract and fixtures; the qualification repository holds corpus, operators and report. Alternative: a `verifier/` package inside ODES. Not chosen because ODES already hosts the reference validators and independence from them is part of the point.
3. Python, standard library only, implementing the existing pinned canonicalization profile byte-for-byte. No migration to RFC 8785 now; the profile's own text says it does not claim JCS or cross-language equivalence, and the report repeats it.
4. The parser rejects duplicate members, non-JSON constants, lone surrogates, trailing data, BOM and excessive depth, with stable `wire_*` codes. Rejection is the verdict; no repair.
5. Verdicts are `reject`, `accept`, `abstain`, `error`; only `reject` counts as detection.
6. A report's scope is the pinned controller revision, contract draft versions and registry digest it names; it is not transferable to other revisions.
7. V1 receipts are destination ledger rows. Journal events are records, not receipts. Monitor-signed, sequenced receipts are deferred (S4b).
8. Traces for the generated corpus come from the component test helpers on synthetic proposals (as the lifecycle conformance suite does). No qualification-controller run and no `tools/v1_validation.py` mode is used.
9. The mutation report is report-only, produced by a non-required workflow, with no composite score. The D5 hard gate and the Control Plane `adversarial_mutations.py` step are unchanged.
10. ODES fixtures are labelled regression seeds. Detection is reported only on the held-out generated corpus.
11. The word "attestation" is reserved for BitRep envelopes. The verifier's output is a "verification report".
12. Reports are unsigned (digest-pinned inputs only). Signing, if wanted, would be a separate issuer decision through BitRep and is not part of this design. The Index is not touched.
13. The scope-statement text in section 5 is proposed, not applied to any V1-closeout or README text; applying it belongs to the end-of-programme docs cleanup (owner's instruction).
14. "Frozen before labels" is enforced by a digest the harness checks, behind an opt-in flag; the default join path is unchanged.
15. No Index change, no Replay or Pack change, no Control Plane change in S1 to S6.
16. Decision re-derivation is deferred (revised 2026-10-18: this default originally called it tier V3; V3 is now the outside-held witness tier, built). The Decision Input Commitment Record is the candidate decision witness; it has no `decision_id` link and is not wired into the live workflow.
17. This document is not added to Appendix C (index) or section 12 (decision log) of `ODES-INTERCOMPONENT-CONTRACTS.md`; the cleanup pass decides.
18. (2026-10-18, decision 28.) Family H (H1 to H8) joins the closed catalogue; witnessed populations are measured and reported apart from unwitnessed ones, never pooled; H7 and H8 expect `abstain`; R5, R6 and F keep their definitions; what a witness cannot prove is a non-claim. Post-hoc: catalogue v2 and its first run are not re-read. Reversible: delete family H.

## 10. Not verified

- The Replay and Pack test suites were not run; their behaviour is from reading the source at the revisions above.
- Runtime ledger export (`producer_contract.py`) was read, not executed. That the ledger has no sequence number or chain is from the sqlite schema in `safe_executor.py` (`effects` keyed by `effect_id`; `attempts` and `attempt_events` carry `created_at`), not from a captured export.
- That the Control Plane store can never emit duplicate members or non-JSON constants was not tested; the claim made is only that no consumer outside the Pack and the Index would notice.
- Whether any real run record already violates a V2 rule (a clean-trace false rejection) is unknown until S2 runs.
- The ODES contracts for exchange, reversibility, deferral, delegation, lineage, reconciliation and source-family counting were not mapped into the catalogue. They add rules (and fixtures) for later categories; this design covers the journal and lifecycle contracts.

## Appendix A. Code read

- Control Plane: `src/agent_control_plane/bounded.py` (`decide`, `execute`, `_resolve_journal`, `_resolve_inputs` capture allow-list, `_effect_id`, `record_resolution_check`, `append_check_event`, `LocalRefundDestination`), `decision_input_profile.py`, `reason_vocabulary.py` (`derive_recomputability`), `schemas/runtime_authority_reasons_0_1.json` (121 codes: 120 `typed_only`, 1 `recomputable`), `tools/adversarial_mutations.py`, `tests/test_contract_lifecycle_conformance.py`, `conformance/decision-input-commitment-vectors.json`.
- Replay: `importers.py`, `refusal_evidence.py`, `reconstruction.py`, `signing.py`, `loader.py`.
- Evidence Pack: `importer.py`, `admission.py`.
- Index: `app/evidence/link_attestation.py`, `app/api/evidence.py`, `app/evidence/service.py`, `app/bitrep_verify/trust.py` (`strict_json`).
- Runtime: `engine/safe_executor.py` (`DurableRefundDestination`, `FrozenOperation.canonical_dict`), `engine/producer_contract.py`.
- ODES: `contracts/control-plane-journal/`, `contracts/execution-attempt-lifecycle/`, `contracts/index-evidence-registry/`, `docs/engineering/ODES-INTERCOMPONENT-CONTRACTS.md`.
- Qualification: `suites/v1-scenarios/_c_2b_helpers.py` (D5 gate), `tools/scenario_report.py`, `docs/v1-known-limits.md`.
- Hub: `tests/test_preview_negative_controls.py`, `tools/*_mutations.py`.

## Appendix B. Commands run for this document

| Command | Result |
|---|---|
| `PYTHONPATH=src python -m pytest -q tests` in ODES at `321bd404` | 880 passed |
| `python tools/adversarial_mutations.py` in the Control Plane at `87f02336` | `DETECTED: delegation`, `DETECTED: independence`, `DETECTED: unknown-context` |
| count of `expected_refusal` over `contracts/{control-plane-journal,execution-attempt-lifecycle}/fixtures/invalid` | journal 67 fixtures, 58 distinct codes; lifecycle 31 fixtures, 22 codes; union 71 distinct, 9 shared; valid 13 and 20 |
| `python -I` on the registry `schemas/runtime_authority_reasons_0_1.json` | 121 codes; `typed_only` 120; `recomputable` 1 (`grant_revoked`) |
| AST count of `CASES` in hub `tools/*_mutations.py` | 13, 8, 9, 7, 4 |
| `python -I -c 'json.loads(...)'` duplicate member and `NaN` | last duplicate wins; `NaN` accepted (3.2) |
| `grep` for `object_pairs_hook` / `parse_constant` across the five repos | present only in Pack `admission.py` and Index `trust.py` |

Nothing in this document was produced by running the qualification controller, `tools/v1_validation.py`, or any component outside a read-only clone and the two local runs above.
