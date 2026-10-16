# Security Policy

This repository welcomes reports about vulnerabilities in supporting materials and security concerns in the draft specification itself.

In scope are concerns such as:

- cryptographic misuse
- signature confusion
- replay risk
- revocation failure
- stale record acceptance
- selective disclosure leakage
- issuer impersonation
- verifier endpoint abuse
- privacy leakage
- malicious conformance claims

Known limitation: the reference tooling applies no size, depth or processing budgets to package input. See [recipient validation input shape and resource limits](docs/recipient-validation.md#input-shape-and-resource-limits) for the recommended operating-system and process limits.

Security contact: andredelima@cogno.us

Security reports sent to this address should include a concise description of the issue, affected files or record elements, potential impact, and any suggested mitigation.
