from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

CANONICALIZATION_PROFILE = "json-sort-keys-compact-utf8-no-nan"
DOCUMENT_VERSION = "0.2"
SCHEMA_VERSION = "0.1"
SCHEMA_NAME = "pder-v0.1"
PROFILE_VERSION = "odes-cognous-stack-export-0.1.0"
PROFILE_ID = "odes_cognous_stack_export_0_1"
PACKAGE_TYPE = "odes_decision_evidence_export_package"
PACKAGE_VERSION = "0.1.0"

PINNED_REVISIONS = {
    "manifest": "46c950bed37fe3812000895430bc0312d29e37ce",
    "authority_context": "fb3d97938969a89e149e8ff8db2756091d1233fc",
    "control_plane": "283500652d47a692fb0b99a1172a6d5faffbd9a7",
    "moltbot_safe": "1d308faf664c504b6e310db3c7a310153ef7b067",
    "replay": "f63ce914504dd06813c4ccd199b0570dbd8dd427",
    "governance_evidence_pack": "c699c1fb7c4f8057631c4e5909d11a721c2c958d",
    "bitrep": "5b5077dafde232a7801cb425c4efddcffb468723",
    "index": "d5e45d275cb301d9684b543e93b05997991d1cf2",
}


PROFILE_V2_ID = "odes_cognous_stack_export_0_2"
PROFILE_V2_VERSION = "odes-cognous-stack-export-0.2.0"
SUPPORTED_V2_CONTROL_PLANE_REVISIONS = (
    "2ea9528eeb87e14ff10f05de06473122b9df540f",
    "248d899634d9db3518e831bc7ab568a48733f825",
)
SUPPORTED_V2_REPLAY_REVISIONS = (
    "274543f1cd7171784a923a8e37015017a0d8bc9d",
    "043830b56595cecddfa65c064afd1c0b95e64792",
)
PINNED_V2_REVISIONS = {
    **PINNED_REVISIONS,
    "control_plane": "248d899634d9db3518e831bc7ab568a48733f825",
    "moltbot_safe": "177354e959cc78c59c1a776f018cfbfbf28c927b",
    "replay": "043830b56595cecddfa65c064afd1c0b95e64792",
}


MERGED_PROFILE_VERSION = "odes-cognous-stack-export-0.2.1"
MERGED_REVISIONS = {
    **PINNED_V2_REVISIONS,
    "control_plane": "d3dadee70bd319812b207389ab1e0f6efe511916",
    "moltbot_safe": "c3c3ee7188b9367cf70b08074b9c40a5c70c94ac",
    "replay": "459e4ba62fca49364aebb0050cd5fb2dd5a71bfa",
}
REFUSAL_PROFILE_VERSION = "odes-cognous-stack-export-0.2.2-refusal-candidate"
REFUSAL_REVISIONS = {"manifest": PINNED_REVISIONS["manifest"]} | {"control_plane": "c7f122ba3a6e39f9268a7163c99be3ee514cd97e", "moltbot_safe": "309e194c1b0a3de23e11e20133e6eaf88875e48a", "replay": "83fbaf2a0f6f071aca1ea0af859eb8fc6385c26a"}
SECURITY_PROFILE_VERSION = "odes-cognous-stack-export-0.2.3-security-runtime-candidate"
SECURITY_REVISIONS = {"manifest": "e385f8c19b4444817a8b84b72ed6edbc37deb807",
    "replay": "3601fb218d5c02f5d86e55d2cf33983e5e130ac3",
    "control_plane": "996baeb476c8745b1a58ddc968b9eecc6a39b76b",
    "moltbot_safe": "fd6b76fa0e85feb5b67324114bf790d3a12fdaf1"}
# F5b merged generation (CP a34c3dc2 / runtime 4a83b175 / Replay def0ee0f /
# Manifest 2c36bcd0). Added alongside, not instead of, SECURITY_REVISIONS so
# retained evidence from that generation stays accepted. Each generation is an
# exact tuple keyed by its Control Plane revision; components never mix across
# generations.
F5B_PROFILE_VERSION = "odes-cognous-stack-export-0.2.4-security-runtime-f5b-candidate"
F5B_REVISIONS = {"manifest": "2c36bcd0b620dbfe7ad924bc7196a3f0c04c5c5e",
    "replay": "def0ee0f3af713283ea3cd13f0caf79e1607b651",
    "control_plane": "a34c3dc26f84a767a55f9d5c89dc0b53e63fefa5",
    "moltbot_safe": "4a83b175d2ef0e65a7ee22a0513bb94a5fdf3a6f"}
