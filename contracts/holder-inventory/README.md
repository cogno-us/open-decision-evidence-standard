# Holder inventory extension profile

Version: `0.1.0-draft`. Status: draft, proposal only, OPTIONAL extension profile. Not frozen (the first freeze is deferred by the owner), not part of the ODES core or `pder-v0.1`, not referenced by any `odes` code path, and not a qualification input. See `docs/engineering/ODES-INTERCOMPONENT-CONTRACTS.md` (Appendix C, section 12 item 27, sub-item 27-C) for the index and the decisions. Nothing here edits the journal contract, the verification-report contract, the witness-digest contract, the core schema or `pder-v0.1`.

## Contract statement

The Control Plane's opt-in holder inventory (`agent_control_plane.holder_inventory`, profile `holder-inventory/0.1`, N5, Control Plane main `128eaa5`, PR #49) is a host-written list of the holders of authority to cause an effect and where each one's authority is enforced. It is selected by the host-governed `RuntimeAuthorityProfile.holder_inventory` field together with the per-class flag `ActionClass.requires_revocation_assurance`: a flagged class holds (reason `holder_inventory_missing`) until the profile carries an inventory that enumerates at least one holder. The point of the hold is that the stack cannot show a revocation reached holders nobody listed. This contract is the shape of the inventory document, written down so the Control Plane, the verifier (tier V3, `--holder-inventory`) and any host that writes an inventory test against one set of fixtures instead of each other's code.

The document is the inventory object, as `HolderInventory.model_dump(mode="json")` writes it. It carries no contract marker beyond its own `version`. All members are required except `extensions`:

| Member | Type | Meaning |
|---|---|---|
| `version` | constant | `holder-inventory/0.1` |
| `inventory_id` | string, 1 to 256 characters | the inventory's id |
| `recorded_by` | string, 1 to 256 characters | who recorded it: an asserted name, not a signature (see Non-claims) |
| `recorded_at` | string, a time with a UTC offset | when it was recorded (default 4) |
| `holders` | list, at most 10000 | the enumerated holders; may be empty (it then claims nothing) |
| `extensions` | object, optional | `x-` names only; ignored by logic, preserved, part of the digest (default 3) |

A holder is a closed object, every member required except `extensions`:

| Member | Type | Meaning |
|---|---|---|
| `holder_id` | string, 1 to 256 characters | the holder |
| `kind` | `routed`, `self_credentialed` or `other` | `routed`: every effect passes the control plane's effect-time check. `self_credentialed`: the holder holds a credential for the destination itself and can act without passing the control plane. `other`: neither claim is made. A closed set; there is no lifecycle kind (no `expired`, `revoked`, `lapsed`) |
| `enforcement_point` | string, 1 to 256 characters | where the holder's authority is enforced |
| `credential_ref` | null or string, at most 256 | a reference, never a secret; null when unset (the producer always writes the member) |
| `extensions` | object, optional | as above |

Shapes were read from the code and checked against real output: `holder_inventory.py` (`AuthorityHolder`, `HolderInventory`, `inventory_defects`), the hold in `runtime_authority.py` (`requires_revocation_assurance` and `holder_inventory.exists()`), and three journal-mode runs of the bounded workflow (fixed clock) in which the same flagged class was run with an inventory of two holders (authorized and applied), with an inventory that enumerates none (held with `holder_inventory_missing`) and with no inventory (held with `holder_inventory_missing`). The two inventory documents the runs carried are the first two valid fixtures, unchanged, with each run's decision as `context`.

## Non-claims

