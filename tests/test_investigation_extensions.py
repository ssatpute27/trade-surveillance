import hashlib
import json
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from app import runtime as rt
from app.config import settings
from app.evidence_tools import EvidenceTools
from app.investigation_extensions import recordings, audio_path, transcribe_calls, prior_cases, timeline
from app.server import app
from scripts.prepare_investigation_archive import conversational_script,ADDITIONAL_CALLS


@pytest.fixture
def extension_tool(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'runtime_path',str(tmp_path/'runtime.sqlite3'))
    monkeypatch.setattr(settings,'investigation_archive',str(tmp_path/'archive'))
    rt.init()
    folder=tmp_path/'archive';(folder/'audio').mkdir(parents=True)
    tool=object.__new__(EvidenceTools)
    tool.ctx={'case_id':'CASE-TEST','accounts':['A'],'cutoff':'2025-05-02T12:00:00Z',
              'start':'2025-05-02T09:00:00Z','families':['size_outlier']}
    tool.run_id='run-test';tool.tokens=0
    return tool,folder


def manifest(folder,**overrides):
    data=b'synthetic audio bytes'
    (folder/'audio'/'CALL-TEST.mp3').write_bytes(data)
    record={'case_id':'CASE-TEST','accounts':['A'],'status':'available','recording_id':'CALL-TEST',
        'recorded_at':'2025-05-02T09:00:00Z','available_at':'2025-05-02T09:01:00Z',
        'ingested_at':'2025-05-02T09:02:00Z','filename':'CALL-TEST.mp3','sha256':hashlib.sha256(data).hexdigest(),
        'derived_from':'E-original',**overrides}
    (folder/'recordings.json').write_text(json.dumps([record]))
    return record


@pytest.mark.parametrize('override',[{'case_id':'OTHER'},{'accounts':['B']},{'status':'access_denied'},{'active':False},
    {'available_at':'2025-05-03T00:00:00Z'},{'ingested_at':'2025-05-03T00:00:00Z'},
    {'recorded_at':'2025-05-03T00:00:00Z'}])
def test_recording_scope_checked_before_audio_access(extension_tool,override):
    tool,folder=extension_tool;manifest(folder,**override)
    assert recordings(tool.ctx)==[]


def test_audio_hash_and_filename_are_enforced(extension_tool):
    _,folder=extension_tool;r=manifest(folder)
    (folder/'audio'/r['filename']).write_bytes(b'tampered')
    with pytest.raises(ValueError,match='integrity'):audio_path(r)
    with pytest.raises(ValueError,match='filename'):audio_path(r|{'filename':'../../.env'})


def test_real_transcription_interface_and_cache_preserve_provenance(extension_tool):
    tool,folder=extension_tool;manifest(folder)
    (folder/'CALL-TEST.script.txt').write_text('AUTHORED SCRIPT MUST NEVER BE USED AS TRANSCRIPT')
    calls=[]
    def create(**kwargs):
        assert kwargs['file'].read()==b'synthetic audio bytes'
        assert kwargs['model']=='whisper-1' and kwargs['timestamp_granularities']==['segment']
        assert 'prompt' not in kwargs
        calls.append(kwargs['model'])
        return SimpleNamespace(text='Recognized audio only.',segments=[{'start':0,'end':1,'text':'Recognized audio only.'}],duration=1,_request_id='req-test')
    tool.client=SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)),
        embeddings=SimpleNamespace(create=lambda **_:SimpleNamespace(usage=SimpleNamespace(total_tokens=5),data=[SimpleNamespace(embedding=[.1]*512)])))
    first=transcribe_calls(tool,'');second=transcribe_calls(tool,'')
    assert calls==['whisper-1']
    assert first==second and first[0]['text']=='Recognized audio only.'
    assert first[0]['derived_from']=='E-original' and first[0]['segments'][0]['start']==0
    assert first[0]['transcription']['request_id']=='req-test'
    assert 'AUTHORED SCRIPT' not in json.dumps(rt.details(tool.run_id))
    with rt.db() as c:
        assert c.execute('SELECT count(*) FROM embeddings').fetchone()[0]==1
        events=[json.loads(r[0]) for r in c.execute("SELECT payload FROM audit WHERE kind='audio_transcription'")]
    assert [e['cache_hit'] for e in events]==[False,True]
    tool.records=lambda _:[]
    searched=tool.communications('recognized call')
    assert searched[0]['source_type']=='call_transcript'
    assert searched[0]['retrieval']['semantic_score']==1


def test_prior_cases_exclude_future_denied_and_other_families(extension_tool):
    tool,folder=extension_tool
    embedded=[]
    def embed(**kwargs):
        embedded.extend(kwargs['input'])
        return SimpleNamespace(usage=SimpleNamespace(total_tokens=5),data=[
            SimpleNamespace(index=i,embedding=[1.0]+[0.0]*511) for i,_ in enumerate(kwargs['input'])])
    tool.client=SimpleNamespace(embeddings=SimpleNamespace(create=embed))
    r={'case_id':'REF-1','families':['size_outlier'],'closed_at':'2025-04-01T00:00:00Z',
       'available_at':'2025-04-01T00:00:00Z','status':'available','origin':'authored_synthetic_reference_case',
       'text':'Explicitly fictional comparison about a large mandate.'}
    (folder/'prior_cases.json').write_text(json.dumps([r,r|{'case_id':'future','closed_at':'2025-05-03'},
        r|{'case_id':'denied','status':'access_denied'},r|{'case_id':'other','families':['front_running']},
        r|{'case_id':'private','accounts':['B'],'text':'DO NOT EMBED PRIVATE'},
        r|{'case_id':'unscoped','origin':'actual_local_analyst_decision','text':'DO NOT EMBED UNSCOPED'}]))
    found=prior_cases(tool,'large mandate')
    assert len(found)==1 and found[0]['prior_case_id']=='REF-1'
    assert found[0]['comparison_only'] and found[0]['origin']=='authored_synthetic_reference_case'
    assert embedded==[r['text'],'large mandate']
    assert found[0]['retrieval']['semantic_score']==1.0


