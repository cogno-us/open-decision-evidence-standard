# Cognous Stack Export 0.2, explicit restriction semantics

Status: Draft implementation profile. Contract labels are unchanged (`0.1.0-draft`). The base schema `pder-v0.1` is unchanged.

Profile id: `odes_cognous_stack_export_0_2_restrictions`. Profile version: the generation's profile version of [profile 0.2](cognous-stack-export-0.2.md) followed by `+restriction-semantics-1`. Recipients must list this id in `supported_profiles` to evaluate such a package; a policy that lists only `odes_cognous_stack_export_0_2` does not accept it, and relabelling a package between the two ids fails profile conformance.

Exports under the existing profile ids are unchanged: an absent restriction value is still exported as `true`. The exporter selects this profile only when called with `restriction_semantics="explicit"` and only for producer-2.0.0 generations.

## Meaning of a restriction value

`risk_coordinates.restricted_use_flag` and `prohibited_use_flag` are booleans in the base schema, which cannot say "unknown". This profile records the state of each value in `provenance.restriction_semantics`:

| Source value (retained proposal `risk_metadata`) | `state` | Base boolean |
| --- | --- | --- |
| `true` | `explicit_true` | `true` |
| `false` | `explicit_false` | `false` |
| absent or `null` | `unknown` | `true`, a conservative placeholder |
| any other value | export refused | |

An unknown value is never exported as `false`. The placeholder `true` does not establish a restriction or a prohibition and is not advertised as one. `jurisdiction` follows the same rule: absent is recorded with state `unknown` and the text `unknown`, which never matches a recipient jurisdiction (not even a policy whose jurisdiction is the text `unknown`).

The exporter refuses contradictory metadata (prohibited use `true` with restricted use `false`), non-boolean flags, a malformed jurisdiction, and an explicit `false` that cannot be attributed to a retained source record. `provenance.restriction_semantics.source` names that record (`record_type`, `record_id`, `record_hash`); an explicit `false` requires it.

## Mandatory limitation

When any value is unknown, `provenance.limits` must contain the limitation text defined in `odes.common.RESTRICTION_UNKNOWN_LIMIT`. The package digest covers it.

## Recipient evaluation

The `consumption_conditions` layer additionally fails when `restriction_semantics` is missing or unsupported; when a base boolean does not match its declared state; when a value is unknown (the reason says the restriction is unknown and is not an established prohibition); when the mandatory limitation is missing; when an explicit `false` is not attributable; and when the jurisdiction is unknown. An unknown or unauthorized case cannot reach `pass`, and cannot reach `informational_only` because that value requires every layer except issuer authentication to pass. The Replay layer re-exports the retained sources under the same restriction semantics and compares the full material.

A nullable or tri-state base-schema field is a separately reviewed future version and is not part of this profile.
