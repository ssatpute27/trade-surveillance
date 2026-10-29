// Analyst-facing journey, derived only from this revision's saved events and evidence.
let investigationStep = 0;
const investigationSteps = [
  {title:'Alert & trade facts', purpose:'Understand what triggered the alert and how the order compares with normal activity.', tools:['read_trades','historical_baseline']},
  {title:'Authority & policies', purpose:'Check whether the activity was authorized and which written standards apply.', tools:['order_authority','restrictions_authority','policy_search','read_submitted_evidence']},
  {title:'Communications & calls', purpose:'Review permitted messages and recordings for explanations, contradictions and evidence gaps.', tools:['search_communications','transcribe_calls','access_relationships']},
  {title:'Context & trading patterns', purpose:'Test the activity against market context, execution patterns and relevant historical cases.', tools:['market_context','search_market_news','strategy_context','order_book','linked_accounts','customer_access','reconstruct_timeline','retrieve_prior_cases','analyze_execution_patterns']},
  {title:'Agent recommendation', purpose:'Bring the evidence together, consider alternative explanations and identify what remains unresolved.', tools:[]},
  {title:'Your decision', purpose:'Review the recommendation and record the action you choose. The agent does not make the analyst decision.', tools:[]}
];
const investigationToolNames = {
  read_trades:'Orders and executions', historical_baseline:'Comparison with earlier trading',
  order_authority:'Mandates and order instructions', restrictions_authority:'Trading restrictions and approvals',
  policy_search:'Relevant policy passages', read_submitted_evidence:'Additional documents supplied for review',
  search_communications:'Trader communications', transcribe_calls:'Recorded-call transcription',
  access_relationships:'Information access and relationships', market_context:'Market prices and volume',
  search_market_news:'Public news search', strategy_context:'Strategy and position context',
  order_book:'Displayed orders and cancellations', linked_accounts:'Related accounts and ownership',
  customer_access:'Customer-order access', reconstruct_timeline:'Sequence of trading and communications',
  retrieve_prior_cases:'Comparable historical cases', analyze_execution_patterns:'Execution calculations and chart'
};
const assessmentNames = {concerning:'Concerning activity',plausibly_benign:'Plausibly explained',inconclusive:'Further evidence needed'};
const recommendationActions = {escalate:'Escalate for manager review',request_more_evidence:'Request more evidence',standard_review:'Complete standard analyst review'};

