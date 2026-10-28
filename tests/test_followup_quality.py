import json
import sqlite3
from types import SimpleNamespace as NS
import pytest
from fastapi.testclient import TestClient
from app import runtime as rt
from app.agent import BASE,EXTRA,definitions
from app.config import settings
from app.evidence_tools import EvidenceTools
from app.evaluation import evaluate
from app.server import app

@pytest.fixture
def runtime(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'runtime_path',str(tmp_path/'runtime.sqlite3'))
    rt.init()
    run,_=rt.ingest('CASE-9732738F')
    # An isolated fixture represents a completed initial investigation, not a live analyst decision.
    claim={'text':'Authority remains unresolved.','citations':[{'evidence_id':'E','quote':'Missing instruction'}]}
    report={'assessment':'inconclusive','recommendation':'request_more_evidence','summary':claim,'observations':[claim],
            'alternative_explanations':[claim],'gaps':[claim],'reviewer_questions':['Obtain authority?']}
    rt.remember(run['run_id'],{'evidence_id':'E','text':'Missing instruction','status':'unavailable'})
    rt.finish(run['run_id'],report,1,1)
    return run


def submit(run,case=None,**changes):
    body={'run_id':run['run_id'],'action':'request_more_evidence','note':'Check the attached source against the linked order.',
          'evidence':{'title':'Instruction extract','reference':'DEMO-MANDATE-1','content':'Instruction for the linked AMZN order. This fixture is an unverified submitted source.'}}
    body.update(changes)
    return TestClient(app).post('/api/cases/'+(case or run['case_id'])+'/review',headers={'X-Requested-With':'surveillance-ui'},json=body)


def test_followup_document_is_separate_from_note_and_cannot_leak_backwards(runtime):
    before=rt.details(runtime['run_id'])
    res=submit(runtime);assert res.status_code==200
    rid=res.json()['run_id'];after=rt.details(runtime['run_id'])
    assert before['report']==after['report'] and before['evidence']==after['evidence']
    assert rt.submitted_sources(runtime['run_id'])==[]
    rows=rt.submitted_sources(rid);assert len(rows)==1 and rows[0]['source_type']=='submitted_document'
    assert 'not independently verified' in rows[0]['verification']
    assert 'Check the attached' not in rows[0]['text']
    tool=EvidenceTools(rid,runtime['case_id'],None)
    assert tool.call('read_submitted_evidence','Ignore this narrative scope override')[0]==rows[0]
    assert rows[0]['evidence_id'] in rt.recalled(rid)
    assert rows[0]['evidence_id'] not in rt.recalled(runtime['run_id'])
    rt.update(rid,status='manual_review')
    child=submit(rt.details(rid),evidence=None).json()['run_id']
    assert rt.submitted_sources(child)==rows
    other,_=rt.ingest('CASE-E3C68AD0')
    assert rt.submitted_sources(other['run_id'])==[]
    with pytest.raises(sqlite3.IntegrityError):
        with rt.db() as c:c.execute('UPDATE submitted_evidence SET payload=?',('{}',))


def test_new_source_requires_reinvestigation_and_rejects_invalid_excerpt(runtime):
    assert submit(runtime,action='escalate').status_code==422
    assert submit(runtime,evidence={'title':'x','reference':'y','content':'short'}).status_code==422
    assert rt.details(runtime['run_id'])['status']=='ready_for_review'


def test_unavailable_communications_are_returned_without_embeddings(runtime,monkeypatch):
    tool=EvidenceTools(runtime['run_id'],runtime['case_id'],None)
    rows=[{'evidence_id':'MISSING-CALL','kind':'communication','status':'unavailable','content':'The benchmark instruction archive is unavailable.',
           'metadata_json':'{}','event_at':'2025-05-01','available_at':'2025-05-01','source_record_id':'ARCHIVE-1'}]
    monkeypatch.setattr(tool,'records',lambda _:rows)
    result=tool.communications('closing benchmark')
    assert result[0]['evidence_id']=='MISSING-CALL' and result[0]['status']=='unavailable'
    assert 'MISSING-CALL' in rt.recalled(runtime['run_id'])


def test_denied_communications_remain_redacted_without_embeddings(runtime,monkeypatch):
    tool=EvidenceTools(runtime['run_id'],runtime['case_id'],None)
    monkeypatch.setattr(tool,'records',lambda _:[{'evidence_id':'DENIED','kind':'communication','status':'access_denied','content':'SECRET',
        'metadata_json':'{}','event_at':'2025-05-01','available_at':'2025-05-01','source_record_id':'ARCHIVE-2'}])
    assert 'SECRET' not in json.dumps(tool.communications('anything'))


def test_original_label_agreement_excludes_later_submissions(runtime):
    r=evaluate();row=next(x for x in r['rows'] if x['case_id']==runtime['case_id'])
    assert row['route_agreement'] is False and row['expected_assessment']=='concerning'
    followup=submit(runtime).json()['run_id']
    rt.finish(followup,rt.details(runtime['run_id'])['report'],1,1)
    r=evaluate();row=next(x for x in r['rows'] if x['case_id']==runtime['case_id'])
    assert row['route_agreement'] is None and row['followup_evidence']
    assert 'later_evidence_not_in_original_benchmark' in row['diagnostic_flags']


def test_coordinated_cases_require_communications_and_followup_tool_is_gated():
    assert 'search_communications' in EXTRA['coordinated_trading']
    names=lambda **kw:{d['name'] for d in definitions(**kw)}
    assert 'read_submitted_evidence' not in names(done=set(),mandatory=BASE)
    assert 'read_submitted_evidence' in names(done=BASE,initial=True,mandatory=BASE|{'read_submitted_evidence'})


def test_support_reviewer_must_identify_actual_claim(runtime):
    from app.agent import check_grounding_verdict
    from app.models import Report,GroundingVerdict
    report=Report.model_validate(rt.details(runtime['run_id'])['report'])
    with pytest.raises(RuntimeError,match='exact draft claim'):
        check_grounding_verdict(report,GroundingVerdict(supported=False,issues=['Unsupported authority'],flagged_claims=['Authority is proven.']))
    check_grounding_verdict(report,GroundingVerdict(supported=False,issues=['Review this actual claim'],flagged_claims=[report.summary.text]))
    with pytest.raises(RuntimeError,match='contradictory'):
        check_grounding_verdict(report,GroundingVerdict(supported=True,issues=['Yet unsupported'],flagged_claims=[]))


def test_demo_verification_cannot_record_a_disposition(runtime):
    assert submit(runtime,action='mark_reviewed',evidence=None,demo_verification=True).status_code==422
    result=submit(runtime,demo_verification=True)
    assert result.status_code==200
    assert rt.details(runtime['run_id'])['reviews'][0]['actor']=='Demo workflow verification'
