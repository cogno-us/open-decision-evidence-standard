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
    P4_REVISIONS, P4_PROFILE_VERSION, P2_REVISIONS, P2_PROFILE_VERSION, SECURITY_RUNTIME_GENERATIONS, ALL_V2_CONTROL_PLANE_REVISIONS)
from odes.exporter import _selected_v2_pins
from odes.recipient_validator import _evaluate_profile, _normalized_replay_material

GENERATIONS = [(SECURITY_PROFILE_VERSION, SECURITY_REVISIONS), (F5B_PROFILE_VERSION, F5B_REVISIONS),
               (P4_PROFILE_VERSION, P4_REVISIONS), (P2_PROFILE_VERSION, P2_REVISIONS)]


def test_retained_security_generation_unchanged_and_f5b_added():
    assert SECURITY_REVISIONS == {'manifest': 'e385f8c19b4444817a8b84b72ed6edbc37deb807',
        'replay': '3601fb218d5c02f5d86e55d2cf33983e5e130ac3',
        'control_plane': '996baeb476c8745b1a58ddc968b9eecc6a39b76b',
        'moltbot_safe': 'fd6b76fa0e85feb5b67324114bf790d3a12fdaf1'}
    assert F5B_REVISIONS == {'manifest': '2c36bcd0b620dbfe7ad924bc7196a3f0c04c5c5e',
        'replay': 'def0ee0f3af713283ea3cd13f0caf79e1607b651',
        'control_plane': 'a34c3dc26f84a767a55f9d5c89dc0b53e63fefa5',
        'moltbot_safe': '4a83b175d2ef0e65a7ee22a0513bb94a5fdf3a6f'}
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


@pytest.mark.parametrize('version,pins', [(SECURITY_PROFILE_VERSION, F5B_REVISIONS), (F5B_PROFILE_VERSION, SECURITY_REVISIONS),
                                          (P4_PROFILE_VERSION, F5B_REVISIONS), (F5B_PROFILE_VERSION, P4_REVISIONS),
                                          (P2_PROFILE_VERSION, P4_REVISIONS), (P4_PROFILE_VERSION, P2_REVISIONS)])
def test_cross_generation_profile_version_rejected(version, pins):
    assert _evaluate_profile(_package(version, pins), [PROFILE_V2_ID])['status'] == 'unsupported'


@pytest.mark.parametrize('pins,replay', [(F5B_REVISIONS, SECURITY_REVISIONS['replay']), (SECURITY_REVISIONS, F5B_REVISIONS['replay']),
                                         (P4_REVISIONS, F5B_REVISIONS['replay']), (F5B_REVISIONS, P4_REVISIONS['replay']),
                                         (P2_REVISIONS, P4_REVISIONS['replay']), (P4_REVISIONS, P2_REVISIONS['replay'])])
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


def test_p4_generation_is_added_beside_f5b_and_exactly_paired():
    assert P4_REVISIONS == {'manifest': '2c36bcd0b620dbfe7ad924bc7196a3f0c04c5c5e',
        'replay': P4_REVISIONS['replay'],
        'control_plane': '26a7e6594eb535827ccc248cbca36a7d119d613b',
        'moltbot_safe': '3024ef6e6ecf7da22e5f4fdf90d873f93b2a55c9'}
    assert len(P4_REVISIONS['replay']) == 40
    assert P4_PROFILE_VERSION not in {SECURITY_PROFILE_VERSION, F5B_PROFILE_VERSION}
    # The P4 tuple keeps the F5b Manifest but shares no Control Plane, runtime or Replay revision with F5b.
    for key in ('replay', 'control_plane', 'moltbot_safe'):
        assert P4_REVISIONS[key] != F5B_REVISIONS[key]
    assert P4_REVISIONS['control_plane'] in ALL_V2_CONTROL_PLANE_REVISIONS
    assert F5B_REVISIONS['control_plane'] in ALL_V2_CONTROL_PLANE_REVISIONS


