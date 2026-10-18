# ODES time semantics (normative draft)

Status: draft, part of the `0.1.0-draft` contract set; nothing here is frozen. Decision 35 in [`ODES-INTERCOMPONENT-CONTRACTS.md`](ODES-INTERCOMPONENT-CONTRACTS.md) records the choices and the open review item. Companion files: [`odes-time-fields.json`](odes-time-fields.json) (every time member, with its class) and [`ODES-TIME-CONFORMANCE.md`](ODES-TIME-CONFORMANCE.md) (every time comparison in the ODES validators, the Control Plane and the runtime, with file and line).

The key words MUST, MUST NOT, and MAY are used in their usual sense for a draft: they say what a conforming validator or component does, not what any component does today (the conformance table says that).

Before this document, a boundary was settled by a bare `<` or `<=` in each place that compared two times (for example decision 34 fixed one comparison). The boundary is now defined once, here, and every validator, component and contract README refers to it.

## 1. Instants

1. An instant is an RFC 3339 `date-time` string with an explicit UTC offset: `YYYY-MM-DDThh:mm:ss[.f]` followed by `Z` or `+hh:mm` or `-hh:mm`.
2. Digits are ASCII `0` to `9` only. `T` and `Z` are upper case. Seconds are mandatory. The whole string is matched: no leading or trailing character, and no trailing line break.
3. A time without an offset (a naive time) MUST be refused. It is not read as UTC or as local time.
4. Fractional seconds are optional and carry one to six digits. A seventh digit MUST be refused, never truncated or rounded, so that two different instants cannot compare as equal. Six is the limit because the reference validators (Python `datetime`) hold microseconds; an instant that needs more precision is outside this draft.
5. A leap second (`:60`) MUST be refused. The hour `24`, impossible calendar dates (for example 30 February) and years outside 0001 to 9999 MUST be refused. The offset hour is `00` to `23` and the offset minute is `00` to `59`; `+24:00` and `+00:60` are refused. `-00:00` is read as `+00:00`.
6. Instants are compared as instants: both sides are converted to UTC and compared exactly, to the microsecond. An offset never changes an outcome: `2026-10-18T14:00:00+02:00`, `2026-10-18T12:00:00Z` and `2026-10-18T12:00:00.000000+00:00` are the same instant. Comparison of the written strings is never used.
7. One member carries an instant as an integer instead: the BitRep attestation window and evaluation times in `index-evidence-registry` (`issued_at`, `not_before`, `expires_at`, `evaluated_at`, `key_status_at`) are integer seconds since 1970-01-01T00:00:00Z, as the attestation statement defines them. Rules 2 to 4 apply to them unchanged; rules 1.1 to 1.6 do not.

What the code accepts today (read 2026-10-18; the conformance table has the lines):

- ODES validators, before this change: any number of fraction digits, silently truncated to six by `datetime.fromisoformat` (so `00:00:00.0000001Z` equalled `00:00:00Z`), and offset minutes `60` (read as one more hour). After this change: at most six digits and minutes `00` to `59` (`contracts/*/validate.py`, `contracts/governed-exchange/schema.json`, and `odes.common.parse_instant`). No existing fixture used either form; the verdict of every existing fixture is unchanged.
- Control Plane and runtime, when this document was written: all read times with `datetime.fromisoformat`, so they accepted any number of fraction digits (truncated to six) and offset minutes `60`. The Control Plane comparison parsers also read a naive time as UTC; the runtime's atomic destination refused a naive time. These were recorded as mismatches; no other repository was changed.
- Control Plane and runtime, after programme 2 (re-read 2026-10-18, docs only): at Control Plane `3cd17ead` every comparison parser calls the strict `parse_instant` in `time_instant.py` (naive refused, never read as UTC; a seventh fraction digit, a leap second and offset minutes above 59 refused), and the escalation deadline in `dedupe.py` is inclusive (`now > deadline`). At runtime `11de097c` the atomic destination parser matches a strict ASCII regular expression before `datetime.fromisoformat`. The only `fromisoformat` use left in the Control Plane comparison code is the trend report period in `reason_vocabulary.py`. The conformance table carries the per-row detail.

Rationale: an instant that two parties read differently (a different zone, a dropped digit) moves a validity boundary silently. Requiring an explicit offset and an exact comparison removes both.

## 2. Validity windows

