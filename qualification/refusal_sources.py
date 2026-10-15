"""Actual current CP/executor records; explicit integration dependencies required."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest
from agent_replay_bundle.importers import (import_bounded_workflow, ImportContractError,
    CONTROL_PLANE_REFUSAL_REVISION, MOLTBOT_REFUSAL_REVISION)
from agent_replay_bundle.refusal_evidence import EXTENDED, extend_retained_inputs


@pytest.fixture
def actual(tmp_path, monkeypatch):
    cp=os.environ.get('ARB_REFUSAL_CP_ROOT');executor=os.environ.get('ARB_REFUSAL_EXECUTOR_ROOT')
    fixture=os.environ.get('ARB_PINNED_MANIFEST_FIXTURE')
    assert all((cp,executor,fixture)), 'exact refusal-profile source checkouts required'
    monkeypatch.syspath_prepend(str(Path(cp)/'src'));monkeypatch.syspath_prepend(executor)
    monkeypatch.setenv('MOLTBOT_SAFE_CONTROL_PLANE_ROOT',cp);monkeypatch.setenv('MOLTBOT_SAFE_MANIFEST_FIXTURE',fixture)
    import agent_control_plane.bounded as bounded
    monkeypatch.setattr(bounded,'_now',lambda:datetime(2026,10,5,19,tzinfo=timezone.utc))
    spec=importlib.util.spec_from_file_location('refusal_runtime_helpers',Path(executor)/'tests/test_safe_executor.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    h,p,r,w,d,dest,ex,env=mod._integrated(tmp_path)
    return h,p,r,w,d,dest,ex,env


def bundle(actual, change='grant'):
    from engine.producer_contract import export_execution_artifacts
    h,p,r,w,d,dest,ex,env=actual
    if change=='grant':next(iter(r.statuses.values())).status='revoked'
    elif change=='approval':next(iter(r.approvals.values())).status='revoked'
    elif change=='policy':next(iter(r.policies.values())).version='changed'
    elif change=='evidence':next(iter(r.evidence.values())).state='stale'
    if change=='lost-ack':
        assert ex.execute(envelope=env,proposal=p,decision=d,now=h.NOW,simulate='lost_ack').status=='unknown'
    result=ex.execute(envelope=env,proposal=p,decision=d,now=h.NOW)
    cp=w.records.load().model_dump(mode='json',exclude_none=False)
    exported=export_execution_artifacts(env,result,dest,repository_revision=MOLTBOT_REFUSAL_REVISION)
    proposal=p.model_dump(mode='json',exclude_none=False)
    replay=import_bounded_workflow(cp,proposal=proposal,moltbot_export=exported,control_plane_revision=CONTROL_PLANE_REFUSAL_REVISION)
    return cp,proposal,exported,replay.model_dump(mode='json'),w.manifest


