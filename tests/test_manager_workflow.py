import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app import runtime as rt
from app.config import settings
from app.server import app

HEADERS={'X-Requested-With':'surveillance-ui'}

@pytest.fixture
def case(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'runtime_path',str(tmp_path/'runtime.sqlite3'))
    monkeypatch.setattr(settings,'escalation_artifacts',str(tmp_path/'pdfs'))
    monkeypatch.setattr(settings,'surveillance_manager_email','manager@example.test')
    rt.init();run,_=rt.ingest('CASE-AF1D9C5F')
    claim={'text':'Authority is unresolved.','citations':[{'evidence_id':'E','quote':'Authority is unresolved.'}]}
    report={'assessment':'inconclusive','recommendation':'request_more_evidence','summary':claim,'observations':[claim],
            'alternative_explanations':[claim],'gaps':[claim],'reviewer_questions':['Obtain the instruction?']}
    rt.remember(run['run_id'],{'evidence_id':'E','status':'available','text':claim['text']});rt.finish(run['run_id'],report,1,1)
    client=TestClient(app);response=client.post('/api/cases/'+run['case_id']+'/review',headers=HEADERS,json={'run_id':run['run_id'],'action':'escalate','note':'Manager should review the unresolved instruction.'})
    assert response.status_code==200
    return run,client


def command(case,action,**kw):
    run,client=case
    with rt.db() as c:state=dict(c.execute('select * from manager_cases where case_id=?',(run['case_id'],)).fetchone())
    body={'action':action,'note':'Obtain the original signed instruction and reconcile quantity.','owner':'Operations','run_id':state['current_run_id'],
          'version':state['version'],'request_id':str(uuid4())}
    body.update(kw)
    return client.post('/api/cases/'+run['case_id']+'/manager-review',headers=HEADERS,json=body),body


def test_manager_evidence_request_waits_until_document_arrives(case):
    run,client=case;response,_=command(case,'return_for_evidence')
    assert response.status_code==200 and response.json()['status']=='awaiting_evidence'
    assert rt.claim() is None
    assert rt.details(run['run_id'])['status']=='awaiting_evidence'
    with rt.db() as c:assert c.execute('select count(*) from runs').fetchone()[0]==1
    url='/api/cases/'+run['case_id']+'/review'
    assert client.post(url,headers=HEADERS,json={'run_id':run['run_id'],'action':'request_more_evidence','note':'Still waiting'}).status_code==422
    data={'run_id':run['run_id'],'action':'request_more_evidence','note':'Review the newly supplied instruction.',
          'evidence':{'title':'Client instruction','reference':'WORKFLOW-FIXTURE','content':'Test fixture document claims the instruction covers the linked order. Its authenticity is unverified.'}}
    new=client.post(url,headers=HEADERS,json=data);assert new.status_code==200
    detail=rt.details(new.json()['run_id'])
    assert detail['status']=='queued' and detail['parent_run']==run['run_id']
    assert 'Manager evidence request:' in detail['review_request']
    assert detail['manager_review']['status']=='investigating'
    assert len(rt.submitted_sources(detail['run_id']))==1
    rt.finish(detail['run_id'],rt.details(run['run_id'])['report'],1,1)
    detail=rt.details(detail['run_id']);assert detail['manager_review']['status']=='awaiting_analyst'
    assert detail['status']=='ready_for_review'
    assert command(case,'approve_closure',closure_reason='explained_activity')[0].status_code==409
    assert client.post(url,headers=HEADERS,json={'run_id':detail['run_id'],'action':'mark_reviewed','note':'Trying to bypass sign-off'}).status_code==409
    assert client.post(url,headers=HEADERS,json={'run_id':detail['run_id'],'action':'escalate','note':'Return this assessed evidence to the manager.'}).status_code==200
    closed,_=command(case,'approve_closure',closure_reason='insufficient_basis_after_review')
    assert closed.json()['status']=='closed'
    assert rt.details(detail['run_id'])['report']==rt.details(run['run_id'])['report']
    assert rt.details(detail['run_id'])['status']=='closed'
    assert len(rt.details(detail['run_id'])['manager_actions'])==2


