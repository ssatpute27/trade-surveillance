"""Offline grading only. This module is never imported by the agent or its tools."""
import json
import statistics
from datetime import datetime,timezone
from . import runtime as rt
from .config import ROOT
from .models import Report
from .agent import BASE,EXTRA,validate_report


def evaluate():
    truth_path=ROOT/'evals/population_truth.json'
    episodes=json.loads(truth_path.read_text())['episodes'] if truth_path.exists() else []
    with rt.source() as c:
        cases={r['case_id']:{'families':set(),'orders':set()} for r in c.execute('SELECT case_id FROM investigation_cases')}
        for r in c.execute('SELECT DISTINCT case_id,rule,order_id FROM case_alerts JOIN alerts USING(alert_id) JOIN alert_orders USING(alert_id)'):
            cases[r['case_id']]['families'].add(r['rule']);cases[r['case_id']]['orders'].add(r['order_id'])
    with rt.db() as c:
        runs=[dict(r) for r in c.execute('SELECT r.* FROM runs r JOIN (SELECT case_id,max(revision) revision FROM runs GROUP BY case_id) l USING(case_id,revision)')]
    rows=[];claims=0;valid_citations=0;citations=0;retrieved=0;expected_evidence=0
    for r in runs:
        if r['status'] in ('queued','running'):continue
        d=rt.details(r['run_id']);ctx=cases[r['case_id']];tools={e['payload'].get('tool') for e in d['events'] if e['kind']=='tool_completed'}
        required=set(BASE)
        started=next((e['payload'] for e in d['events'] if e['kind']=='investigation_started'),{})
        required.update(started.get('mandatory_checks',[]))
        if not started.get('mandatory_checks'):
            for f in ctx['families']:required|=EXTRA.get(f,set())
        records={e['evidence_id']:e for e in d['evidence']}
        report=d['report'];errors=[]
        if report:
            try:
                parsed=Report.model_validate(report);errors=validate_report(parsed,records)
                for claim in [parsed.summary,*parsed.observations,*parsed.alternative_explanations,*parsed.gaps]:
                    claims+=1
                    for cite in claim.citations:
                        citations+=1
                        valid_citations+=int(cite.evidence_id in records and cite.quote in records[cite.evidence_id]['text'])
            except Exception as e:errors=[type(e).__name__]
        matched=[e for e in episodes if set(e['order_ids']) & ctx['orders']]
        relevant={eid for e in matched for eid in e['evidence_ids']}
        found=len(relevant & records.keys());retrieved+=found;expected_evidence+=len(relevant)
        variants={e['variant'] for e in matched}
        expected=('concerning' if 'concerning' in variants else 'inconclusive' if 'inconclusive' in variants else 'plausibly_benign' if variants else None)
        missing=sorted(relevant-records.keys())
        followup=bool(rt.submitted_sources(r['run_id']))
        disagreement=bool(report and expected and report['assessment']!=expected)
        flags=[]
        if disagreement:
            if missing:flags.append('retrieval_gap')
            if report['assessment']=='inconclusive':flags.append('uncertainty_vs_scenario_label')
            if report['assessment']=='concerning' and expected!='concerning':flags.append('potential_over_escalation')
        if followup:flags.append('later_evidence_not_in_original_benchmark')
        verdicts=[e['payload'] for e in d['events'] if e['kind']=='grounding_review']
        rows.append({'case_id':r['case_id'],'run_id':r['run_id'],'revision':r['revision'],'status':r['status'],'depth':r['depth'],
            'report_valid':bool(report) and not errors,'issues':errors,'required_checks':required<=tools,
            'support_review':verdicts[-1]['supported'] if verdicts else None,
            'assessment':report['assessment'] if report else None,'recommendation':report['recommendation'] if report else None,
            'expected_assessment':expected,'scenario_variants':sorted(variants),'families':sorted(ctx['families']),
            'route_agreement':(report['assessment']==expected) if report and expected and not followup else None,
            'controls_version':started.get('controls_version','legacy'),'followup_evidence':followup,
            'diagnostic_flags':flags,'missing_key_evidence':missing,
            'summary':report['summary']['text'] if report else None,'gaps':[g['text'] for g in report['gaps']] if report else [],
            'retrieved_key_records':found,'key_record_count':len(relevant),'elapsed':r['elapsed'],'tokens':r['tokens'],
            'tool_sequence':[e['payload']['tool'] for e in d['events'] if e['kind']=='tool_completed'],
            'human_decisions':len(d['reviews'])})
    def metric(label,n,total,note):return {'label':label,'value':n,'total':total,'note':note}
    drafts=[r for r in rows if r['assessment']];graded=[r for r in drafts if r['route_agreement'] is not None]
    return {'generated_at':datetime.now(timezone.utc).isoformat(),'case_count':len(cases),'completed_runs':len(rows),'draft_count':len(drafts),
      'metrics':[
        metric('Validated drafts',sum(r['report_valid'] for r in drafts),len(drafts),'Schema, exact excerpt matching and deterministic report controls. Held runs are counted separately.'),
        metric('Exact citations',valid_citations,citations,'Quote appears verbatim in a source actually retrieved by this run. This does not establish semantic support.'),
        metric('Required checks completed',sum(r['required_checks'] for r in rows),len(rows),'Successful mandatory tool calls recorded in the audit.'),
        metric('Independent support checks',sum(r['support_review'] is True for r in drafts),len(drafts),'A separate model review; not a human accuracy score.'),
        metric('Key evidence retrieved',retrieved,expected_evidence,'Offline comparison with authored synthetic evidence keys, which the investigator cannot access.'),
        metric('Scenario assessment agreement',sum(r['route_agreement'] is True for r in graded),len(graded),'Agreement with authored scenario labels; not a legal finding or production accuracy estimate.'),
      ],'held_count':sum(not r['assessment'] for r in rows),
      'median_seconds':round(statistics.median([r['elapsed'] for r in rows if r['elapsed'] is not None]),1) if rows else None,
      'disagreements':[r for r in rows if r['route_agreement'] is False],
      'controls_cohorts':{v:sum(r['controls_version']==v for r in rows) for v in sorted({r['controls_version'] for r in rows})},
      'rows':rows,'limitations':'Small synthetic benchmark. Original scenario labels are preserved, not adjudicated truth. Diagnostic flags suggest review areas, not proven causes. Later submitted evidence is excluded from original-label agreement. Revisions use different control versions. Evaluation keys stay outside agent tools. Model support review is fallible; every draft requires analyst review.'}
