"""Generic recipient profile: not tied to the Cognous export profiles, carries the native evidence inventory, needs no Replay."""
import base64
import hashlib
import json
import subprocess
import sys
import textwrap
from copy import deepcopy
from pathlib import Path

import pytest

from odes import common, signatures
from odes.canonicalization import JCS_CANONICALIZATION_PROFILE, digest_for
from odes.common import CANONICALIZATION_PROFILE, RESTRICTION_UNKNOWN_LIMIT
from odes.evidence_inventory import build_inventory, build_inventory_entry, extract_artifact
from odes.generic_profile import (GENERIC_PROFILE_ID, GENERIC_PROFILE_VERSION, GENERIC_PROVENANCE_MEMBERS, build_generic_package)
from odes.recipient_validator import evaluate_recipient_package

ROOT = Path(__file__).resolve().parents[1]
BASE_RECORD = json.loads((ROOT / "conformance" / "test-vectors" / "valid-minimal.example.json").read_text(encoding="utf-8"))
SEED = bytes(range(32))  # synthetic test key material only
OTHER_SEED = bytes(range(32, 64))
RAW = b'{ "z" : 1,\n "a":[1.0, 2e0] }\n'
SOURCE = {"record_id": "source-record-1", "record_hash": "sha256:" + "ab" * 32}
EXPLICIT = {"restricted_use_flag": "explicit_false", "prohibited_use_flag": "explicit_false",
            "jurisdiction": {"state": "explicit", "value": "example-jurisdiction"}, "source": SOURCE}


def _record():
    record = deepcopy(BASE_RECORD)
    record["consumption_conditions"] = {"permitted_relying_parties": ["recipient.example.org"], "permitted_purposes": ["audit"],
                                        "expires_at": "2027-01-01T00:00:00Z"}
    return record


def _package(canonicalization=CANONICALIZATION_PROFILE, restrictions=None, inventory=None, **kw):
    return build_generic_package(_record(), created_by="example-issuer", created_at="2026-10-01T00:00:00Z",
                                 restrictions=restrictions or EXPLICIT, native_evidence_inventory=inventory,
                                 canonicalization=canonicalization, **kw)


def _crypto():
    return pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519", exc_type=ImportError)


def _key(seed=SEED):
    return _crypto().Ed25519PrivateKey.from_private_bytes(seed)


def _trusted(seed=SEED):
    from cryptography.hazmat.primitives import serialization
    raw = _key(seed).public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return [{"keyid": "issuer-key-1", "algorithm": "ed25519", "public_key": base64.b64encode(raw).decode(), "issuer": "example-issuer/example-system"}]


def _policy(package, **over):
    record = package["record"]
    policy = {
        "now": "2026-10-06T00:00:00Z", "purpose": "audit", "relying_party": "recipient.example.org", "jurisdiction": "example-jurisdiction",
        "supported_profiles": [GENERIC_PROFILE_ID], "evaluation_scope": "audit", "status_max_age_seconds": 300,
        "trusted_issuer": record["issuer"],
        "status_inputs": {"issuer": record["issuer"], "record_id": record["decision_id"], "authority_basis": record["authority"]["authority_basis"],
                          "evaluation_scope": "audit", "authority_valid_at_decision_verified": True, "evaluated_at": "2026-10-05T23:59:00Z",
                          "evidence_freshness": "current", "freshness": "current", "revoked": False, "superseded": False},
        "detached_authentication": {"envelope": signatures.sign_package(package, _key(), "issuer-key-1"), "trusted_keys": _trusted()},
    }
    policy.update(over)
    return policy


def _statuses(layers):
    return {name: layer["status"] for name, layer in layers.items() if isinstance(layer, dict) and "status" in layer}


def _entry(artifact_id="receipt-1", data=RAW, **kw):
    return build_inventory_entry(artifact_id, data=data, source_format="example-receipt", source_format_version="1",
                                 relation="execution_evidence", media_type="application/json", **kw)


# ---------------------------------------------------------------- the profile and a full synthetic pass

