import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import FileResponse,JSONResponse,Response
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from scripts.render_workspace import workspace_snapshot
from . import runtime as rt
from . import notifications
from . import escalations
from . import manager
from .agent import run_investigation
from .config import settings,ROOT
from .models import Action,AnalystReviewRequest,ManagerAction

stop=asyncio.Event()
worker_tasks=[]


async def worker():
    while not stop.is_set():
        run=rt.claim()
        if not run:
            try:await asyncio.wait_for(stop.wait(),timeout=1)
            except asyncio.TimeoutError:pass
            continue
        try:await asyncio.to_thread(run_investigation,run)
        except Exception as e:
            rt.update(run['run_id'],status='manual_review',error=type(e).__name__+'; worker could not initialize this investigation')
            rt.audit(run['run_id'],'manual_review_required',{'error_class':type(e).__name__,'evidence_preserved':True})


async def intake_worker():
    while not stop.is_set():
        if rt.meta_get('automatic_intake',False):await asyncio.to_thread(rt.ingest_all)
        try:await asyncio.wait_for(stop.wait(),timeout=10)
        except asyncio.TimeoutError:pass


async def email_worker():
    while not stop.is_set():
        await asyncio.to_thread(notifications.deliver_pending)
        try:await asyncio.wait_for(stop.wait(),timeout=5)
        except asyncio.TimeoutError:pass


async def escalation_worker():
    while not stop.is_set():
        try:await asyncio.to_thread(escalations.process_pending)
        except Exception as e:rt.meta_set('escalation_worker_error',type(e).__name__)
        try:await asyncio.wait_for(stop.wait(),timeout=5)
        except asyncio.TimeoutError:pass


@asynccontextmanager
async def lifespan(app):
    rt.init();rt.recover();notifications.recover();escalations.recover();stop.clear()
    if rt.meta_get('index_ready',False):
        if rt.meta_get('automatic_intake',False):rt.ingest_all()
        worker_tasks.extend(asyncio.create_task(worker(),name='investigator') for _ in range(settings.worker_concurrency))
        worker_tasks.append(asyncio.create_task(intake_worker(),name='intake'))
    worker_tasks.append(asyncio.create_task(email_worker()))
    worker_tasks.append(asyncio.create_task(escalation_worker()))
    yield
    stop.set()
    # Allow the bounded active run to finish instead of abandoning a partial report.
    await asyncio.gather(*worker_tasks,return_exceptions=True)
    worker_tasks.clear()


app=FastAPI(title='AI Trade Surveillance Investigation',lifespan=lifespan)

@app.exception_handler(RequestValidationError)
async def safe_validation_error(request,exc):
    return JSONResponse(status_code=422,content={'detail':[{'loc':e['loc'],'msg':e['msg'],'type':e['type']} for e in exc.errors()]})



@app.middleware('http')
async def local_only(request:Request,call_next):
    host=request.headers.get('host','').split(':')[0]
    if host not in ('127.0.0.1','localhost','testserver'):
        return __import__('starlette.responses',fromlist=['JSONResponse']).JSONResponse({'detail':'Local workspace only'},status_code=403)
    if request.method not in ('GET','HEAD','OPTIONS'):
        if request.headers.get('x-requested-with')!='surveillance-ui':
            return __import__('starlette.responses',fromlist=['JSONResponse']).JSONResponse({'detail':'Workspace request header required'},status_code=403)
        origin=request.headers.get('origin')
        if origin and origin not in (settings.app_url,'http://localhost:8767','http://testserver'):
            return __import__('starlette.responses',fromlist=['JSONResponse']).JSONResponse({'detail':'Unexpected request origin'},status_code=403)
    return await call_next(request)


