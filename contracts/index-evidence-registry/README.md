# Index evidence-registry contract (0.1.0-draft)

A behavioural contract for the boundary around the Index (cognous-evidence-registry): what its evidence API exposes (links, link outcomes, epistemic status), what it consumes (a BitRep v1 link attestation and the operator trust snapshot), and how the BitRep attestation maps onto the chain profile. It is an optional extension profile in the pattern of `contracts/execution-attempt-lifecycle/` and `contracts/governed-exchange/`. It is a DRAFT: nothing here is frozen, and conformance shows structure and the stated rules only. It does not show that a link is true, that an issuer is authoritative, or that evidence is independent.

Rules were read from the Index code, producer side (`app/api/evidence.py`, `app/evidence/link_attestation.py`, `app/evidence/service.py`, `app/core/models.py`) and consumer side (the vendored BitRep verifier `app/bitrep_verify`, the chain adapter `chain/python/bitrep_adapter.py`, `chain/PROTOCOL.md`, `chain/client.mjs`). Fixtures were captured by running that code with synthetic inputs and a throwaway Ed25519 key.

Status: `0.1.0-draft`. Open questions IX-1 to IX-14 are in Appendix E of `docs/engineering/ODES-INTERCOMPONENT-CONTRACTS.md`. Version gate: any other `contract_version` is `unsupported_contract_version`.

## Index main against the feature branch

P0 inspected `fix/issues-23-24-link-attestation-independence`. This draft was written against Index `main` at d17b8ac (`fix: verify link attestations (BitRep v1) and count distinct sources for independence (#25)`). That squash commit already carries the link attestation, the 401/409/422/503 route behaviour and the distinct-source independence rule, and the feature branch is not on origin any more, so there is no remaining difference to carry: main is the contract's baseline. What main still lacks is listed under "Known producer non-conformance".

## Boundary members

A document is `{contract, contract_version, producer?, extensions?, <member>}` with at least one member. Every declared object is a closed member set; undeclared members are `undeclared_member` and are never dropped (F-10). `extensions` member names must match `^x-[a-z0-9][a-z0-9._-]*$` (`invalid_extension_key`). The BitRep envelope and statement are closed and carry no `extensions`: BitRep parses them with extra=forbid and an extra member would change the signed statement.

| Member | Index surface | Notes |
|---|---|---|
| `link_submission` | `POST <prefix>/evidence/links` body (`LinkCreate`) | claim, evidence or second claim, relation, strength, `attested_by`, `attestation` (BitRep v1 envelope) |
| `stored_link` | the `Link` the route returns and `GET /evidence/links/claim/{id}`, `/links/evidence/{id}` return | names the verified attestation id and statement digest |
| `verification_result` | `bitrep-verification/1` from the vendored verifier, with the envelope it judged | `outcome` verified or rejected, a closed reason set, `assurance` |
| `link_outcome` | the route's answer: 200, 201, 401, 409, 422, 503 | `reason` is the Index's `detail.reason` |
| `epistemic_status` | `GET <prefix>/evidence/epistemic-status/{claim_id}` | derived view, never truth |
| `chain_attestation_check` | the chain profile's binding of a BitRep statement to chain data | chain id, contract address, claim id, relation, evidence digest, statement digest |

## Rules

Structure (level S): `schema.json` closes the member sets, types, patterns and enumerations. Closed enumerations refuse an unknown value with `unknown_enum_value` and never coerce: relation types (seven), claim statuses (five), assurance (two), verifier reasons (twelve plus `ok`), HTTP statuses (six). `strength` is a number from 0 to 1 and is never coerced from a string or a boolean. Digests are `sha256:` plus 64 lowercase hex. A BitRep signature is exactly 88 characters.

Link submission (level L):

