import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from app import runtime as rt, chatgpt_cases as cases
from app.config import settings

@pytest.fixture
def case(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'runtime_path',str(tmp_path/'cases.sqlite3'))
    monkeypatch.setattr(settings,'escalation_artifacts',str(tmp_path/'pdfs'))
    monkeypatch.setattr(settings,'surveillance_manager_email','manager@example.test')
    rt.init();cases.init();r,_=rt.ingest('CASE-AF1D9C5F')
    claim={'text':'Authority is unresolved.','citations':[{'evidence_id':'E','quote':'Authority is unresolved.'}]}
    report={'assessment':'inconclusive','recommendation':'request_more_evidence','summary':claim,'observations':[claim],
      'alternative_explanations':[claim],'gaps':[claim],'reviewer_questions':['Obtain instruction?']}
    rt.remember(r['run_id'],{'evidence_id':'E','status':'available','text':claim['text']})
    rt.finish(r['run_id'],report,1,1)
    return r


def test_source_scope_denial_and_no_read_side_effects(case):
    rt.remember(case['run_id'],{'evidence_id':'DENIED','status':'access_denied','text':'SECRET','metadata':{'private':'SECRET'},'citation_options':['SECRET']})
    with rt.db() as c:before=c.execute('select count(*) from snapshots').fetchone()[0]
    assert 'SECRET' not in json.dumps(cases.read_source(case['case_id'],'DENIED'))
    assert 'SECRET' not in json.dumps(cases.read_section(case['case_id'],'sources'))
    overview=cases.case_overview(case['case_id'])
    assert overview['cited_sources']==[{'evidence_id':'E','status':'available','text':'Authority is unresolved.'}]
    assert 'SECRET' not in json.dumps(overview)
    with pytest.raises(ValueError):cases.read_source('CASE-0088C625','E')
    with pytest.raises(ValueError):cases.read_section(case['case_id'],'sources',offset=-1)
    with rt.db() as c:assert c.execute('select count(*) from snapshots').fetchone()[0]==before


def test_lookup_and_full_fills(case):
    matches=cases.find_cases('O-0000253')['items']
    assert len(matches)==1 and matches[0]['case_id']==case['case_id']
    rows=[];offset=0
    while True:
        p=cases.read_section(case['case_id'],'trades',offset=offset,limit=2)['fills'];rows.extend(p['items'])
        if p['next_offset'] is None:break
        offset=p['next_offset']
    assert len(rows)==p['total'] and len({r['fill_id'] for r in rows})==len(rows)
    assert cases.case_overview(case['case_id'])['report']['assessment']=='inconclusive'


def test_confirmation_token_and_concurrent_deduplication(case):
    p,token=cases.propose(case['case_id'],case['run_id'],'mark_reviewed','Reviewed the evidence and unresolved authority.')
    assert rt.details(case['run_id'])['status']=='ready_for_review'
    with pytest.raises(HTTPException):cases.confirm(p['proposal_id'],'wrong-token')
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:cases.confirm(p['proposal_id'],token),range(2)))
    assert all(r['status']=='reviewed' for r in results)
    with rt.db() as c:
        assert c.execute('select count(*) from reviews').fetchone()[0]==1
        event=json.loads(c.execute("select payload from audit where kind='human_review'").fetchone()[0])
        assert event['origin']=='chatgpt' and event['actor']=='ChatGPT analyst'


def test_stale_or_expired_confirmation_cannot_write(case):
    p,token=cases.propose(case['case_id'],case['run_id'],'mark_reviewed','Review complete.')
    with rt.db() as c:c.execute("update chatgpt_proposals set expires_at='2000-01-01' where id=?",(p['proposal_id'],))
    with pytest.raises(HTTPException,match='expired'):cases.confirm(p['proposal_id'],token)
    p,token=cases.propose(case['case_id'],case['run_id'],'request_more_evidence','Obtain the original source.')
    rt.ingest(case['case_id'],revision=2,parent_run=case['run_id'])
    with pytest.raises(HTTPException,match='revision changed'):cases.confirm(p['proposal_id'],token)
    assert rt.details(case['run_id'])['reviews']==[]


def test_followup_retry_queues_one_child_and_scopes_submitted_evidence(case):
    evidence={'title':'Instruction document','reference':'TEST-ONLY','content':'Unverified supplied instruction for testing the review workflow.'}
    p,token=cases.propose(case['case_id'],case['run_id'],'request_more_evidence','Validate this instruction.',evidence)
    first=cases.confirm(p['proposal_id'],token);assert cases.confirm(p['proposal_id'],token)==first
    assert not rt.submitted_sources(case['run_id'])
    assert len(rt.submitted_sources(first['run_id']))==1
    with rt.db() as c:assert c.execute('select count(*) from runs').fetchone()[0]==2


def test_escalation_uses_existing_packet_and_manager_guards(case):
    p,token=cases.propose(case['case_id'],case['run_id'],'escalate','Escalate the unresolved authority to the manager.')
    first=cases.confirm(p['proposal_id'],token);second=cases.confirm(p['proposal_id'],token)
    assert first['packet_id']==second['packet_id']
    assert first['pdf_status']==second['pdf_status']=='ready'
    with rt.db() as c:
        assert c.execute('select count(*) from escalation_packets').fetchone()[0]==1
        assert c.execute('select count(*) from manager_cases').fetchone()[0]==1
    # Restore ready status to simulate an assessment returned from the manager; closure still forbidden.
    rt.update(case['run_id'],status='ready_for_review')
    with pytest.raises(ValueError,match='Manager'):cases.propose(case['case_id'],case['run_id'],'mark_reviewed','Approve closure.')


