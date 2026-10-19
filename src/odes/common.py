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
# Explicit restriction semantics: a separate profile id for the behaviour that records whether each restriction value is explicit or
# unknown. Legacy exports (PROFILE_V2_ID) are unchanged. The version is the generation's profile version plus the suffix.
PROFILE_V2_RESTRICTIONS_ID = "odes_cognous_stack_export_0_2_restrictions"
RESTRICTION_VERSION_SUFFIX = "+restriction-semantics-1"
RESTRICTION_SEMANTICS_VERSION = "restriction-semantics-1"
RESTRICTION_UNKNOWN_LIMIT = ("Restriction semantics: where a restriction or jurisdiction value is recorded with state unknown, the record carries true "
                             "(or the text unknown) as a conservative placeholder. The placeholder does not establish a restriction, a prohibition "
                             "or a jurisdiction, and a recipient may not treat the record as unrestricted.")
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
# P2 generation (Programme 2 producers): Control Plane 2bac7875 / runtime 6b16962d / Replay 6a6a4774 / Manifest ff549082.
# Added beside P4 (retained P4 evidence stays accepted); an exact tuple keyed by its Control Plane revision, never mixed.
# The tuple was moved in place twice: the earlier P2 tuples (3cd17ead / 11de097c / 46e8bd7c / 2c36bcd0, then 6093aca7 /
# 62a5cc15 / c8e665bd / f9ae8527; then the runtime c4a05883 and Replay 2a7963b1 of the same Control Plane and Manifest) are not kept, so a bundle of any of them is no longer accepted as P2 (decisions 38, 41 and 42). The profile version string is unchanged: the generation
# is still one non-selected candidate. Alpha scaffolding: removed with the other hard pins at end-of-alpha (P5).
P2_PROFILE_VERSION = "odes-cognous-stack-export-0.2.6-security-runtime-p2-candidate"
P2_REVISIONS = {"manifest": "ff5490828b2bf7f6a976da209f3f533701855687",
    "replay": "6a6a477495ac24e813f12bb0fe314acfe8bac9cf",
    "control_plane": "2bac7875391cad0a431fa0d75208b7ade39743e3",
    "moltbot_safe": "6b16962db140590b808f02b5c2cb11a217aec46f"}
SECURITY_RUNTIME_GENERATIONS = {
    SECURITY_REVISIONS["control_plane"]: (SECURITY_PROFILE_VERSION, SECURITY_REVISIONS),
    F5B_REVISIONS["control_plane"]: (F5B_PROFILE_VERSION, F5B_REVISIONS),
    P4_REVISIONS["control_plane"]: (P4_PROFILE_VERSION, P4_REVISIONS),
    P2_REVISIONS["control_plane"]: (P2_PROFILE_VERSION, P2_REVISIONS),
}
SECURITY_RUNTIME_CP_REVISIONS = frozenset(SECURITY_RUNTIME_GENERATIONS)
ALL_V2_CONTROL_PLANE_REVISIONS = (*SUPPORTED_V2_CONTROL_PLANE_REVISIONS, MERGED_REVISIONS["control_plane"], REFUSAL_REVISIONS["control_plane"], SECURITY_REVISIONS["control_plane"], F5B_REVISIONS["control_plane"], P4_REVISIONS["control_plane"], P2_REVISIONS["control_plane"])


def accepted_replay_revisions(control_plane_revision: str) -> frozenset[str]:
    """The Replay revisions the accepted validators for a Control Plane generation name (empty when the generation is unknown)."""
    if control_plane_revision in SECURITY_RUNTIME_GENERATIONS:
        return frozenset({SECURITY_RUNTIME_GENERATIONS[control_plane_revision][1]["replay"]})
    if control_plane_revision == REFUSAL_REVISIONS["control_plane"]:
        return frozenset({REFUSAL_REVISIONS["replay"]})
    if control_plane_revision == MERGED_REVISIONS["control_plane"]:
        return frozenset({MERGED_REVISIONS["replay"]})
    if control_plane_revision in SUPPORTED_V2_CONTROL_PLANE_REVISIONS:
        return frozenset(SUPPORTED_V2_REPLAY_REVISIONS)
    return frozenset()


def all_accepted_replay_revisions() -> frozenset[str]:
    """Every Replay revision any accepted generation names. Older packages are re-validated with a newer accepted Replay
    (``recipient_validator._normalized_replay_material``), so the installed code must be one of these, not necessarily the package's own."""
    return frozenset(SUPPORTED_V2_REPLAY_REVISIONS) | frozenset(
        accepted for cp in ALL_V2_CONTROL_PLANE_REVISIONS for accepted in accepted_replay_revisions(cp))


