const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const code = fs.readFileSync(path.join(__dirname, '../scripts/investigation-view.js'), 'utf8');
const claim = (text, id='E-1') => ({text, citations:[{evidence_id:id,quote:text}]});
const esc = value => String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
function environment() {
  const listeners=[];
  const context=vm.createContext({
    investigation:{revision:2,status:'ready_for_review',events:[],evidence:[],report:null},
    d:{alerts:[],details:{}},selected:'CASE-1',apiConnected:true,replayMode:false,
    historyRuns:[],detailTab:'overview',reviewDrafts:{},
    document:{addEventListener:(_,fn)=>listeners.push(fn)},
    esc,sourceName:x=>x,citation:c=>`<button>${esc(c.evidence_id)}</button>`,
    claimBlock:c=>`<p>${esc(c.text)}</p>`,when:x=>x,num:x=>String(x),statusLabel:x=>x,
    titles:{size_outlier:'Unusual trading size'},descriptions:{size_outlier:'Size alert'},
    factTitles:{},reviewControls:()=>'',originalRecordingPanel:()=>'',assessmentJourney:()=>'',
    escalationPanel:()=>'',managerStatus:x=>x,renderCase:()=>{},el:()=>null
  });
  vm.runInContext(code,context);
  const report={assessment:'inconclusive',recommendation:'request_more_evidence',summary:claim('Summary'),observations:[claim('Saved finding')],alternative_explanations:[claim('Alternative')],gaps:[claim('Missing signed instruction')],reviewer_questions:['Provide the exception approval?']};
  context.investigation.report=report;
  context.a={id:'CASE-1',revision:2,status:'ready_for_review',family:'size_outlier',symbols:['AMZN'],accounts:['A-1']};
  context.c={orders:[{}],signal_features:[]};
  return {context,listeners,run:expr=>vm.runInContext(expr,context)};
}

test('request recommendation exposes actual missing evidence and questions before context',()=>{
  const {run}=environment();
  const html=run('overview(a,c)');
  assert.ok(html.indexOf('Request more evidence')<html.indexOf('Why this alert was raised'));
  assert.ok(html.indexOf('Missing signed instruction')<html.indexOf('Why this alert was raised'));
  assert.ok(html.indexOf('Provide the exception approval?')<html.indexOf('Why this alert was raised'));
});

test('a failed or unavailable tool is not displayed as a completed successful check',()=>{
  const {context,run}=environment();
  context.investigation.events=[{kind:'tool_started',payload:{tool:'read_trades'}},{kind:'tool_failed',payload:{tool:'read_trades',error_class:'TimeoutError'}}];
  assert.equal(run('investigationStepStatus(0).tone'),'attention');
  context.investigation.events=[{kind:'tool_completed',payload:{tool:'read_trades',evidence_ids:['MISSING']}}];
  context.investigation.evidence=[{evidence_id:'MISSING',status:'unavailable'}];
  assert.equal(run('investigationStepStatus(0).tone'),'attention');
});

test('findings are assigned only to sections whose saved sources they cite',()=>{
  const {context,run}=environment();
  context.investigation.events=[{kind:'tool_completed',payload:{tool:'read_trades',evidence_ids:['E-1']}}];
  context.investigation.evidence=[{evidence_id:'E-1',status:'available'},{evidence_id:'OTHER',status:'available'}];
  context.investigation.report.observations=[claim('Trade finding'),claim('Unrelated finding','OTHER')];
  assert.equal(run('investigationStepData(investigationSteps[0]).findings.length'),1);
  assert.equal(run('investigationStepData(investigationSteps[0]).findings[0].text'),'Trade finding');
  assert.equal(run('investigationStepData(investigationSteps[1]).findings.length'),0);
});

