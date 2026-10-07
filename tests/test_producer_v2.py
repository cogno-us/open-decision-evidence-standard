import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from odes.common import PINNED_V2_REVISIONS, PROFILE_V2_ID, SUPPORTED_V2_CONTROL_PLANE_REVISIONS, sha256
from odes.exporter import ExportError, export_cognous_stack_package
from odes.recipient_validator import evaluate_recipient_package
from odes.schema_validation import validate_record


@pytest.fixture(scope='module')
def produced(tmp_path_factory):
    if not os.environ.get('ODES_V2_REPLAY_ROOT'):
        pytest.skip('accepted producer checkouts not configured')
    out = tmp_path_factory.mktemp('odes-v2')
    subprocess.run([sys.executable, 'scripts/qualify_producer_v2.py', str(out)], check=True)
    data = json.loads((out / 'cases.json').read_text())
    data['results'] = json.loads((out / 'results.json').read_text())
    return data


def policy(package):
    from scripts.qualify_producer_v2 import policy as make_policy
    return make_policy(package)


def records(bundle, kind):
    return [r for r in bundle['records'] if r['record_type'] == kind]


@pytest.mark.parametrize('name', ['success', 'rejected_wrong_effect', 'rejected_stale',
    'rejected_malformed', 'rejected_contradictory', 'unavailable', 'restart',
    'rejected_restart', 'lost_ack', 'partial', 'prior_absence', 'denied',
    'historical_applied', 'historical_absent', 'held'])
def test_actual_producer_lifecycle(produced, name):
    case = produced['cases'][name]
    source = copy.deepcopy(case['bundle'])
    package = export_cognous_stack_package(produced['manifest'], source)
    validate_record(package['record'])
    result = evaluate_recipient_package(package, policy(package))
    assert result['replay_semantic_consistency']['status'] == 'pass'
    assert result['package_content_integrity']['status'] == 'pass'
    assert result['integrity_authentication_checks']['status'] == 'unavailable'
    assert source == case['bundle']
    assert package['provenance']['retained_sources']['reconstruction_bundle'] == source
    assert package['provenance']['source_artifacts']['reconstruction_bundle_digest'] == sha256(source)
    assert package['provenance']['source_artifacts']['reconstruction_bundle_id'] == source['bundle_id']
    selected_cp = source['metadata']['control_plane_revision']
    assert selected_cp in SUPPORTED_V2_CONTROL_PLANE_REVISIONS
    assert package['provenance']['pinned_revisions']['control_plane'] == selected_cp
    assert package['provenance']['selected_revisions']['control_plane'] == selected_cp
    assert package['provenance']['pinned_revisions']['replay'] == PINNED_V2_REVISIONS['replay']
    assert package['provenance']['replay_validation']['required_revision'] == PINNED_V2_REVISIONS['replay']
    facts = package['provenance']['execution_facts']
    assert facts['retry_permission'] == 'not_established'
    assert facts['independent_delivery_verification'] == 'unavailable'
    if name in {'rejected_wrong_effect','rejected_stale','rejected_malformed','rejected_contradictory','unavailable'}:
        assert facts['reconstruction_status'] == 'reconstruction_complete'
        assert facts['destination_observed'] == 'unknown'
        assert facts['execution_results'][0]['observation'] is None
        assert facts['execution_results'][0]['acknowledged'] is True
        assert len(facts['destination_effects']) == 1
    if name == 'rejected_wrong_effect':
        assert facts['rejected_observations'][0]['effect_id'] != source['records'][1]['data']['effect_id']
    if name in {'restart','rejected_restart'}:
        assert facts['destination_observed'] == 'applied'
        assert any(not r['observation_accepted'] for r in facts['reconciliations'])
    if name == 'lost_ack':
        assert facts['acknowledgement_summary'] == 'unknown'
        assert facts['destination_observed'] == 'applied'
        assert facts['execution_results'][0]['acknowledged'] is False
    if name == 'partial':
        assert facts['reconstruction_status'] == 'reconstruction_complete'
        assert facts['destination_observed'] == 'partial'
    if name == 'prior_absence':
        assert facts['destination_observed'] == 'absent'
        assert any(r['result'] == 'observed_absent' and not r['retry_eligible'] for r in facts['reconciliations'])
        assert not facts['destination_effects']
    evidence = produced['results']['scenarios'][name]
    assert evidence['records_unchanged']
    assert evidence['effect_count_before_import'] == evidence['effect_count_after_import']


@pytest.mark.parametrize('attack', ['promoted_rejection','completeness','effect','decision',
    'attempt','reconciliation','payload','target','amount','profile','revision',
    'copied_reconciliation','history','accepted_observation','missing_rejected'])
