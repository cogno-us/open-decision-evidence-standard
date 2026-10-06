# Cognous Stack to ODES Field Mapping

Status: Informative mapping for the `odes_cognous_stack_export_0_1` implementation profile.

Starting baseline for this workstream: `7a0c0312037b78da6d995184507384393b51ee2b`.

## Version boundary

ODES narrative document version `0.2`, base schema version `pder-v0.1`, and implementation-profile version `odes-cognous-stack-export-0.1.0` are distinct. This mapping preserves the existing `pder-v0.1` schema.

## Source baselines

| Component | Role | Pinned revision |
|---|---|---|
| Manifest v1.1 | Declares operations and requirements | `46c950bed37fe3812000895430bc0312d29e37ce` |
| Authority Context 0.1.0 | Authority profile/context evidence | `fb3d97938969a89e149e8ff8db2756091d1233fc` |
| Control Plane | Resolves authorization and attempts | `283500652d47a692fb0b99a1172a6d5faffbd9a7` |
| Moltbot Safe | Bounded execution envelope/evidence | `054e92d12ccb0bc756ca6652f39fc13b51e05d9b` (producer profile 1.0.0; proposed dependency head) |
| Replay | Reconstructs retained producer records | `22aa742b2735b64b850c2c37688ef1fae5ff9014` (proposed dependency head) |
| Governance Evidence Pack | Business-readable review evidence | `c699c1fb7c4f8057631c4e5909d11a721c2c958d` |

## Mapping table

| ODES `pder-v0.1` field | Source path | Transformation | Meaning | Loss / limitation |
|---|---|---|---|---|
| `decision_id` | `records[runtime_decision].data.decision_id` | String copy, or deterministic decision hash when no ID is present | Issuer-side decision identifier | Hash fallback is an export identifier, not a producer-assigned business ID. |
| `decision_type` | `runtime_decision.data.result` | Normalize to `agent_action_authorized`, `agent_action_held`, or `agent_action_denied` | Governance disposition over a proposed agent action | More granular producer result vocabulary is retained in package provenance. |
| `decision_timestamp` | `runtime_decision.data.decided_at` | String copy only | Time of authorization decision | If unavailable, export fails. The exporter does not substitute bundle generation time or export time for an unknown decision time. |
| `issuer.organization_id` | Export profile constant | `cognous.synthetic.baseline` | Synthetic baseline issuer namespace | Does not establish institutional adoption or production issuer identity. |
| `issuer.system_id` | Exporter identity | Constant | System producing the ODES export | Not a public authentication claim. |
| `authority.authority_basis` | `runtime_decision.data.binding.grant_id`, `runtime_proposal.data.authority_context_ref`, Manifest action requirements | Prefer grant, then authority profile reference | Authority coordinate represented by producer records | Ground truth of institutional authority is not proven. Recipient authority verification requires explicit external status evidence. |
| `authority.authority_valid_at_decision` | `runtime_decision.data.result` plus binding presence | `true` for authorized with binding; `false` for held/denied | Record-level issuer assertion about authority | This is not recipient-verified historical authority and cannot pass recipient authority checks by itself. |
| `machine_role` | Decision result plus execution records | `execution` only when authorized execution evidence exists; `assistance` for authorized/no execution; `escalation` for held/denied | Captures machine participation without claiming execution from authorization alone | Model identity/version are unavailable in pinned synthetic baseline and exported as unavailable. |
| `human_disposition` | Explicit retained human review/disposition fields only | Copy supported disposition when evidenced; otherwise `unknown` | Human posture when actually evidenced | Machine hold/deny is not mapped to human escalation/rejection. No human approval or review is manufactured. |
| `evidence.evidence_hash` | Manifest + Reconstruction Bundle | Canonical SHA-256 digest | Content binding for retained source artifacts | Hash binds content only; it is not issuer identity, independent review, signing time, present validity or authority. |
| `policy_basis` | `binding.policy_versions`, requirement IDs, Manifest declarations | Convert to policy references | Rules/requirements referenced by decision | Full policy evaluation trace is not native to base schema. |
| `risk_coordinates` | Manifest/risk metadata when available | Conservative defaults | Risk and jurisdiction coordinates | Synthetic baseline does not establish production jurisdiction or risk severity. |
| `consumption_conditions` | Exporter configuration | Explicit recipient/purpose/expiry | Recipient policy boundary | Wrong recipient/purpose must fail recipient validation. Expiry requires a recipient evaluation time to evaluate. |
| `status` | Bundle metadata only | Preserve freshness/revocation/supersession only if supplied; otherwise `unknown` | Issuer-reported lifecycle state | The exporter does not default missing freshness to current. Revocation/supersession linkage is required when those states are claimed. Present validity must be evaluated from explicit recipient status inputs. |
| `verification` | Export profile metadata | `content-digest`, key reference explaining no public issuer auth, profile ID | Verification coordinates | No JWS, PKI, BitRep or Index dependency is implied. Content digest is integrity metadata, not authentication. |

## Package-level integrity and provenance

The base `pder-v0.1` schema cannot carry every Cognous Stack fact. The export package therefore carries additional informative material outside the base record under a separately versioned implementation profile.

- `integrity.value` binds the embedded ODES record and profile metadata.
- `package_digest` binds the material exported package content: record, profile, integrity metadata and provenance.
- `provenance.execution_facts` carries effects, attempts, acknowledgements and observations as distinct facts.
- `provenance.source_record_refs` carries source record references and per-record hashes.
- `provenance.redaction` carries original/derivative lineage when declared.
- `provenance.unsupported_semantics` and `provenance.limits` must survive export and recipient validation.

Recomputing hashes after altering the package can restore content self-consistency but does not authenticate an issuer or establish authority.

## Unsupported semantics carried outside the base record

`pder-v0.1` has no native fields for effect IDs, separate Control Plane and executor attempt namespaces, execution-result attempt references, destination effects, effect observations, acknowledgement source records, reconciliation records, restart recovery, partial delivery, Replay import findings, external status evidence, or redacted-derivative lineage. It also requires a `decision_timestamp`, so an unknown decision time cannot be represented without either failing export or changing the base schema. These semantics remain in the export package `provenance` object and in this separately versioned profile where evidenced.

## Component ownership boundary

ODES carries portable decision evidence. Manifest declares operations. The Control Plane resolves authorization. Moltbot Safe enforces the bounded execution path. Replay reconstructs evidence. Governance Evidence Pack presents review material. The recipient determines reliance.

This mapping does not implement GAX messaging, IMX continuity, a scheduler, a runtime gate, a constitutional engine, production key custody, authenticated institutional resolvers, or a replacement runtime.

## Executor producer migration

ODES consumes executor semantics through the Reconstruction Bundle and Replay validator. Versioned executor producer data must retain the `urn:cognous:profiles:moltbot-safe-executor-producer` profile at version `1.0.0`, including its source-asserted repository revision. Legacy unversioned executor records remain valid only through Replay's explicit revision-pinned legacy path; ODES does not relabel them.