// Label evidence by its recorded retrieval tool, never by guessing from claim text.
function claimSources(claim, run=investigation) {
  return (claim.citations||[]).map(ref=>{
    const record=(run?.evidence||[]).find(e=>e.evidence_id===ref.evidence_id);
    const tools=[...new Set((run?.events||[]).filter(e=>e.kind==='tool_completed'&&(e.payload?.evidence_ids||[]).includes(ref.evidence_id)).map(e=>e.payload.tool))];
    const labels=tools.map(tool=>investigationToolNames[tool]||tool.replaceAll('_',' '));
    if(!labels.length)labels.push(record?sourceName(record.source_type||'source'):'Source not found');
    return {ref,record,labels};
  });
}
function claimEvidenceLabels(claim) {
  const labels=[...new Set(claimSources(claim).flatMap(s=>s.labels))];
  return `<span class="finding-source-labels">${labels.length?labels.map(label=>`<span>${esc(label)}</span>`).join(''):'<span>No cited sources</span>'}</span>`;
}
function claimEvidenceDetails(claim) {
  const sources=claimSources(claim);
  if(!sources.length)return '<p class="factsnote">No supporting source citations were saved for this statement.</p>';
  return `<details class="claim-support"><summary>Evidence behind this statement · ${sources.length} cited sources</summary>${sources.map(({ref,record,labels})=>`<div class="claim-source"><b>${esc(labels.join(' · '))}</b>${record&&['unavailable','access_denied'].includes(record.status)?'<span class="journey-warning"> · Evidence unavailable</span>':''}<p>${citation(ref)} ${esc(record?.filename||sourceName(record?.source_type||'source'))}</p>${ref.quote?`<blockquote>${esc(ref.quote)}</blockquote>`:'<p class="factsnote">No quoted passage saved; open the source to inspect its contents.</p>'}</div>`).join('')}</details>`;
}
function historicalReferenceSummary(source) {
  const original=source.text||'No reference summary was saved.';
  if(source.origin!=='authored_synthetic_reference_case')return original;
  let summary=original.replace(/^AUTHORED SYNTHETIC HISTORICAL REFERENCE — not an actual analyst decision\.\s*/, '');
  if(source.prior_case_id&&summary.startsWith(source.prior_case_id+': '))summary=summary.slice(source.prior_case_id.length+2);
  return summary.replace(/Fictional outcome:[^.]*\.\s*/, '')
    .replaceAll('The fictional reviewer','The reviewer')
    .replace(/\s*This analogy is not evidence of facts or permission in the current case\.$/, '');
}
function assessmentAreaSummaries() {
  const report=investigation?.report;
  if(!report)return '';
  const areas=[
    ['Orders & execution analysis',['read_trades','order_book','analyze_execution_patterns']],
    ['Historical trading',['historical_baseline']],
    ['Authority & approvals',['order_authority','restrictions_authority','read_submitted_evidence']],
    ['Policies',['policy_search']],
    ['Trader communications & recordings',['search_communications','transcribe_calls']],
    ['Market data & public news',['market_context','search_market_news']],
    ['Strategy & positions',['strategy_context']],
    ['Accounts & information access',['linked_accounts','customer_access','access_relationships']],
    ['Trading timeline',['reconstruct_timeline']],
    ['Similar historical cases',['retrieve_prior_cases']]
  ];
  return `<div class="assessment-areas">${areas.map(([title,tools])=>{
    const {checks,sources}=investigationStepData({tools});
    if(!checks.length)return '';
    const ids=new Set(sources.map(source=>source.evidence_id));
    const matches=claim=>(claim.citations||[]).some(ref=>ids.has(ref.evidence_id));
    const findings=[...report.observations,...report.alternative_explanations].filter(matches);
    const gaps=report.gaps.filter(matches);
    const news=sources.filter(source=>source.source_type==='market_news');
    const prior=sources.filter(source=>source.source_type==='prior_case'&&source.status==='available');
    if(!findings.length&&!gaps.length&&!news.length&&!prior.length&&!checks.some(check=>check.tone==='attention'))return '';
    const priorBody=prior.map(source=>`<div class="area-news"><p><b>${esc(source.prior_case_id||'Historical reference')}</b></p><p>${esc(historicalReferenceSummary(source))}</p><details class="area-sources"><summary>View matched case details · ${esc(source.prior_case_id||source.evidence_id)}</summary>${source.closed_at?`<p><b>Reference closed:</b> ${esc(when(source.closed_at))}</p>`:''}${source.retrieval?.method?`<p><b>Retrieved using:</b> ${esc(source.retrieval.method)}</p>`:''}${source.retrieval?.model?`<p><b>Embedding model:</b> ${esc(source.retrieval.model)}</p>`:''}<p>Reference summary only; linked orders and executions are not attached.</p><p class="factsnote">${esc(source.limitation||'Historical comparison only; this does not establish facts or authority in the current case.')}</p><p>Open the saved source: ${citation({evidence_id:source.evidence_id})}</p></details></div>`).join('');
    const newsBody=news.map(source=>`<div class="area-news"><p class="area-caption">Public news found through web search</p>${source.findings?.length?`<ul>${source.findings.map(item=>`<li><b>${esc(item.title)}</b>${item.publication_date?' · '+esc(item.publication_date):''}<p>${esc(item.summary)}</p></li>`).join('')}</ul><p class="factsnote">Historical news retrieved from the live web. Publication timing remains unverified; news alone does not establish trader knowledge or intent.</p>`:`<p>The search returned no citable news findings. This does not establish that no relevant news existed.</p>`}${citation({evidence_id:source.evidence_id})}</div>`).join('');
    return `<section class="area-summary"><h4>${esc(title)}</h4>${findings.length?findings.map(claimBlock).join(''):!news.length&&!prior.length&&!gaps.length?`<p class="factsnote">${checks.some(check=>check.tone==='attention')?'This check has an evidence gap or failed. See the check details below.':'Evidence was reviewed, but no separate finding was included in the saved assessment.'}</p>`:''}${newsBody}${priorBody}${gaps.length?`<div class="area-gaps"><p class="area-caption">Still unresolved</p>${gaps.map(claimBlock).join('')}</div>`:''}<details class="area-sources"><summary>Checks & sources · ${sources.length}</summary>${checks.map(check=>`<p><b>${esc(investigationToolNames[check.tool]||check.tool)}</b> · ${esc(check.state)}</p>${check.reason?`<p class="factsnote">${esc(check.reason)}</p>`:''}${check.sources.map(source=>`<p>${citation({evidence_id:source.evidence_id})} ${esc(source.filename||sourceName(source.source_type||'source'))}</p>`).join('')}`).join('')}</details></section>`;
  }).join('')}</div><details class="journey-details"><summary>All investigation checks</summary>${assessmentEvidenceCoverage()}</details>`;
}