- An inventory is a claim by whoever wrote it. The stack cannot check it for completeness: a holder nobody enumerated stays invisible to every probe, so the inventory is the control and this contract cannot check it. A conforming inventory is not a complete inventory.
- Listing a holder does not show it is the only route to an effect, that its `kind` is true (nothing here checks that a `routed` holder really passes the effect-time check or that a `self_credentialed` one really cannot be stopped), or that its `enforcement_point` exists.
- `recorded_by` is an asserted name. The document has no signer and no proof; it is trusted by who handed it over, not by cryptography.
- `credential_ref` is a reference. This contract does not resolve it, check it, or carry a secret: no member could hold one.
- Nothing here shows a revocation reached any holder. An authorized decision under a flagged class shows only that an inventory enumerating a holder existed; a held decision shows the stack declined to proceed, not that anything was revoked. The probe that reports holders (`classify_holders`) calls a holder with no refusal `coverage_unknown` and never expired, revoked, lapsed or inactive; this contract's `kind` set carries no such word either.
- The run record does not carry the inventory (it is a member of the runtime-authority profile, which the record does not retain; the profile commitment is not the profile). A held decision carries only the reason code `holder_inventory_missing`. So a verifier handed an inventory and a record cannot tie a held row to that inventory, and this contract has no rule that does.
- An inventory that enumerates no holder is valid in shape and claims nothing.

## Rules

Structure (`schema.json` is the source of truth): `undeclared_member` (a member neither declared nor in `extensions`, on the inventory or on a holder), `invalid_extension_key` (an `extensions` name not matching `^x-[a-z0-9][a-z0-9._-]*$`), `unknown_enum_value` (a `kind` outside the three), `unsupported_contract_version` (`version` is another string: this validator implements `holder-inventory/0.1` only), `schema_violation` (anything else: wrong type, a missing member, an empty or over-long string, more than 10000 holders, a document that is not an object).

Document rule: `timestamp_invalid` (`recorded_at` is not an ISO-8601 time with a UTC offset; stricter than the producer, default 4).

Behaviour helpers (not violations): `enumerates_a_holder(inventory)` is the profile's `exists()`; `class_holds(inventory, requires_revocation_assurance)` returns `["holder_inventory_missing"]` when the class is flagged and the inventory is absent or enumerates no holder, otherwise `[]` (an unflagged class is never held by an inventory). The captured runs pin both: the `context` of each valid fixture that has one is that run's decision, and the helper reproduces its reasons.

## Not checked here

- Completeness, truth, or sole-route claims (see Non-claims). Who the inventory is for or which action classes it covers: the flag is per action class in the profile, not in this document.
- That `holder_id`s are unique. The profile defines no such rule and the Control Plane accepts a repeated id (a valid fixture pins this); the verifier does not check it.
- That the inventory is the one in force in a run (the record does not say), or that the approval commitment covers it. The Control Plane's profile commitment covers the inventory once set, so a changed inventory without re-approval is refused by the Control Plane with `runtime_authority_approval_mismatch`; that is Control Plane behaviour (its `tests/test_holder_inventory.py`, run on 2026-10-18 and passing), not a rule of this document.
- The `classify_holders` report (`witnessed_refusals` and `unenumerated_authority_needing_containment`): an in-process return value that no component writes to a file, so it is not a boundary document and has no contract here (default 8).

## Fixtures

