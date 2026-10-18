# Public Messaging

ODES is a vendor-neutral, portable decision-evidence record format for AI-influenced decisions that cross organizational, system, or jurisdictional boundaries. It gives decisions a structured evidence container: authority, machine role, human disposition, model state, policy basis, evidence commitments, freshness, revocation, and consumption conditions. It is a draft with single-maintainer governance (Cognous is the initial editorial maintainer), not a ratified standard.

The goal is not to force a conclusion. The goal is to carry coordinates. A relying party can evaluate the record under its own rules without requiring shared infrastructure, proprietary trust networks, or disclosure of confidential source data.

## Core lines

- Decisions travel. Evidence usually does not.
- Coordinates, not conclusions.
- Record, not copy.
- Intentionally minimal, but not simplistic.
- Decisions as governed artifacts, not bare outcomes.
- Open record format; commercial implementations separate.
- Structured evidence, not raw data.
- Open format, not platform lock-in.

## Approved short description

ODES is a portable governance envelope for AI-influenced decisions: structured evidence, not raw data; coordinates, not conclusions; open format, not platform lock-in.

## Adjacent work

When discussing ODES alongside adjacent projects, keep the distinction narrow and factual.

### ODS / Operational Decision Standard

Safe framing:

ODS is about institutional decision memory. ODES is about cross-boundary decision-evidence portability.

Longer version:

Operational Decision Standard focuses on recording, verifying, governing, and learning from organizational decisions over time. ODES focuses on the portable decision-evidence record that travels with or alongside an AI-influenced decision when another party needs to evaluate it under its own rules.

Do not say:
- ODES replaces ODS.
- ODS is wrong or insufficient.
- ODES is the first decision standard.
- ODES owns the entire decision-record category.

### OES / Open Evidence Standard

Safe framing:

OES is about structured legal evidence extracted from source materials. ODES is about evidence attached to a decision crossing a boundary.

Longer version:

Open Evidence Standard focuses on structured, verifiable legal evidence from documents, audio, and video. ODES may reference evidence commitments or evidence packages, but its unit of interoperability is the decision-evidence record, not the extracted evidence item.

Do not say:
- ODES replaces OES.
- OES and ODES solve the same problem.
- Evidence extraction and decision-evidence portability are identical.

### Open Decision

Safe framing:

Open Decision is a workflow automation platform. ODES is a portable record format.

Longer version:

Open Decision appears to focus on no-code workflow automation for recurring legal requests. ODES does not automate workflows. It defines a portable decision-evidence record.

Do not say:
- Open Decision is a standards competitor.
- ODES is a workflow platform.
- The name similarity implies technical overlap.

Canonical contrast:

ODS is about institutional decision memory.
OES is about structured legal evidence.
Open Decision is about workflow automation.
ODES is about cross-boundary decision-evidence portability.

## Qualified wording

Use these forms where a short claim needs its dependency stated.

- Freshness and revocation: ODES records freshness, expiry and revocation coordinates. The reference validator can check them only given recipient-supplied status evidence; the record's own status is an issuer assertion.
- Authentication: the reference validator does not verify signatures. A content digest binds content and does not identify the issuer. Do not describe packages as signed or issuer-verified.
- Evidence disclosure: the base record carries commitments, not raw evidence. Profile 0.2 packages carry the retained original sources so a recipient can re-derive the summary, so with that profile raw evidence does move. Selective disclosure remains an open question ([selective-disclosure.md](selective-disclosure.md)).
- Layers: the record, the package envelope, the Cognous profile and the selected release are different layers ([capabilities and versions](capabilities-and-versions.md)). A Cognous profile feature is not part of the base ODES schema.
- Interoperability: compatibility between producers and the reference validator is tested in this project's own CI. No interoperability exchange with an independent implementation has been performed, and none is claimed.
- Standing: a draft with single-maintainer governance, not a ratified or certified standard.

## What not to say

Do not say:
- official standard
- regulator-approved standard
- regulator-recognized standard
- compliance guarantee
- certification
- tamper-proof
- proves correctness
- guarantees trust
- full AI governance platform
- Cognous owns the standard or trust network
- ODES is the first, only or unique standard, or the layer that lets other standards interoperate
- signed, issuer-verified or verifiable-issuer packages
- privacy-preserving, or raw evidence never moves
- revocation is checkable, without naming the recipient-supplied status evidence it depends on
- any adoption, interoperability, compliance or certification claim

## Boundary

ODES is not a product announcement, legal advice, compliance advice, certification, assurance, warranty, or proof that any underlying decision is correct, lawful, complete, or suitable for reliance. It has not been recognized, approved, adopted, or endorsed by any regulator or standards body.
