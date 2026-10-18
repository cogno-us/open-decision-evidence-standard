"""The contract vendor tool copies the contract and detects drift."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("vendor_contract", ROOT / "contracts" / "tools" / "vendor_contract.py")
vc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vc)
CONTRACT = "execution-attempt-lifecycle"


def test_copy_declares_contract_level_and_digests(tmp_path):
    dest = tmp_path / "vendored"
    m = vc.copy(CONTRACT, dest, "consumer", "L", "abc123")
    assert m["contract"] == CONTRACT and m["contract_version"].startswith("0.") and m["odes_commit"] == "abc123"
    assert m["role"] == "consumer" and m["conformance_level"] == "L"
    assert "fixtures/valid/executor-unknown-ack-unobserved.json" in m["files"]
    assert vc.check(dest) == []


def test_check_detects_modified_missing_and_unlisted_files(tmp_path):
    dest = tmp_path / "v"
    vc.copy(CONTRACT, dest, "producer", "P", "abc")
    (dest / "validate.py").write_text("# tampered\n")
    (dest / "fixtures" / "valid" / "executor-unknown-ack-unobserved.json").unlink()
    (dest / "fixtures" / "valid" / "new.json").write_text("{}")
    problems = vc.check(dest)
    assert "modified: validate.py" in problems
    assert "missing: fixtures/valid/executor-unknown-ack-unobserved.json" in problems
    assert "unlisted: fixtures/valid/new.json" in problems


def test_vendored_validator_runs_the_vendored_fixtures(tmp_path):
    dest = tmp_path / "v"
    vc.copy(CONTRACT, dest, "consumer", "L", "abc")
    spec2 = importlib.util.spec_from_file_location("vendored_validate", dest / "validate.py")
    mod = importlib.util.module_from_spec(spec2)
    import sys
    sys.modules["vendored_validate"] = mod  # the validator uses a dataclass, which needs its module registered
    spec2.loader.exec_module(mod)
    for f in sorted((dest / "fixtures" / "valid").glob("*.json")):
        assert mod.validate(json.loads(f.read_text())["document"]) == [], f.name


def test_unknown_contract_and_bad_level_are_refused(tmp_path):
    import pytest
    with pytest.raises(SystemExit):
        vc.copy("no-such-contract", tmp_path / "x", "consumer", "L", None)
    with pytest.raises(SystemExit):
        vc.copy(CONTRACT, tmp_path / "y", "consumer", "Z", None)


def _rewrite(dest, mutate):
    path = dest / "CONTRACT.json"
    manifest = json.loads(path.read_text())
    mutate(manifest)
    path.write_text(json.dumps(manifest))


def test_check_refuses_a_manifest_that_drops_required_files(tmp_path):
    dest = tmp_path / "v"
    vc.copy(CONTRACT, dest, "consumer", "L", "abc")
    _rewrite(dest, lambda m: m["files"].pop("schema.json"))
    problems = vc.check(dest)
    assert "inventory omits required file: schema.json" in problems and "unlisted: schema.json" in problems


def test_check_refuses_traversal_absolute_and_symlinked_names(tmp_path):
    dest = tmp_path / "v"
    vc.copy(CONTRACT, dest, "consumer", "L", "abc")
    outside = tmp_path / "outside.txt"
    outside.write_text("x")
    digest = vc._sha256(outside)

    def add(m):
        m["files"]["../outside.txt"] = digest
        m["files"][str(outside)] = digest
        m["files"]["fixtures/../../outside.txt"] = digest
    _rewrite(dest, add)
    unsafe = [p for p in vc.check(dest) if p.startswith("unsafe name")]
    assert len(unsafe) == 3
    link = tmp_path / "v2"
    vc.copy(CONTRACT, link, "consumer", "L", "abc")
    (link / "README.md").unlink()
    (link / "README.md").symlink_to(outside)
    assert any("unsafe name: 'README.md'" in p for p in vc.check(link))


def test_check_reports_a_broken_manifest_instead_of_raising(tmp_path):
    dest = tmp_path / "v"
    vc.copy(CONTRACT, dest, "consumer", "L", "abc")
    (dest / "CONTRACT.json").write_text("{not json")
    assert vc.check(dest)[0].startswith("manifest unreadable")
    (dest / "CONTRACT.json").write_text('{"files": 5}')
    assert vc.check(dest) == ["manifest has no files mapping"]
