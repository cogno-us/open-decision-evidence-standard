# Non-broadening delegation contract (optional ODES extension profile)

Version: `0.1.0-draft`. Status: draft, proposal only, OPTIONAL extension profile. Not frozen (the first freeze is deferred by the owner), not part of the ODES core or `pder-v0.1`, not referenced by any `odes` code path, and not a qualification input. See `docs/engineering/ODES-INTERCOMPONENT-CONTRACTS.md` (Appendix C, decision 20) for the index and the decisions.

## Current behaviour (read this first)

Today the Control Plane does NOT support delegation. In `BoundedAuthorizationWorkflow` (`src/agent_control_plane/bounded.py`, Control Plane main `5f5ae03`) any grant whose `delegation.parent_grant_id` is set is refused with `delegation_profile_unsupported` (and `delegation_chain_missing` when the identity carries no chain). The comment there says no ancestor revocation walk or shared ancestor budget exists. Nothing in the stack checks a delegated grant against its parent. This contract defines the profile that would REPLACE that refusal; it describes no current behaviour, and no component implements it. Adopting it is a behaviour change that must be opt-in (a new profile or flag), so the pinned default path stays unchanged.

The delegation scenario in the catalog is C18 (D03 is "Authority changes", not delegation).

## Contract statement

A delegated grant is a subset of its parent in amount, time window and scope. A conforming document carries the grants of one delegation tree and the delegation record of each, so a consumer can check every parent/child edge from the document alone.

- Producer: whatever issues grants (in the stack, the Authority Context input to the Control Plane; see `src/agent_control_plane/bounded.py` grant shape and the Governed Exchange reference `experiments/odex_gax_imx_reference/gax_ref.py`).
- Consumers: the Control Plane resolution step (in place of the refusal), Replay and the Evidence pack when they retain the grants.
- Layering: this contract layers on the grant shape by reference and edits none of the existing contracts. It does not alter `control-plane-journal` (which carries grants only as minimized `resolution_input` rows) or any core ODES file.

## Document model

`contract: "non-broadening-delegation"`, `contract_version: "0.1.0-draft"`, `profile: "non-broadening-delegation/0.1"`, `grants` (non-empty list), optional `extensions`. A grant carries `grant_id`, `revision`, `issuer`, `grantee`, `not_before`, `expires_at`, `permissions` (non-empty; each with `action`, `targets`, `data_scopes`, `max_amount`, `unit`, `max_effects`) and `delegation` (`parent_grant_id` or null, `may_delegate`, `remaining_depth`). The permission and delegation members are exactly those of the Control Plane grant.

## Member model

Same model as the other drafts. Declared required members must be present. Every declared object is closed: a member neither declared nor inside `extensions` is `undeclared_member`, never dropped. `extensions` accepts `x-` names (`invalid_extension_key` otherwise); consumers ignore them for contract logic, preserve them and include them in any digest. Types, required members and the version are structural (`schema_violation`, `unsupported_contract_version`).

## Rules

For a grant with `parent_grant_id` set (edge child -> parent):

- The parent is in the document (`parent_missing`). Parent references never form a cycle, a self-reference included (`delegation_cycle`, reported once per cycle; the edge rules below are skipped inside a cycle).
- Window: `not_before` is not earlier and `expires_at` not later than the parent's (`window_extended`). Times are timezone-aware (`timestamp_invalid`); `not_before` is earlier than `expires_at` (`window_invalid`).
- Scope, unit, amount: every child permission fits inside ONE parent permission with the same `action`, `targets` and `data_scopes` as subsets, the same `unit`, `max_amount` not above, `max_effects` not above. The most specific code is reported: `scope_widened` (action, a target or a data scope the parent lacks), `unit_changed`, `amount_broadened`, `effects_broadened`.
- Depth: the parent must allow delegation (`may_delegate` true and `remaining_depth` at least 1, else `depth_exhausted`); the child's `remaining_depth` is at most the parent's minus one (`depth_not_decreased`). In every grant `may_delegate` is true if and only if `remaining_depth` is above zero (`delegation_flags_inconsistent`).
- Delegator: the child's `issuer` is the parent's `grantee` (`delegator_mismatch`).
- Grant ids are unique (`duplicate_grant_id`).

Subset means "not above", not "strictly below": a child equal to its parent in every bound conforms.

## Not checked here

