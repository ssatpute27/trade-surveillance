"""Group source alerts by shared orders; never consult scenario outcomes."""
import hashlib
import json

ORDER=['spoofing_layering','pre_announcement','front_running','wash_self_trade',
       'marking_close','authorization_restriction','coordinated_trading','size_outlier']


def grouped_alerts(db):
    rows={r['alert_id']:dict(r) for r in db.execute('SELECT a.*,f.features_json FROM alerts a JOIN alert_features f USING(alert_id)')}
    parent={aid:aid for aid in rows}
    def root(a):
        while parent[a]!=a:
            parent[a]=parent[parent[a]];a=parent[a]
        return a
    first={}
    for link in db.execute('SELECT * FROM alert_orders ORDER BY alert_id,order_id'):
        aid,oid=link['alert_id'],link['order_id']
        if oid in first:parent[root(aid)]=root(first[oid])
        else:first[oid]=aid
    groups={}
    for aid in rows:groups.setdefault(root(aid),[]).append(rows[aid])
    result=[]
    for alerts in groups.values():
        alerts.sort(key=lambda a:(ORDER.index(a['rule']),a['alert_id']))
        source_ids=sorted(a['source_event_id'] for a in alerts)
        case_id='CASE-'+hashlib.sha256('|'.join(source_ids).encode()).hexdigest()[:8].upper()
        result.append({'case_id':case_id,'primary_alert_id':alerts[0]['alert_id'],
                       'created_at':min(a['detected_at'] for a in alerts),
                       'cutoff_at':max(a['cutoff_at'] for a in alerts),'alerts':alerts})
    return sorted(result,key=lambda c:(c['created_at'],c['case_id']))


def persist_cases(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS investigation_cases(
        case_id TEXT PRIMARY KEY,primary_alert_id TEXT NOT NULL REFERENCES alerts,
        created_at TEXT NOT NULL,cutoff_at TEXT NOT NULL,status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS case_alerts(case_id TEXT NOT NULL REFERENCES investigation_cases,
        alert_id TEXT NOT NULL UNIQUE REFERENCES alerts,PRIMARY KEY(case_id,alert_id));''')
    for case in grouped_alerts(db):
        db.execute('INSERT OR IGNORE INTO investigation_cases VALUES (?,?,?,?,?)',
                   (case['case_id'],case['primary_alert_id'],case['created_at'],case['cutoff_at'],'awaiting_investigation'))
        db.executemany('INSERT OR IGNORE INTO case_alerts VALUES (?,?)',[(case['case_id'],a['alert_id']) for a in case['alerts']])
    db.commit()
