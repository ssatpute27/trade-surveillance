import json
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import pytest
from fastapi.testclient import TestClient
from app import runtime as rt
from app.agent import definitions,BASE,validate_report,check_claim
from app.config import settings,ROOT
from app.models import Claim,Report
from app.server import app
from app.evidence_tools import EvidenceTools

@pytest.fixture
def runtime(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'runtime_path',str(tmp_path/'runtime.sqlite3'))
    rt.init()
    if not (ROOT/'data/population.sqlite3').exists():pytest.skip('Generate source population first')
    with rt.source() as c:case=c.execute('SELECT case_id FROM investigation_cases LIMIT 1').fetchone()[0]
    return case


def test_concurrent_intake_and_claim_are_deduplicated(runtime):
    with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(lambda _:rt.ingest(runtime),range(4)))
    assert sum(not duplicate for _,duplicate in rows)==1
    with ThreadPoolExecutor(max_workers=4) as pool:claims=list(pool.map(lambda _:rt.claim(),range(4)))
    assert sum(r is not None for r in claims)==1


def test_audit_cannot_be_rewritten(runtime):
    run,_=rt.ingest(runtime)
    with pytest.raises(sqlite3.IntegrityError):
        with rt.db() as c:c.execute('DELETE FROM audit WHERE run_id=?',(run['run_id'],))


def test_interrupted_run_preserves_evidence(runtime):
    run,_=rt.ingest(runtime);rt.claim()
    rt.remember(run['run_id'],{'evidence_id':'E-test','text':'Retained','status':'available'})
    rt.recover();d=rt.details(run['run_id'])
    assert d['status']=='manual_review' and d['evidence'][0]['text']=='Retained'
    assert any(e['kind']=='recovery' for e in d['events'])


def test_report_and_outbox_are_deduplicated(runtime):
    run,_=rt.ingest(runtime)
    rt.finish(run['run_id'],{'assessment':'inconclusive'},10,1)
    rt.finish(run['run_id'],{'assessment':'inconclusive'},10,1)
    with rt.db() as c:assert c.execute('SELECT count(*) FROM notifications').fetchone()[0]==1


def test_workflow_tools_follow_server_state():
    names=lambda **kw:{s['name'] for s in definitions(**kw)}
    assert not {'record_initial_assessment','promote_to_deep','finish_investigation'} & names(done=set(),mandatory=BASE)
    assert names(done=BASE,mandatory=BASE)=={'record_initial_assessment'}
    pending=names(done=BASE,initial=True,mandatory=BASE,needs_deep=True)
    assert 'promote_to_deep' in pending and 'finish_investigation' not in pending
    assert 'finish_investigation' in names(done=BASE,initial=True,depth='deep',mandatory=BASE,needs_deep=True)


def test_wrong_quotes_and_broad_exculpation_fail():
    records={'E':{'text':'A signed instruction was located.','status':'available'}}
    claim=Claim(text='A mandate exists',citations=[{'evidence_id':'E','quote':'fabricated quotation'}])
    assert check_claim(claim,records)
    claim=Claim(text='No evidence of improper motive is present.',citations=[{'evidence_id':'E','quote':records['E']['text']}])
    assert check_claim(claim,records)


def test_missing_evidence_requires_a_cited_gap():
    available={'text':'An order was placed.','status':'available'};missing={'text':'The access archive is unavailable.','status':'unavailable'}
    c={'text':'An order was placed.','citations':[{'evidence_id':'E','quote':available['text']}]}
    report=Report(assessment='inconclusive',recommendation='request_more_evidence',summary=c,observations=[c],alternative_explanations=[c],gaps=[c],reviewer_questions=['Can the archive be obtained?'])
    assert validate_report(report,{'E':available,'G':missing})


def test_human_review_requires_a_draft_and_preserves_revisions(runtime):
    run,_=rt.ingest(runtime);rt.update(run['run_id'],status='manual_review')
    client=TestClient(app);headers={'X-Requested-With':'surveillance-ui'}
    r=client.post('/api/cases/'+runtime+'/review',headers=headers,json={'run_id':run['run_id'],'action':'escalate','note':'Testing a missing draft'})
    assert r.status_code==409
    r=client.post('/api/cases/'+runtime+'/review',headers=headers,json={'run_id':run['run_id'],'action':'request_more_evidence','note':'Obtain the missing archive'})
    assert r.status_code==200
    prior=rt.details(run['run_id']);next_run=rt.details(r.json()['run_id'])
    assert prior['status']=='more_evidence_requested' and len(prior['reviews'])==1
    assert next_run['revision']==2 and next_run['parent_run']==run['run_id']
    assert next_run['status']=='queued' and next_run['review_request']=='Obtain the missing archive'


