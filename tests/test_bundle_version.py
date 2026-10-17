"""Regression for #43: an unsupported Reconstruction Bundle version must fail explicitly."""
import pytest

from odes.exporter import ExportError, export_cognous_stack_package


@pytest.mark.parametrize("version", ["0.3.0", "0.1", None, ""])
def test_unsupported_bundle_version_fails_explicitly(version):
    b = {"records": []}
    if version is not None:
        b["bundle_version"] = version
    with pytest.raises(ExportError, match="unsupported Reconstruction Bundle version"):
        export_cognous_stack_package({"manifest_id": "m", "manifest_version": "1.1", "actions": [{"action_id": "a"}]}, b)
