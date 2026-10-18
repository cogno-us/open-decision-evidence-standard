# Witness digest extension profile

Version: `0.1.0-draft`. Status: draft, proposal only, OPTIONAL extension profile. Not frozen (the first freeze is deferred by the owner), not part of the ODES core or `pder-v0.1`, not referenced by any `odes` code path, and not a qualification input. See `docs/engineering/ODES-INTERCOMPONENT-CONTRACTS.md` (Appendix C, section 12 item 27, sub-item 27-B) for the index and the decisions. Nothing here edits the journal contract, the verification-report contract, the core schema or `pder-v0.1`.

## Contract statement

The Control Plane's opt-in witness (`agent_control_plane.witness`, profile `witness-digest/0.1`, N5, Control Plane main `128eaa5`, PR #49) lets a party other than the holder of the record-store key keep a short chain of digests of the run record's ledgers. A reader who holds that chain can tell afterwards that a covered row was dropped or rewritten, even if the key holder re-signed or re-sealed the record set. Until this draft the shape of what the witness holds lived only in the Control Plane code and, as a second implementation, in the verifier's tier V3 (`cognous_verify/witness.py`). This contract is that shape, and the rules a witness file and a run record must satisfy together, written down so the Control Plane, the verifier and any witness holder test against one set of fixtures instead of each other's code.

The document is the file a witness holds: a JSON array of records, oldest first. On the wire it is JSON lines (one record per line, written by `acp witness publish` as sorted compact JSON); the array is that file read in order. The document carries no contract marker of its own: each record names its profile in `version`.

A record is a closed object, every member required except `extensions`:

| Member | Type | Meaning |
|---|---|---|
| `version` | constant | `witness-digest/0.1` |
| `run_id` | string, non-empty | the run the record covers (the run record's `run_id`) |
| `sequence` | integer, at least 0 | the record's index in the witness's own chain |
| `previous_digest` | null or digest | the `digest` of the record before it; null for the first |
| `ledgers` | object | ledger name to `{count, head}` |
| `digest` | digest | the commitment of the record without its `digest` member |
| `extensions` | object, optional | `x-` names only; ignored by logic, preserved, covered by `digest` (default 3) |

A ledger is every list-valued top-level member of the run record document, rows in stored order (`input_time_floors` and `run_id` are not lists and are not covered). A ledger entry is exactly `count` (rows covered, at least 1: empty ledgers are omitted) and `head`. The head is the end of a hash chain: `heads[0]` is `sha256:` plus 64 zeros and `heads[i+1] = commitment({"prev": heads[i], "row": commitment(row_i)})`; a ledger head covers exactly its first `count` rows, so appending rows later keeps the head of the covered prefix valid. `commitment` is the Control Plane's: SHA-256 over sorted compact UTF-8 JSON, `ensure_ascii` off, NaN refused, `sha256:` plus lowercase hex (the same form as the verification-report contract's pinned profile). A digest is `sha256:` plus 64 lowercase hex.

Shapes were read from the code and checked against real output, not proposed: `witness.py` (`make_record`, `head_digest`, `check_witness_chain`, `verify_against_witness`, `publish_head`, the `witness` subcommands of `acp`), and the files `acp witness publish` and `publish_head` wrote over run records the Control Plane wrote. The valid fixtures are those unchanged outputs, and `validate.py` reproduces the single-record captures byte for byte (`make_record`).

## Non-claims

