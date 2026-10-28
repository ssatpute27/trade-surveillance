const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function fixture(legacy){
  const listeners={},sent=[],timers=new Map();let timerId=0;
  const parent={postMessage:message=>sent.push(message)};
  const window={parent,openai:legacy,addEventListener:(name,fn)=>listeners[name]=fn};
  const context={window,Map,Promise,Error,Object,document:{body:{}},ResizeObserver:class{observe(){}},
    setTimeout:fn=>{timers.set(++timerId,fn);return timerId;},clearTimeout:id=>timers.delete(id)};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(__dirname+'/bridge.js','utf8').replace('export function createBridge','function createBridge')+';this.bridge=createBridge()',context);
  const respond=(message,source=parent)=>listeners.message({source,data:message});
  return {bridge:context.bridge,respond,sent,listeners,timers};
}
test('only parent messages can deliver hidden card metadata or resolve confirmation',async()=>{
  const f=fixture();let received;
  f.bridge.ontoolresult=r=>received=r;
  const ready=f.bridge.connect();const init=f.sent[0];
  f.respond({jsonrpc:'2.0',id:init.id,result:{}});await ready;
  assert.equal(f.sent[1].method,'ui/notifications/initialized');
  const notification={jsonrpc:'2.0',method:'ui/notifications/tool-result',params:{_meta:{confirmation_token:'private'}}};
  f.respond(notification,{});assert.equal(received,undefined);
  f.respond(notification);assert.equal(received._meta.confirmation_token,'private');
  const result=f.bridge.callServerTool({name:'confirm_analyst_decision',arguments:{proposal_id:'test',confirmation_token:'private'}});
  const call=f.sent.at(-1);assert.equal(call.method,'tools/call');
  f.respond({jsonrpc:'2.0',id:call.id,result:{structuredContent:{status:'reviewed'}}});
  assert.equal((await result).structuredContent.status,'reviewed');
  assert.equal(f.timers.size,0);
});
test('legacy fallback preserves UI-only metadata after initialization rejection',async()=>{
  let calls=0;const legacy={toolOutput:{proposal_id:'test'},toolResponseMetadata:{mcp_tool_result:{_meta:{confirmation_token:'private'}}},callTool:async()=>{calls++;return {structuredContent:{status:'reviewed'}};}};
  const f=fixture(legacy);let result;f.bridge.ontoolresult=r=>result=r;
  const ready=f.bridge.connect();f.respond({jsonrpc:'2.0',id:f.sent[0].id,error:{message:'Unsupported lifecycle'}});await ready;
  assert.equal(result._meta.confirmation_token,'private');
  assert.equal((await f.bridge.callServerTool({name:'confirm_analyst_decision',arguments:{}})).structuredContent.status,'reviewed');
  assert.equal(calls,1);
});
test('confirmation timeout never retries or switches transports automatically',async()=>{
  const f=fixture();const ready=f.bridge.connect();f.respond({jsonrpc:'2.0',id:f.sent[0].id,result:{}});await ready;
  const result=f.bridge.callServerTool({name:'confirm_analyst_decision',arguments:{}});
  [...f.timers.values()][0]();await assert.rejects(result,/timed out/);
  assert.equal(f.sent.filter(m=>m.method==='tools/call').length,1);
});
