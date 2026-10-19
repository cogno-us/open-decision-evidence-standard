<!-- cognous-banner:start -->
```text
──────────────────────────────────────────────────
   __________  _______   ______  __  _______
  / ____/ __ \/ ____/ | / / __ \/ / / / ___/
 / /   / / / / / __/  |/ / / / / / / /\__ \
/ /___/ /_/ / /_/ / /|  / /_/ / /_/ /___/ /
\____/\____/\____/_/ |_/\____/\____//____/
         OPEN DECISION EVIDENCE STANDARD
       g o v e r n e d   b y   d e s i g n
  github.com/cogno-us/cognous-open-control-stack
──────────────────────────────────────────────────
```
<!-- cognous-banner:end -->

# Open Decision Evidence Standard

**Portable decision evidence across system and organizational boundaries.**

**Status:** group 05 · Replay & Evidence; lock status **selected** (ODES implementation profile 0.2.1, merged producer pair; record schema `pder-v0.1`). The specification is a draft, not a ratified standard. The contract drafts under `contracts/` are **proposed** and stay `0.1.0-draft`. Nothing here is a release; operational trust remains [HOLD under #30](https://github.com/cogno-us/cognous-stack-orchestrator/issues/30).

## What it is

ODES is an open, vendor-neutral discussion draft and reference tooling for portable decision evidence. The v0.2 narrative and implementation profile retain the pder-v0.1 record schema. It carries coordinates for recipient evaluation, rather than deciding whether a recipient should rely on the underlying decision. Governance is currently single-maintainer (Cognous is the initial editorial maintainer) and the work is a draft, not a ratified standard.

**Who it is for.** Engineers who want to inspect the reference contracts and examples, and enterprise architecture, security and governance reviewers who want to examine the boundary and the evidence. A decision can cross a boundary without its authority basis, human disposition, evidence commitments, freshness or consumption conditions; recipients need structured context while keeping their own policy and without mandatory disclosure of confidential raw evidence.

**What it does not do.** ODES is not a shared policy plane, blockchain requirement, certification or proof that a decision is correct, lawful or suitable for reliance. It does not grant execution authority. Reference implementation compatibility is narrower than a universal interoperability or standards-adoption claim. See [what it does not do](#what-it-does-not-do-known-limits).

**How it works.** A producer exports a decision-evidence package from retained reconstruction. The recipient validates the record and commitments, then evaluates the package under its own policy. Missing authentication or current-authority evidence remains unavailable; package validity cannot silently fill those gaps. Selective disclosure concerns what is shared, not permission to infer omitted facts. A valid signature, chain inclusion, message receipt, reasoning instruction or evidence-package digest does not authorize execution; institutional authority must be supplied and evaluated through the appropriate trusted boundary.

## Where it fits

<a id="cognous-stack-components"></a>

<!-- stack-map:start -->
<!-- Canonical block: identical text in every component README. Source: docs/stack-map.md in the hub. Refresh at the pin round. -->
The Open Control Stack groups its repositories by responsibility. The groups are a navigation map, not an execution sequence and not a requirement to install every component. The hub [component lock](https://github.com/cogno-us/cognous-open-control-stack/blob/main/component-lock.json) is the only source of selected revisions; [release status](https://github.com/cogno-us/cognous-open-control-stack/blob/main/docs/release-status.md) states their evidence and limits. Last checked against `component-lock.json` at hub commit `dcc9bd7533ef`.

| Group | Members |
| --- | --- |
| **01 Knowledge & Provenance** | [Evidence Registry (The Index)](https://github.com/cogno-us/cognous-evidence-registry) · [Evidence Attestation (BitRep)](https://github.com/cogno-us/cognous-evidence-attestation) |
| **02 Institutional Governance** | [Institutional Governance (Alvorada)](https://github.com/cogno-us/cognous-institutional-governance) |
| **03 Declaration & Policy Control** | [Action Manifest](https://github.com/cogno-us/cognous-action-manifest) · [Control Plane](https://github.com/cogno-us/cognous-control-plane) |
| **04 Constrained Execution** | [Execution Runtime](https://github.com/cogno-us/cognous-execution-runtime) |
| **05 Replay & Evidence** | [Replay Bundle](https://github.com/cogno-us/cognous-replay-bundle) · [Governance Evidence Pack](https://github.com/cogno-us/cognous-governance-evidence-pack) · [ODES](https://github.com/cogno-us/open-decision-evidence-standard) |
| **Cross-cutting exchange** | [Governed Exchange (GAX/IMX)](https://github.com/cogno-us/cognous-governed-exchange) |
| **Tooling and qualification** (side group) | [Ergonomics (`cognous-ocs`)](https://github.com/cogno-us/cognous-open-control-stack-ergonomics) · [Verifier](https://github.com/cogno-us/cognous-open-control-stack-verifier) · [Orchestrator](https://github.com/cogno-us/cognous-stack-orchestrator) · [Qualification](https://github.com/cogno-us/cognous-stack-qualification) |

Status labels used in this README: **merged** (reviewed and merged in the owning repository; not by itself selected), **selected** (pinned in the hub lock), **known limit** (a limitation that is stated and kept visible) and **proposed** (draft or planned work, not a supported interface). Full map, names and commands: [stack map](https://github.com/cogno-us/cognous-open-control-stack/blob/main/docs/stack-map.md), [naming](https://github.com/cogno-us/cognous-open-control-stack/blob/main/docs/naming.md), [profiles and tools](https://github.com/cogno-us/cognous-open-control-stack/blob/main/docs/profiles-and-tools.md). A signature, registry entry, message receipt or evidence summary does not grant execution authority.
<!-- stack-map:end -->

ODES is in group 05. It consumes retained material from [Action Manifest](https://github.com/cogno-us/cognous-action-manifest), [Control Plane](https://github.com/cogno-us/cognous-control-plane) and [Replay Bundle](https://github.com/cogno-us/cognous-replay-bundle) through the Cognous export profiles, and its `contracts/` drafts are the source of the contract copies that other repositories vendor. The [verifier](https://github.com/cogno-us/cognous-open-control-stack-verifier) implements the verification-report contract. For audience navigation use the hub [start guide](https://github.com/cogno-us/cognous-open-control-stack/blob/main/docs/start-here.md); revision-specific qualification commentary is in the [central test hub](https://github.com/cogno-us/cognous-stack-qualification/blob/main/results/readme-commentary/index.md).

## Quick start

Prerequisites: Linux, Python 3.11 or newer, an activated virtual environment and network access for the install. Nothing below contacts a network after the install. From a fresh checkout (about 15 seconds):

```bash
python -m pip install -e ".[dev]"
odes validate-record examples/ai-assisted-review.example.json
echo "exit $?"
odes recipient-validate examples/producer-v2/partial.package.json \
  --policy examples/policies/recipient-audit-policy-producer-v2.json \
  --out /tmp/odes-result.json
echo "exit $?"
python -c "import json; d = json.load(open('/tmp/odes-result.json')); print({k: v['status'] for k, v in sorted(d.items()) if isinstance(v, dict) and 'status' in v})"
```

Expected output:

```text
exit 0
exit 1
{'authority_status_and_freshness': 'unavailable', 'consumption_conditions': 'fail', 'declared_profile_conformance': 'pass', 'historical_authority_assertions': 'unavailable', 'integrity_authentication_checks': 'unavailable', 'package_content_integrity': 'pass', 'recipient_reliance_decision': 'fail', 'replay_semantic_consistency': 'unavailable', 'schema_validity': 'pass'}
```

What this shows:

- `odes validate-record` prints nothing when the record is schema-valid and exits 0. On a schema-invalid record it raises `ValueError` (a traceback, exit 1); this command is not one of the commands that return a structured result.
- `odes recipient-validate` always prints (or writes with `--out`) a JSON result with one status per layer. Exit codes: 0 when the reliance decision is `pass`, 3 for `informational_only`, 1 otherwise. Here the package is well formed and its digest matches (`schema_validity`, `declared_profile_conformance` and `package_content_integrity` pass), but the reliance decision is `fail`: the recipient policy supplies no status evidence, no issuer authentication evidence and no trusted digests, the consumption check does not pass for this policy, and the Replay distribution is not installed in a clean checkout, so `replay_semantic_consistency` is `unavailable`. Every status other than `pass` blocks reliance. See [recipient validation](docs/recipient-validation.md) for the status set and precedence.
- What this does not prove: a package that passes its integrity layers is content-consistent, not authenticated, not currently authorized and not suitable for reliance.
- `odes export-cognous` needs a Cognous Action Manifest and a Replay reconstruction as inputs, and, for the qualified-build gate, an installed Replay at an accepted revision. It cannot run from this repository alone; the hub [quickstart](https://github.com/cogno-us/cognous-open-control-stack/blob/main/docs/quickstart.md) supplies the exact producer checkouts.

## What ships

Labels as defined above. The lock pins an older ODES revision than `main`; items marked "after the lock" were merged after it.

### Command line: `odes`

| Command | Purpose | Label |
| --- | --- | --- |
| `odes export-cognous --manifest F --reconstruction F --out F [--relying-party S] [--purpose S] [--expires-at T]` | Export a Cognous-stack decision-evidence package. | selected |
| `odes validate-record <record>` | Validate a record against the `pder-v0.1` schema. | selected |
| `odes recipient-validate <package> --policy F [--out F]` | Evaluate a package against a recipient policy; refuses over-budget input with the closed reason code `budget_exceeded`. | selected |

### Profiles, schema and versions

| Item | What it is | Label |
| --- | --- | --- |
| [`schema/pder-v0.1.schema.json`](schema/pder-v0.1.schema.json), [field notes](schema/pder-v0.1-fields.md) | Closed JSON schema for one decision-evidence record. Every substantive field is an issuer assertion. | selected |
| [minimal](profiles/minimal.md), [agentic AI](profiles/agentic-ai.md), [regulated enterprise](profiles/regulated-enterprise.md) | Informative sector and minimal profiles. | merged |
| [Cognous stack export 0.1](profiles/cognous-stack-export-0.1.md) | Historical Cognous export profile. | merged |
| [Cognous stack export 0.2](profiles/cognous-stack-export-0.2.md) | Producer 2.0.0 export with Replay semantic consistency; generation 0.2.1 (merged producer pair) is the lock's profile. | selected |
| [Cognous stack export 0.2 restrictions](profiles/cognous-stack-export-0.2-restrictions.md) | Explicit restriction semantics (`odes_cognous_stack_export_0_2_restrictions`): unknown is not unrestricted. | merged (after the lock) |
| [Generic recipient 0.1](profiles/generic-recipient-0.1.md) | `odes_generic_recipient_0_1`: needs no Cognous component and can carry the native evidence inventory; no Replay check is run or claimed. | merged (after the lock) |
| [Native evidence inventory](docs/native-evidence-inventory.md) | Byte-preserving inventory of native evidence with limits; recipient checked; nothing fetched. | merged (after the lock) |
| [Detached authentication](docs/detached-authentication.md) | Optional DSSE with Ed25519 (`pip install -e ".[signatures]"`); a verifying signature authenticates origin only. | merged (after the lock) |
| `rfc8785-jcs` canonicalization | RFC 8785 as a separate profile next to the legacy one; integers within -(2^53 - 1) to 2^53 - 1; relabelling a package does not make its digests valid. See [recipient validation](docs/recipient-validation.md#canonicalization-profiles). | merged (after the lock) |

Version coordinates: the lock's "implementation profile 0.2.1" is the profile version `odes-cognous-stack-export-0.2.1` (the merged Control Plane and Replay pair); it sits beside the narrative version 0.2, the base schema `pder-v0.1`, the package envelope 0.1.0 and the Python package 0.2.0. These are different axes, not conflicting values. The [capabilities and version register](docs/capabilities-and-versions.md) lists every coordinate and where it is defined. <!-- pin-round: refresh the lock pin and the "after the lock" labels -->

### Contract drafts (`contracts/`)

Seventeen drafts, each a directory with a README, `schema.json`, `validate.py` and fixtures; all are **proposed**, `0.1.0-draft`, not frozen, and not required by `pder-v0.1`. `contracts/tools/vendor_contract.py` is the vendoring and drift-check tool. Other repositories vendor copies of some contract directories; edit them here, not in the copies.

| Contract | Covers | Label |
| --- | --- | --- |
| [`authority-lineage`](contracts/authority-lineage/README.md) | Hash-linked record from grant to delegation to terminal effect; an unexplained effect is refused. | proposed (`0.1.0-draft`) |
| [`bounded-deferral`](contracts/bounded-deferral/README.md) | Bounded deferral of an effect and what a deferral does not establish. | proposed (`0.1.0-draft`) |
| [`control-plane-journal`](contracts/control-plane-journal/README.md) | The Control Plane run record (journal): decisions, attempts, observations, refusals, checks; rules for dispatch license and result consistency. | proposed (`0.1.0-draft`) |
| [`destination-ledger`](contracts/destination-ledger/README.md) | Destination-side ledger of effects and observations. | proposed (`0.1.0-draft`) |
| [`effect-reversibility`](contracts/effect-reversibility/README.md) | Reversibility classes and the recorded use of a cached purpose snapshot. | proposed (`0.1.0-draft`) |
| [`execution-attempt-lifecycle`](contracts/execution-attempt-lifecycle/README.md) | Attempt state machine, result and observation consistency (executor and Control Plane transition tables). | proposed (`0.1.0-draft`) |
| [`freshness-clocks`](contracts/freshness-clocks/README.md) | Named clocks, check deadlines and overdue state. | proposed (`0.1.0-draft`) |
| [`governed-exchange`](contracts/governed-exchange/README.md) | Governed exchange messages and acknowledgements. | proposed (`0.1.0-draft`) |
| [`holder-inventory`](contracts/holder-inventory/README.md) | Enumerated holders of authority and what a revocation probe may claim. | proposed (`0.1.0-draft`) |
| [`index-evidence-registry`](contracts/index-evidence-registry/README.md) | Evidence-registry (Index) records and chain commitments. | proposed (`0.1.0-draft`) |
| [`non-broadening-delegation`](contracts/non-broadening-delegation/README.md) | A delegated grant is a subset of its parent; delegation itself stays refused by the Control Plane. | proposed (`0.1.0-draft`) |
| [`operation-identity`](contracts/operation-identity/README.md) | Operation identity across grant revisions and the attempt join. | proposed (`0.1.0-draft`) |
| [`rule-revision`](contracts/rule-revision/README.md) | Digest-pinned rules with append-only revision rows. | proposed (`0.1.0-draft`) |
| [`source-family-counting`](contracts/source-family-counting/README.md) | Counting evidence by source family. | proposed (`0.1.0-draft`) |
| [`two-party-reconciliation`](contracts/two-party-reconciliation/README.md) | Two-party reconciliation of an effect. | proposed (`0.1.0-draft`) |
| [`verification-report`](contracts/verification-report/README.md) | Report format of an independent verifier: verdicts, tallies, non-claims, mutation report. | proposed (`0.1.0-draft`) |
| [`witness-digest`](contracts/witness-digest/README.md) | Hash chain over ledger rows and a witness record. | proposed (`0.1.0-draft`) |

### RFCs, conformance, examples

- **RFCs** in [rfcs/](rfcs): [0001 portable decision evidence record](rfcs/0001-portable-decision-evidence-record.md), [0002 combined specification and informative evidence review](rfcs/0002-combined-specification-and-informative-evidence-review.md), [0003 verifier behavior and reliance boundaries](rfcs/0003-verifier-behavior-and-reliance-boundaries.md), [0004 decision-evidence lifecycle semantics](rfcs/0004-decision-evidence-lifecycle-semantics.md).
- **Conformance** in [conformance/](conformance): [minimal conformance profile](conformance/pder-v0.1-minimal.md), [verifier requirements](conformance/verifier-requirements.md), [generic profile vectors](conformance/generic-profile-vectors.json) and [test vectors](conformance/test-vectors).
- **Examples** in [examples/](examples): three records (`ai-assisted-review`, `claims-review`, `vendor-assurance`), two recipient policies (historical profile; producer 2.0.0) and five producer-v2 packages (`lost_ack`, `partial`, `prior_absence`, `rejected_wrong_effect`, `restart`).
- **Python modules** in [src/odes/](src/odes): `canonicalization`, `cli`, `common`, `evidence_inventory`, `exporter`, `generic_profile`, `recipient_validator`, `schema_validation`, `signatures`.

## What it does not do (known limits)

| Limit | Detail |
| --- | --- |
| Validity is not authority | A schema-valid record or a package that passes its integrity layers is not verified, trusted, authorized or suitable for reliance. A digest binds content; it does not authenticate an issuer. A verifying detached signature authenticates origin only. |
| Digest scope | `package_digest` covers record, profile, integrity metadata and provenance. `package_type`, `package_version`, `created_by` and `created_at` sit outside it; the validator checks their shape and refuses extra top-level members, but `created_by` and `created_at` are not tamper-evident. Covering them is a format decision that is not made. |
| Consumption conditions | The relying-party check applies to the record's `permitted_relying_parties` list; an absent, empty or malformed list is refused, never read as "any recipient". |
| The journal validator does not check the destination | The `control-plane-journal` validator has no rule that reads an observation's target, amount, unit or payload, so it does not confirm what happened at the destination. |
| Verification reports | A report decides on `verdict`, `tally` and `could_not_check_reason`; the `detail` text of a finding is diagnostic. A scope the report does not state (tenant, task, operation) is "not asserted", never "not applicable". See [the contract](contracts/verification-report/README.md). |
| Activation of operation identity | The document alone cannot show the operation-identity profile was on: a record with every profile member removed is accepted unless the caller passes `require_profile`. |
| Input budgets | The validator and CLI commands enforce in-process budgets (bytes, depth, nodes, items, fields, string length) and a 5 second worker deadline for the Replay check. These are starting values, not memory or CPU isolation. Run validation of untrusted input under operating-system limits. |
| Validators and exceptions | The contract validators (`contracts/*/validate.py`) return typed violations for any parsed JSON document, and for a context argument of the wrong shape in the contracts that take one; this is tested by mutation sweeps. The recipient validator returns a structured `fail` result for malformed package or policy shapes. `odes validate-record` raises `ValueError` on a schema-invalid record. |
| Approvals | An approval record, where one exists, shows the approver's identity and commitment. It does not show what the approver was shown. A human step-up profile (a digest of the displayed content equal to the dispatched operation commitment) is proposed, not defined. |
| Verification tiers and durable inclusion | A V1 or V2 pass of the independent verifier establishes integrity and internal consistency of the record, not that the recorded decision was correct, and no tier checks permission. A record that validates, or a journal whose counts, order and bindings agree, does not show durable storage or retention of any row: durable inclusion is not a verification level. See [the contract](contracts/verification-report/README.md). |
| Draft status | The specification is a draft with a single maintainer. Contract content can differ across repositories under an unchanged `0.1.0-draft` label; compare digests, not labels. No contract is frozen. |
| Replay-dependent checks | Profile 0.2 semantic consistency needs the Replay distribution at an accepted revision; otherwise the layer is `unavailable` or `unsupported`, never `pass`. |

Review original artifacts and their exact source revisions before extending a claim to a new environment. New dependencies, authority sources, destinations or enforcement mechanisms need their own compatibility and qualification. A passing reference case is not a certification of an enterprise deployment.

## Documentation

The [documentation index](docs/README.md) lists every page by role and marks historical pages. Start with [recipient validation](docs/recipient-validation.md), the [capabilities and version register](docs/capabilities-and-versions.md), [selective disclosure](docs/selective-disclosure.md) and [related work](docs/related-work.md). For a non-technical introduction, read the [business overview](collateral/business-collateral.md) and [one-page overview](collateral/one-page-overview.md); both describe this component's role and evidence limits, not additional runtime features.

## Compatibility and selection

The [component lock](https://github.com/cogno-us/cognous-open-control-stack/blob/main/component-lock.json) selects the integration; a merge here does not change that selection or approve deployment. The lock pins this repository at `c5e9a0f3695a`; `main` is ahead of it. The implementation supports the persistence-compatible Control Plane and Replay generation while preserving older mappings (see the [compatibility checkpoint](docs/workstreams/odes-control-plane-store-checkpoint.md) and [merged producer compatibility](docs/merged-producer-compatibility.md): the exact merged pair has the consumer mapping `odes-cognous-stack-export-0.2.1`; atomic-claim and refund-intent evidence are not added). This accepted implementation does not turn the discussion draft into a ratified standard or establish external adoption. Test results and historical qualification records are in the [central test hub](https://github.com/cogno-us/cognous-stack-qualification/blob/main/results/readme-commentary/index.md); read them against their recorded source revisions.

## Run the tests

```bash
python -m pip install -e ".[dev]"
PYTHONPATH=src python -m pytest -q   # 2 to 3 minutes; 3011 passed, 8 skipped at the time of writing
```

Cross-component test commands run in a disposable checkout assembled by the [qualification workflows](CROSS_COMPONENT_TESTS.md); plain local test discovery covers the component-local tests retained here. Historical reports and dependency pins keep their original scope. The [qualification suites](https://github.com/cogno-us/cognous-stack-qualification/tree/39f038435afdd71ba162860faa5718d90d7bde64/suites/open-decision-evidence-standard) hold the executable integration harnesses. The documentation register and contract vendoring tests (`tests/test_documentation_register.py`, `tests/test_vendor_contract_tool.py`) check that public text keeps its qualified wording and that contract copies verify.

## Contributing, governance and attribution

[Contribution guidance](CONTRIBUTING.md) describes review and validation expectations (Python 3.11 to 3.14 are supported local interpreters); see also [GOVERNANCE](GOVERNANCE.md), [SECURITY](SECURITY.md) and [CODE_OF_CONDUCT](CODE_OF_CONDUCT.md). Keep evidence-linked claims, preserve historical records and separate proposed features from accepted implementation.

See [LICENSE](LICENSE) and [attribution](NOTICE) for the existing terms and third-party scope. Developed by [Cognous](https://cogno.us); no licensing change is part of this documentation update. Repository renames: see the [rename map](https://github.com/cogno-us/cognous-open-control-stack/blob/main/docs/repository-renames.md); package names, schema identifiers and retained producer identities are unchanged.

---

## Bibliography

Selected external sources from the October 2026 research review. These inform evaluation questions; they do not establish Cognous implementation, adoption, conformance or production qualification.

- [Alexander Barrett. *Boundary Blindness Under Artificial Intelligence: Early Cross-Industry Findings on the Missing Decision-Evidence Layer* (2026)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7210798). Working paper on carrying the basis for reliance across organizational boundaries; proposed architecture, not a validated interoperability guarantee.
- [John M. Willis. *Runtime Governance Body of Knowledge for Artificial Intelligence and Other Autonomous Systems — Glossary* (19 July 2026)](https://sustainablefuturetech.com/asg-wg-runtime-governance-glossary/). Discussion draft on authority, execution and evidence terminology; not an adopted standard or Cognous conformance requirement.
- [OECD. *Agentic AI in organisations: Early insights from practitioner interviews*. OECD Artificial Intelligence Papers, No. 65 (2026)](https://doi.org/10.1787/1257a26f-en). Qualitative practitioner research on bounded autonomy, oversight and organizational deployment.

See the [research bibliography](https://github.com/cogno-us/cognous-open-control-stack/blob/main/docs/research-bibliography.md) for review scope and source-verification limits.

<!-- Retained anchors for existing documentation links. -->
<a id="evidence-and-supported-scope"></a>
