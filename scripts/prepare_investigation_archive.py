"""Build labeled demo reference cases and audio re-enactments; no grading keys.

Run explicitly, once: .venv/bin/python -m scripts.prepare_investigation_archive
Speech synthesis uses live OpenAI TTS. Transcription occurs when the agent calls
transcribe_calls, not by copying the authored speech script into a transcript.
"""
import hashlib
import json
import re
from pathlib import Path
from app.evidence_tools import EvidenceTools,context
from app.investigation_extensions import archive
from app.indexes import client
from app import runtime as rt


EXAMPLES={
 'spoofing_layering':('Displayed-order cancellations','Escalated for specialist review',
   'Repeated short-lived orders overlapped opposite-side executions. The fictional reviewer requested venue-level records and strategy controls; cancellation rate alone was insufficient to establish intent.'),
 'pre_announcement':('Trading before an announcement','More access evidence requested',
   'Trading preceded a public announcement and an ambiguous research message was present. The fictional reviewer requested information-access logs and document publication times; a public event schedule was not proof of advance results.'),
 'front_running':('Customer and principal order timing','Escalated for specialist review',
   'Principal executions occurred after customer instruction receipt. The fictional reviewer required evidence of who received the instruction and any documented hedging consent before drawing a conclusion.'),
 'wash_self_trade':('Matched orders under common control','Reviewed with documented crossing rationale',
   'Matched executions involved common control. In this fictional historical example a contemporaneous approved cross reference explained the matching. Current cases require their own approval and ownership evidence.'),
 'marking_close':('Heavy participation near the close','More strategy evidence requested',
   'High closing participation coincided with a benchmark instruction. The fictional reviewer sought the actual instruction, participation limits and order-book context; timing alone did not establish price manipulation.'),
 'coordinated_trading':('Similar activity across accounts','More relationship evidence requested',
   'Similar quantities and times across accounts prompted review. The fictional reviewer requested controller records and independent instructions. Similar trading alone was insufficient to infer coordination.'),
 'size_outlier':('Large order relative to prior activity','Reviewed with documented authority',
   'A large order exceeded its historical cohort. In this fictional historical example a signed instruction and the execution window supported the stated order authority. That authority did not establish all aspects of investment rationale.'),
 'authorization_restriction':('Trading during a restriction window','More exception evidence requested',
   'Executions intersected an effective restriction. An exception was mentioned but unavailable. The fictional reviewer requested the exception archive instead of treating a missing document as proof of an unauthorized trade.'),
}

ADDITIONAL_CALLS={
 'CASE-AF1D9C5F':{'source_id':'E-000085','kind':'communication',
     'script':"Hey, the closing print matters for the valuation. Keep our buys concentrated in the final few minutes. And keep this message for the supervisor to review."},
 'CASE-E6272323':{'source_id':'E-000068','kind':'customer_order_access',
     'script':"Just confirming, the customer instruction allows the disclosed principal hedge ahead of the block. The risk approval and allocation link are attached. Compliance still needs to check the exception."},
 'CASE-0088C625':{'source_id':'E-000005','kind':'strategy_log',
     'script':"The bids come out when the inventory hedge sells are done. That's how this strategy's been running all week. The risk ticket is approved, but check the full sequence before drawing a conclusion."},
}


def conversational_script(case_id,source):
    """Adapt source wording for speech without introducing new investigative facts."""
    if case_id in ADDITIONAL_CALLS:
        if source['evidence_id']!=ADDITIONAL_CALLS[case_id]['source_id']:raise ValueError('Call requires its approved source record')
        return ADDITIONAL_CALLS[case_id]['script']
    if case_id=='CASE-52074E40':
        match=re.search(r': (buy|sell) ([\d,]+) (\w+) shares for ([\w-]+);',source['content'])
        if not match:raise ValueError('Cannot prepare conversational mandate without source quantities')
        side,quantity,symbol,account=match.groups()
        spoken_symbol={'NVDA':'Nvidia'}.get(symbol,symbol)
        digits=dict(zip('0123456789','zero one two three four five six seven eight nine'.split()))
        spoken_account=' '.join(digits.get(char,char) for char in account if char!='-')
        return f"Hi. I've got a {side} instruction for {quantity} shares of {spoken_symbol}, account {spoken_account}. Please work it within the execution window on the signed mandate."
    content=re.sub(r'^Trader to research colleague:\s*','',source['content'])
    return 'Hey, '+content[0].lower()+content[1:]


