"""Build the valid profile-on journal fixtures from captured run records (step 2 of 3; step 3 is mutate_invalid_fixtures.py).

    python build_fixtures.py <raw-root> <contracts/control-plane-journal dir> <control-plane-commit>

<raw-root> holds one directory per capture: operation-identity/, rule-revision/, freshness-clocks/ (written by the capture_fixtures.py
of those three contracts) and stack/ (capture_profile_stack.py here), all captured from the same Control Plane commit. Each run record
is written unchanged apart from (a) the two journal contract markers the producer's export does not carry and (b) normalising random
uuids, nonces and the process owner to synthetic ones (stable order of first appearance, as the sidecar builds do). Re-running it on a
second capture of the same code reproduces the fixtures byte for byte. Nothing is hand-written.

Not built: `default-path` (profile unset; the existing default fixtures cover it) and `freshness-report` (the capture appends two
hand-made check events with no decision to feed refusal_trends; the journal contract rightly refuses that, and it is not producer output).
"""
import json, re, sys
from pathlib import Path

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
NONCE = re.compile(r"[0-9a-f]{32}")
BARE_NONCE = re.compile(r"(?<![0-9a-f:])[0-9a-f]{32}(?![0-9a-f])")
KINDS = {"decision_id": "decision", "attempt_id": "attempt", "check_id": "check", "join_id": "join", "renewal_id": "renewal",
         "refusal_id": "refusal", "extension_id": "extension", "run_id": "recovery-run"}


def normalise(doc):
    text = json.dumps(doc, ensure_ascii=False)
    counters, mapping = {}, {}

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if isinstance(v, str) and UUID.fullmatch(v) and v not in mapping:
                    kind = KINDS.get(k, "id")
                    counters[kind] = counters.get(kind, 0) + 1
                    mapping[v] = f"syn-{kind}-{counters[kind]}"
                elif k == "nonce" and isinstance(v, str) and NONCE.fullmatch(v) and v not in mapping:
                    counters["nonce"] = counters.get("nonce", 0) + 1
                    mapping[v] = f"syn-nonce-{counters['nonce']:02d}"
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(doc)
    for old, new in mapping.items():
        text = text.replace(old, new)
    out = json.loads(text)
    n = [0]

    def owners(x):
        if isinstance(x, dict):
            if set(x) == {"pid", "token"}:
                key = x["token"]
                if key not in mapping:
                    n[0] += 1
                    mapping[key] = f"syn-owner-token-{n[0]}"
                x["pid"] = "1001"
                x["token"] = mapping[key]
            else:
                for v in x.values():
                    owners(v)
        elif isinstance(x, list):
            for v in x:
                owners(v)
    owners(out)
    left = UUID.findall(json.dumps(out)) + BARE_NONCE.findall(json.dumps(out))
    assert not left, left
    return out



RAW, CDIR, CP = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
DEST = CDIR / "fixtures" / "valid"
for old in DEST.glob("profile-*.json"):
    old.unlink()

