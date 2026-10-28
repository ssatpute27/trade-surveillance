import { createBridge } from './bridge.js';
const app = createBridge();
let proposal, token;
let expiryTimer;
const root=document.getElementById('root');
function text(tag,value){const e=document.createElement(tag);e.textContent=value;root.append(e);return e;}
app.ontoolresult=(result)=>{
  clearTimeout(expiryTimer);
  if(result.isError){root.replaceChildren();text('p','The card could not be prepared. No decision was submitted. Ask ChatGPT to retrieve the latest case and prepare a new card.');return;}
  if(result.structuredContent?.chart_present){
    const data=result.structuredContent;root.replaceChildren();
    text('small',`${data.case_id} · Revision ${data.revision}`);text('h2','Execution analysis');
    const img=document.createElement('img');img.alt='Saved Code Interpreter execution chart';img.style.width='100%';
    if(result._meta?.chart_data_url?.startsWith('data:image/png;base64,')){img.src=result._meta.chart_data_url;root.append(img);}
    text('small','Evidence: '+data.evidence_id+' · Saved chart content hash verified.');
    const m=data.measurements||{};const format=n=>new Intl.NumberFormat('en-US').format(n);
    const metrics=[['Executed shares',format(m.total_shares||0)],['Executions',format(m.fill_count||0)],['Final five minutes',`${m.last_five_minutes_pct??'Unavailable'}%`],['Executed notional',new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format((m.notional_cents||0)/100)]];
    const table=document.createElement('table');table.style.width='100%';table.style.marginTop='16px';
    for(const [label,value] of metrics){const row=table.insertRow();const l=row.insertCell();l.textContent=label;l.style.padding='8px 0';const v=row.insertCell();v.textContent=value;v.style.textAlign='right';v.style.fontWeight='600';}root.append(table);
    text('p','Execution patterns support analyst review. They do not establish intent or causal price impact.');return;
  }
  if (!result.structuredContent?.proposal_id){root.replaceChildren();text('p','No decision card is available for this result. Ask ChatGPT to prepare a new decision for the latest case, or open the case in the analyst app.');return;}
  proposal=result.structuredContent;token=result._meta?.confirmation_token;
  root.replaceChildren();
  text('small',`${proposal.case_id} · Revision ${proposal.revision}`);
  text('h2',({escalate:'Escalate to manager',mark_reviewed:'Mark reviewed',request_more_evidence:'Request more evidence'})[proposal.action]);
  text('p',proposal.note);text('p',proposal.effect);
  if(proposal.recipient)text('p','Manager: '+proposal.recipient);
  if(proposal.evidence){text('h3',proposal.evidence.title);text('small',proposal.evidence.reference);text('pre',proposal.evidence.content);}
  text('small','This records your analyst decision in the same case shown in the app.');
  if(proposal.app_url){
    const url=new URL(proposal.app_url);
    if(['127.0.0.1','localhost'].includes(url.hostname)&&['http:','https:'].includes(url.protocol)){
      const link=text('a','Open this case in the analyst app');link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';link.style.display='block';link.style.marginTop='12px';
    }
  }
  const expired=Date.now()>=Date.parse(proposal.expires_at);
  if(expired)text('p','This confirmation has expired. Ask ChatGPT to prepare a new decision card after reviewing the latest case.');
  const button=text('button',expired?'Confirmation expired':'Confirm decision');button.disabled=!token||expired;
  if(!token)text('p','This card did not receive its confirmation credential. No decision was submitted. Prepare a fresh card or use the analyst app.');
  if(!expired)expiryTimer=setTimeout(()=>{if(button.textContent==='Recorded')return;button.disabled=true;button.textContent='Confirmation expired';text('p','This card has expired. Retrieve the latest case and prepare a new card.');},Math.max(0,Date.parse(proposal.expires_at)-Date.now()));
  button.onclick=async()=>{
    button.disabled=true;button.textContent='Recording…';
    try{
      const r=await app.callServerTool({name:'confirm_analyst_decision',arguments:{proposal_id:proposal.proposal_id,confirmation_token:token}});
      if(r.isError)throw new Error(r.content?.map(x=>x.text||'').join('\n')||'Decision could not be recorded');
      text('p','Decision recorded. Case status: '+(r.structuredContent?.status||'updated'));
      button.textContent='Recorded';
    }catch(e){text('p',e.message);const stale=/expired|revision changed|not awaiting|manager approval|closure approval/i.test(e.message);button.textContent=stale?'Prepare a new card':'Try again';button.disabled=stale;}
  };
};
app.connect().catch(()=>{root.textContent='The confirmation viewer could not connect to ChatGPT. No decision was submitted. Retry the viewer or open this case in the analyst app.';});
