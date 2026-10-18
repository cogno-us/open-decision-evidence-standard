# ODES time conformance table (draft)

Status: draft, `0.1.0-draft`; nothing here is frozen. Companion to [`ODES-TIME-SEMANTICS.md`](ODES-TIME-SEMANTICS.md) (the rules) and [`odes-time-fields.json`](odes-time-fields.json) (member classes). Decision 35 in [`ODES-INTERCOMPONENT-CONTRACTS.md`](ODES-INTERCOMPONENT-CONTRACTS.md).

Every time comparison found in the ODES validators and package evaluator, the Control Plane and the execution runtime, with its file and line, the class the rules give it, and whether the code agrees. Read from the sources named below; no other repository was edited. Line numbers are those of the named commits and will drift. `MATCH` means the boundary agrees with the rules; `MISMATCH` means it does not (or the rule is not applied). Classes: `window` (half-open), `deadline` (inclusive), `instant` (parsing and instants), `ordering` (one instant not before another; no boundary class, equality noted).

Sources:
- ODES: this repository, main `c3f97ca3` plus this change.
- Control Plane: `cogno-us/cognous-control-plane`. Rows were first read at `6b8fb627`; the rows that were MISMATCH there (parsers and the escalation deadline) were re-read at `3cd17ead` (revision 2026-10-18, below). All other Control Plane rows keep their earlier reading and line numbers and were not re-read.
- Runtime: `cogno-us/cognous-execution-runtime`. Rows were first read at `eeb4583a`; the atomic destination parser row was re-read at `11de097c`. All other runtime rows keep their earlier reading and line numbers and were not re-read.

Summary: 81 comparisons, 78 MATCH, 3 MISMATCH (after the 2026-10-18 re-read; it was 69 MATCH and 12 MISMATCH). ODES changed behaviour in two places only (instant syntax: at most six fraction digits, offset minutes 00 to 59), both listed under "Changed in ODES" in the semantics document. The remaining mismatches are two ODES gaps and one Control Plane reporting-period comparison (a reporting period is not a validity window).

Revision 2026-10-18 (docs only): the Control Plane and the runtime adopted the strict instant rules after this table was first written. At `3cd17ead` every Control Plane comparison parser calls `parse_instant` in `time_instant.py`, which refuses a naive time (`time_instant_naive`) and every other non-instant (`time_instant_invalid`), takes at most six fraction digits (a seventh is refused, never truncated), refuses a leap second and offset minutes above 59. At `11de097c` the atomic destination parser matches a strict ASCII regular expression before `datetime.fromisoformat`. The escalation deadline in `dedupe.py` is now inclusive (`now > deadline`). Rows 3 and 5 to 12 below are therefore MATCH; the earlier findings are kept in the notes so the history stays readable. The only `fromisoformat` use left in the Control Plane comparison code is `reason_vocabulary.py` (reporting period, row 4).

## Mismatches (as of the 2026-10-18 re-read)

