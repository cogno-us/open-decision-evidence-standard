"""Documentation claims are tied to the code and files they describe: the status set, related work, the version register, the example
policy for producer-2.0.0 packages and the qualified wording of public claims."""
import hashlib
import json
import re
import tomllib
from pathlib import Path

import pytest

from odes import common
from odes.canonicalization import JCS_CANONICALIZATION_PROFILE, LEGACY_CANONICALIZATION_PROFILE
from odes.recipient_validator import evaluate_recipient_package

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs" / "capabilities-and-versions.md"


def text(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_every_status_the_validator_emits_is_documented():
    source = text("src/odes/recipient_validator.py")
    emitted = set(re.findall(r'_result\(\s*"([a-z_]+)"', source))
    documented = set(re.findall(r"^\| `([a-z_]+)` \|", text("docs/recipient-validation.md"), flags=re.M))
    assert emitted and emitted <= documented, emitted - documented
    assert {"pass", "fail", "unavailable", "unsupported", "not_evaluated", "not_applicable", "informational_only"} <= documented


@pytest.mark.parametrize("name", ["VES", "DPS", "AskLedger", "OVERT"])
def test_related_work_covers_each_adjacent_effort(name):
    assert name in text("docs/related-work.md")


def test_related_work_makes_no_adoption_or_interoperability_claim():
    body = text("docs/related-work.md").lower()
    assert "no interoperability exchange" in body
    assert "not endorsements" in body
    for phrase in ("interoperable with", "partnership", "adopted by"):
        assert phrase not in body


def test_conformance_guidance_names_the_reference_validator_and_its_limits():
    body = text("conformance/verifier-requirements.md")
    assert "does not provide production verifier code" not in body
    assert "reference recipient validator" in body
    assert "not production-qualified" in body


def _register_text():
    return REGISTER.read_text(encoding="utf-8")


def test_register_lists_every_version_coordinate():
    body = _register_text()
    project = tomllib.loads(text("pyproject.toml"))["project"]
    coordinates = [
        common.DOCUMENT_VERSION, common.SCHEMA_NAME, common.PACKAGE_VERSION, project["version"],
        LEGACY_CANONICALIZATION_PROFILE, JCS_CANONICALIZATION_PROFILE,
        common.PROFILE_ID, common.PROFILE_VERSION, common.PROFILE_V2_ID, common.PROFILE_V2_VERSION,
        common.PROFILE_V2_RESTRICTIONS_ID, common.RESTRICTION_VERSION_SUFFIX,
        common.MERGED_PROFILE_VERSION, common.REFUSAL_PROFILE_VERSION,
        *(version for version, _ in common.SECURITY_RUNTIME_GENERATIONS.values()),
        "2.0.0",
    ]
    missing = [c for c in coordinates if c not in body]
    assert not missing, missing


def test_register_schema_digest_matches_the_schema_file():
    digest = hashlib.sha256((ROOT / "schema" / "pder-v0.1.schema.json").read_bytes()).hexdigest()
    assert digest in _register_text()


def test_register_separates_the_capability_layers():
    body = _register_text()
    for layer in ("Base schema", "Package envelope", "Cognous profile", "Accepted source qualification", "Selected release"):
        assert layer in body
    assert "not production-qualified" in body


def test_register_notes_that_a_version_label_is_not_proof_of_identical_content():
    assert "label alone" in _register_text()


PRODUCER_V2 = sorted((ROOT / "examples" / "producer-v2").glob("*.package.json"))
V2_POLICY = ROOT / "examples" / "policies" / "recipient-audit-policy-producer-v2.json"
V1_POLICY = ROOT / "examples" / "policies" / "recipient-audit-policy.json"


@pytest.mark.parametrize("path", PRODUCER_V2, ids=lambda p: p.name)
def test_producer_v2_examples_work_under_their_declared_profile_and_not_under_the_legacy_policy(path):
    package = json.loads(path.read_text())
    v2 = evaluate_recipient_package(package, json.loads(V2_POLICY.read_text()))
    assert v2["declared_profile_conformance"]["status"] == "pass"
    assert v2["package_content_integrity"]["status"] == "pass"
    v1 = evaluate_recipient_package(package, json.loads(V1_POLICY.read_text()))
    assert v1["declared_profile_conformance"]["status"] == "unsupported"
    assert v1["recipient_reliance_decision"]["status"] == "fail"


def test_example_policies_list_exact_profiles():
    assert json.loads(V1_POLICY.read_text())["supported_profiles"] == [common.PROFILE_ID]
    assert json.loads(V2_POLICY.read_text())["supported_profiles"] == [common.PROFILE_V2_ID]


PUBLIC = ["README.md", "GOVERNANCE.md", "collateral/business-collateral.md", "collateral/one-page-overview.md", "docs/public-messaging.md",
          "docs/problem-statement.md", "docs/related-work.md", "docs/design-principles.md"]
UNQUALIFIED = ["lets the rest interoperate", "privacy-preserving", "verifiable issuer", "make freshness and revocation checkable"]


@pytest.mark.parametrize("rel", PUBLIC)
def test_public_text_has_no_unqualified_claims(rel):
    body = text(rel)
    if rel == "docs/public-messaging.md":  # the "do not say" list names these phrases on purpose
        body = body.split("## What not to say")[0] + body.split("## Boundary")[-1]
    body = body.lower()
    for phrase in UNQUALIFIED:
        assert phrase not in body, phrase
    assert "tamper-proof" not in body.replace("- tamper-proof", "")


@pytest.mark.parametrize("rel", ["README.md", "collateral/business-collateral.md", "collateral/one-page-overview.md", "docs/public-messaging.md", "docs/problem-statement.md"])
def test_vendor_neutral_is_qualified_with_the_governance_status(rel):
    paragraphs = [p for p in re.split(r"\n\s*\n", text(rel)) if "vendor-neutral" in p]
    assert paragraphs
    for paragraph in paragraphs:
        assert "single" in paragraph and "maintainer" in paragraph and "draft" in paragraph, paragraph[:120]


def test_public_messaging_does_not_claim_raw_evidence_stays_home_without_the_profile_limit():
    body = text("docs/public-messaging.md")
    assert "profile 0.2" in body.lower() and "retained original sources" in body.lower()


def test_freshness_and_revocation_wording_names_its_dependency():
    body = text("docs/public-messaging.md").lower()
    assert "recipient-supplied status evidence" in body