function assessmentEvidenceCoverage() {
  const report=investigation?.report;
  const allClaims=report?[report.summary,...report.observations,...report.alternative_explanations,...report.gaps]:[];
  const cited=new Set(allClaims.flatMap(c=>(c.citations||[]).map(ref=>ref.evidence_id)));
  const groups=investigationSteps.filter(step=>step.tools.length);
  return `<section class="evidence-coverage" aria-label="Investigation evidence coverage"><h4>What the agent checked</h4><p class="factsnote">All available investigation checks, with their recorded status for this revision. Each finding below labels the evidence it cites.</p><div class="coverage-grid">${groups.map(step=>{
    const {checks}=investigationStepData(step);
    return `<div class="coverage-group"><h5>${esc(step.title)}</h5>${step.tools.map(tool=>{
      const check=checks.find(c=>c.tool===tool);
      const used=check?.sources.some(source=>cited.has(source.evidence_id));
      const status=!check?'No check recorded':check.tone!=='done'?check.state:check.sources.length?(used?'Retrieved · cited in assessment':'Retrieved · not cited in assessment'):'Completed · no saved sources';
      return `<div class="coverage-check"><div><b>${esc(investigationToolNames[tool]||tool.replaceAll('_',' '))}</b><span class="coverage-state ${check?.tone||'pending'}">${esc(status)}</span></div>${check?`<details><summary>Check details${check.sources.length?' · '+check.sources.length+' source'+(check.sources.length===1?'':'s'):''}</summary>${check.reason?`<p>${esc(check.reason)}</p>`:''}${check.error?`<p class="journey-warning">${esc(check.error)}</p>`:''}${check.sources.map(source=>`<p>${citation({evidence_id:source.evidence_id})} ${esc(source.filename||sourceName(source.source_type||'source'))}${['unavailable','access_denied'].includes(source.status)?' · Unavailable':''}</p>`).join('')}${!check.sources.length?'<p>No source records were saved for this check.</p>':''}</details>`:''}</div>`;
    }).join('')}</div>`;
  }).join('')}</div><small>“No check recorded” means this revision has no saved execution of that check. Retrieving evidence does not mean it supports a finding.</small></section>`;
}