def main():
    rt.init();folder=archive();(folder/'audio').mkdir(parents=True,exist_ok=True)
    examples=[]
    for i,(family,(title,outcome,rationale)) in enumerate(EXAMPLES.items(),1):
        examples.append({'case_id':f'REF-2025-{i:03}','families':[family],'closed_at':'2025-02-20T16:00:00Z',
            'available_at':'2025-02-21T09:00:00Z','status':'available','origin':'authored_synthetic_reference_case',
            'text':f'AUTHORED SYNTHETIC HISTORICAL REFERENCE — not an actual analyst decision. REF-2025-{i:03}: {title}. Fictional outcome: {outcome}. {rationale} This analogy is not evidence of facts or permission in the current case.'})
    (folder/'prior_cases.json').write_text(json.dumps(examples,indent=2)+'\n')
    manifest=json.loads((folder/'recordings.json').read_text()) if (folder/'recordings.json').exists() else []
    c=client()
    for case_id in ['CASE-52074E40','CASE-4A3C38E5','CASE-51CDC1FB',*ADDITIONAL_CALLS]:
        tool=object.__new__(EvidenceTools);tool.ctx=context(case_id)
        candidates=[r for r in tool.records(['communication']) if r['status']=='available']
        # Select the existing research-message lead without using any evaluation labels.
        if case_id in ADDITIONAL_CALLS:
            spec=ADDITIONAL_CALLS[case_id]
            candidates=[r for r in tool.records([spec['kind']]) if r['status']=='available' and r['evidence_id']==spec['source_id']]
        elif case_id!='CASE-52074E40':candidates.sort(key=lambda r:('blue folder' not in r['content'].lower(),r['event_at']))
        else:
            with rt.source() as db:
                ids=tool.ctx['order_ids'];marks=','.join('?' for _ in ids)
                mandate_ids={r[0] for r in db.execute(f'SELECT mandate_id FROM orders WHERE order_id IN ({marks})',ids) if r[0]}
            candidates=[r for r in tool.records(['mandate']) if r['status']=='available' and any(mid in r['content'] for mid in mandate_ids)]
        if not candidates:raise RuntimeError('No source is eligible for the demo re-enactment: '+case_id)
        source=candidates[0]
        if any(r['case_id']==case_id and r['derived_from']==source['evidence_id'] and r.get('active',True) and r.get('speech_style')=='conversational-v3' for r in manifest):continue
        # Retain old pilot assets for preserved reports, but use only the linked order's mandate going forward.
        for r in manifest:
            if r['case_id']==case_id:r['active']=False
        recording_id='CALL-'+case_id.removeprefix('CASE-')+'-'+source['evidence_id']+'-V3';filename=recording_id+'.mp3'
        script=conversational_script(case_id,source)
        voice='marin'
        path=folder/'audio'/filename
        with c.audio.speech.with_streaming_response.create(model='gpt-4o-mini-tts',voice=voice,input=script,
                instructions='You are speaking privately to a familiar colleague on a quick phone call, not reading a script. Use casual American English, a relaxed lower volume, easy contractions, subtle breaths and slightly uneven natural pacing. Start softly on Hey or Hi, pause briefly after the question, then deliver the rest matter-of-factly. No announcer cadence, no theatrical suspicion, no whispering, no exaggerated emphasis. Keep the supplied words exactly; add no commentary.',response_format='mp3') as response:
            response.stream_to_file(path)
        manifest.append({'recording_id':recording_id,'case_id':case_id,'accounts':tool.ctx['accounts'],
            'recorded_at':source['event_at'],'available_at':source['available_at'],'ingested_at':source['ingested_at'],
            'status':'available','filename':filename,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'derived_from':source['evidence_id'],'synthetic':True,'created_at':rt.now(),
            'voice_origin':f'OpenAI gpt-4o-mini-tts, {voice}; AI-generated voice','speech_style':'conversational-v3',
            'disclosure':'Fictional historical call time. Audio re-enacts an existing synthetic source and is not independent corroboration.'})
        (folder/'recordings.json').write_text(json.dumps(manifest,indent=2)+'\n')
        # Keep authored source scripts separate; they never enter the transcription response.
        (folder/(recording_id+'.script.txt')).write_text(script+'\n')
        print('Prepared synthetic audio:',recording_id,flush=True)
    print('Archive ready:',len(examples),'labeled reference cases;',len(manifest),'synthetic recordings',flush=True)


if __name__=='__main__':main()
