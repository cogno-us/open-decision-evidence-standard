# ODES Cognous Stack Export Profile 0.2

Status: informative implementation profile proposal; ODES remains draft.
Base record: unchanged `pder-v0.1`. Narrative document version: unchanged `0.2`.
Package envelope remains `0.1.0`.

Profile identifier: `odes_cognous_stack_export_0_2`.
Transformation version: `odes-cognous-stack-export-0.2.0`.

This explicit new profile changes the execution-summary contract and requires
retained original sources for recipient semantic checking. Consumers must opt in;
profile 0.1 remains the historical transformation and is not silently redefined.

## Compatibility

| Profile | Executor interface / revision | Control Plane revision | Replay decoder |
|---|---|---|---|
| 0.2 | Producer 2.0.0 / `177354e959cc78c59c1a776f018cfbfbf28c927b` | `2ea9528eeb87e14ff10f05de06473122b9df540f` | `274543f1cd7171784a923a8e37015017a0d8bc9d` |
| 0.1 | Producer 1.0.0 / `1d308faf664c504b6e310db3c7a310153ef7b067` | `283500652d47a692fb0b99a1172a6d5faffbd9a7` | Historical mapping at `f63ce914504dd06813c4ccd199b0570dbd8dd427` |
| 0.1 | Legacy unversioned / `6b0ba1185bcd390f71df947dda349415e4105f5f` | `283500652d47a692fb0b99a1172a6d5faffbd9a7` | Same historical Replay mapping |

Accepted Replay also implements the historical decoder paths; CI installs the
accepted runtime and tests both generations. Existing historical packages retain
original profile/pin coordinates. No source artifact is relabeled. Manifest
remains `46c950bed37fe3812000895430bc0312d29e37ce`.

The exporter reconstructs the public Replay importer inputs including explicit
Control Plane revision, compatibility metadata, nullable result observation,
Control Plane evidence, attributed attempts, rejected observations and complete
reconciliations. It invokes accepted Replay, rather than a local substitute.
For profile 0.2 it checks retained records, links, commitments, producer profiles,
status and effect-history metadata against the accepted reconstruction. Modified
owning records, dropped rejection evidence or promoted observation claims fail.

## Execution facts

`provenance.execution_facts` in 0.2 contains:

- `reconstruction_status`, independently of delivery or acknowledgement.
- Accepted Replay `effect_observation_history`, using exact effect identity and
  owning producer array order. Cross-sequence order remains not established and
  import-time freshness is not evaluated.
- `destination_observed`, the latest supported Control Plane observation state
  for the single effect, or unknown if unavailable. This is not derived from
  reconstruction completeness or a count of retained destination rows.
- Full acknowledgement/attempt lifecycle, actual execution results (including
  null observation), destination rows, accepted observations and reconciliations.
  Acknowledgement summary can be `mixed` when history includes both unknown and
  received acknowledgement; earlier unknown states are never rewritten.
- Current-result `rejected_observations` and `control_plane_evidence`; earlier
  rejected/unavailable observations remain in the full reconciliation history.
  Wrong effect IDs inside rejected content are not accepted lineage identifiers.
- Separate owning attempt namespaces and explicit Replay links. Strings alone
  never establish attempt equivalence; the Replay validator matches owner records.
- Historical-local-observation flag, `retry_permission=not_established`, and
  independent delivery verification unavailable. `observed_absent` remains a
  point-in-time fact with retry false, not permission to resubmit.

Complete reconstruction may describe unresolved or partial delivery. Lost
acknowledgement can coexist with an applied observation. Recovery can establish
applied state while keeping all earlier rejected evidence. No unrelated clocks
are merged to infer event ordering.

## Original source and recipient boundary

`provenance.retained_sources` includes the original Manifest and Replay JSON.
`source_artifacts` binds the original Replay bundle ID and canonical digest,
without replacing it with the reconstruction used for validation. Original import
reports and findings are retained separately from freshly computed findings.
The full material package digest includes these retained sources and summaries.

Recipient validation adds `replay_semantic_consistency` for profile 0.2: it invokes
the same exporter/accepted Replay validation on retained sources and compares the
entire material transformation. Even recomputed package hashes cannot promote
completeness into delivery success or bypass semantic contradictions. This check
is source-content consistency, not authentication of the supplied producer data.

All original recipient controls remain: explicit policy profile, recipient,
purpose, timezone-aware evaluation time, status maximum age, exact policy scope,
status identity/freshness and future/malformed/timezone-free timestamp rejection.
Digest validity does not authenticate an issuer or renew authority. Without
trusted external evidence, authentication and current authority remain unavailable.
Explicit synthetic status fixtures in tests are not independently verified facts.
Where all other policy checks pass, unauthenticated inspection is informational
only. Held/no-authority records cannot acquire authority through inspection.

Exporter and recipient validation read supplied JSON only, not producer stores;
qualification nevertheless checks actual SQLite and CP stores before and after
all operations. No effects, retries or authority decisions are created.