- A witness that matches the record shows that the records match what the witness was given. It does not show that the witness was published anywhere, that it was published in time, or that any party independent of the record keeper held it. The code writes a local file; a signed tag in the hub repository is the owner's default for a real location and is a deployment step nobody has taken (the module makes no network call and creates no tag).
- Whoever controls the witness can withhold, replace or back-date a digest, and a reader with no independent copy cannot tell. A witness file supplied by the party that supplied the records vouches for nothing that party could rewrite: a record and a witness rewritten together to agree validate (a test pins it).
- A record carries no signer and no proof. There is no member that names who published it and no keyed proof of it. Who wrote the file is an asserted name outside the document (a file path, a repository, a person); this contract cannot check it. A member that looks like a signer or a proof is `undeclared_member`, never read as one, and an `x-` extension is never one either. A keyed proof would be a new profile version.
- Rows appended after the latest digest are not covered. They are reported by `coverage` as unwitnessed, never as intact and never as a violation.
- Only list-valued ledgers are covered. Top-level scalars and mutable dictionaries (`run_id`, `input_time_floors`) are not.
- Nothing here says a record's rows are true, complete, or that an effect occurred. A matching head shows the covered rows are the rows the digest was computed over, nothing more.
- The first record of a chain vouches for nothing before it: it is a baseline.

## Rules

Structure (`schema.json` is the source of truth): `undeclared_member` (a member neither declared nor in `extensions`; this is where a signer or proof member lands), `invalid_extension_key` (an `extensions` name not matching `^x-[a-z0-9][a-z0-9._-]*$`), `unsupported_contract_version` (a record whose `version` is another string: this validator implements `witness-digest/0.1` only), `schema_violation` (anything else: wrong type, a missing member, a count below 1, a malformed digest, a float where an integer is required, a document that is not an array).

File rules (the witness's own chain; the Control Plane's `check_witness_chain`, which reports every defect under `witness_chain_invalid`):

