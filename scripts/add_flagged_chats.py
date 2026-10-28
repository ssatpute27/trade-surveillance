"""Add clearly concerning fictional dialogue to four selected interview cases."""
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sqlite3
import sys
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from app.config import settings

SCENARIOS={
 'CASE-AF1D9C5F':[
  ('trader','I need that AMZN closing mark higher. The valuation looks awful where it is.'),
  ('support','Are you saying the purpose of the order is to move the closing price? Where is the client instruction?'),
  ('trader',"There isn't one on this ticket. I'm trying to improve the mark. Keep that explanation out of the booking notes.")],
 'CASE-0088C625':[
  ('trader',"Those AAPL bids aren't genuine buying interest. I don't want them filled; I want the book to look stronger while we're selling."),
  ('support',"That is not the approved hedge explanation. We need to preserve this conversation and the order sequence."),
  ('trader',"Just call it inventory management if anyone asks. Don't put what I said about the bids in the ticket.")],
 'CASE-542714B9':[
  ('trader',"The same owner is on both sides of these AAPL trades. The point is to make the activity look busier, not change our exposure."),
  ('support','Then this is not an accidental self-match. Has compliance approved any of this?'),
  ('trader',"No. Put it down as a system cross and leave the common-owner detail out of the explanation.")],
 'CASE-1905FED2':[
  ('trader',"Those two AAPL accounts are coordinating. We want the prints to look like separate demand."),
  ('support',"There is no approved cross instruction attached. I'm not recording these as independent client decisions."),
  ('trader',"They aren't independent. Keep the coordination out of the case notes; it will raise questions.")],
}


def add_flagged(path):
    with sqlite3.connect(path) as c:
        c.row_factory=sqlite3.Row
        added=0
        for cid,dialogue in SCENARIOS.items():
            eid='CHAT-FLAG-'+cid
            if c.execute('SELECT 1 FROM evidence WHERE evidence_id=?',(eid,)).fetchone():continue
            orders=c.execute('''SELECT DISTINCT o.*,t.name trader FROM case_alerts ca JOIN alert_orders ao USING(alert_id)
              JOIN orders o USING(order_id) JOIN traders t USING(trader_id) WHERE ca.case_id=? ORDER BY o.submitted_at,o.order_id''',(cid,)).fetchall()
            if not orders:raise ValueError('Missing case '+cid)
            start=datetime.fromisoformat(orders[0]['submitted_at'].replace('Z','+00:00'))-timedelta(minutes=3)
            stamp=lambda offset:(start+timedelta(seconds=offset)).isoformat(timespec='milliseconds').replace('+00:00','Z')
            messages=[{'at':stamp(i*19),'sender':orders[0]['trader'] if role=='trader' else 'Dana Mercer',
                       'role':'Trader' if role=='trader' else 'Trade support','text':text} for i,(role,text) in enumerate(dialogue)]
            meta={'origin':'synthetic','channel':'Desk messaging','thread_id':'IB-FLAG-'+cid,'order_ids':[o['order_id'] for o in orders],
                  'participants':sorted({m['sender'] for m in messages}),'messages':messages,'dataset_version':'flagged-chat-v1',
                  'added_at':datetime.now(timezone.utc).isoformat(),
                  'limitation':'Authored fictional conversation for this interview scenario. Statements of intent must be corroborated against trading records; not an actual allegation.'}
            text='\n'.join(f'{m["at"]} | {m["sender"]} ({m["role"]}): {m["text"]}' for m in messages)
            c.execute('INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?)',(eid,'communication',stamp(38),stamp(38),stamp(39),'Desk chat archive',meta['thread_id'],'available',text,json.dumps(meta)))
            c.executemany('INSERT INTO evidence_scope VALUES (?,?)',[(eid,aid) for aid in sorted({o['account_id'] for o in orders})])
            added+=1
        return added

if __name__=='__main__':
    folder=ROOT/'data/chat_backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');folder.mkdir(parents=True)
    with sqlite3.connect(settings.source_path) as source,sqlite3.connect(folder/'population.sqlite3') as backup:source.backup(backup)
    print('Concerning conversations added:',add_flagged(settings.source_path))
