# Open Decision Evidence Standard — One-Page Overview

## Purpose

ODES is an open, vendor-neutral discussion draft and reference tooling for portable decision evidence. The v0.2 narrative and implementation profile retain the pder-v0.1 record schema. It carries coordinates for recipient evaluation, rather than deciding whether a recipient should rely on the underlying decision.

## Problem

A decision can cross a boundary without its authority basis, human disposition, evidence commitments, freshness or consumption conditions. Recipients need structured context while retaining their own policy and avoiding mandatory disclosure of confidential raw evidence.

## What It Provides

- **Portable records:** Represent authority, machine role, human disposition, model/policy context and evidence references.
- **Integrity packaging:** Bind exported content to explicit commitments while preserving the difference between integrity and authenticity.
- **Recipient evaluation:** Evaluate package validity and declared consumption conditions under an explicit recipient policy.
- **Stack mapping:** Export from exact supported Cognous Manifest and Replay inputs through a documented field mapping.

## Where It Fits

A producer exports a decision-evidence package from retained reconstruction. The recipient validates the record and commitments, then evaluates the package under its own policy. Missing authentication or current-authority evidence remains unavailable; package validity cannot silently fill those gaps. Selective disclosure concerns what is shared, not permission to infer omitted facts.

A valid signature, chain inclusion, message receipt, reasoning instruction or evidence-package digest does not authorize execution. Institutional authority must be supplied and evaluated through the appropriate trusted boundary.

## Evidence and Limits

The [accepted hub lock](https://github.com/cogno-us/cognous-open-control-stack/blob/5737267d94d2b445735c95e8480a31de73a2abe8/component-lock.json) selects this component at `0486b645e99c46d9cd16ca34b1ba7c653a6b3024`. Read the component's [README](../README.md) for version-specific acceptance and the [hub support ledger](https://github.com/cogno-us/cognous-open-control-stack/blob/main/docs/release-status.md) for the executed scope. Component acceptance is not automatic adoption of newer revisions or production qualification.

ODES is not a shared policy plane, blockchain requirement, certification or proof that a decision is correct, lawful or suitable for reliance. It does not grant execution authority. Reference implementation compatibility is narrower than a universal interoperability or standards-adoption claim.

## Practical Next Step

Choose one bounded example and follow the [README](../README.md). Compare expected and observed results and retain uncertainty. The [business collateral](business-collateral.md) supplies evaluation questions and the component's wider context.

[Cognous](https://cogno.us) · [Source](https://github.com/cogno-us/open-decision-evidence-standard) · [All stack components](https://github.com/cogno-us/cognous-open-control-stack). Existing licenses and notices apply.