test('copying suggestions preserves notes, includes every gap, is idempotent and does not submit',()=>{
  const {context,listeners}=environment();
  context.reviewDrafts['CASE-1']='Existing note';
  const event={target:{closest:selector=>selector==='[data-use-evidence-request]'?{}:null}};
  listeners[0](event);
  const value=context.reviewDrafts['CASE-1'];
  assert.ok(value.startsWith('Existing note'));
  assert.ok(value.includes('Missing signed instruction'));
  assert.ok(value.includes('Provide the exception approval?'));
  listeners[0](event);
  assert.equal(context.reviewDrafts['CASE-1'],value);
  assert.equal(context.investigation.status,'ready_for_review');
});

test('a saved report does not imply a human decision or checks that did not run',()=>{
  const {run}=environment();
  assert.equal(run('investigationStepStatus(5).label'),'Your review');
  assert.equal(run('investigationStepStatus(2).label'),'Not recorded');
});

test('historical matches appear even when the report does not cite the reference',()=>{
  const {context,run}=environment();
  context.investigation.events=[{kind:'tool_completed',payload:{tool:'retrieve_prior_cases',evidence_ids:['PRIOR-1']}}];
  context.investigation.evidence=[{evidence_id:'PRIOR-1',source_type:'prior_case',status:'available',
    prior_case_id:'REF-2025-001',text:'Short-lived orders overlapped opposite-side executions.',
    origin:'authored_synthetic_reference_case',closed_at:'2025-02-20',
    retrieval:{method:'OpenAI embeddings + cosine similarity',model:'text-embedding-3-small'}}];
  const html=run('assessmentAreaSummaries()');
  assert.ok(html.includes('<h4>Similar historical cases</h4>'));
  assert.ok(html.includes('REF-2025-001'));
  assert.ok(html.includes('View matched case details'));
  assert.ok(html.includes('Fictional demo reference'));
  assert.ok(html.includes('linked orders and executions are not attached'));
  assert.ok(html.includes('text-embedding-3-small'));
});

test('historical cards do not expose denied source text and escape reference content',()=>{
  const {context,run}=environment();
  context.investigation.events=[{kind:'tool_completed',payload:{tool:'retrieve_prior_cases',evidence_ids:['PRIOR-1']}}];
  context.investigation.evidence=[{evidence_id:'PRIOR-1',source_type:'prior_case',status:'access_denied',text:'SECRET'}];
  assert.ok(!run('assessmentAreaSummaries()').includes('SECRET'));
  context.investigation.evidence[0]={evidence_id:'PRIOR-1',source_type:'prior_case',status:'available',text:'<script>bad</script>'};
  const html=run('assessmentAreaSummaries()');
  assert.ok(!html.includes('<script>'));
  assert.ok(html.includes('&lt;script&gt;'));
});

test('queued and manual-attention cases have no fabricated final recommendation',()=>{
  const {context,run}=environment();
  context.investigation.report=null;
  context.investigation.status=context.a.status='awaiting_investigation';
  assert.ok(run('overview(a,c)').includes('has not started'));
  assert.ok(!run('overview(a,c)').includes('Escalate for manager review'));
  context.investigation.status=context.a.status='manual_review';
  context.investigation.error='Tool <failed>';
  assert.ok(run('overview(a,c)').includes('Tool &lt;failed&gt;'));
});

test('recommendation and evidence text are escaped as content',()=>{
  const {context,run}=environment();
  context.investigation.report.reviewer_questions=['<img src=x onerror=alert(1)>'];
  const html=run('overview(a,c)');
  assert.ok(!html.includes('<img src=x'));
  assert.ok(html.includes('&lt;img src=x'));
});