def test_scope_cutoff_and_denial_redaction(tmp_path,monkeypatch):
    source=tmp_path/'source.sqlite3';db=sqlite3.connect(source)
    db.executescript('CREATE TABLE evidence(evidence_id TEXT,kind TEXT,status TEXT,event_at TEXT,available_at TEXT,ingested_at TEXT,content TEXT,metadata_json TEXT,source_record_id TEXT); CREATE TABLE evidence_scope(evidence_id TEXT,account_id TEXT);')
    for eid,account,status,date,text in [('allowed','A','available','2025-05-01','Allowed message'),('denied','A','access_denied','2025-05-01','SECRET_DENIED'),('future','A','available','2025-05-03','SECRET_FUTURE'),('other','B','available','2025-05-01','SECRET_OTHER')]:
        db.execute('INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?)',(eid,'communication',status,date,date,date,text,'{}',eid))
        db.execute('INSERT INTO evidence_scope VALUES (?,?)',(eid,account))
    db.commit();db.close()
    monkeypatch.setattr(settings,'source_path',str(source));monkeypatch.setattr(settings,'runtime_path',str(tmp_path/'runtime.sqlite3'));rt.init()
    monkeypatch.setattr('app.evidence_tools.context',lambda _: {'case_id':'case','accounts':['A'],'cutoff':'2025-05-02','start':'2025-05-01'})
    tool=EvidenceTools('run','case',None);records=tool.records(['communication'])
    assert {r['evidence_id'] for r in records}=={'allowed','denied'}
    returned=[tool.as_record(r) for r in records]
    assert 'SECRET_' not in json.dumps(returned)
    assert next(r for r in returned if r['evidence_id']=='denied')['status']=='access_denied'


def test_api_failure_routes_to_human_attention(runtime,monkeypatch):
    from app.agent import run_investigation
    from agents.models.interface import Model
    class FailingModel(Model):
        async def get_response(self,*args,**kwargs):raise TimeoutError('Upstream test timeout')
        async def stream_response(self,*args,**kwargs):
            raise TimeoutError('Upstream test timeout')
            yield
    monkeypatch.setattr('app.sdk_workflow.create_sdk_model',lambda _:FailingModel())
    run,_=rt.ingest(runtime);rt.claim()
    result=run_investigation(run)
    assert result['status']=='manual_review'
    assert result['report'] is None and result['notification'] is None
    assert any(e['kind']=='manual_review_required' for e in result['events'])


def test_agent_cannot_see_offline_answer_keys():
    from app import agent,evidence_tools
    for module in (agent,evidence_tools):
        text=__import__('inspect').getsource(module)
        assert 'population_truth' not in text and 'app.evaluation' not in text


def test_pdf_linewraps_resolve_to_the_exact_source_span():
    text='Use account scope and time cutoffs before search.\nUnavailable evidence cannot establish absence.'
    claim=Claim(text='The policy requires scoped retrieval.',citations=[{'evidence_id':'P','quote':'Use account scope and time cutoffs before search. Unavailable evidence cannot establish absence.'}])
    assert check_claim(claim,{'P':{'text':text,'status':'available'}})==[]
    assert claim.citations[0].quote==text


def test_an_incoming_event_starts_a_persisted_worker_without_an_analyst_click(runtime,monkeypatch):
    import time
    rt.meta_set('index_ready',True)
    rt.meta_set('automatic_intake',False)
    def bounded_test_worker(run):
        rt.audit(run['run_id'],'test_worker_claimed',{'case_id':run['case_id']})
        rt.update(run['run_id'],status='manual_review',error='Isolated worker test completed')
    monkeypatch.setattr('app.server.run_investigation',bounded_test_worker)
    with TestClient(app) as client:
        headers={'X-Requested-With':'surveillance-ui'}
        first=client.post('/api/cases/'+runtime+'/events',headers=headers)
        second=client.post('/api/cases/'+runtime+'/events',headers=headers)
        assert first.status_code==second.status_code==200
        assert first.json()['run_id']==second.json()['run_id']
        assert second.json()['duplicate'] is True
        for _ in range(40):
            result=client.get('/api/cases/'+runtime+'/investigation').json()
            if result['status']=='manual_review':break
            time.sleep(.05)
        assert result['status']=='manual_review'
        assert any(e['kind']=='test_worker_claimed' for e in result['events'])