@app.get('/api/workspace')
def workspace():
    with rt.source() as c:snapshot=workspace_snapshot(c)
    with rt.db() as c:
        latest={r['case_id']:dict(r) for r in c.execute('''SELECT r.* FROM runs r JOIN
            (SELECT case_id,max(revision) revision FROM runs GROUP BY case_id) latest USING(case_id,revision)''')}
        reviews=[dict(r) for r in c.execute('SELECT * FROM reviews ORDER BY at')]
        report_ids=[r[0] for r in c.execute("SELECT run_id FROM runs WHERE status IN ('ready_for_review','reviewed','escalated') AND report_json IS NOT NULL")]
        recorded_cases={r[0] for r in c.execute('''SELECT DISTINCT r.case_id FROM runs r JOIN snapshots s USING(run_id)
            JOIN (SELECT case_id,max(revision) revision FROM runs GROUP BY case_id) latest USING(case_id,revision)
            WHERE json_extract(s.payload,'$.source_type')='call_transcript' ''')}
        managed={r['case_id']:dict(r) for r in c.execute('SELECT * FROM manager_cases')}
    review_map={r['run_id']:r for r in reviews}
    from .investigation_extensions import load_records
    available_audio=load_records('recordings.json')
    for a in snapshot['alerts']:
        a['has_recording']=a['id'] in recorded_cases or any(record.get('active',True) and record['case_id']==a['id'] and record['status']=='available' and set(record['accounts'])<=set(a['accounts']) and all(record[key]<=a['cutoff_at'] for key in ('recorded_at','available_at','ingested_at')) for record in available_audio)
        a['manager_review']=managed.get(a['id'])
        r=latest.get(a['id'])
        a['last_activity_at']=a['detected_at']
        if r:
            a['last_activity_at']=max(r['updated_at'],managed.get(a['id'],{}).get('updated_at',''))
            a['status']=r['status'];a['run_id']=r['run_id'];a['depth']=r['depth'];a['revision']=r['revision']
            a['assessment']=json.loads(r['report_json'])['assessment'] if r['report_json'] else None
            a['recommendation']=json.loads(r['report_json'])['recommendation'] if r['report_json'] else None
            a['error']=r['error']
    snapshot.update({'worker_connected':any(t.get_name()=='investigator' and not t.done() for t in worker_tasks) and rt.meta_get('index_ready',False),
        'reports':report_ids,'dispositions':reviews,'notification_configured':notifications.configured(),
        'automatic_intake':rt.meta_get('automatic_intake',False),'analyst_email':settings.analyst_email,'sender_email':settings.notification_from,'manager_email':settings.surveillance_manager_email})
    return snapshot


@app.get('/api/cases/{case_id}/investigation')
def investigation(case_id:str):
    with rt.db() as c:r=c.execute('SELECT run_id FROM runs WHERE case_id=? ORDER BY revision DESC LIMIT 1',(case_id,)).fetchone()
    from .evidence_tools import context
    from .investigation_extensions import recording_previews
    result=rt.details(r[0]) if r else {'status':'awaiting_investigation','events':[],'evidence':[],'report':None,'reviews':[]}
    try:result['recordings']=recording_previews(context(case_id),r[0] if r else None)
    except ValueError:raise HTTPException(404,'Case unavailable')
    from .image_evidence import previews
    result['images']=previews(context(case_id),r[0] if r else None)
    return result


@app.get('/api/cases/{case_id}/images/{image_id}.png')
def case_image(case_id:str,image_id:str):
    from .image_evidence import resolve
    try:_,_,path=resolve(case_id,image_id)
    except (ValueError,OSError):raise HTTPException(404,'Image unavailable for this case')
    return FileResponse(path,media_type='image/png',headers={'Cache-Control':'private, no-store'})


class ImageReviewRequest(BaseModel):
    run_id:str=Field(min_length=36,max_length=36)