@pytest.mark.parametrize("canonicalization", [CANONICALIZATION_PROFILE, JCS_CANONICALIZATION_PROFILE])
def test_synthetic_generic_decision_reaches_reliance_pass_only_with_every_prerequisite(canonicalization):
    package = _package(canonicalization)
    layers = evaluate_recipient_package(package, _policy(package))
    assert layers["recipient_reliance_decision"]["status"] == "pass", {k: v["reasons"] for k, v in layers.items() if isinstance(v, dict) and v.get("status") not in {"pass", None}}
    assert set(_statuses(layers).values()) == {"pass"}


def test_no_cognous_replay_layer_runs_and_the_boundary_says_so():
    package = _package()
    layers = evaluate_recipient_package(package, _policy(package))
    assert "replay_semantic_consistency" not in layers
    assert layers["declared_profile_conformance"]["evidence"]["cognous_replay_reconstruction"] == "not_applicable"
    assert any("Cognous" in note and "not" in note for note in layers["boundary_notes"])


def test_evaluation_never_imports_replay_and_works_where_it_cannot_be_imported():
    code = textwrap.dedent("""
        import sys, json
        class Block:                                  # any import of the Replay distribution raises
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] == "agent_replay_bundle":
                    raise ImportError("Replay is not installed in this environment")
        sys.meta_path.insert(0, Block())
        from odes.generic_profile import build_generic_package
        from odes.recipient_validator import evaluate_recipient_package
        record = json.load(open(sys.argv[1]))
        record["consumption_conditions"] = {"permitted_relying_parties": ["r"], "permitted_purposes": ["audit"], "expires_at": "2027-01-01T00:00:00Z"}
        package = build_generic_package(record, created_by="x", created_at="2026-10-01T00:00:00Z",
            restrictions={"restricted_use_flag": "explicit_false", "prohibited_use_flag": "explicit_false",
                          "jurisdiction": {"state": "explicit", "value": "j"}, "source": {"record_id": "s", "record_hash": "sha256:" + "0" * 64}})
        layers = evaluate_recipient_package(package, {"supported_profiles": ["odes_generic_recipient_0_1"]})
        assert layers["package_content_integrity"]["status"] == "pass", layers["package_content_integrity"]
        assert layers["declared_profile_conformance"]["status"] == "pass"
        assert not any(m.split(".")[0] == "agent_replay_bundle" for m in sys.modules), "replay imported"
        print("ok")
    """)
    out = subprocess.run([sys.executable, "-I", "-c", code, str(ROOT / "conformance" / "test-vectors" / "valid-minimal.example.json")],
                         capture_output=True, text=True, env={"PYTHONPATH": str(ROOT / "src"), "ODES_ALLOW_UNVERIFIED_REPLAY": "1"})
    assert out.returncode == 0 and out.stdout.strip() == "ok", out.stderr


@pytest.mark.parametrize("name, change", [
    ("no status evidence", lambda p, pol: pol.update(status_inputs={})),
    ("authority not verified", lambda p, pol: pol["status_inputs"].update(authority_valid_at_decision_verified=False)),
    ("revoked", lambda p, pol: pol["status_inputs"].update(revoked=True)),
    ("not current", lambda p, pol: pol["status_inputs"].update(freshness="stale")),
    ("other issuer trusted", lambda p, pol: pol.update(trusted_issuer={"organization_id": "other", "system_id": "other"})),
    ("after expiry", lambda p, pol: pol.update(now="2027-06-01T00:00:00Z")),
    ("other relying party", lambda p, pol: pol.update(relying_party="someone.else.example")),
    ("other purpose", lambda p, pol: pol.update(purpose="marketing")),
    ("other jurisdiction", lambda p, pol: pol.update(jurisdiction="elsewhere")),
    ("no jurisdiction", lambda p, pol: pol.pop("jurisdiction")),
    ("profile not accepted", lambda p, pol: pol.update(supported_profiles=[common.PROFILE_V2_ID])),
    ("signature removed", lambda p, pol: pol.pop("detached_authentication")),
    ("signature by an untrusted key", lambda p, pol: pol["detached_authentication"].update(trusted_keys=_trusted(OTHER_SEED))),
    ("package changed after signing", lambda p, pol: p.update(created_by="changed")),
    ("record changed after signing", lambda p, pol: p["record"].update(decision_id="changed")),
])
def test_changing_any_single_prerequisite_refuses_reliance(name, change):
    package = _package()
    policy = _policy(package)
    assert evaluate_recipient_package(deepcopy(package), deepcopy(policy))["recipient_reliance_decision"]["status"] == "pass"
    change(package, policy)
    assert evaluate_recipient_package(package, policy)["recipient_reliance_decision"]["status"] != "pass", name


