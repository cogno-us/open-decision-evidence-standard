"""Actual accepted producers; run ODES inside Replay's destination immutability checks."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sqlite3
import sys
import tempfile

from odes.common import MERGED_REVISIONS as PINNED_V2_REVISIONS, PROFILE_V2_ID, sha256
from odes.exporter import export_cognous_stack_package
from odes.recipient_validator import evaluate_recipient_package
from odes.schema_validation import validate_record


def policy(package):
    return {
        'supported_profiles': [PROFILE_V2_ID], 'relying_party': 'recipient.example.org',
        'purpose': 'audit', 'now': '2026-10-06T00:00:00Z',
        'status_max_age_seconds': 300, 'evaluation_scope': 'recipient_reliance',
        'allow_unauthenticated_informational_inspection': True,
        'trusted_digests': [package['package_digest']], 'trusted_key_refs': [],
        'status_inputs': {'record_id': package['record']['decision_id'],
            'authority_basis': package['record']['authority']['authority_basis'],
            'evaluation_scope': 'recipient_reliance', 'evaluated_at': '2026-10-06T00:00:00Z',
            'evidence_freshness': 'current', 'freshness': 'current', 'revoked': False,
            'superseded': False, 'authority_valid_at_decision_verified': True},
    }


def main(output):
    root = Path(os.environ['ODES_V2_REPLAY_ROOT']).resolve()
    assert subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip() == PINNED_V2_REVISIONS['replay']
    sys.path.insert(0, str(root / 'src'))
    from agent_replay_bundle import import_bounded_workflow
    spec = importlib.util.spec_from_file_location('accepted_replay_generator', root / 'scripts/generate_producer_v2_examples.py')
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    manifest = json.loads(Path(os.environ['ARB_PINNED_MANIFEST_FIXTURE']).read_text())
    captured = []
    def inspect(*args, **kwargs):
        bundle = import_bounded_workflow(*args, **kwargs)
        # Explicit synthetic fixture status label; never defaulted by exporter.
        bundle.metadata['freshness'] = 'current'
        source = bundle.model_dump(mode='json')
        package = export_cognous_stack_package(manifest, source)
        validate_record(package['record'])
        recipient = evaluate_recipient_package(package, policy(package))
        assert recipient['replay_semantic_consistency']['status'] == 'pass', recipient
        assert recipient['package_content_integrity']['status'] == 'pass'
        assert recipient['integrity_authentication_checks']['status'] == 'unavailable'
        if package['record']['authority']['authority_valid_at_decision']:
            assert recipient['recipient_reliance_decision']['status'] == 'informational_only'
        else:
            assert recipient['recipient_reliance_decision']['status'] != 'pass'
        assert package['provenance']['source_artifacts']['reconstruction_bundle_id'] == bundle.bundle_id
        assert package['provenance']['source_artifacts']['reconstruction_bundle_digest'] == sha256(source)
        assert package['provenance']['retained_sources']['reconstruction_bundle'] == source
        captured.append({'bundle': source, 'package': package, 'recipient': recipient})
        return bundle
    # Replay generator snapshots CP record bytes and full logical SQLite contents
    # before invoking this wrapper and asserts unchanged after ODES inspection.
    generator.import_bounded_workflow = inspect
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        generator.main(Path(temporary))
        sources = json.loads((Path(temporary) / 'producer_v2_sources.json').read_text())
        results = json.loads((Path(temporary) / 'producer_v2_results.json').read_text())
    cases = dict(zip(sources, captured, strict=True))
    # A genuinely held authorization decision, with no execution envelope.
    executor_root = Path(os.environ['ARB_V2_MOLTBOT_ROOT']).resolve()
    fixture_spec = importlib.util.spec_from_file_location('odes_held_fixture', executor_root / 'tests/test_safe_executor.py')
    fixture = importlib.util.module_from_spec(fixture_spec)
    fixture_spec.loader.exec_module(fixture)
    with tempfile.TemporaryDirectory() as temporary:
        h, proposal, resolver, workflow, _, destination, _, request = fixture._integrated(Path(temporary))
        resolver.statuses[request.operation.grant_id].status = 'revoked'
        workflow.records = h.BoundedRecordStore(Path(temporary) / 'held.json', 'run-1')
        decision = workflow.decide(proposal, now=h.NOW)
        assert decision.result == 'hold'
        before_cp = workflow.records.path.read_bytes()
        def rows():
            with sqlite3.connect(destination.path) as db:
                return list(db.iterdump())
        before_rows = rows()
        inspect(workflow.records.load().model_dump(mode='json'),
                proposal=proposal.model_dump(mode='json', exclude_none=False),
                control_plane_revision=PINNED_V2_REVISIONS['control_plane'])
        assert rows() == before_rows and workflow.records.path.read_bytes() == before_cp
        assert destination.effect_count(request.operation.grant_id) == 0
        cases['held'] = captured[-1]
        results['scenarios']['held'] = {'decision_id': decision.decision_id,
            'effect_count_before_import': 0, 'effect_count_after_import': 0,
            'records_unchanged': True, 'classification': 'required_safety_invariant_pass'}
    for name, data in cases.items():
        facts = data['package']['provenance']['execution_facts']
        results['scenarios'][name]['odes_destination_observed'] = facts['destination_observed']
        results['scenarios'][name]['odes_package_digest'] = data['package']['package_digest']
        results['scenarios'][name]['recipient_status'] = data['recipient']['recipient_reliance_decision']['status']
    results['pins']['replay'] = PINNED_V2_REVISIONS['replay']
    results['scope'] += '; export, record validation and recipient validation executed inside unchanged-store assertions'
    (output / 'cases.json').write_text(json.dumps({'manifest': manifest, 'cases': cases}, indent=2) + '\n')
    (output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    for name in ('rejected_wrong_effect', 'restart', 'lost_ack', 'partial', 'prior_absence'):
        (output / f'{name}.package.json').write_text(json.dumps(cases[name]['package'], indent=2) + '\n')
    print(f'{len(cases)} ODES actual-producer scenarios passed without producer-state changes')


if __name__ == '__main__':
    main(Path(sys.argv[1]))