@app.post('/api/cases/{case_id}/images/{image_id}/review')
def review_case_image(case_id:str,image_id:str,body:ImageReviewRequest):
    from .image_evidence import resolve,read_image
    from .indexes import client
    with rt.db() as c:r=c.execute('SELECT run_id FROM runs WHERE case_id=? ORDER BY revision DESC LIMIT 1',(case_id,)).fetchone()
    if not r or r[0]!=body.run_id:raise HTTPException(409,'Case revision changed; reopen the case')
    try:resolve(case_id,image_id)
    except (ValueError,OSError):raise HTTPException(404,'Image unavailable for this case')
    try:return read_image(case_id,image_id,client().with_options(timeout=60,max_retries=1),body.run_id)
    except Exception as exc:
        rt.audit(body.run_id,'image_review_failed',{'image_id':image_id,'error_class':type(exc).__name__,'assessment_unchanged':True})
        raise HTTPException(502,'Image review could not be verified. Original evidence and saved assessment are unchanged.')


@app.get('/api/cases/{case_id}/communications')
def case_communications(case_id:str):
    from .chatgpt_cases import read_section
    try:return read_section(case_id,'communications',limit=100)
    except ValueError as e:raise HTTPException(404,str(e))


@app.post('/api/cases/{case_id}/events')
def incoming(case_id:str):
    if not rt.meta_get('index_ready',False):raise HTTPException(503,'Evidence indexing is not ready')
    try:r,duplicate=rt.ingest(case_id)
    except ValueError as e:raise HTTPException(404,str(e))
    return {'run_id':r['run_id'],'duplicate':duplicate,'status':r['status']}


@app.post('/api/cases/{case_id}/manager-review')
def manager_review(case_id:str,action:ManagerAction):
    try:return manager.decide(case_id,action)
    except ValueError as e:raise HTTPException(409,str(e))


@app.post('/api/cases/{case_id}/review')
def review(case_id:str,action:AnalystReviewRequest):
    from .reviews import record_review
    return record_review(case_id,Action.model_validate(action.model_dump(exclude={'run_id'})),expected_run_id=str(action.run_id))

