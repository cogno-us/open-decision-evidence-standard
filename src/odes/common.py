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
PINNED_V2_REVISIONS = {
    **PINNED_REVISIONS,
    "control_plane": "2ea9528eeb87e14ff10f05de06473122b9df540f",
    "moltbot_safe": "177354e959cc78c59c1a776f018cfbfbf28c927b",
    "replay": "274543f1cd7171784a923a8e37015017a0d8bc9d",
}


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
