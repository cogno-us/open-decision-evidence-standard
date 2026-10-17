#!/usr/bin/env python3
"""Vendor an ODES behavioural contract into a component repository.

A component repository does not depend on the ODES repository at test time. It carries a pinned copy of the
contract (schema, reference validator, README, golden fixtures) plus ``CONTRACT.json``, which declares the
contract, its version, the ODES commit it was copied from, the conformance level the component claims and the
SHA-256 of every file. A component test (``check`` mode) recomputes the digests so drift is visible.

Usage:
    vendor_contract.py copy  --contract execution-attempt-lifecycle --dest DIR --role producer|consumer \
                             --level S|L|P [--odes-commit SHA]
    vendor_contract.py check --dest DIR

Stdlib only. Nothing here grants authority or establishes external truth: a passing check shows the vendored copy
is unmodified, nothing more.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

CONTRACTS = Path(__file__).resolve().parents[1]
LEVELS = {"S": "structure only", "L": "structure and lifecycle rules", "P": "structure, rules and a real producer run"}
COPY_FILES = ("README.md", "schema.json", "validate.py")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _files(root: Path) -> list[Path]:
    out = [root / name for name in COPY_FILES]
    out += sorted((root / "fixtures").rglob("*.json"))
    return out


def _odes_commit() -> str:
    try:
        return subprocess.run(["git", "-C", str(CONTRACTS), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return "unknown"


def copy(contract: str, dest: Path, role: str, level: str, odes_commit: str | None) -> dict:
    src = CONTRACTS / contract
    if not src.is_dir():
        raise SystemExit(f"unknown contract: {contract}")
    if role not in {"producer", "consumer"} or level not in LEVELS:
        raise SystemExit("role must be producer|consumer and level S|L|P")
    meta = json.loads((src / "schema.json").read_text(encoding="utf-8"))
    version = meta["properties"]["contract_version"]["const"]
    if dest.exists():
        shutil.rmtree(dest)
    for f in _files(src):
        target = dest / f.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, target)
    manifest = {
        "contract": contract,
        "contract_version": version,
        "odes_repository": "cogno-us/open-decision-evidence-standard",
        "odes_commit": odes_commit or _odes_commit(),
        "role": role,
        "conformance_level": level,
        "conformance_level_meaning": LEVELS[level],
        "files": {str(f.relative_to(dest)): _sha256(f) for f in _files(dest)},
    }
    (dest / "CONTRACT.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return manifest


def check(dest: Path) -> list[str]:
    manifest = json.loads((dest / "CONTRACT.json").read_text(encoding="utf-8"))
    problems: list[str] = []
    listed = manifest["files"]
    for name, digest in listed.items():
        path = dest / name
        if not path.is_file():
            problems.append(f"missing: {name}")
        elif _sha256(path) != digest:
            problems.append(f"modified: {name}")
    actual = {str(f.relative_to(dest)) for f in _files(dest) if f.is_file()}
    for extra in sorted(actual - set(listed)):
        problems.append(f"unlisted: {extra}")
    return problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("copy")
    c.add_argument("--contract", required=True)
    c.add_argument("--dest", required=True, type=Path)
    c.add_argument("--role", required=True)
    c.add_argument("--level", required=True)
    c.add_argument("--odes-commit")
    k = sub.add_parser("check")
    k.add_argument("--dest", required=True, type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "copy":
        m = copy(args.contract, args.dest, args.role, args.level, args.odes_commit)
        print(f"vendored {m['contract']} {m['contract_version']} at ODES {m['odes_commit'][:8]} into {args.dest}")
        return 0
    problems = check(args.dest)
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