1. A validity window is the half-open interval `[not_before, expires_at)`. The start is inclusive and the end is exclusive.
2. At an evaluation instant `t`: `t < not_before` is not yet valid; `not_before <= t < expires_at` is valid; `t == expires_at` is EXPIRED; `t > expires_at` is expired.
3. A window whose `expires_at <= not_before` is empty and invalid (equal bounds included). A validator that reads both members MUST refuse it.
4. A window with one end open (only `expires_at`, or only `reversible_until`) follows the same rule at its one end.
5. A window nested in another (a delegated grant inside its parent) is contained when `child.not_before >= parent.not_before` and `child.expires_at <= parent.expires_at`. Two windows `[a, b)` and `[b, c)` share no instant and leave no gap.

Rationale: a window says when something is in force. Authority must fail closed, so the instant a bound is reached is the instant the thing stops: no instant is both valid and expired, and a consumer that evaluates at exactly `expires_at` refuses. A half-open interval also lets consecutive windows meet without overlap or gap and makes length arithmetic exact (`expires_at - not_before`).

## 3. Deadlines

1. A deadline is an inclusive instant: the last instant at which something may still be done.
2. An action, a response or a receipt at exactly the deadline counts. An evaluation at exactly the deadline finds the matter still open. OVERDUE, EXPIRED (of a check or deferral) and refusal for lateness apply only strictly after the deadline: `t > deadline`.
3. A bound on an age (`max_status_age_seconds`, `status_max_age_seconds`, `age_bound_seconds`, `observation_max_age_seconds`) is a deadline at `observed_at + bound`: an age equal to the bound is accepted, an age above it is not. A clock tolerance is read the same way: `observed_at == reference + tolerance` is accepted.

Why windows and deadlines differ: a window grants validity, so reaching its end withdraws it at once. A deadline sets a limit on a duty or on a wait, and an overdue or expired finding is held against whoever missed it. "By T" is read as including T, and the finding needs an instant that is unambiguously after T. The two are not interchangeable and a field is never both: each member is classed once, in [`odes-time-fields.json`](odes-time-fields.json). A deadline is also not a validity end: a deferral that is open at its deadline is not "valid until" that instant, it is open until the instant has passed.

Classification of the members that carry the rule (the full list, 75 members of 13 contracts and the package evaluator, is the JSON table):

| Class | Members |
|---|---|
| window | `not_before` and `expires_at` of grants, proposals, `operation_horizon`, `age_extensions` and delegated grants; `reversible_until`; governed message `expires_at`; consumption `expires_at` of a package record; the attestation window of `index-evidence-registry`; a dedupe key lifetime (`first + ttl`, `committed_at + ttl`) |
| deadline | `deadline` of `bounded-deferral` (`opened_at + max_age_seconds`); `deadline` of the freshness-clocks check opening (`recorded_at + age_bound_seconds`) and of refusal rows; status, observation and cached-snapshot age bounds; clock tolerances; closeout and recovery deadlines |
| instant | every `*_at`, `evaluation_time`, `as_of`, `row_time`, `adoption_time` and similar |
| duration | every `*_seconds` |

`reversible_until` is a window end (the class becomes irreversible at that instant), not a deadline, even though it is named like one in prose.

REVIEW (owner): the choice of an inclusive deadline against an exclusive window end is a coordinator decision, taken so that authority fails closed and obligations are read generously. It replaces the open question left by decision 34-B. If the owner prefers one boundary for both, the change is one predicate in `odes.common` and the deadline rows of the conformance table; the 29 deadline rows of the conformance table would change meaning.

## 4. Durations and ages

1. A duration is a number of seconds: an integer, or where a member says so a finite number. A boolean is not a number. `NaN`, `Infinity` and `-Infinity` MUST be refused wherever a number is read.
2. A duration is non-negative. The contracts that declare a minimum say it per member: `max_age_seconds` of `bounded-deferral` and `max_status_age_seconds` of `effect-reversibility` at least 1; `age_bound_seconds`, `from_max_age_seconds` and `to_max_age_seconds` of `freshness-clocks` at least 0; `period_seconds` of `rule-revision` at least 1. An observation age computed from two instants that is negative means the observation is later than the reference and is handled by the tolerance rule, not as a duration.
3. Range bound. No contract fixes a numeric maximum for a duration (the one fixed maximum is `9007199254740991`, on the epoch-second members of `index-evidence-registry`). What the validators enforce, after the input hardening of ODES #93 (decision 32), is representability: `start + duration` MUST be an instant inside years 0001 to 9999, and a duration that is not (the sum overflows, or the number is not finite) is a typed violation from the contract's existing families (`deadline_mismatch`, `snapshot_stale`, `schema_violation`), never an exception. The helper `odes.common.after_seconds` is that rule.
4. Ages are computed as `(later - earlier).total_seconds()` and compared with the bound without rounding. A bound is compared as written; no unit conversion is implied.