def test_adversarial_replay_sources(produced, attack):
    name = 'rejected_wrong_effect' if attack in {'promoted_rejection','completeness','missing_rejected','history'} else 'success'
    bundle = copy.deepcopy(produced['cases'][name]['bundle'])
    execution = records(bundle,'execution_result')[0]['data']
    if attack == 'promoted_rejection':
        rejected = records(bundle,'rejected_executor_observation')[0]['data']
        execution['observation'] = copy.deepcopy(rejected); execution['observed_state'] = 'applied'
    elif attack == 'completeness':
        assert bundle['status'] == 'reconstruction_complete'
        execution['status'] = 'executed'; execution['observed_state'] = 'applied'
    elif attack == 'effect': execution['effect_id'] = 'other'
    elif attack == 'decision': execution['decision_id'] = 'other'
    elif attack == 'attempt': records(bundle,'moltbot_attributed_control_plane_attempt')[0]['data']['attempt_id'] = 'fake'
    elif attack == 'reconciliation': records(bundle,'executor_control_plane_evidence')[0]['data']['reconciliation']['effect_id'] = 'other'
    elif attack in {'payload','target','amount'}:
        records(bundle,'destination_effect')[0]['data'][{'payload':'payload_json'}.get(attack,attack)] = {'payload':'{"fake":true}','target':'other','amount':999}[attack]
    elif attack == 'profile': bundle['metadata']['moltbot_producer_contract']['interface_profile_version'] = '9.0.0'
    elif attack == 'revision': bundle['metadata']['control_plane_revision'] = 'unknown'
    elif attack == 'copied_reconciliation':
        bundle['records'] = [r for r in bundle['records'] if r['record_type'] != 'reconciliation']
    elif attack == 'history': next(iter(bundle['metadata']['effect_observation_history'].values()))['latest_supported_destination_state'] = 'applied'
    elif attack == 'accepted_observation': records(bundle,'executor_observation')[0]['data']['effect_id'] = 'other'
    elif attack == 'missing_rejected': bundle['records'] = [r for r in bundle['records'] if r['record_type'] != 'rejected_executor_observation']
    with pytest.raises(ExportError):
        export_cognous_stack_package(produced['manifest'], bundle)


@pytest.mark.parametrize('rehash', [False, True])
def test_package_completeness_cannot_promote_delivery(produced, rehash):
    package = copy.deepcopy(produced['cases']['unavailable']['package'])
    package['provenance']['execution_facts']['destination_observed'] = 'applied'
    if rehash:
        package['package_digest'] = sha256({k:package[k] for k in ('record','profile','integrity','provenance')})
    result = evaluate_recipient_package(package, policy(package))
    assert result['replay_semantic_consistency']['status'] == 'fail'
    assert result['recipient_reliance_decision']['status'] == 'fail'
    assert result['integrity_authentication_checks']['status'] == 'unavailable'
    assert result['package_content_integrity']['status'] == ('pass' if rehash else 'fail')


@pytest.mark.parametrize('attack', ['stale','future','malformed','no_timezone','no_age','no_clock','scope','recipient','purpose','no_status'])
def test_recipient_boundaries(produced, attack):
    package = produced['cases']['success']['package']
    p = policy(package)
    if attack in {'stale','future','malformed','no_timezone'}:
        p['status_inputs']['evaluated_at'] = {'stale':'2026-10-05T00:00:00Z','future':'2026-10-07T00:00:00Z','malformed':'bad','no_timezone':'2026-10-06T00:00:00'}[attack]
    elif attack == 'no_age': p.pop('status_max_age_seconds')
    elif attack == 'no_clock': p.pop('now')
    elif attack == 'scope': p['status_inputs']['evaluation_scope'] = 'other'
    elif attack == 'recipient': p['relying_party'] = 'other'
    elif attack == 'purpose': p['purpose'] = 'other'
    else: p['status_inputs'] = {}
    result = evaluate_recipient_package(package,p)
    assert result['recipient_reliance_decision']['status'] == 'fail'
    assert result['integrity_authentication_checks']['status'] == 'unavailable'
    if attack == 'no_status':
        assert result['historical_authority_assertions']['status'] == 'unavailable'
        assert result['authority_status_and_freshness']['status'] == 'unavailable'