def test_a_valid_signature_alone_is_not_reliance():
    package = _package()
    policy = _policy(package, status_inputs={})
    layers = evaluate_recipient_package(package, policy)
    assert layers["integrity_authentication_checks"]["status"] == "pass"
    assert layers["recipient_reliance_decision"]["status"] == "fail"


def test_without_a_signature_the_generic_package_is_not_authenticated():
    package = _package()
    policy = _policy(package)
    del policy["detached_authentication"]
    layers = evaluate_recipient_package(package, policy)
    assert layers["integrity_authentication_checks"]["status"] == "unavailable"
    assert layers["recipient_reliance_decision"]["status"] == "fail"


# ---------------------------------------------------------------- profile identity and relabelling

def test_new_identifier_and_existing_profiles_are_unchanged():
    assert GENERIC_PROFILE_ID == "odes_generic_recipient_0_1" and GENERIC_PROFILE_ID not in {common.PROFILE_ID, common.PROFILE_V2_ID, common.PROFILE_V2_RESTRICTIONS_ID}
    assert (common.PROFILE_ID, common.PROFILE_V2_ID, common.PROFILE_V2_RESTRICTIONS_ID) == (
        "odes_cognous_stack_export_0_1", "odes_cognous_stack_export_0_2", "odes_cognous_stack_export_0_2_restrictions")
    assert common.PROFILE_V2_VERSION == "odes-cognous-stack-export-0.2.0" and common.PACKAGE_VERSION == "0.1.0"
    assert "0.1.0-draft" in GENERIC_PROFILE_VERSION
    exporter_source = (ROOT / "src" / "odes" / "exporter.py").read_text(encoding="utf-8")
    assert "generic_profile" not in exporter_source and "GENERIC_PROFILE" not in exporter_source  # the Cognous exporter cannot emit it


def test_a_policy_listing_only_other_profiles_does_not_accept_it():
    package = _package()
    for supported in ([common.PROFILE_V2_ID], [common.PROFILE_ID], [common.PROFILE_V2_RESTRICTIONS_ID]):
        layers = evaluate_recipient_package(package, {"supported_profiles": supported})
        assert layers["declared_profile_conformance"]["status"] == "unsupported"
    assert evaluate_recipient_package(package, {})["declared_profile_conformance"]["status"] == "unsupported"  # default list is the historical profile only


def test_unsupported_version_and_schema_coordinates():
    package = _package()
    package["profile"]["implementation_profile_version"] = "odes-generic-recipient-9.9.9"
    assert evaluate_recipient_package(package, {"supported_profiles": [GENERIC_PROFILE_ID]})["declared_profile_conformance"]["status"] == "unsupported"
    package = _package()
    package["profile"]["schema_version"] = "9"
    assert evaluate_recipient_package(package, {"supported_profiles": [GENERIC_PROFILE_ID]})["declared_profile_conformance"]["status"] == "fail"


def _redigest(package, canonicalization=CANONICALIZATION_PROFILE):
    package["integrity"]["value"] = digest_for(canonicalization, {"record": package["record"], "profile": package["profile"]})
    package["package_digest"] = digest_for(canonicalization, {k: package[k] for k in ("record", "profile", "integrity", "provenance")})
    return package


