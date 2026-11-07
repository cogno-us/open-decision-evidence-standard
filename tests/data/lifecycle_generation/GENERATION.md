LIFECYCLE GENERATION FIXTURES -- SYNTHETIC / NONPRODUCTION / UNQUALIFIED, non-authorizing, development only.

What / why
  A new strict-tenant (CP-2) Control Plane run plus proposal whose proposal carries explicit risk metadata
  BEFORE the Control Plane commits it, so the Control Plane's own proposal commitment, decision binding, evidence and
  approvals bind the risk metadata. Produced by the real pinned Control Plane; no commitment or JSON was edited afterwards.
  Purpose: input for a bounded ODES lifecycle scenario (opt-in, development-only). Not independent qualification.

Pins
  Control Plane (cp): 484fdbd297235dd24148ddb0703f2055a31eabff (clean checkout; test helpers blob-checked against HEAD)
  Replay (rb, verification only): 93a76e281fcae6a65d2cd1d35376f87442dafb95
  Manifest: tests/data/current_generation/manifest.json (sha256 789ad39596b9e1ef84a726a671883e1cb6b83343da3a31db0a1120906d68c074)
    == Control Plane tests.test_bounded_authorization.manifest() (asserted by the generator); manifest digest
    sha256:4d1ad6c96bc242c63998231b4df3ad7c86dc2e5e59cdae63afe7bff86e60f6ac (matches the proposal manifest_digest).
  Orchestrator c5d5c6759ffe26e287d22c4dbdd68404835015c3 reference helpers (read, not executed, not copied):
    tests/manual_contract/refund_producer.py sha256 da24b4aec5d01a35b6876a012963c895d45ad9e68442896ee460c255c59615b4
    tests/manual_contract/c2_producer.py     sha256 7c4f2595d7939e4a373586faafc0de86469dc03b791d893d7b27fb328a02a895
  Generator actually used: a strict-case variant of the Replay generate_from_cp.py flow (script_sha256 of the original
    recorded in tests/data/cp2_generation/PROVENANCE.json), driven by a supplied proposal, no frozen-commitment check:
    gen_lifecycle.py sha256 7a0f76b7431738a4c861d85cc64bde1a5ef9a3b0c990d2a169a0317408a91bec (kept outside every repo).
  Flow: baseline decide (discarded), signed synthetic evidence with the Control Plane's TEST-ONLY Ed25519 key, bind_approval,
    decide(now=2026-10-05T19:00Z virtual clock), then execute once against the CP's LocalRefundDestination scratch JSON
    (same as generate_from_cp.py; synthetic, no network, no payment). Result: authorized.

Proposal
  = tests/data/cp2_generation/strict_proposal.json (tenant-alpha; byte-identical to legacy_proposal.json) with ONLY
  risk_metadata replaced by:
    {"jurisdiction": "SYNTHETIC-JURISDICTION-NONPRODUCTION", "prohibited_use_flag": false, "restricted_use_flag": false,
     "risk_tier": "low", "synthetic_nonproduction": true}
  (original value was {}). Serialised in the same style as the original (json indent=1, sort_keys, trailing newline).
  Proposal commitment (CP-derived): sha256:f91ac0ca45863b5bacdc2514405bf359bc7c3ff19205f85463f0b2e663129a10
    (REFUND/original strict value: sha256:becaea3f...8c53)
  effect_id: sha256:3c4b70da002aa31d315b536492d7ae44fe68c3fa0465f624b8c6eb05ef8d49b2
  generation bounded-authorization-effect/0.3-strict-tenant, tenant_id tenant-alpha, grant urn:cognous:grant:routine-1.

Outputs (sha256)
  lifecycle_proposal.json           dbe041aff423fe8cd9eda07c680460cf5be8a621fe4c917d21a588ab63b96fc1
  lifecycle_control_plane_run.json  1b48b5499c469e2a70b3701c9712d3955010c48cc48e7478445d3f3810f257d6
  Run record has the same top-level key set and per-section counts as strict_control_plane_run.json.
  Random per-run values (attempt/decision/check UUIDs, pid, tokens) differ from any other run; a control run with the
  ORIGINAL proposal reproduced the original strict run except those random values and was byte-identical for the proposal.

Command (cp = pinned Control Plane checkout; run from the scratch gen dir, no bytecode)
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<cp>/src:<cp> python3 -I -B gen_lifecycle.py <cp> proposal_in.json \
     tests/data/current_generation/manifest.json tests/data/lifecycle_generation
  (proposal_in.json sha256 dbe041af..., identical to lifecycle_proposal.json)

Integrity statements
  - No commitment, digest, binding or CP record was hand-edited; the proposal was validated by the CP's TenantRuntimeProposal
    model and every commitment derived by the CP. The only input change is the risk_metadata value above.
  - Original REFUND-DEMO-01 fixtures and every existing file (cp2_generation/*, current_generation/*) were untouched.
  - Pinned clone working trees stayed clean. Scratch work dirs were outside every repo.
  - Replay verification (read-only, ODES_ALLOW_UNVERIFIED_REPLAY unset): import_bounded_workflow(run, proposal=proposal,
    moltbot_export=None, control_plane_revision=484fdbd2...) -> status reconstruction_partial (same as the original strict
    fixture), 37 records of types control_plane_attempt_transition, effect_observation, input_time_floors, reconciliation,
    resolution_check, resolution_check_event, runtime_decision, runtime_proposal; runtime_proposal data.risk_metadata equals
    the new value; runtime_decision binding.proposal_commitment equals the new commitment above.
  - These records are caller-asserted synthetic data, not evidence of real authority or present validity.

ITERATION 2 (supersedes the values above where they differ)
  Iteration 1 used risk_tier "synthetic-low", which the ODES record schema rejects (enum low|medium|high|critical|unknown); the
  first test run failed 10 tests for that reason (kept verbatim in the PR). Iteration 2 regenerated with the same real pinned Control
  Plane and generator, changing ONLY risk_tier to "low" (no hand edits; commitments CP-derived).
  lifecycle_proposal.json           02ddf4a3c305fb0db8dec1ba233473df9b88bb3ad076b005125b52b68bb29295
  lifecycle_control_plane_run.json  bb29adafd657a0855ed0e8fd69c6825888163103f23b59f8a302705d074f60f7
  effect_id sha256:e87734d3b0fef15eb90e3195b5c6eedeebb59e5e402d4cdda1a213b2d8730e32
  The iteration 1 proposal commitment and outputs listed above are superseded; risk_metadata.synthetic_nonproduction stays true.
