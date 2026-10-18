# Recipient Validation Reference Path

Status: Informative reference behavior for exported ODES packages.

The recipient validator consumes only an exported package and explicit recipient policy/status inputs. It does not access producer databases, call private runtime services, execute workflows, renew authority or mutate destination state.

## Validation layers

The reference validator returns separate results for:

1. `schema_validity` — validates the embedded `record` against `pder-v0.1`.
2. `declared_profile_conformance` — checks package version, implementation-profile version and the profile declared by the package and record.
3. `package_content_integrity` — validates supported content-digest metadata, canonicalization profile and the complete material package digest over record, profile, integrity metadata and provenance.
4. `integrity_authentication_checks` — evaluates issuer-authentication evidence separately from content integrity. A public hash is not issuer authentication.
5. `historical_authority_assertions` — distinguishes record self-assertions from externally configured evidence about authority at decision time.
6. `authority_status_and_freshness` — evaluates present authority, revocation, supersession, freshness and expiry against recipient policy inputs and an explicit recipient evaluation time. A record consumption window is half-open: an evaluation time equal to `consumption_conditions.expires_at` is expired.
7. `consumption_conditions` — checks relying party and purpose. A record whose `permitted_relying_parties` is absent, empty or not a list of non-empty strings names no recipient and is refused; an empty list never means "any recipient" (decision 39-N).
8. `recipient_reliance_decision` — recipient policy result.

A schema-valid record cannot automatically become verified, trusted, authorized or suitable for reliance.

## Result values and precedence

Every layer result has a `status`, a list of `reasons` and an `evidence` object. The status set is closed:

| Status | Meaning | Examples |
| --- | --- | --- |
| `pass` | The layer's check ran and the evidence supports it. | Digest matches; consumption conditions satisfied. |
| `fail` | Known-invalid content, a definitive refusal, a contradiction or an operational error that makes the check unusable. | Digest mismatch; consumption window expired (with or without status inputs); retained sources contradict the exported summary; Replay raised an unexpected error. |
| `unavailable` | Required evidence or a required optional dependency is absent, so the check could not run. | No status inputs and the window has not expired; no issuer authentication evidence; the Replay distribution is not installed or its installed revision cannot be determined. |
| `unsupported` | The format, method or installed revision is not implemented by this reference validator. | Unknown declared profile; declared signature type; an installed Replay that is not an accepted revision or lacks a module the check needs. |
| `not_evaluated` | The layer was skipped because the input could not be examined. | `schema_validity` when the package or policy is not an object. |
| `not_applicable` | The layer does not apply to the declared profile. | `replay_semantic_consistency` when the record declares profile 0.2 but the package profile does not (this also fails profile conformance). It is never a pass. |
| `informational_only` | `recipient_reliance_decision` only. | Recipient policy allows inspection of unauthenticated material and the only non-passing layer is `integrity_authentication_checks`. It is not reliance, authorization or verification. |

Precedence. A layer returns the first row that applies: known invalid content or a definitive expiry is `fail`; then an unimplemented format or revision is `unsupported`; then absent required evidence or dependency is `unavailable`. A skipped layer is `not_evaluated`; a layer excluded by the selected profile is `not_applicable`. `recipient_reliance_decision` is `pass` only when every evaluated layer is `pass`. It is `informational_only` only under the explicit policy flag and only when the single non-passing layer is `integrity_authentication_checks`. Otherwise it is `fail`, and its `evidence.blocking_layers` names each non-passing layer with its status, so a caller can tell a settled refusal (`fail`) from missing evidence (`unavailable`) or an unimplemented check (`unsupported`). Every status other than `pass` blocks reliance; the classes differ only in what a caller may reasonably do next. Inspection and reliance are separate: `informational_only` never satisfies a caller that asked for reliance.

The Replay check separates three situations. The retained sources contradict the package, or Replay raises an unexpected error: `fail`. The Replay distribution is not installed, or its installed revision cannot be determined: `unavailable`. An installed Replay is not an accepted revision, or lacks a module the check needs: `unsupported`. Any other import error stays `fail` with the error type in the reason.

## Integrity boundary

Hashes establish content binding, not issuer identity. The reference package carries two digest surfaces:

- `integrity.value` binds the exported ODES record and profile metadata.
- `package_digest` binds the material exported package content: record, profile, integrity metadata and provenance, including execution facts, source references, limitations and redaction lineage.

Top-level members outside the digest (decision 39-M). The digest does not cover `package_type`, `package_version`, `created_by` and `created_at`. The validator refuses a package that carries any top-level member other than those four, the four digest-covered members and `package_digest` (nothing binds an extra member), refuses a `package_type` or `package_version` that is not the declared one, and requires `created_by` to be a non-empty string and `created_at` an RFC 3339 instant with an offset. `created_by` and `created_at` are not tamper-evident in packages exported so far (the retained packages bind four members); a recipient that relies on them needs a digest that covers them, which is a format decision, not made here.

A recipient may configure a digest as trusted for inspection, but that still does not authenticate the issuer, prove signing time, establish institutional authority, verify successful delivery or create reliance. Recomputing hashes after changing package content can restore content self-consistency but still cannot create issuer authentication.