def test_generic_package_relabelled_as_a_cognous_profile_fails():
    for target in (common.PROFILE_V2_ID, common.PROFILE_V2_RESTRICTIONS_ID, common.PROFILE_ID):
        package = _package()
        package["profile"]["implementation_profile"] = target
        package["record"]["verification"]["conformance_profile"] = target
        _redigest(package)
        layers = evaluate_recipient_package(package, {"supported_profiles": [target]})
        assert layers["recipient_reliance_decision"]["status"] == "fail"
        assert layers["declared_profile_conformance"]["status"] in {"fail", "unsupported"}
        assert layers.get("replay_semantic_consistency", {}).get("status", "fail") != "pass"


def test_cognous_package_relabelled_as_generic_fails():
    for path in sorted((ROOT / "examples" / "producer-v2").glob("*.package.json")):
        package = json.loads(path.read_text(encoding="utf-8"))
        package["profile"]["implementation_profile"] = GENERIC_PROFILE_ID
        package["profile"]["implementation_profile_version"] = GENERIC_PROFILE_VERSION
        package["record"]["verification"]["conformance_profile"] = GENERIC_PROFILE_ID
        _redigest(package)
        layers = evaluate_recipient_package(package, {"supported_profiles": [GENERIC_PROFILE_ID]})
        assert layers["declared_profile_conformance"]["status"] == "fail", path.name
        assert layers["recipient_reliance_decision"]["status"] == "fail"


def test_provenance_is_closed_and_required_members_must_be_present():
    package = _package()
    package["provenance"]["retained_sources"] = {}
    _redigest(package)
    assert evaluate_recipient_package(package, {"supported_profiles": [GENERIC_PROFILE_ID]})["declared_profile_conformance"]["status"] == "fail"
    for missing in ("limits", "unsupported_semantics", "restriction_semantics"):
        package = _package()
        del package["provenance"][missing]
        _redigest(package)
        layers = evaluate_recipient_package(package, {"supported_profiles": [GENERIC_PROFILE_ID]})
        assert layers["package_content_integrity"]["status"] == "fail", missing
        assert layers["recipient_reliance_decision"]["status"] == "fail"
    assert GENERIC_PROVENANCE_MEMBERS == {"limits", "unsupported_semantics", "restriction_semantics", "native_evidence_inventory"}


def test_top_level_envelope_checks_still_apply():
    package = _package()
    package["extra"] = 1
    layers = evaluate_recipient_package(package, {"supported_profiles": [GENERIC_PROFILE_ID]})
    assert layers["package_content_integrity"]["status"] == "fail"


# ---------------------------------------------------------------- restriction semantics (#118)

def test_unknown_restriction_values_are_conservative_and_block_reliance():
    restrictions = {"restricted_use_flag": "unknown", "prohibited_use_flag": "unknown", "jurisdiction": {"state": "unknown"}}
    package = _package(restrictions=restrictions)
    assert package["record"]["risk_coordinates"]["restricted_use_flag"] is True and package["record"]["risk_coordinates"]["jurisdiction"] == "unknown"
    assert RESTRICTION_UNKNOWN_LIMIT in package["provenance"]["limits"]
    layers = evaluate_recipient_package(package, _policy(package, jurisdiction="unknown"))
    assert layers["consumption_conditions"]["status"] == "fail"
    assert layers["recipient_reliance_decision"]["status"] == "fail"
    assert any("unknown" in r for r in layers["consumption_conditions"]["reasons"])


def test_builder_refuses_an_unattributable_false_and_a_malformed_state():
    with pytest.raises(ValueError):
        _package(restrictions={**EXPLICIT, "source": None})
    with pytest.raises(ValueError):
        _package(restrictions={**EXPLICIT, "restricted_use_flag": "false"})
    with pytest.raises(ValueError):
        _package(restrictions={**EXPLICIT, "jurisdiction": {"state": "explicit", "value": "unknown"}})


@pytest.mark.parametrize("mutate", [
    lambda p: p["provenance"].pop("restriction_semantics"),
    lambda p: p["provenance"]["restriction_semantics"].update(semantics_version="restriction-semantics-0"),
    lambda p: p["provenance"]["restriction_semantics"]["restricted_use_flag"].update(state="explicit_true"),  # base boolean says false
    lambda p: p["provenance"]["restriction_semantics"].pop("source"),                                       # explicit false without source
    lambda p: p["record"]["risk_coordinates"].update(prohibited_use_flag=True),
])
def test_handcrafted_restriction_inconsistencies_are_refused(mutate):
    package = _package()
    mutate(package)
    _redigest(package)
    layers = evaluate_recipient_package(package, _policy(package))
    assert layers["recipient_reliance_decision"]["status"] != "pass"
    assert layers["consumption_conditions"]["status"] == "fail" or layers["package_content_integrity"]["status"] == "fail"


