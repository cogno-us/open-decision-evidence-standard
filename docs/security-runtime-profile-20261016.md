# Repaired runtime ODES generation — 16 October 2026

Adds implementation profile version `odes-cognous-stack-export-0.2.3-security-runtime-candidate` for the exact CP 996baeb4 / runtime fd6b76fa / Replay 3601fb21 / Manifest e385f8c1 generation. Historical mappings remain unchanged.

The exporter reconstructs and validates actual runtime-authority journals, reason vocabulary changes, typed refusals, closeouts and time floors through Replay; it does not merely add revision labels. The recipient recomputes material and requires the exact Replay revision for this generation. Retained source records remain nonauthorizing. Existing restriction, issuer/status and informational-inspection boundaries are unchanged; successful semantic reconstruction cannot supply missing current authority or use permission.

Tests and results are maintained in the central qualification repository's `suites/security-runtime`. No selected source, deployment or publication permission changes.
