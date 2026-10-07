# Open Decision Evidence Standard — Business Collateral

## 1. Executive Summary

ODES is an open, vendor-neutral discussion draft and reference tooling for portable decision evidence. The v0.2 narrative and implementation profile retain the pder-v0.1 record schema. It carries coordinates for recipient evaluation, rather than deciding whether a recipient should rely on the underlying decision.

## 2. The Business Problem

A decision can cross a boundary without its authority basis, human disposition, evidence commitments, freshness or consumption conditions. Recipients need structured context while retaining their own policy and avoiding mandatory disclosure of confidential raw evidence.

## 3. The Component in One View

| Capability | Practical role |
|---|---|
| Portable records | Represent authority, machine role, human disposition, model/policy context and evidence references. |
| Integrity packaging | Bind exported content to explicit commitments while preserving the difference between integrity and authenticity. |
| Recipient evaluation | Evaluate package validity and declared consumption conditions under an explicit recipient policy. |
| Stack mapping | Export from exact supported Cognous Manifest and Replay inputs through a documented field mapping. |
| Open draft process | Keep schema, profiles, conformance material and lifecycle/reliance RFCs available for public review. |

## 4. Who Should Evaluate It

Engineers can inspect the reference contracts and examples; enterprise architecture, security and governance reviewers can examine the boundary and evidence. Evaluate this component for its named responsibility rather than as a complete governance platform.

## 5. A Bounded Workflow

A producer exports a decision-evidence package from retained reconstruction. The recipient validates the record and commitments, then evaluates the package under its own policy. Missing authentication or current-authority evidence remains unavailable; package validity cannot silently fill those gaps. Selective disclosure concerns what is shared, not permission to infer omitted facts.

This is a reference use case. Adopting the format or running the example does not establish a production deployment, institutional acceptance or measured business benefit.

## 6. Relationship to the Stack

This component contributes **portable decision evidence across system and organizational boundaries**. The [Cognous Open Control Stack](https://github.com/cogno-us/cognous-open-control-stack) connects declared proposals, independent authority, constrained execution and retained review evidence. Components remain separately owned and versioned; the [selected lock](https://github.com/cogno-us/cognous-open-control-stack/blob/5737267d94d2b445735c95e8480a31de73a2abe8/component-lock.json) determines which revisions participate in the supported integration.

A valid signature, chain inclusion, message receipt, reasoning instruction or evidence-package digest does not authorize execution. Institutional authority must be supplied and evaluated through the appropriate trusted boundary.

## 7. What the Evidence Supports

The selected implementation is `0486b645e99c46d9cd16ca34b1ba7c653a6b3024`, accepting the persistence-compatible Control Plane/Replay generation while preserving older mappings. See the [compatibility checkpoint](../docs/workstreams/odes-control-plane-store-checkpoint.md). This accepted implementation does not turn the discussion draft into a ratified standard or establish external adoption.

The [accepted hub evidence](https://github.com/cogno-us/cognous-open-control-stack/blob/5737267d94d2b445735c95e8480a31de73a2abe8/examples/control-plane-store-adoption/qualification-summary.json) supports bounded synthetic integration at its exact pins. Aggregate test totals do not establish deployment benefit, compliance or independent real-world verification. The [support ledger](https://github.com/cogno-us/cognous-open-control-stack/blob/main/docs/release-status.md) distinguishes the standard reference, separate protected-worker campaign and unqualified production work.

## 8. What It Does Not Establish

ODES is not a shared policy plane, blockchain requirement, certification or proof that a decision is correct, lawful or suitable for reliance. It does not grant execution authority. Reference implementation compatibility is narrower than a universal interoperability or standards-adoption claim.

## 9. Evaluation Questions

- Which exact input, output and source revision will the receiving system consume?
- Who supplies trusted authority or evidence, and which assumptions remain outside this component?
- Can a reviewer trace the result to retained sources, including rejected or missing information?
- Which documented checks were actually executed in the intended environment?
- What deployment-specific work is required before relying on the result?

## 10. Why Open Reference Material Matters

Public formats, source, examples and evidence allow reviewers to inspect the claimed boundary and reproduce its checks. They also expose what has not been tested. Openness supports review; it does not substitute for independent assurance or operating responsibility.

## 11. Practical Next Step

Follow the [README](../README.md) and select one bounded use case. Inspect its inputs and expected outputs, reproduce the documented checks where prerequisites are available, and record failures and unresolved assumptions alongside passes. Use the [one-page overview](one-page-overview.md) for initial stakeholder orientation.

## 12. Status and Attribution

This collateral summarizes merged public material at repository `0486b645e99c46d9cd16ca34b1ba7c653a6b3024` and the accepted hub baseline `5737267d94d2b445735c95e8480a31de73a2abe8`. It does not anticipate pending branches. The protected-worker result applies only to its recorded Linux/bubblewrap fixture; live OpenShell and logical-intent prevention are not hub-supported at this snapshot.

[Cognous](https://cogno.us) · [Source repository](https://github.com/cogno-us/open-decision-evidence-standard) · [Stack responsibilities](https://github.com/cogno-us/cognous-open-control-stack/blob/main/docs/architecture.md). Existing licenses and third-party notices remain controlling.