| # | Component | Location | Finding |
|---|---|---|---|
| 1 | ODES | `contracts/control-plane-journal/validate.py:741` | operation_horizon not_before / expires_at: read only for time shape; an empty horizon (expires_at <= not_before) is not refused (rule 2 gap). Not changed: it would add a rule the producer does not apply |
| 2 | ODES | `contracts/index-evidence-registry/schema.json:98` | timestamp pattern (last_computed_at): offset optional, any fraction length: deviates from rule 1 (offset mandatory, at most six fraction digits); the member is never compared. Not changed |
| 3 | Control Plane | `src/agent_control_plane/dedupe.py:169` | escalation_due at escalation deadline: RESOLVED at `3cd17ead`: `now > deadline`; at exactly the escalation deadline the state is still open (rule 3). Was `>=` at `6b8fb627` |
| 4 | Control Plane | `src/agent_control_plane/reason_vocabulary.py:135` | reporting period of a trend report: period is (start, end]; a reporting period, not a validity window. Left out of rules 2 and 3 on purpose (the owner may declare reporting periods out of scope) |
| 5 | Control Plane | `src/agent_control_plane/bounded.py:63` | time parser used for grants, proposals, deadlines: RESOLVED at `3cd17ead`: `_parse` calls `parse_instant`; naive refused, a seventh fraction digit and offset minutes 60 refused. Was naive-as-UTC and truncating at `6b8fb627` |
| 6 | Control Plane | `src/agent_control_plane/freshness.py:136` | time parser used for extensions and deadlines: RESOLVED at `3cd17ead`: `parse_time` calls `parse_instant` |
| 7 | Control Plane | `src/agent_control_plane/policy_gate.py:295` | time parser used for authority record expiry: RESOLVED at `3cd17ead`: `_parse_time` calls `parse_instant` (a datetime input goes through `aware_utc`, which refuses a naive one) |
| 8 | Control Plane | `src/agent_control_plane/dedupe.py:103` | time parser used for the dedupe profile: RESOLVED at `3cd17ead`: `_t` calls `parse_instant` |
| 9 | Control Plane | `src/agent_control_plane/reversibility.py:82` | time parser used for reversible_until: RESOLVED at `3cd17ead`: `_utc` calls `parse_instant`; the declaration check and the comparison parser now both refuse a naive time |
| 10 | Control Plane | `src/agent_control_plane/rule_revision.py:79` | time parser used for rule rows: RESOLVED at `3cd17ead`: `_t` calls `parse_instant`, so a naive time is refused and no longer reaches a comparison with an aware one (no TypeError) |
| 11 | Control Plane | `src/agent_control_plane/decision_input_profile.py:91` | time parser used for decision inputs: RESOLVED at `3cd17ead`: `_parse_time` calls `parse_instant` and maps naive to the existing timezone refusal; a seventh fraction digit is refused, not truncated |
| 12 | Runtime | `engine/local_authority_effect.py:55` | time parser of the atomic destination: RESOLVED at `11de097c`: a strict ASCII regular expression (one to six fraction digits, offset hour 00 to 23, minute 00 to 59, offset mandatory) must match before `datetime.fromisoformat` |

## ODES validators and evaluator

