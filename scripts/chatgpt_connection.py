"""Operate the existing private ChatGPT connection without exposing local credentials."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.config import ROOT,settings

p=argparse.ArgumentParser();p.add_argument('action',choices=['start','status','doctor']);args=p.parse_args()
binary=str(ROOT/'tools/tunnel-client/tunnel-client')
env=os.environ.copy();env['CONTROL_PLANE_API_KEY']=settings.openai_api_key
if args.action=='start':
    command=[binary,'runtimes','connect','--alias','trade-surveillance','--profile','trade-surveillance',
      '--tunnel-id','tunnel_6ad6e29487308191a3414d9d4ae5c3d8','--runtime-api-key','env:CONTROL_PLANE_API_KEY',
      '--mcp-command',str(ROOT/'.venv/bin/python')+' '+str(ROOT/'scripts/run_chatgpt_mcp.py'),'--json']
elif args.action=='status':command=[binary,'runtimes','status','trade-surveillance','--json']
else:command=[binary,'doctor','--profile','trade-surveillance','--explain']
r=subprocess.run(command,env=env,capture_output=True,text=True,timeout=60)
if args.action=='doctor':
    print('Connection doctor:', 'passed' if r.returncode==0 else 'failed')
else:
    try:
        data=json.loads(r.stdout)
        print(json.dumps({k:data.get(k) for k in ('alias','process_running','healthy','ready','runtime_state','remote_error')},indent=2))
    except ValueError:print('Connection command did not return valid status. Inspect the local tunnel-client configuration.')
if r.returncode:print('Command failed; exit code',r.returncode)
sys.exit(r.returncode)
