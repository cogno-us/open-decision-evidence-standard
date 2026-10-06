<!-- cognous-banner:start -->
```text
──────────────────────────────────────────────────
   __________  _______   ______  __  _______
  / ____/ __ \/ ____/ | / / __ \/ / / / ___/
 / /   / / / / / __/  |/ / / / / / / /\__ \
/ /___/ /_/ / /_/ / /|  / /_/ / /_/ /___/ /
\____/\____/\____/_/ |_/\____/\____//____/
         OPEN DECISION EVIDENCE STANDARD
       g o v e r n e d   b y   d e s i g n
  github.com/cogno-us/cognous-open-control-stack
──────────────────────────────────────────────────
```
<!-- cognous-banner:end -->

# Open Decision Evidence Standard

- **Status:** Discussion Draft v0.2 narrative; schema reference `pder-v0.1`
- **Repository name:** `open-decision-evidence-standard`
- **Public project page:** https://opendecisionevidence.org (pending publication)
- **Repository URL:** https://github.com/titanicprime/open-decision-evidence-standard
- **License:** Apache License 2.0
- **Initial editorial maintainer:** Cognous, pending neutral governance transition
- **Purpose:** Open, vendor-neutral record format for portable decision evidence in AI-mediated and cross-boundary decisions
- **Note:** This is not a product announcement

> Decisions travel. Evidence usually does not. ODES defines the portable decision-evidence record for that missing layer.
>
> Coordinates, not conclusions.

## Version note

The current machine-readable schema is `pder-v0.1`. The v0.2 narrative draft expands the explanatory specification text and informative related-work review but does not introduce a schema-breaking change.

A future schema-breaking update should be versioned separately.

## Summary

The Open Decision Evidence Standard is a discussion draft for a vendor-neutral, portable decision-evidence record format for AI-influenced decisions that cross organizational, system, or jurisdictional boundaries.

It gives decisions a structured evidence container: authority, machine role, human disposition, model state, policy basis, evidence commitments, freshness, revocation, and consumption conditions.

The goal is not to force a conclusion. The goal is to carry coordinates. A relying party can evaluate the record under its own rules without requiring shared infrastructure, proprietary trust networks, or disclosure of confidential source data.

A good decision evidence record should carry coordinates, not conclusions.

## What This Is

This repository contains a candidate standard for an open, vendor-neutral, freely implementable portable decision-evidence record. ODES is intentionally minimal, but not simplistic. It does not try to govern all of AI. It defines one open interoperability object: the portable decision-evidence record.

That record lets human, machine, and hybrid decisions carry structured governance metadata across boundaries without forcing raw data disclosure, shared infrastructure, shared policy planes, shared model internals, or proprietary trust networks.

ODES treats decisions as governed artifacts rather than bare outcomes: when a decision crosses a boundary, it should carry enough governance context for another party to evaluate it.

A portable decision evidence record is meant to answer:

> What was decided, who or what participated, under what authority, with what machine role and human disposition, against what evidence and policy basis, under what model state, and under what freshness, revocation, and consumption conditions?

The repository includes a discussion-draft schema, field documentation, examples, conformance materials, and profiles for different implementation contexts.

## What This Is Not

This is not:

- a commercial product;
- a proprietary trust network;
- a data lake;
- a shared ledger by default;
- a blockchain requirement;
- a universal workflow system;
- a model registry;
- a policy management platform;
- a replacement for ISO, NIST, SOC, audit, legal review, GRC, AIBOMs, model passports, provenance systems, or sector-specific standards;
- a requirement that counterparties expose confidential data to one another;
- a requirement that raw evidence be disclosed;
- a certification that any decision is correct;
- a proof that any decision was correct, lawful, complete, fair, or suitable for reliance;
- a compliance guarantee;
- a claim that any commercial platform is the standard itself;
- or a claim that portable records eliminate misuse, fraud, regulatory risk, or governance failure.

ODES records structured evidence about how a decision was represented as having been made. It does not prove that the decision was correct, lawful, complete, fair, or suitable for reliance.

