"""Decision 45: a configured trusted-digest set anchors only ``package_digest``. ``integrity.value`` (the record/profile digest) does not
cover ``provenance`` (limits, unsupported_semantics, restriction_semantics), so it is never accepted as the anchor for the
'complete package bound' pass; a package with stripped provenance and a recomputed ``package_digest`` must not pass under it."""
from copy import deepcopy

from odes.canonicalization import digest_for
from odes.common import CANONICALIZATION_PROFILE
from odes.recipient_validator import _evaluate_package_content_integrity, _material_package_content
from test_generic_recipient_profile import _package


def _original():
    """A package whose provenance states a limit and an unsupported semantic (an honest producer's export)."""
    return _package(limits=["example limit: synthetic data only"], unsupported_semantics=["example unsupported semantic"])


def _layer(package, trusted):
    return _evaluate_package_content_integrity(deepcopy(package), trusted)


def _tamper(package):
    t = deepcopy(package)
    t["provenance"]["limits"] = []
    t["provenance"]["unsupported_semantics"] = []
    t["package_digest"] = digest_for(CANONICALIZATION_PROFILE, _material_package_content(t))
    return t


def test_control_the_package_digest_anchor_passes_for_the_original():
    p = _original()
    assert _layer(p, [p["package_digest"]])["status"] == "pass"


def test_record_profile_digest_alone_is_not_accepted_as_the_anchor():
    p = _original()
    layer = _layer(p, [p["integrity"]["value"]])
    assert layer["status"] == "unavailable"
    assert "bound by digest" not in " ".join(layer["reasons"])


def test_tampered_provenance_with_recomputed_package_digest_does_not_pass_under_the_record_profile_anchor():
    p = _original()
    t = _tamper(p)
    assert t["provenance"]["limits"] == [] and t["integrity"]["value"] == p["integrity"]["value"]
    assert t["package_digest"] != p["package_digest"]
    layer = _layer(t, [p["integrity"]["value"]])
    assert layer["status"] != "pass"
    assert "bound by digest" not in " ".join(layer["reasons"])


def test_tampered_package_is_unavailable_under_the_original_package_digest_anchor():
    p = _original()
    assert _layer(_tamper(p), [p["package_digest"]])["status"] == "unavailable"
