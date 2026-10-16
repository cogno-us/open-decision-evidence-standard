# F5b security-runtime ODES generation — 16 October 2026

Adds implementation profile version `odes-cognous-stack-export-0.2.4-security-runtime-f5b-candidate` for the exact merged F5b generation CP a34c3dc2 / runtime e20f92e1 / Replay 79ba16d4 / Manifest 2c36bcd0. It is added beside the security-runtime generation in [security-runtime-profile-20261016.md](security-runtime-profile-20261016.md) (CP 996baeb4 / runtime fd6b76fa / Replay 3601fb21 / Manifest e385f8c1, profile `0.2.3`), which stays accepted unchanged so retained evidence from that generation still re-exports and validates.

Each generation is an exact tuple selected by its Control Plane revision. The exporter emits the pins and profile version of that one generation; the recipient requires the matching profile version and the exact Replay revision of that generation. Mixing components across generations (for example F5b CP with the earlier Replay, or the earlier profile version on F5b pins) is rejected or fails semantic re-export.

The export semantics are the same as the earlier security-runtime generation: runtime-authority journals, reason vocabulary changes, typed refusals, closeouts and time floors are reconstructed through Replay. Failure-record identifiers remain source-asserted references, not independently verified durability or authority. Retained source records remain nonauthorizing, and existing restriction, issuer/status and informational-inspection boundaries are unchanged.

This changes a candidate component revision; it requires F3 requalification, refreeze and re-review before acceptance. No selected source, release, deployment or production authorization changes. Cross-component tests are maintained in the central qualification repository's `suites/security-runtime`.
