"""Build only the curated review sample, never the full simulation.

Run from the project root: .venv/bin/python -m scripts.build_data_sample
No API calls or credentials are used. Output files in sample/ are deterministic.
"""
import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'sample'
TABLES = ['desks', 'traders', 'accounts', 'securities', 'sessions', 'mandates', 'orders',
          'order_events', 'fills', 'market_bars', 'market_daily', 'evidence', 'evidence_scope', 'alerts', 'alert_orders']
SYMBOL_MAP={'S-01':'NVDA','S-02':'AAPL','S-03':'MSFT','S-04':'AMZN','S-05':'JPM','S-06':'XOM'}
# Preserve the small sample's relative session roles while moving onto a real earnings window.
DATES={1:'2025-05-01',9:'2025-05-22',10:'2025-05-23',11:'2025-05-27',
       12:'2025-05-28',15:'2025-05-29',16:'2025-05-30'}


def cents(value):
    return int((Decimal(str(value))*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))


def market_snapshot():
    return json.loads((OUT/'market_history.json').read_text())


def reference_price(security_id,day):
    security=next(s for s in market_snapshot()['securities'] if s['symbol']==SYMBOL_MAP[security_id])
    bar=next(b for b in security['bars'] if b['date']==DATES[day])
    return cents(bar['open'])


def stamp(day, time):
    return f'{DATES[day]}T{time}:00Z'


def plus(ts, seconds):
    return (datetime.fromisoformat(ts.replace('Z', '+00:00')) + timedelta(seconds=seconds)).isoformat(timespec='seconds').replace('+00:00', 'Z')


def insert(db, table, **row):
    db.execute(f'INSERT INTO {table} ({",".join(row)}) VALUES ({",".join("?" for _ in row)})', list(row.values()))


def add_order(db, oid, trader, account, security, submitted, quantity, price, parts,
              mandate=None, claimed=None, cancelled=False, amended=False):
    limit = price + (8 if amended else 2)
    insert(db, 'orders', order_id=oid, trader_id=trader, account_id=account,
           security_id=security, submitted_at=submitted, side='buy', original_quantity=quantity,
           limit_price_cents=limit, mandate_id=mandate, claimed_instruction_at=claimed)
    insert(db, 'order_events', event_id=oid+'-E01', order_id=oid, event_type='accepted',
           event_at=plus(submitted, 1), ingested_at=plus(submitted, 2), total_quantity=quantity,
           limit_price_cents=limit)
    if amended:
        # Existing shares are retained; only the limit changes before the second fill.
        insert(db, 'order_events', event_id=oid+'-E02', order_id=oid, event_type='amended',
               event_at=plus(submitted, 110), ingested_at=plus(submitted, 111),
               total_quantity=quantity, limit_price_cents=price+2)
    for i, qty in enumerate(parts):
        at = plus(submitted, 60 + i*120)
        px = price  # Fixed prices make this review sample easy to reconcile by hand.
        insert(db, 'fills', fill_id=f'{oid}-F{i+1:02d}', order_id=oid, executed_at=at,
               ingested_at=plus(at, 2), quantity=qty, price_cents=px,
               venue_id=['VEN-A', 'VEN-B', 'VEN-C'][i % 3])
    end = plus(submitted, 70 + max(len(parts)-1, 0)*120)
    state = 'cancelled' if cancelled else 'filled'
    insert(db, 'order_events', event_id=oid+'-E99', order_id=oid, event_type=state,
           event_at=end, ingested_at=plus(end, 1), total_quantity=quantity,
           limit_price_cents=price+2 if amended else limit)


