import hashlib
import json
from io import BytesIO
from pathlib import Path
import smtplib
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from app import runtime as rt,escalations
from app.config import settings
from app.server import app

@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'runtime_path',str(tmp_path/'runtime.sqlite3'))
    monkeypatch.setattr(settings,'escalation_artifacts',str(tmp_path/'packets'))
    monkeypatch.setattr(settings,'surveillance_manager_email','manager@example.test')
    monkeypatch.setattr(settings,'smtp_host','localhost');monkeypatch.setattr(settings,'smtp_user','')
    monkeypatch.setattr(settings,'smtp_starttls',False);monkeypatch.setattr(settings,'smtp_port',1025)
    rt.init();run,_=rt.ingest('CASE-AF1D9C5F')
    quote='A recorded instruction refers to valuation; intent remains unresolved.'
    claim={'text':quote,'citations':[{'evidence_id':'E-SOURCE','quote':quote}]}
    report={'assessment':'inconclusive','recommendation':'request_more_evidence','summary':claim,'observations':[claim],
            'alternative_explanations':[claim],'gaps':[claim],'reviewer_questions':['Obtain the signed instruction?']}
    rt.remember(run['run_id'],{'evidence_id':'E-SOURCE','text':quote,'status':'available','source_type':'communication'})
    rt.finish(run['run_id'],report,1,1)
    return run


def escalate(run):
    return TestClient(app).post('/api/cases/'+run['case_id']+'/review',headers={'X-Requested-With':'surveillance-ui'},json={'run_id':run['run_id'],'action':'escalate','note':'Please review the conflicting authority and the valuation-related instruction.'})


class SMTP:
    sent=[]
    def __init__(self,*args,**kwargs):pass
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def send_message(self,message):self.sent.append(message);return {}


def test_escalation_creates_cited_pdf_and_single_manager_email(setup,monkeypatch):
    SMTP.sent=[];monkeypatch.setattr(escalations.smtplib,'SMTP',SMTP)
    res=escalate(setup);assert res.status_code==200
    data=res.json();assert data['pdf_status']=='ready'
    d=rt.details(setup['run_id']);assert d['status']=='escalated' and len(d['reviews'])==1
    assert d['report']['recommendation']=='request_more_evidence'
    row=escalations.packet(data['packet_id'])
    body=escalations.verified_pdf(row);pages=PdfReader(BytesIO(body)).pages;text='\n'.join(p.extract_text() for p in pages)
    assert setup['case_id'] in text and 'Analyst decision: Escalate' in text and 'E-SOURCE' in text
    assert 'Please review the conflicting authority' in text and 'intent remains unresolved' in text
    client=TestClient(app);assert client.get(data['pdf_url']).content==body
    assert client.get(data['pdf_url'].replace(setup['case_id'],'CASE-OTHER')).status_code==404
    escalations.process_pending();escalations.process_pending()
    assert len(SMTP.sent)==1 and SMTP.sent[0]['To']=='manager@example.test'
    attachment=list(SMTP.sent[0].iter_attachments())[0]
    assert attachment.get_content_type()=='application/pdf' and attachment.get_payload(decode=True)==body
    assert escalations.packet(row['id'])['delivery_status']=='sent'
    assert escalate(setup).status_code==409
    with rt.db() as c:assert c.execute('select count(*) from escalation_packets').fetchone()[0]==1


def test_pdf_failure_preserves_decision_and_can_retry_without_new_review(setup,monkeypatch):
    original=escalations.pdf_bytes
    monkeypatch.setattr(escalations,'pdf_bytes',lambda _:(_ for _ in ()).throw(OSError('test')))
    res=escalate(setup);data=res.json()
    assert data['pdf_status']=='failed' and rt.details(setup['run_id'])['status']=='escalated'
    monkeypatch.setattr(escalations,'pdf_bytes',original)
    res=TestClient(app).post('/api/cases/'+setup['case_id']+'/escalations/'+data['packet_id']+'/retry-pdf',headers={'X-Requested-With':'surveillance-ui'})
    assert res.json()['pdf_status']=='ready' and len(rt.details(setup['run_id'])['reviews'])==1


