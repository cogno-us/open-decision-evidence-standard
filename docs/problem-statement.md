# Problem Statement

Draft status note: This document is part of a discussion draft for an open, vendor-neutral candidate standard. It is not a product announcement, legal advice, compliance advice, certification, assurance, or warranty. Governance is currently single-maintainer (Cognous is the initial editorial maintainer); the work is a draft.

Decisions travel. Evidence usually does not.

When an AI-influenced decision leaves the system or organization that produced it, the receiving party may get the outcome without the structured evidence needed to evaluate who or what participated, under what authority, against what evidence and policy basis, under what model state, and under what freshness, revocation, and consumption conditions.

Artificial intelligence makes this problem more acute through speed, scale, model change, agentic action, and weaker human review artifacts. Internal governance remains necessary, but it is insufficient when decision evidence must be consumed by another party that does not share the issuer's systems or internal controls.

ODES addresses that missing layer by defining the portable decision-evidence record.

This project addresses decision evidence portability rather than raw data sharing. The goal is to support portable evidence coordinates while preserving confidentiality, data locality, and implementation independence.

This problem framing is aligned with Alexander D. Barrett’s July 2026 paper, Boundary Blindness Under Artificial Intelligence, which independently articulates the cross-boundary decision-evidence gap and frames AI as an amplifier of a pre-existing structural failure. No endorsement, affiliation, or relationship is implied.
