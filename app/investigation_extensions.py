"""Scoped timelines, historical analogies and on-demand audio transcription.

Authored reference cases are separate from live analyst decisions and evaluation keys.
Demo recordings re-enact existing evidence; they are not independent corroboration.
"""
import hashlib
import json
import re
from array import array
from datetime import datetime, timedelta
from pathlib import Path
from . import runtime as rt
from .config import settings


def archive():
    return Path(settings.investigation_archive)


def load_records(filename):
    path=archive()/filename
    return json.loads(path.read_text()) if path.exists() else []


def recordings(ctx,include_retired=False):
    """Permissions and source availability are checked before reading any audio."""
    return [r for r in load_records('recordings.json')
            if (include_retired or r.get('active',True)) and r['case_id']==ctx['case_id'] and set(r['accounts'])<=set(ctx['accounts'])
            and r['status']=='available'
            and all(r[key]<=ctx['cutoff'] for key in ('recorded_at','available_at','ingested_at'))]


def recording_previews(ctx,run_id=None):
    """Expose permitted original audio without transcribing or changing a run."""
    saved=rt.recalled(run_id) if run_id else {}
    transcribed={r.get('recording_id') for r in saved.values() if r.get('source_type')=='call_transcript' and r.get('status')=='available'}
    result=[]
    for r in recordings(ctx):
        result.append({key:r.get(key) for key in ('recording_id','recorded_at','available_at','ingested_at','sha256','derived_from','voice_origin','disclosure')}|
                      {'audio_url':f"/api/cases/{ctx['case_id']}/audio/{r['recording_id']}",
                       'transcript_status':'available' if r['recording_id'] in transcribed else 'pending',
                       'synthetic':True})
    return result


def audio_path(record):
    filename=record['filename']
    if not re.fullmatch(r'CALL-[A-Z0-9-]+\.mp3',filename):raise ValueError('Invalid recording filename')
    path=archive()/'audio'/filename
    if not path.is_file():raise FileNotFoundError('Recording unavailable')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:raise ValueError('Recording integrity check failed')
    return path


def timeline(tool):
    ctx=tool.ctx;events=[]
    marks=','.join('?' for _ in ctx['order_ids'])
    with rt.source() as c:
        for row in c.execute(f'SELECT * FROM orders WHERE order_id IN ({marks}) AND submitted_at<=?',(*ctx['order_ids'],ctx['cutoff'])):
            events.append({'at':row['submitted_at'],'kind':'order_submitted','source_id':row['order_id'],
                           'detail':f"{row['side']} {row['original_quantity']} {row['security_id']} shares"})
        # Collapse executions into exact totals per order, retaining first and last times.
        for row in c.execute(f'''SELECT order_id,min(executed_at) first_at,max(executed_at) last_at,
                count(*) fills,sum(quantity) quantity FROM fills WHERE order_id IN ({marks})
                AND executed_at<=? AND ingested_at<=? GROUP BY order_id''',(*ctx['order_ids'],ctx['cutoff'],ctx['cutoff'])):
            for field,kind in [('first_at','first_fill'),('last_at','last_fill')]:
                events.append({'at':row[field],'kind':kind,'source_id':row['order_id'],
                               'detail':f"{row['quantity']} shares across {row['fills']} eligible fills; totals cover the full execution interval, not this instant"})
        for row in c.execute(f'SELECT * FROM customer_instructions WHERE order_id IN ({marks}) AND received_at<=?',(*ctx['order_ids'],ctx['cutoff'])):
            events.append({'at':row['received_at'],'kind':'customer_instruction','source_id':row['instruction_id'],'detail':row['channel']})
        for row in c.execute(f'SELECT * FROM venue_orders WHERE parent_order_id IN ({marks}) AND submitted_at<=?',(*ctx['order_ids'],ctx['cutoff'])):
            for field,kind in [('submitted_at','venue_order_submitted'),('cancelled_at','venue_order_cancelled')]:
                if row[field] and row[field]<=ctx['cutoff']:
                    events.append({'at':row[field],'kind':kind,'source_id':row['venue_order_id'],'detail':f"Parent {row['parent_order_id']}"})
    for r in tool.records(['communication','authorization_record','access','strategy_log']):
        if r['status']=='available':
            events.append({'at':r['event_at'],'kind':r['kind'],'source_id':r['evidence_id'],
                           'detail':r['content'],'relationship':'Same authorized account scope; not necessarily the same order or security'})
    for r in recordings(ctx):
        events.append({'at':r['recorded_at'],'kind':'recorded_call','source_id':r['recording_id'],
                       'detail':'Synthetic audio re-enactment; use transcribe_calls for actual transcript',
                       'derived_from':r['derived_from']})
    events.sort(key=lambda r:(r['at'],r['kind'],r['source_id']))
    # Bounded output is explicit, never silently interpreted as complete archive coverage.
    limited=events[:160]
    return [tool.doc('timeline',{'scope':'Linked orders plus account-scoped source events, all at or before case cutoff. Event proximity does not prove causation or knowledge.',
                                'cutoff':ctx['cutoff'],'event_count':len(events),'returned_count':len(limited),
                                'truncated':len(events)>len(limited),'events':limited},extra={'timeline_events':limited})]


