"""Analyst-triggered PDF generation and durable manager delivery; no model decision."""
import hashlib
import json
import re
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo
import certifi
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle,getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,PageBreak,KeepTogether
from .config import settings
from . import runtime as rt


def queue_packet(c,run,review_id,note,actor,at):
    """Caller commits this snapshot atomically with the analyst's escalation."""
    pid=review_id
    evidence=[json.loads(r[0]) for r in c.execute('SELECT payload FROM snapshots WHERE run_id=?',(run['run_id'],))]
    from .evidence_tools import context
    ctx=context(run['case_id'])
    payload={'case_id':run['case_id'],'run_id':run['run_id'],'revision':run['revision'],
             'report':json.loads(run['report_json']),'evidence':evidence,'symbols':ctx['symbols'],
             'accounts':ctx['accounts'],'families':ctx['families'],'cutoff':ctx['cutoff'],
             'analyst_note':note,'analyst':actor,'escalated_at':at,'manager':settings.surveillance_manager_email}
    c.execute('INSERT INTO escalation_packets(id,review_id,run_id,case_id,created_at,payload,recipient) VALUES (?,?,?,?,?,?,?)',
              (pid,review_id,run['run_id'],run['case_id'],at,json.dumps(payload),settings.surveillance_manager_email))
    c.execute('INSERT INTO audit(run_id,at,kind,payload) VALUES (?,?,?,?)',(run['run_id'],at,'escalation_packet_queued',json.dumps({'packet_id':pid,'recipient':settings.surveillance_manager_email,'tool':'generate_escalation_pdf'})))
    return pid


def packet(pid):
    with rt.db() as c:r=c.execute('SELECT * FROM escalation_packets WHERE id=?',(pid,)).fetchone()
    return dict(r) if r else None


def preview_data(case_id):
    with rt.db() as c:r=c.execute('SELECT run_id FROM runs WHERE case_id=? ORDER BY revision DESC LIMIT 1',(case_id,)).fetchone()
    detail=rt.details(r[0]) if r else None
    if not detail or not detail['report']:raise ValueError('No validated draft is available for this case')
    from .evidence_tools import context
    ctx=context(case_id)
    return {'case_id':case_id,'run_id':detail['run_id'],'revision':detail['revision'],'report':detail['report'],
            'evidence':detail['evidence'],'symbols':ctx['symbols'],'accounts':ctx['accounts'],'families':ctx['families'],
            'cutoff':ctx['cutoff'],'analyst':'Workflow preview','escalated_at':rt.now(),'manager':settings.surveillance_manager_email,
            'analyst_note':'Your escalation note will appear here when you choose Escalate. This preview does not record an analyst decision or send an email.',
            'preview':True}


