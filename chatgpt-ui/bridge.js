// MCP Apps JSON-RPC lifecycle, matching OpenAI's single-file UI quickstart.
// No remote scripts or network requests. Confirmation remains an app-only tool.
export function createBridge(){
  let sequence=0,standard=false,listener;
  const pending=new Map();
  const notify=(method,params)=>window.parent.postMessage({jsonrpc:'2.0',method,params},'*');
  const request=(method,params,timeout=20000)=>new Promise((resolve,reject)=>{
    const id=++sequence;
    const timer=setTimeout(()=>{pending.delete(id);reject(new Error('The ChatGPT connection timed out. Check the case status before retrying.'));},timeout);
    pending.set(id,{resolve,reject,timer});
    window.parent.postMessage({jsonrpc:'2.0',id,method,params},'*');
  });
  const legacyResult=()=>{
    const host=window.openai,metadata=host?.toolResponseMetadata;
    const envelope=metadata?.call_tool_result||metadata?.mcp_tool_result;
    if(!host?.toolOutput&&!envelope)return;
    listener?.({...(envelope||{}),structuredContent:host.toolOutput||envelope?.structuredContent,_meta:envelope?._meta||metadata?._meta||metadata});
  };
  window.addEventListener('message',event=>{
    if(event.source!==window.parent)return;
    const message=event.data;
    if(!message||message.jsonrpc!=='2.0')return;
    if(Object.hasOwn(message,'id')&&!message.method){
      const entry=pending.get(message.id);if(!entry)return;
      clearTimeout(entry.timer);pending.delete(message.id);
      if(message.error)entry.reject(new Error(message.error.message||'ChatGPT rejected the request.'));
      else entry.resolve(message.result);
    }else if(message.method==='ui/notifications/tool-result')listener?.(message.params);
  });
  window.addEventListener('openai:set_globals',()=>{if(!standard)legacyResult();});
  const api={
    set ontoolresult(fn){listener=fn;},
    async connect(){
      try{
        await request('ui/initialize',{appInfo:{name:'Surveillance analyst review',version:'4.0.0'},appCapabilities:{},protocolVersion:'2026-01-26'},8000);
        standard=true;notify('ui/notifications/initialized',{});
      }catch(error){
        if(!window.openai?.callTool)throw error;
        legacyResult();
      }
      let height=0;
      new ResizeObserver(()=>{const next=Math.ceil(document.body.getBoundingClientRect().height);if(next===height)return;height=next;
        if(standard)notify('ui/notifications/size-changed',{height});
        else window.openai?.notifyIntrinsicHeight?.(height);
      }).observe(document.body);
    },
    async callServerTool({name,arguments:args}){
      if(standard)return request('tools/call',{name,arguments:args});
      if(window.openai?.callTool)return window.openai.callTool(name,args);
      throw new Error('The confirmation connection is unavailable. No decision was submitted.');
    }
  };
  return api;
}
