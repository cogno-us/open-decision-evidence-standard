# Destination ledger extension profile

Version: `0.1.0-draft`. Status: draft, proposal only, OPTIONAL extension profile. Not frozen (the first freeze is deferred by the owner), not part of the ODES core or `pder-v0.1`, not referenced by any `odes` code path, and not a qualification input. See `docs/engineering/ODES-INTERCOMPONENT-CONTRACTS.md` (Appendix C, section 12 items 25 and 26) for the index and the decisions. Nothing here edits the journal contract, the lifecycle contract, the verification-report contract, the core schema or `pder-v0.1`.

## Contract statement

The independent verifier (`cogno-us/cognous-open-control-stack-verifier`, tier V4) reads one effect-side record: the destination ledger. Until this draft the shape of that ledger lived only in the verifier (`src/cognous_verify/ledger.py`, `ROW_MEMBERS`, finding `ledger_shape`; `docs/tiers.md`). This contract is the closed shape, written down so the verifier, the Control Plane and the orchestrator can test it against one set of fixtures instead of each other's code.

A ledger export is a JSON object with two required members and one optional member:

| Member | Type | Meaning |
|---|---|---|
| `effects` | object | effect id to ledger row. A row is keyed by its own `effect_id`. |
| `grant_effect_counts` | object | grant id to a non-negative integer: the number of rows for that grant. |
| `operations` | object, optional | operation id to effect id (present only when a destination was driven with an operation id, `operation-identity/0.1`). |
| `extensions` | object, optional | `x-` names only; ignored by logic, preserved, part of the digest input (default 3). |

A row is a closed object:

| Member | Type |
|---|---|
| `effect_id`, `grant_id`, `target`, `unit`, `state` | string |
| `amount` | number (not a boolean) |
| `payload` | object |
| `operation_digest` | string, OPTIONAL; documented default `sha256:` plus 64 lowercase hex (defaults 4 and 5) |
| `extensions` | object, optional (`x-` names only) |

Shapes were read from the code, not from a proposal: the verifier's `ROW_MEMBERS` and `shape()` (main `5ed1ffb`); the Control Plane's `LocalRefundDestination` (`src/agent_control_plane/bounded.py`, main `128eaa5`), whose `destination.json` is what `acp run` writes; and the orchestrator's projection of the runtime SQLite effect rows (`tests/overlay/test_overlay_verifier.py`, `ledger_projection`; programme-2 gap report F-1 and F-2, orchestrator `ad79749`, runtime `d90a2ca`). The valid fixtures are those producers' unchanged outputs.

## Non-claims

