import json
import sqlite3
from pathlib import Path
import pytest
from scripts.render_workspace import workspace_snapshot

ROOT=Path(__file__).resolve().parent.parent


@pytest.fixture(scope='module')
def workspace():
    path=ROOT/'data/population.sqlite3'
    if not path.exists():pytest.skip('Generate population first')
    db=sqlite3.connect(f'file:{path}?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    try:
        yield workspace_snapshot(db),db
    finally:db.close()


def test_workspace_does_not_invent_completed_investigations(workspace):
    snapshot,db=workspace
    assert len(snapshot['alerts'])==db.execute('SELECT count(*) FROM investigation_cases').fetchone()[0]
    assert all(a['status']=='awaiting_investigation' for a in snapshot['alerts'])
    assert snapshot['reports']==[]
    assert snapshot['dispositions']==[]
    assert not snapshot['worker_connected']


def test_case_source_preview_respects_case_scope_and_cutoff(workspace):
    snapshot,db=workspace
    scopes={}
    for row in db.execute('SELECT evidence_id,account_id FROM evidence_scope'):
        scopes.setdefault(row['evidence_id'],set()).add(row['account_id'])
    for a in snapshot['alerts']:
        case=snapshot['details'][a['id']]
        accounts={o['account_id'] for o in case['orders']}
        for e in case['evidence']:
            assert scopes[e['evidence_id']] & accounts
            assert e['status']!='access_denied'
            assert max(e['event_at'],e['available_at'],e['ingested_at'])<=a['cutoff_at']
        assert set(case)=={'orders','features','signal_features','evidence','policy'}