def test_replay_is_read_only_and_checks_integrity(runtime,tmp_path,monkeypatch):
    from app import replay
    monkeypatch.setattr(replay,'FOLDER',tmp_path/'recordings')
    run,_=rt.ingest(runtime);rt.finish(run['run_id'],{'assessment':'inconclusive'},10,1)
    manifest=replay.archive_completed();snapshot=replay.load_replay(run['run_id'])
    assert snapshot['mode']=='replay' and snapshot['recorded_run']['case_id']==runtime
    with rt.db() as c:assert c.execute('SELECT count(*) FROM notifications').fetchone()[0]==1
    path=replay.FOLDER/(run['run_id']+'.json');path.write_text('{}')
    with pytest.raises(ValueError,match='integrity'):replay.load_replay(run['run_id'])


def test_policy_search_is_scoped_and_preserves_pdf_provenance(runtime):
    from types import SimpleNamespace
    run,_=rt.ingest(runtime)
    rt.meta_set('policy_index',{'ready':True,'vector_store_id':'vs_test'})
    captured={}
    def create(**kw):
        captured.update(kw)
        hit=SimpleNamespace(text='Use account scope before search.',filename='POL-test.pdf',file_id='file_test',score=.9)
        return SimpleNamespace(id='resp_test',usage=SimpleNamespace(total_tokens=5),output=[SimpleNamespace(type='file_search_call',results=[hit])])
    client=SimpleNamespace(responses=SimpleNamespace(create=create))
    tools=EvidenceTools(run['run_id'],runtime,client);records=tools.policy('Required review')
    assert captured['tools'][0]['filters']=={'type':'in','key':'family','value':tools.ctx['families']}
    assert records[0]['filename']=='POL-test.pdf' and records[0]['file_id']=='file_test'
    assert rt.recalled(run['run_id'])[records[0]['evidence_id']]['text']=='Use account scope before search.'


def test_demo_delivery_is_idempotent_and_preserves_case_revisions(runtime):
    rt.meta_set('index_ready',True)
    client=TestClient(app);headers={'X-Requested-With':'surveillance-ui'}
    body={'scenario':'documented_order','event_id':'demo-event-one'}
    first=client.post('/api/demo/events',headers=headers,json=body)
    second=client.post('/api/demo/events',headers=headers,json=body)
    assert first.status_code==second.status_code==200
    assert first.json()['run_id']==second.json()['run_id'] and second.json()['duplicate']
    prior=rt.details(first.json()['run_id']);assert prior['queue_priority']==100
    rt.update(prior['run_id'],status='manual_review',error='Preserved test outcome')
    body['event_id']='demo-event-two'
    third=client.post('/api/demo/events',headers=headers,json=body)
    new=rt.details(third.json()['run_id'])
    assert new['revision']==prior['revision']+1 and new['parent_run']==prior['run_id']
    assert rt.details(prior['run_id'])['error']=='Preserved test outcome'
    with rt.db() as c:assert c.execute('SELECT count(*) FROM notifications').fetchone()[0]==0


def test_demo_queue_priority_and_live_activity_come_from_real_events(runtime):
    rt.meta_set('index_ready',True);normal,_=rt.ingest(runtime)
    client=TestClient(app)
    event=client.post('/api/demo/events',headers={'X-Requested-With':'surveillance-ui'},json={'scenario':'documented_order','event_id':'demo-priority-event'}).json()
    claimed=rt.claim();assert claimed['run_id']==event['run_id']
    rt.audit(claimed['run_id'],'tool_started',{'tool':'read_trades','reason':'Verify the submitted order'})
    rt.remember(claimed['run_id'],{'evidence_id':'E-live-test','text':'Order received','status':'available'})
    activity=client.get('/api/activity').json()
    card=next(c for c in activity['cards'] if c['run_id']==event['run_id'])
    assert card['status']=='running' and card['source_count']==1
    assert card['last_event']['payload']['reason']=='Verify the submitted order'
    assert card['assessment'] is None


def test_demo_rejects_unknown_scenarios_and_untrusted_mutations(runtime):
    rt.meta_set('index_ready',True);client=TestClient(app)
    body={'scenario':'unapproved','event_id':'demo-invalid-event'}
    assert client.post('/api/demo/events',json=body).status_code==403
    assert client.post('/api/demo/events',headers={'X-Requested-With':'surveillance-ui'},json=body).status_code==422