test('finding labels and supporting passages follow cited source provenance only',()=>{
  const {context,run}=environment();
  context.investigation.events=[{kind:'tool_completed',payload:{tool:'market_context',evidence_ids:['MARKET']}},{kind:'tool_completed',payload:{tool:'search_communications',evidence_ids:['CHAT']}}];
  context.investigation.evidence=[{evidence_id:'MARKET',source_type:'market'},{evidence_id:'CHAT',source_type:'communication'}];
  context.sample=claim('A finding','CHAT');
  assert.ok(run('claimEvidenceLabels(sample)').includes('Trader communications'));
  assert.ok(!run('claimEvidenceLabels(sample)').includes('Market prices'));
  context.sample.citations[0].quote='<saved passage>';
  assert.ok(run('claimEvidenceDetails(sample)').includes('&lt;saved passage&gt;'));
});

test('market coverage distinguishes retrieved, cited, missing and unavailable checks',()=>{
  const {context,run}=environment();
  context.investigation.events=[{kind:'tool_completed',payload:{tool:'market_context',evidence_ids:['MARKET']}}];
  context.investigation.evidence=[{evidence_id:'MARKET',source_type:'market',status:'available'}];
  assert.ok(run('assessmentEvidenceCoverage()').includes('Retrieved · not cited in assessment'));
  assert.ok(run('assessmentEvidenceCoverage()').includes('No check recorded'));
  context.investigation.report.observations.push(claim('Market finding','MARKET'));
  assert.ok(run('assessmentEvidenceCoverage()').includes('Retrieved · cited in assessment'));
  context.investigation.evidence[0].status='unavailable';
  assert.ok(run('assessmentEvidenceCoverage()').includes('Evidence gap'));
  assert.ok(!run('assessmentEvidenceCoverage()').includes('Retrieved · cited'));
});

test('coverage includes every evidence tool and distinguishes empty results',()=>{
  const {context,run}=environment();
  context.investigation.events=[{kind:'tool_completed',payload:{tool:'read_trades',evidence_ids:[]}}];
  const html=run('assessmentEvidenceCoverage()');
  for(const label of ['Orders and executions','Relevant policy passages','Trading restrictions and approvals','Trader communications','Recorded-call transcription','Market prices and volume','Public news search','Comparable historical cases','Execution calculations and chart','Related accounts and ownership','Customer-order access'])assert.ok(html.includes(label),label);
  assert.ok(!html.includes('finish investigation'));
  assert.ok(html.includes('Completed · no saved sources'));
  assert.ok(!html.includes('Retrieved · cited'));
});

test('area summaries use saved findings and news, without assigning findings to unrelated checks',()=>{
  const {context,run}=environment();
  context.investigation.events=[{kind:'tool_completed',payload:{tool:'search_communications',evidence_ids:['CHAT']}},{kind:'tool_completed',payload:{tool:'search_market_news',evidence_ids:['NEWS']}}];
  context.investigation.evidence=[{evidence_id:'CHAT',source_type:'communication'},{evidence_id:'NEWS',source_type:'market_news',findings:[{title:'Issuer announcement',summary:'Reported earnings update.',publication_date:'2025-05-14'}]}];
  context.investigation.report.observations=[claim('Chat describes cancelled orders','CHAT')];
  const html=run('assessmentAreaSummaries()');
  assert.ok(html.includes('Trader communications &amp; recordings'));
  assert.ok(html.includes('Chat describes cancelled orders'));
  assert.ok(html.includes('Reported earnings update.'));
  assert.ok(html.includes('Publication timing remains unverified'));
  assert.ok(html.indexOf('Chat describes cancelled orders')<html.indexOf('Market data &amp; public news'));
  assert.ok(!html.includes('<h4>Accounts &amp; information access</h4>'));
});

test('area summaries do not turn search gaps into exculpatory conclusions',()=>{
  const {context,run}=environment();
  context.investigation.events=[{kind:'tool_completed',payload:{tool:'search_market_news',evidence_ids:['NEWS']}}];
  context.investigation.evidence=[{evidence_id:'NEWS',source_type:'market_news',findings:[],search_status:'no_citable_findings'}];
  assert.ok(run('assessmentAreaSummaries()').includes('does not establish that no relevant news existed'));
});
