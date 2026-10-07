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

**Portable decision evidence across system and organizational boundaries.**

## Overview

ODES is an open, vendor-neutral discussion draft and reference tooling for portable decision evidence. The v0.2 narrative and implementation profile retain the pder-v0.1 record schema. It carries coordinates for recipient evaluation, rather than deciding whether a recipient should rely on the underlying decision.

**Implementation status:** this README describes merged public reference work. Component acceptance, selection in the hub and execution of a qualification are separate facts. The selected revision for this component is `0486b645e99c46d9cd16ca34b1ba7c653a6b3024`; the [hub lock](https://github.com/cogno-us/cognous-open-control-stack/blob/5737267d94d2b445735c95e8480a31de73a2abe8/component-lock.json) is the source of that integration choice.

## Purpose and intended users

A decision can cross a boundary without its authority basis, human disposition, evidence commitments, freshness or consumption conditions. Recipients need structured context while retaining their own policy and avoiding mandatory disclosure of confidential raw evidence.

Engineers can inspect the reference contracts and examples; enterprise architecture, security and governance reviewers can examine the boundary and evidence. Evaluate this component for its named responsibility rather than as a complete governance platform.

## Key features

| Capability | Implemented or specified responsibility |
|---|---|
| **Portable records** | Represent authority, machine role, human disposition, model/policy context and evidence references. |
| **Integrity packaging** | Bind exported content to explicit commitments while preserving the difference between integrity and authenticity. |
| **Recipient evaluation** | Evaluate package validity and declared consumption conditions under an explicit recipient policy. |
| **Stack mapping** | Export from exact supported Cognous Manifest and Replay inputs through a documented field mapping. |
| **Open draft process** | Keep schema, profiles, conformance material and lifecycle/reliance RFCs available for public review. |

## How it works

A producer exports a decision-evidence package from retained reconstruction. The recipient validates the record and commitments, then evaluates the package under its own policy. Missing authentication or current-authority evidence remains unavailable; package validity cannot silently fill those gaps. Selective disclosure concerns what is shared, not permission to infer omitted facts.

A valid signature, chain inclusion, message receipt, reasoning instruction or evidence-package digest does not authorize execution. Institutional authority must be supplied and evaluated through the appropriate trusted boundary.

## Getting started

From a fresh repository checkout, use Python 3.11+ and an activated virtual environment. Install only into that environment. Package installation needs network access; the commands below exercise local reference tooling. For the full selected integration, use the [hub quickstart](https://github.com/cogno-us/cognous-open-control-stack/blob/main/docs/quickstart.md), whose runner supplies exact producer checkouts and test wiring.

```bash
python -m pip install -e ".[dev]"
odes --help
```

## Evidence and supported scope

The selected implementation is `0486b645e99c46d9cd16ca34b1ba7c653a6b3024`, accepting the persistence-compatible Control Plane/Replay generation while preserving older mappings. See the [compatibility checkpoint](docs/workstreams/odes-control-plane-store-checkpoint.md). This accepted implementation does not turn the discussion draft into a ratified standard or establish external adoption.

The accepted [hub persistence-generation evidence](https://github.com/cogno-us/cognous-open-control-stack/blob/5737267d94d2b445735c95e8480a31de73a2abe8/examples/control-plane-store-adoption/qualification-summary.json) records 915 Python tests in each of two repetitions, 35 matrix entries satisfying their gates and 120 separate mocked OpenShell tests. Those are aggregate hub results, not a per-component test count or a claim of production readiness. Optional behavioral layers receive static checks only. The [support ledger](https://github.com/cogno-us/cognous-open-control-stack/blob/main/docs/release-status.md) separates implementation, execution and adoption.

## Limitations and deployment decisions

ODES is not a shared policy plane, blockchain requirement, certification or proof that a decision is correct, lawful or suitable for reliance. It does not grant execution authority. Reference implementation compatibility is narrower than a universal interoperability or standards-adoption claim.

Review original artifacts and their exact source revisions before extending a claim to a new environment. New dependencies, authority sources, destinations or enforcement mechanisms need their own compatibility and qualification. A passing reference case is not a certification of an enterprise deployment.

## Repository guide

Use these sources for details; their historical checkpoints retain the status and scope of the work they recorded:

- [docs/recipient-validation.md](docs/recipient-validation.md)
- [docs/cognous-stack-field-mapping.md](docs/cognous-stack-field-mapping.md)
- [docs/selective-disclosure.md](docs/selective-disclosure.md)
- [docs/related-work.md](docs/related-work.md)

For a nontechnical introduction, read the [business overview](collateral/business-collateral.md) and [one-page overview](collateral/one-page-overview.md). Both describe this component's role and evidence limits, not additional runtime features.

## Contributing and attribution

[Contribution guidance](CONTRIBUTING.md) describes review and validation expectations. Keep evidence-linked claims, preserve historical records and separate proposed features from accepted implementation.

See [LICENSE](LICENSE) and [attribution](NOTICE) for the existing terms and third-party scope. Developed by [Cognous](https://cogno.us); no licensing change is part of this documentation update.

---

## Bibliography

Selected external sources from the October 2026 research review. These inform evaluation questions; they do not establish Cognous implementation, adoption, conformance or production qualification.

- [Alexander Barrett. *Boundary Blindness Under Artificial Intelligence: Early Cross-Industry Findings on the Missing Decision-Evidence Layer* (2026)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7210798). Working paper on carrying the basis for reliance across organizational boundaries; proposed architecture, not a validated interoperability guarantee.
- [John M. Willis. *Runtime Governance Body of Knowledge for Artificial Intelligence and Other Autonomous Systems — Glossary* (19 July 2026)](https://sustainablefuturetech.com/asg-wg-runtime-governance-glossary/). Discussion draft on authority, execution and evidence terminology; not an adopted standard or Cognous conformance requirement.
- [OECD. *Agentic AI in organisations: Early insights from practitioner interviews*. OECD Artificial Intelligence Papers, No. 65 (2026)](https://doi.org/10.1787/1257a26f-en). Qualitative practitioner research on bounded autonomy, oversight and organizational deployment.

See the [research bibliography](https://github.com/cogno-us/cognous-open-control-stack/blob/main/docs/research-bibliography.md) for review scope and source-verification limits.

## Cognous stack components

[Stack hub](https://github.com/cogno-us/cognous-open-control-stack) · [Selected pins](https://github.com/cogno-us/cognous-open-control-stack/blob/main/component-lock.json) · [Evidence and limits](https://github.com/cogno-us/cognous-open-control-stack/blob/main/docs/release-status.md)

Component links are navigation, not a requirement to install every component. The hub lock determines its supported integration.

| Component | Responsibility |
|---|---|
| [Agent Action Manifest](https://github.com/cogno-us/cognous-agent-action-manifest) | Declare the action before evaluating permission |
| [Agent Control Plane](https://github.com/cogno-us/cognous-agent-control-plane) | Evaluate proposals against authority and preserve the decision record |
| [Agent Replay Bundle](https://github.com/cogno-us/cognous-agent-replay-bundle) | Reconstruct what the retained records support |
| [Agent Governance Evidence Pack](https://github.com/cogno-us/cognous-agent-governance-evidence-pack) | Turn traceable runtime records into reviewable governance evidence |
| [Alvorada Experimental Workbench](https://github.com/cogno-us/alvorada) | Governed exchange and continuity for a bounded synthetic workflow |
| [Moltbot Safe](https://github.com/cogno-us/moltbot-safe) | Constrained execution beneath independent current authorization |
| [BitRep](https://github.com/cogno-us/bitrep) | Verify issuer signatures under explicit trust assumptions |
| [The Index](https://github.com/cogno-us/the-index) | A local blockchain reference for claims, evidence commitments and lifecycle history |
| [Portable Reasoning Protocol v1.0](https://github.com/cogno-us/portable-reasoning-protocol) | Portable instructions for evidence-bounded reasoning |
| [Research Intelligence Protocol v1.0](https://github.com/cogno-us/research-intelligence-protocol) | Disciplined discovery and cross-domain abstraction, kept separate |
| [TFA Protocol (S43)](https://github.com/cogno-us/truth-freedom-agency-protocol) | Truth · Freedom · Agency |
| [Constitutional Governance for Institutions](https://github.com/cogno-us/constitutional-governance-for-institutions) | Alvorada: authority, challenge and correction for institutions |