def installed_replay_revision() -> str | None:
    """The commit the imported ``agent_replay_bundle`` comes from, or None when unknown.

    Order: the module's own git checkout (editable or in-tree installs), then pip's ``direct_url.json`` VCS commit. A copy in
    site-packages without either is unknown; unknown is never a pass.
    """
    import importlib.metadata as metadata
    import importlib.util
    import subprocess
    try:
        spec = importlib.util.find_spec("agent_replay_bundle")
        origin = Path(spec.origin).resolve() if spec is not None and spec.origin else None
    except Exception:
        origin = None
    if origin is not None:
        for parent in list(origin.parents)[:4]:
            if (parent / ".git").exists():
                try:
                    out = subprocess.run(["git", "-C", str(parent), "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=20).stdout.strip()
                except Exception:
                    break
                return out if re.fullmatch(r"[0-9a-f]{40}", out) else None
    try:
        names = metadata.packages_distributions().get("agent_replay_bundle") or []
        if len(set(names)) != 1:
            return None
        raw = metadata.distribution(names[0]).read_text("direct_url.json")
        commit = ((json.loads(raw).get("vcs_info") or {}).get("commit_id")) if raw else None
        return commit if isinstance(commit, str) else None
    except Exception:  # metadata trouble is "unknown", never a pass
        return None


def installed_replay_checkout_dirty() -> bool | None:
    """True when the imported ``agent_replay_bundle`` comes from a git checkout with uncommitted changes, False when that checkout is
    clean, None when it is not a checkout (or git cannot say). A dirty checkout runs code no commit names, so it is not a qualified build."""
    import importlib.util
    import subprocess
    try:
        spec = importlib.util.find_spec("agent_replay_bundle")
        origin = Path(spec.origin).resolve() if spec is not None and spec.origin else None
    except Exception:
        return None
    if origin is None:
        return None
    for parent in list(origin.parents)[:4]:
        if (parent / ".git").exists():
            try:
                out = subprocess.run(["git", "-C", str(parent), "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True,
                                     check=True, timeout=20).stdout
            except Exception:
                return None
            return any(not _generated_path(line[3:]) for line in out.splitlines() if line.strip())
    return None


def _generated_path(path: str) -> bool:
    """Packaging and bytecode files that an editable install or the interpreter rewrites (a checkout may track them); they are not
    source, so rewriting them does not make the checkout run different code."""
    path = path.strip().strip('"')
    return ".egg-info/" in path or "/__pycache__/" in path or path.startswith("__pycache__/") or path.endswith((".pyc", ".pyo"))


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


# Input budgets for validator-side inputs (packages, policies, records). Starting values, reversible before the first freeze.
# Basis: the qualification repository's measured admission budget (results/u1-security-20261015/budget-measurement.json: 1 MiB, depth 20,
# 16,384 nodes, 4,096 items, 256 fields, 65,536-character strings), kept for every dimension because every valid fixture and producer-v2
# example is within it (largest valid input: 138,883 bytes, 3,298 nodes, 14 levels of nesting). The plan's 8 MiB / depth 64 / 100,000 nodes
# are the fallback for a dimension a valid input exceeds. The aggregate string budget equals the byte budget; there is no decompression.
INPUT_LIMITS = {"max_bytes": 1_048_576, "max_depth": 20, "max_nodes": 16_384, "max_items": 4_096, "max_fields": 256, "max_string": 65_536}
MAX_REPORTED_ERRORS = 100
BUDGET_EXCEEDED = "budget_exceeded"


class BudgetExceeded(ValueError):
    """An input is over a budget. Closed reason code ``budget_exceeded``; distinct from malformed input."""

    code = BUDGET_EXCEEDED

    def __init__(self, dimension: str, limit: int):
        super().__init__(f"{BUDGET_EXCEEDED}: input exceeds {dimension} {limit}")
        self.dimension = dimension
        self.limit = limit


def check_budget(value: Any, limits: dict[str, int] | None = None) -> None:
    """Refuse a parsed value over a budget. Iterative (no recursion), stops at the first breach, so a cyclic or huge value is bounded."""
    limits = limits or INPUT_LIMITS
    nodes = 0
    total_chars = 0
    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > limits["max_nodes"]:
            raise BudgetExceeded("max_nodes", limits["max_nodes"])
        if isinstance(item, str):
            total_chars += len(item)
            if len(item) > limits["max_string"]:
                raise BudgetExceeded("max_string", limits["max_string"])
        elif isinstance(item, (dict, list, tuple)):
            if depth + 1 > limits["max_depth"]:
                raise BudgetExceeded("max_depth", limits["max_depth"])
            if isinstance(item, dict):
                if len(item) > limits["max_fields"]:
                    raise BudgetExceeded("max_fields", limits["max_fields"])
                for key, child in item.items():
                    if isinstance(key, str):
                        total_chars += len(key)
                        if len(key) > limits["max_string"]:
                            raise BudgetExceeded("max_string", limits["max_string"])
                    stack.append((child, depth + 1))
            else:
                if len(item) > limits["max_items"]:
                    raise BudgetExceeded("max_items", limits["max_items"])
                stack.extend((child, depth + 1) for child in item)
        if total_chars > limits["max_bytes"]:
            raise BudgetExceeded("max_bytes", limits["max_bytes"])


def _nesting_exceeds(text: str, max_depth: int) -> bool:
    """Bracket nesting over the raw text, ignoring string contents; a cheap pre-parse bound that needs no recursion."""
    depth = 0
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch in "[{":
            depth += 1
            if depth > max_depth:
                return True
        elif ch in "]}":
            depth -= 1
    return False


def load_json(path: str | Path, *, limits: dict[str, int] | None = None) -> Any:
    """Strict JSON: UTF-8 only, no duplicate members, no NaN or Infinity (including by overflow).

    With ``limits``, the byte budget is checked before reading more than the budget, the nesting budget before parsing, and the
    remaining budgets after parsing; an over-budget input raises ``BudgetExceeded``. Without ``limits`` behaviour is unchanged.
    """
    with Path(path).open("rb") as handle:
        raw = handle.read(limits["max_bytes"] + 1) if limits else handle.read()
    if limits and len(raw) > limits["max_bytes"]:
        raise BudgetExceeded("max_bytes", limits["max_bytes"])
    text = raw.decode("utf-8")
    if limits and _nesting_exceeds(text, limits["max_depth"]):
        raise BudgetExceeded("max_depth", limits["max_depth"])
    value = json.loads(text, object_pairs_hook=_refuse_duplicates, parse_constant=_refuse_constant, parse_float=_parse_float)
    if limits:
        check_budget(value, limits)
    return value


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

INSTANT_PATTERN = (r"[0-9]{4}-[0-9]{2}-[0-9]{2}T(?:[01][0-9]|2[0-3]):[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?"
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