- A row shows what a destination recorded as its effect. It does not show that the effect really happened in the world, that the destination is honest, or that the amount, target or unit are right.
- A conforming ledger is not a complete ledger. It has no sequence number, no chain and no signature; a dropped tail, a consistent rewrite, or a decision that never reached the ledger cannot be seen from the document. It is trusted by deployment, not by cryptography.
- A conforming ledger does not show that any effect was authorized. Whether a row has an authorized decision, whether the row matches the decision's binding, and whether it agrees with an attempt are the verifier's V4 checks over a run record, not rules of this contract.
- `operation_digest` is a recorded value. This contract does not recompute it and does not show it names the operation the destination actually ran.
- Two rows for one business operation are valid here (the legacy renewal race); detecting that is the operation-identity profile's concern, and only when its sidecar exists.
- A count written `1.0` is a float, not an integer (the verifier's strict parse keeps the form and refuses it), and the reference validator refuses it; a generic JSON Schema validator reads `1.0` as an integer and cannot see the difference, so `schema.json` alone is not enough for that case (the test suite pins it).
- Number form is not normalised here: `50` and `50.0` are both numbers to this contract. The verifier's commitments treat them differently (an integer written where a float was changes the canonical bytes), so a consumer that compares by commitment must keep the producer's form.

## Rules

Structure (`schema.json` is the source of truth): `undeclared_member` (a member neither declared nor in `extensions`), `invalid_extension_key` (an `extensions` name not matching `^x-[a-z0-9][a-z0-9._-]*$`), `schema_violation` (anything else: wrong type, missing required member, count negative or not an integer, malformed `operation_digest`).

Document rules (one export):

- `ledger_key_mismatch`: a row is keyed by its own `effect_id` (same finding as the verifier's `v4.ledger.keys`).
- `ledger_count_mismatch`: for every grant named by a row or by `grant_effect_counts`, the count equals the number of rows for it; an absent count is read as 0 (same finding as the verifier's `v4.ledger.counts`).

Observation cross-check (optional second argument to `validate`, a run record or a list of accepted reconciliations, decision 25-A):

- `operation_digest_mismatch`: if a row and an accepted observation's `destination_state` for the same effect both carry `operation_digest`, they must be equal. If only one carries it, nothing is compared. An observation that is not accepted, or whose `destination_state` is empty (an `absent` observation), is not read. The verifier may enforce this inside `v4.ledger.observations-agree`; it is reported once per row.

## Not checked here

- Anything about a decision, attempt, grant, binding or acknowledgement: a ledger is validated alone, or against observed destination states only.
- That an `operations` value names a row in `effects` (the Control Plane writes it that way; the verifier does not read it; not a rule here).
- That `state` is `applied` or `partial` (default 6).
- That the digest was computed over the operation (default 5).

## Fixtures

Each fixture file is `{fixture_id, synthetic, expected_outcome, reason, expected_refusal, provenance, document}`, plus an optional `observations` member (the accepted reconciliations of the run record, unchanged) for the cross-check. `fixtures/valid/` must be accepted. `fixtures/invalid/` must be refused with `expected_refusal` as the only violation.

Valid (13): 9 are producer outputs unchanged (Control Plane `acp run` authorized and held; `LocalRefundDestination` partial and with an `operations` member; the orchestrator's projections A and B for the applied, held and renewal-race scenarios; the atomic-route projection), 2 pair a captured ledger with captured observations, and 2 are derived from captured ledgers (a row mix without the digest, an `extensions` member), each marked in its `reason`. All data is synthetic; the two `LocalRefundDestination` captures use placeholder effect ids. Invalid (48): 46 single-defect mutations of the valid ones, plus the two added by decision 32 (`trailing-line-break-digest`, `unpaired-surrogate-text`). `provenance/capture_fixtures.py` and `provenance/build_fixtures.py` regenerate everything and assert each outcome; they are not tests and are not vendored.

## Run

```
python contracts/destination-ledger/validate.py <fixture-or-document.json>...
PYTHONPATH=src python -m pytest -q tests/test_contract_destination_ledger.py
```

`validate.py` is stdlib only. The test suite also cross-checks `schema.json` against the `jsonschema` package when it is installed.

## What this does and does not show

A passing run shows that a ledger export has the closed shape the verifier reads, is internally consistent (keys, counts) and carries no malformed digest. It does not show that the ledger is true, complete, or that any effect it records happened.

## Divergences

Checked on 2026-10-18 by running the verifier's own `ledger.shape()` (main `5ed1ffb`) over every fixture. The three verifier bullets below record that first check and are superseded by the update that follows them:

- Verifier, `operation_digest`: the verifier's row is still closed without the member, so it refuses the valid fixtures whose rows carry it (`ledger_shape`, "undeclared member"; gap report F-1, projection B). Decision 25-A already says the verifier owner changes the shape. This is the divergence this contract records; it is the same member, the same type.
- Verifier, `extensions`: the verifier has no `extensions` member at either level and refuses the `extension-namespace-members-preserved` fixture. Default 3 is the ODES convention; if the verifier owner prefers no extension namespace on a ledger export, drop the member here instead (reversible).
- Verifier, digest format: the verifier will accept any string once it declares the member; this contract constrains it to the format the runtime emits (default 4). Rows with another string would be valid to the verifier and refused here.
- Verifier, `state`: both accept any string in shape. The verifier reports an unknown state only for a row with an authorized decision (`ledger_row_state_unknown`).
- Update 2026-10-18 (docs only, after programme 2): at verifier `f99a6543` (`src/cognous_verify/ledger.py`) the row declares `operation_digest` (`sha256:` plus 64 lowercase hex, the format this contract constrains) and `extensions` (`x-` names), at the document and row level, and `v4.ledger.observations-agree` reports `operation_digest_mismatch`. Running that revision's `ledger.shape()` over the 13 valid fixtures gave 0 findings. The first three verifier bullets (operation_digest, extensions, digest format) no longer describe a divergence; `state` stays a plain string on both sides. The verifier carries its own copy of the shape; it does not import this contract.
- Control Plane: none. `acp run` and `LocalRefundDestination` outputs conform unchanged (verifier shape: 0 findings on all producer outputs without `operation_digest`).
- Orchestrator: projection A conforms; projection B conforms here and is refused by the verifier only for `operation_digest`.
- Runtime: its SQLite `effects` table carries `operation_digest`; the orchestrator's projection decodes `payload_json` to the `payload` object. No runtime code emits this JSON export; the projection is the orchestrator's.

## Defaults taken (questions not asked, owner review at the end; every one is reversible while the contract is `0.1.0-draft`)

1. The document is the verifier's export unchanged: no `contract`, `contract_version` or `profile` member, because the verifier's top-level member set is closed and a marker would make every producer output refused. The contract is identified by where it is used. Reversible: add a marker (a verifier change too).
2. The closed row members are exactly the verifier's seven plus the optional `operation_digest`. No member is added for fields the runtime SQLite row has but the verifier's row does not (`decision_id`, `payload_json`, attempt data).
3. `extensions` is an object with `x-` names at the document level and in each row (ODES convention, ignored by logic, preserved and digested, a name without `x-` is `invalid_extension_key`). The verifier has none today (see Divergences).
4. `operation_digest` is an optional string (decision 25-A). An absent row stays valid and a default record stays byte-identical. An explicit `null` is not an absent member and is refused.
5. The digest format is constrained to `^sha256:[0-9a-f]{64}$`. Evidence: every value the runtime emits is `"sha256:" + hashlib.sha256(...).hexdigest()` (`engine/safe_executor.py` `commitment`; the orchestrator's `refund_runtime._operation_digest`), and the real values in the fixtures all match. It is a documented default, not a design requirement: relax to a plain string if another producer needs it (the lifecycle contract types the same member as an unconstrained string).
6. `state` is a plain string, as in the verifier. `applied` and `partial` are the only values the producers emit; an enumeration would be stricter than the verifier's shape, so none is declared. A closed enumeration is a candidate once the verifier agrees.
7. `amount` is a number and not a boolean; no range, no finiteness rule beyond what JSON can carry.
8. `grant_effect_counts` is required, even when empty, as in the verifier.
9. The key and count rules (`ledger_key_mismatch`, `ledger_count_mismatch`) are included because they are properties of one export and both producers satisfy them; they carry the verifier's own finding names so a consumer can map them.
10. The `operation_digest` cross-check is an optional second argument, not a document member, because the observation is not part of the ledger. Only accepted observations are read.
11. `operations` values are strings and nothing more (see Not checked here).

## Versioning and change rules (0.x)

While the version is `0.x-draft` nothing is frozen and any change may break. Enumerations, when added, are closed (decision 6).

## Current conformance (2026-10-18, local runs, not a qualification)

- Producers: the Control Plane's `acp run` ledgers and `LocalRefundDestination` snapshots, and the orchestrator's projections A and B, pass this validator unchanged.
- Consumer: at verifier `f99a6543` the verifier accepts rows with `operation_digest` and `extensions` and its own `ledger.shape()` accepts all 13 valid fixtures (see the update under Divergences); it keeps its own copy of the shape. At the earlier check (`5ed1ffb`) it refused both.

## Input hardening (decision 32, 2026-10-18)

The reference validator never raises: any parsed JSON value gets a list of typed violations. Non-finite numbers (NaN, Infinity) and text that is not valid Unicode are refused as `schema_violation`; `main()` reads files with a strict loader (duplicate members, NaN, Infinity, overflowing numbers and non-UTF-8 input are refused, exit status 2, line `input_refused`); schema patterns match the whole string (`(?!\n)$` in `schema.json`) and times are ISO-8601 with ASCII digits and a UTC offset. No code, member or accepted form changed meaning; no code was added.

Invalid fixtures added: `trailing-line-break-digest`, `unpaired-surrogate-text`.