Each fixture file is `{fixture_id, synthetic, expected_outcome, reason, expected_refusal, provenance, document}`, plus an optional `context` (a captured run's decision: `class_requires_revocation_assurance`, `result`, `reasons`). `fixtures/valid/` must be accepted. `fixtures/invalid/` must be refused with `expected_refusal` as the only violation.

Valid (6): two are producer outputs unchanged (the inventory of two holders and the inventory of none, each with its run's decision), four are DERIVED from the first and say so (a credential reference, a holder of kind `other`, a repeated holder id, `x-` members). Invalid (18) are single-defect mutations. All data is synthetic (test helpers, fixed clock). `provenance/build_fixtures.py` regenerates and checks them from the capture of `contracts/witness-digest/provenance/capture_fixtures.py` (one capture serves both drafts); `provenance/differential_with_control_plane.py` is the check against the Control Plane's model. Neither is a test and neither is vendored.

## Run

```
python contracts/holder-inventory/validate.py <fixture-or-document.json>...
PYTHONPATH=src python -m pytest -q tests/test_contract_holder_inventory.py
```

`validate.py` is stdlib only. The test suite also cross-checks `schema.json` against the `jsonschema` package when it is installed.

## What this does and does not show

A passing run shows that an inventory has the closed shape the Control Plane writes and the verifier reads, and that its kinds are from the closed set. It does not show the inventory is complete, true, signed, or in force, and it shows nothing about whether any revocation reached any holder.

## Divergences

Checked on 2026-10-18 by running the Control Plane's `HolderInventory` model (main `128eaa5`, `provenance/differential_with_control_plane.py`) and the verifier's `inventory_document_check` (main `05afab8`) over every fixture. Both producer captures conform; 0 unexpected differences from the model.

- Control Plane, `extensions`: the model forbids extra members everywhere, so the `x-` fixture is valid here and refused there. `extensions` is the ODES convention (default 3); drop it here if the owner prefers (reversible). The verifier also refuses it (`undeclared_member`).
- Control Plane, required members: the model defaults `credential_ref` (null) and `holders` (empty), so it accepts an inventory without them. The producer always writes both, so they are required here (default 5). The verifier requires `holders` and accepts a missing `credential_ref`.
- Control Plane and verifier, `recorded_at`: both accept any non-empty string; this contract requires a time with an offset (default 4). The verifier confirms the two invalid time fixtures.
- Control Plane, `version`: the model checks it as a literal; here a different string is `unsupported_contract_version` and a non-string is `schema_violation`. The verifier reports both as `holder_inventory_shape`.
- Verifier, codes: the verifier's finding names differ (`holder_inventory_shape` for every shape defect, `undeclared_member`, `unknown_enum_value`); outcomes agree on the other 15 invalid fixtures (it refuses all but the three it confirms). The verifier reports an inventory that enumerates no holder as `could_not_check` (`inventory_enumerates_no_holder`), where this contract calls it valid in shape and the helper says it claims nothing.

## Defaults taken (questions not asked, owner review at the end; every one is reversible while the contract is `0.1.0-draft`)

1. The document is the inventory object unchanged, with no contract marker: the Control Plane's model is closed and the verifier's reader is closed, so a marker would refuse every producer output. `version` is the marker.
2. The closed members are exactly the Control Plane's: five on the inventory, four on a holder. No member is added for a signer, a secret, a completeness claim, the action classes covered or a lifecycle state.
3. `extensions` is an object with `x-` names on the inventory and on a holder (ODES convention, ignored by logic, preserved, part of the digest). The producer emits none (see Divergences).
4. `recorded_at` must be a time with a UTC offset (`timestamp_invalid`), as everywhere in ODES; the producer takes any non-empty string (stricter than the producer).
5. `credential_ref` and `holders` are required, `credential_ref` nullable, because the producer always writes them; the model's defaults would accept their absence.
6. `kind` is a closed set of three (`unknown_enum_value`); a new kind is a major bump.
7. String lengths follow the model (1 to 256; `credential_ref` at most 256; at most 10000 holders).
8. The `classify_holders` report is not a document of this contract (see Not checked here); a contract for it is possible if a component starts to write it.
9. No uniqueness rule on `holder_id` (the profile has none).
10. `enumerates_a_holder` and `class_holds` are helpers that restate the profile's hold, because the hold is the profile's one behaviour; they are not document rules and read no run record.

## Versioning and change rules (0.x)

While the version is `0.x-draft` nothing is frozen and any change may break. Enumerations, when added, are closed (decision 6).

## Current conformance (2026-10-18, local runs, not a qualification)

- Producer: the Control Plane's inventory documents (as dumped by `HolderInventory`) at `128eaa5` conform unchanged; the flagged class's hold behaviour matches `class_holds` on all three captured runs.
- Consumer: the verifier's `v3.holder-inventory.document` (main `05afab8`) agrees on every fixture except those listed under Divergences.