## 5. Observation, evaluation and recorded time

The three clocks keep the meaning the [freshness-clocks contract](../../contracts/freshness-clocks/README.md) gives them (`evaluated_at`: the instant the decision is judged at; `recorded_at`: when the row is written; `observed_at`: when the checked party's value was observed). This document does not redefine them. It adds only that each is an instant under section 1, that a window or deadline is evaluated at the evaluation instant a rule names (never at an unnamed "now"), and that the freshness rule that "future" is judged against the service clock re-read at the check, with staleness measured from the evaluation, is unchanged.

## 6. How validators and components refer to this document

- `src/odes/common.py` implements the rules: `parse_instant`, `instant_problem`, `after_seconds`, and the predicates `window_is_empty`, `in_window`, `window_expired`, `window_not_yet_open`, `deadline_open`, `deadline_passed`. The package evaluator (`recipient_validator.py`) uses it.
- The contract validators under `contracts/` are stdlib-only single files that components vendor with a digest, so they do not import `odes`. Each carries the same instant pattern (`INSTANT_PATTERN`) and its own comparison, and `tests/test_time_semantics.py` runs every one of them against the helper on a corpus of boundary instants and refuses any difference. A new contract that reads a time copies the pattern and adds its members to the JSON table; the test fails if a time member of a schema is missing from the table.
- A component that compares times cites the section here in its code or README and lists its comparison in the conformance table.

## 7. Changed in ODES (decision 35)

- Syntax: at most six fraction digits; offset minutes `00` to `59` (17 contract validators, the governed-exchange timestamp pattern, `odes.common`). The verdict of all 2037 fixtures that existed before is unchanged.
- Package evaluator: `recipient_validator.py` reads times and compares the consumption window through the helper (same verdicts).
- Fixtures (all single mutations of an existing fixture; `contracts/tools/build_time_boundary_fixtures.py` rebuilds them and refuses a fixture whose verdict differs from the one declared): invalid `time-seven-fraction-digits` in the 11 contracts that carry a time pattern fixture; invalid `expired-event-at-the-deadline` and `overdue-event-at-the-deadline` (freshness-clocks); invalid `cached-snapshot-used-at-the-window-end` and valid `cached-snapshot-at-exactly-the-age-bound` (effect-reversibility); valid `release-response-at-exactly-the-deadline`, valid `open-deferral-evaluated-at-exactly-the-deadline` and invalid `expiry-declared-at-exactly-the-deadline` (bounded-deferral); invalid `window-empty-equal-bounds` (non-broadening-delegation). Window and deadline boundary fixtures that already existed are unchanged (`window-inverted`, `delegation-equal-bounds`, `message-expiry-not-after-creation`, `expired-not-past-the-deadline`, `overdue-before-the-deadline`, `cached-snapshot-after-reversal-window`).

## 8. Non-claims and open items

- A conforming comparison shows the code agrees with these rules at a boundary; it does not show a clock is right, synchronised or trusted.
- The mismatches in the conformance table outside ODES were, when first written: Control Plane naive-as-UTC parsing and fraction truncation, the `dedupe.py` escalation deadline read as `>=`, a reporting period read as `(start, end]`, and the runtime parser's fraction handling. After the 2026-10-18 re-read only the reporting period in `reason_vocabulary.py` remains (a reporting period is not a validity window; the owner may declare it out of scope); the others are resolved in the Control Plane at `3cd17ead` and the runtime at `11de097c`.
- Two ODES rows are recorded and not changed: the journal contract does not refuse an empty `operation_horizon` (the producer applies no such rule), and `index-evidence-registry` `last_computed_at` allows a missing offset.
- Leap seconds: refused in this draft. A producer that must record one writes `23:59:59` of the same day and says so in a member of its own.