def test_missing_mandatory_limitation_for_an_unknown_value_is_refused():
    restrictions = {"restricted_use_flag": "unknown", "prohibited_use_flag": "explicit_false", "jurisdiction": {"state": "explicit", "value": "example-jurisdiction"}, "source": SOURCE}
    package = _package(restrictions=restrictions)
    package["provenance"]["limits"] = []
    _redigest(package)
    layers = evaluate_recipient_package(package, _policy(package))
    assert layers["consumption_conditions"]["status"] == "fail"
    assert any("limitation" in r for r in layers["consumption_conditions"]["reasons"])


# ---------------------------------------------------------------- native evidence inventory (#116)

@pytest.mark.parametrize("canonicalization", [CANONICALIZATION_PROFILE, JCS_CANONICALIZATION_PROFILE])
def test_generic_package_carries_the_inventory_byte_for_byte(canonicalization):
    entry = _entry(required=True)
    package = _package(canonicalization, inventory=build_inventory([entry]))
    carried = package["provenance"]["native_evidence_inventory"]["artifacts"][0]
    assert extract_artifact(carried) == RAW
    layers = evaluate_recipient_package(package, _policy(package))
    assert layers["native_evidence_inventory"]["status"] == "pass"
    assert layers["recipient_reliance_decision"]["status"] == "pass"


def test_changing_the_inventory_changes_the_digest_and_fails():
    package = _package(inventory=build_inventory([_entry()]))
    policy = _policy(package)
    tampered = deepcopy(package)
    tampered["provenance"]["native_evidence_inventory"]["artifacts"][0]["relation"] = "supporting_context"
    layers = evaluate_recipient_package(tampered, policy)
    assert layers["package_content_integrity"]["status"] == "fail" and layers["recipient_reliance_decision"]["status"] == "fail"
    tampered = deepcopy(package)
    tampered["provenance"]["native_evidence_inventory"]["artifacts"][0]["bytes_base64"] = base64.b64encode(b"x").decode()
    assert evaluate_recipient_package(tampered, policy)["native_evidence_inventory"]["status"] == "fail"


def test_required_artifact_that_is_unavailable_blocks_reliance():
    entry = _entry(embed=False, locator={"kind": "opaque-reference", "reference": "x"}, required=True)
    package = _package(inventory=build_inventory([entry]))
    layers = evaluate_recipient_package(package, _policy(package))
    assert layers["native_evidence_inventory"]["status"] == "unavailable"
    assert layers["recipient_reliance_decision"]["status"] == "fail"


def test_inventory_limits_are_respected_under_the_input_budgets():
    big = build_inventory_entry("big", data=b"\x00" * 100_000, source_format="example-receipt", source_format_version="1",
                                relation="execution_evidence", media_type="application/octet-stream")  # base64 text exceeds the string budget
    package = _package(inventory=build_inventory([big]))
    layers = evaluate_recipient_package(package, {"supported_profiles": [GENERIC_PROFILE_ID]})
    assert layers["recipient_reliance_decision"]["status"] == "fail"
    assert layers["recipient_reliance_decision"]["evidence"]["reason_code"] == common.BUDGET_EXCEEDED
    too_many = build_inventory([_entry(f"a{i}", b"x") for i in range(257)])
    package = _package(inventory=too_many)
    layers = evaluate_recipient_package(package, {"supported_profiles": [GENERIC_PROFILE_ID]})
    assert layers["recipient_reliance_decision"]["status"] == "fail"