# (capture dir, scenario, what it shows)
SCENARIOS = [
 ("operation-identity", "op-normal", "operation-identity/0.1: an admitted operation, one join row per attempt, the shared check_id; the operation_id sits on the binding's runtime_authority block."),
 ("operation-identity", "op-delayed-first-attempt-rejected-after-renewal", "operation-identity/0.1: a delayed first attempt rejected after an accepted renewal; four attempt rows, renewal row and join rows."),
 ("operation-identity", "op-duplicate-submission-reconciled-existing", "operation-identity/0.1: a duplicate submission of one operation reconciles to the existing effect."),
 ("operation-identity", "op-effect-time-refusal-carries-check-id", "operation-identity/0.1: an effect-time refusal row carries the check_id of the completed check."),
 ("operation-identity", "op-grant-mismatch-held", "operation-identity/0.1: an operation whose grant does not match is held; no join, no attempt."),
 ("operation-identity", "op-lost-ack-then-reconciled-existing", "operation-identity/0.1: a lost acknowledgement, then the retry reconciles to the existing effect."),
 ("operation-identity", "op-operation-id-missing-held", "operation-identity/0.1: the profile is on but the request carries no operation_id: held, no operation row."),
 ("operation-identity", "op-renewal-accepted", "operation-identity/0.1: an issuer renewal accepted (operation_renewals row) after an applied effect."),
 ("operation-identity", "op-renewal-refused-not-admitted-and-not-new", "operation-identity/0.1: refused renewals are kept as rows (operation not admitted; revision not new)."),
 ("operation-identity", "op-worker-self-renewal-then-unrecorded-hold", "operation-identity/0.1: a renewal written by the worker is not the issuer's and leaves the operation held."),
 ("rule-revision", "rule-adopted-decision-and-refusal-rows", "rule-revision/0.1: an adopted policy revision; the decision and the effect-time refusal row carry rule_identity."),
 ("rule-revision", "rule-edit-in-place-held-then-readopted", "rule-revision/0.1: a policy edited in place holds, then a new revision row re-adopts it."),
 ("rule-revision", "rule-host-rule-unadopted-does-not-gate", "rule-revision/0.1: a host-configured rule with no adopted revision is reported but does not gate."),
 ("rule-revision", "rule-refused-revision-attempts-kept", "rule-revision/0.1: refused revision attempts are kept as rule_revision_refusals rows."),
 ("rule-revision", "rule-reports", "rule-revision/0.1: revision rows next to decisions that the trend, arity and recomputability reports are computed over."),
 ("rule-revision", "rule-unsigned-row-resolves-unknown", "rule-revision/0.1: an unsigned revision row resolves the policy to unknown and the decision holds."),
 ("rule-revision", "rule-unsigned-then-resigned-by-supersession", "rule-revision/0.1: an unsigned row superseded by a signed one."),
 ("freshness-clocks", "clocks-follow-the-service-clock", "freshness/0.1: evaluated_at and recorded_at on decision, attempt, resolution-check and journal rows; the events of one check are stamped at different instants."),
 ("freshness-clocks", "operation-rows-carry-the-clocks", "freshness/0.1 with operation-identity/0.1: operation, join and renewal rows carry the clocks."),
 ("freshness-clocks", "deadline-at-opening-within-bound", "freshness/0.1: the check opens with a deadline; a 59 s stall before dispatch is inside the bound."),
 ("freshness-clocks", "expired-before-dispatch", "freshness/0.1: a 61 s stall passes the deadline: failed attempt (check_expired_before_dispatch), refusal row with deadline, a terminal expired event."),
 ("freshness-clocks", "expired-with-operation-join", "freshness/0.1 with operation-identity/0.1: the expiry with a join row whose attempt is failed."),
 ("freshness-clocks", "expired-then-retry-dispatches", "freshness/0.1: after an expiry a fresh check dispatches; the failed expired attempt is excused from the one-attempt-per-effect rule."),
 ("freshness-clocks", "observation-clock-decoupled", "freshness/0.1: a live observation clock stamps the observation after the evaluation pass; not 'future' under the profile."),
 ("freshness-clocks", "overdue-reported-not-closed", "freshness/0.1: a live check past its deadline gets a non-terminal overdue event, then completes."),
 ("freshness-clocks", "reaper-closes-the-dead-and-reports-the-late", "freshness/0.1: the reaper closes an abandoned check as interrupted and records a recovery run."),
 ("freshness-clocks", "extension-recorded-and-applied", "freshness/0.1 with rule-revision/0.1: a signed age extension recorded and applied; the check opens with age_bound_seconds and extension_id."),
 ("freshness-clocks", "extension-refusals-kept", "freshness/0.1: refused age extensions are kept as age_extension_refusals rows."),
 ("freshness-clocks", "extension-withdrawn-at-use", "freshness/0.1: a signer withdrawn from the configured set after an extension was used; the next decision holds."),
 ("freshness-clocks", "nonce-bound-reads", "freshness/0.1: nonce-bound reads (age_basis nonce_bound, the check opening carries the nonce)."),
 ("freshness-clocks", "nonce-replay-rejected", "freshness/0.1: a replayed response reads as nonce_mismatch (a profile read state); the effect is refused."),
 ("freshness-clocks", "lease-unavailable-holds", "freshness/0.1: the per-check lease cannot be taken: a hold for check_lease_unavailable alone, with no journal and no vocabulary version."),
 ("freshness-clocks", "source-asserted-without-capability", "freshness/0.1: a resolver without the nonce capability: every read is source_asserted."),
 ("stack", "all-profiles-applied", "freshness, operation identity, rule revision and holder inventory on together: authorized, applied, then an issuer renewal."),
 ("stack", "all-profiles-expired-before-dispatch", "All four profiles on together: the dispatch gate refuses an expired check (failed attempt, refusal with deadline, join row)."),
 ("stack", "all-profiles-holder-inventory-missing", "All four profiles on, a class flagged requires_revocation_assurance and no inventory: held with holder_inventory_missing (holder-inventory/0.1 adds no record member; it surfaces as a reason)."),
]
for capture, scenario, why in SCENARIOS:
    cap = json.load(open(RAW / capture / f"{scenario}.json"))
    run = normalise(cap["run"])
    doc = {"contract": "control-plane-journal", "contract_version": "0.1.0-draft", "producer": "control-plane", **run}
    fx = {"fixture_id": f"profile-{scenario}", "synthetic": True, "expected_outcome": "accept",
          "reason": f"Real producer run, unchanged (Control Plane {CP}, opt-in profiles, synthetic proposals, throwaway store). {why} Ids, nonces and the process owner are synthetic.",
          "provenance": {"source": "control-plane-capture", "control_plane_commit": CP, "capture": capture, "scenario": scenario},
          "document": doc}
    (DEST / f"{fx['fixture_id']}.json").write_text(json.dumps(fx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(len(SCENARIOS), "fixtures written")
