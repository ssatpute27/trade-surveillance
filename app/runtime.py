"""Durable local investigation runs, audit, evidence snapshots and email outbox."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from .config import settings


def now():return datetime.now(timezone.utc).isoformat()


@contextmanager
def db():
    Path(settings.runtime_path).parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(settings.runtime_path,timeout=20);c.row_factory=sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    try:
        with c:yield c
    finally:c.close()


@contextmanager
def source():
    c=sqlite3.connect(f'file:{Path(settings.source_path).resolve()}?mode=ro',uri=True)
    c.row_factory=sqlite3.Row
    try:yield c
    finally:c.close()


def init():
    with db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS runs(
            run_id TEXT PRIMARY KEY,case_id TEXT NOT NULL,revision INTEGER NOT NULL,status TEXT NOT NULL,
            depth TEXT NOT NULL DEFAULT 'lightweight',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
            report_json TEXT,error TEXT,tokens INTEGER NOT NULL DEFAULT 0,elapsed REAL,
            parent_run TEXT,review_request TEXT,UNIQUE(case_id,revision));
            CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL,
             at TEXT NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS snapshots(run_id TEXT NOT NULL,evidence_id TEXT NOT NULL,payload TEXT NOT NULL,
             PRIMARY KEY(run_id,evidence_id));
            CREATE TABLE IF NOT EXISTS demo_events(event_id TEXT PRIMARY KEY,case_id TEXT NOT NULL,run_id TEXT NOT NULL,received_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS embeddings(evidence_id TEXT PRIMARY KEY,source_hash TEXT NOT NULL,model TEXT NOT NULL,vector BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,at TEXT NOT NULL,
             actor TEXT NOT NULL,action TEXT NOT NULL,note TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS manager_cases(case_id TEXT PRIMARY KEY,current_run_id TEXT NOT NULL,
             escalation_run_id TEXT NOT NULL,owner TEXT NOT NULL,status TEXT NOT NULL,destination TEXT NOT NULL DEFAULT '',
             closure_reason TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS manager_actions(id TEXT PRIMARY KEY,case_id TEXT NOT NULL,run_id TEXT NOT NULL,
             at TEXT NOT NULL,actor TEXT NOT NULL,action TEXT NOT NULL,note TEXT NOT NULL,owner TEXT NOT NULL,
             destination TEXT NOT NULL,closure_reason TEXT NOT NULL,request_json TEXT NOT NULL,result_json TEXT NOT NULL);
            CREATE TRIGGER IF NOT EXISTS immutable_manager_update BEFORE UPDATE ON manager_actions BEGIN SELECT RAISE(ABORT,'Append-only manager decisions');END;
            CREATE TRIGGER IF NOT EXISTS immutable_manager_delete BEFORE DELETE ON manager_actions BEGIN SELECT RAISE(ABORT,'Append-only manager decisions');END;
            CREATE TABLE IF NOT EXISTS submitted_evidence(evidence_id TEXT PRIMARY KEY,run_id TEXT NOT NULL,
             case_id TEXT NOT NULL,received_at TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS escalation_packets(id TEXT PRIMARY KEY,review_id TEXT NOT NULL UNIQUE,
             run_id TEXT NOT NULL,case_id TEXT NOT NULL,created_at TEXT NOT NULL,payload TEXT NOT NULL,
             pdf_status TEXT NOT NULL DEFAULT 'pending',filename TEXT,sha256 TEXT,pdf_error TEXT,
             recipient TEXT NOT NULL,delivery_status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,
             delivery_error TEXT,sent_at TEXT);
            CREATE TRIGGER IF NOT EXISTS immutable_packet_payload BEFORE UPDATE OF payload,run_id,case_id,review_id ON escalation_packets
             BEGIN SELECT RAISE(ABORT,'Immutable escalation snapshot');END;
            CREATE TRIGGER IF NOT EXISTS immutable_submitted_update BEFORE UPDATE ON submitted_evidence BEGIN SELECT RAISE(ABORT,'Append-only evidence');END;
            CREATE TRIGGER IF NOT EXISTS immutable_submitted_delete BEFORE DELETE ON submitted_evidence BEGIN SELECT RAISE(ABORT,'Append-only evidence');END;
            CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY,run_id TEXT NOT NULL UNIQUE,
             created_at TEXT NOT NULL,status TEXT NOT NULL,recipient TEXT NOT NULL,subject TEXT NOT NULL,
             body TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,error TEXT,sent_at TEXT);
            CREATE TRIGGER IF NOT EXISTS immutable_audit_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'Append-only audit');END;
            CREATE TRIGGER IF NOT EXISTS immutable_audit_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'Append-only audit');END;
        ''')

        if 'queue_priority' not in {r[1] for r in c.execute('PRAGMA table_info(runs)')}:
            c.execute('ALTER TABLE runs ADD COLUMN queue_priority INTEGER NOT NULL DEFAULT 0')
        if 'required_depth' not in {r[1] for r in c.execute('PRAGMA table_info(runs)')}:
            c.execute("ALTER TABLE runs ADD COLUMN required_depth TEXT NOT NULL DEFAULT 'lightweight'")
        c.execute('''INSERT OR IGNORE INTO manager_cases(case_id,current_run_id,escalation_run_id,owner,status,updated_at)
          SELECT r.case_id,r.run_id,r.run_id,?,'awaiting_manager',r.updated_at FROM runs r JOIN
          (SELECT case_id,max(revision) revision FROM runs GROUP BY case_id) latest USING(case_id,revision)
          WHERE r.status='escalated' ''',(settings.surveillance_manager_email or 'Surveillance manager',))


def meta_get(key,default=None):
    with db() as c:r=c.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
    return json.loads(r[0]) if r else default


def meta_set(key,value):
    with db() as c:c.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',(key,json.dumps(value)))


def audit(run_id,kind,payload):
    with db() as c:c.execute('INSERT INTO audit(run_id,at,kind,payload) VALUES (?,?,?,?)',(run_id,now(),kind,json.dumps(payload)))
    from .observability import trace_event
    trace_event(kind,payload)


def ingest(case_id,revision=1,parent_run=None,review_request=None):
    with source() as s:
        if not s.execute('SELECT 1 FROM investigation_cases WHERE case_id=?',(case_id,)).fetchone():raise ValueError('Unknown case')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM runs WHERE case_id=? AND revision=?',(case_id,revision)).fetchone()
        if row:return dict(row),True
        rid=str(uuid4());t=now()
        c.execute('INSERT INTO runs(run_id,case_id,revision,status,created_at,updated_at,parent_run,review_request) VALUES (?,?,?,?,?,?,?,?)',
            (rid,case_id,revision,'queued',t,t,parent_run,review_request))
        c.execute('INSERT INTO audit(run_id,at,kind,payload) VALUES (?,?,?,?)',(rid,t,'case_received',json.dumps({'case_id':case_id,'revision':revision})))
        return dict(c.execute('SELECT * FROM runs WHERE run_id=?',(rid,)).fetchone()),False


def ingest_all():
    with source() as c:ids=[r[0] for r in c.execute('SELECT case_id FROM investigation_cases ORDER BY created_at,case_id')]
    with db() as c:existing={r[0] for r in c.execute('SELECT DISTINCT case_id FROM runs')}
    return sum(not ingest(cid)[1] for cid in ids if cid not in existing)


def claim():
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        r=c.execute("SELECT * FROM runs WHERE status='queued' ORDER BY queue_priority DESC,created_at LIMIT 1").fetchone()
        if not r:return None
        c.execute("UPDATE runs SET status='running',updated_at=? WHERE run_id=?",(now(),r['run_id']))
        return dict(r)


def update(rid,**fields):
    if not set(fields)<={'status','depth','report_json','error','tokens','elapsed'}:raise ValueError('Invalid run field')
    fields['updated_at']=now()
    with db() as c:c.execute('UPDATE runs SET '+','.join(f'{k}=?' for k in fields)+' WHERE run_id=?',(*fields.values(),rid))


def remember(rid,record):
    with db() as c:c.execute('INSERT OR IGNORE INTO snapshots VALUES (?,?,?)',(rid,record['evidence_id'],json.dumps(record)))


def annotate_retrieval(rid,eid,retrieval):
    with db() as c:
        row=c.execute('SELECT payload FROM snapshots WHERE run_id=? AND evidence_id=?',(rid,eid)).fetchone()
        if row:
            payload=json.loads(row[0]);payload['retrieval']=retrieval
            c.execute('UPDATE snapshots SET payload=? WHERE run_id=? AND evidence_id=?',(json.dumps(payload),rid,eid))


def recalled(rid):
    with db() as c:return {r['evidence_id']:json.loads(r['payload']) for r in c.execute('SELECT * FROM snapshots WHERE run_id=?',(rid,))}


def submitted_sources(rid):
    """Only this revision and its same-case ancestors can expose later submissions."""
    with db() as c:
        rows=c.execute('''WITH RECURSIVE lineage(run_id,case_id,parent_run) AS (
          SELECT run_id,case_id,parent_run FROM runs WHERE run_id=?
          UNION SELECT r.run_id,r.case_id,r.parent_run FROM runs r JOIN lineage l
          ON r.run_id=l.parent_run AND r.case_id=l.case_id)
          SELECT e.* FROM submitted_evidence e JOIN lineage l
          ON e.run_id=l.run_id AND e.case_id=l.case_id ORDER BY e.received_at,e.evidence_id''',(rid,)).fetchall()
    return [json.loads(r['payload']) for r in rows]


def details(rid):
    with db() as c:
        r=c.execute('SELECT * FROM runs WHERE run_id=?',(rid,)).fetchone()
        if not r:return None
        result=dict(r)
        result['events']=[dict(e)|{'payload':json.loads(e['payload'])} for e in c.execute('SELECT * FROM audit WHERE run_id=? ORDER BY seq',(rid,))]
        result['reviews']=[dict(e) for e in c.execute('SELECT * FROM reviews WHERE run_id=? ORDER BY at',(rid,))]
        result['notification']=next((dict(n) for n in c.execute('SELECT id,status,recipient,sent_at,error FROM notifications WHERE run_id=?',(rid,))),None)
        result['escalation_packets']=[{'id':p['id'],'pdf_status':p['pdf_status'],'delivery_status':p['delivery_status'],
          'recipient':p['recipient'],'pdf_error':p['pdf_error'],'delivery_error':p['delivery_error'],'sent_at':p['sent_at'],
          'url':f"/api/cases/{p['case_id']}/escalations/{p['id']}.pdf"} for p in c.execute('SELECT * FROM escalation_packets WHERE run_id=? ORDER BY created_at',(rid,))]
        manager=c.execute('SELECT * FROM manager_cases WHERE case_id=? AND current_run_id=?',(r['case_id'],rid)).fetchone()
        result['manager_review']=dict(manager) if manager else None
        result['manager_actions']=[dict(a) for a in c.execute('SELECT id,run_id,at,actor,action,note,owner,destination,closure_reason FROM manager_actions WHERE case_id=? ORDER BY at,id',(r['case_id'],))]
    result['report']=json.loads(result.pop('report_json')) if result['report_json'] else None
    result.pop('report_json',None)
    result['evidence']=list(recalled(rid).values())
    from .demo_identities import display_identities
    return display_identities(result)


def finish(rid,report,tokens,elapsed):
    """Report readiness and notification enqueue commit together; unique run deduplicates."""
    with db() as c:
        r=c.execute('SELECT * FROM runs WHERE run_id=?',(rid,)).fetchone()
        t=now()
        c.execute("UPDATE runs SET status='ready_for_review',report_json=?,tokens=?,elapsed=?,updated_at=? WHERE run_id=?",(json.dumps(report),tokens,elapsed,t,rid))
        c.execute("UPDATE manager_cases SET status='awaiting_analyst',updated_at=?,version=version+1 WHERE current_run_id=? AND status='investigating'",(t,rid))
        url=f'{settings.app_url}/population.html?case={r["case_id"]}'
        body=f'A draft investigation for {r["case_id"]} (revision {r["revision"]}) is ready for your review.\n\nOpen the analyst workspace: {url}\n\nThis is a draft for human review. No disposition has been recorded.\nSynthetic demonstration.'
        c.execute('INSERT OR IGNORE INTO notifications(id,run_id,created_at,status,recipient,subject,body) VALUES (?,?,?,?,?,?,?)',
            (str(uuid4()),rid,t,'pending',settings.analyst_email or 'analyst@demo.local',f'Review ready: {r["case_id"]}',body))
        c.execute('INSERT INTO audit(run_id,at,kind,payload) VALUES (?,?,?,?)',(rid,t,'report_ready',json.dumps({'notification_queued':True,'tokens':tokens})))


def recover():
    with db() as c:ids=[r[0] for r in c.execute("SELECT run_id FROM runs WHERE status='running'")]
    for rid in ids:
        update(rid,status='manual_review',error='Investigation interrupted. Prior evidence and activity are preserved; request a new revision to continue.')
        with db() as c:c.execute("UPDATE manager_cases SET status='awaiting_analyst',updated_at=?,version=version+1 WHERE current_run_id=? AND status='investigating'",(now(),rid))
        audit(rid,'recovery',{'outcome':'manual_review','reason':'Worker interrupted'})
