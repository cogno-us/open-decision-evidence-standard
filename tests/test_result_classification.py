"""Result classification for the recipient validator.

Definitive facts (an expired consumption window, a contradiction) are ``fail``. Absent required evidence, including an absent optional
Replay installation, is ``unavailable``. An installed Replay that lacks what the check needs is ``unsupported``. Every one of them blocks
reliance; the classes only keep a retrying caller from treating a settled refusal as missing evidence.
"""
import copy
import json
import sys
import types
from pathlib import Path

import pytest

from odes import exporter
from odes.common import PROFILE_V2_ID
from odes.recipient_validator import _evaluate_authority_and_freshness, evaluate_recipient_package

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = sorted((ROOT / "examples" / "producer-v2").glob("*.package.json"))
EXPIRY = "2026-10-18T12:00:00Z"
EXPIRED = "record consumption window has expired under recipient policy time"
POLICY = {"supported_profiles": [PROFILE_V2_ID], "now": "2026-01-01T00:00:00Z", "relying_party": "recipient.example.org", "purpose": "audit"}


def _package(name="lost_ack"):
    return json.loads((ROOT / "examples" / "producer-v2" / f"{name}.package.json").read_text())


def _record(expires=EXPIRY):
    return {"consumption_conditions": {"expires_at": expires}}


def _valid_status(record):
    return {"issuer": record.get("issuer"), "record_id": record.get("decision_id"), "authority_basis": None,
            "evaluation_scope": "audit", "evaluated_at": "2026-10-18T11:59:00Z", "evidence_freshness": "current",
            "authority_valid_at_decision_verified": True, "freshness": "current", "revoked": False, "superseded": False}


@pytest.mark.parametrize("now", ["2026-10-18T12:00:00Z", "2026-10-18T12:00:01Z", "2027-01-01T00:00:00Z", "2026-10-18T14:00:00+02:00"])
def test_expiry_is_fail_without_status_inputs(now):
    out = _evaluate_authority_and_freshness(_record(), {}, now, {})
    assert out["status"] == "fail"
    assert EXPIRED in out["reasons"]
    assert any("external status evidence is required" in r for r in out["reasons"])


@pytest.mark.parametrize("now", ["2026-10-18T12:00:00Z", "2027-01-01T00:00:00Z"])
def test_expiry_is_fail_with_status_inputs(now):
    policy = {"status_max_age_seconds": 10 ** 9, "evaluation_scope": "audit"}
    out = _evaluate_authority_and_freshness(_record(), _valid_status({}), now, policy)
    assert out["status"] == "fail"
    assert EXPIRED in out["reasons"]


@pytest.mark.parametrize("now", ["2026-10-18T11:59:59Z", "2026-10-18T13:59:59+02:00"])
def test_unexpired_without_status_inputs_stays_unavailable(now):
    out = _evaluate_authority_and_freshness(_record(), {}, now, {})
    assert out["status"] == "unavailable"
    assert EXPIRED not in out["reasons"]


@pytest.mark.parametrize("now", [None, "", "2026-10-18T12:00:00", "not a time", 5])
def test_unusable_evaluation_time_stays_unavailable(now):
    out = _evaluate_authority_and_freshness(_record(), {}, now, {})
    assert out["status"] == "unavailable"
    assert EXPIRED not in out["reasons"]


def test_expired_package_never_reaches_reliance_pass():
    package = _package()
    package["record"]["consumption_conditions"]["expires_at"] = "2025-06-01T00:00:00Z"
    result = evaluate_recipient_package(package, POLICY)
    assert result["authority_status_and_freshness"]["status"] == "fail"
    assert result["recipient_reliance_decision"]["status"] == "fail"


def test_reliance_names_the_status_of_each_blocking_layer():
    result = evaluate_recipient_package(_package(), {**POLICY, "now": "2026-01-01T00:00:00Z"})
    blocking = result["recipient_reliance_decision"]["evidence"]["blocking_layers"]
    assert blocking["authority_status_and_freshness"] == "unavailable"
    assert blocking["integrity_authentication_checks"] == "unavailable"
    assert all(v != "pass" for v in blocking.values())


def _no_replay(monkeypatch):
    """Behave as an environment where the Replay distribution is not installed."""
    for name in [n for n in sys.modules if n == "agent_replay_bundle" or n.startswith("agent_replay_bundle.")]:
        monkeypatch.delitem(sys.modules, name)

    class Absent:
        @staticmethod
        def find_spec(name, path=None, target=None):
            if name == "agent_replay_bundle":
                raise ModuleNotFoundError("No module named 'agent_replay_bundle'", name="agent_replay_bundle")
            return None

    monkeypatch.setattr(sys, "meta_path", [Absent, *sys.meta_path])


def test_absent_replay_installation_is_unavailable_not_fail(monkeypatch):
    _no_replay(monkeypatch)
    result = evaluate_recipient_package(_package(), POLICY)
    layer = result["replay_semantic_consistency"]
    assert layer["status"] == "unavailable"
    assert "install" in layer["reasons"][0]
    assert result["recipient_reliance_decision"]["status"] == "fail"
    assert result["recipient_reliance_decision"]["evidence"]["blocking_layers"]["replay_semantic_consistency"] == "unavailable"