## ODES as the cross-boundary decision-evidence layer

ODES formalizes a portable governance object that current AI governance, AIBOM, model documentation, provenance, audit, and decision-memory systems generally do not center as their primary unit of cross-boundary interoperability: the decision-evidence record.

AIBOMs describe what the AI system is: its components, dependencies, lineage, lifecycle context, and supply-chain properties. ODES describes what the AI-influenced decision was: who or what participated, under what authority, with what human disposition, under what model state, against what evidence and policy basis, and under what consumption conditions.

ODES does not replace the adjacent stack. It gives those systems a decision-level object to emit or consume at the boundary.

The intended role of ODES is to help decision-level evidence travel across organizational, system, and jurisdictional boundaries without forcing counterparties into the same platform, proprietary trust network, or shared infrastructure, and without requiring disclosure of underlying confidential data.

### Adjacent work

ODES is adjacent to, but distinct from, other open efforts around decision records, legal evidence, and workflow automation.

- **Operational Decision Standard (ODS)** focuses on institutional decision memory: recording, verifying, governing, and learning from organizational decisions over time. ODES focuses on cross-boundary decision-evidence portability: the record that travels with or alongside an AI-influenced decision so another party can evaluate it under its own rules.

- **Open Evidence Standard (OES)** focuses on structured, verifiable legal evidence extracted from documents, audio, and video. ODES may reference evidence commitments or evidence packages, but its unit of interoperability is the decision-evidence record, not the extracted evidence item.

- **Open Decision** is an open-source no-code workflow automation platform for recurring legal requests. ODES is not a workflow automation platform; it is a portable record format.

The ODES claim is intentionally narrow: decisions travel, evidence usually does not. ODES defines a portable decision-evidence record for that missing cross-boundary layer. See [Related and Adjacent Work](docs/related-work.md) for a longer comparison.

## Why This Should Be Open

A decision evidence format intended for cross-boundary use should not require trust in a single vendor or operator. Openness matters because relying parties need to inspect the format, implement it independently, test it publicly, and use it without joining a proprietary control plane.

An open candidate standard also helps preserve a clean distinction between the public record format and any commercial products that may later produce, verify, route, or govern records built on top of it.

## Background

Artificial intelligence makes an existing governance gap more acute. Decisions can now be created, recommended, routed, or executed at greater speed and scale, with changing model states and weaker human review artifacts than many legacy control environments assumed.

Internal governance remains necessary, but internal governance alone is not enough when a decision must be consumed by another organization, another system, or another jurisdiction. This draft focuses on portability of decision evidence rather than portability of raw underlying data.

## Core Design Principles

1. **Record, not copy** — the record carries commitments, references, attestations, and verification metadata rather than requiring raw evidence to move.
2. **Coordinates, not conclusions** — the record gives relying parties structured information for evaluation; it does not force them to accept a decision.
3. **Portable across boundaries** — the record is usable across organizations, systems, and jurisdictions without requiring shared infrastructure or a proprietary trust network.
4. **Human and machine roles must be distinguishable** — machine assistance, recommendation, execution, escalation, human review, modification, override, and non-review must not collapse into one approval label.
5. **Model state matters** — relevant model version, runtime conditions, tool access, and configuration should be captured or referenced.
6. **Authority must be time-bound** — authority should be tied to a basis, actor, system, and validity window.
7. **Freshness and revocation are first-class** — expiration, supersession, revocation, stale status, and revalidation matter.
8. **Fail closed where required conditions are missing** — records should not silently pass when verification, authority, freshness, or consumption conditions cannot be evaluated.

## What ODES makes possible

ODES makes evidence referenceable, verifiable, and bounded. A record can carry hashes, references, attestations, verification metadata, policy identifiers, consumption conditions, and status information while sensitive underlying evidence remains with the issuer.

This separation lets a receiving party evaluate a decision without forcing both sides onto one platform, one ledger, one cloud, one policy engine, one model registry, or one proprietary trust network.

