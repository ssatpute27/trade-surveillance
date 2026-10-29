"""Add a separate fictional Apple desk exchange, preserving the audio's source."""
import json
import sqlite3
from datetime import datetime, timezone

from app.config import settings

CASE_ID = 'CASE-0088C625'
EVIDENCE_ID = 'CHAT-DESK-' + CASE_ID
DIALOGUE = [
    ('2025-05-14T15:30:00.000Z', 'Casey Morgan', 'Trader',
     "We're selling Apple in small clips, but showing three much larger bids at nearby price levels. Keep that buying interest visible while the sells are working."),
    ('2025-05-14T15:30:19.000Z', 'Dana Mercer', 'Trade support',
     "Are those bids intended to execute, or are they part of the hedge routine? The ticket doesn't explain why all three should disappear after each sell."),
    ('2025-05-14T15:30:38.000Z', 'Casey Morgan', 'Trader',
     "The sell executions are the priority. Pull the bids once each sell is done, and use the same sequence for the next clip."),
]


def add(path):
    with sqlite3.connect(path) as db:
        if db.execute('SELECT 1 FROM evidence WHERE evidence_id=?', (EVIDENCE_ID,)).fetchone():
            return False
        orders = db.execute('''SELECT DISTINCT o.order_id,o.account_id FROM case_alerts ca
            JOIN alert_orders ao USING(alert_id) JOIN orders o USING(order_id)
            WHERE ca.case_id=? ORDER BY o.order_id''', (CASE_ID,)).fetchall()
        if not orders:
            raise ValueError('Apple demo case is missing')
        messages = [dict(at=at, sender=sender, role=role, text=text)
                    for at, sender, role, text in DIALOGUE]
        metadata = {
            'origin': 'synthetic', 'channel': 'Desk messaging',
            'thread_id': 'IB-DESK-' + CASE_ID,
            'order_ids': [order[0] for order in orders],
            'participants': ['Casey Morgan', 'Dana Mercer'], 'messages': messages,
            'dataset_version': 'apple-desk-chat-v2',
            'added_at': datetime.now(timezone.utc).isoformat(),
            'limitation': 'Separate authored fictional desk exchange for the same demo scenario. '
                          'Not a transcript of the audio, independently verified evidence, or an actual allegation.',
        }
        text = '\n'.join(f'{at} | {sender} ({role}): {body}' for at,sender,role,body in DIALOGUE)
        db.execute('INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?)', (
            EVIDENCE_ID, 'communication', DIALOGUE[-1][0], DIALOGUE[-1][0],
            '2025-05-14T15:30:39.000Z', 'Desk chat archive', metadata['thread_id'],
            'available', text, json.dumps(metadata)))
        db.executemany('INSERT INTO evidence_scope VALUES (?,?)',
                       [(EVIDENCE_ID, account) for account in sorted({o[1] for o in orders})])
    return True


if __name__ == '__main__':
    print('Separate Apple desk conversation added:', add(settings.source_path))
