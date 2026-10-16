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
from odes.exporter import _actions, _manifest_id, _manifest_version, _status_from_sources


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


@pytest.mark.parametrize('manifest', [
 {'manifest_id': 'm', 'id': 'other'},
 {'manifest_id': 'm', 'name': 'other'},
 {'id': 'm', 'name': 'other'},
])
def test_conflicting_manifest_identity_aliases_rejected(manifest):
    with pytest.raises(ExportError, match='conflicting Manifest identity'):
        _manifest_id(manifest)


@pytest.mark.parametrize('manifest', [
 {'manifest_version': '1.1', 'version': '2.0'},
 {'manifest_version': '1.1', 'schema_version': '1.0'},
 {'version': '1.1', 'schema_version': '9'},
])
def test_conflicting_manifest_version_aliases_rejected(manifest):
    with pytest.raises(ExportError, match='conflicting Manifest version'):
        _manifest_version(manifest)


def test_agreeing_manifest_aliases_accepted():
    assert _manifest_id({'manifest_id': 'm', 'id': 'm'}) == 'm'
    assert _manifest_version({'manifest_version': '1.1', 'version': '1.1'}) == '1.1'


@pytest.mark.parametrize('manifest', [
 {'actions': [{'action_id': 'a'}], 'tool_actions': [{'action_id': 'b'}]},
 {'actions': [{'action_id': 'a'}], 'declared_actions': []},
 {'action_inventory': [{'action_id': 'a'}], 'declared_actions': [{'action_id': 'a'}]},
])
def test_multiple_action_inventories_rejected(manifest):
    with pytest.raises(ExportError, match='more than one action inventory'):
        _actions(manifest)


def test_inventory_alongside_tool_actions_rejected():
    manifest = {'actions': [{'action_id': 'a'}], 'tools': [{'tool_name': 't', 'actions': [{'action_id': 'b'}]}]}
    with pytest.raises(ExportError, match='both actions and tools'):
        _actions(manifest)
    manifest = {'manifest_id': 'm', 'manifest_version': '1.1', **manifest}
    proposal = {'manifest_id': 'm', 'manifest_version': '1.1', 'manifest_digest': sha256(manifest),
                'action_id': 'a', 'payload': {}, 'payload_commitment': sha256({})}
    with pytest.raises(ExportError, match='both actions and tools'):
        _validate_manifest_binding(manifest, proposal)


def test_single_inventory_and_tool_only_actions_still_supported():
    assert _actions({'actions': [{'action_id': 'a'}], 'tools': [{'tool_name': 't'}]}) == [{'action_id': 'a'}]
    assert _actions({'tools': [{'tool_name': 't', 'actions': [{'action_id': 'b'}]}]}) == [{'action_id': 'b', 'tool_name': 't'}]


def _lost_ack_package():
    return json.loads((Path(__file__).resolve().parents[1]/'examples/producer-v2/lost_ack.package.json').read_text())


@pytest.mark.parametrize('bad', [[], 'x', 1, None, True])
@pytest.mark.parametrize('where', ['package', 'policy', 'record.verification', 'record.consumption_conditions', 'profile', 'policy.status_inputs'])
def test_non_object_shapes_return_structured_fail(where, bad):
    package, policy = _lost_ack_package(), {}
    if where == 'package':
        package = bad
    elif where == 'policy':
        policy = bad
    elif where == 'policy.status_inputs':
        policy = {'status_inputs': bad}
    elif where == 'profile':
        package['profile'] = bad
    else:
        package['record'][where.split('.')[1]] = bad
    result = evaluate_recipient_package(package, policy)
    assert result['recipient_reliance_decision']['status'] == 'fail'


@pytest.mark.parametrize('package_text', [
 '[]',
 '[{"package_type": "odes_decision_evidence_export_package"}]',
 '{"package_type": "odes_decision_evidence_export_package", "record": {"verification": []}}',
 '{"package_type": "odes_decision_evidence_export_package", "record": {"consumption_conditions": "x"}}',
 '{not json',
 pytest.param('[' * 200000 + ']' * 200000, id='deeply-nested-array'),
])
def test_recipient_cli_malformed_input_exits_nonzero_with_json(tmp_path, capsys, package_text):
    package = tmp_path/'package.json'; policy = tmp_path/'policy.json'
    package.write_text(package_text); policy.write_text('{}')
    assert main(['recipient-validate', str(package), '--policy', str(policy)]) == 1
    assert json.loads(capsys.readouterr().out)['recipient_reliance_decision']['status'] == 'fail'


def test_recipient_cli_non_object_policy_exits_nonzero_with_json(tmp_path, capsys):
    package = tmp_path/'package.json'; policy = tmp_path/'policy.json'
    package.write_text(json.dumps(_lost_ack_package())); policy.write_text('[]')
    assert main(['recipient-validate', str(package), '--policy', str(policy)]) == 1
    assert json.loads(capsys.readouterr().out)['recipient_reliance_decision']['status'] == 'fail'


