import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from .config import settings
from .fixtures import ALERTS, EVIDENCE


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(settings.database_path, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    try:
        with db:
            yield db
    finally:
        db.close()


def init():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS alerts(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, alert_id TEXT NOT NULL, mode TEXT NOT NULL,
          revision INTEGER NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL DEFAULT 'lightweight',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL, report TEXT, error TEXT,
          elapsed REAL, tokens INTEGER NOT NULL DEFAULT 0, UNIQUE(alert_id, mode, revision));
        CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
          timestamp TEXT NOT NULL, type TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS retrieved(job_id TEXT NOT NULL, evidence_id TEXT NOT NULL,
          payload TEXT NOT NULL, PRIMARY KEY(job_id, evidence_id));
        CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY, job_id TEXT NOT NULL,
          timestamp TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, note TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS evaluations(id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'Append-only audit'); END;
        CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'Append-only audit'); END;
        ''')
        for a in ALERTS:
            db.execute('INSERT OR IGNORE INTO alerts VALUES (?,?)', (a['id'], json.dumps(a)))
        for e in EVIDENCE:
            db.execute('INSERT OR IGNORE INTO evidence VALUES (?,?)', (e['id'], json.dumps(e)))


def event(job_id, kind, payload):
    with connect() as db:
        db.execute('INSERT INTO events(job_id,timestamp,type,payload) VALUES (?,?,?,?)',
                   (job_id, now(), kind, json.dumps(payload)))


def ingest(alert_id, mode, revision=1):
    with connect() as db:
        row = db.execute('SELECT * FROM jobs WHERE alert_id=? AND mode=? AND revision=?',
                         (alert_id, mode, revision)).fetchone()
        if row:
            return dict(row), True
        if not db.execute('SELECT id FROM alerts WHERE id=?', (alert_id,)).fetchone():
            raise ValueError('Unknown synthetic alert')
        jid, stamp = str(uuid4()), now()
        db.execute('INSERT INTO jobs(id,alert_id,mode,revision,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',
                   (jid, alert_id, mode, revision, 'queued', stamp, stamp))
        db.execute('INSERT INTO events(job_id,timestamp,type,payload) VALUES (?,?,?,?)',
                   (jid, stamp, 'alert_received', json.dumps({'mode': mode, 'revision': revision})))
        return dict(db.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone()), False


def claim_job():
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
        if not row:
            return None
        db.execute("UPDATE jobs SET status='running',updated_at=? WHERE id=?", (now(), row['id']))
        return dict(row)


def update_job(jid, **fields):
    allowed = {'status', 'stage', 'report', 'error', 'elapsed', 'tokens'}
    if not set(fields) <= allowed:
        raise ValueError('Invalid job field')
    fields['updated_at'] = now()
    with connect() as db:
        db.execute('UPDATE jobs SET '+','.join(f'{k}=?' for k in fields)+' WHERE id=?', [*fields.values(), jid])


def get_job(jid):
    with connect() as db:
        row = db.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone()
        return dict(row) if row else None


def source_records(case_id):
    with connect() as db:
        rows = [json.loads(r[0]) for r in db.execute('SELECT payload FROM evidence')]
    return [r for r in rows if r['case_id'] in (case_id, '*') and r['permission'] == 'surveillance' and r['status'] != 'access_denied']


def remember(jid, rows):
    with connect() as db:
        for r in rows:
            db.execute('INSERT OR IGNORE INTO retrieved VALUES (?,?,?)', (jid, r['id'], json.dumps(r)))


def recalled(jid):
    with connect() as db:
        return [json.loads(r[0]) for r in db.execute('SELECT payload FROM retrieved WHERE job_id=?', (jid,))]


def config_get(key):
    with connect() as db:
        r = db.execute('SELECT value FROM config WHERE key=?', (key,)).fetchone()
        return json.loads(r[0]) if r else None


def config_set(key, value):
    with connect() as db:
        db.execute('INSERT OR REPLACE INTO config VALUES (?,?)', (key, json.dumps(value)))


def recover():
    # A single local worker owns the queue. Never silently repeat an interrupted live run.
    with connect() as db:
        ids = [r[0] for r in db.execute("SELECT id FROM jobs WHERE status='running'")]
        db.execute("UPDATE jobs SET status='manual_review',error='Worker interrupted; request more evidence to start a new revision',updated_at=? WHERE status='running'", (now(),))
    for jid in ids:
        event(jid, 'recovery', {'reason': 'Interrupted job preserved for human review'})


def detail(jid):
    job = get_job(jid)
    if not job:
        return None
    with connect() as db:
        job['alert'] = json.loads(db.execute('SELECT payload FROM alerts WHERE id=?', (job['alert_id'],)).fetchone()[0])
        job['events'] = [dict(r) | {'payload': json.loads(r['payload'])} for r in db.execute('SELECT * FROM events WHERE job_id=? ORDER BY seq', (jid,))]
        job['actions'] = [dict(r) for r in db.execute('SELECT * FROM actions WHERE job_id=? ORDER BY timestamp', (jid,))]
    job['report'] = json.loads(job['report']) if job['report'] else None
    job['evidence'] = recalled(jid)
    return job