def test_public_cli_roundtrip(produced,tmp_path):
    from odes.cli import main
    manifest=tmp_path/'manifest.json'; bundle=tmp_path/'replay.json'; out=tmp_path/'package.json'
    manifest.write_text(json.dumps(produced['manifest']))
    bundle.write_text(json.dumps(produced['cases']['unavailable']['bundle']))
    assert main(['export-cognous','--manifest',str(manifest),'--reconstruction',str(bundle),'--out',str(out)]) == 0
    assert main(['validate-record',str(out)]) == 0
    p=tmp_path/'policy.json'; result=tmp_path/'recipient.json'
    p.write_text(json.dumps(policy(json.loads(out.read_text()))))
    assert main(['recipient-validate',str(out),'--policy',str(p),'--out',str(result)]) == 0
    assert json.loads(result.read_text())['recipient_reliance_decision']['status'] == 'informational_only'


def test_repaired_package_cannot_be_relabeled_historical(produced):
    from odes.common import PROFILE_ID, PROFILE_VERSION
    package = copy.deepcopy(produced['cases']['success']['package'])
    package['profile']['implementation_profile'] = PROFILE_ID
    package['profile']['implementation_profile_version'] = PROFILE_VERSION
    package['record']['verification']['conformance_profile'] = PROFILE_ID
    package['integrity']['value'] = sha256({k:package[k] for k in ('record','profile')})
    package['package_digest'] = sha256({k:package[k] for k in ('record','profile','integrity','provenance')})
    p = policy(package); p['supported_profiles'] = [PROFILE_ID, PROFILE_V2_ID]
    result = evaluate_recipient_package(package,p)
    assert result['declared_profile_conformance']['status'] == 'fail'
    assert result['recipient_reliance_decision']['status'] == 'fail'


def test_generated_lifecycle_packages():
    for path in Path('examples/producer-v2').glob('*.package.json'):
        package = json.loads(path.read_text())
        validate_record(package['record'])
        result = evaluate_recipient_package(package, policy(package))
        assert result['package_content_integrity']['status'] == 'pass'
        assert result['replay_semantic_consistency']['status'] == 'pass'
        assert result['recipient_reliance_decision']['status'] == 'informational_only'
        replay = package['provenance']['retained_sources']['reconstruction_bundle']
        assert package['provenance']['source_artifacts']['reconstruction_bundle_digest'] == sha256(replay)


@pytest.mark.parametrize('field', ['control_plane', 'moltbot_safe', 'replay'])
def test_selected_revision_contradictions_rejected(produced, field):
    package = copy.deepcopy(produced['cases']['success']['package'])
    package['provenance']['selected_revisions'][field] = 'contradictory'
    package['package_digest'] = sha256({k: package[k] for k in ('record', 'profile', 'integrity', 'provenance')})
    result = evaluate_recipient_package(package, policy(package))
    assert result['package_content_integrity']['status'] == 'pass'
    assert result['replay_semantic_consistency']['status'] == 'fail'
    assert result['recipient_reliance_decision']['status'] == 'fail'


def test_old_replay_cannot_claim_new_control_plane(produced):
    from odes.common import SUPPORTED_V2_REPLAY_REVISIONS
    package = copy.deepcopy(produced['cases']['success']['package'])
    provenance = package['provenance']
    for field in ('pinned_revisions', 'selected_revisions'):
        provenance[field]['replay'] = SUPPORTED_V2_REPLAY_REVISIONS[0]
    provenance['replay_validation']['required_revision'] = SUPPORTED_V2_REPLAY_REVISIONS[0]
    package['package_digest'] = sha256({k: package[k] for k in ('record', 'profile', 'integrity', 'provenance')})
    result = evaluate_recipient_package(package, policy(package))
    assert result['replay_semantic_consistency']['status'] == 'fail'


@pytest.mark.parametrize('field', ['moltbot_safe_revision', 'manifest_revision', 'alvorada_revision'])
def test_source_revision_contradictions_rejected(produced, field):
    source = copy.deepcopy(produced['cases']['success']['bundle'])
    source['metadata'][field] = 'contradictory'
    with pytest.raises(ExportError, match=field):
        export_cognous_stack_package(produced['manifest'], source)


def test_historical_export_preserves_selected_revision_and_source():
    for path in Path('examples/producer-v2').glob('*.package.json'):
        original = json.loads(path.read_text())
        before = copy.deepcopy(original)
        sources = original['provenance']['retained_sources']
        package = export_cognous_stack_package(sources['manifest'], sources['reconstruction_bundle'])
        assert package['provenance']['selected_revisions']['control_plane'] == SUPPORTED_V2_CONTROL_PLANE_REVISIONS[0]
        assert package['provenance']['retained_sources'] == sources
        assert evaluate_recipient_package(package, policy(package))['replay_semantic_consistency']['status'] == 'pass'
        assert original == before