def test_p2_generation_is_added_beside_p4_and_exactly_paired():
    assert P2_REVISIONS == {'manifest': 'fa170815ef96a54c233d0dd9da821b60debabf8b',
        'replay': '53c0cd60d565ea1797ed0be87a2310c5b68b24f6',
        'control_plane': 'e77fe0ee8714617899592528e660a80fbb2e864a',
        'moltbot_safe': 'cab4d9abc651c7efbafb429798d2c908f048bf5c'}
    assert all(len(v) == 40 for v in P2_REVISIONS.values())
    assert P2_PROFILE_VERSION not in {SECURITY_PROFILE_VERSION, F5B_PROFILE_VERSION, P4_PROFILE_VERSION}
    # P2 shares no revision (Manifest included, since the scan-fix stream moved it) with any earlier generation.
    for other in (SECURITY_REVISIONS, F5B_REVISIONS, P4_REVISIONS):
        for key in ('manifest', 'replay', 'control_plane', 'moltbot_safe'):
            assert P2_REVISIONS[key] != other[key]
    # The earlier P2 tuples are replaced, not kept (decisions 38, 41, 42, 43 and 46): their control planes are no longer known generations.
    from odes.exporter import ExportError as _ExportError
    from odes.common import all_accepted_replay_revisions
    for replaced_control_plane in ('3cd17ead6b24301290ad1e50ae4b22bbd93c12fb', '6093aca7b945698e89c0d8ac7c75306375e1a298', '2bac7875391cad0a431fa0d75208b7ade39743e3', '5c474ba83a1477df93dec92d076f8e62b0a98ae1'):
        assert replaced_control_plane not in ALL_V2_CONTROL_PLANE_REVISIONS
        assert replaced_control_plane not in SECURITY_RUNTIME_GENERATIONS
        with pytest.raises(_ExportError, match='unsupported Control Plane compatibility revision'):
            _selected_v2_pins(replaced_control_plane)
    for replaced_replay in ('c8e665bd1936e4da90f6a324b486a320934c4bff', '2a7963b18d96eb2e9e4fdb1a09c7588cf5c0ef00', '6a6a477495ac24e813f12bb0fe314acfe8bac9cf', 'd268b1ea864cfb9400fab334f1f72987cb1409bb'):
        assert replaced_replay not in all_accepted_replay_revisions()
    assert P2_REVISIONS['control_plane'] in ALL_V2_CONTROL_PLANE_REVISIONS
    assert P4_REVISIONS['control_plane'] in ALL_V2_CONTROL_PLANE_REVISIONS
    assert _selected_v2_pins(P2_REVISIONS['control_plane']) == P2_REVISIONS


@pytest.mark.parametrize('pinned', [7, 'x', ['a'], None, {'control_plane': ['x']}, {'control_plane': 5}])
def test_malformed_pinned_revisions_is_a_structured_failure(pinned):
    package = {'package_type': 'odes-recipient-package', 'provenance': {'pinned_revisions': pinned}}
    from odes.recipient_validator import PACKAGE_TYPE
    package['package_type'] = PACKAGE_TYPE
    result = evaluate_recipient_package(package, {})
    assert result['recipient_reliance_decision']['status'] == 'fail'


@pytest.mark.parametrize('field,value', [
    ('decision_timestamp', '2026-10-05T19:00:00+00:00\n'),
    ('decision_timestamp', '2026-10-05T19:00:00.1234567Z'),
    ('decision_timestamp', '2026-10-05T19:00:00z'),
    ('decision_timestamp', '2026-10-05 19:00:00Z'),
    ('decision_timestamp', '2026-10-05T19:00:00+0000'),
    ('decision_timestamp', '2026-10-05T19:00:60Z'),
])
def test_record_instants_outside_the_normative_grammar_are_refused(field, value):
    from odes.schema_validation import schema_errors
    record = json.loads((Path(__file__).resolve().parents[1] / 'examples/claims-review.example.json').read_text())
    record = record.get('record', record)
    assert schema_errors(record) == []
    record[field] = value
    assert schema_errors(record) != []


def test_installed_replay_revision_must_match_the_declared_generation(monkeypatch):
    from odes import exporter
    from odes.common import P2_REVISIONS, accepted_replay_revisions
    cp = P2_REVISIONS['control_plane']
    assert accepted_replay_revisions(cp) == {P2_REVISIONS['replay']}
    monkeypatch.setenv('ODES_ALLOW_UNVERIFIED_REPLAY', '0')
    monkeypatch.setattr(exporter, 'installed_replay_revision', lambda: 'f' * 40)
    with pytest.raises(ExportError, match='not an accepted'):
        exporter._require_installed_replay(cp)
    monkeypatch.setattr(exporter, 'installed_replay_revision', lambda: P2_REVISIONS['replay'])
    exporter._require_installed_replay(cp)
    # An older generation's package may be re-validated with a newer accepted Replay.
    exporter._require_installed_replay(next(iter(__import__('odes.common', fromlist=['x']).SUPPORTED_V2_CONTROL_PLANE_REVISIONS)))
    monkeypatch.setattr(exporter, 'installed_replay_revision', lambda: None)
    with pytest.raises(ExportError, match='cannot be determined'):
        exporter._require_installed_replay(cp)
    monkeypatch.setenv('ODES_ALLOW_UNVERIFIED_REPLAY', '1')
    exporter._require_installed_replay(cp)
    assert accepted_replay_revisions('0' * 40) == frozenset()


def test_installed_replay_revision_is_read_from_the_modules_git_checkout(tmp_path, monkeypatch):
    import subprocess, sys
    from odes.common import installed_replay_revision
    repo = tmp_path / 'replay'
    (repo / 'agent_replay_bundle').mkdir(parents=True)
    (repo / 'agent_replay_bundle' / '__init__.py').write_text('')
    env = {'GIT_AUTHOR_NAME': 'a', 'GIT_AUTHOR_EMAIL': 'a@example.org', 'GIT_COMMITTER_NAME': 'a', 'GIT_COMMITTER_EMAIL': 'a@example.org', 'PATH': __import__('os').environ['PATH']}
    for cmd in (['init', '-q'], ['add', '-A'], ['commit', '-q', '-m', 'x']):
        subprocess.run(['git', '-C', str(repo), *cmd], check=True, env=env)
    head = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    monkeypatch.syspath_prepend(str(repo))
    sys.modules.pop('agent_replay_bundle', None)
    assert installed_replay_revision() == head