def pdf_bytes(data):
    """Render the validated report, exact citations and analyst note, without a new LLM call."""
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='BriefTitle',fontName='Helvetica-Bold',fontSize=23,leading=28,textColor=colors.HexColor('#173c43'),spaceAfter=14))
    styles.add(ParagraphStyle(name='BriefHeading',fontName='Helvetica-Bold',fontSize=12,leading=16,textColor=colors.HexColor('#176e68'),spaceBefore=14,spaceAfter=7,keepWithNext=True))
    styles.add(ParagraphStyle(name='BriefBody',fontName='Helvetica',fontSize=10,leading=15,spaceAfter=8,splitLongWords=True))
    styles.add(ParagraphStyle(name='BriefSmall',fontName='Helvetica',fontSize=8,leading=11,textColor=colors.HexColor('#52676b'),spaceAfter=5,splitLongWords=True))
    def clean(value):
        return str(value).translate(str.maketrans({'\u2013':'-','\u2014':'-','\u2011':'-','\u2019':"'",'\u2018':"'",'\u201c':'"','\u201d':'"','\u2026':'...','\u00a0':' '}))
    def p(value,style='BriefBody'):return Paragraph(escape(clean(value)).replace('\n','<br/>'),styles[style])
    def et(value):return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).strftime('%b %d, %Y %I:%M %p ET')
    story=[p('TRADE SURVEILLANCE','BriefSmall'),p('Analyst escalation brief','BriefTitle')]
    if data.get('preview'):story.append(p('PREVIEW ONLY - no analyst escalation has been recorded or emailed.','BriefSmall'))
    metadata=[('Case / revision',f"{data['case_id']} / {data['revision']}"),('Securities / accounts',', '.join(data['symbols'])+' / '+', '.join(data['accounts'])),
              ('Alert concerns',', '.join(x.replace('_',' ') for x in data['families'])),('Prepared for',data.get('manager') or 'Surveillance manager'),('Escalated by' if not data.get('preview') else 'Preview prepared by',data['analyst']),('Escalated at' if not data.get('preview') else 'Preview prepared at',et(data['escalated_at'])),('Original evidence cutoff',et(data['cutoff']))]
    table=Table([[p(k,'BriefSmall'),p(v)] for k,v in metadata],colWidths=[142,354],hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#f1f6f5')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),2)]))
    story += [table,p('Example escalation note' if data.get('preview') else 'Analyst decision: Escalate','BriefHeading'),p(data['analyst_note']),p('The agent recommendation below is preserved separately from the analyst decision. Escalation does not establish misconduct.','BriefSmall')]
    report=data['report'];refs={};quotes={}
    def claim(c):
        labels=[]
        for cite in c['citations']:
            eid=cite['evidence_id']
            if eid not in refs:refs[eid]=len(refs)+1
            if cite['quote'] not in quotes.setdefault(eid,[]):quotes[eid].append(cite['quote'])
            if refs[eid] not in labels:labels.append(refs[eid])
        return p(c['text']+' '+''.join(f'[{n}]' for n in labels))
    story += [p('Case summary','BriefHeading'),claim(report['summary']),p('Agent assessment: '+report['assessment'].replace('_',' ')+' | Recommendation: '+report['recommendation'].replace('_',' '),'BriefSmall')]
    for title,key in [('Material findings','observations'),('Alternative explanations','alternative_explanations'),('Remaining evidence gaps','gaps')]:
        story.append(p(title,'BriefHeading'))
        story.extend(claim(c) for c in report[key])
        if not report[key]:story.append(p('No explicit gaps were recorded in this draft. This is not a completeness guarantee.'))
    story.append(p('Questions for supervisory review','BriefHeading'))
    story.extend(p(f'{i}. {q}') for i,q in enumerate(report['reviewer_questions'],1))
    quant=next((e for e in data['evidence'] if e.get('source_type')=='quantitative_analysis'),None)
    if quant:
        from .quantitative import artifact_folder
        meta=quant['artifacts']['chart'];path=artifact_folder(data['run_id'])/meta['filename']
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==meta['sha256']:
            story += [PageBreak(),p('Execution pattern','BriefHeading'),p('Case-scoped trading analysis. Timing and concentration do not establish intent or causal price impact. Numeric validation is separate from visual review.','BriefSmall'),Image(str(path),width=496,height=496*980/1540),p('Chart SHA-256: '+meta['sha256'],'BriefSmall')]
    story += [PageBreak(),p('Source references','BriefTitle'),p('These references preserve exact excerpts cited in the validated draft. They are not a complete archive. Later analyst submissions retain their separate provenance.','BriefSmall')]
    evidence={r['evidence_id']:r for r in data['evidence']}
    for eid,num in refs.items():
        r=evidence.get(eid,{})
        block=[p(f'[{num}] {eid}','BriefHeading'),p('Type: '+r.get('source_type','retrieved source')+' | Status: '+r.get('status','unknown'),'BriefSmall')]
        if r.get('verification'):block.append(p(r['verification'],'BriefSmall'))
        if r.get('limitation'):block.append(p(r['limitation'],'BriefSmall'))
        if r.get('derived_from'):block.append(p('Derived from: '+r['derived_from']+'. Not independent corroboration.','BriefSmall'))
        if r.get('received_at'):block.append(p('Submission received: '+et(r['received_at']),'BriefSmall'))
        block.extend(p('"'+quote+'"') for quote in quotes[eid])
        story.append(KeepTogether(block))
    story += [Spacer(1,12),p('Audit reference: '+data['run_id'],'BriefSmall'),p('Demonstration case using simulated private trading activity. This brief records a supervisory handoff, not a regulatory filing or a finding of misconduct.','BriefSmall')]
    output=BytesIO()
    def footer(canvas,doc):
        canvas.setStrokeColor(colors.HexColor('#d6e2e0'));canvas.line(50,43,546,43)
        canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#52676b'))
        canvas.drawString(50,29,data['case_id']+' | Revision '+str(data['revision'])+' | '+('Preview only' if data.get('preview') else 'Analyst escalation'))
        canvas.drawRightString(546,29,str(doc.page))
    doc=SimpleDocTemplate(output,pagesize=(596,842),leftMargin=50,rightMargin=50,topMargin=46,bottomMargin=60,
                          title=data['case_id']+' - Analyst escalation brief',author='Trade Surveillance')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()


def generate_escalation_pdf(pid):
    with rt.db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM escalation_packets WHERE id=?',(pid,)).fetchone()
        if not row:return None
        row=dict(row)
        if row['pdf_status']!='pending':return row
        c.execute("UPDATE escalation_packets SET pdf_status='generating' WHERE id=?",(pid,))
    rt.audit(row['run_id'],'tool_started',{'tool':'generate_escalation_pdf','reason':'Prepare the analyst-approved escalation for supervisory review.','packet_id':pid})
    try:
        body=pdf_bytes(json.loads(row['payload']))
        if not body.startswith(b'%PDF-') or len(body)>10_000_000:raise ValueError('Invalid escalation PDF')
        digest=hashlib.sha256(body).hexdigest();folder=Path(settings.escalation_artifacts);folder.mkdir(parents=True,exist_ok=True)
        filename=pid+'-'+digest+'.pdf';target=folder/filename
        temp=target.with_suffix('.tmp');temp.write_bytes(body);temp.replace(target)
        with rt.db() as c:c.execute("UPDATE escalation_packets SET pdf_status='ready',filename=?,sha256=?,pdf_error=NULL WHERE id=?",(filename,digest,pid))
        rt.audit(row['run_id'],'tool_completed',{'tool':'generate_escalation_pdf','packet_id':pid,'sha256':digest,'bytes':len(body)})
    except Exception as e:
        with rt.db() as c:c.execute("UPDATE escalation_packets SET pdf_status='failed',pdf_error=? WHERE id=?",(type(e).__name__,pid))
        rt.audit(row['run_id'],'escalation_pdf_failed',{'packet_id':pid,'error_class':type(e).__name__,'analyst_decision_preserved':True})
    return packet(pid)


def verified_pdf(row):
    if row['pdf_status']!='ready' or not row['filename']:raise FileNotFoundError('Escalation PDF is not ready')
    if not re.fullmatch(r'[a-f0-9-]{36}-[a-f0-9]{64}\.pdf',row['filename']):raise ValueError('Invalid stored artifact name')
    body=(Path(settings.escalation_artifacts)/row['filename']).read_bytes()
    if hashlib.sha256(body).hexdigest()!=row['sha256']:raise ValueError('Escalation PDF integrity check failed')
    return body


def process_pending():
    with rt.db() as c:ids=[r[0] for r in c.execute("SELECT id FROM escalation_packets WHERE pdf_status='pending' ORDER BY created_at LIMIT 5")]
    for pid in ids:generate_escalation_pdf(pid)
    sender_ready=bool(settings.smtp_host and (settings.smtp_password or settings.smtp_host in ('localhost','127.0.0.1')))
    with rt.db() as c:
        if settings.surveillance_manager_email:
            c.execute("UPDATE escalation_packets SET recipient=? WHERE recipient='' AND delivery_status IN ('pending','blocked_configuration')",(settings.surveillance_manager_email,))
        if sender_ready:
            c.execute("UPDATE escalation_packets SET delivery_status='pending',delivery_error=NULL WHERE delivery_status='blocked_configuration' AND recipient!=''")
        c.execute("UPDATE escalation_packets SET delivery_status='pending' WHERE delivery_status='failed' AND attempts<3")
        rows=[dict(r) for r in c.execute("SELECT * FROM escalation_packets WHERE pdf_status='ready' AND delivery_status='pending' AND attempts<3 ORDER BY created_at LIMIT 5")]
    for row in rows:
        if not row['recipient'] or not sender_ready:
            with rt.db() as c:c.execute("UPDATE escalation_packets SET delivery_status='blocked_configuration',delivery_error=? WHERE id=?",('Manager address or sender configuration required',row['id']))
            continue
        try:body=verified_pdf(row)
        except (ValueError,OSError) as e:
            with rt.db() as c:c.execute("UPDATE escalation_packets SET pdf_status='failed',pdf_error=? WHERE id=?",(type(e).__name__,row['id']))
            continue
        with rt.db() as c:
            changed=c.execute("UPDATE escalation_packets SET delivery_status='sending',attempts=attempts+1 WHERE id=? AND delivery_status='pending'",(row['id'],)).rowcount
        if not changed:continue
        data=json.loads(row['payload']);message=EmailMessage()
        message['From']=settings.notification_from;message['To']=row['recipient'];message['Subject']='Analyst escalation: '+row['case_id']+' (revision '+str(data['revision'])+')'
        message['Message-ID']='<escalation-'+row['id']+'@trade-surveillance.local>'
        message.set_content(f"An analyst escalated {row['case_id']} for your supervisory review.\n\nAnalyst: {data['analyst']}\nEscalation note: {data['analyst_note']}\n\nThe attached PDF preserves the case summary, agent recommendation, cited evidence and remaining gaps.\n\nOpen case: {settings.app_url}/population.html?case={row['case_id']}&section=manager\n\nDemonstration case; escalation is not a finding of misconduct.")
        message.add_attachment(body,maintype='application',subtype='pdf',filename=row['case_id']+'-escalation.pdf')
        submitting=False;accepted=False
        try:
            smtp_type=smtplib.SMTP_SSL if settings.smtp_port==465 else smtplib.SMTP
            kw={'timeout':15}
            if settings.smtp_port==465:kw['context']=ssl.create_default_context(cafile=certifi.where())
            with smtp_type(settings.smtp_host,settings.smtp_port,**kw) as smtp:
                if settings.smtp_starttls:smtp.starttls(context=ssl.create_default_context(cafile=certifi.where()))
                if settings.smtp_user:smtp.login(settings.smtp_user,settings.smtp_password)
                submitting=True
                refused=smtp.send_message(message)
                if refused:raise smtplib.SMTPRecipientsRefused(refused)
                accepted=True
        except Exception as e:
            if not accepted:
                status='delivery_unknown' if submitting else 'failed'
                if isinstance(e,smtplib.SMTPAuthenticationError):status='blocked_authentication'
                with rt.db() as c:c.execute('UPDATE escalation_packets SET delivery_status=?,delivery_error=? WHERE id=?',(status,type(e).__name__,row['id']))
                rt.audit(row['run_id'],'manager_delivery_issue',{'packet_id':row['id'],'status':status,'error_class':type(e).__name__})
                continue
        with rt.db() as c:c.execute("UPDATE escalation_packets SET delivery_status='sent',sent_at=?,delivery_error=NULL WHERE id=?",(rt.now(),row['id']))
        rt.audit(row['run_id'],'manager_escalation_sent',{'packet_id':row['id'],'recipient':row['recipient'],'transport':'SMTP','pdf_sha256':row['sha256']})


def recover():
    with rt.db() as c:
        c.execute("UPDATE escalation_packets SET pdf_status='pending' WHERE pdf_status='generating'")
        c.execute("UPDATE escalation_packets SET delivery_status='delivery_unknown',delivery_error='Interrupted submission; check Sent before retrying' WHERE delivery_status='sending'")
