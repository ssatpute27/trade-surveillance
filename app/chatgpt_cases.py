"""Case-scoped ChatGPT access to the existing workflow, with UI-confirmed decisions."""
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import HTTPException
from . import runtime as rt
from .config import ROOT, settings
from .evidence_tools import context, EvidenceTools, placeholders
from .models import Action


def init():
    with rt.db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS chatgpt_proposals(
          id TEXT PRIMARY KEY,case_id TEXT NOT NULL,run_id TEXT NOT NULL,action_json TEXT NOT NULL,
          token_hash TEXT NOT NULL,expires_at TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',result_json TEXT)''')


def resolve(case_id, revision=None):
    ctx=context(case_id)
    with rt.db() as c:
        if revision is None:r=c.execute('SELECT * FROM runs WHERE case_id=? ORDER BY revision DESC LIMIT 1',(case_id,)).fetchone()
        else:r=c.execute('SELECT * FROM runs WHERE case_id=? AND revision=?',(case_id,revision)).fetchone()
    if not r:raise ValueError('No investigation exists for this case revision')
    return ctx,dict(r)


def permitted(record):
    if record.get('status')=='access_denied':
        return {'evidence_id':record.get('evidence_id'),'source_type':record.get('source_type',record.get('kind')),
                'status':'access_denied','text':'Access denied. Request authorized access; source contents are not disclosed.'}
    from .demo_identities import display_identities
    return display_identities(record)


def page(rows,offset,limit):
    if offset<0 or not 1<=limit<=100:raise ValueError('Use offset >= 0 and limit between 1 and 100')
    from .demo_identities import display_identities
    return {'items':display_identities(rows[offset:offset+limit]),'total':len(rows),'next_offset':offset+limit if offset+limit<len(rows) else None}


def find_cases(query='',status='',offset=0,limit=25):
    from scripts.group_cases import grouped_alerts
    with rt.source() as c:
        groups=grouped_alerts(c)
        orders={r['case_id']:[dict(o) for o in c.execute('''SELECT DISTINCT o.order_id,o.security_id,o.account_id,t.name trader
          FROM case_alerts ca JOIN alert_orders ao USING(alert_id) JOIN orders o USING(order_id)
          JOIN traders t USING(trader_id) WHERE ca.case_id=?''',(r['case_id'],))] for r in groups}
    with rt.db() as c:
        latest={r['case_id']:dict(r) for r in c.execute('''SELECT r.case_id,r.run_id,r.status,r.revision,r.report_json FROM runs r
          JOIN (SELECT case_id,max(revision) revision FROM runs GROUP BY case_id) l USING(case_id,revision)''')}
    rows=[]
    for g in groups:
        cid=g['case_id'];run=latest.get(cid,{});report=json.loads(run['report_json']) if run.get('report_json') else {}
        item={'case_id':cid,'orders':orders[cid],'families':sorted({a['rule'] for a in g['alerts']}),
              'status':run.get('status','awaiting_investigation'),'revision':run.get('revision'),'run_id':run.get('run_id'),
              'assessment':report.get('assessment'),'recommendation':report.get('recommendation')}
        if status and status!=item['status']:continue
        if query and query.casefold() not in json.dumps(item).casefold():continue
        rows.append(item)
    return page(rows,offset,limit)


def case_overview(case_id,revision=None):
    ctx,run=resolve(case_id,revision);detail=rt.details(run['run_id'])
    sources=[permitted(x) for x in detail.pop('evidence')]
    events=detail.pop('events')
    # Provisional draft candidates are separate from the final validated assessment.
    detail.pop('tokens',None);detail.pop('elapsed',None)
    from .investigation_extensions import recording_previews
    detail['recordings']=recording_previews(ctx,run['run_id'])
    from .image_evidence import previews
    detail['images']=previews(ctx,run['run_id'])
    detail['context']=ctx
    report=detail.get('report') or {}
    claims=[report.get('summary',{})]+report.get('observations',[])+report.get('alternative_explanations',[])+report.get('gaps',[])
    cited={citation['evidence_id'] for claim in claims for citation in claim.get('citations',[])}
    detail['cited_sources']=[r for r in sources if r.get('evidence_id') in cited]
    detail['evidence_index']=[{k:r.get(k) for k in ('evidence_id','source_type','status','event_at','origin')} for r in sources]
    detail['assessment_journey']=[e for e in events if e['kind'] in ('initial_assessment','depth_changed','validation','manual_review_required','case_received','evidence_submitted','human_review')]
    detail['app_url']=settings.app_url+'/population.html?case='+case_id
    detail['available_sections']=['trades','sources','communications','policies','history','activity','analysis','recordings']
    return detail


