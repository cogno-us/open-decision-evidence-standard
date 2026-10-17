# Typed refusal consumer candidate migration

Status: nonselected candidate profile proposal; ODES remains draft. Profile version `odes-cognous-stack-export-0.2.2-refusal-candidate` is a proposed, separately versioned extension of unchanged `pder-v0.1`, not part of the core standard.

Separate nonselected profile. Exact actual merged predecessors:
CP `c7f122ba3a6e39f9268a7163c99be3ee514cd97e`, executor
`309e194c1b0a3de23e11e20133e6eaf88875e48a` (runtime #86), Replay
`83fbaf2a0f6f071aca1ea0af859eb8fc6385c26a` (Replay #25), Manifest
`46c950bed37fe3812000895430bc0312d29e37ce`. The exact-source gate verifies
these checkouts before executing; final hub candidate qualification remains separate.

The separate transformation profile rebuilds all four retained new CP collections
(refusals, resolution checks, time floors, closeouts) before calling Replay.
Full records, links, commitments, producer profile, status and observation-history
comparisons remain required. Typed executor refusal evidence and original
operation/decision/effect/attempt/observation lineage are retained; no unknown data
is silently made supported and no safety semantics are weakened to pass imports.
Historical transformations keep their original pins and behavior. The new ODES
profile lists only the four inputs used here, excluding unused downstream Evidence
Pack and historical discovery/reference pins; it does not claim those executed.

Dedicated exact-checkout Python 3.11/3.12 CI runs ten actual-component cases: four
refusals, success, lost-ack closeout, and four retained-evidence tampering negatives.
Local ten-case run passes without failures/errors/skips/subtests. Broader historical
matrices require their own original dependency environment and remain required.
Unconfigured local broad runs are not passes: ODES 2 passed/112 skipped; Evidence
Pack 117 passed/15 failed/42 setup errors/74 skipped (missing CLI/dependency inputs
and a historical fixture/validator mismatch). No exclusions were added to existing
CI, and no assertion was weakened to resolve that environment mismatch.

Source consistency is not independent authentication, fresh authority, delivery
or current retry permission. Candidate selection remains a separate owner decision.
The hub selected lock/profiles remain unchanged; both authorizations remain false,
operational trust and publication/production HOLD. C0 check-to-commit limits,
optional cooperative same-host C1 and no C2/C3/real settlement remain explicit.
