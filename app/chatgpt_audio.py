"""Original case audio delivered through an allowlisted HTTPS media origin."""
import json
from urllib.parse import urlparse
from mcp.types import CallToolResult,TextContent,ToolAnnotations
from .config import ROOT,settings
from . import runtime as rt
from .evidence_tools import context
from .investigation_extensions import recordings,audio_path,recording_previews

ORIGIN='https://trade-surveillance-demo-audio.vercel.app'
URI='ui://trade-surveillance/https-recording-v1.html'


def recording_result(case_id,recording_id=None):
    ctx=context(case_id);eligible=recordings(ctx)
    if recording_id is not None:eligible=[r for r in eligible if r['recording_id']==recording_id]
    if len(eligible)!=1:raise ValueError('Choose one permitted recording from this case recording list')
    record=eligible[0];audio_path(record)
    path=ROOT/'data/hosted_recordings.json'
    hosted=json.loads(path.read_text()).get('recordings',{}).get(record['recording_id'],{}) if path.exists() else {}
    media_url=hosted.get('url','');parsed=urlparse(media_url)
    allowed=parsed.scheme=='https' and parsed.netloc==urlparse(ORIGIN).netloc and hosted.get('sha256')==record['sha256']
    with rt.db() as c:run=c.execute('SELECT run_id FROM runs WHERE case_id=? ORDER BY revision DESC LIMIT 1',(case_id,)).fetchone()
    preview=next(r for r in recording_previews(ctx,run['run_id'] if run else None) if r['recording_id']==record['recording_id'])
    public={'case_id':case_id,'recording_id':record['recording_id'],'recording_present':True,'inline_available':allowed,
            'recorded_at':record['recorded_at'],'transcript_status':preview['transcript_status'],
            'audio_sha256':record['sha256'],'original_recording_url':settings.app_url+preview['audio_url'],
            'disclosure':'AI-generated fictional case recording. Playback does not start investigation or transcription.'}
    return CallToolResult(content=[TextContent(type='text',text=json.dumps(public))],structuredContent=public,
                          _meta={'media_url':media_url if allowed else None})


def register(mcp):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False),
              meta={'ui':{'resourceUri':URI},'openai/outputTemplate':URI})
    def play_case_recording(case_id:str,recording_id:str|None=None)->CallToolResult:
        """Play original case audio inside ChatGPT using an allowlisted HTTPS source. Works before investigation; no transcription, agent run, decision or email. Validates case scope, cutoff, recording ID, original content hash and hosted media mapping. The user presses Play. If inline_available=false, offer original_recording_url in the analyst app. Do not claim successful playback merely because the tool returned."""
        return recording_result(case_id,recording_id)

    @mcp.resource(URI,mime_type='text/html;profile=mcp-app',meta={
        'ui':{'prefersBorder':True,'csp':{'connectDomains':[],'resourceDomains':[ORIGIN]}},
        'openai/widgetCSP':{'connect_domains':[],'resource_domains':[ORIGIN]}})
    def player():
        bridge=(ROOT/'chatgpt-ui/bridge.js').read_text().replace('export function createBridge','function createBridge')
        return '''<!doctype html><html><head><meta charset="utf-8"><style>body{font:14px/1.5 system-ui;margin:0;padding:24px;color:light-dark(#183139,#e5eef2);background:light-dark(white,#18232e);color-scheme:light dark}h2{font-size:21px;margin:4px 0 14px}audio{width:100%;margin:12px 0}small{color:light-dark(#62787d,#a8b8c8)}a{display:block;margin-top:12px}</style></head><body><main id="root">Loading original recording…</main><script>'''+bridge+'''
const root=document.getElementById('root');const app=createBridge();
function text(tag,value){const e=document.createElement(tag);e.textContent=value;root.append(e);return e;}
app.ontoolresult=result=>{root.replaceChildren();const data=result.structuredContent||{};if(!data.recording_present){text('p','No permitted recording is available for this result.');return;}
text('small',data.case_id);text('h2','Original voice recording');text('small',data.recording_id);
const media=result._meta?.media_url;
if(data.inline_available&&typeof media==='string'&&new URL(media).origin==='''+json.dumps(ORIGIN)+'''){
const audio=document.createElement('audio');audio.controls=true;audio.preload='metadata';audio.setAttribute('aria-label','Play original case recording');audio.src=media;root.append(audio);
const status=text('p','Loading original audio…');audio.addEventListener('loadedmetadata',()=>{status.textContent='Ready to play · '+audio.duration.toFixed(1)+' seconds';});audio.addEventListener('play',()=>{status.textContent='Playing original recording';});audio.addEventListener('error',()=>{status.textContent='Playback failed: '+(audio.error?.message||'Open the original recording below.');});
audio.addEventListener('pause',()=>{status.textContent=audio.ended?'Recording finished':'Recording paused';});audio.addEventListener('ended',()=>{status.textContent='Recording finished';});
}else text('p','Use the original recording link for this case.');
text('p',data.transcript_status==='available'?'Transcript available in the case evidence.':'Transcript pending for this revision.');text('small',data.disclosure);
try{const linkUrl=new URL(data.original_recording_url);if(['127.0.0.1','localhost'].includes(linkUrl.hostname)){const link=text('a','Open recording in the analyst app');link.href=linkUrl.href;link.target='_blank';link.rel='noopener noreferrer';}}catch{}
};app.connect().catch(()=>{root.textContent='The recording viewer could not connect. Ask for the original recording link.';});
</script></body></html>'''
