from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
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
    "replay": "7c6888fb0bf3218b3e315bc22714c4406f6d3908",
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


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(value: Any, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    return datetime.fromisoformat(text)