def test_assignment_is_one_deep_run_and_retry_is_idempotent(case):
    run,client=case;response,body=command(case,'assign_investigation',owner='Senior investigator')
    assert response.status_code==200
    child=rt.details(response.json()['run_id'])
    assert child['required_depth']=='deep' and child['queue_priority']==100 and child['parent_run']==run['run_id']
    retry=client.post('/api/cases/'+run['case_id']+'/manager-review',headers=HEADERS,json=body)
    assert retry.json()['duplicate'] and retry.json()['run_id']==child['run_id']
    with rt.db() as c:assert c.execute('select count(*) from runs').fetchone()[0]==2
    assert command(case,'refer',destination='Legal team')[0].status_code==409


def test_referral_records_destination_without_external_dispatch(case):
    run,_=case
    with rt.db() as c:before=c.execute('select count(*) from escalation_packets').fetchone()[0]
    res,_=command(case,'refer',destination='Legal team',owner='')
    assert res.json()['status']=='referred' and res.json()['owner']=='Legal team'
    detail=rt.details(run['run_id']);assert detail['status']=='referred'
    assert detail['manager_review']['destination']=='Legal team'
    assert detail['events'][-1]['payload']['dispatch'].startswith('Local referral recorded')
    with rt.db() as c:assert c.execute('select count(*) from escalation_packets').fetchone()[0]==before


def test_closure_requires_reason_and_is_preserved(case):
    run,client=case
    assert command(case,'approve_closure')[0].status_code==409
    response,_=command(case,'approve_closure',closure_reason='resolved_control_issue')
    assert response.json()['status']=='closed'
    assert command(case,'return_for_evidence')[0].status_code==409
    rt.meta_set('index_ready',True)
    res=client.post('/api/demo/events',headers=HEADERS,json={'scenario':'closing_valuation','event_id':'prevent-manager-bypass'})
    assert res.status_code==409
    workspace=client.get('/api/workspace').json();a=next(a for a in workspace['alerts'] if a['id']==run['case_id'])
    assert a['status']=='closed' and a['manager_review']['closure_reason']=='resolved_control_issue'


def test_manager_decision_rejects_stale_run_and_blank_owner(case):
    run,client=case
    assert command(case,'assign_investigation',owner='   ')[0].status_code==409
    assert command(case,'return_for_evidence',note='     ')[0].status_code==409
    response,body=command(case,'return_for_evidence')
    body.update(request_id=str(uuid4()),action='approve_closure',closure_reason='explained_activity')
    assert client.post('/api/cases/'+run['case_id']+'/manager-review',headers=HEADERS,json=body).status_code==409
    body.update(request_id=str(uuid4()),run_id=str(uuid4()))
    assert client.post('/api/cases/'+run['case_id']+'/manager-review',headers=HEADERS,json=body).status_code==409


def test_manager_history_is_append_only(case):
    command(case,'refer',destination='Compliance investigations')
    with pytest.raises(sqlite3.IntegrityError):
        with rt.db() as c:c.execute("update manager_actions set note='overwrite'")
    with pytest.raises(sqlite3.IntegrityError):
        with rt.db() as c:c.execute('delete from manager_actions')


def test_parallel_manager_actions_cannot_create_two_assignments(case):
    run,client=case
    state=rt.details(run['run_id'])['manager_review']
    def post(_):return client.post('/api/cases/'+run['case_id']+'/manager-review',headers=HEADERS,json={
      'action':'assign_investigation','note':'Investigate approval records independently.','owner':'Senior investigator',
      'run_id':run['run_id'],'version':state['version'],'request_id':str(uuid4())}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(post,range(2)))
    assert sorted(codes)==[200,409]
    with rt.db() as c:assert c.execute('select count(*) from runs').fetchone()[0]==2


def test_legacy_escalation_gets_manager_state_without_new_email(case):
    run,_=case
    with rt.db() as c:
        c.execute('delete from manager_cases')
        packets=c.execute('select count(*) from escalation_packets').fetchone()[0]
    rt.init();rt.init()
    assert rt.details(run['run_id'])['manager_review']['status']=='awaiting_manager'
    with rt.db() as c:assert c.execute('select count(*) from escalation_packets').fetchone()[0]==packets
