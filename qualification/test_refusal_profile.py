from copy import deepcopy
import pytest
from refusal_sources import actual, bundle
from odes.exporter import export_cognous_stack_package, ExportError
from odes.recipient_validator import evaluate_recipient_package
from odes.common import REFUSAL_REVISIONS, REFUSAL_PROFILE_VERSION
from scripts.qualify_merged_producer import policy

@pytest.mark.parametrize('change',['grant','approval','policy','evidence','lost-ack','success'])
def test_exact_refusal_evidence_reaches_recipient(actual,change):
    cp,p,e,b,m=bundle(actual,change)
    package=export_cognous_stack_package(m,b)
    result=evaluate_recipient_package(package,policy(package))
    assert result['replay_semantic_consistency']['status']=='pass'
    assert result['package_content_integrity']['status']=='pass'
    assert result['integrity_authentication_checks']['status']=='unavailable'
    assert package['profile']['implementation_profile_version']==REFUSAL_PROFILE_VERSION
    assert package['provenance']['pinned_revisions']==REFUSAL_REVISIONS
    assert package['provenance']['retained_sources']['reconstruction_bundle']==b
    facts=package['provenance']['execution_facts']
    for field,kind in [('refusals','effect_time_refusal'),('resolution_checks','resolution_check'),('closeouts','attempt_closeout')]:
        assert facts[kind]==cp[field]
    assert facts['input_time_floors']==[cp['input_time_floors']]
    assert facts['retry_permission']=='not_established'

@pytest.mark.parametrize('change',['drop-refusal','substitute-effect','erase-floors','promote-status'])
def test_retained_evidence_tampering_is_rejected(actual,change):
    _,_,_,b,m=bundle(actual)
    if change=='drop-refusal': b['records']=[r for r in b['records'] if r['record_type']!='effect_time_refusal']
    elif change=='erase-floors': b['records']=[r for r in b['records'] if r['record_type']!='input_time_floors']
    elif change=='substitute-effect': next(r for r in b['records'] if r['record_type']=='effect_time_refusal')['data']['effect_id']='other'
    else:b['status']='reconstruction_partial'
    with pytest.raises((ExportError,ValueError)):export_cognous_stack_package(m,b)