function investigationStepData(step, run=investigation) {
  const events=run?.events||[], records=run?.evidence||[];
  const checks=step.tools.flatMap(tool=>{
    const activity=events.filter(e=>e.payload?.tool===tool&&['tool_started','tool_completed','tool_failed','tool_rejected'].includes(e.kind));
    if(!activity.length)return [];
    const latest=activity.at(-1), p=latest.payload||{};
    const completed=[...activity].reverse().find(e=>e.kind==='tool_completed');
    const ids=completed?.payload?.evidence_ids||[];
    const sources=records.filter(r=>ids.includes(r.evidence_id));
    const failed=['tool_failed','tool_rejected'].includes(latest.kind);
    const pending=latest.kind==='tool_started';
    const missing=sources.some(r=>r.status==='unavailable'||r.status==='access_denied');
    return [{tool,reason:p.reason||activity.find(e=>e.payload?.reason)?.payload.reason||'',sources,
      state:failed?'Check failed':pending?'In progress':missing?'Evidence gap':'Checked',
      tone:failed||missing?'attention':pending?'pending':'done',at:latest.at,
      error:failed?(p.message||p.error_class||'This check could not complete.'):'',
      count:completed?.payload?.result?.record_count??sources.length}];
  });
  const ids=new Set(checks.flatMap(c=>c.sources.map(s=>s.evidence_id)));
  const sources=records.filter(r=>ids.has(r.evidence_id));
  const findings=(run?.report?.observations||[]).filter(c=>c.citations?.some(s=>ids.has(s.evidence_id)));
  return {checks,sources,findings};
}

function investigationStepStatus(index,run=investigation) {
  if(index===5){
    const decision=(run?.events||[]).findLast(e=>e.kind==='human_review');
    return decision?{label:'Decision recorded',tone:'done'}:{label:run?.report?'Your review':'Pending',tone:'pending'};
  }
  if(index===4)return run?.report?{label:run.status==='manual_review'?'Needs attention':'Draft ready',tone:run.status==='manual_review'?'attention':'done'}:{label:run?.status==='manual_review'?'Needs attention':'Pending',tone:run?.status==='manual_review'?'attention':'pending'};
  const {checks}=investigationStepData(investigationSteps[index],run);
  return checks.some(c=>c.tone==='attention')?{label:'Check gaps',tone:'attention'}:
    checks.some(c=>c.tone==='pending')?{label:'In progress',tone:'pending'}:
    checks.length?{label:'Checks recorded',tone:'done'}:{label:run?.report?'Not recorded':'Pending',tone:'pending'};
}

function investigationRecommendation(a) {
  const report=investigation?.report;
  if(!report)return `<section class="investigation-brief"><div class="eyebrow">Investigation progress</div><h3>${a.status==='manual_review'?'Human attention required':esc(statusLabel(a.status))}</h3><p>${a.status==='manual_review'?esc(investigation?.error||'The agent could not complete all required checks. Review the preserved evidence and activity.'):'Follow the evidence checks below. A recommendation will appear once the investigation produces a draft.'}</p></section>`;
  const tone=report.recommendation==='escalate'?'attention':report.recommendation==='standard_review'?'done':'pending';
  const decision=(investigation.events||[]).findLast(e=>e.kind==='human_review');
  return `<section class="investigation-brief ${tone}"><div class="eyebrow">Agent recommendation · Revision ${investigation.revision}</div><div class="evidencehead"><h3>${esc(recommendationActions[report.recommendation]||report.recommendation)}</h3><span class="journey-status ${tone}">${esc(assessmentNames[report.assessment]||report.assessment)}</span></div><div class="recommendation-rationale">${claimBlock(report.summary)}</div>${report.recommendation==='request_more_evidence'?`<div class="suggested-request"><h4>Suggested information to request</h4>${report.gaps.length?`<div class="suggested-evidence-gaps">${report.gaps.map(claimBlock).join('')}</div>`:''}${report.reviewer_questions.length?`<ul class="journey-questions">${report.reviewer_questions.map(q=>`<li>${esc(q)}</li>`).join('')}</ul>`:report.gaps.map(claimBlock).join('')}${!replayMode&&investigation.revision===a.revision&&['ready_for_review','manual_review','awaiting_evidence'].includes(a.status)?'<button class="plain" data-use-evidence-request>Add suggestions to review note</button>':''}<p class="factsnote">Based on the saved assessment. Review and edit the request before sending.</p></div>`:''}<p class="factsnote">${decision?'Analyst action recorded: '+esc(decision.payload.action.replaceAll('_',' '))+' · '+when(decision.at)+' ET.':['reviewed','escalated','closed'].includes(a.status)?'Current case status: '+esc(statusLabel(a.status))+'.':'Awaiting an analyst decision.'} ${decision?'The recommendation and recorded decision are shown separately.':'The analyst can choose a different action.'}</p></section>`;
}