# F3R (2026-10-16): F5b merged security-runtime generation is added beside the
# retained security generation; each generation is an exact tuple.
from odes.common import (SECURITY_REVISIONS, SECURITY_PROFILE_VERSION, F5B_REVISIONS, F5B_PROFILE_VERSION,
    SECURITY_RUNTIME_GENERATIONS, ALL_V2_CONTROL_PLANE_REVISIONS)
from odes.exporter import _selected_v2_pins
from odes.recipient_validator import _evaluate_profile, _normalized_replay_material

GENERATIONS = [(SECURITY_PROFILE_VERSION, SECURITY_REVISIONS), (F5B_PROFILE_VERSION, F5B_REVISIONS)]


def test_retained_security_generation_unchanged_and_f5b_added():
    assert SECURITY_REVISIONS == {'manifest': 'e385f8c19b4444817a8b84b72ed6edbc37deb807',
        'replay': '3601fb218d5c02f5d86e55d2cf33983e5e130ac3',
        'control_plane': '996baeb476c8745b1a58ddc968b9eecc6a39b76b',
        'moltbot_safe': 'fd6b76fa0e85feb5b67324114bf790d3a12fdaf1'}
    assert F5B_REVISIONS == {'manifest': '2c36bcd0b620dbfe7ad924bc7196a3f0c04c5c5e',
        'replay': '79ba16d48b9be1e059b3045989c7df960c3df1c2',
        'control_plane': 'a34c3dc26f84a767a55f9d5c89dc0b53e63fefa5',
        'moltbot_safe': 'e20f92e104aba2ba6ad06120d8549c6170eaf63f'}
    assert SECURITY_PROFILE_VERSION != F5B_PROFILE_VERSION
    # Generations share no component revision, so no pin can bridge them.
    assert not set(SECURITY_REVISIONS.values()) & set(F5B_REVISIONS.values())
    assert {SECURITY_REVISIONS['control_plane'], F5B_REVISIONS['control_plane']} <= set(ALL_V2_CONTROL_PLANE_REVISIONS)


@pytest.mark.parametrize('version,pins', GENERATIONS)
def test_generation_pins_selected_exactly_by_control_plane(version, pins):
    assert _selected_v2_pins(pins['control_plane']) == pins
    assert SECURITY_RUNTIME_GENERATIONS[pins['control_plane']] == (version, pins)


def _package(version, pins, replay=None):
    pinned = {**pins, 'replay': replay or pins['replay']}
    return {'package_version': '0.1.0',
            'profile': {'implementation_profile': PROFILE_V2_ID, 'implementation_profile_version': version,
                        'schema_name': 'pder-v0.1', 'schema_version': '0.1'},
            'record': {'verification': {'conformance_profile': PROFILE_V2_ID}},
            'provenance': {'pinned_revisions': pinned, 'selected_revisions': pinned,
                           'replay_validation': {'required_revision': pinned['replay']}}}


@pytest.mark.parametrize('version,pins', GENERATIONS)
def test_generation_profile_version_accepted_for_own_control_plane(version, pins):
    assert _evaluate_profile(_package(version, pins), [PROFILE_V2_ID])['status'] == 'pass'


@pytest.mark.parametrize('version,pins', [(SECURITY_PROFILE_VERSION, F5B_REVISIONS), (F5B_PROFILE_VERSION, SECURITY_REVISIONS)])
def test_cross_generation_profile_version_rejected(version, pins):
    assert _evaluate_profile(_package(version, pins), [PROFILE_V2_ID])['status'] == 'unsupported'


@pytest.mark.parametrize('pins,replay', [(F5B_REVISIONS, SECURITY_REVISIONS['replay']), (SECURITY_REVISIONS, F5B_REVISIONS['replay'])])
def test_cross_generation_replay_pin_rejected(pins, replay):
    version = SECURITY_RUNTIME_GENERATIONS[pins['control_plane']][0]
    with pytest.raises(ValueError, match='exact qualified Replay revision'):
        _normalized_replay_material(_package(version, pins, replay), _package(version, pins))


@pytest.mark.parametrize('version,pins', GENERATIONS)
def test_same_generation_replay_pin_accepted(version, pins):
    left, right = _normalized_replay_material(_package(version, pins), _package(version, pins))
    assert left == right


@pytest.mark.parametrize('component', ['manifest', 'moltbot_safe'])
def test_cross_generation_component_pin_differs_from_reexport(component):
    # A package that keeps the F5b CP/Replay but carries a retained-generation
    # component pin cannot match the exact F5b re-export material.
    mixed = _package(F5B_PROFILE_VERSION, {**F5B_REVISIONS, component: SECURITY_REVISIONS[component]})
    expected = _package(F5B_PROFILE_VERSION, _selected_v2_pins(F5B_REVISIONS['control_plane']))
    left, right = _normalized_replay_material(mixed, expected)
    assert left != right
