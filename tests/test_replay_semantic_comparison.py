"""Regression: the retained Replay bundle must equal a fresh accepted reconstruction including import_reports and semantics.

Replay is stubbed, so no Replay install is needed.
"""
import copy
import sys
import types

import pytest

from odes import exporter
from odes.common import MERGED_REVISIONS, ALL_V2_CONTROL_PLANE_REVISIONS
from odes.exporter import ExportError

REVISION = MERGED_REVISIONS["control_plane"]
REPORTS = [{"adapter_profile": "p", "complete": True, "findings": [{"code": "M002", "severity": "warning", "value_state": "unknown"}]}]
SEMANTICS = {"record_reconstruction": True, "destination_observation": "producer_reported", "independent_effect_verification": False}


def retained():
    return {"bundle_version": "0.2.0", "records": [{"record_type": "runtime_proposal", "source_sequence": 1, "data": {}}], "links": [], "commitments": [], "producer_profiles": [], "status": "reconstruction_complete",
            "import_reports": copy.deepcopy(REPORTS), "semantics": copy.deepcopy(SEMANTICS),
            "metadata": {"control_plane_revision": REVISION}}


@pytest.fixture(autouse=True)
def stub_replay(monkeypatch):
    assert REVISION in ALL_V2_CONTROL_PLANE_REVISIONS
    package = types.ModuleType("agent_replay_bundle")
    module = types.ModuleType("agent_replay_bundle.importers")

    class ImportContractError(ValueError):
        pass

    def import_bounded_workflow(cp, **kwargs):
        reference = retained()
        return types.SimpleNamespace(status=reference["status"], import_reports=[],
                                     model_dump=lambda mode="json": copy.deepcopy(reference))

    module.ImportContractError = ImportContractError
    module.import_bounded_workflow = import_bounded_workflow
    package.importers = module
    monkeypatch.setitem(sys.modules, "agent_replay_bundle", package)
    monkeypatch.setitem(sys.modules, "agent_replay_bundle.importers", module)


def test_matching_bundle_is_accepted():
    assert exporter._run_replay_validation(retained())[0] == "reconstruction_complete"


@pytest.mark.parametrize("mutate,field", [
    (lambda b: b["import_reports"].clear(), "import_reports"),
    (lambda b: [r["findings"].clear() for r in b["import_reports"]], "import_reports"),
    (lambda b: b["semantics"].__setitem__("independent_effect_verification", True), "semantics"),
    (lambda b: b["semantics"].__setitem__("destination_observation", "not_performed"), "semantics"),
])
def test_tampered_reports_or_semantics_are_rejected(mutate, field):
    bundle = retained()
    mutate(bundle)
    with pytest.raises(ExportError, match=f"retained Replay {field} differs from accepted validator reconstruction"):
        exporter._run_replay_validation(bundle)