def add_evidence(db, eid, kind, at, content, accounts, status='available', available=None,
                 source=None, metadata=None):
    available = available or at
    insert(db, 'evidence', evidence_id=eid, kind=kind, event_at=at, available_at=available,
           ingested_at=plus(available, 5), source_system=source or 'Synthetic ' + {
               'communications': 'Message Archive', 'public': 'Public News Snapshot',
               'mandate': 'Document Archive', 'access': 'Access Archive',
               'relationships': 'Approved Directory', 'policy': 'Policy Repository',
           }.get(kind, 'Operations Archive'), source_record_id='SRC-'+eid, status=status,
           content=content, metadata_json=json.dumps({'origin':'synthetic',**(metadata or {})}, sort_keys=True))
    for account in accounts:
        insert(db, 'evidence_scope', evidence_id=eid, account_id=account)


def build(path=None):
    OUT.mkdir(exist_ok=True)
    path = path or OUT / 'review.sqlite3'
    if path.exists():
        path.unlink()  # This script owns this reproducible sample output only.
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript((OUT / 'schema.sql').read_text())
    for row in [('D-01','Event Strategies','Internal risk taking'),
                ('D-02','Portfolio Execution','Institutional agency execution'),
                ('D-03','Client Execution','Institutional agency execution'),
                ('D-04','Liquidity Execution','Internal inventory management')]:
        db.execute('INSERT INTO desks VALUES (?,?,?)', row)
    for row in [('T-01','D-01','Alex Morgan'),('T-02','D-02','Jordan Lee'),
                ('T-03','D-03','Sam Patel'),('T-04','D-04','Riley Chen'),
                ('T-05','D-02','Casey Brooks'),('T-06','D-01','Drew Ellis')]:
        db.execute('INSERT INTO traders VALUES (?,?,?)', row)
    for row in [('A-01','Event Book A','internal','Sector and event strategies'),
                ('A-02','Cedar Pension','institutional','Index tracking portfolio'),
                ('A-03','Elm Asset Management','institutional','Discretionary equity portfolio'),
                ('A-04','Liquidity Book','internal','Inventory management'),
                ('A-05','Birch Insurance','institutional','Periodic portfolio allocation'),
                ('A-06','Event Book B','internal','Sector strategies')]:
        db.execute('INSERT INTO accounts VALUES (?,?,?,?)', row)
    snapshot=market_snapshot()
    market_index={s['symbol']:s for s in snapshot['securities']}
    sectors=['Technology','Technology','Technology','Consumer Discretionary','Financials','Energy']
    securities=[(sid,symbol,market_index[symbol]['name'],sectors[i],'high')
                for i,(sid,symbol) in enumerate(SYMBOL_MAP.items())]
    db.executemany('INSERT INTO securities VALUES (?,?,?,?,?)', securities)
    for sid,symbol in SYMBOL_MAP.items():
        source=market_index[symbol]
        for bar in source['bars']:
            insert(db,'market_daily',security_id=sid,session_date=bar['date'],
                   open_cents=cents(bar['open']),high_cents=cents(bar['high']),
                   low_cents=cents(bar['low']),close_cents=cents(bar['close']),
                   volume_shares=bar['volume'],source_url=source['source_url'],
                   retrieved_at=source['fetched_at'],response_sha256=source['response_sha256'],
                   price_basis=source['price_basis'])
    for day in [9,10,11,12,15]:
        insert(db, 'sessions', session_date=DATES[day], open_at=stamp(day,'13:30'), close_at=stamp(day,'20:00'))
    for args in [('M-731','A-02','S-02',100000,'14:30','15:30',stamp(10,'16:00'),'DOC-731'),
                 ('M-731-02','A-02','S-04',80000,'14:30','15:30',stamp(10,'16:00'),'DOC-731'),
                 ('M-612','A-05','S-05',200000,'14:00','16:00',stamp(11,'11:00'),'DOC-612'),
                 ('M-844','A-03','S-03',50000,'14:00','15:30',stamp(12,'15:10'),'DOC-844')]:
        mid, acct, sec, qty, start, end, signed, doc = args
        insert(db,'mandates',mandate_id=mid,account_id=acct,security_id=sec,side='buy',quantity=qty,
               window_start=stamp(12,start),window_end=stamp(12,end),signed_at=signed,
               ingested_at=plus(signed,30),source_record_id=doc)
    prices = {sid:reference_price(sid,12) for sid in SYMBOL_MAP}
    # Curated ordinary history; deliberately too sparse for a statistical baseline.
    for n in range(12):
        day = [9,10,11][n//4]
        sec = f'S-{n%6+1:02d}'
        participant = n%4+1
        qty = [4000,7000,12000,18000][n%4]
        add_order(db,f'O-{1001+n}',f'T-{participant:02d}',f'A-{participant:02d}',sec,
                  stamp(day,f'{14+n%3:02d}:00'),qty,reference_price(sec,day),
                  [qty//4]*4)
    # Main orders begin shortly before their first execution.
    add_order(db,'O-842','T-01','A-01','S-01',stamp(12,'14:09'),120000,prices['S-01'],[20000,35000,25000,40000])
    add_order(db,'O-843','T-02','A-02','S-02',stamp(12,'14:59'),100000,prices['S-02'],[25000]*4,'M-731',stamp(10,'16:00'))
    add_order(db,'O-844','T-03','A-03','S-03',stamp(12,'14:44'),50000,prices['S-03'],[10000,15000,25000],'M-844',stamp(12,'14:20'))
    # Other large legitimate activity, including another line of the rebalance.
    add_order(db,'O-1013','T-02','A-02','S-04',stamp(12,'14:50'),80000,prices['S-04'],[20000]*4,'M-731-02',stamp(10,'16:00'))
    add_order(db,'O-1014','T-05','A-05','S-05',stamp(12,'14:30'),200000,prices['S-05'],[50000]*4,'M-612',stamp(11,'11:00'))
    add_order(db,'O-1015','T-04','A-04','S-06',stamp(12,'16:10'),10000,prices['S-06'],[2000,3000],cancelled=True)
    add_order(db,'O-1016','T-06','A-06','S-01',stamp(12,'17:10'),8000,prices['S-01'],[],cancelled=True)
    add_order(db,'O-1017','T-04','A-04','S-04',stamp(12,'17:30'),12000,prices['S-04'],[3000]*4,amended=True)
    # Sparse bars at observed fill minutes. A full continuous path comes with the full generator.
    groups = db.execute('''SELECT o.security_id,substr(f.executed_at,1,16)||':00Z' minute_at,
                          min(f.price_cents) low,max(f.price_cents) high,sum(f.quantity) qty
                          FROM fills f JOIN orders o USING(order_id) GROUP BY 1,2''').fetchall()
    for r in groups:
        daily=db.execute('SELECT * FROM market_daily WHERE security_id=? AND session_date=?',
                         (r['security_id'],r['minute_at'][:10])).fetchone()
        own_volume=db.execute('''SELECT sum(f.quantity) FROM fills f JOIN orders o USING(order_id)
                             WHERE o.security_id=? AND substr(f.executed_at,1,10)=?''',
                             (r['security_id'],r['minute_at'][:10])).fetchone()[0]
        insert(db,'market_bars',security_id=r['security_id'],minute_at=r['minute_at'],
               open_cents=r['low'],high_cents=min(r['high']+2,daily['high_cents']),
               low_cents=max(r['low']-2,daily['low_cents']),close_cents=r['high'],
               market_volume_shares=daily['volume_shares']*r['qty']//own_volume//4)
    accounts=['A-01','A-02','A-03','A-04','A-05','A-06']
    add_evidence(db,'E-001','public','2025-05-01T00:00:00Z',
        'NVIDIA announced on 30 April 2025 that its next results were scheduled for 28 May, approximately 13:20 Pacific, with a conference call at 14:00 Pacific. The schedule was public before the sample trading.',accounts,
        source='NVIDIA Investor Relations / public summary',metadata={'origin':'historical_public_summary','source_url':'https://investor.nvidia.com/news/press-release-details/2025/NVIDIA-Sets-Conference-Call-for-First-Quarter-Financial-Results/default.aspx','publication_date':'2025-04-30','timestamp_basis':'conservative next-day availability; exact publication time not asserted'})
    add_evidence(db,'E-002','public','2025-05-29T00:00:00Z',
        'NVIDIA published first-quarter fiscal 2026 results on 28 May 2025, reporting revenue of $44.1 billion. The actual public results provide context for a fictional trading investigation; no misconduct by NVIDIA or its personnel is alleged.',accounts,
        source='NVIDIA Investor Relations / public summary',metadata={'origin':'historical_public_summary','source_url':'https://investor.nvidia.com/news/press-release-details/2025/NVIDIA-Announces-Financial-Results-for-First-Quarter-Fiscal-2026/default.aspx','publication_date':'2025-05-28','timestamp_basis':'conservative next-day availability; exact publication time not asserted'})
    add_evidence(db,'E-003','mandate',stamp(9,'10:00'),
        'Synthetic portfolio allocation notice: Cedar Pension plans to rebalance AAPL and AMZN on 28 May. This is a fictional client instruction, not a claim of an actual index membership change.',['A-02'])
    add_evidence(db,'E-004','communications',stamp(12,'13:35'),
        'Alex to Taylor: Is the blue folder going out after the bell today? Keep the figures away from the desk channel until they are public.',['A-01'],metadata={'sender':'T-01','recipient':'ADV-07'})
    add_evidence(db,'E-005','communications',stamp(12,'13:45'),
        'Alex to execution desk: The public earnings calendar makes this a scheduled event trade in NVDA. Stay within the approved order limit.',['A-01'])
    add_evidence(db,'E-006','communications',stamp(10,'10:00'),
        'Facilities to Alex: The blue folder for the office lease needs a signature. Facilities will collect it next week.',['A-01'])
    add_evidence(db,'E-007','relationships',stamp(9,'12:00'),
        'Fictional bank directory: Taylor Reed is assigned to Project Blue, an internal restricted research project covering NVDA. Alex and Taylor attended a training session on 22 May. The attendance record does not establish what was discussed.',['A-01'],metadata={'person_id':'ADV-07','resource_id':'PROJECT-BLUE','valid_from':stamp(1,'09:00'),'valid_to':None})
    add_evidence(db,'E-008','access',stamp(12,'12:55'),
        'Synthetic bank access extract: Taylor Reed accessed a restricted Project Blue research draft at 12:55 UTC on 28 May. Alex had no direct entitlement or successful access event in the supplied 23-28 May extract. This does not establish access to actual issuer confidential results or any off-system disclosure.',['A-01'],available=stamp(15,'10:00'),metadata={'person_id':'ADV-07','resource_id':'PROJECT-BLUE','access_outcome':'success','coverage_start':stamp(10,'00:00'),'coverage_end':stamp(12,'20:00')})
    add_evidence(db,'E-009','mandate',stamp(10,'16:00'),
        'Signed DOC-731 instructs Cedar Pension to buy 100,000 AAPL and 80,000 AMZN shares on 28 May between 14:30 and 15:30 UTC for a portfolio rebalance.',['A-02'])
    add_evidence(db,'E-010','communications',stamp(12,'14:20'),
        'Jordan to portfolio operations: Execute both lines of the signed DOC-731 portfolio allocation instruction within the approved window.',['A-02'])
    add_evidence(db,'E-011','mandate',stamp(12,'15:10'),
        'DOC-844 / Elm Asset Management: Buy 50,000 MSFT shares on 28 May 2025 within the 14:00-15:30 UTC execution window. Signed by the authorized client representative on 28 May 2025 at 15:10 UTC. Archive version: 1.',['A-03'])
    add_evidence(db,'E-012','communications',stamp(12,'14:25'),
        'Sam to operations: We have verbal approval; the signed copy should follow.',['A-03'])
    add_evidence(db,'E-013','communications',stamp(12,'15:15'),
        'Operations: The DOC-844 attachment timestamp does not match the original order record. Please locate the original approval.',['A-03'])
    add_evidence(db,'E-014','access',stamp(12,'16:00'),
        'Archive coverage failure: MSFT access logs for 28 May 12:00-16:00 UTC are unavailable. This is not a successful query finding no access events.',['A-03'],status='unavailable',available=stamp(15,'11:00'),metadata={'coverage_start':stamp(12,'12:00'),'coverage_end':stamp(12,'16:00'),'reason':'archive_partition_unavailable'})
    add_evidence(db,'E-015','mandate',stamp(11,'11:00'),
        'Signed DOC-612 instructs Birch Insurance to buy 200,000 JPM shares on 28 May between 14:00 and 16:00 UTC for a scheduled portfolio allocation.',['A-05'])
    add_evidence(db,'E-016','communications',plus(stamp(12,'16:12'),50),
        'Riley to operations: Cancel the remaining 5,000 XOM shares after the completed fills.',['A-04'])
    # A future record tests cutoff filtering. It must not be available in the 29 May case.
    add_evidence(db,'E-017','communications',stamp(16,'10:00'),
        'Operations follow-up: Archive restoration is still pending.',['A-03'])
    add_evidence(db,'E-018','personnel',stamp(12,'10:00'),
        'Restricted personnel source; content withheld from surveillance retrieval.',['A-03'],status='access_denied')
    for aid, rule, acct, oid in [('TS-1042','pre_announcement','A-01','O-842'),
                                 ('TS-1043','size_outlier','A-02','O-843'),
                                 ('TS-1044','provenance_conflict','A-03','O-844')]:
        insert(db,'alerts',alert_id=aid,source_event_id='SURV-EVT-'+aid[3:],rule=rule,
               detected_at=stamp(15,'12:05'),cutoff_at=stamp(15,'12:10'),account_id=acct)
        insert(db,'alert_orders',alert_id=aid,order_id=oid)
    db.commit()
    return db


def validate(db):
    checks = {}
    checks['foreign_keys'] = len(db.execute('PRAGMA foreign_key_check').fetchall()) == 0
    errors=[]
    for o in db.execute('SELECT * FROM orders'):
        events=db.execute('SELECT * FROM order_events WHERE order_id=? ORDER BY event_at',(o['order_id'],)).fetchall()
        fills=db.execute('SELECT * FROM fills WHERE order_id=? ORDER BY executed_at',(o['order_id'],)).fetchall()
        running=0
        for f in fills:
            prior=[e for e in events if e['event_at']<=f['executed_at']]
            if not prior or prior[-1]['event_type'] not in ('accepted','amended'):
                errors.append(o['order_id']+': invalid state at fill');continue
            state=prior[-1];running+=f['quantity']
            if running>state['total_quantity'] or f['price_cents']>state['limit_price_cents']:
                errors.append(o['order_id']+': quantity/limit')
            session=db.execute('SELECT * FROM sessions WHERE session_date=?',(f['executed_at'][:10],)).fetchone()
            if not session or not session['open_at']<=f['executed_at']<session['close_at']:
                errors.append(o['order_id']+': session')
            minute=f['executed_at'][:16]+':00Z'
            bar=db.execute('SELECT * FROM market_bars WHERE security_id=? AND minute_at=?',(o['security_id'],minute)).fetchone()
            if not bar or not bar['low_cents']<=f['price_cents']<=bar['high_cents']:
                errors.append(o['order_id']+': market price')
        if events[-1]['event_type']=='filled' and running!=events[-1]['total_quantity']:
            errors.append(o['order_id']+': incomplete terminal fill')
        if events[-1]['event_type']=='cancelled' and running>=events[-1]['total_quantity']:
            errors.append(o['order_id']+': nothing left to cancel')
    checks['lifecycle_quantity_limits_sessions_market_price'] = not errors
    over=db.execute('''SELECT count(*) FROM (SELECT o.security_id,substr(f.executed_at,1,16)||':00Z' minute_at,sum(f.quantity) qty
                       FROM fills f JOIN orders o USING(order_id) GROUP BY 1,2) x
                       JOIN market_bars b USING(security_id,minute_at) WHERE x.qty>b.market_volume_shares''').fetchone()[0]
    checks['market_volume_bounds'] = over==0
    expected={'O-842':120000*reference_price('S-01',12),'O-843':100000*reference_price('S-02',12),'O-844':50000*reference_price('S-03',12)}
    checks['showcase_notionals_reconcile'] = all(db.execute('SELECT sum(quantity*price_cents) FROM fills WHERE order_id=?',(o,)).fetchone()[0]==n for o,n in expected.items())
    checks['intentional_late_mandate_preserved'] = db.execute("SELECT m.signed_at>min(f.executed_at) FROM mandates m JOIN orders o USING(mandate_id) JOIN fills f USING(order_id) WHERE o.order_id='O-844'").fetchone()[0]==1
    checks['fills_within_sourced_daily_range'] = db.execute('''SELECT count(*) FROM fills f JOIN orders o USING(order_id)
         LEFT JOIN market_daily d ON d.security_id=o.security_id AND d.session_date=substr(f.executed_at,1,10)
         WHERE d.security_id IS NULL OR f.price_cents<d.low_cents OR f.price_cents>d.high_cents''').fetchone()[0]==0
    checks['synthetic_volume_within_sourced_daily_volume'] = db.execute('''SELECT count(*) FROM
         (SELECT security_id,substr(minute_at,1,10) session_date,sum(market_volume_shares) volume FROM market_bars GROUP BY 1,2) b
         JOIN market_daily d USING(security_id,session_date) WHERE b.volume>d.volume_shares''').fetchone()[0]==0
    return checks, errors


def visible_evidence(db, account_id, cutoff):
    """Apply scope and all availability times before retrieval, including before ranking."""
    return [dict(r) for r in db.execute('''SELECT e.* FROM evidence e JOIN evidence_scope s USING(evidence_id)
          WHERE s.account_id=? AND e.status!='access_denied' AND e.event_at<=?
          AND e.available_at<=? AND e.ingested_at<=? ORDER BY e.event_at,e.evidence_id''',
          (account_id,cutoff,cutoff,cutoff))]


def export(db):
    data={t:[dict(r) for r in db.execute(f'SELECT * FROM {t} ORDER BY 1')] for t in TABLES}
    checks,errors=validate(db)
    assert all(checks.values()), (checks,errors)
    for table,rows in data.items():
        with (OUT / f'{table}.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]))
            writer.writeheader();writer.writerows(rows)
    payload=json.dumps(data,indent=2,sort_keys=True)
    (OUT / 'review.json').write_text(payload+'\n')
    snapshot=market_snapshot()
    manifest={'dataset_kind':'mixed_public_market_and_synthetic_activity','contains_synthetic_activity':True,'scope':'real securities and sourced daily context; curated simulated activity',
              'counts':{t:len(v) for t,v in data.items()},'checks':checks,
              'market_foundation':{'securities':len(snapshot['securities']),'sessions':len(snapshot['sessions']),
                                   'start':snapshot['sessions'][0],'end':snapshot['sessions'][-1],
                                   'provider':'Yahoo Finance chart','resolution':'daily'},
              'data_sha256':hashlib.sha256(payload.encode()).hexdigest(),
              'limitations':['All sample orders are buys.','Sparse market bars only at fill minutes.',
                             'Simulated fills use the historical daily open as a price anchor, not the actual price at the simulated execution time.',
                             'Minute bars, order books, orders, participants and private evidence are simulated; only daily reference bars and cited public facts are sourced.',
                             'Curated alerts are not generated by a detection engine yet.',
                             'The sample trading history is insufficient for statistical baselines, even though real market history is cached.']}
    (OUT / 'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    template=(OUT / 'review.template.html').read_text()
    # Escape less-than to prevent any source content from terminating the JSON script block.
    packed=json.dumps({'data':data,'manifest':manifest}).replace('<','\\u003c')
    (OUT / 'review.html').write_text(template.replace('__SAMPLE_JSON__',packed))
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':
    db=build()
    try:
        export(db)
    finally:
        db.close()