function assessmentSection(number,title,body,extra='') {
  return `<section class="block assessment-section ${extra}"><div class="assessment-section-title"><span class="journey-number">${number}</span><h3>${title}</h3></div>${body}</section>`;
}

function overview(a,c) {
  if(!apiConnected||!investigation)return '<div class="block" role="status"><h3>Loading current assessment…</h3><p>Retrieving the case and saved recommendation.</p></div>';
  const report=investigation.report,decision=(investigation.events||[]).findLast(e=>e.kind==='human_review');
  const controls=reviewControls(a);
  const findings=report?`<p class="factsnote">Findings are grouped by the evidence the agent reviewed. Open the source details to verify a statement.</p>${assessmentAreaSummaries()}`:`<p>${a.status==='manual_review'?esc(investigation.error||'The run could not complete its required checks. Review the evidence and activity before deciding the next step.'):a.status==='awaiting_investigation'?'The investigation has not started for this revision. Its source recordings and trading records are available below.':'The agent is gathering evidence. The assessment will appear here when a draft is ready.'}</p>`;
  const gaps=report?(report.gaps.length?report.gaps.map(claimBlock).join(''):'<p>No separate evidence gaps were recorded in this draft. The analyst should still verify that the evidence supports the proposed action.</p>'):'<p>Unresolved evidence will be listed when the agent produces an assessment.</p>';
  const context=`<p class="assessment-alert"><strong>${esc(titles[a.family])}</strong></p><p>${esc(descriptions[a.family])}</p><div class="summarygrid journey-facts"><div><small>Stock / account</small><strong>${esc(a.symbols.join(', '))} · ${esc(a.accounts.join(', '))}</strong></div><div><small>Linked orders</small><strong>${num(c.orders.length)}</strong></div></div><details class="journey-details"><summary>All alert signals and measurements</summary>${c.signal_features.map(signal=>`<div class="journey-check"><b>${esc(titles[signal.family])}</b>${Object.entries(signal.features).filter(([key])=>factTitles[key]).map(([key,value])=>`<div class="kvrow"><span>${esc(factTitles[key])}</span><b>${factValue(key,value)}</b></div>`).join('')}</div>`).join('')}</details>`;
  return `${investigationRecommendation(a)}<nav class="assessment-map" aria-label="Assessment walkthrough"><a href="#assessment-context">1 · Why flagged</a><a href="#assessment-findings">2 · Agent findings</a><a href="#assessment-gaps">3 · Evidence gaps</a><a href="#assessment-decision">4 · Your decision</a></nav><div id="assessment-context">${assessmentSection(1,'Why this alert was raised',context)}</div><div id="assessment-findings">${assessmentSection(2,'What the agent found',findings)}<div class="assessment-investigation-link"><span>Want to see how the evidence was gathered?</span><button class="plain" data-detail="investigation">Walk through investigation →</button></div></div><div id="assessment-gaps">${assessmentSection(3,'What remains unresolved',gaps+(report&&report.recommendation!=='request_more_evidence'?`<details class="journey-details"><summary>Questions suggested for the analyst</summary><ul class="journey-questions">${report.reviewer_questions.map(q=>`<li>${esc(q)}</li>`).join('')}</ul></details>`:''))}</div><div id="assessment-decision">${assessmentSection(4,decision?'Analyst decision recorded':'Your decision',decision?`<p><strong>${esc(({escalate:'Escalated to surveillance manager',mark_reviewed:'Approved / marked reviewed',request_more_evidence:'More evidence requested'})[decision.payload.action]||decision.payload.action)}</strong></p><p>${esc(decision.payload.note||'')}</p><p class="factsnote">${esc(decision.payload.actor||'Analyst')} · ${when(decision.at)} ET</p>`:`<p>Use the agent’s recommendation and cited evidence to decide the next action. Your decision is recorded separately.</p>`)}${controls||(!decision?'<div class="block"><p>No analyst action is available for this revision and case status. Check the investigation status or open the latest revision.</p></div>':'')}${investigation.manager_review?`<div class="block"><h3>Manager follow-up</h3><p>${esc(managerStatus(investigation.manager_review.status))} · ${esc(investigation.manager_review.owner)}</p><button class="plain" data-detail="manager">Open manager review</button></div>`:''}${escalationPanel()}</div><details class="block journey-details"><summary>Recordings, charts and source evidence</summary><div class="draweractions"><button class="plain" data-detail="activity">Trades &amp; charts</button><button class="plain" data-detail="communications">Trader communications</button><button class="plain" data-detail="evidence">All evidence sources</button></div>${originalRecordingPanel()||'<p>No original voice recording is attached to this revision.</p>'}</details><details class="block journey-details"><summary>Assessment history, case record and delivery</summary>${assessmentJourney()}${report&&!replayMode&&investigation.revision===a.revision?`<p><a class="plain" href="/api/cases/${encodeURIComponent(a.id)}/report.json">Download cited case record</a></p>`:''}${investigation.notification?`<p>Analyst notification: ${esc(investigation.notification.status.replaceAll('_',' '))} · ${esc(investigation.notification.recipient)}</p>`:''}<button class="plain" data-detail="history">View preserved revisions</button></details>`;
}