def test_tampered_pdf_is_never_downloaded_or_emailed(setup,monkeypatch):
    SMTP.sent=[];monkeypatch.setattr(escalations.smtplib,'SMTP',SMTP)
    data=escalate(setup).json();row=escalations.packet(data['packet_id'])
    (Path(settings.escalation_artifacts)/row['filename']).write_bytes(b'tampered')
    assert TestClient(app).get(data['pdf_url']).status_code==409
    escalations.process_pending();assert not SMTP.sent
    assert escalations.packet(row['id'])['pdf_status']=='failed'


def test_missing_manager_blocks_email_without_fallback_to_analyst(setup,monkeypatch):
    monkeypatch.setattr(settings,'surveillance_manager_email','')
    monkeypatch.setattr(settings,'analyst_email','analyst@example.test')
    row=escalate(setup).json();escalations.process_pending()
    packet=escalations.packet(row['packet_id']);assert packet['recipient']=='' and packet['delivery_status']=='blocked_configuration'


def test_ambiguous_submission_is_not_retried(setup,monkeypatch):
    class Uncertain(SMTP):
        attempts=0
        def send_message(self,message):Uncertain.attempts+=1;raise smtplib.SMTPServerDisconnected('test')
    monkeypatch.setattr(escalations.smtplib,'SMTP',Uncertain)
    data=escalate(setup).json();escalations.process_pending();escalations.process_pending()
    assert Uncertain.attempts==1 and escalations.packet(data['packet_id'])['delivery_status']=='delivery_unknown'


def test_restart_does_not_resend_interrupted_submission(setup):
    data=escalate(setup).json()
    with rt.db() as c:c.execute("update escalation_packets set delivery_status='sending' where id=?",(data['packet_id'],))
    escalations.recover();assert escalations.packet(data['packet_id'])['delivery_status']=='delivery_unknown'


def test_packet_snapshot_is_immutable(setup):
    import sqlite3
    data=escalate(setup).json()
    with pytest.raises(sqlite3.IntegrityError):
        with rt.db() as c:c.execute("update escalation_packets set payload='{}' where id=?",(data['packet_id'],))


def test_preview_never_records_escalation_or_sends_email(setup):
    res=TestClient(app).get('/api/cases/'+setup['case_id']+'/escalation-preview.pdf')
    assert res.status_code==200
    text='\n'.join(p.extract_text() for p in PdfReader(BytesIO(res.content)).pages)
    assert 'PREVIEW ONLY' in text and 'no analyst escalation has been recorded or emailed' in text
    assert rt.details(setup['run_id'])['status']=='ready_for_review'
    with rt.db() as c:
        assert c.execute('select count(*) from escalation_packets').fetchone()[0]==0
        assert c.execute('select count(*) from reviews').fetchone()[0]==0


def test_server_acceptance_is_not_resent_when_quit_fails(setup,monkeypatch):
    class QuitFailure(SMTP):
        sent=[]
        def __exit__(self,*args):raise smtplib.SMTPServerDisconnected('quit failed after acceptance')
    monkeypatch.setattr(escalations.smtplib,'SMTP',QuitFailure)
    data=escalate(setup).json();escalations.process_pending();escalations.process_pending()
    assert len(QuitFailure.sent)==1 and escalations.packet(data['packet_id'])['delivery_status']=='sent'


def test_missing_sender_never_attempts_manager_submission(setup,monkeypatch):
    monkeypatch.setattr(settings,'smtp_host','');SMTP.sent=[]
    monkeypatch.setattr(escalations.smtplib,'SMTP',SMTP)
    data=escalate(setup).json();escalations.process_pending()
    assert not SMTP.sent and escalations.packet(data['packet_id'])['delivery_status']=='blocked_configuration'
