# ODES Control Plane Store Compatibility Checkpoint

Worker: 8
Branch: `worker8/odes-control-plane-store-compatibility`
Starting SHA: `226adb0e3cde5377ac9db6f7e5857bfa7e65e30a`

## Scope

Bounded ODES compatibility update for the accepted Control Plane persistence
repair. The persistence repair changes record-store mechanics only; it does not
change the bounded-record wire model. This branch therefore preserves:

- base `pder-v0.1` schema version;
- ODES Cognous Stack export profile `odes-cognous-stack-export-0.2.0`;
- producer 1.0.0 and historical unversioned mappings;
- profile 0.2 executor producer `177354e959cc78c59c1a776f018cfbfbf28c927b`;
- Execution Envelope `0.2.0` and Reconstruction Bundle `0.2.0` assumptions.

No Evidence Pack, GAX, executor, hub, deployment, DOCX or unrelated cleanup work
was performed.

## Accepted compatibility pins

Selected profile-0.2 runtime for this branch:

- Replay: `043830b56595cecddfa65c064afd1c0b95e64792`
- Control Plane: `248d899634d9db3518e831bc7ab568a48733f825`
- Executor: `177354e959cc78c59c1a776f018cfbfbf28c927b`

Supported profile-0.2 Control Plane revisions:

- `2ea9528eeb87e14ff10f05de06473122b9df540f`
- `248d899634d9db3518e831bc7ab568a48733f825`

Historical mappings remain pinned to their original revisions and are not
relabelled.

## Changes

- Added explicit supported revision sets in `src/odes/common.py` while keeping
  selected profile-0.2 revisions distinct from supported revision sets.
- Updated `src/odes/exporter.py` to accept both exact v2 Control Plane revisions
  through accepted Replay, while preserving selected revision attribution in
  exported provenance.
- Updated `src/odes/recipient_validator.py` so semantic re-export validation
  remains compatible with prior accepted profile-0.2 packages without relabelling
  their producer records.
- Updated CI to install accepted Replay `043830...` and execute against Control
  Plane `248d899...`.
- Added regression assertions that selected Control Plane and Replay revisions
  agree between Replay input metadata and ODES provenance.
- Updated profile documentation to state that this is a compatibility update,
  not a schema or profile bump.

## Intended qualification coverage

The existing real-producer generator remains the qualification source. It is
expected to cover:

- success;
- lost acknowledgement;
- original-effect restart recovery;
- rejected observation followed by accepted applied recovery;
- partial delivery;
- prior-attempt absence without retry permission;
- held/denied no-effect;
- unsupported revision/profile;
- contradictory revision, effect and attempt lineage;
- package tampering;
- recipient, purpose, scope and freshness rejection;
- public CLI paths: `export-cognous`, `validate-record`, `recipient-validate`.

The tests assert that ODES export and recipient validation are non-effecting:
producer destination state and Control Plane records must remain unchanged across
export/import/validation.

## Current validation status

Local execution was not available in this environment because repository network
access from the execution container could not resolve `github.com`; qualification
is delegated to GitHub Actions on the exact branch head.

At checkpoint creation time, branch CI had been triggered by push and was queued
for the then-current head. The final-head CI status is recorded in the PR body / worker response after the final commit and one final CI inspection.

## Worker 8b takeover — 2026-10-07

Accepted main at inspection: `226adb0e3cde5377ac9db6f7e5857bfa7e65e30a`.
Starting/reused Worker 8 head: `719277c29fff2018813bc28d2ace354bf65ba845`
(PR #25, `worker8/odes-control-plane-store-compatibility`).
Isolated continuation branch: `worker8b/odes-persistence-compatibility`.
No AGENTS.md was present; CONTRIBUTING.md was read. Main and the original
Worker 8 head were rechecked and unchanged before publication.

### Recovered evidence and smallest repair

Exact-head prior CI run `37581752762`: Python 3.11 had **105 passed, 1 failed**;
Python 3.12 was cancelled. Failure: `test_generated_lifecycle_packages`.
Local reproduction identified `retained Replay moltbot_producer_contract differs
from accepted validator`: accepted Replay adds
`compatible_control_plane_revisions`, absent in historical profile-0.2 artifacts.

Reused all seven Worker 8 commits, revision mapping, CI dependency pins, producer
generator, lifecycle tests and checkpoint. The continuation only:

- Permits that absent supported-set field when comparing the original accepted
  Control Plane revision; every selected revision and other contract field must
  still agree. Original packages and retained sources are unchanged.
- Compares selected revisions to reconstructed pins instead of copying untrusted
  selected revisions into the expected value. Old Replay cannot claim support
  for the newer Control Plane revision.
- Rejects contradictory source executor, Manifest and Authority Context revision
  metadata. Existing Replay profile and denied-execution/effect checks remain.
- Adds eight regression cases for these compatibility/attribution boundaries.

### Executed validation (Python 3.12.14)

- Focused producer suite: **53 passed**, no skips.
- Full suite, once: **114 passed**, no skips.
- Existing workflow CLI block: `export-cognous`, `validate-record`,
  `recipient-validate`, and its recipient-result assertions passed.
- Existing qualification generator: **15 actual-producer scenarios passed**.
  Exact accepted dependency checkouts were used, not substitute producer mocks.
  Synthetic faults are those already defined in the accepted Replay generator.
- Destination logical SQLite contents and Control Plane record bytes remained
  unchanged during Replay import, ODES export, record and recipient validation.
- Historical checked-in profile-0.2 packages validate without modification.
  Producer 1.0.0 and unversioned coverage remains in the passing full suite.
- `git diff --check` passed. Historical examples and all downstream repositories
  remain unchanged.

The unchanged CI workflow repeats the full suite and CLI/producer checks on
Python 3.11 and 3.12 for the PR. Final-head CI is checked once at publication;
its observed status and exact SHA are reported in the continuation PR/response.
Local evidence is not a claim that remote CI has completed.

### Supported mapping and remaining action

Profile 0.2: executor `177354e959cc78c59c1a776f018cfbfbf28c927b` / producer 2.0.0,
Control Plane `248d899634d9db3518e831bc7ab568a48733f825` or
`2ea9528eeb87e14ff10f05de06473122b9df540f`, validated using Replay
`043830b56595cecddfa65c064afd1c0b95e64792`. Historical packages attributed to
Replay `274543f1cd7171784a923a8e37015017a0d8bc9d` are supported only with the
older Control Plane revision. Profile 0.1 retains producer 1.0.0 and historical
unversioned mappings documented in `profiles/cognous-stack-export-0.2.md`.
Manifest remains `46c950bed37fe3812000895430bc0312d29e37ce`.

Governor: review the continuation PR (which includes PR #25's work), confirm its
exact-head CI, and accept/merge the ODES change if satisfactory. Then the GAX
owner can consume the accepted ODES revision and rerun Alvorada/GAX PR #8.
This worker does not merge, close the original PR, edit downstream pins or
claim that GAX has already been requalified.
