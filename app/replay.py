"""Read-only archive of real completed runs, explicitly labeled as replay."""
import hashlib
import json
from .config import ROOT
from . import runtime as rt

FOLDER=ROOT/'data/replays'

def archive_completed():
    FOLDER.mkdir(parents=True,exist_ok=True)
    with rt.db() as c:ids=[r[0] for r in c.execute('SELECT run_id FROM runs WHERE report_json IS NOT NULL')]
    saved=[]
    for rid in ids:
        data=rt.details(rid)
        payload={'mode':'replay','label':'Recorded live investigation. No new AI calls or email are sent.','recorded_run':data}
        raw=json.dumps(payload,sort_keys=True,indent=2).encode();digest=hashlib.sha256(raw).hexdigest()
        path=FOLDER/(rid+'.json');path.write_bytes(raw);saved.append({'run_id':rid,'case_id':data['case_id'],'sha256':digest})
    (FOLDER/'manifest.json').write_text(json.dumps(saved,indent=2))
    return saved

def list_replays():
    path=FOLDER/'manifest.json';return json.loads(path.read_text()) if path.exists() else []

def load_replay(rid):
    entry=next((x for x in list_replays() if x['run_id']==rid),None)
    if entry is None:raise ValueError('Unknown recorded run')
    raw=(FOLDER/(rid+'.json')).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise ValueError('Recording integrity check failed')
    return json.loads(raw)

if __name__=='__main__':print(json.dumps(archive_completed(),indent=2))
