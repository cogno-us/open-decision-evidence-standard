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
| Moltbot Safe | Bounded execution envelope/evidence | `6b0ba1185bcd390f71df947dda349415e4105f5f` |
| Replay | Reconstructs retained producer records | `f12648313cedc2cf06145d397fa56cdea18cc800` |
| Governance Evidence Pack | Business-readable review evidence | `c699c1fb7c4f8057631c4e5909d11a721c2c958d` |

## Mapping table

| ODES `pder-v0.1` field | Source path | Transformation | Meaning | Loss / limitation |
|---|---|---|---|---|
| `decision_id` | `records[runtime_decision].data.decision_id` | String copy | Issuer-side decision identifier | None when present; otherwise export fails. |
| `decision_type` | `runtime_decision.data.result` | Normalize to `agent_action_authorized`, `agent_action_held`, or `agent_action_denied` | Governance disposition over a proposed agent action | More granular producer result vocabulary is retained in package provenance. |
| `decision_timestamp` | `runtime_decision.data.decided_at` | String copy | Time of authorization decision | If unavailable, exporter uses bundle generated time and records limitation. |
| `issuer.organization_id` | Export profile constant | `cognous.synthetic.baseline` | Synthetic baseline issuer namespace | Does not establish institutional adoption or production issuer identity. |
| `issuer.system_id` | Exporter identity | Constant | System producing the ODES export | Not a public authentication claim. |
| `authority.authority_basis` | `runtime_decision.data.binding.grant_id`, `runtime_proposal.data.authority_context_ref`, Manifest action requirements | Prefer grant, then authority profile reference | Authority coordinate represented by producer records | Ground truth of institutional authority is not proven. |
| `authority.authority_valid_at_decision` | `runtime_decision.data.result` plus binding presence | `true` for authorized with binding; `false` for held/denied | Record-level authority assertion | Does not verify historical authority outside retained producer records. |
| `machine_role` | Manifest + proposal + execution records | Constant role mapping with runtime profile | Captures agentic automation participation | Model identity/version are unavailable in pinned synthetic baseline and exported as unavailable. |
| `human_disposition` | Control Plane decision result and reasons | Held => escalated; denied => rejected; authorized => unknown unless human evidence exists | Human posture when actually evidenced | No human approval is manufactured. |
| `evidence.evidence_hash` | Manifest + Reconstruction Bundle | Canonical SHA-256 digest | Content binding for retained source artifacts | Hash binds content only; it is not issuer identity or independent review. |
| `policy_basis` | `binding.policy_versions`, requirement IDs, Manifest declarations | Convert to policy references | Rules/requirements referenced by decision | Full policy evaluation trace is not native to base schema. |
| `risk_coordinates` | Manifest/risk metadata when available | Conservative defaults | Risk and jurisdiction coordinates | Synthetic baseline does not establish production jurisdiction or risk severity. |
| `consumption_conditions` | Exporter configuration | Explicit recipient/purpose/expiry | Recipient policy boundary | Wrong recipient/purpose must fail recipient validation. |
| `status` | Bundle metadata/status inputs | Preserve freshness/revocation/supersession if supplied; otherwise current | Lifecycle state | Current does not mean independently verified present validity. |
| `verification` | Export profile metadata | `content-digest`, key reference explaining no public issuer auth, profile ID | Verification coordinates | No JWS, PKI, BitRep or Index dependency is implied. |

## Unsupported semantics carried outside the base record

`pder-v0.1` has no native fields for effect IDs, separate Control Plane and executor attempt namespaces, execution-result attempt references, destination effects, effect observations, acknowledgement source records, reconciliation records, restart recovery, partial delivery, Replay import findings, or redacted-derivative lineage. These remain in the export package `provenance` object and in this separately versioned profile.

## Component ownership boundary

ODES carries portable decision evidence. Manifest declares operations. The Control Plane resolves authorization. Moltbot Safe enforces the bounded execution path. Replay reconstructs evidence. Governance Evidence Pack presents review material. The recipient determines reliance.

This mapping does not implement GAX messaging, IMX continuity, a scheduler, a runtime gate, a constitutional engine, production key custody, authenticated institutional resolvers, or a replacement runtime.