| Location | Comparison | Class | Verdict | Note |
|---|---|---|---|---|
| `src/odes/recipient_validator.py:206` | record consumption_conditions.expires_at against recipient time | window | MATCH | decision 34-A; now uses common.window_expired |
| `src/odes/recipient_validator.py:228` | status evidence age against status_max_age_seconds | deadline | MATCH | an age equal to the bound is accepted; observed_at + bound is a deadline |
| `contracts/bounded-deferral/validate.py:317` | first response against the deferral deadline | deadline | MATCH | a response at exactly the deadline counts |
| `contracts/bounded-deferral/validate.py:322` | evaluation against the deferral deadline | deadline | MATCH | evaluation at exactly the deadline leaves the deferral open |
| `contracts/bounded-deferral/validate.py:378` | deadline = opened_at + max_age_seconds | deadline | MATCH | derivation, exact instant equality |
| `contracts/bounded-deferral/validate.py:419` | resolved_at of an expiry refusal against the deadline | deadline | MATCH | resolved_at records when the expiry was recorded, and the producer may stamp it at the deadline instant; the verdict itself (expired) still needs evaluation strictly after the deadline (line above). Tightening to > changes the verdict of existing valid fixtures, so not changed |
| `contracts/effect-reversibility/validate.py:434` | use time against reversible_until | window | MATCH | the window end is exclusive: at reversible_until the class is irreversible |
| `contracts/effect-reversibility/validate.py:441` | cached snapshot age against class max_status_age_seconds | deadline | MATCH | a snapshot exactly the bound old is accepted |
| `contracts/freshness-clocks/validate.py:325` | age_extension window must be non-empty | window | MATCH |  |
| `contracts/freshness-clocks/validate.py:366` | open check overdue count | deadline | MATCH | overdue only strictly after the deadline |
| `contracts/freshness-clocks/validate.py:470` | overdue/expired event written after the deadline | deadline | MATCH | an event at exactly the deadline is refused |
| `contracts/freshness-clocks/validate.py:478` | deadline = opening recorded_at + age_bound_seconds | deadline | MATCH |  |
| `contracts/freshness-clocks/validate.py:494` | extension window covers the evaluation pass | window | MATCH |  |
| `contracts/freshness-clocks/validate.py:757` | extension active at a decision | window | MATCH |  |
| `contracts/control-plane-journal/validate.py:648` | observation not later than reference + tolerance | deadline | MATCH | inclusive tolerance: observed == reference + tolerance is accepted |
| `contracts/control-plane-journal/validate.py:651` | observation age against the recorded maximum | deadline | MATCH | inclusive bound |
| `contracts/control-plane-journal/validate.py:741` | operation_horizon not_before / expires_at | window | MISMATCH | read only for time shape; an empty horizon (expires_at <= not_before) is not refused (rule 2 gap). Not changed: it would add a rule the producer does not apply |
| `contracts/non-broadening-delegation/validate.py:334` | grant window must be non-empty | window | MATCH |  |
| `contracts/non-broadening-delegation/validate.py:408` | child window inside the parent window | window | MATCH | half-open containment |
| `contracts/governed-exchange/validate.py:378` | message window must be non-empty (transport) | window | MATCH |  |
| `contracts/governed-exchange/validate.py:402` | message window must be non-empty (envelope) | window | MATCH |  |
| `contracts/index-evidence-registry/validate.py:333` | attestation window (integer epoch seconds), non-empty | window | MATCH | integer instants, same half-open rule; the validator never compares the window with an evaluation time |
| `contracts/rule-revision/validate.py:517` | rule rows as of an instant | instant | MATCH | a row recorded at t is in force at t (window start inclusive) |
| `contracts/rule-revision/validate.py:560` | flagged row strictly before adoption | instant | MATCH | a row at the adoption instant does not predate it |
| `contracts/index-evidence-registry/schema.json:98` | timestamp pattern (last_computed_at): offset optional, any fraction length | instant | MISMATCH | deviates from rule 1 (offset mandatory, at most six fraction digits); the member is never compared. Not changed |
| `contracts/freshness-clocks/validate.py:400` | a row is recorded no earlier than evaluated | ordering | MATCH | equal allowed |
| `contracts/freshness-clocks/validate.py:451` | events never go backwards in recorded_at | ordering | MATCH | equal allowed |
| `contracts/freshness-clocks/validate.py:496` | extension recorded no later than its first use | ordering | MATCH | equal allowed |
| `contracts/bounded-deferral/validate.py:507` | a deferral opens at or after the decision | ordering | MATCH | equal allowed |
| `contracts/bounded-deferral/validate.py:445` | no effect observable before RELEASE | ordering | MATCH | equal allowed |
| `contracts/effect-reversibility/validate.py:426` | a snapshot is not observed after it is used | ordering | MATCH | equal allowed |
| `contracts/effect-reversibility/validate.py:447` | a recorded closure in force at its recorded_at | ordering | MATCH | closure effective from its own instant |
| `contracts/two-party-reconciliation/validate.py:373` | commit not before the comparison | ordering | MATCH | equal allowed |
| `contracts/two-party-reconciliation/validate.py:380` | records are recorded no later than the comparison | ordering | MATCH | equal allowed |
| `contracts/governed-exchange/validate.py:399` | envelope created no earlier than the message | ordering | MATCH | equal allowed |
| `contracts/control-plane-journal/validate.py:985` | input time floors never move backwards | ordering | MATCH | equal allowed |

## Control Plane