- `witness_holds_no_digest`: an empty file verifies nothing (the Control Plane's verdict code for the same condition).
- `witness_chain_invalid`: a record's `digest` does not recompute; `sequence` is not its index; `previous_digest` is not the previous record's `digest` (null for the first); `run_id` differs from the record before it; a ledger the record before it covered is missing or covers fewer rows. One violation per defect, the path names the record and member.

Record rules (optional second argument to `validate`, the run record document; the Control Plane's `verify_against_witness`). They run only when the file rules found nothing, as the Control Plane's verifier stops after a chain defect or a run mismatch:

- `witness_run_mismatch`: a record's `run_id` is not the run record's (a run record with no `run_id` mismatches).
- `witness_ledger_shrunk`: for a record and a ledger it covers, the run record holds fewer rows than `count` (a ledger that disappeared counts as emptied).
- `witness_ledger_head_mismatch`: the chain head over the first `count` rows differs from the held `head` (a covered row was rewritten, reordered, or dropped and replaced).

Every record in the file is checked, not only the latest. `coverage(records, run_record)` returns `witnessed_through` (ledger to rows the latest record covers) and `unwitnessed_rows` (ledger to rows the run record holds beyond that): information, not violations; it equals what `acp witness verify` prints for the same inputs (the fixtures that carry `expected_coverage` are the captured outputs).

## Not checked here

- That the file was published, when, or by whom (see Non-claims). That the witness location is outside the key holder's reach.
- That the run record is itself well formed (the journal contract), or that its rows are true.
- That `ledgers` names the ledgers the run record has: a record that names a ledger the run record lacks is `witness_ledger_shrunk`; a record that omits a ledger the run record has is simply not covering it (`coverage` reports it).
- The run record as a whole: top-level scalars and dictionaries are not covered.
- `sequence` continuing a chain across files: one file is one chain.

## Fixtures

Each fixture file is `{fixture_id, synthetic, expected_outcome, reason, expected_refusal, provenance, document}`, plus an optional `record` (the run record the witness covers, unchanged) and, on valid fixtures captured with `acp witness verify`, `expected_coverage`. `fixtures/valid/` must be accepted. `fixtures/invalid/` must be refused with `expected_refusal` as the only violation.

Valid (7): six are producer outputs unchanged (single-record witnesses published by `acp witness publish` over the stores of an authorized and a held `acp run`; a two-record witness published after the decision and again after execution; its first record against the finished record, so rows are unwitnessed; the same file alone, without a run record; a single record over a journal-mode run whose class requires revocation assurance); one is DERIVED from a capture (`x-` members on both records, chain re-computed) and says so. Invalid (31) are single-defect mutations of the valid ones: where a mutation changes a record's content the digests are re-computed so that exactly one rule is broken. All data is synthetic (test helpers, fixed clock, the repository's own `examples/acp_run`). The three scripts in `provenance/` regenerate and check everything and are not tests and are not vendored: `capture_fixtures.py` (runs the Control Plane at `128eaa5`; also captures the holder-inventory runs), `build_fixtures.py`, and `differential_with_control_plane.py` (see Divergences).

## Run

```
python contracts/witness-digest/validate.py <fixture-or-witness-file>... [--record <run-record.json>]
PYTHONPATH=src python -m pytest -q tests/test_contract_witness_digest.py
```

`validate.py` is stdlib only and reads a JSON array or a JSON-lines witness file. The test suite also cross-checks `schema.json` against the `jsonschema` package when it is installed.

## What this does and does not show

A passing run shows that a witness file has the closed shape the Control Plane writes, that its own chain is intact, and, with a run record, that every covered row is the row the digest was computed over. It does not show the witness was published, timely, independent, or signed, and it never says a record is intact beyond `witnessed_through`.

## Divergences

Checked on 2026-10-18 by running the Control Plane's own `verify_against_witness` and `check_witness_chain` (main `128eaa5`) over every fixture that carries one of its verdict codes (23 fixtures: every valid fixture, plus the file and record rule fixtures), `provenance/differential_with_control_plane.py`: same accept or refuse, same code, and equal `witnessed_through` and `unwitnessed_rows` on every valid fixture that carries them. 0 mismatches. The verifier's tier V3 (main `05afab8`) was run over the captured records: it confirmed all six witness checks on the complete captures, reported the first-publication capture's later rows as `could_not_check` (unwitnessed), and `v3.witness.ledger-heads` refused a record with a covered row removed (`witness_ledger_shrunk`). The verifier was not run over the invalid fixtures here.

- Control Plane, structure: the Control Plane's reader does not refuse extra members of a witness record, reads members with `get`, and takes a count of 0 (it only compares counts). This contract is closed and stricter on all of these; the producer's own output conforms.
- Control Plane, `extensions`: the producer emits none and nothing reads one. Admitting `extensions` is the ODES convention (default 3); the verifier refuses an extra member as `witness_record_shape`, so a record with `extensions` is valid here and refused there. If the owner prefers no extension namespace on a witness record, drop the member here (reversible).
- Verifier, counts: the verifier accepts a ledger entry with `count` 0; this contract requires at least 1 because the producer omits empty ledgers (default 5).
- Verifier, empty file and missing run id: the verifier reports an empty witness file and a record with no `run_id` as `could_not_check`; this contract refuses them (`witness_holds_no_digest`, `witness_run_mismatch`, the Control Plane's verdicts). The verifier's choice is the safer one for a report (not a refusal of an input it was not asked to judge); the contract states the document rule.
- Verifier, codes: the verifier uses the Control Plane's codes `witness_chain_invalid`, `witness_run_mismatch`, `witness_ledger_shrunk`, `witness_ledger_head_mismatch` and its own `witness_record_shape` and `witness_version_unsupported` for shape and version (here `schema_violation`, `undeclared_member`, `unsupported_contract_version`). Outcomes agree; the shape codes differ by name.
- Owner's brief and the code: the instruction for this draft described the signer as an asserted name unless a keyed proof is carried. The code carries neither a signer nor a proof (the record has six members), so the contract has no signer member and says so in the non-claims; the asserted name, if any, lives outside the record. The code wins.

## Defaults taken (questions not asked, owner review at the end; every one is reversible while the contract is `0.1.0-draft`)

1. The document is the witness file as a JSON array of records, oldest first (the JSON-lines file read in order). No wrapper member, no `contract` or `contract_version`: the wire form has none and a marker would make every producer file refused. The record's `version` is the marker. Reversible: add a wrapper (a producer change).
2. The closed record members are exactly the six `make_record` writes. No signer, proof, timestamp, publisher or location member is added: the producer emits none (see Divergences).
3. `extensions` is an object with `x-` names on a record and on a ledger entry (ODES convention, ignored by logic, preserved, covered by `digest`; a name without `x-` is `invalid_extension_key`). The producer emits none; the verifier refuses them (see Divergences).
4. `unsupported_contract_version` for a record whose `version` is another string, matching the other drafts; a non-string `version` is `schema_violation`.
5. `count` is at least 1: the producer omits empty ledgers, so a count of 0 is not something it writes (the verifier is looser).
6. Ledger names are plain non-empty strings, not an enumeration: they are the list-valued members of whatever run record is witnessed, which this contract does not own.
7. Digest strings are `sha256:` plus 64 lowercase hex, as the Control Plane writes them.
8. File defects use the Control Plane's single code `witness_chain_invalid`, one violation per defect with the record index and member in the path, rather than a code per defect; the verifier does the same. Reversible: split into codes.
9. The record rules run only when the file rules found nothing (the Control Plane's order), and check every record, not only the latest.
10. `coverage` is a function, not a violation: unwitnessed rows are information (the Control Plane's `unwitnessed_rows`). A run record with rows after the latest digest is valid.
11. An empty file is refused (`witness_holds_no_digest`), as the Control Plane's verdict: a witness that holds nothing verifies nothing.
12. A run record with no `run_id` is `witness_run_mismatch`, as in the Control Plane (the verifier's `could_not_check` is a report outcome, not a document rule).
13. Only the ledger and chain rules are in the contract. The Control Plane's `acp witness verify` output (`ok`, `reasons`, `findings`, `witnessed_through`, `unwitnessed_rows`, `published_records`, `scope`) and the `publish` output (`published`, `sequence`) are CLI output, not documents a component reads; `coverage` restates the two figures the verdict carries. A contract for the verdict is possible if a component starts to consume it.
14. The `Witness` protocol (`publish`, `latest`, optional `history`) and `LocalFileWitness` (append-only file with an advisory lock) are an interface and an implementation, not a document; they are not in this contract. Where a real witness is held is a deployment decision.
15. The run record's `run_id` is the join key between a witness and a record; a record without one cannot be witnessed (the Control Plane raises in `make_record`).

## Versioning and change rules (0.x)

While the version is `0.x-draft` nothing is frozen and any change may break. Enumerations, when added, are closed (decision 6). A keyed proof, a signer member, a second hash profile or a wider ledger definition is a new profile version, not an extension.

## Current conformance (2026-10-18, local runs, not a qualification)

- Producer: the Control Plane's witness output (`acp witness publish`, `publish_head`) at `128eaa5` conforms unchanged; the differential above passes.
- Consumer: the verifier's tier V3 (main `05afab8`) implements these rules from the profile text and agrees on the captured records. It reports in an extension today and moves into `checks` under the 2026-10-18 verification-report revision (decision 27-A).

## Input hardening (decision 32, 2026-10-18)

The reference validator never raises: any parsed JSON value gets a list of typed violations. Non-finite numbers (NaN, Infinity) and text that is not valid Unicode are refused as `schema_violation`; `main()` reads files with a strict loader (duplicate members, NaN, Infinity, overflowing numbers and non-UTF-8 input are refused, exit status 2, line `input_refused`); schema patterns match the whole string (`(?!\n)$` in `schema.json`) and times are ISO-8601 with ASCII digits and a UTC offset. No code, member or accepted form changed meaning; no code was added.

Invalid fixtures added: `trailing-line-break-digest`, `unpaired-surrogate-text`.