- Status. Whether a parent is active, revoked or stale is a status-resolver fact and not in the document. The current code has no ancestor revocation walk; this contract does not add one (question 8).
- Aggregate budget across siblings or over time (question 4). `max_effects` and `max_amount` are per grant, as in `_matching_permission`.
- Signatures and the identity `chain` (`delegation_chain_missing` remains the Control Plane's own check).

## Entry conditions for enabling delegation

Delegation stays refused (`delegation_profile_unsupported`) until all of the following hold. They are conditions on a future opt-in implementation, not behaviour of any component today, and they do not change this document's rules.

- (a) Delegator binding. The child grant is bound to its delegator over the exact child grant, and the binding is checked at acceptance, not only at issuance.
- (b) Ancestor status walk. At decision time every ancestor's status is read and a non-active ancestor refuses the decision with its own refusal code. Status is not part of this document (see "Not checked here"), so the walk is a Control Plane responsibility.
- (c) Unendorsed-parent fixture. A producer fixture in which the child names a real parent that never endorsed it, and is refused.

The same conditions are recorded in the Control Plane documentation (`docs/bounded_authorization_effect.md`, "Delegation entry conditions").

## Questions asked as defaults (owner asked not to be asked; each is reversible while the draft stays `0.1.0-draft`)

1. Parent reference by `grant_id` only, not `grant_id` plus revision. Default: id only (the control plane grant model has no parent revision). Reversible: add an optional `parent_grant_revision`.
2. Subset strict or non-strict? Default: non-strict (equal bounds allowed).
3. May a child permission draw on several parent permissions (pooling)? Default: no; each fits inside one parent permission.
4. Sibling aggregate budget (parent amount shared by children)? Default: not modelled; each child is checked against the parent alone. Recorded as a known gap, the one the current code comment names.
5. Depth arithmetic. Default: child `remaining_depth` at most parent minus one; `may_delegate` true iff depth above zero (matches the zeros in every existing grant).
6. Delegator identity. Default: child `issuer` equals parent `grantee`.
7. Scope comparison. Default: set inclusion on `targets` and `data_scopes`, equality on `action` and `unit`, no unit conversion.
8. Ancestor revocation or expiry of a parent invalidating children. Default: out of scope (status, not shape); stays a gap.
9. Relation to the refusal. Default: this profile replaces `delegation_profile_unsupported` only when opted in; the default path keeps refusing.
10. Time basis. Default: the stated windows are compared as written; no evaluation time is involved.
11. Cycle handling. Default: report the cycle once and skip the edge rules for members of the cycle (avoids contradictory depth findings).
12. Root grants. Default: a root grant (no parent) is not checked against any higher authority here.

## Fixtures

Each fixture file is `{fixture_id, synthetic, expected_outcome, reason, [expected_refusal], document}`. `fixtures/valid/` must be accepted. `fixtures/invalid/` must be refused with `expected_refusal` as the only violation. All fixtures are synthetic; none was produced by a real component (none can be, see Current behaviour).

Valid (7): `root-grant-no-delegation`, `delegation-equal-bounds`, `delegation-narrower-in-every-bound`, `two-level-chain-depth-exhausts`, `two-siblings-from-one-parent`, `child-permission-fits-second-parent-permission`, `extension-namespace-members-preserved`.

Invalid (23): the six required cases are `broadened-amount`, `window-expires-later` (and `window-starts-earlier`), `widened-data-scope` (and `widened-targets`, `action-not-in-parent`), `depth-exhausted`, `missing-parent`, `cycle` (and `self-parent`); the rest pin each other code.

## Run

```
python contracts/non-broadening-delegation/validate.py <document.json>...   # prints violations; fixtures wrap the document
PYTHONPATH=src python -m pytest -q tests/test_contract_non_broadening_delegation.py
```

`validate.py` is stdlib only. The test suite also cross-checks `schema.json` against the `jsonschema` package when it is installed. `chain(doc, grant_id)` returns the root-to-grant ids.

## Versioning and change rules (0.x)

While the version is `0.x-draft` nothing is frozen and any change may break. Enumerations, when added, are closed (decision 6).

## Current conformance (2026-10-17, local runs, not a qualification)

- Producer: none. No component emits this document.
- Consumer: none. The Control Plane refuses a delegated grant (`delegation_profile_unsupported`); a conforming delegated grant is therefore refused today.

## Input hardening (decision 32, 2026-10-18)

The reference validator never raises: any parsed JSON value gets a list of typed violations. Non-finite numbers (NaN, Infinity) and text that is not valid Unicode are refused as `schema_violation`; `main()` reads files with a strict loader (duplicate members, NaN, Infinity, overflowing numbers and non-UTF-8 input are refused, exit status 2, line `input_refused`); schema patterns match the whole string (`(?!\n)$` in `schema.json`) and times are ISO-8601 with ASCII digits and a UTC offset. No code, member or accepted form changed meaning; no code was added.

Invalid fixtures added: `non-ascii-digit-time`, `trailing-line-break-time`, `unpaired-surrogate-text`.