function investigationSourceCards(sources) {
  if(!sources.length)return '<p class="journey-empty">No source records were returned by the recorded checks in this section.</p>';
  return `<div class="journey-sources">${sources.map(source=>`<article class="journey-source"><div class="evidencehead"><b>${esc(source.filename||sourceName(source.source_type||'source'))}</b><span class="journey-status ${['unavailable','access_denied'].includes(source.status)?'attention':'done'}">${['unavailable','access_denied'].includes(source.status)?'Unavailable':'Retrieved'}</span></div><p>${esc((source.text||'No source text recorded.').slice(0,250))}${(source.text||'').length>250?'…':''}</p>${citation({evidence_id:source.evidence_id})}</article>`).join('')}</div>`;
}

function investigationEvidenceStep(a,c,index) {
  const step=investigationSteps[index], {checks,sources,findings}=investigationStepData(step);
  return `<section class="block journey-section"><div class="eyebrow">Purpose of this section</div><p class="journey-purpose">${esc(step.purpose)}</p>${index===0?`<div class="summarygrid journey-facts"><div><small>Primary alert</small><strong>${esc(titles[a.family])}</strong></div><div><small>Linked orders</small><strong>${num(c.orders.length)} · ${esc(a.symbols.join(', '))}</strong></div></div><p>${esc(descriptions[a.family])}</p><details class="journey-details"><summary>See the alert signals and measurements</summary>${c.signal_features.map(signal=>`<div class="journey-check"><b>${esc(titles[signal.family])}</b>${Object.entries(signal.features).filter(([k])=>factTitles[k]).map(([k,v])=>`<div class="kvrow"><span>${esc(factTitles[k])}</span><b>${factValue(k,v)}</b></div>`).join('')}</div>`).join('')}</details>`:''}<h3>What the agent checked</h3>${checks.length?checks.map(check=>`<div class="journey-check"><div class="evidencehead"><b>${esc(investigationToolNames[check.tool]||check.tool.replaceAll('_',' '))}</b><span class="journey-status ${check.tone}">${check.state}</span></div>${check.reason?`<p>${esc(check.reason)}</p>`:''}${check.error?`<p class="journey-warning">${esc(check.error)}</p>`:''}<small>${check.sources.length} saved source${check.sources.length===1?'':'s'}${check.at?' · '+when(check.at)+' ET':''}</small></div>`).join(''):`<p class="journey-empty">${investigation?.report?'No checks are recorded in this section for this revision.':'No checks have been recorded here yet. The agent selects checks relevant to the case.'}</p>`}</section><section class="block journey-section"><h3>What the agent found</h3>${findings.length?`<p class="factsnote">Findings from the saved assessment that cite evidence retrieved in this section. A finding can draw on several sections.</p>${findings.map(claimBlock).join('')}`:`<p class="journey-empty">${investigation?.report?'The saved assessment has no separate observation citing these sources. Review the returned evidence below and the overall recommendation in step 5.':'Findings will appear here when a saved assessment cites evidence from these checks.'}</p>`}</section>${index===2?originalRecordingPanel():''}${index===3&&sources.some(s=>s.source_type==='quantitative_analysis')?`<section class="block">${quantitativePanel(sources.find(s=>s.source_type==='quantitative_analysis'))}</section>`:''}<details class="block journey-details"><summary>Evidence returned <span class="factsnote">${sources.length} sources</span></summary>${investigationSourceCards(sources)}</details>`;
}