def test_cognous_export_profile_0_2_is_unchanged_and_carries_no_inventory_of_its_own():
    """The Cognous profile is not extended: the exporter has no inventory parameter and its package digests keep the same members."""
    import inspect
    from odes.exporter import export_cognous_stack_package
    assert "inventory" not in " ".join(inspect.signature(export_cognous_stack_package).parameters)
    package = json.loads((ROOT / "examples" / "producer-v2" / "lost_ack.package.json").read_text(encoding="utf-8"))
    assert "native_evidence_inventory" not in package["provenance"]


# ---------------------------------------------------------------- reproducible bytes for a second implementation

VECTORS = ROOT / "conformance" / "generic-profile-vectors.json"


def _vector_package(canonicalization):
    record = deepcopy(BASE_RECORD)
    record["consumption_conditions"] = {"permitted_relying_parties": ["recipient.example.org"], "permitted_purposes": ["audit"], "expires_at": "2027-01-01T00:00:00Z"}
    return build_generic_package(record, created_by="example-issuer", created_at="2026-10-01T00:00:00Z", restrictions=EXPLICIT,
                                 native_evidence_inventory=build_inventory([_entry(required=True)]), canonicalization=canonicalization)


def _build_vectors():
    out = {"description": "Synthetic vectors for the generic recipient profile. The key is synthetic; only its public part is listed.",
           "profile": GENERIC_PROFILE_ID, "payload_type": signatures.PAYLOAD_TYPE, "cases": []}
    for name in (CANONICALIZATION_PROFILE, JCS_CANONICALIZATION_PROFILE):
        package = _vector_package(name)
        payload = signatures.package_payload(package)
        envelope = signatures.sign_package(package, _key(), "issuer-key-1")
        out["cases"].append({"canonicalization_profile": name, "package": package, "payload_sha256": hashlib.sha256(payload).hexdigest(),
                             "pae_sha256": hashlib.sha256(signatures.pae(signatures.PAYLOAD_TYPE, payload)).hexdigest(),
                             "trusted_keys": _trusted(), "envelope": envelope})
    return out


def test_vectors_file_matches_what_the_implementation_produces():
    _crypto()
    assert json.loads(VECTORS.read_text(encoding="utf-8")) == _build_vectors()


def test_independent_implementation_reproduces_digests_payload_and_signature_from_the_vectors():
    """Uses only json, hashlib and the Ed25519 primitive; nothing from odes."""
    _crypto()
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    vectors = json.loads(VECTORS.read_text(encoding="utf-8"))
    assert [c["canonicalization_profile"] for c in vectors["cases"]] == ["json-sort-keys-compact-utf8-no-nan", "rfc8785-jcs"]
    legacy = vectors["cases"][0]
    body = json.dumps(legacy["package"], sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    assert hashlib.sha256(body).hexdigest() == legacy["payload_sha256"]
    material = {k: legacy["package"][k] for k in ("record", "profile", "integrity", "provenance")}
    digest = "sha256:" + hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    assert digest == legacy["package"]["package_digest"]
    kind = vectors["payload_type"].encode()
    pae = b"DSSEv1 %d %s %d %s" % (len(kind), kind, len(body), body)
    assert hashlib.sha256(pae).hexdigest() == legacy["pae_sha256"]
    key = Ed25519PublicKey.from_public_bytes(base64.b64decode(legacy["trusted_keys"][0]["public_key"]))
    key.verify(base64.b64decode(legacy["envelope"]["signatures"][0]["sig"]), pae)
    inner = legacy["package"]["provenance"]["native_evidence_inventory"]["artifacts"][0]
    assert base64.b64decode(inner["bytes_base64"]) == RAW and hashlib.sha256(RAW).hexdigest() == inner["digest_value"]


def test_documentation_names_the_profile_and_the_register_lists_it():
    profile_doc = (ROOT / "profiles" / "generic-recipient-0.1.md").read_text(encoding="utf-8")
    for token in (GENERIC_PROFILE_ID, GENERIC_PROFILE_VERSION, "native_evidence_inventory", "restriction_semantics", "Replay"):
        assert token in profile_doc, token
    register = (ROOT / "docs" / "capabilities-and-versions.md").read_text(encoding="utf-8")
    assert GENERIC_PROFILE_ID in register and GENERIC_PROFILE_VERSION in register
