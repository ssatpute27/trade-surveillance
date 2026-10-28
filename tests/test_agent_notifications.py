import smtplib
import ssl
import pytest
from fastapi.testclient import TestClient
from app import runtime as rt, notifications
from app.config import settings
from app.server import app

@pytest.fixture
def local_runtime(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'runtime_path',str(tmp_path/'runtime.sqlite3'))
    monkeypatch.setattr(settings,'smtp_host','smtp.gmail.com')
    monkeypatch.setattr(settings,'smtp_user','sender@example.com')
    monkeypatch.setattr(settings,'analyst_email','recipient@example.com')
    monkeypatch.setattr(settings,'smtp_password','')
    monkeypatch.setattr(settings,'smtp_starttls',True)
    rt.init()
    with rt.db() as c:
        c.execute("INSERT INTO notifications (id,run_id,created_at,status,recipient,subject,body,attempts) VALUES ('n','r',?,'pending','recipient@example.com','Review ready','Synthetic draft',0)",(rt.now(),))
    return tmp_path

def test_missing_auth_holds_message(local_runtime):
    notifications.deliver_pending()
    with rt.db() as c:r=c.execute('SELECT * FROM notifications').fetchone()
    assert r['status']=='blocked_configuration' and r['attempts']==0

def test_auth_failure_waits_for_configuration_change(local_runtime,monkeypatch):
    monkeypatch.setattr(settings,'smtp_password','x'*16)
    class BadSMTP:
        def __init__(self,*args,**kwargs):raise smtplib.SMTPAuthenticationError(535,b'Invalid credentials')
    monkeypatch.setattr(smtplib,'SMTP',BadSMTP)
    notifications.deliver_pending();notifications.deliver_pending()
    with rt.db() as c:r=c.execute('SELECT * FROM notifications').fetchone()
    assert r['status']=='blocked_configuration' and r['attempts']==1

def test_accepted_email_is_not_sent_twice(local_runtime,monkeypatch):
    monkeypatch.setattr(settings,'smtp_password','x'*16)
    sent=[]
    class SMTP:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def starttls(self,**kwargs):
            context=kwargs['context']
            assert context.verify_mode==ssl.CERT_REQUIRED
            assert context.check_hostname
            assert context.cert_store_stats()['x509_ca']>0
        def login(self,*args):pass
        def send_message(self,message):sent.append(message);return {}
    monkeypatch.setattr(smtplib,'SMTP',SMTP)
    notifications.deliver_pending();notifications.deliver_pending()
    assert len(sent)==1
    with rt.db() as c:assert c.execute('SELECT status FROM notifications').fetchone()[0]=='sent'

def test_validation_does_not_echo_credentials():
    client=TestClient(app)
    secret='credential-that-must-not-be-echoed'
    response=client.post('/api/notifications/gmail',headers={'X-Requested-With':'surveillance-ui'},json={'app_password':secret})
    assert response.status_code==422
    assert secret not in response.text

def test_mutation_requires_workspace_header():
    response=TestClient(app).post('/api/notifications/gmail',json={'app_password':'x'*16})
    assert response.status_code==403
