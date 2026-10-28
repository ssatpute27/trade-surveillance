"""Correct only the generator's inconsistent mandate-summary window ends.

Preserve before/after hashes and original text. Existing runtime snapshots are untouched.
"""
import hashlib
import re
import sqlite3
from datetime import datetime,timezone
from app.config import settings


def repair():
    c=sqlite3.connect(settings.source_path);c.row_factory=sqlite3.Row
    changed=0
    with c:
        c.execute('CREATE TABLE IF NOT EXISTS source_repairs(evidence_id TEXT,at TEXT,reason TEXT,before_text TEXT,before_hash TEXT,after_hash TEXT,PRIMARY KEY(evidence_id,after_hash))')
        for e in c.execute("SELECT evidence_id,content FROM evidence WHERE kind='mandate'").fetchall():
            match=re.search(r'^Document (M-[0-9]+):.*execution window (\S+) to (\S+)\. Signed',e['content'])
            if not match:continue
            m=c.execute('SELECT * FROM mandates WHERE mandate_id=?',(match[1],)).fetchone()
            if not m or m['window_start']!=match[2]:continue
            if m['window_end']==match[3]:continue
            before=e['content'];after=before[:match.start(3)]+m['window_end']+before[match.end(3):]
            sha=lambda x:hashlib.sha256(x.encode()).hexdigest()
            c.execute('INSERT OR IGNORE INTO source_repairs VALUES (?,?,?,?,?,?)',(e['evidence_id'],datetime.now(timezone.utc).isoformat(),'Align generated summary with authoritative mandate execution window',before,sha(before),sha(after)))
            c.execute('UPDATE evidence SET content=? WHERE evidence_id=?',(after,e['evidence_id']));changed+=1
    c.close();return changed

if __name__=='__main__':print('Mandate summaries corrected:',repair())
