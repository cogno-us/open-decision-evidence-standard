import json
from pathlib import Path
import pytest
from odes.cli import main
from odes.common import sha256, PROFILE_V2_ID
from odes.exporter import _validate_manifest_binding, ExportError
from odes.recipient_validator import _status_identity_matches, _evaluate_consumption, evaluate_recipient_package


def test_failed_recipient_decision_is_nonzero(tmp_path, capsys):
    package=tmp_path/'package.json';policy=tmp_path/'policy.json'
    package.write_text('{}');policy.write_text('{}')
    assert main(['recipient-validate',str(package),'--policy',str(policy)]) == 1
    assert json.loads(capsys.readouterr().out)['recipient_reliance_decision']['status']=='fail'


def test_issuer_bound_to_both_status_and_recipient_policy():
    issuer={'organization_id':'org-a','system_id':'issuer-a'}
    record={'decision_id':'d','issuer':issuer,'authority':{'authority_basis':'a'}}
    status={'record_id':'d','authority_basis':'a','evaluation_scope':'audit','issuer':issuer}
    policy={'evaluation_scope':'audit','trusted_issuer':issuer}
    assert not _status_identity_matches(record,status,policy)
    other={**record,'issuer':{'organization_id':'org-b','system_id':'issuer-a'}}
    assert _status_identity_matches(other,status,policy)


@pytest.mark.parametrize('risk',[
 {'prohibited_use_flag':True,'restricted_use_flag':False,'jurisdiction':'test'},
 {'prohibited_use_flag':False,'restricted_use_flag':True,'jurisdiction':'test'},
 {'prohibited_use_flag':False,'restricted_use_flag':False,'jurisdiction':'other'},
 {},
])
def test_restrictions_and_jurisdiction_fail_closed(risk):
    record={'consumption_conditions':{'permitted_relying_parties':['r'],'permitted_purposes':['audit']},'risk_coordinates':risk}
    assert _evaluate_consumption(record,'r','audit',{'jurisdiction':'test'})['status']=='fail'


def test_unambiguous_declared_action_required():
    manifest={'manifest_id':'m','manifest_version':'1.1','actions':[{'action_id':'valid'}]}
    proposal={'manifest_id':'m','manifest_version':'1.1','manifest_digest':sha256(manifest),
              'action_id':'missing','payload':{},'payload_commitment':sha256({})}
    with pytest.raises(ExportError,match='exactly one'):_validate_manifest_binding(manifest,proposal)
    manifest['actions']=[{'action_id':'missing'},{'action_id':'missing'}]
    proposal['manifest_digest']=sha256(manifest)
    with pytest.raises(ExportError,match='exactly one'):_validate_manifest_binding(manifest,proposal)


def test_record_only_v2_profile_cannot_skip_replay_layer():
    p=json.loads((Path(__file__).resolve().parents[1]/'examples/producer-v2/lost_ack.package.json').read_text())
    p['profile'].pop('implementation_profile',None)
    p['record']['verification']['conformance_profile']=PROFILE_V2_ID
    result=evaluate_recipient_package(p,{})
    assert 'replay_semantic_consistency' in result
    assert result['declared_profile_conformance']['status']=='fail'


# F5b repairs (2026-10-16): lifecycle alias conflicts, Manifest alias/inventory
# ambiguity, and non-object recipient input shapes.
from odes.exporter import _status_from_sources


@pytest.mark.parametrize('metadata', [
 {'odes_freshness': 'current', 'freshness': 'revoked', 'revoked_at': '2026-01-01T00:00:00Z'},
 {'odes_freshness': 'current', 'freshness': 'superseded', 'superseded_by': 'r2'},
 {'odes_freshness': 'revoked', 'freshness': 'current', 'revoked_at': '2026-01-01T00:00:00Z'},
])
def test_conflicting_lifecycle_freshness_aliases_rejected(metadata):
    with pytest.raises(ExportError, match='conflicting lifecycle freshness'):
        _status_from_sources({'metadata': metadata})


@pytest.mark.parametrize('metadata', [
 {'freshness': 'current', 'revoked': True, 'revoked_at': '2026-01-01T00:00:00Z'},
 {'freshness': 'current', 'superseded': True, 'superseded_by': 'r2'},
 {'freshness': 'revoked', 'revoked': False, 'revoked_at': '2026-01-01T00:00:00Z'},
 {'odes_freshness': 'superseded', 'superseded': False, 'superseded_by': 'r2'},
])
def test_lifecycle_flag_contradicting_freshness_rejected(metadata):
    with pytest.raises(ExportError, match='contradicts lifecycle freshness'):
        _status_from_sources({'metadata': metadata})


def test_consistent_lifecycle_aliases_still_export():
    assert _status_from_sources({'metadata': {'odes_freshness': 'current', 'freshness': 'current', 'revoked': False, 'superseded': False}}) == {'freshness': 'current', 'superseded': False, 'revoked': False}
    assert _status_from_sources({'metadata': {'freshness': 'revoked', 'revoked': True, 'revoked_at': '2026-01-01T00:00:00Z'}})['revoked'] is True