@app.get('/api/cases/{case_id}/escalations/{packet_id}.pdf')
def escalation_pdf(case_id:str,packet_id:str):
    row=escalations.packet(packet_id)
    if not row or row['case_id']!=case_id:raise HTTPException(404,'Escalation packet not found')
    if row['pdf_status']!='ready':raise HTTPException(409,'Escalation PDF is not ready')
    try:body=escalations.verified_pdf(row)
    except (ValueError,OSError):raise HTTPException(409,'Escalation PDF integrity check failed')
    return Response(body,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="{case_id}-escalation.pdf"','Cache-Control':'private, no-store'})


@app.get('/api/cases/{case_id}/escalation-preview.pdf')
def escalation_preview(case_id:str):
    try:data=escalations.preview_data(case_id)
    except ValueError as e:raise HTTPException(409,str(e))
    return Response(escalations.pdf_bytes(data),media_type='application/pdf',headers={'Content-Disposition':f'inline; filename="{case_id}-escalation-preview.pdf"','Cache-Control':'private, no-store'})


@app.post('/api/cases/{case_id}/escalations/{packet_id}/retry-pdf')
def retry_escalation_pdf(case_id:str,packet_id:str):
    row=escalations.packet(packet_id)
    if not row or row['case_id']!=case_id:raise HTTPException(404,'Escalation packet not found')
    with rt.db() as c:c.execute("UPDATE escalation_packets SET pdf_status='pending',pdf_error=NULL WHERE id=? AND pdf_status='failed'",(packet_id,))
    row=escalations.generate_escalation_pdf(packet_id)
    return {'pdf_status':row['pdf_status']}


class EmailCredentials(BaseModel):
    app_password:str=Field(min_length=16,max_length=24)


@app.post('/api/notifications/gmail')
def configure_gmail(body:EmailCredentials):
    password=''.join(body.app_password.split())
    if not re.fullmatch('[A-Za-z0-9]{16}',password):raise HTTPException(422,'Enter the 16-character Google app password')
    # Persist only to the ignored local env file, never the audit log or response.
    path=ROOT/'.env';lines=path.read_text().splitlines() if path.exists() else []
    lines=[line for line in lines if not line.startswith('SMTP_PASSWORD=')]
    lines.append('SMTP_PASSWORD='+password)
    temp=path.with_suffix('.env-tmp')
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:f.write('\n'.join(lines)+'\n')
    temp.replace(path);path.chmod(0o600)
    settings.smtp_password=password
    with rt.db() as c:c.execute("UPDATE escalation_packets SET delivery_status='pending',attempts=0,delivery_error=NULL WHERE delivery_status='blocked_authentication'")
    with rt.db() as c:
        c.execute("UPDATE notifications SET status='pending',error=NULL,attempts=0 WHERE status IN ('blocked_configuration','failed')")
    return {'configured':True,'sender':settings.notification_from,'recipient':settings.analyst_email}


@app.get('/api/notifications')
def email_status():
    with rt.db() as c:rows=[dict(r) for r in c.execute('SELECT id,created_at,status,recipient,subject,error,sent_at FROM notifications ORDER BY created_at DESC LIMIT 30')]
    return {'configured':notifications.configured(),'sender':settings.notification_from,'recipient':settings.analyst_email,'messages':rows}




DEMO_CASES={'documented_order':'CASE-52074E40','pre_announcement':'CASE-4A3C38E5','missing_evidence':'CASE-51CDC1FB',
            'principal_hedge':'CASE-E6272323','quote_cancellations':'CASE-0088C625',
            'closing_valuation':'CASE-AF1D9C5F'}

class DemoEvent(BaseModel):
    scenario:str
    event_id:str=Field(min_length=8,max_length=80,pattern=r'^[a-zA-Z0-9-]+$')

@app.post('/api/demo/events')
def demo_event(body:DemoEvent):
    if body.scenario not in DEMO_CASES:raise HTTPException(422,'Choose an available demonstration sample')
    if not rt.meta_get('index_ready',False):raise HTTPException(503,'Evidence indexing is not ready')
    case_id=DEMO_CASES[body.scenario]
    with rt.source() as c:
        if not c.execute('SELECT 1 FROM investigation_cases WHERE case_id=?',(case_id,)).fetchone():raise HTTPException(404,'Demo source case is unavailable')
    with rt.db() as c:
        c.execute('BEGIN IMMEDIATE')
        existing=c.execute('SELECT * FROM demo_events WHERE event_id=?',(body.event_id,)).fetchone()
        if existing:return {'case_id':existing['case_id'],'run_id':existing['run_id'],'duplicate':True}
        if c.execute('SELECT 1 FROM manager_cases WHERE case_id=?',(case_id,)).fetchone():raise HTTPException(409,'This case is supervised. Use the manager workflow or submit requested evidence to continue it.')
        prior=c.execute('SELECT * FROM runs WHERE case_id=? ORDER BY revision DESC LIMIT 1',(case_id,)).fetchone()
        at=rt.now()
        if prior and prior['status']=='awaiting_investigation':
            rid=prior['run_id']
            c.execute("UPDATE runs SET status='queued',queue_priority=100,updated_at=? WHERE run_id=?",(at,rid))
        elif prior and prior['status'] in ('queued','running'):
            rid=prior['run_id'];c.execute('UPDATE runs SET queue_priority=100 WHERE run_id=?',(rid,))
        else:
            rid=str(uuid4());revision=prior['revision']+1 if prior else 1
            c.execute('INSERT INTO runs(run_id,case_id,revision,status,created_at,updated_at,parent_run,queue_priority) VALUES (?,?,?,?,?,?,?,?)',
                (rid,case_id,revision,'queued',at,at,prior['run_id'] if prior else None,100))
            c.execute('INSERT INTO audit(run_id,at,kind,payload) VALUES (?,?,?,?)',(rid,at,'case_received',json.dumps({'case_id':case_id,'revision':revision,'source':'synthetic upstream event simulator'})))
        c.execute('INSERT INTO demo_events VALUES (?,?,?,?)',(body.event_id,case_id,rid,at))
        c.execute('INSERT INTO audit(run_id,at,kind,payload) VALUES (?,?,?,?)',(rid,at,'demo_event_received',json.dumps({'event_id':body.event_id,'source':'synthetic upstream event simulator','live_api_calls':True})))
    return {'case_id':case_id,'run_id':rid,'duplicate':False,'message':'Synthetic event accepted. An available worker will investigate automatically using live APIs.'}


@app.get('/api/activity')
def live_activity():
    with rt.db() as c:
        latest=[dict(r) for r in c.execute('SELECT r.* FROM runs r JOIN (SELECT case_id,max(revision) revision FROM runs GROUP BY case_id) l USING(case_id,revision)')]
        active=[r for r in latest if r['status']=='running']
        waiting=sorted([r for r in latest if r['status']=='queued'],key=lambda r:(-r['queue_priority'],r['created_at']))
        recent=sorted([r for r in latest if r['status'] not in ('queued','running')],key=lambda r:r['updated_at'],reverse=True)[:6]
        cards=[]
        for r in active+waiting[:3]+recent:
            events=[dict(e)|{'payload':json.loads(e['payload'])} for e in c.execute('SELECT * FROM audit WHERE run_id=? ORDER BY seq',(r['run_id'],))]
            source_checks=[e for e in events if e['kind']=='tool_completed' and e['payload'].get('evidence_ids')]
            last=next((e for e in reversed(events) if e['kind'] in ('tool_started','tool_completed','initial_assessment','depth_changed','draft_started','validation','report_ready','manual_review_required')),None)
            initial=next((e for e in events if e['kind']=='initial_assessment'),None)
            started=next((e for e in events if e['kind']=='investigation_started'),None)
            stage='Queued'
            if r['status']=='running':
                stage='Deep investigation' if r['depth']=='deep' else 'Initial evidence checks'
                if any(e['kind']=='draft_started' for e in events):stage='Writing / validating draft'
            elif r['status']=='awaiting_investigation':stage='Awaiting investigation'
            elif r['status']=='ready_for_review':stage='Ready for analyst review'
            elif r['status']=='manual_review':stage='Needs human attention'
            elif r['status']=='escalated':stage='Analyst escalated'
            elif r['status']=='reviewed':stage='Analyst reviewed'
            sources=c.execute('SELECT count(*) FROM snapshots WHERE run_id=?',(r['run_id'],)).fetchone()[0]
            cards.append({'case_id':r['case_id'],'run_id':r['run_id'],'revision':r['revision'],'status':r['status'],'depth':r['depth'],'stage':stage,
                'started_at':started['at'] if started else None,'updated_at':r['updated_at'],'last_event':last,
                'initial_assessment':initial['payload']['assessment'] if initial else None,'source_count':sources,'check_count':len(source_checks),
                'assessment':json.loads(r['report_json'])['assessment'] if r['report_json'] else None,'error':r['error']})
    return {'automatic_intake':rt.meta_get('automatic_intake',False),'running_count':len(active),'queued_count':len(waiting),'cards':cards}


@app.get('/api/operations')
def operations():
    with rt.db() as c:
        counts={r[0]:r[1] for r in c.execute('SELECT status,count(*) FROM runs r JOIN (SELECT case_id,max(revision) revision FROM runs GROUP BY case_id) latest USING(case_id,revision) GROUP BY status')}
    return {'automatic_intake':rt.meta_get('automatic_intake',False),'index_ready':rt.meta_get('index_ready',False),'counts':counts}


@app.post('/api/operations/intake')
def enable_intake():
    if not rt.meta_get('index_ready',False):raise HTTPException(503,'Evidence indexing is not ready')
    count=rt.ingest_all();rt.meta_set('automatic_intake',True)
    return {'automatic_intake':True,'new_cases':count}


@app.get('/api/evaluation')
def evaluation():
    from .evaluation import evaluate
    return evaluate()


@app.get('/api/cases/{case_id}/history')
def history(case_id:str):
    with rt.db() as c:ids=[r[0] for r in c.execute('SELECT run_id FROM runs WHERE case_id=? ORDER BY revision DESC',(case_id,))]
    return {'runs':[rt.details(rid) for rid in ids]}


@app.get('/api/cases/{case_id}/audio/{recording_id}')
def case_audio(case_id:str,recording_id:str):
    from .evidence_tools import context
    from .investigation_extensions import recordings,audio_path
    try:ctx=context(case_id)
    except ValueError:raise HTTPException(404,'Case unavailable')
    record=next((r for r in recordings(ctx,include_retired=True) if r['recording_id']==recording_id),None)
    if not record:raise HTTPException(404,'Recording unavailable in this case scope')
    try:path=audio_path(record)
    except (ValueError,FileNotFoundError):raise HTTPException(409,'Recording failed integrity or availability checks')
    return FileResponse(path,media_type='audio/mpeg',headers={'Cache-Control':'private, no-store'})


@app.get('/api/cases/{case_id}/report.json')
def report_export(case_id:str):
    with rt.db() as c:r=c.execute('SELECT run_id FROM runs WHERE case_id=? ORDER BY revision DESC LIMIT 1',(case_id,)).fetchone()
    data=rt.details(r[0]) if r else None
    if not data or not data['report']:raise HTTPException(409,'No validated draft exists for this revision')
    return Response(json.dumps({'title':'AI Trade Surveillance Investigation','synthetic':True,'mode':'live_record','investigation':data},indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="{data["case_id"]}-revision-{data["revision"]}.json"'})


@app.get('/api/cases/{case_id}/analysis/{run_id}/{filename}')
def analysis_artifact(case_id:str,run_id:str,filename:str):
    import hashlib
    from .quantitative import artifact_folder
    if not re.fullmatch(r'[a-f0-9]{64}\.(png|json)',filename):raise HTTPException(404,'Unknown analysis artifact')
    with rt.db() as c:
        records=[json.loads(r[0]) for r in c.execute('''SELECT s.payload FROM snapshots s JOIN runs r USING(run_id)
            WHERE r.run_id=? AND r.case_id=? AND json_extract(s.payload,'$.source_type')='quantitative_analysis' ''',(run_id,case_id))]
    metadata=next((a for r in records for a in r.get('artifacts',{}).values() if a['filename']==filename),None)
    if not metadata:raise HTTPException(404,'Analysis artifact unavailable in this case revision')
    path=artifact_folder(run_id)/filename
    if not path.is_file():raise HTTPException(404,'Saved analysis artifact unavailable')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=metadata['sha256']:raise HTTPException(409,'Analysis artifact integrity check failed')
    return FileResponse(path,media_type=metadata['media_type'],headers={'Cache-Control':'private, no-store',
        'Content-Disposition':('inline' if filename.endswith('.png') else 'attachment')+f'; filename="{filename}"'})


@app.get('/api/policies')
def policies():
    index=rt.meta_get('policy_index',{})
    return {'documents':[{'filename':p.name,'content':p.read_text(),'indexed':any(Path(name).stem==p.stem for name in index.get('files',{})),'indexed_filename':next((name for name in index.get('files',{}) if Path(name).stem==p.stem),None)} for p in sorted((ROOT/'docs/surveillance_policies').glob('POL-*.md'))]}


@app.get('/api/policies/{filename}')
def policy_download(filename:str):
    allowed={p.stem+'.pdf' for p in (ROOT/'docs/surveillance_policies').glob('POL-*.md')}
    if filename not in allowed:raise HTTPException(404,'Unknown policy')
    path=ROOT/'output/pdf'/filename
    if not path.is_file():raise HTTPException(404,'PDF has not been rendered')
    return FileResponse(path,media_type='application/pdf',filename=filename)


@app.get('/api/replays')
def replays():
    from .replay import list_replays
    return {'recordings':list_replays()}


@app.get('/api/replays/{run_id}')
def replay(run_id:str):
    from .replay import load_replay
    try:return load_replay(run_id)
    except ValueError:raise HTTPException(404,'Unknown recorded investigation')


@app.get('/')
def home():return FileResponse(ROOT/'sample/population.html')


app.mount('/',StaticFiles(directory=ROOT/'sample'),name='workspace')