def prior_cases(tool,query):
    ctx=tool.ctx;candidates=[]
    for r in load_records('prior_cases.json'):
        if r['status']!='available' or r['closed_at']>=ctx['start'] or r['available_at']>ctx['cutoff']:
            continue
        if not set(r['families']) & set(ctx['families']):continue
        if r['case_id']==ctx['case_id']:continue
        # Unscoped archive entries are permitted only for authored demo references.
        if r.get('accounts'):
            if not set(r['accounts'])<=set(ctx['accounts']):continue
        elif r.get('origin')!='authored_synthetic_reference_case':continue
        candidates.append(r)
    # Only actual human-reviewed prior live cases are eligible. Agent recommendations never count.
    with rt.db() as c:
        live=[dict(r) for r in c.execute('''SELECT v.*,r.case_id FROM reviews v JOIN runs r USING(run_id)
            WHERE v.at<? AND r.case_id!=? AND v.action IN ('mark_reviewed','escalate') ORDER BY v.at DESC LIMIT 100''',
            (ctx['start'],ctx['case_id']))]
    for r in live:
        from .evidence_tools import context
        previous=context(r['case_id'])
        if not set(previous['accounts'])<=set(ctx['accounts']) or not set(previous['families']) & set(ctx['families']):continue
        text=f"Prior case {r['case_id']}. Analyst action: {r['action']}. Recorded note: {r['note']}"
        candidates.append({'case_id':r['case_id'],'closed_at':r['at'],'text':text,'origin':'actual_local_analyst_decision'})
    if not candidates:
        return [tool.doc('prior_case','No eligible earlier reviewed cases were found in the authorized archive. This is not evidence that this activity is benign or novel.')]
    from .prior_case_search import rank_prior_cases
    ranked=rank_prior_cases(tool,candidates,query)
    return [tool.doc('prior_case',r['text'],origin=r['origin'],extra={
        'prior_case_id':r['case_id'],'closed_at':r['closed_at'],
        'comparison_only':True,'retrieval':{
            'method':'family filter + OpenAI embeddings + cosine similarity',
            'model':settings.embedding_model,'semantic_score':round(score,4),
            'lexical_score':lexical,'score':round(score,4)},
        'limitation':'Historical analogy only. Does not establish current-case facts, authority or disposition.'})
        for score,lexical,r in ranked]


def transcribe_calls(tool,query):
    eligible=recordings(tool.ctx)
    if not eligible:
        return [tool.doc('call_coverage','No eligible recording is present in the supplied case archive. This does not establish that no call occurred.',status='unavailable')]
    result=[]
    for r in eligible[:3]:
        path=audio_path(r)
        key='audio_transcript:'+r['sha256']+':'+settings.transcription_model
        cached=rt.meta_get(key)
        if cached:
            rt.audit(tool.run_id,'audio_transcription',{'recording_id':r['recording_id'],'model':settings.transcription_model,
                'cache_hit':True,'audio_sha256':r['sha256'],'original_request_id':cached.get('request_id')})
        else:
            with path.open('rb') as audio:
                response=tool.client.audio.transcriptions.create(file=audio,model=settings.transcription_model,
                    response_format='verbose_json',timestamp_granularities=['segment'],language='en',temperature=0)
            cached={'text':response.text,'segments':[s.model_dump() if hasattr(s,'model_dump') else dict(s) for s in (response.segments or [])],
                    'duration':response.duration,'model':settings.transcription_model,'transcribed_at':rt.now(),
                    'request_id':getattr(response,'_request_id',None)}
            if not cached['text'].strip():raise RuntimeError('Empty audio transcript')
            rt.meta_set(key,cached)
            rt.audit(tool.run_id,'audio_transcription',{'recording_id':r['recording_id'],'model':settings.transcription_model,
                'cache_hit':False,'audio_sha256':r['sha256'],'request_id':cached['request_id'],'duration_seconds':cached['duration']})
        record=tool.doc('call_transcript',cached['text'],origin='OpenAI Audio Transcriptions API',extra={
            'recording_id':r['recording_id'],'event_at':r['recorded_at'],
            'audio_url':f"/api/cases/{tool.ctx['case_id']}/audio/{r['recording_id']}",
            'audio_sha256':r['sha256'],'segments':cached['segments'],'transcription':{k:v for k,v in cached.items() if k not in ('text','segments')},
            'synthetic':True,'derived_from':r['derived_from'],
            'limitation':'AI-generated voice re-enacts an existing synthetic source; not an independent recording or corroboration. Transcript can contain recognition errors; verify the audio. Speaker identity is not verified.'})
        digest=hashlib.sha256(record['text'].encode()).hexdigest()
        with rt.db() as c:
            embedded=c.execute('SELECT 1 FROM embeddings WHERE evidence_id=? AND source_hash=? AND model=?',
                (record['evidence_id'],digest,settings.embedding_model)).fetchone()
        if not embedded:
            embedding=tool.client.embeddings.create(model=settings.embedding_model,input=record['text'],dimensions=512)
            tool.tokens+=embedding.usage.total_tokens
            with rt.db() as c:c.execute('INSERT OR REPLACE INTO embeddings VALUES (?,?,?,?)',
                (record['evidence_id'],digest,settings.embedding_model,array('f',embedding.data[0].embedding).tobytes()))
        result.append(record)
    return result