| Without ODES | With ODES |
| --- | --- |
| The outcome travels, but evidence stays behind. | The decision can travel with a structured evidence record. |
| The receiver may blindly trust the issuer or duplicate the review. | The receiver can evaluate authority, evidence commitments, freshness, and conditions. |
| Human review and machine reliance may blur together. | Human disposition and machine role are separated. |
| Model state may be reconstructed later, if at all. | Model state and runtime coordinates can be captured at decision time. |
| Validity may be ambiguous after policy, evidence, or authority changes. | Freshness, expiration, revocation, and supersession become explicit record semantics. |

## Minimum Expressible Field Categories

The table below describes conceptual field categories. The normative draft JSON field paths are defined in `schema/pder-v0.1.schema.json` and documented in `schema/pder-v0.1-fields.md`.

| Field category | Purpose |
| --- | --- |
| Decision identifier | Stable identifier for the decision being evidenced. |
| Decision type | High-level category of decision or disposition. |
| Decision timestamp | Time at which the decision was made. |
| Issuer identity | Organization and system identity for the record issuer. |
| Authority basis and validity | Source and validity window of decision authority. |
| Machine role | Whether and how AI or automation participated. |
| Model state | Model identity, version, and runtime coordinates relevant to review. |
| Human disposition | Human review status and disposition in relation to machine output. |
| Machine reliance level | Approximate degree of machine reliance in the human decision path. |
| Evidence commitment | Hash, reference, attestation, other verification material, or explicit absence of supporting evidence commitment. |
| Policy basis | Rules, controls, contracts, or standards used in the decision. |
| Risk coordinates | Risk tier, jurisdiction, and restricted or prohibited use flags. |
| Consumption conditions | Who may assess the record for a stated purpose, under stated conditions, and until when. |
| Freshness status | Current, stale, expired, superseded, revoked, pending revalidation, or unknown status. |
| Verification metadata | Signature, key reference, profile, and verifier information. |

In the v0.1 schema, the model-state, machine-reliance-level, evidence-commitment, and freshness-status concepts are represented within the `machine_role`, `human_disposition`, `evidence`, and `status` objects.

## Illustrative Example

```json
{
  "record_type": "portable_decision_evidence_record",
  "schema_version": "0.1",
  "decision_id": "air-2026-07-001",
  "decision_type": "ai_assisted_review",
  "decision_timestamp": "2026-07-01T14:30:00Z",
  "issuer": {
    "organization_id": "issuer.example.org",
    "system_id": "review-orchestrator"
  },
  "authority": {
    "human_reviewer_role": "senior_case_reviewer",
    "authority_basis": "internal-review-policy-v3",
    "authority_valid_at_decision": true
  },
  "machine_role": {
    "ai_used": true,
    "role": "recommendation",
    "model_id": "triage-model",
    "model_version": "2026.06"
  },
  "human_disposition": {
    "status": "modified",
    "review_substantiveness": "substantive",
    "machine_reliance_level": "medium"
  },
  "evidence": {
    "evidence_commitment_type": "hash",
    "evidence_hash": "sha256:...",
    "selective_disclosure_available": true
  },
  "policy_basis": [
    {
      "policy_id": "review-policy",
      "policy_version": "3.2",
      "policy_type": "internal_policy"
    }
  ],
  "risk_coordinates": {
    "risk_tier": "medium",
    "jurisdiction": "multi-jurisdiction"
  },
  "consumption_conditions": {
    "permitted_relying_parties": ["counterparty-a"],
    "permitted_purposes": ["audit"],
    "expires_at": "2026-09-30T00:00:00Z"
  },
  "status": {
    "freshness": "current",
    "superseded": false,
    "revoked": false
  },
  "verification": {
    "signature_type": "jws-detached",
    "issuer_key_reference": "did:web:issuer.example.org#keys-1",
    "conformance_profile": "pder_v0_1_minimal"
  }
}
```

Schema validation checks structure. It does not establish that the underlying decision is correct, lawful, complete, or suitable for reliance. A record may be schema-valid and still fail profile conformance, verifier acceptance, or a relying party's decision to rely.

## Candidate Use Cases

