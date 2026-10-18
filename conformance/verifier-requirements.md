# Verifier Requirements

Schema validity means the record conforms to the base JSON structure. Profile conformance means the record satisfies a named conformance profile such as `pder_v0_1_minimal`. Verifier acceptance means the record is acceptable for a specific relying party, purpose, time, freshness state, and consumption condition.

A conceptual verifier for PDER v0.1 should:

1. parse the record;
2. validate the record against the schema;
3. verify `record_type` and `schema_version`;
4. check signature material or an explicit verification placeholder;
5. check expiration;
6. check freshness;
7. check the revocation flag;
8. check the permitted relying party;
9. check the permitted purpose;
10. check any required conformance profile; and
11. return pass/fail with reasons.

A record may be schema-valid and still fail verifier acceptance because it is expired, revoked, stale, outside the permitted purpose, outside the permitted relying party, or otherwise unsuitable for reliance.

Schema validation checks structure. It does not establish that the underlying decision is correct, lawful, complete, or suitable for reliance.

This repository provides a reference recipient validator (`odes recipient-validate`; see [recipient validation](../docs/recipient-validation.md)) for Cognous export packages. It is reference code and is not production-qualified, and no conformance certification exists. It does not verify signatures: a declared signature type is reported `unsupported` or `unavailable`, never `pass`. It evaluates only the Cognous profiles; a package under another profile is reported `unsupported`.

The list above describes expected verifier behavior for the open record format. It is not a statement of what the reference validator implements for every step, and a verifier for another profile needs its own documented behavior and tests.