| Location | Comparison | Class | Verdict | Note |
|---|---|---|---|---|
| `src/agent_control_plane/bounded.py:2338` | grant validity (grant_outside_validity) | window | MATCH | [not_before, expires_at) |
| `src/agent_control_plane/bounded.py:2589` | proposal not_before | window | MATCH |  |
| `src/agent_control_plane/bounded.py:2591` | proposal expires_at | window | MATCH |  |
| `src/agent_control_plane/policy_gate.py:283` | authority record expiry | window | MATCH |  |
| `src/agent_control_plane/local_authority_effect.py:384` | execution claim interval usable | window | MATCH |  |
| `src/agent_control_plane/freshness.py:161` | age extension window non-empty | window | MATCH |  |
| `src/agent_control_plane/freshness.py:186` | age extension active | window | MATCH |  |
| `src/agent_control_plane/reversibility.py:175` | reversible_until passed | window | MATCH |  |
| `src/agent_control_plane/dedupe.py:172` | dedupe key expired (key_expired) | window | MATCH | dedupe_ttl window is [first, first + ttl) |
| `src/agent_control_plane/dedupe.py:183` | escalation fired inside the key window | window | MATCH |  |
| `src/agent_control_plane/dedupe.py:169` | escalation_due at escalation deadline | deadline | MATCH | inclusive since `3cd17ead` (`now > deadline`); was `>=` at `6b8fb627` |
| `src/agent_control_plane/dedupe.py:168` | provider horizon passed | instant | MATCH | a horizon is an earliest-time threshold (window start, inclusive), not a deadline |
| `src/agent_control_plane/bounded.py:1367` | expired before dispatch (dispatch gate) | deadline | MATCH |  |
| `src/agent_control_plane/bounded.py:919` | check overdue (recovery pass) | deadline | MATCH |  |
| `src/agent_control_plane/freshness.py:229` | overdue count | deadline | MATCH |  |
| `src/agent_control_plane/bounded.py:1373` | monotonic elapsed against the age bound | deadline | MATCH | elapsed > bound; equal is still inside |
| `src/agent_control_plane/bounded.py:1870` | observation stale | deadline | MATCH |  |
| `src/agent_control_plane/bounded.py:1966` | cached input fresh | deadline | MATCH |  |
| `src/agent_control_plane/runtime_authority.py:332` | status age against the action class bound (purpose status) | deadline | MATCH | per action class max_status_age_seconds, default 60 |
| `src/agent_control_plane/reversibility.py:206` | cached snapshot age (bound compared by the caller) | deadline | MATCH |  |
| `src/agent_control_plane/local_authority_effect.py:311` | evidence projection stale | deadline | MATCH |  |
| `src/agent_control_plane/decision_input_profile.py:232` | decision input stale | deadline | MATCH |  |
| `src/agent_control_plane/bounded.py:1868` | observation in the future (tolerance) | deadline | MATCH | inclusive tolerance |
| `src/agent_control_plane/bounded.py:1964` | cached input in the future (tolerance) | deadline | MATCH |  |
| `src/agent_control_plane/bounded.py:618` | input time floor accepts up to now + tolerance | deadline | MATCH |  |
| `src/agent_control_plane/reason_vocabulary.py:135` | reporting period of a trend report | window | MISMATCH | period is (start, end]; a reporting period, not a validity window. Left out of rules 2 and 3 on purpose (the owner may declare reporting periods out of scope) |
| `src/agent_control_plane/bounded.py:63` | time parser used for grants, proposals, deadlines | instant | MATCH | strict `parse_instant` (`time_instant.py`) since `3cd17ead`: naive, a seventh fraction digit, a leap second and offset minutes above 59 are refused; earlier: naive read as UTC, fractions truncated, minutes 60 accepted |
| `src/agent_control_plane/freshness.py:136` | time parser used for extensions and deadlines | instant | MATCH | strict `parse_instant` (`time_instant.py`) since `3cd17ead`: naive, a seventh fraction digit, a leap second and offset minutes above 59 are refused; earlier: same as bounded.py |
| `src/agent_control_plane/policy_gate.py:295` | time parser used for authority record expiry | instant | MATCH | strict `parse_instant` (`time_instant.py`) since `3cd17ead`: naive, a seventh fraction digit, a leap second and offset minutes above 59 are refused; earlier: same as bounded.py |
| `src/agent_control_plane/dedupe.py:103` | time parser used for the dedupe profile | instant | MATCH | strict `parse_instant` (`time_instant.py`) since `3cd17ead`: naive, a seventh fraction digit, a leap second and offset minutes above 59 are refused; earlier: same as bounded.py |
| `src/agent_control_plane/reversibility.py:82` | time parser used for reversible_until | instant | MATCH | strict `parse_instant` (`time_instant.py`) since `3cd17ead`: naive, a seventh fraction digit, a leap second and offset minutes above 59 are refused; earlier: same as bounded.py |
| `src/agent_control_plane/rule_revision.py:79` | time parser used for rule rows | instant | MATCH | strict `parse_instant` (`time_instant.py`) since `3cd17ead`: naive, a seventh fraction digit, a leap second and offset minutes above 59 are refused; earlier: naive kept naive (TypeError against an aware time) |
| `src/agent_control_plane/decision_input_profile.py:91` | time parser used for decision inputs | instant | MATCH | strict `parse_instant` (`time_instant.py`) since `3cd17ead`: naive, a seventh fraction digit, a leap second and offset minutes above 59 are refused; earlier: naive and malformed refused, fractions truncated |
| `src/agent_control_plane/bounded.py:2147` | nonce (status-nonce/0.1) | instant | MATCH | no time comparison: an echoed nonce is compared for equality; the age of a nonce-bound read still uses the age rows above |
| `src/agent_control_plane/witness.py:140` | witness chain | instant | MATCH | no time comparison: digest, contiguity, linkage and non-decreasing counts only |
| `src/agent_control_plane/bounded.py:615` | input observation time regressed | ordering | MATCH | equal allowed |

