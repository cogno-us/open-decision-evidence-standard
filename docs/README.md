# Documentation index

Pages in this repository, grouped by what a reader wants to do. Status labels: **merged**, **selected**, **known limit** and **proposed** (see the [README](../README.md#where-it-fits)). ODES is a single-maintainer draft; every contract is `0.1.0-draft`. Pages marked *historical* record a checkpoint and keep the status and scope of the work they recorded.

Back to the [README](../README.md) (what it is, quick start, what ships, known limits). Hub pages: [stack map](https://github.com/cogno-us/cognous-open-control-stack/blob/main/docs/stack-map.md), [naming](https://github.com/cogno-us/cognous-open-control-stack/blob/main/docs/naming.md), [profiles and tools](https://github.com/cogno-us/cognous-open-control-stack/blob/main/docs/profiles-and-tools.md).

## Reading paths

| If you are | Read, in order |
| --- | --- |
| New to ODES | [problem statement](problem-statement.md), [terminology](terminology.md), [design principles](design-principles.md), [README quick start](../README.md#quick-start) |
| A recipient or relying-party engineer | [recipient validation](recipient-validation.md), [selective disclosure](selective-disclosure.md), [detached authentication](detached-authentication.md), [native evidence inventory](native-evidence-inventory.md) |
| A producer or exporter engineer | [Cognous stack field mapping](cognous-stack-field-mapping.md), [profile 0.2](../profiles/cognous-stack-export-0.2.md), [merged producer compatibility](merged-producer-compatibility.md), [shared journal export](shared-journal-export.md) |
| A reviewer of claims and limits | [capabilities and versions](capabilities-and-versions.md), [threat model](threat-model.md), [related work](related-work.md), [known limits](../README.md#what-it-does-not-do-known-limits) |
| A contract or verifier implementer | [contract drafts](../README.md#contract-drafts-contracts), [verifier requirements](../conformance/verifier-requirements.md), [inter-component contracts](engineering/ODES-INTERCOMPONENT-CONTRACTS.md), [time semantics](engineering/ODES-TIME-SEMANTICS.md) |
| A maintainer | [CONTRIBUTING](../CONTRIBUTING.md), [GOVERNANCE](../GOVERNANCE.md), [cross-component tests](../CROSS_COMPONENT_TESTS.md) |

## Specification and orientation

| Page | What it covers | Label |
| --- | --- | --- |
| [problem-statement.md](problem-statement.md) | The problem ODES addresses. | merged |
| [terminology.md](terminology.md) | Terms used across the draft. | merged |
| [design-principles.md](design-principles.md) | Design principles. | merged |
| [threat-model.md](threat-model.md) | Preliminary threat model. | merged |
| [related-work.md](related-work.md) | Related and adjacent work; no adoption or interoperability claim. | merged |
| [public-messaging.md](public-messaging.md) | How to describe the draft, including what not to say. | merged |
| [selective-disclosure.md](selective-disclosure.md) | What selective disclosure does and does not permit. | merged |
| [capabilities-and-versions.md](capabilities-and-versions.md) | Capability layers and the version register (compared with code by a test). | merged |
| [../schema/pder-v0.1-fields.md](../schema/pder-v0.1-fields.md) | Field notes for the `pder-v0.1` schema. | selected |
| [../rfcs/0001-portable-decision-evidence-record.md](../rfcs/0001-portable-decision-evidence-record.md), [0002](../rfcs/0002-combined-specification-and-informative-evidence-review.md), [0003](../rfcs/0003-verifier-behavior-and-reliance-boundaries.md), [0004](../rfcs/0004-decision-evidence-lifecycle-semantics.md) | The four RFC drafts. | proposed |
| [../conformance/pder-v0.1-minimal.md](../conformance/pder-v0.1-minimal.md), [../conformance/verifier-requirements.md](../conformance/verifier-requirements.md) | Minimal conformance profile and verifier requirements. | proposed |

## Validation and profiles

| Page | What it covers | Label |
| --- | --- | --- |
| [recipient-validation.md](recipient-validation.md) | Validation layers, result values and precedence, integrity boundary, canonicalization profiles, input budgets, restriction semantics. | merged |
| [detached-authentication.md](detached-authentication.md) | Optional DSSE with Ed25519; authenticates origin only. | merged |
| [native-evidence-inventory.md](native-evidence-inventory.md) | Native evidence inventory: limits, byte-preserving entries, nothing fetched. | merged |
| [cognous-stack-field-mapping.md](cognous-stack-field-mapping.md) | Cognous stack to ODES field mapping (profile 0.1). | merged |
| [merged-producer-compatibility.md](merged-producer-compatibility.md) | Merged producer pair, profile `odes-cognous-stack-export-0.2.1`. | selected |
| [typed-refusal-profile.md](typed-refusal-profile.md) | Typed refusal candidate profile. | proposed |
| [shared-journal-export.md](shared-journal-export.md) | Export from a shared journal (exporter behaviour note). | merged |
| [reconstruction-bundle-version.md](reconstruction-bundle-version.md) | Reconstruction bundle version (exporter behaviour note). | merged |
| [retained-replay-comparison.md](retained-replay-comparison.md) | Retained Replay bundle comparison (exporter behaviour note). | merged |
| Profile documents | [minimal](../profiles/minimal.md), [agentic AI](../profiles/agentic-ai.md), [regulated enterprise](../profiles/regulated-enterprise.md), [Cognous export 0.1](../profiles/cognous-stack-export-0.1.md), [0.2](../profiles/cognous-stack-export-0.2.md), [0.2 restrictions](../profiles/cognous-stack-export-0.2-restrictions.md), [generic recipient 0.1](../profiles/generic-recipient-0.1.md) | see README |

## Contract drafts (proposed, `0.1.0-draft`)

Each contract README is the source of the copies other repositories vendor.

[authority-lineage](../contracts/authority-lineage/README.md) · [bounded-deferral](../contracts/bounded-deferral/README.md) · [control-plane-journal](../contracts/control-plane-journal/README.md) · [destination-ledger](../contracts/destination-ledger/README.md) · [effect-reversibility](../contracts/effect-reversibility/README.md) · [execution-attempt-lifecycle](../contracts/execution-attempt-lifecycle/README.md) · [freshness-clocks](../contracts/freshness-clocks/README.md) · [governed-exchange](../contracts/governed-exchange/README.md) · [holder-inventory](../contracts/holder-inventory/README.md) · [index-evidence-registry](../contracts/index-evidence-registry/README.md) · [non-broadening-delegation](../contracts/non-broadening-delegation/README.md) · [operation-identity](../contracts/operation-identity/README.md) · [rule-revision](../contracts/rule-revision/README.md) · [source-family-counting](../contracts/source-family-counting/README.md) · [two-party-reconciliation](../contracts/two-party-reconciliation/README.md) · [verification-report](../contracts/verification-report/README.md) · [witness-digest](../contracts/witness-digest/README.md)

## Engineering records (historical or draft)

| Page | Note |
| --- | --- |
| [engineering/ODES-INTERCOMPONENT-CONTRACTS.md](engineering/ODES-INTERCOMPONENT-CONTRACTS.md) | Inter-component contracts proposal and the decisions record. |
| [engineering/ODES-TIME-SEMANTICS.md](engineering/ODES-TIME-SEMANTICS.md), [engineering/ODES-TIME-CONFORMANCE.md](engineering/ODES-TIME-CONFORMANCE.md), [engineering/odes-time-fields.json](engineering/odes-time-fields.json) | Time rules (draft), conformance table and member classes. |
| [engineering/INDEPENDENT-VERIFIER-DESIGN.md](engineering/INDEPENDENT-VERIFIER-DESIGN.md) | Independent verifier and mutation suite design. *Historical.* |
| [engineering/ODES-P0-INVENTORY.md](engineering/ODES-P0-INVENTORY.md) | Decoupling inventory, with retained per-repository inventories in `engineering/p0-inventory/` (JSON, not edited). *Historical.* |
| [workstreams/odes-control-plane-store-checkpoint.md](workstreams/odes-control-plane-store-checkpoint.md) | Control Plane store compatibility checkpoint. *Historical.* |
| [workstreams/odes-producer-v2-checkpoint.md](workstreams/odes-producer-v2-checkpoint.md) | Producer v2 checkpoint. *Historical.* |
| [security-runtime-profile-20261016.md](security-runtime-profile-20261016.md), [security-runtime-f5b-profile-20261016.md](security-runtime-f5b-profile-20261016.md), [security-runtime-p4-p2-profiles.md](security-runtime-p4-p2-profiles.md) | Candidate producer generations (listed here; selection is by the hub lock). *Historical.* |
| [security-cloud-remediation-20261016.md](security-cloud-remediation-20261016.md) | Remediation proposal and its disposition. *Historical.* |

## Repository pages outside docs/

[README](../README.md) · [CONTRIBUTING](../CONTRIBUTING.md) · [GOVERNANCE](../GOVERNANCE.md) · [SECURITY](../SECURITY.md) · [CODE_OF_CONDUCT](../CODE_OF_CONDUCT.md) · [CROSS_COMPONENT_TESTS](../CROSS_COMPONENT_TESTS.md) · [LICENSE](../LICENSE) · [NOTICE](../NOTICE) · [business overview](../collateral/business-collateral.md) · [one-page overview](../collateral/one-page-overview.md)