def test_timeline_is_ordered_scoped_and_bounded_at_cutoff(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'runtime_path',str(tmp_path/'runtime.sqlite3'));rt.init()
    tool=EvidenceTools('timeline-test','CASE-4A3C38E5',None)
    r=timeline(tool)[0];events=r['timeline_events']
    assert events and events==sorted(events,key=lambda e:(e['at'],e['kind'],e['source_id']))
    assert all(e['at']<=tool.ctx['cutoff'] for e in events)
    order_events=[e for e in events if e['kind'] in ('order_submitted','first_fill','last_fill')]
    assert all(e['source_id'] in tool.ctx['order_ids'] for e in order_events)
    assert 'truncated' in r['text'] and 'does not prove causation' in r['text']


def test_audio_route_cannot_cross_case_scope(extension_tool,monkeypatch):
    tool,folder=extension_tool;manifest(folder)
    c=TestClient(app)
    assert c.get('/api/cases/CASE-52074E40/audio/CALL-TEST').status_code==404
    assert c.get('/api/cases/UNKNOWN/audio/CALL-TEST').status_code==404
    # Retired assets stay playable in preserved revisions, but are not investigated again.
    manifest(folder,active=False)
    monkeypatch.setattr('app.evidence_tools.context',lambda _:tool.ctx)
    response=c.get('/api/cases/CASE-TEST/audio/CALL-TEST',headers={'Range':'bytes=0-8'})
    assert response.status_code==206 and response.content==b'synthetic'


def test_conversational_audio_keeps_source_values_without_spoken_demo_intro():
    text=conversational_script('CASE-52074E40',{'content':'Document M-1: buy 30,000 NVDA shares for A-02; execution window listed. Signed earlier.'})
    assert '30,000 shares of Nvidia' in text and 'account A zero two' in text
    assert 'signed mandate' in text
    assert not any(word in text.lower() for word in ('synthetic','training','re-enactment','simulation'))
    text=conversational_script('CASE-4A3C38E5',{'content':'Trader to research colleague: Does the blue folder go public after the bell? Keep the figures out of the desk channel until then.'})
    assert text=='Hey, does the blue folder go public after the bell? Keep the figures out of the desk channel until then.'


def test_conversational_audio_rejects_unparseable_mandate():
    with pytest.raises(ValueError):conversational_script('CASE-52074E40',{'content':'No signed mandate is available.'})


def test_additional_call_scripts_require_their_scoped_source_record():
    for case_id,spec in ADDITIONAL_CALLS.items():
        tool=object.__new__(EvidenceTools)
        from app.evidence_tools import context
        tool.ctx=context(case_id)
        source=next(r for r in tool.records([spec['kind']]) if r['evidence_id']==spec['source_id'])
        assert source['status']=='available'
        assert conversational_script(case_id,source)==spec['script']
        with pytest.raises(ValueError):conversational_script(case_id,{'evidence_id':'unrelated'})


def test_workspace_marks_only_retrieved_call_evidence(extension_tool):
    case='CASE-E6272323';run,_=rt.ingest(case)
    client=TestClient(app)
    find=lambda:next(a for a in client.get('/api/workspace').json()['alerts'] if a['id']==case)
    assert not find()['has_recording']
    rt.remember(run['run_id'],{'evidence_id':'CALL-TEST','text':'Recognized call','status':'available','source_type':'call_transcript'})
    assert find()['has_recording']


def test_original_recording_available_before_investigation_without_transcription(extension_tool):
    tool,folder=extension_tool
    from app.evidence_tools import context
    case='CASE-AF1D9C5F';ctx=context(case)
    record=manifest(folder,case_id=case,accounts=ctx['accounts'])
    client=TestClient(app)
    result=client.get('/api/cases/'+case+'/investigation')
    assert result.status_code==200
    data=result.json()
    assert data['status']=='awaiting_investigation' and data['report'] is None
    preview=data['recordings'][0]
    assert preview['transcript_status']=='pending' and 'filename' not in preview
    audio=client.get(preview['audio_url'],headers={'Range':'bytes=0-8'})
    assert audio.status_code==206 and audio.content==b'synthetic'
    with rt.db() as c:
        assert c.execute('SELECT count(*) FROM runs').fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM snapshots').fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM audit').fetchone()[0]==0
    entry=next(a for a in client.get('/api/workspace').json()['alerts'] if a['id']==case)
    assert entry['has_recording']


def test_recording_pending_is_revision_specific(extension_tool):
    tool,folder=extension_tool
    from app.evidence_tools import context
    from app.investigation_extensions import recording_previews
    case='CASE-AF1D9C5F';ctx=context(case)
    record=manifest(folder,case_id=case,accounts=ctx['accounts'])
    old,_=rt.ingest(case)
    rt.remember(old['run_id'],{'evidence_id':'TRANSCRIPT-TEST','recording_id':record['recording_id'],'source_type':'call_transcript','status':'available','text':'Saved transcript'})
    fresh,_=rt.ingest(case,revision=2,parent_run=old['run_id'])
    assert recording_previews(ctx,old['run_id'])[0]['transcript_status']=='available'
    assert recording_previews(ctx,fresh['run_id'])[0]['transcript_status']=='pending'

