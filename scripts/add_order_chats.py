"""Add fictional order-linked desk chat threads without modifying existing evidence."""
import hashlib
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sqlite3
import sys
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from app.config import settings


def add_threads(path):
    with sqlite3.connect(path) as c:
        c.row_factory=sqlite3.Row
        orders=c.execute('''SELECT DISTINCT o.*,t.name trader,a.name account FROM orders o
          JOIN alert_orders ao USING(order_id) JOIN traders t USING(trader_id) JOIN accounts a USING(account_id)
          ORDER BY o.order_id''').fetchall()
        added=0
        for o in orders:
            eid='CHAT-'+o['order_id'];thread='IB-'+o['order_id']
            if c.execute('SELECT 1 FROM evidence WHERE evidence_id=?',(eid,)).fetchone():continue
            start=datetime.fromisoformat(o['submitted_at'].replace('Z','+00:00'))-timedelta(seconds=75)
            def stamp(seconds):return (start+timedelta(seconds=seconds)).isoformat(timespec='milliseconds').replace('+00:00','Z')
            instruction=f'The ticket references {o["mandate_id"]}; check the document for the authorized window.' if o['mandate_id'] else 'Please check the instruction and any required approvals separately; this chat is not the authorization record.'
            messages=[{'at':stamp(0),'sender':o['trader'],'role':'Trader','text':f'For ticket {o["order_id"]}: {o["side"]} {o["original_quantity"]:,} {o["security_id"]} shares in {o["account"]}. Please check the booking details.'},
                      {'at':stamp(18),'sender':'Dana Mercer','role':'Trade support','text':f'I have {o["account_id"]}, {o["security_id"]}, {o["side"]}, {o["original_quantity"]:,} on the ticket. {instruction}'},
                      {'at':stamp(36),'sender':o['trader'],'role':'Trader','text':f'Thanks. The ticket is set to {o["execution_strategy"]} execution with a {o["order_type"]} order. Keep the order reference on any follow-up so support can reconcile the activity.'}]
            text='\n'.join(f'{m["at"]} | {m["sender"]} ({m["role"]}): {m["text"]}' for m in messages)
            meta={'origin':'synthetic','channel':'Desk messaging','thread_id':thread,'order_ids':[o['order_id']],
                  'participants':sorted({m['sender'] for m in messages}),'messages':messages,
                  'added_at':datetime.now(timezone.utc).isoformat(),'dataset_version':'order-chat-v1',
                  'limitation':'Authored fictional order-coordination conversation. Not proof of authorization, intent or independent corroboration.'}
            c.execute('INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?)',(eid,'communication',stamp(36),stamp(36),stamp(37),'Desk chat archive',thread,'available',text,json.dumps(meta)))
            c.execute('INSERT INTO evidence_scope VALUES (?,?)',(eid,o['account_id']))
            added+=1
        return {'linked_orders':len(orders),'added_threads':added,'message_count':len(orders)*3}

if __name__=='__main__':
    folder=ROOT/'data/chat_backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');folder.mkdir(parents=True)
    with sqlite3.connect(settings.source_path) as c,sqlite3.connect(folder/'population.sqlite3') as backup:c.backup(backup)
    print(json.dumps(add_threads(settings.source_path)))
