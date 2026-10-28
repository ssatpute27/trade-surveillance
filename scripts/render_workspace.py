"""Render the analyst workspace from source alerts, without grading keys or invented reports."""
import json
import sqlite3
from pathlib import Path
from scripts.group_cases import grouped_alerts

ROOT=Path(__file__).resolve().parent.parent
HIGH={'spoofing_layering','pre_announcement','front_running','wash_self_trade','marking_close','authorization_restriction'}


def workspace_snapshot(db):
    alerts=[]
    details={}
    for group in grouped_alerts(db):
        a=group['alerts'][0]
        raw_ids=[x['alert_id'] for x in group['alerts']]
        linked=[dict(o) for o in db.execute('''SELECT o.*,t.name trader,d.name desk,ac.name account_name,
                    count(f.fill_id) executions,coalesce(sum(f.quantity),0) filled_shares,coalesce(sum(f.quantity*f.price_cents),0) notional_cents
                    FROM alert_orders ao JOIN orders o USING(order_id) JOIN traders t USING(trader_id)
                    JOIN desks d USING(desk_id) JOIN accounts ac USING(account_id) LEFT JOIN fills f USING(order_id)
                    WHERE ao.alert_id IN ('''+','.join('?' for _ in raw_ids)+''') GROUP BY o.order_id ORDER BY o.submitted_at''',raw_ids)]
        # A shared order must be counted once, even if several alerts refer to it.
        for order in linked:
            totals=db.execute('SELECT count(*),coalesce(sum(quantity),0),coalesce(sum(quantity*price_cents),0) FROM fills WHERE order_id=?',(order['order_id'],)).fetchone()
            order['executions'],order['filled_shares'],order['notional_cents']=totals
        accounts=sorted({o['account_id'] for o in linked})
        start=min(o['submitted_at'] for o in linked)
        # This static preview is read-only. Production user ACLs will be enforced by server tools.
        evidence=[dict(e) for e in db.execute('''SELECT DISTINCT e.* FROM evidence e JOIN evidence_scope s USING(evidence_id)
             WHERE s.account_id IN ('''+','.join('?' for _ in accounts)+''') AND e.status!='access_denied'
             AND e.event_at<=? AND e.available_at<=? AND e.ingested_at<=?
             AND (e.kind='public_news' OR julianday(e.event_at)>=julianday(?)-2)
             ORDER BY e.event_at DESC LIMIT 24''',(*accounts,group['cutoff_at'],group['cutoff_at'],group['cutoff_at'],start))]
        families=list(dict.fromkeys(x['rule'] for x in group['alerts']))
        row={'id':group['case_id'],'family':a['rule'],'families':families,'raw_alert_ids':raw_ids,
             'priority':'High' if any(f in HIGH for f in families) else 'Medium',
             'status':'awaiting_investigation','detected_at':group['created_at'],'cutoff_at':group['cutoff_at'],
             'symbols':sorted({o['security_id'] for o in linked}),'traders':sorted({o['trader'] for o in linked}),
             'accounts':accounts,'order_count':len(linked),'notional_cents':sum(o['notional_cents'] for o in linked)}
        alerts.append(row)
        details[group['case_id']]={'orders':linked,'features':json.loads(a['features_json']),
             'signal_features':[{'alert_id':x['alert_id'],'family':x['rule'],'features':json.loads(x['features_json'])} for x in group['alerts']],
             'evidence':evidence,'policy':dict(db.execute('SELECT * FROM policies WHERE policy_id=?',('POL-'+a['rule'],)).fetchone())}
    return {'alerts':alerts,'details':details,'as_of':max(a['cutoff_at'] for a in alerts),
            'worker_connected':False,'reports':[],'dispositions':[],
            'raw_alert_count':db.execute('SELECT count(*) FROM alerts').fetchone()[0]}


def render(db):
    snapshot=workspace_snapshot(db)
    payload=json.dumps(snapshot,separators=(',',':')).replace('<','\\u003c')
    template=(ROOT/'scripts/population.template.html').read_text()
    out=ROOT/'sample/population.html'
    template=template.replace('__INVESTIGATION_VIEW_CSS__',(ROOT/'scripts/investigation-view.css').read_text())
    template=template.replace('__INVESTIGATION_VIEW_JS__',(ROOT/'scripts/investigation-view.js').read_text())
    out.write_text(template.replace('__WORKSPACE_JSON__',payload))
    return snapshot


if __name__=='__main__':
    db=sqlite3.connect(f'file:{ROOT / "data/population.sqlite3"}?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    try:
        snapshot=render(db)
        print(f'Analyst workspace rendered with {len(snapshot["alerts"])} source alerts; no investigation reports or dispositions.')
    finally:db.close()