def test_absent_replay_never_promotes_other_layers(monkeypatch):
    _no_replay(monkeypatch)
    policy = {**POLICY, "allow_unauthenticated_informational_inspection": True}
    result = evaluate_recipient_package(_package(), policy)
    assert result["recipient_reliance_decision"]["status"] == "fail"


def _stub_replay(monkeypatch, importer):
    package = types.ModuleType("agent_replay_bundle")
    module = types.ModuleType("agent_replay_bundle.importers")

    class ImportContractError(ValueError):
        pass

    module.ImportContractError = ImportContractError
    module.import_bounded_workflow = importer(ImportContractError)
    package.importers = module
    monkeypatch.setitem(sys.modules, "agent_replay_bundle", package)
    monkeypatch.setitem(sys.modules, "agent_replay_bundle.importers", module)


def test_replay_contradiction_remains_fail(monkeypatch):
    def importer(error):
        def run(*args, **kwargs):
            raise error("retained records contradict")
        return run
    _stub_replay(monkeypatch, importer)
    monkeypatch.setattr(exporter, "installed_replay_revision", lambda: None)
    monkeypatch.setenv("ODES_ALLOW_UNVERIFIED_REPLAY", "1")
    layer = evaluate_recipient_package(_package(), POLICY)["replay_semantic_consistency"]
    assert layer["status"] == "fail"
    assert "retained records contradict" in layer["reasons"][0]


def test_replay_operational_error_remains_fail_and_diagnosable(monkeypatch):
    def importer(error):
        def run(*args, **kwargs):
            raise RuntimeError("worker crashed")
        return run
    _stub_replay(monkeypatch, importer)
    monkeypatch.setattr(exporter, "installed_replay_revision", lambda: None)
    monkeypatch.setenv("ODES_ALLOW_UNVERIFIED_REPLAY", "1")
    layer = evaluate_recipient_package(_package(), POLICY)["replay_semantic_consistency"]
    assert layer["status"] == "fail"
    assert "worker crashed" in layer["reasons"][0]


def test_unaccepted_installed_replay_revision_is_unsupported(monkeypatch):
    def importer(error):
        return lambda *a, **k: pytest.fail("must not run an unaccepted revision")
    _stub_replay(monkeypatch, importer)
    monkeypatch.setattr(exporter, "installed_replay_revision", lambda: "f" * 40)
    monkeypatch.setenv("ODES_ALLOW_UNVERIFIED_REPLAY", "0")
    layer = evaluate_recipient_package(_package(), POLICY)["replay_semantic_consistency"]
    assert layer["status"] == "unsupported"
    assert "not an accepted Replay revision" in layer["reasons"][0]


def test_undeterminable_installed_replay_revision_is_unavailable(monkeypatch):
    def importer(error):
        return lambda *a, **k: pytest.fail("must not run an unverified revision")
    _stub_replay(monkeypatch, importer)
    monkeypatch.setattr(exporter, "installed_replay_revision", lambda: None)
    monkeypatch.setenv("ODES_ALLOW_UNVERIFIED_REPLAY", "0")
    layer = evaluate_recipient_package(_package(), POLICY)["replay_semantic_consistency"]
    assert layer["status"] == "unavailable"
    assert "cannot be determined" in layer["reasons"][0]


def test_installed_replay_missing_a_required_module_is_unsupported(monkeypatch):
    package = types.ModuleType("agent_replay_bundle")
    monkeypatch.setitem(sys.modules, "agent_replay_bundle", package)
    monkeypatch.setitem(sys.modules, "agent_replay_bundle.importers", None)
    layer = evaluate_recipient_package(_package(), POLICY)["replay_semantic_consistency"]
    assert layer["status"] == "unsupported"


def test_unrelated_import_error_is_a_diagnosable_fail(monkeypatch):
    class Broken:
        def __getattr__(self, name):
            raise ImportError("No module named 'pydantic'", name="pydantic")
    package = types.ModuleType("agent_replay_bundle")
    monkeypatch.setitem(sys.modules, "agent_replay_bundle", package)
    monkeypatch.setitem(sys.modules, "agent_replay_bundle.importers", Broken())
    layer = evaluate_recipient_package(_package(), POLICY)["replay_semantic_consistency"]
    assert layer["status"] == "fail"
    assert "pydantic" in layer["reasons"][0]


def test_typed_dependency_errors_are_export_errors():
    assert issubclass(exporter.ReplayDependencyError, exporter.ExportError)
    assert issubclass(exporter.ReplayRevisionUnsupportedError, exporter.ExportError)


def _pinned_replay_available():
    try:
        import agent_replay_bundle  # noqa: F401
        from odes.common import all_accepted_replay_revisions, installed_replay_revision
        return installed_replay_revision() in all_accepted_replay_revisions()
    except Exception:
        return False


@pytest.mark.skipif(not _pinned_replay_available(), reason="needs the accepted Replay revision installed")
@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_control_producer_v2_examples_pass_the_semantic_layer(path):
    package = json.loads(path.read_text())
    result = evaluate_recipient_package(package, POLICY)
    assert result["replay_semantic_consistency"]["status"] == "pass"
    assert result["package_content_integrity"]["status"] == "pass"
    assert result["recipient_reliance_decision"]["status"] == "fail"