## Execution runtime

| Location | Comparison | Class | Verdict | Note |
|---|---|---|---|---|
| `engine/local_authority_effect.py:574` | atomic destination: execution claim validity | window | MATCH | [not_before, expires_at) |
| `engine/local_authority_effect.py:590` | atomic destination: authoritative grant validity | window | MATCH |  |
| `engine/local_authority_effect.py:640` | atomic destination: evidence age | deadline | MATCH |  |
| `engine/local_authority_effect.py:55` | time parser of the atomic destination | instant | MATCH | strict ASCII regular expression before `datetime.fromisoformat` since `11de097c`: seventh fraction digit, leap second, offset minutes above 59 and a missing offset refused; earlier: fractions truncated, minutes 60 accepted |
| `engine/dedupe_destination.py:82` | operation key valid inside its TTL (float epoch clock) | window | MATCH | valid for [committed_at, committed_at + ttl) |
| `engine/dedupe_destination.py:91` | in-progress hold inside its TTL | window | MATCH |  |
| `engine/revocation_closeout.py:398` | closeout overdue | deadline | MATCH | overdue only strictly after the deadline |
| `engine/recovery_resolution.py:341` | recovery overdue count | deadline | MATCH |  |
| `engine/recovery_resolution.py:253` | synthetic observation within 24 hours | deadline | MATCH | inclusive bound |

## Not found

- Witness (`witness.py`): no time comparison; the witness record carries no time member. Nonce: no time comparison (see the row above). Both are listed so the absence is explicit.
- `contracts/execution-attempt-lifecycle` rows carry instants but the lifecycle validator compares no pair of them beyond the instant syntax shared by every validator.
- ODES `exporter.py` writes a default `expires_at` of `2027-01-01T00:00:00Z`; it compares nothing.
