"""Explicit local manager decisions and case ownership. No automated dispositions or external referrals."""
import json
from uuid import uuid4
from . import runtime as rt
from .config import settings


def open_review(c,run):
    c.execute('''INSERT INTO manager_cases(case_id,current_run_id,escalation_run_id,owner,status,updated_at)
      VALUES (?,?,?,?,'awaiting_manager',?) ON CONFLICT(case_id) DO UPDATE SET
      current_run_id=excluded.current_run_id,escalation_run_id=excluded.escalation_run_id,owner=excluded.owner,
      status='awaiting_manager',destination='',closure_reason='',updated_at=excluded.updated_at,version=manager_cases.version+1''',
      (run['case_id'],run['run_id'],run['run_id'],settings.surveillance_manager_email or 'Surveillance manager',rt.now()))


def decide(case_id,request):
    body=request.model_dump(mode='json');request_json=json.dumps(body,sort_keys=True)
    with rt.db() as c:
        c.execute('BEGIN IMMEDIATE')
        previous=c.execute('SELECT * FROM manager_actions WHERE id=?',(str(request.request_id),)).fetchone()
        if previous:
            if previous['case_id']!=case_id or previous['request_json']!=request_json:raise ValueError('This request ID was already used for a different action')
            return json.loads(previous['result_json'])|{'duplicate':True}
        state=c.execute('SELECT * FROM manager_cases WHERE case_id=?',(case_id,)).fetchone()
        if not state:raise ValueError('Escalate this case before recording a manager decision')
        latest=c.execute('SELECT * FROM runs WHERE case_id=? ORDER BY revision DESC LIMIT 1',(case_id,)).fetchone()
        if not latest or latest['run_id']!=str(request.run_id) or state['current_run_id']!=str(request.run_id) or state['version']!=request.version:
            raise ValueError('The case changed. Reload it before recording a manager decision')
        if state['status']=='closed':raise ValueError('This case is closed; its decision remains preserved')
        if latest['status'] in ('queued','running') or state['status']=='investigating':raise ValueError('The assigned investigation must finish before another manager decision')
        note=request.note.strip();owner=request.owner.strip()
        if len(note)<5:raise ValueError('Explain the manager decision in at least five characters')
        action=request.action;rid=latest['run_id'];at=rt.now();destination='';closure_reason=''
        if action=='return_for_evidence':
            if not owner:raise ValueError('Name the person or team responsible for providing evidence')
            status='awaiting_evidence'
            c.execute("UPDATE runs SET status='awaiting_evidence',updated_at=? WHERE run_id=?",(at,rid))
        elif action=='assign_investigation':
            if not owner:raise ValueError('Name the investigator responsible for the deeper review')
            status='investigating';rid=str(uuid4())
            c.execute('''INSERT INTO runs(run_id,case_id,revision,status,created_at,updated_at,parent_run,review_request,queue_priority,required_depth)
              VALUES (?,?,?,'queued',?,?,?,?,100,'deep')''',
              (rid,case_id,latest['revision']+1,at,at,latest['run_id'],'Manager assigned deeper investigation to '+owner+': '+note))
            c.execute('INSERT INTO audit(run_id,at,kind,payload) VALUES (?,?,?,?)',(rid,at,'case_received',json.dumps({'case_id':case_id,'parent_run':latest['run_id'],'owner':owner,'required_depth':'deep'})))
        elif action=='approve_closure':
            if state['status'] not in ('awaiting_manager','referred') or not latest['report_json']:raise ValueError('Return a completed analyst assessment to the manager before approving closure')
            if not request.closure_reason:raise ValueError('Select a closure reason')
            closure_reason=request.closure_reason;status='closed';owner=settings.surveillance_manager_email or 'Surveillance manager'
            c.execute("UPDATE runs SET status='closed',updated_at=? WHERE run_id=?",(at,rid))
        else:
            if not request.destination:raise ValueError('Choose Compliance investigations or Legal team')
            destination=request.destination;owner=destination;status='referred'
            c.execute("UPDATE runs SET status='referred',updated_at=? WHERE run_id=?",(at,rid))
        c.execute('''UPDATE manager_cases SET current_run_id=?,status=?,owner=?,destination=?,closure_reason=?,updated_at=?,version=version+1 WHERE case_id=?''',
                  (rid,status,owner,destination,closure_reason,at,case_id))
        result={'case_id':case_id,'run_id':rid,'status':status,'owner':owner,'version':state['version']+1,'duplicate':False}
        c.execute('INSERT INTO manager_actions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                  (str(request.request_id),case_id,latest['run_id'],at,'Local surveillance manager',action,note,owner,destination,closure_reason,request_json,json.dumps(result)))
        payload={'action':action,'note':note,'owner':owner,'destination':destination,'closure_reason':closure_reason,'next_run_id':rid,'actor':'Local surveillance manager'}
        if action=='refer':payload['dispatch']='Local referral recorded; no external email or regulatory filing sent'
        c.execute('INSERT INTO audit(run_id,at,kind,payload) VALUES (?,?,?,?)',(latest['run_id'],at,'manager_decision',json.dumps(payload)))
    return result