def read_section(case_id,section,revision=None,offset=0,limit=50):
    ctx,run=resolve(case_id,revision);rid=run['run_id']
    records=[permitted(r) for r in rt.recalled(rid).values()]
    if section=='trades':
        with rt.source() as c:
            marks=placeholders(ctx['order_ids'])
            orders=[dict(r) for r in c.execute(f'SELECT * FROM orders WHERE order_id IN ({marks})',ctx['order_ids'])]
            fills=[dict(r) for r in c.execute(f'''SELECT * FROM fills WHERE order_id IN ({marks})
              AND executed_at<=? AND ingested_at<=? ORDER BY executed_at,fill_id''',(*ctx['order_ids'],ctx['cutoff'],ctx['cutoff']))]
        return {'orders':orders,'fills':page(fills,offset,limit),'cutoff':ctx['cutoff'],'money_unit':'USD cents'}
    if section in ('sources','communications'):
        # Reuse the existing cutoff/account/availability and access controls, without a model call or snapshot mutation.
        reader=EvidenceTools(rid,case_id,None)
        raw=reader.records(['communication'] if section=='communications' else ['communication','mandate','mandate_index','authorization_record','public_news','strategy_log','archive_coverage','access','relationships','customer_order_access','crossing_records'])
        for r in raw:
            records.append(permitted({'evidence_id':r['evidence_id'],'source_type':r['kind'],'status':r['status'],
              'text':r['content'],'event_at':r['event_at'],'available_at':r['available_at'],'ingested_at':r['ingested_at'],
              'metadata':json.loads(r['metadata_json']),'source_record_id':r['source_record_id'],'included_in_assessment':r['evidence_id'] in rt.recalled(rid)}))
        records.extend(rt.submitted_sources(rid))
        unique={r['evidence_id']:r for r in records}
        records=list(unique.values())
        if section=='communications':records=[r for r in records if r.get('source_type') in ('communication','call_transcript')]
        if section=='communications':records.sort(key=lambda r:(bool(r.get('metadata',{}).get('order_ids')),r.get('event_at','')),reverse=True)
    elif section=='analysis':records=[r for r in records if r.get('source_type')=='quantitative_analysis']
    elif section=='recordings':
        from .investigation_extensions import recordings
        return {'recordings':[{k:v for k,v in r.items() if k not in ('path','audio_path','filename')} for r in recordings(ctx)],
          'transcripts':[r for r in records if r.get('source_type')=='call_transcript'],
          'playback_note':'Local audio playback is available in the app; transcripts retain recording provenance.'}
    elif section=='policies':
        records=[{'filename':p.name,'text':p.read_text(),'source_type':'policy'} for p in sorted((ROOT/'docs/surveillance_policies').glob('POL-*.md'))]
    elif section=='activity':
        events=rt.details(rid)['events']
        # Expose traceable workflow steps, not provisional draft text or model API internals.
        records=[]
        for event in events:
            if event['kind'] in ('model_response','draft_candidate'):continue
            payload=event['payload']
            if event['kind'] in ('tool_started','tool_completed'):
                payload={k:v for k,v in payload.items() if k in ('tool','evidence_ids')}
            records.append({'seq':event['seq'],'at':event['at'],'kind':event['kind'],'payload':payload})
    elif section=='history':
        with rt.db() as c:
            rows=[dict(r) for r in c.execute('SELECT run_id,revision,status,parent_run,review_request,created_at,updated_at FROM runs WHERE case_id=? ORDER BY revision',(case_id,))]
        return {'revisions':rows,'reviews':rt.details(rid)['reviews'],'manager_actions':rt.details(rid)['manager_actions'],
                'escalation_packets':rt.details(rid)['escalation_packets']}
    else:raise ValueError('Unknown case section')
    return page(records,offset,limit)


def read_source(case_id,evidence_id,revision=None):
    ctx,run=resolve(case_id,revision)
    record=rt.recalled(run['run_id']).get(evidence_id)
    if not record:record=next((r for r in rt.submitted_sources(run['run_id']) if r['evidence_id']==evidence_id),None)
    if record:return permitted(record)
    reader=EvidenceTools(run['run_id'],case_id,None)
    raw=next((r for r in reader.records(['communication','mandate','mandate_index','authorization_record','public_news','strategy_log','archive_coverage','access','relationships','customer_order_access','crossing_records']) if r['evidence_id']==evidence_id),None)
    if not raw:raise ValueError('Source not available in this case revision')
    return permitted({'evidence_id':raw['evidence_id'],'source_type':raw['kind'],'status':raw['status'],'text':raw['content'],
                      'event_at':raw['event_at'],'available_at':raw['available_at'],'ingested_at':raw['ingested_at'],
                      'metadata':json.loads(raw['metadata_json']),'source_record_id':raw['source_record_id']})


