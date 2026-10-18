# Related and Adjacent Work

## Purpose

This note positions ODES alongside adjacent open efforts without treating them as substitutes. ODES remains a discussion-draft, candidate open standard for portable decision evidence, not a claim to cover every decision-record use case.

## Operational Decision Standard / ODS

Operational Decision Standard is the closest adjacent effort. It focuses on institutional decision memory: recording, verifying, governing, and learning from organizational decisions over time.

ODES is narrower and complementary. It focuses on cross-boundary decision-evidence portability: the record that travels with or alongside an AI-influenced decision so another party can evaluate it under its own rules.

## Open Evidence Standard / OES

Open Evidence Standard focuses on structured, verifiable legal evidence extracted from documents, audio, and video. Its unit of interoperability is the extracted evidence item and related evidence package.

ODES may reference evidence commitments or evidence packages, including an OES packet, but its unit of interoperability is the decision-evidence record rather than the extracted legal evidence item.

## Open Decision

Open Decision appears to focus on no-code workflow automation for recurring legal requests. That makes it adjacent in terminology, not a standards competitor in scope.

ODES is not a workflow automation platform. It is a portable record format.

## Adjacent decision-evidence efforts (reviewed October 2026)

These are short summaries of public material as read in October 2026. They may be out of date, they are not endorsements, and no affiliation or relationship is implied. Publication terms and patent covenants differ between efforts and are diligence inputs for any integration; this note makes no statement about them.

No interoperability exchange between ODES and any effort below has been performed. Compatibility tests in this repository's own CI show internal consistency only.

### VES (Verifiable Evidence Standard)

VES defines a decision envelope that wraps external evidence objects in their native formats and carries a verification block declared by the producer. It is the closest peer to the ODES base record at the decision-envelope layer. ODES keeps verification results with the recipient and does not put them in the record; a crosswalk would lose information in both directions (VES has outcome and several evidence entries, ODES binds recipient and purpose). ODES does not vendor or evaluate VES schemas.

### DPS (Decision Provenance Standard)

DPS defines organizational charters, decision records whose lifecycle requires an affirmative human act, and proposal-status extensions for portable verification, signatures and action binding. Its portable verification vocabulary (not checked, unsupported, unavailable) is the closest peer to the ODES recipient result values documented in [recipient validation](recipient-validation.md). A crosswalk of result semantics is possible; ODES does not adopt charters or a conformance ladder.

### AskLedger Receipts

AskLedger produces a signed, hash-chained receipt for each AI invocation. It is a complement: an ODES package may carry an unchanged receipt as native evidence ([native evidence inventory](native-evidence-inventory.md)) so that its own verifier and a recipient-owned key can check it. A receipt's policy verdict is not a human disposition and is not mapped to one.

### OVERT

OVERT specifies runtime attestation with notary receipts and transparency-log proofs. It is a complement: ODES may reference an attestation by identifier and digest as evidence. ODES makes no claim to verify OVERT receipts natively and does not reproduce its attestation chaining.

### What this means for ODES

ODES overlaps these efforts at the decision-envelope and recipient-verification layers and complements them at the runtime-receipt layer. Its distinguishing combination is recipient and purpose binding, separation of historical and present authority, and (in the Cognous profile only) source-to-summary consistency checking. None of the efforts, ODES included, establishes institutional authority or reliance on its own.

## ODES positioning

ODES is not a general decision-memory standard, legal-evidence extraction format, or workflow automation platform. It is a portable decision-evidence record format for AI-influenced decisions that cross organizational, system, or jurisdictional boundaries.

Its claim is intentionally narrow: when decisions travel, evidence usually does not. ODES defines the portable record for that missing cross-boundary layer.

## Non-claims

- ODES does not replace adjacent projects.
- ODES does not claim to be the first or only decision standard.
- ODES does not prove correctness or guarantee compliance.
- ODES does not require shared infrastructure or raw evidence disclosure.
- ODES does not make any commercial implementation the standard itself.
