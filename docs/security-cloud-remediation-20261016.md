# Security Cloud remediation proposal — open-decision-evidence-standard

Scan: https://chatgpt.com/codex/cloud/security/runs/wfr_abaa9ae08c188316b9377616d1df5755644fc4d717ddc2ecbd8105ec44dc1d6e
Scanned/base revision: `7b7eb444d30ee65354a8c0cd4d07a4c05a261a95`.

Fail recipient CLI status on rejected reliance; require explicit consistent profile declarations and Replay layer dispatch; bind authority status to recipient-trusted issuer identity; reject unverified derivation; preserve conservative use restrictions and require recipient jurisdiction; require exactly one digest-bound Manifest action.

## Finding coverage

- `csf_4aef8c66723c79943cfd7708` (medium): recipient-validate exits successfully after a failed reliance decision. Proposed code correction; final disposition pending review and source-bound checks.
- `csf_f2a5049e4d834b487fd1aa6b` (medium): Fallback profile parsing can skip mandatory profile-0.2 Replay validation. Proposed code correction; final disposition pending review and source-bound checks.
- `csf_357df0135a47f7338a34d117` (low): Trusted status evidence is not bound to issuer identity. Proposed code correction; final disposition pending review and source-bound checks.
- `csf_085b040edde47324e9405df1` (low): Caller-controlled derivation metadata is promoted into validated redaction claims. Proposed code correction; final disposition pending review and source-bound checks.
- `csf_b66134c55b0758c15e57a8ae` (low): Use restrictions are overwritten during export and ignored during recipient validation. Proposed code correction; final disposition pending review and source-bound checks.
- `csf_7b91222039fbbb881da9fde3` (low): Manifest validation does not require the proposal action to be declared. Proposed code correction; final disposition pending review and source-bound checks.

## Validation and limits

8 targeted regression tests passed; full relocated cross-component suite pending.

Component changes require integrated qualification before any selected hub pin advances. These are proposed repairs; passing local checks is not independent security certification. The package frozen at hub `7f335099ca52a68533b6e78c2e35166a9109e35c` has not been regenerated or relabeled as containing these edits. No publication or production authorization is granted. No paid model trials, production probes or external communications ran.

Historical retained packages may fail stricter claim validation. They must not be silently rewritten; compatibility and any newly generated package require explicit evidence reconciliation.
