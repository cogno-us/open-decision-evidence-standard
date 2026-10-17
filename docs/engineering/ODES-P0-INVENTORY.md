# ODES decoupling, P0 inventory

Status: read-only inventory, 2026-10-17. Phase P0 of the decoupling plan (cogno-us/cognous-control-plane#38). Scope: Cognous components only. Nothing here changes code, pins or any verdict, and no release is declared.

Raw per-repo data, with file and line for every claim, is in `docs/engineering/p0-inventory/<repo>.json`. This page is the summary and the findings.

## 1. Method and limits

- Eleven repositories were inventoried by five read-only workers, each in its own clone. Every row carries file and line. Nobody ran the component code except where a finding says so.
- "Unwritten" means: absent from that repository's own docs, schemas and README (grepped). Peer-owned specs in other repositories were not read, so some "unwritten" rules may be written elsewhere.
- Revisions inspected are in the table. Four of them are pinned local copies with no `main` ref (control plane, action manifest, runtime, evidence pack). A read-only `git ls-remote` showed the control plane and manifest equal the GitHub HEAD; the others were not compared by name. **The Index was inspected on a feature branch (`fix/issues-23-24-link-attestation-independence`), not main.** Re-run that row against main before using it.
- Counts are entries in the JSON, not a measure of severity. The replay and evidence pack JSON arrays each carry one extra trailing note entry, so their rule counts here are one lower than the array length.

## 2. Summary table

| Repository | Inspected | Produces | Consumes | Hard-coded peer pins | Unwritten consumer rules |
|---|---|---:|---:|---:|---:|
| control plane | a34c3dc2 | 8 | 11 | 20 | 15 |
| action manifest | 2c36bcd0 | 7 | 3 | 10 | 7 |
| execution runtime | 4a83b175 | 17 | 11 | 19 | 11 |
| institutional governance (authority) | bae4bce8 (main; pin fb3d9793 is 25 commits behind) | 6 | 5 | 10 | 9 |
| replay bundle | 8eaf3a42 | 4 | 10 | 113 | 68 |
| evidence pack | 505a3590 | 6 | 8 | 96 | 27 |
| governed exchange | ec6ba5bd | 9 | 9 | 83 | 20 |
| the Index (evidence registry) | 703ff3cd (feature branch) | 13 | 5 | 21 | 10 |
| ODES | 9ca8ad05 | 9 | 8 | 23 | 11 |
| hub (open control stack) | 755d3577 | 5 | 2 | 21 | 2 |
| qualification | 7aa2dbfb | 5 | 2 | 10 | 5 |

Replay, evidence pack and exchange carry most of the pins and unwritten rules. Replay alone enforces 68 consumer rules, 30 of them unwritten anywhere in its repo and 32 only partly written.

## 3. How the components are coupled today

1. **In-process import of a peer's source.** Replay is imported by the evidence pack and by the ODES exporter; the control plane, runtime and exchange peers are imported by the exchange reference runtime and the qualification suites. The Replay dependency is not declared: the evidence pack's `pyproject.toml` omits Replay, and ODES lists only `jsonschema`.
2. **Hard-coded peer revisions.** 40-hex shas repeated across code, tests, docs and workflows (section 4 for the biggest clusters).
3. **Exact-match strings instead of schemas.** For example the control plane requires `MANIFEST_VERSION="1.1"`, `AUTHORITY_CONTEXT_VERSION="0.1.0"`, the status `proposed_pending_governor_review` and the capability id `sqlite-effective-grant/0.1`. Record types are free strings, so about 35 Replay record types exist only in importer code.
4. **Duplicated logic.** The control plane re-implements the manifest's proposal mismatch checks and re-declares `RuntimeProposal`, emitting reason codes that neither repo specifies.
5. **Private reach-ins from qualification.** Eight private-symbol import lines, nine `bounded._now` monkeypatches, thirteen private destination-method uses, and imports of peers' test packages and internal modules (206 submodule import lines, not all confirmed non-public).

## 4. Pin clusters

- Replay 113 and evidence pack 96: every per-revision pairing is hard-coded on both sides, and the evidence pack asserts equality with Replay's constants (Replay holds 8 control plane and 8 executor revisions).
- Exchange 83 (about 47 in code and tests, 30 in docs, 3 in CI), repeated across five profile blocks in `gax_ref_runtime.py`.
- Hub 21 plus 370 files containing a 40-hex string, 21 workflows, and a lock selecting a different generation (merged, control plane d3dadee7) from the one qualification validates (F5b).
- ODES 27 distinct shas, all in `src/odes/common.py`. Its effective qualification pin (5675f1b9) is not ODES main.
- Dead constants (defined, never read): runtime `safe_executor.py:16-18` and `ALVORADA_COMMIT`; control plane `bounded.py:30-33`; exchange `ALVORADA_REVISION`. Several pins decorate documents but gate nothing.
- Only a few components actually check a peer's revision in code (exchange for three profiles; replay and evidence pack by table lookup). Most coupling is by shape, not by sha.

## 5. Findings that affect the plan

**N-1. A route can emit `unknown` together with a validated observation (checked by reading the code).** In `engine/safe_executor.py` the timeout path returns status `unknown` with the observation from `observe_bound`, which can be a validated applied or partial row. The OpenShell destination raises that timeout after it has already observed `applied` when the acknowledgement's `duplicate` flag is not a boolean (`openshell_environment.py:378-386`). So `status == "unknown"` does not always mean no known effect. This contradicts ODES decision item 8 (`unknown` with a validated observation is invalid). It is not a Replay or contract bug until someone decides which side moves. **Needs an owner decision; see section 7.**

**N-2. Evidence pack cannot re-validate the route-B bundles Replay now produces (reproduced).** For all three captured route-B fixtures (`observe_bound_fail`, `lost_ack_recon_down`, `reconcile_only`) the pack's pinned-Replay re-validation fails with "accepted executor observations differ from result". Replay retains the recovery report as record type `executor_recovery_report`; the pack rebuilds the executor export from the retained records and does not map that type back. Replay #37 did not break anything that passed before, but F-24 is not closed end to end until the pack accepts it. Recorded as F-25.

**N-3. Route naming is not in the runtime repo.** The runtime names route A (`PinnedControlPlaneExecutor`) and route B (`AtomicLocalControlPlaneExecutor`). "Route C" is a qualification term, and the inventory worker had to infer which code it means. The contract and the qualification suites should use names the runtime repo defines.

**N-4. No schema exists for several boundary objects.** Authority Context (the control plane reads about 25 dict paths), the claim object (docs cite a schema that is not in `schemas/`), the destination executor interface (duck-typed, test-hook kwargs `lose_ack` and `partial` always passed), and the manifest proposal (no 1.1/1.2 discriminator).

**N-5. The authority repository is spec, schemas and fixtures only.** It consumes no peer artifact at runtime. Authority Context 0.1.0 is unchanged between the pin and main; Authority lineage 0.1.0 is new. Both interfaces still disclaim conformance with ODES. The runtime's `ALVORADA_COMMIT` equals the authority pin and is never read.

**N-6. The Index does not feed any other Cognous component in this set.** It consumes BitRep (pin 5b5077da, vendored). Two BitRep profiles in the repo do not match (`index.link.v1` versus `index-support/1`), and the chain mapping is not enforced in code. The copied-evidence limit (F-19) sits wholly on the Index side because BitRep attests the issuer signature only.

**N-7. Manifest digest depends on explicit nulls and carries an Alvorada pin inside the digest-covered example.** Bumping that pin changes `manifest_digest`, and the digest check passes only for a full dump with explicit nulls.

**N-8. Several documents disagree.** The runtime docs carry three different control plane shas; ODES points at two different qualification commits; the hub lock's ODES pin (c5e9a0f3) is neither ODES main nor the qualification pin; ODES exporter still uses stale repository names.

## 6. What this means per phase

- **P1, lifecycle contract.** Add to the draft: separate fields for result status, `observed_state` and observation (N-1), `recovery_observations` (decided), and route names taken from the runtime repo (N-3).
- **P2, conformance suites.** The unwritten-rule lists per repo are the work queue: each one is either written into a contract or removed from the consumer. Replay's 30 unwritten and 32 partial rules and the pack's 20 unwritten rules are the largest.
- **P3, one component per PR.** Evidence pack: map `executor_recovery_report` back (N-2). Runtime: decide N-1's direction and add the probe. Declare the Replay dependency in the pack and in ODES.
- **P4, qualification.** Remove the private reach-ins (section 3.5) by moving what they need into public entry points or fixtures.
- **Hygiene.** Dead pin constants, stale repository names, mismatched shas in docs (N-8), the Alvorada pin in the manifest example (N-7).

## 7. Decisions this needs from the owner

1. **N-1 direction.** Two options: (a) the contract allows `unknown` with a validated observation and consumers treat status, `observed_state` and observation separately; (b) the runtime reports `reconciled` or `partial` when a validated observation exists. Recommendation: (a). Status describes the delivery attempt, observation describes what is known, and (b) changes runtime behaviour that the existing route-A and OpenShell paths rely on.
2. **F-25 handling.** Fix the evidence pack now (small change: map one record type back) or leave it to P3. Recommendation: P3, with the other pack changes.

## 8. External dependencies (appendix, no contracts planned)

NVIDIA OpenShell 0.1.2 CLI and gateway with Docker (runtime), SQLite as the synthetic destination, pydantic, cryptography, pytest, the Microsoft Agent Governance Toolkit (control plane), Linux `fcntl.flock`, GitHub Actions and reusable workflows, git CLI via subprocess (exchange), and for the Index: BitRep (a Cognous component, listed under consumes), Solidity/ethers/Ganache/EVM JSON-RPC, and unimplemented IPFS/HTTPS replicas. Full lists are in each JSON file under `external_deps`.
