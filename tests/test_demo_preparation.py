import json
import sqlite3
import pytest
from app import runtime as rt
from app.config import settings
from app.server import demo_event,DemoEvent
from scripts.prepare_demo import prepare,DEMO_CASES


def test_demo_reset_archives_decisions_retains_evidence_and_waits_for_start(tmp_path,monkeypatch):
    path=tmp_path/'runtime.sqlite3'
    monkeypatch.setattr(settings,'runtime_path',str(path))
    rt.init();rt.meta_set('index_ready',True)
    for cid in DEMO_CASES:
        r,_=rt.ingest(cid)
        rt.remember(r['run_id'],{'evidence_id':cid,'text':'Retained source'})
        rt.finish(r['run_id'],{'assessment':'inconclusive'},1,1)
        rt.update(r['run_id'],status='reviewed')
        with rt.db() as c:c.execute('INSERT INTO reviews VALUES (?,?,?,?,?,?)',(cid,r['run_id'],rt.now(),'Analyst','mark_reviewed','Original decision'))
    result=prepare(path,tmp_path/'archives')
    with sqlite3.connect(result['archive']) as c:
        assert c.execute('SELECT count(*) FROM reviews').fetchone()[0]==3
        assert c.execute('SELECT count(*) FROM notifications').fetchone()[0]==3
    with rt.db() as c:
        assert c.execute('SELECT count(*) FROM reviews').fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM notifications').fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM snapshots').fetchone()[0]==3
        assert c.execute("SELECT count(*) FROM runs WHERE status='awaiting_investigation'").fetchone()[0]==3
    assert rt.claim() is None
    event=DemoEvent(scenario='closing_valuation',event_id='rehearsal-test-123')
    first=demo_event(event);second=demo_event(event)
    assert first['run_id']==second['run_id'] and second['duplicate']
    run=rt.claim()
    assert run['case_id']==DEMO_CASES[0] and run['revision']==2
    assert rt.claim() is None
    assert rt.details(run['run_id'])['report'] is None
    assert rt.details(run['parent_run'])['report']['assessment']=='inconclusive'


def test_demo_reset_refuses_active_work(tmp_path,monkeypatch):
    path=tmp_path/'runtime.sqlite3'
    monkeypatch.setattr(settings,'runtime_path',str(path))
    rt.init();rt.ingest(DEMO_CASES[0])
    with pytest.raises(RuntimeError,match='active investigations'):prepare(path,tmp_path/'archives')
    assert rt.claim()['case_id']==DEMO_CASES[0]
