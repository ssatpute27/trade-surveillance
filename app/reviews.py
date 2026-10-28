"""Shared analyst workflow for dashboard and confirmed ChatGPT actions."""
import json
from uuid import uuid4
from fastapi import HTTPException
from . import runtime as rt, manager, escalations
from .models import Action

def record_review(case_id: str, action: Action, *, origin='app', expected_run_id=None, proposal_id=None, confirmation_token=None, host_approved=False):
    if host_approved and (origin!='chatgpt' or not proposal_id):raise HTTPException(403,'Native approval requires a staged ChatGPT decision')
    if action.evidence and action.action!='request_more_evidence':raise HTTPException(422,'Submit supporting evidence with a request for a new investigation')
    if action.demo_verification and action.action!='request_more_evidence':raise HTTPException(422,'Demo verification can request investigation, not record a disposition')
    actor='Demo workflow verification' if action.demo_verification else ('ChatGPT analyst' if origin=='chatgpt' else 'Local compliance analyst')
    with rt.db() as c:
        c.execute('BEGIN IMMEDIATE')
        r=c.execute('SELECT * FROM runs WHERE case_id=? ORDER BY revision DESC LIMIT 1',(case_id,)).fetchone()
        if not r:raise HTTPException(409,'No investigation exists')
        if proposal_id:
            from .chatgpt_cases import consume_proposal
            previous=consume_proposal(c,proposal_id,confirmation_token,case_id,r,action,host_approved=host_approved)
            if previous is not None:return previous
        if expected_run_id and r['run_id']!=expected_run_id:raise HTTPException(409,'Case revision changed; retrieve and review the latest case')
        if r['status'] not in ('ready_for_review','manual_review','awaiting_evidence'):raise HTTPException(409,'This investigation is not awaiting a review action')
        managed=c.execute('SELECT * FROM manager_cases WHERE case_id=?',(case_id,)).fetchone()
        if managed and action.action=='mark_reviewed':raise HTTPException(409,'Manager closure approval is required. Return the assessment to the manager.')
        if r['status']=='awaiting_evidence' and action.action!='request_more_evidence':raise HTTPException(409,'Submit the requested evidence before continuing review')
        if managed and action.action=='request_more_evidence' and not action.evidence:raise HTTPException(422,'Add a supporting document. This case waits for evidence rather than repeating the same investigation.')
        if action.action!='request_more_evidence' and not r['report_json']:raise HTTPException(409,'A draft is required before disposition')
        review_id=str(uuid4());review_at=rt.now()
        c.execute('INSERT INTO reviews VALUES (?,?,?,?,?,?)',(review_id,r['run_id'],review_at,actor,action.action,action.note))
        status={'escalate':'escalated','mark_reviewed':'reviewed','request_more_evidence':'more_evidence_requested'}[action.action]
        c.execute('UPDATE runs SET status=?,updated_at=? WHERE run_id=?',(status,rt.now(),r['run_id']))
        c.execute('INSERT INTO audit(run_id,at,kind,payload) VALUES (?,?,?,?)',(r['run_id'],rt.now(),'demo_followup_request' if action.demo_verification else 'human_review',json.dumps({'actor':actor,'origin':origin,'action':action.action,'note':action.note})))
        if action.action=='escalate':
            manager.open_review(c,dict(r))
            packet_id=escalations.queue_packet(c,dict(r),review_id,action.note,actor,review_at)
        if action.action=='request_more_evidence':
            rid=str(uuid4());at=rt.now()
            next_request=action.note
            if managed:
                prior_request=c.execute("SELECT note FROM manager_actions WHERE case_id=? AND action='return_for_evidence' ORDER BY at DESC LIMIT 1",(case_id,)).fetchone()
                if prior_request:next_request='Manager evidence request: '+prior_request[0]+'\nAnalyst response: '+action.note
            c.execute('INSERT INTO runs(run_id,case_id,revision,status,created_at,updated_at,parent_run,review_request) VALUES (?,?,?,?,?,?,?,?)',
                      (rid,case_id,r['revision']+1,'queued',at,at,r['run_id'],next_request))
            if managed:c.execute("UPDATE manager_cases SET current_run_id=?,status='investigating',owner='Local compliance analyst',updated_at=?,version=version+1 WHERE case_id=?",(rid,at,case_id))
            c.execute('INSERT INTO audit(run_id,at,kind,payload) VALUES (?,?,?,?)',(rid,at,'case_received',json.dumps({'case_id':case_id,'revision':r['revision']+1,'parent_run':r['run_id']})))
            if action.evidence:
                import hashlib
                submitted=action.evidence.model_dump()
                eid='SUBMITTED-'+str(uuid4())
                text=f"Analyst-submitted source: {submitted['title']}\nReference: {submitted['reference']}\n{submitted['content']}"
                payload={'evidence_id':eid,'source_type':'submitted_document','status':'available','text':text,
                         'citation_options':text.splitlines(),'received_at':at,'submitted_by':actor,
                         'sha256':hashlib.sha256(text.encode()).hexdigest(),'origin':'analyst_submission',
                         'verification':'Submitted text; authenticity and its claims are not independently verified. Received after the original case cutoff; available only to this follow-up and descendants.'}
                c.execute('INSERT INTO submitted_evidence VALUES (?,?,?,?,?)',(eid,rid,case_id,at,json.dumps(payload)))
                c.execute('INSERT INTO audit(run_id,at,kind,payload) VALUES (?,?,?,?)',(rid,at,'evidence_submitted',json.dumps({'evidence_id':eid,'title':submitted['title'],'reference':submitted['reference'],'sha256':payload['sha256'],'received_at':at})))
        result={'status':'queued','run_id':rid,'prior_revision_preserved':True} if action.action=='request_more_evidence' else {'status':status}
        if action.action=='escalate':result.update(packet_id=packet_id,pdf_url=f'/api/cases/{case_id}/escalations/{packet_id}.pdf',pdf_status='pending',delivery_status='pending')
        if proposal_id:c.execute("UPDATE chatgpt_proposals SET status='committed',result_json=? WHERE id=?",(json.dumps(result),proposal_id))
    if action.action=='request_more_evidence':
        return result
    if action.action=='escalate':
        pdf=escalations.generate_escalation_pdf(packet_id)
        return {'status':status,'packet_id':packet_id,'pdf_status':pdf['pdf_status'],
                'pdf_url':f'/api/cases/{case_id}/escalations/{packet_id}.pdf','delivery_status':pdf['delivery_status']}
    return {'status':status}