function investigationAssessmentStep() {
  const report=investigation?.report;
  if(!report)return `<section class="block"><h3>Recommendation not ready</h3><p>${investigation?.status==='manual_review'?'The run needs human attention. Its recorded checks and evidence remain available.':'The agent is still gathering evidence or has not started. No final recommendation is available for this revision.'}</p></section>${assessmentJourney()}`;
  const validation=(investigation.events||[]).findLast(e=>e.kind==='validation');
  return `<section class="block journey-section"><div class="eyebrow">How to read this assessment</div><p class="journey-purpose">The agent weighs the evidence, considers other explanations and recommends a next action. You decide whether that action is appropriate.</p><h3>Recommended next action</h3><p><strong>${esc(recommendationActions[report.recommendation])}</strong></p>${claimBlock(report.summary)}</section><section class="block journey-section"><h3>Evidence supporting the assessment</h3>${report.observations.map(claimBlock).join('')}</section><section class="block journey-section"><h3>Other explanations considered</h3>${report.alternative_explanations.map(claimBlock).join('')}</section><section class="block journey-section"><h3>What remains unresolved</h3>${report.gaps.length?report.gaps.map(claimBlock).join(''):'<p>No separate evidence gaps were recorded in this draft. This is not a guarantee that every source is complete.</p>'}<h3 class="journey-subheading">Questions for the analyst</h3><ul class="journey-questions">${report.reviewer_questions.map(q=>`<li>${esc(q)}</li>`).join('')}</ul></section><details class="journey-details"><summary>How the assessment developed and was checked</summary>${assessmentJourney()}<div class="block"><h3>Draft checks</h3><p>${validation?(validation.payload.passed?'The latest recorded draft validation passed.':'The latest recorded draft validation did not pass. Review the activity log and any flagged issues.'):'No draft-validation event is recorded for this revision.'}</p><p class="factsnote">Validation checks citations and report requirements. It does not prove that the recommendation is correct.</p></div></details>`;
}

function investigationDecisionStep(a) {
  const decision=(investigation?.events||[]).findLast(e=>e.kind==='human_review');
  const labels={escalate:'Escalated to surveillance manager',mark_reviewed:'Approved / marked reviewed',request_more_evidence:'More evidence requested'};
  return `<section class="block journey-section"><div class="eyebrow">Human decision</div><h3>${decision?'Recorded analyst action':'Choose the next action'}</h3><p class="journey-purpose">${esc(investigationSteps[5].purpose)}</p>${decision?`<p><strong>${esc(labels[decision.payload.action]||decision.payload.action)}</strong> · ${when(decision.at)} ET</p><p>${esc(decision.payload.note||'')}</p><p class="factsnote">Recorded by ${esc(decision.payload.actor||'analyst')}</p>`:''}<div class="decision-options"><p><b>Escalate</b><span>Send the case to the surveillance manager with its summary PDF.</span></p><p><b>Request more evidence</b><span>Specify what is missing or submit a supporting document for a follow-up investigation.</span></p><p><b>Approve / mark reviewed</b><span>Record that you reviewed the case and your rationale. This completes analyst review.</span></p></div></section>${reviewControls(a)}${!decision&&!reviewControls(a)?`<div class="block"><p>${replayMode?'This is a read-only recording.':investigation?.revision!==a.revision?'This is a preserved revision. Open the latest revision to record a decision.':!investigation?.report?'A decision is not available while the investigation is incomplete. Review the case status and any evidence gaps.':'Analyst decisions are not available in the current case status.'}</p></div>`:''}${investigation?.manager_review?`<section class="block"><h3>Manager follow-up</h3><p>${esc(managerStatus(investigation.manager_review.status))}</p><button class="plain" data-detail="manager">Open manager review</button></section>`:''}${escalationPanel()}`;
}