- Exactly one of `evidence_id` and `claim_id_2` is non-null (`link_target_invalid`).
- An attestation is present: `attested_by` alone is not accepted (`attestation_required`, the route's 401).
- The statement's times satisfy `issued_at <= not_before < expires_at` (`malformed_attestation`, the route's 422; the verifier's model refuses it).
- The statement binds this link (`attestation_binding_mismatch`, the route's 422), field by field: `statement_type` is `index.link.v1`; `subject` is the link's `claim_id`; `issuer` is `attested_by`; `content_digest` is `sha256:` plus SHA-256 of the link content bytes. Those bytes are the sorted-key compact ASCII-escaped JSON of `claim_id`, `claim_id_2`, `evidence_id`, `relation_type`, `strength`, with absent targets as null and `strength` as a float (`1.0`, never `1`). Note this is not the exchange's canonicalisation (that one keeps non-ASCII characters; this one escapes them). Only those five members are signed: `attested_by`, `attestation_id`, `extensions` and everything else are outside the commitment.

Stored link:

- The same single-target rule (`link_target_invalid`).
- `attestation_id` and `attestation_statement_digest` are both present or both absent (`attestation_commitment_incomplete`), and a stored link names them (`link_without_attestation`): the route admits only verified links.

Verification result:

- `outcome` verified, `reason` `ok` and `assurance` `issuer_signature_only` go together; a rejection has assurance `none` (`verification_result_inconsistent`). "Verified" means an issuer signature under the operator trust snapshot at the evaluation time and nothing more.
- When the envelope is carried, `statement_digest` is the BitRep digest of its statement: `sha256:` plus SHA-256 of `"BitRep attestation v1\n"` followed by the sorted compact ASCII JSON of the twelve statement fields (`statement_digest_mismatch`).
- `result_version` is `bitrep-verification/1`; any other version is a `schema_violation` (the Index refuses it).

Link outcome:

- 200 and 201 return the stored link and no reason; 401 carries `attestation_required`; 409 carries `attestation_id_conflict`; 503 carries `trust_unavailable`; 422 carries `malformed_attestation`, `attestation_binding_mismatch` or a verifier rejection reason (`outcome_status_reason_mismatch`). A refusal stores and returns no link (`outcome_link_mismatch`). A returned link follows the stored-link rules.

Epistemic status (derived view; the rules are the Index's own computation, `app/evidence/service.py`):

- `status` follows the weights: contradicting above supporting is `refuted` above 3.0 and `contested` otherwise; else supporting above 2.0 is `supported`; else `proposed` (`status_weights_mismatch`). `deprecated` is a claim lifecycle value the computation never produces and is not judged here.
- `robustness_score` is `min(total weight / 10, 1)`, or 0 without weight (`robustness_mismatch`).
- `independence_score` is `min(distinct source identifiers / 5, 1)`: a multiple of 0.2 below 1 (`independence_not_distinct_source_count`). Source identifiers are compared with whitespace collapsed and case folded, so five evidence records citing one source give 0.2 (issue #24). This counts identifiers. It does not establish independence of origin: copies of one publication under different identifiers still count as several sources (F-19 copied-evidence limit). Many issuers, wallets or records do not multiply evidential weight.

Chain attestation check (the chain profile's BitRep mapping; `chain/PROTOCOL.md`). Expected values come from chain data and local policy, never from the statement itself, and are reconstructed here in the adapter's order:

- The statement's `content_digest` equals the evidence content commitment (`chain_content_commitment_mismatch`).
- `subject` is the audience plus `:claim:` plus the 64 lowercase hex of the claim id without `0x` (`chain_subject_mismatch`).
- `statement_type` is `index-support/1` for relation 1 and `index-challenge/1` for relation 2 (`chain_statement_type_mismatch`).
- `audience` is `index:eip155:<chainId>:<lowercase contract address>:v1` (`chain_audience_mismatch`).
- `statement_digest` (the commitment the chain holds) is the BitRep digest of the statement (`statement_digest_mismatch`); statement times as above (`malformed_attestation`).
- Contract addresses are lowercase `0x` plus 40 hex, claim ids `0x` plus 64 hex, relations 1 or 2 only.

Chain inclusion is not current validity: a statement can stay on chain after it expires or its key is revoked, and the verification result is evaluated at the verifier's own time, never the block time.

## Rules that need the trust snapshot or the Index store (stated, not checkable from one document)

- Whether the signature verifies, whether the issuer and key are in the operator snapshot, key validity windows, revocation and the snapshot's currency (verifier reasons `unknown_key`, `key_revoked`, `invalid_signature`, `attestation_expired` and the rest). The validator checks the shape and the bindings; a flipped signature passes it (test `test_trust_dependent_rules_are_not_claimed_by_the_validator`).
- Idempotent resubmission (200 returns the existing link) and `attestation_id_conflict` (409): issuer plus attestation id against stored statement digests.
- That a stored link was admitted under the attestation it names; that evidence and claim ids exist (the Index does not check).
- The weights and source identifiers an epistemic status was computed from; whether a status is current.
- On chain: that the commitments equal the contract's logged values, finality and reorganisation handling, and `statementSHA256` zero meaning no statement.

## Consumer reliance

Read from `cognous-stack-qualification/suites/v1-scenarios/` (SCN-C03, SCN-C04) and `suites/v1-probes/`: the route's HTTP status and `detail.reason` (401, 409 `attestation_id_conflict`, 422 binding and verifier reasons, 503 `trust_unavailable`), 200 with the same link `id` for an exact resubmission, that a refused link is never stored and leaves `supporting_weight` unchanged, and the five epistemic fields `status`, `supporting_weight`, `contradicting_weight`, `independence_score`, `robustness_score` (the copied-evidence cases read `independence_score`). The same suites call the vendored verifier for `outcome`, `reason` and `assurance` (`issuer_signature_only` on success, `none` on rejection). The BitRep link profile (`docs/BITREP_LINK_ATTESTATION.md`) and the chain adapter rely on the binding and digest rules above. A consumer must not read `epistemic_status` or `verified` as a verdict. The rules above are what protect those reads; the qualification suites address the routes under the `/api/v1` prefix, which is deployment configuration and not part of this contract.

## Known producer non-conformance (found by running the Index producer paths against this draft, 2026-10-17)

Each item is a finding against the Index (P2/P3 work), not a fix:

- The submission model ignores undeclared members silently (pydantic default), so F-10 does not hold at the route: a request with `injected_member` or an `x-` member is accepted and the member is dropped. The stored link and the epistemic status have no `extensions` member either, so nothing round-trips.
- `strength` is coerced: the string `"0.9"` becomes 0.9 and `true` becomes 1.0, and the signed content digest then commits to the coerced float.
- `EvidenceService.create_link` accepts a link with no attestation and returns `attestation_id` null. The route never calls it that way, but the service is the stored-link producer; the contract refuses such a link (`link_without_attestation`).
- Body-level errors (both or neither target, strength above 1, unknown relation) are FastAPI request-validation 422s with a list `detail`, not the `{reason, message}` object the attestation refusals use, so the 422 reason set is not uniform. The route's own attestation refusals are conformant.
- `Link.timestamp` and `last_computed_at` are naive `datetime.utcnow()` values with no zone. The draft accepts a missing zone (IX-6).
- Independence counts distinct source identifiers only (F-19 limit above); claim-to-claim links add no weight at all. These are conformant with the draft but are limits a reader must not miss.

Conformant as exercised: attestation required (401), malformed envelope (422), every verifier rejection mapped to 422 with the verifier's reason, binding checks, 503 fail-closed without a trust snapshot, `verified` carrying `issuer_signature_only`, statement digest computation, link content digest, the epistemic computation, and the chain adapter's binding order. The chain adapter and the vendored verifier pin the same BitRep commit (5b5077d).

## Fixtures

Each fixture file is `{fixture_id, synthetic, expected_outcome, reason, [expected_refusal], document}`. `fixtures/valid/` must be accepted. `fixtures/invalid/` must be refused with `expected_refusal` as the only violation. Link submissions, verification results, link outcomes (except 409), stored links and epistemic statuses were captured by running the Index's own code (`verify_link_attestation`, the vendored `verify_attestation`, `EvidenceService.create_link`, `compute_epistemic_status`) with synthetic ids, a throwaway key and a fixed clock; stored link ids and timestamps were then normalised. The 409 outcome is written from the route code. The chain documents use synthetic bytes32 values (keccak is not computed) and statement digests from the vendored verifier. No fixture carries a real key, issuer or identifier.

## Run

```
python contracts/index-evidence-registry/validate.py <document.json>...   # prints violations; fixtures wrap the document
PYTHONPATH=src python -m pytest -q tests/test_contract_index_evidence_registry.py
```

`validate.py` is stdlib only. The test suite also cross-checks `schema.json` against the `jsonschema` package when it is installed.

## Conformance levels

Level S: `schema.json` valid. Level L: schema valid and every rule above holds. Level P: a consumer additionally preserves `extensions`. Unlike the exchange there is no digest that covers them, so level P here means preserved, not protected. A producer claims the level it tests; a consumer claims the level at which it refuses the invalid fixtures.

## Versioning and change rules (0.x)

While the version is `0.x-draft` nothing is frozen and any change may break. The freeze rules in the engineering document apply from `1.0.0`: patch for clarifications and added fixtures, minor for optional additions, major for required additions or semantic change, with a published deprecation window.

## Known gaps in this draft

- Producer-side conformance was exercised on pure code paths without a running FastAPI app (fastapi was not installed), so route status codes were captured from `verify_link_attestation` and read from the route source, not from HTTP responses.
- The claims, governance and evidence-submission routes and the legacy `api/` and `protocol/` layers are not modelled.
- On-chain records (claims, lifecycle, evidence submissions) are modelled only through the attestation binding, not as a reconstruction contract.
- The trust snapshot format (`bitrep-trust/1`) belongs to BitRep's contract and is not restated here.
- Honest limits carry over unchanged: conformance shows structure and the stated rules. It does not establish that a link or claim is true, that an issuer is legitimate, that evidence is independent or available, or that an attestation is still valid now.

## Input hardening (decision 32, 2026-10-18)

The reference validator never raises: any parsed JSON value gets a list of typed violations. Non-finite numbers (NaN, Infinity) and text that is not valid Unicode are refused as `schema_violation`; `main()` reads files with a strict loader (duplicate members, NaN, Infinity, overflowing numbers and non-UTF-8 input are refused, exit status 2, line `input_refused`); schema patterns match the whole string (`(?!\n)$` in `schema.json`) and times are ISO-8601 with ASCII digits and a UTC offset. No code, member or accepted form changed meaning; no code was added.

Invalid fixtures added: `trailing-line-break-digest`, `unpaired-surrogate-text`.
