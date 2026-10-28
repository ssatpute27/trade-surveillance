"""Archive the current workflow and build a clean rehearsal runtime. Stop services first."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import os
import sqlite3
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from app.config import settings
from app import runtime as rt, chatgpt_cases

DEMO_CASES=('CASE-AF1D9C5F','CASE-0088C625','CASE-52074E40')
COPY_TABLES=('runs','snapshots','submitted_evidence','embeddings','meta')
WORKFLOW_EVENTS=('human_review','demo_followup_request','demo_rehearsal_reset')


def prepare(runtime_path,archive_root):
    """Call only with all app/MCP writers stopped. Never calls AI or email APIs."""
    runtime_path=Path(runtime_path)
    archive=Path(archive_root)/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    archive.mkdir(parents=True,exist_ok=False)
    backup=archive/'agent.sqlite3'
    with sqlite3.connect(runtime_path) as source,sqlite3.connect(backup) as dest:
        if source.execute("SELECT count(*) FROM runs WHERE status IN ('running','queued')").fetchone()[0]:
            raise RuntimeError('Wait for active investigations before preparing the demo')
        source.backup(dest)
    staging=archive/'prepared.sqlite3'
    original_setting=settings.runtime_path
    try:
        settings.runtime_path=str(staging)
        rt.init();chatgpt_cases.init()
        with sqlite3.connect(backup) as source,rt.db() as dest:
            source.row_factory=sqlite3.Row
            for table in COPY_TABLES:
                columns=[r[1] for r in source.execute(f'PRAGMA table_info({table})')]
                names=','.join(columns);marks=','.join('?' for _ in columns)
                dest.executemany(f'INSERT INTO {table} ({names}) VALUES ({marks})',
                                 [tuple(r) for r in source.execute(f'SELECT {names} FROM {table}')])
            # Original reviews, sent-email receipts and manager actions remain in the archive.
            # Preserve investigator history and evidence in the new rehearsal environment.
            for row in source.execute('SELECT run_id,at,kind,payload FROM audit ORDER BY seq'):
                if row['kind'] not in WORKFLOW_EVENTS and not row['kind'].startswith(('manager_','escalation_')):
                    dest.execute('INSERT INTO audit(run_id,at,kind,payload) VALUES (?,?,?,?)',tuple(row))
            latest=list(dest.execute('SELECT r.* FROM runs r JOIN (SELECT case_id,max(revision) revision FROM runs GROUP BY case_id) l USING(case_id,revision)'))
            if not set(DEMO_CASES)<=set(r['case_id'] for r in latest):raise RuntimeError('Demo cases missing')
            reset_at=rt.now()
            for row in latest:
                status='ready_for_review' if row['report_json'] else 'manual_review'
                dest.execute('UPDATE runs SET status=? WHERE run_id=?',(status,row['run_id']))
                dest.execute('INSERT INTO audit(run_id,at,kind,payload) VALUES (?,?,?,?)',
                             (row['run_id'],reset_at,'demo_rehearsal_reset',json.dumps({'archive':str(backup),'prior_status':row['status'],'analyst_decision_pending':True})))
            for cid in DEMO_CASES:
                prior=next(r for r in latest if r['case_id']==cid)
                rid=str(uuid4())
                dest.execute('INSERT INTO runs(run_id,case_id,revision,status,created_at,updated_at,parent_run,queue_priority) VALUES (?,?,?,?,?,?,?,?)',
                             (rid,cid,prior['revision']+1,'awaiting_investigation',reset_at,reset_at,prior['run_id'],100))
                dest.execute('INSERT INTO audit(run_id,at,kind,payload) VALUES (?,?,?,?)',
                             (rid,reset_at,'demo_staged',json.dumps({'case_id':cid,'prior_report_preserved':True,'live_calls_started':False})))
            dest.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',('demo_preparation',json.dumps({'at':reset_at,'archive':str(backup),'staged_cases':DEMO_CASES})))
        with sqlite3.connect(staging) as c:
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        with sqlite3.connect(runtime_path) as c:c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        # No writers may be running during this atomic swap.
        for suffix in ('-wal','-shm'):
            Path(str(runtime_path)+suffix).unlink(missing_ok=True)
        os.replace(staging,runtime_path)
    finally:settings.runtime_path=original_setting
    manifest={'archive':str(backup),'runtime':str(runtime_path),'staged_cases':DEMO_CASES,
              'note':'Original decisions and delivery records are archived. No email was sent or recalled. Reports and source artifacts are retained.'}
    (archive/'manifest.json').write_text(json.dumps(manifest,indent=2))
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--services-stopped',action='store_true',required=True)
    args=parser.parse_args()
    print(json.dumps(prepare(settings.runtime_path,ROOT/'data/demo_backups'),indent=2))