def test_mcp_confirmation_token_is_only_in_ui_metadata(case):
    from app.chatgpt_mcp import prepare_analyst_decision,mcp,decision_card
    result=prepare_analyst_decision(case['case_id'],case['run_id'],'mark_reviewed','Review complete.')
    token=result.meta['confirmation_token']
    assert token not in json.dumps(result.structuredContent)
    assert token not in json.dumps([c.model_dump() for c in result.content])
    tools=asyncio.run(mcp.list_tools());confirm=next(t for t in tools if t.name=='confirm_analyst_decision')
    assert confirm.meta['ui']['visibility']==['app']
    assert confirm.annotations.destructiveHint and not confirm.annotations.readOnlyHint
    prepare=next(t for t in tools if t.name=='prepare_analyst_decision')
    assert not prepare.meta or 'ui' not in prepare.meta
    submit=next(t for t in tools if t.name=='submit_analyst_decision')
    assert submit.annotations.destructiveHint and not submit.annotations.readOnlyHint
    assert not submit.meta or 'ui' not in submit.meta
    assert '<script type="module">' in decision_card()


def test_mcp_confirmation_returns_structured_committed_status(case):
    from app.chatgpt_mcp import confirm_analyst_decision
    p,token=cases.propose(case['case_id'],case['run_id'],'mark_reviewed','Review complete.')
    result=confirm_analyst_decision(p['proposal_id'],token)
    assert result.structuredContent=={'status':'reviewed'}
    assert json.loads(result.content[0].text)==result.structuredContent


def test_dashboard_rejects_missing_and_stale_run_without_recording(case):
    from fastapi.testclient import TestClient
    from app.server import app
    client=TestClient(app);url='/api/cases/'+case['case_id']+'/review'
    headers={'X-Requested-With':'surveillance-ui'}
    body={'action':'mark_reviewed','note':'Review complete.'}
    assert client.post(url,headers=headers,json=body).status_code==422
    next_run,_=rt.ingest(case['case_id'],revision=2,parent_run=case['run_id'])
    rt.finish(next_run['run_id'],rt.details(case['run_id'])['report'],1,1)
    response=client.post(url,headers=headers,json={**body,'run_id':case['run_id']})
    assert response.status_code==409 and 'revision changed' in response.json()['detail']
    assert not rt.details(case['run_id'])['reviews']
    assert not rt.details(next_run['run_id'])['reviews']
    assert client.post(url,headers=headers,json={**body,'run_id':next_run['run_id']}).json()['status']=='reviewed'


def test_native_write_binds_exact_proposal_and_is_idempotent(case):
    note='Review complete after checking all source evidence.'
    p,_=cases.propose(case['case_id'],case['run_id'],'mark_reviewed',note)
    with pytest.raises(HTTPException,match='match'):
        cases.submit_from_host(p['proposal_id'],case['case_id'],case['run_id'],'mark_reviewed','Different note')
    first=cases.submit_from_host(p['proposal_id'],case['case_id'],case['run_id'],'mark_reviewed',note)
    second=cases.submit_from_host(p['proposal_id'],case['case_id'],case['run_id'],'mark_reviewed',note)
    assert first==second and first['submitted'] and first['status']=='reviewed'
    with rt.db() as c:assert c.execute('SELECT count(*) FROM reviews').fetchone()[0]==1


def test_native_write_rejects_expired_proposal(case):
    note='Review complete after checking source evidence.'
    p,_=cases.propose(case['case_id'],case['run_id'],'mark_reviewed',note)
    with rt.db() as c:c.execute("UPDATE chatgpt_proposals SET expires_at='2000-01-01' WHERE id=?",(p['proposal_id'],))
    with pytest.raises(HTTPException,match='expired'):
        cases.submit_from_host(p['proposal_id'],case['case_id'],case['run_id'],'mark_reviewed',note)
    assert rt.details(case['run_id'])['status']=='ready_for_review'


def test_saved_escalation_cannot_report_success_after_demo_reset(case):
    note='Escalate unresolved authority for manager review.'
    proposal,_=cases.propose(case['case_id'],case['run_id'],'escalate',note)
    args=(proposal['proposal_id'],case['case_id'],case['run_id'],'escalate',note)
    assert cases.submit_from_host(*args)['status']=='escalated'
    rt.update(case['run_id'],status='ready_for_review')
    with rt.db() as c:c.execute('DELETE FROM manager_cases WHERE case_id=?',(case['case_id'],))
    with pytest.raises(HTTPException,match='prepare a new decision'):
        cases.submit_from_host(*args)
    assert rt.details(case['run_id'])['status']=='ready_for_review'
    fresh,_=cases.propose(case['case_id'],case['run_id'],'escalate',note)
    result=cases.submit_from_host(fresh['proposal_id'],case['case_id'],case['run_id'],'escalate',note)
    assert result['submitted'] and result['status']=='escalated'
    from app.server import workspace
    visible=next(a for a in workspace()['alerts'] if a['id']==case['case_id'])
    assert visible['status']=='escalated'
    assert visible['manager_review']['status']=='awaiting_manager'
    with rt.db() as c:
        assert c.execute('SELECT count(*) FROM reviews WHERE run_id=?',(case['run_id'],)).fetchone()[0]==2
