# Typed refusal consumer candidate migration

Draft, nonselected profile. Current exact source pins are CP c7f122ba,
executor PR #86 head 63bd4d8d, Replay PR #25 head 24fa9571 and Manifest 46c950be.
Executor/Replay pins must be replaced by their actual merge commits and affected
checks rerun before integration. No final merged-chain qualification is asserted.

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
