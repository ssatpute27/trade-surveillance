"""Read-only readiness check. Does not run agents, submit decisions, or send mail."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from app.config import settings
from app import runtime as rt
from app.quantitative import artifact_folder


def main():
    failures=[]
    def check(label,ok,detail=''):
        print(('PASS' if ok else 'FAIL')+' · '+label+(' · '+detail if detail else ''))
        if not ok:failures.append(label)
    def fetch(route):
        with urllib.request.urlopen(settings.app_url+route,timeout=15) as response:
            return json.load(response)
    try:
        workspace=fetch('/api/workspace');operations=fetch('/api/operations');policies=fetch('/api/policies')
        check('App service',True)
        check('Investigation workers connected',workspace['worker_connected'])
        check('Policy index ready',operations['index_ready'])
        check('Policies available',len(policies['documents'])==8 and all(p['indexed'] for p in policies['documents']))
        counts=operations['counts']
        print('INFO · Current case states · '+json.dumps(counts,sort_keys=True))
        primary=fetch('/api/cases/CASE-AF1D9C5F/investigation')
        if primary['status']=='awaiting_investigation':
            history=fetch('/api/cases/CASE-AF1D9C5F/history')['runs']
            check('Primary demo staged with prior assessment',any(r.get('report') for r in history))
        else:check('Primary demo assessment',bool(primary.get('report')))
    except Exception as e:check('App endpoints',False,type(e).__name__)
    try:
        # Open read-only, including for SQLite integrity checks.
        import sqlite3
        with sqlite3.connect('file:'+settings.runtime_path+'?mode=ro',uri=True) as conn:
            check('Runtime database integrity',conn.execute('PRAGMA quick_check').fetchone()[0]=='ok')
            rows=conn.execute("SELECT run_id,payload FROM snapshots WHERE json_extract(payload,'$.source_type')='quantitative_analysis'").fetchall()
        count=0;valid=True
        for rid,payload in rows:
            for artifact in json.loads(payload).get('artifacts',{}).values():
                count+=1;path=artifact_folder(rid)/artifact['filename']
                valid=valid and path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==artifact['sha256']
        check('Saved analysis integrity',valid and count>0,str(count)+' artifacts')
    except Exception as e:check('Stored evidence checks',False,type(e).__name__)
    try:
        result=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/chatgpt_connection.py'),'status'],capture_output=True,text=True,timeout=20)
        state=json.loads(result.stdout)
        check('Private ChatGPT connection',result.returncode==0 and state.get('healthy') and state.get('ready'))
    except Exception as e:check('Private ChatGPT connection',False,type(e).__name__)
    print('No agents, decisions, or email deliveries were triggered.')
    print('Readiness checks '+('passed.' if not failures else 'need attention.'))
    return bool(failures)


if __name__=='__main__':sys.exit(main())