function agentActivity() {
  const a=d.alerts.find(a=>a.id===selected),c=d.details[selected];
  if(!a||!c)return '';
  if(!investigation)return '<div class="block" role="status"><h3>Loading investigation…</h3><p>Retrieving this case’s saved checks and evidence.</p></div>';
  const step=investigationSteps[investigationStep],status=investigationStepStatus(investigationStep);
  return `${investigationRecommendation(a)}<div class="journey-intro"><h3>Follow the investigation</h3><p>Choose a section to see its purpose, recorded checks, evidence and findings. Sections organize the work; checks can run in a different order.</p></div><div class="investigation-layout"><nav class="journey-nav" aria-label="Investigation steps">${investigationSteps.map((s,i)=>{const state=investigationStepStatus(i);return `<button data-investigation-step="${i}" aria-current="${i===investigationStep?'step':'false'}"><span class="journey-number">${i+1}</span><span><b>${esc(s.title)}</b><small class="${state.tone}">${esc(state.label)}</small></span></button>`}).join('')}</nav><div class="journey-content"><div class="journey-heading"><div><span class="eyebrow">Section ${investigationStep+1} of ${investigationSteps.length}</span><h2 id="journey-title" tabindex="-1">${esc(step.title)}</h2></div><span class="journey-status ${status.tone}">${esc(status.label)}</span></div>${investigationStep<4?investigationEvidenceStep(a,c,investigationStep):investigationStep===4?investigationAssessmentStep():investigationDecisionStep(a)}<div class="journey-pagination"><button class="plain" data-investigation-step="${investigationStep-1}" ${investigationStep===0?'disabled':''}>← Previous</button><span>${investigationStep+1} / ${investigationSteps.length}</span><button class="plain" data-investigation-step="${investigationStep+1}" ${investigationStep===investigationSteps.length-1?'disabled':''}>${investigationStep===4?'Continue to your decision':'Next section'} →</button></div></div></div><details class="block journey-details journey-audit"><summary>Activity log &amp; Platform trace <span class="factsnote">Detailed recorded events</span></summary>${technicalAgentActivity()}</details>`;
}

document.addEventListener('click',event=>{
  const requestButton=event.target.closest('[data-use-evidence-request]');
  if(requestButton){
    const report=investigation?.report;
    if(!report)return;
    const request=[report.gaps.length?'Please provide supporting evidence to resolve:\n'+report.gaps.map(gap=>'• '+gap.text).join('\n'):'',report.reviewer_questions.length?'Please address these questions:\n'+report.reviewer_questions.map(question=>'• '+question).join('\n'):''].filter(Boolean).join('\n\n');
    const existing=reviewDrafts[selected]||'';
    reviewDrafts[selected]=existing.includes(request)?existing:[existing,request].filter(Boolean).join('\n\n');
    detailTab='overview';renderCase();
    el('reviewnote')?.focus();
    el('assessment-decision')?.scrollIntoView({block:'start',behavior:'instant'});
    return;
  }
  const button=event.target.closest('[data-investigation-step]');
  if(!button||button.disabled)return;
  const index=Number(button.dataset.investigationStep);
  if(!Number.isInteger(index)||index<0||index>=investigationSteps.length)return;
  investigationStep=index;
  renderCase();
  const heading=el('journey-title');
  heading?.focus({preventScroll:true});
  heading?.scrollIntoView({block:'start',behavior:'instant'});
});
