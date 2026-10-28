import smtplib
import ssl
import certifi
from email.message import EmailMessage
from .config import settings
from . import runtime as rt


def configured():
    return bool(settings.smtp_host and settings.analyst_email and (settings.smtp_password or settings.smtp_host in ('localhost','127.0.0.1')))


def deliver_pending():
    if not configured():
        with rt.db() as c:c.execute("UPDATE notifications SET status='blocked_configuration',error='Sender authentication is required' WHERE status='pending'")
        return
    with rt.db() as c:
        c.execute("UPDATE notifications SET status='pending',error=NULL WHERE status='blocked_configuration' AND error='Sender authentication is required'")
        c.execute("UPDATE notifications SET status='pending' WHERE status='failed' AND attempts<3")
        rows=[dict(r) for r in c.execute("SELECT * FROM notifications WHERE status='pending' AND attempts<3 ORDER BY created_at LIMIT 10")]
    for n in rows:
        with rt.db() as c:
            c.execute('BEGIN IMMEDIATE')
            changed=c.execute("UPDATE notifications SET status='sending',attempts=attempts+1 WHERE id=? AND status='pending'",(n['id'],)).rowcount
        if not changed:continue
        message=EmailMessage()
        message['From']=settings.notification_from;message['To']=n['recipient'];message['Subject']=n['subject']
        message['Message-ID']=f'<{n["id"]}@trade-surveillance.local>'
        message.set_content(n['body'])
        submitting=False
        try:
            smtp_type=smtplib.SMTP_SSL if settings.smtp_port==465 else smtplib.SMTP
            kw={'timeout':15}
            if smtp_type==smtplib.SMTP_SSL:kw['context']=ssl.create_default_context(cafile=certifi.where())
            with smtp_type(settings.smtp_host,settings.smtp_port,**kw) as smtp:
                if settings.smtp_starttls:smtp.starttls(context=ssl.create_default_context(cafile=certifi.where()))
                if settings.smtp_user:smtp.login(settings.smtp_user,settings.smtp_password)
                submitting=True
                refused=smtp.send_message(message)
                if refused:raise smtplib.SMTPRecipientsRefused(refused)
            with rt.db() as c:c.execute("UPDATE notifications SET status='sent',sent_at=?,error=NULL WHERE id=?",(rt.now(),n['id']))
            rt.audit(n['run_id'],'email_sent',{'notification_id':n['id'],'transport':'SMTP','recipient':n['recipient']})
        except Exception as e:
            status='delivery_unknown' if submitting else 'failed'
            if isinstance(e,smtplib.SMTPAuthenticationError):status='blocked_configuration'
            with rt.db() as c:c.execute('UPDATE notifications SET status=?,error=? WHERE id=?',(status,type(e).__name__,n['id']))
            rt.audit(n['run_id'],'email_delivery_issue',{'notification_id':n['id'],'status':status,'error_class':type(e).__name__})


def recover():
    with rt.db() as c:c.execute("UPDATE notifications SET status='delivery_unknown',error='Delivery was interrupted; check the sent mailbox before retrying' WHERE status='sending'")