def propose(case_id,run_id,action,note,evidence=None):
    init();_,run=resolve(case_id)
    if run['run_id']!=run_id:raise ValueError('Case revision changed; retrieve the latest case')
    if run['status'] not in ('ready_for_review','manual_review','awaiting_evidence'):raise ValueError('Case is not awaiting analyst review')
    a=Action(action=action,note=note,evidence=evidence)
    if a.evidence and action!='request_more_evidence':raise ValueError('Evidence must accompany a follow-up request')
    with rt.db() as c:managed=c.execute('SELECT 1 FROM manager_cases WHERE case_id=?',(case_id,)).fetchone()
    if managed and action=='mark_reviewed':raise ValueError('Manager approval is required for closure')
    if managed and action=='request_more_evidence' and not a.evidence:raise ValueError('Provide the requested supporting document')
    if run['status']=='awaiting_evidence' and action!='request_more_evidence':raise ValueError('Submit the requested evidence before review')
    if action!='request_more_evidence' and not run['report_json']:raise ValueError('No assessment is available for disposition')
    token=secrets.token_urlsafe(32);pid=str(uuid4());expires=(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat()
    with rt.db() as c:c.execute('INSERT INTO chatgpt_proposals(id,case_id,run_id,action_json,token_hash,expires_at) VALUES (?,?,?,?,?,?)',
      (pid,case_id,run_id,a.model_dump_json(),hashlib.sha256(token.encode()).hexdigest(),expires))
    effect={'escalate':'Create the escalation PDF and queue email delivery to the surveillance manager.',
      'mark_reviewed':'Record the analyst decision and move this case to completed cases.',
      'request_more_evidence':'Submit the supplied evidence, if present, and queue one follow-up investigation.'}[action]
    public={'proposal_id':pid,'case_id':case_id,'run_id':run_id,'revision':run['revision'],'action':action,'note':note,
      'app_url':settings.app_url+'/population.html?case='+case_id,
      'confirmation_method':'native_tool_approval',
      'confirmation_instructions':'To record an explicitly authorized decision, call submit_analyst_decision with this exact proposal. ChatGPT native write-tool approval confirms the action; no embedded card is required. Preparation alone makes no case change.',
      'app_instructions':'Open app_url, enter your review note, then select '+{'escalate':'Escalate','mark_reviewed':'Approve / mark reviewed','request_more_evidence':'Request more evidence'}[action]+'.',
      'evidence':a.evidence.model_dump() if a.evidence else None,'expires_at':expires,'effect':effect,
      'recipient':settings.surveillance_manager_email if action=='escalate' else None,'status':'awaiting_human_confirmation'}
    return public,token


def consume_proposal(c,pid,token,case_id,run,action,*,host_approved=False):
    row=c.execute('SELECT * FROM chatgpt_proposals WHERE id=?',(pid,)).fetchone()
    if not row or not (host_approved or isinstance(token,str) and hmac.compare_digest(row['token_hash'],hashlib.sha256(token.encode()).hexdigest())):
        raise HTTPException(403,'Invalid confirmation')
    if row['case_id']!=case_id or json.loads(row['action_json'])!=action.model_dump():raise HTTPException(409,'Proposal does not match decision')
    if row['status']=='committed':
        result=json.loads(row['result_json'])
        if result.get('packet_id'):
            packet=c.execute('SELECT pdf_status,delivery_status FROM escalation_packets WHERE id=?',(result['packet_id'],)).fetchone()
            if packet:result.update(dict(packet))
        return result
    if row['status']!='pending':raise HTTPException(409,'This decision proposal was cancelled; prepare a new decision')
    if row['expires_at']<rt.now():raise HTTPException(409,'Confirmation expired; prepare a new decision')
    if row['run_id']!=run['run_id']:raise HTTPException(409,'Case revision changed; retrieve the latest case')
    return None


def confirm(pid,token):
    with rt.db() as c:row=c.execute('SELECT * FROM chatgpt_proposals WHERE id=?',(pid,)).fetchone()
    if not row:raise ValueError('Unknown proposal')
    from .reviews import record_review
    return record_review(row['case_id'],Action.model_validate_json(row['action_json']),origin='chatgpt',
       expected_run_id=row['run_id'],proposal_id=pid,confirmation_token=token)


def submit_from_host(pid,case_id,run_id,action,note,evidence=None):
    """Called only by the consequential MCP WRITE tool; host approval precedes delivery.

    The native host reviews the full tool arguments. The server still binds every
    argument to the staged proposal and enforces revision, expiry and workflow guards.
    No client-provided confirmation boolean or HTTP approval shortcut is accepted.
    """
    a=Action(action=action,note=note,evidence=evidence)
    with rt.db() as c:row=c.execute('SELECT * FROM chatgpt_proposals WHERE id=?',(pid,)).fetchone()
    if not row or row['case_id']!=case_id or row['run_id']!=run_id or json.loads(row['action_json'])!=a.model_dump():
        raise HTTPException(409,'Decision arguments do not match the staged proposal')
    from .reviews import record_review
    result=record_review(case_id,a,origin='chatgpt',expected_run_id=run_id,proposal_id=pid,host_approved=True)
    return {**result,'case_id':case_id,'action':action,'submitted':True,'app_url':settings.app_url+'/population.html?case='+case_id}