- AI-assisted underwriting
- Claims handling
- Trade finance
- Customs and logistics
- AML and sanctions
- Vendor AI governance
- Agentic AI operations
- Regulatory response

## Current schema scope

The current `pder-v0.1` schema scope is intentionally limited. It proposes:

- a baseline JSON record structure;
- a shared vocabulary for portable decision evidence;
- a minimal conformance profile;
- verifier requirements at the conceptual level;
- and illustrative profiles for different implementation settings.

It does not attempt to settle cryptographic profiles, sector-specific mandates, trust frameworks, or governance arrangements for a mature standards body.

## Repository Structure

```text
/
├── README.md
├── LICENSE
├── NOTICE
├── GOVERNANCE.md
├── CONTRIBUTING.md
├── SECURITY.md
├── CODE_OF_CONDUCT.md
├── docs/
├── schema/
├── examples/
├── conformance/
├── profiles/
└── rfcs/
```

See the repository directories for the current discussion-draft schema, examples, profiles, and conformance materials.

## Related RFCs

- [RFC 0003: Verifier Behavior and Reliance Boundaries](rfcs/0003-verifier-behavior-and-reliance-boundaries.md) defines verifier behavior and reliance boundaries.
- [RFC 0004: Decision-Evidence Lifecycle Semantics](rfcs/0004-decision-evidence-lifecycle-semantics.md) defines decision-evidence lifecycle semantics.

## Governance Proposal

The repository is currently under initial editorial maintenance by Cognous as a public discussion draft, with the stated goal of transitioning to neutral standards governance if the effort gains external participation and sufficient implementation interest.

See [`GOVERNANCE.md`](GOVERNANCE.md) for the current draft governance approach.

## What Would Strengthen the Draft

The draft would be strengthened by evidence that independent parties can implement it, exchange records across boundaries, validate records consistently, and use it without disclosing unnecessary confidential data.

Signs of validation would include public review, independent prototypes, comments from regulated sectors, cross-organizational testing, and convergence on useful conformance profiles.

## What Would Weaken or Falsify the Standard

The proposal would be weakened if the record cannot be interpreted consistently, requires excessive disclosure to be useful, cannot support meaningful verification without hidden infrastructure, or collapses into product-specific assumptions.

It would also be weakened if the same use cases can be met more simply by existing open formats without loss of meaning or interoperability.

## Relationship to Commercial Implementations

Commercial implementations may be developed separately. Those implementations may offer control planes, governance workflows, key management, verification services, audit interfaces, or operational tooling.

That commercial layer is outside the scope of this repository. The intent here is to keep the record format open and interoperable so that no commercial implementation becomes the format itself.

## License

Unless otherwise noted, this repository is licensed under the Apache License 2.0. The intent is to develop an open, vendor-neutral, freely implementable record format for portable decision evidence. Commercial implementations may be developed separately, provided the record format remains open and interoperable.

## Contribution Policy

Contributions are welcome through issues and pull requests. Contributors should focus on technical clarity, portability, verifiability, privacy, and realistic cross-boundary use.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for contribution expectations.

## Call for Comment

Comments are especially welcome on record scope, field selection, conformance requirements, verifier behavior, privacy-preserving disclosure patterns, sector-specific examples, and alignment with existing open standards.

## Disclaimer

This repository is a discussion draft for an open, vendor-neutral candidate decision evidence standard. It is not a product announcement, legal advice, compliance advice, certification, assurance, warranty, or representation that any record produced under the draft prevents misuse, fraud, error, regulatory failure, or harm.

A schema-valid or profile-conforming record does not establish that the underlying decision is correct, legal, complete, or suitable for reliance.

This draft has not been recognized, approved, adopted, or endorsed by any regulator or standards body.

No endorsement, affiliation, approval, sponsorship, or relationship with any external researcher, standards body, regulator, or institution is implied unless expressly stated.

## Suggested Citation

*Open Decision Evidence Standard: Discussion Draft v0.2 narrative; schema reference `pder-v0.1`*. Cognous, July 2026. Repository: `open-decision-evidence-standard`. Apache License 2.0.
