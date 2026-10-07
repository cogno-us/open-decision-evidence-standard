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