HMAC, where a future profile defines it, establishes shared-secret integrity. Synthetic signature profiles must bind the complete relevant record and profile metadata and require explicit recipient trust configuration. BitRep verification and Index inclusion can provide optional evidence signals but cannot create authority, adoption or recipient reliance by themselves.

## Canonicalization profiles

`integrity.canonicalization_profile` names the byte form that both digests are computed over. The validator dispatches on that declared identifier and never infers one:

- `json-sort-keys-compact-utf8-no-nan` is the legacy profile. It is unchanged, and every digest already issued under it stays valid. The Cognous export profiles (`odes_cognous_stack_export_0_1`, `odes_cognous_stack_export_0_2`) are defined only with this profile; a package that declares one of them with another canonicalization identifier fails declared-profile conformance.
- `rfc8785-jcs` is RFC 8785 (JSON Canonicalization Scheme). It is a separate profile, not a relabelling: its bytes differ from the legacy bytes for UTF-16 property order of non-BMP names, integral floats (`5.0`), small and large exponents and negative zero. Changing the label of a package does not make its digests valid, because the label sits inside the material both digests cover.
- Any other identifier, or a non-string value, gives `unsupported` for package content integrity. Nothing falls back to a default.

Permitted value domain for `rfc8785-jcs` (implemented in `odes.canonicalization`, documented there too): null, booleans, strings, lists and objects with string names; no lone surrogates; unique member names (a document with a duplicate name is refused when parsed); integers only within -(2^53 - 1) to 2^53 - 1 (larger integers are refused, not rounded); finite floats only, written with the ECMAScript number rules RFC 8785 requires; nesting up to 64 levels. Content outside the domain gives `fail` for package content integrity under that profile.

## Time and status evidence

Time-dependent acceptance requires a valid recipient evaluation time. Missing or malformed `now` prevents acceptance for the affected purpose.

Decision-critical status evidence must be explicitly configured by the recipient and bound to the relevant record/authority identity and evaluation scope. The reference status input contract requires, at minimum:

- `record_id` matching `record.decision_id`;
- `authority_basis` matching `record.authority.authority_basis`;
- `evaluation_scope` exactly matching recipient policy `evaluation_scope` (one of `recipient_reliance`, `audit`, or `inspection`);
- `evaluated_at` as a valid timestamp;
- `evidence_freshness` that is current or recent;
- present `freshness`, `revoked` and `superseded` status;
- `authority_valid_at_decision_verified` when historical authority verification is required.

Missing, stale, unsupported or mismatched status evidence prevents acceptance for the affected purpose.

## Historical and present validity

Historical admission, present validity, issuer authentication and proven signing time are separate. This reference implementation does not invent historical authority verification. The record's own `authority_valid_at_decision=true` is treated as an issuer assertion, not recipient-verified authority.

If recipient policy permits inspection of unauthenticated material, the validator reports `recipient_reliance_decision.status = informational_only`. That disposition permits review of the exported material only; it is not reliance, authorization, institutional approval, deployment approval or independent verification.

### Recipient freshness policy

Recipient policy must explicitly supply `status_max_age_seconds`, a non-negative integer (booleans, fractions, non-finite values and strings are rejected), and `evaluation_scope`. No default age or cross-scope mapping is inferred. The age is computed as `now - status_inputs.evaluated_at`; it must be between zero and the configured maximum, inclusive. Future observations fail with no implicit clock tolerance. Both timestamps must include a timezone. A source's `current` or `recent` label cannot override the computed age.

Historical authority assertions remain a separate result: an old observation may retain its configured historical assertion while failing present freshness and preventing recipient acceptance. Scope matching applies to both evaluations. These checks do not add issuer authentication.

Example policy additions:

```json
{"evaluation_scope": "recipient_reliance", "status_max_age_seconds": 300}
```

## Input shape and resource limits

Packages and recipient policies must be JSON objects, and nested `profile`, `record.verification`, `record.consumption_conditions` and `policy.status_inputs` must be objects. Other shapes return a structured `fail` decision. The `recipient-validate` command also turns malformed JSON and inputs nested too deeply for the Python interpreter into a JSON `fail` result with a nonzero exit, instead of an uncaught exception.

Residual limitation: the reference validator and exporter set no byte-size, nesting-depth, container-count or error-count budgets. They parse the whole document, make deep copies, collect every schema error, canonicalize whole objects and, for profile 0.2, re-export the retained sources. An oversized or very broad package can therefore use a lot of memory and CPU before a decision is returned. Recipients who process packages from untrusted senders should run validation under operating-system or process limits (for example memory, CPU-time and file-size limits, or a timeout), and should reject oversized files before invoking the validator. This is not a hardened parser.

## Profile 0.2 semantic consistency

Recipients must explicitly support `odes_cognous_stack_export_0_2` to inspect new
producer-2.0.0 packages. The new `replay_semantic_consistency` layer revalidates
retained original Replay through the accepted importer and checks the full
material transformation. It is additional to package integrity, authentication,
historical authority, current status and consumption-condition checks. Content
consistency is not independent producer authentication or authority verification.
See [profile 0.2](../profiles/cognous-stack-export-0.2.md).