# P4 generation (alpha decoupling, qualification P4): Control Plane 26a7e659 / runtime 3024ef6e / Manifest 2c36bcd0
# with the Replay revision below, the producers after the execution-attempt lifecycle contract work. Added beside
# F5b (retained F5b evidence stays accepted); an exact tuple keyed by its Control Plane revision, never mixed.
# Alpha scaffolding: removed with the other hard pins at end-of-alpha (P5).
P4_PROFILE_VERSION = "odes-cognous-stack-export-0.2.5-security-runtime-p4-candidate"
P4_REVISIONS = {"manifest": "2c36bcd0b620dbfe7ad924bc7196a3f0c04c5c5e",
    "replay": "9aab3f6c34d2721ef1be3f6468b71dc3bad99a2a",
    "control_plane": "26a7e6594eb535827ccc248cbca36a7d119d613b",
    "moltbot_safe": "3024ef6e6ecf7da22e5f4fdf90d873f93b2a55c9"}
SECURITY_RUNTIME_GENERATIONS = {
    SECURITY_REVISIONS["control_plane"]: (SECURITY_PROFILE_VERSION, SECURITY_REVISIONS),
    F5B_REVISIONS["control_plane"]: (F5B_PROFILE_VERSION, F5B_REVISIONS),
    P4_REVISIONS["control_plane"]: (P4_PROFILE_VERSION, P4_REVISIONS),
}
SECURITY_RUNTIME_CP_REVISIONS = frozenset(SECURITY_RUNTIME_GENERATIONS)
ALL_V2_CONTROL_PLANE_REVISIONS = (*SUPPORTED_V2_CONTROL_PLANE_REVISIONS, MERGED_REVISIONS["control_plane"], REFUSAL_REVISIONS["control_plane"], SECURITY_REVISIONS["control_plane"], F5B_REVISIONS["control_plane"], P4_REVISIONS["control_plane"])


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _refuse_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError("duplicate member name in JSON object")
        seen[key] = value
    return seen


def _refuse_constant(name: str) -> Any:
    raise ValueError(f"non-finite number {name} is not JSON")


def _parse_float(text: str) -> float:
    number = float(text)
    if not math.isfinite(number):
        raise ValueError("number outside the finite range")
    return number


def load_json(path: str | Path) -> Any:
    """Strict JSON: UTF-8 only, no duplicate members, no NaN or Infinity (including by overflow)."""
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle, object_pairs_hook=_refuse_duplicates, parse_constant=_refuse_constant, parse_float=_parse_float)


def dump_json(value: Any, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------- time semantics
# Normative text: docs/engineering/ODES-TIME-SEMANTICS.md (draft). Field table: docs/engineering/odes-time-fields.json.
# The contract validators under contracts/ stay stdlib-only single files (they are vendored); they carry the same
# instant pattern, and tests/test_time_semantics.py checks each of them against this module.

MAX_FRACTION_DIGITS = 6  # a datetime holds microseconds; more digits are refused, never truncated

INSTANT_PATTERN = (r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?"
                   r"(Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])")
_INSTANT = re.compile(INSTANT_PATTERN)
# The same shape without a mandatory offset: tells a naive time from a malformed one in messages only.
_NAIVE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?")


def parse_instant(value: Any) -> datetime | None:
    """An RFC 3339 instant with an explicit offset as a timezone-aware datetime, or None.

    Refused (None): non-strings, naive times, lower-case ``t``/``z``, non-ASCII digits, a trailing line break, missing seconds,
    more than six fractional digits, a leap second (``:60``), an hour of 24, impossible calendar dates, years outside 0001-9999.
    Aware datetimes compare as instants, so an offset never changes an outcome.
    """
    if not isinstance(value, str) or _INSTANT.fullmatch(value) is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


def instant_problem(value: Any) -> str | None:
    """None for a valid instant; else ``unavailable`` (absent or empty), ``naive`` (no offset) or ``malformed``."""
    if not isinstance(value, str) or not value:
        return "unavailable"
    if parse_instant(value) is not None:
        return None
    return "naive" if _NAIVE.fullmatch(value) is not None else "malformed"


def parse_time(value: str | None) -> datetime | None:
    """Kept for callers that expect ValueError: None for an empty value, else the instant or ValueError (naive included)."""
    if not value:
        return None
    parsed = parse_instant(value)
    if parsed is None:
        raise ValueError("not an RFC 3339 time with ASCII digits and a UTC offset")
    return parsed


def after_seconds(start: datetime, seconds: Any) -> datetime | None:
    """``start`` plus a duration in seconds; None when the duration is not a finite number or the sum is not representable."""
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds):
        return None
    try:
        return start + timedelta(seconds=seconds)
    except (OverflowError, ValueError):
        return None


# Validity windows are half-open: [not_before, expires_at). Deadlines are inclusive: open through the deadline itself.

def window_is_empty(not_before: datetime, expires_at: datetime) -> bool:
    return expires_at <= not_before


def in_window(at: datetime, not_before: datetime, expires_at: datetime) -> bool:
    return not_before <= at < expires_at


def window_expired(at: datetime, expires_at: datetime) -> bool:
    return at >= expires_at


def window_not_yet_open(at: datetime, not_before: datetime) -> bool:
    return at < not_before


def deadline_open(at: datetime, deadline: datetime) -> bool:
    """An action, response or evaluation at exactly the deadline still counts."""
    return at <= deadline


def deadline_passed(at: datetime, deadline: datetime) -> bool:
    return at > deadline
