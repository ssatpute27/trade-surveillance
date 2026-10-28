"""Reproducible synthetic broker activity anchored to cached daily market data.

No network calls or model calls. Truth keys are written outside source data.
Intraday paths and order books are simulated, never represented as observations.
"""
import argparse
import csv
import hashlib
import json
import math
import random
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from scripts.build_data_sample import cents

ROOT=Path(__file__).resolve().parent.parent
FAMILIES=['spoofing_layering','pre_announcement','front_running','wash_self_trade',
          'marking_close','coordinated_trading','size_outlier','authorization_restriction']
TABLES=['desks','traders','accounts','securities','sessions','market_daily','market_bars',
        'orders','order_events','fills','opening_positions','account_ownership',
        'mandates','venue_orders','book_snapshots','customer_instructions','execution_matches',
        'restrictions','public_events','evidence','evidence_scope','alerts','alert_orders','alert_features','policies',
        'investigation_cases','case_alerts']


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')


def dt(s):
    return datetime.fromisoformat(s.replace('Z','+00:00'))


def put(db,table,**row):
    db.execute(f'INSERT INTO {table} ({",".join(row)}) VALUES ({",".join("?" for _ in row)})',list(row.values()))


class Population:
    def __init__(self,path,seed=1042):
        self.path=path
        self.rng=random.Random(seed)
        self.seed=seed
        self.db=sqlite3.connect(path)
        self.db.row_factory=sqlite3.Row
        self.db.executescript((ROOT/'sample/schema.sql').read_text())
        self.db.executescript((ROOT/'scripts/population_schema.sql').read_text())
        self.db.execute('PRAGMA synchronous=NORMAL')
        self.source=json.loads((ROOT/'sample/market_history.json').read_text())
        self.days=self.source['sessions']
        self.symbols=[s['symbol'] for s in self.source['securities']]
        self.price={}
        self.volume={}
        self.used=defaultdict(int)
        self.inventory=defaultdict(lambda:20000)
        self.order_seq=0
        self.fill_seq=0
        self.evidence_seq=0
        self.truth=[]
        self.catalog=[]
        self.background_mode=False

    def setup(self):
        for i,(name,business) in enumerate([('Event Strategies','internal'),('Portfolio Execution','institutional'),('Client Execution','institutional'),('Liquidity Management','internal')]):
            self.db.execute('INSERT INTO desks VALUES (?,?,?)',(f'D-{i+1:02}',name,business))
        from app.demo_identities import TRADER_NAMES,ACCOUNT_NAMES
        for i,name in enumerate(TRADER_NAMES):
            self.db.execute('INSERT INTO traders VALUES (?,?,?)',(f'T-{i+1:02}',f'D-{i//6+1:02}',name))
        for i in range(40):
            aid=f'A-{i+1:02}'
            internal=i<16
            self.db.execute('INSERT INTO accounts VALUES (?,?,?,?)',(aid,ACCOUNT_NAMES[i],
                'internal' if internal else 'institutional','Inventory and event strategies' if internal else 'Diversified equity allocation'))
            group='OWNER-01' if i in (0,8) else f'OWNER-{i+1:02}'
            self.db.execute('INSERT INTO account_ownership VALUES (?,?,?,?,?)',(aid,group,group,self.days[0]+'T00:00:00.000Z',None))
        sectors={'AAPL':'Technology','MSFT':'Technology','NVDA':'Technology','AMZN':'Consumer Discretionary','GOOGL':'Communication Services',
                 'META':'Communication Services','TSLA':'Consumer Discretionary','AMD':'Technology','AVGO':'Technology','ORCL':'Technology',
                 'JPM':'Financials','BAC':'Financials','GS':'Financials','MS':'Financials','V':'Financials','MA':'Financials',
                 'XOM':'Energy','CVX':'Energy','UNH':'Health Care','JNJ':'Health Care','PFE':'Health Care','LLY':'Health Care',
                 'WMT':'Consumer Staples','COST':'Consumer Staples','HD':'Consumer Discretionary','PG':'Consumer Staples','KO':'Consumer Staples',
                 'CAT':'Industrials','GE':'Industrials','DIS':'Communication Services'}
        for s in self.source['securities']:
            self.db.execute('INSERT INTO securities VALUES (?,?,?,?,?)',(s['symbol'],s['symbol'],s['name'],sectors[s['symbol']],'large_cap'))
            for b in s['bars']:
                if b['date'] in self.days:
                    self.db.execute('INSERT INTO market_daily VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                        (s['symbol'],b['date'],cents(b['open']),cents(b['high']),cents(b['low']),cents(b['close']),b['volume'],
                         s['source_url'],s['fetched_at'],s['response_sha256'],s['price_basis']))
        for day in self.days:
            opening=datetime.fromisoformat(day+'T09:30:00').replace(tzinfo=ZoneInfo('America/New_York'))
            self.db.execute('INSERT INTO sessions VALUES (?,?,?)',(day,iso(opening),iso(opening+timedelta(minutes=390))))
        for a in range(1,41):
            for s in self.symbols:
                self.db.execute('INSERT INTO opening_positions VALUES (?,?,?,?)',(f'A-{a:02}',s,20000,self.days[0]+'T00:00:00.000Z'))
        self.db.execute('INSERT INTO public_events VALUES (?,?,?,?,?,?,?)',('PUB-NVDA-0528','NVDA','earnings','2025-05-28T20:20:00.000Z','2025-05-01T00:00:00.000Z',
            'https://investor.nvidia.com/news/press-release-details/2025/NVIDIA-Sets-Conference-Call-for-First-Quarter-Financial-Results/default.aspx','approximately scheduled; not an asserted exact release timestamp'))
        for fid in FAMILIES:
            content=('All alerts require trade and historical-context checks, relevant policy consultation and human disposition. '
                'A pattern is not proof of misconduct. Test alternative explanations and preserve contradictory evidence. '
                'Use account scope and time cutoffs before search. Unavailable evidence cannot establish absence. ')
            specific={
                'spoofing_layering':'Compare displayed orders, opposite-side fills and cancellations over repeated cycles. Repricing, hedging and volatility may explain cancellations. Cancellation rate alone is insufficient.',
                'pre_announcement':'Distinguish public event schedules and public research from nonpublic results. Test access/relationship leads. A restricted research project does not itself establish issuer confidential information.',
                'front_running':'Compare receipt of customer instructions, knowledge/access, principal trading and documented hedging consent. Timing alone does not establish knowledge or misconduct.',
                'wash_self_trade':'Check beneficial ownership, control, matched executions and independent decision making. A single accidental cross is not proof of manipulative intent.',
                'marking_close':'Examine final-minute participation, price context, positions and benchmark mandates. Closing-auction participation and index tracking may be legitimate.',
                'coordinated_trading':'Examine repeated matched trades, account relationships and authorized cross instructions. Matching sizes and times alone do not establish improper coordination.',
                'size_outlier':'Use earlier comparable parent orders with cohort and sample count. Verify dated mandates, side, security, quantity and execution window.',
                'authorization_restriction':'Compare execution, instruction receipt, signature, effective restrictions and recorded exceptions. This fictional bank permits verbal client instructions when a pre-execution recording and supervisor acknowledgment exist and the signature follows within one business day. Missing authority records require human attention. A later signature alone does not establish earlier approval.'}[fid]
            self.db.execute('INSERT INTO policies VALUES (?,?,?,?)',('POL-'+fid,'demo-v1',self.days[0],content+specific))
        self.db.commit()

    def market(self):
        rows=[]
        for daily in self.db.execute('SELECT * FROM market_daily ORDER BY session_date,security_id'):
            day,s=daily['session_date'],daily['security_id']
            op,hi,lo,cl=[daily[k] for k in ['open_cents','high_cents','low_cents','close_cents']]
            # A deterministic conditioned path, NOT recovered intraday observations.
            early=self.rng.randint(55,140);late=self.rng.randint(220,335)
            extremal=[lo,hi] if self.rng.random()<.5 else [hi,lo]
            anchors=[(0,op),(early,extremal[0]),(late,extremal[1]),(390,cl)]
            path=[]
            for m in range(391):
                j=next((j for j in range(3) if anchors[j][0]<=m<=anchors[j+1][0]),2)
                a,b=anchors[j],anchors[j+1];frac=(m-a[0])/(b[0]-a[0])
                noise=math.sin(math.pi*frac)*self.rng.gauss(0,max(1,(hi-lo)*.025))
                path.append(max(lo,min(hi,round(a[1]+frac*(b[1]-a[1])+noise))))
            weights=[1+2.2*math.exp(-m/28)+3*math.exp(-(389-m)/24) for m in range(390)]
            total=sum(weights);vols=[int(daily['volume_shares']*w/total) for w in weights]
            vols[-1]+=daily['volume_shares']-sum(vols)
            opening=dt(self.db.execute('SELECT open_at FROM sessions WHERE session_date=?',(day,)).fetchone()[0])
            for m in range(390):
                t=iso(opening+timedelta(minutes=m))
                opening_px,closing_px=path[m],path[m+1]
                high=min(hi,max(opening_px,closing_px)+self.rng.randint(0,2))
                low=max(lo,min(opening_px,closing_px)-self.rng.randint(0,2))
                rows.append((s,t,opening_px,high,low,closing_px,vols[m]))
                self.price[(day,s,m)]=opening_px
                self.volume[(day,s,m)]=vols[m]
            if len(rows)>=23400:
                self.db.executemany('INSERT INTO market_bars VALUES (?,?,?,?,?,?,?)',rows);rows=[]
        if rows:self.db.executemany('INSERT INTO market_bars VALUES (?,?,?,?,?,?,?)',rows)
        self.db.commit()

    def time(self,day,minute,seconds=0):
        opening=self.db.execute('SELECT open_at FROM sessions WHERE session_date=?',(day,)).fetchone()[0]
        return dt(opening)+timedelta(minutes=minute,seconds=seconds)

    def order(self,day,s,account,trader,side,minutes,quantities=None,partial=False,cancel=False,amend=False,strategy='manual',otype='limit',second=10):
        self.order_seq+=1;oid=f'O-{self.order_seq:07}'
        # Budget all broker executions to <=35% of simulated minute market volume.
        qs=[]
        for m in minutes:
            key=(day,s,m)
            cap=max(0,int(self.volume[key]*.35)-self.used[key])
            desired=quantities[len(qs)] if quantities else max(1,round(self.rng.lognormvariate(5.2,.65)))
            qty=min(desired,cap)
            if side=='sell':qty=min(qty,max(0,self.inventory[(account,s)]-(5000 if self.background_mode else 0)))
            if qty<=0:raise ValueError(f'No execution budget for {key}')
            qs.append(qty);self.used[key]+=qty
            self.inventory[(account,s)]+=qty if side=='buy' else -qty
        total=sum(qs)+(max(100,sum(qs)//2) if partial else 0)
        if cancel:total=max(500,total)
        prices=[self.price[(day,s,m)] for m in minutes] or [self.price[(day,s,100)]]
        cushion=max(5,round(prices[0]*.01))
        limit=prices[0]+cushion if side=='buy' else max(1,prices[0]-cushion)
        if any((p>limit if side=='buy' else p<limit) for p in prices):
            otype='market'
        if otype=='market':
            cushion=max(5,round(prices[0]*.10))
            limit=prices[0]+cushion if side=='buy' else max(1,prices[0]-cushion)
        at=self.time(day,min(minutes) if minutes else 100,second-5)
        put(self.db,'orders',order_id=oid,trader_id=trader,account_id=account,security_id=s,submitted_at=iso(at),side=side,
            original_quantity=total,limit_price_cents=limit,mandate_id=None,claimed_instruction_at=None,order_type=otype,execution_strategy=strategy,
            price_limit_role='internal_protection' if otype=='market' else 'order_limit')
        self.db.execute('INSERT INTO order_events VALUES (?,?,?,?,?,?,?)',(oid+'-A',oid,'accepted',iso(at+timedelta(milliseconds=5)),iso(at+timedelta(milliseconds=20)),total,limit))
        fs=[]
        for i,(m,q,p) in enumerate(zip(minutes,qs,prices)):
            self.fill_seq+=1;fid=f'F-{self.fill_seq:08}'
            when=self.time(day,m,second)
            self.db.execute('INSERT INTO fills VALUES (?,?,?,?,?,?,?)',(fid,oid,iso(when),iso(when+timedelta(milliseconds=self.rng.randint(10,400))),q,p,self.rng.choice(['SIM-LIT-A','SIM-LIT-B','SIM-ATS'])))
            fs.append(fid)
            if amend and i==0:
                limit+=1 if side=='buy' else -1
                self.db.execute('INSERT INTO order_events VALUES (?,?,?,?,?,?,?)',(oid+'-U',oid,'amended',iso(when+timedelta(milliseconds=500)),iso(when+timedelta(milliseconds=520)),total,limit))
        terminal=self.time(day,max(minutes) if minutes else 100,second+2)
        self.db.execute('INSERT INTO order_events VALUES (?,?,?,?,?,?,?)',(oid+'-Z',oid,'cancelled' if partial or cancel else 'filled',iso(terminal),iso(terminal+timedelta(milliseconds=20)),total,limit))
        return oid,fs

    def evidence(self,kind,at,content,accounts,status='available',meta=None):
        self.evidence_seq+=1;eid=f'E-{self.evidence_seq:06}'
        put(self.db,'evidence',evidence_id=eid,kind=kind,event_at=iso(at),available_at=iso(at),ingested_at=iso(at+timedelta(seconds=1)),
            source_system='Simulated '+kind.replace('_',' ').title(),source_record_id='SRC-'+eid,status=status,content=content,
            metadata_json=json.dumps({'origin':'synthetic',**(meta or {})},sort_keys=True))
        self.db.executemany('INSERT INTO evidence_scope VALUES (?,?)',[(eid,a) for a in accounts])
        return eid

    def mandate(self,oid,signed_offset=-86400):
        o=self.db.execute('SELECT * FROM orders WHERE order_id=?',(oid,)).fetchone()
        signed=dt(o['submitted_at'])+timedelta(seconds=signed_offset)
        end=self.db.execute('SELECT max(executed_at) FROM fills WHERE order_id=?',(oid,)).fetchone()[0]
        window_end=iso(dt(end)+timedelta(minutes=5))
        mid='M-'+oid[2:]
        self.db.execute('INSERT INTO mandates VALUES (?,?,?,?,?,?,?,?,?,?)',(mid,o['account_id'],o['security_id'],o['side'],o['original_quantity'],
            o['submitted_at'],window_end,iso(signed),iso(signed+timedelta(seconds=5)),'DOC-'+mid))
        self.db.execute('UPDATE orders SET mandate_id=?,claimed_instruction_at=? WHERE order_id=?',(mid,iso(dt(o['submitted_at'])-timedelta(minutes=2)),oid))
        self.db.execute('INSERT INTO customer_instructions VALUES (?,?,?,?,?,?)',('CI-'+oid,oid,iso(dt(o['submitted_at'])-timedelta(minutes=2)),iso(signed),'signed_document','DOC-'+mid))
        return self.evidence('mandate',signed,f'Document {mid}: {o["side"]} {o["original_quantity"]:,} {o["security_id"]} shares for {o["account_id"]}; execution window {o["submitted_at"]} to {window_end}. Signed {iso(signed)}.',[o['account_id']])

    def scenarios(self):
        # Four episodes of each review variant per family. Keys stay outside source data.
        for family in FAMILIES:
            for episode in range(12):
                variant=episode%3
                repeat=episode//3
                expected=['concerning','plausibly_explained','inconclusive'][variant]
                day=self.days[-16+episode]
                if family=='pre_announcement':day='2025-05-28'
                s={'spoofing_layering':['NVDA','AAPL','MSFT','AMZN'],'pre_announcement':['NVDA']*4,
                   'front_running':['AAPL','MSFT','AMZN','NVDA'],'wash_self_trade':['MSFT','AAPL','AMZN','NVDA'],
                   'marking_close':['AMZN','AAPL','MSFT','NVDA'],'coordinated_trading':['AAPL','MSFT','AMZN','NVDA'],
                   'size_outlier':['NVDA','AAPL','MSFT','AMZN'],'authorization_restriction':['MSFT','AAPL','AMZN','JPM']}[family][repeat]
                account_index=episode+1
                a=f'A-{account_index:02}'
                trader_index=(episode%6+1) if account_index<=8 else (19+episode%6)
                tr=f'T-{trader_index:02}'
                orders=[];eids=[]
                start=70+variant*40+repeat*12
                if family=='spoofing_layering':
                    for cycle in range(3):
                        minute=start+cycle*4
                        other,fs=self.order(day,s,a,tr,'sell',[minute],[300]);orders.append(other)
                        fill=self.db.execute('SELECT * FROM fills WHERE fill_id=?',(fs[0],)).fetchone();px=fill['price_cents'];t=dt(fill['executed_at'])
                        for level in range(3):
                            quote,_=self.order(day,s,a,tr,'buy',[],cancel=True);orders.append(quote)
                            # Reset empty-order lifecycle onto the subsecond episode window.
                            submitted=t-timedelta(milliseconds=900-level*40);cancelled=t+timedelta(milliseconds=100+level*30)
                            self.db.execute('UPDATE orders SET submitted_at=?,original_quantity=15000,limit_price_cents=? WHERE order_id=?',(iso(submitted),px-level-1,quote))
                            self.db.execute("UPDATE order_events SET event_at=?,ingested_at=?,total_quantity=15000,limit_price_cents=? WHERE event_id=?",(iso(submitted+timedelta(milliseconds=5)),iso(submitted+timedelta(milliseconds=10)),px-level-1,quote+'-A'))
                            self.db.execute("UPDATE order_events SET event_at=?,ingested_at=?,total_quantity=15000,limit_price_cents=? WHERE event_id=?",(iso(cancelled),iso(cancelled+timedelta(milliseconds=10)),px-level-1,quote+'-Z'))
                            self.db.execute('INSERT INTO venue_orders VALUES (?,?,?,?,?,?,?,?,?,?)',('VO-'+quote,quote,'SIM-LIT-A',iso(submitted),iso(submitted+timedelta(milliseconds=5)),iso(cancelled),'buy',px-level-1,15000,0))
                        for j,offset in enumerate([-1,0,1]):
                            self.db.execute('INSERT INTO book_snapshots VALUES (?,?,?,?,?,?,?,?)',(f'B-{other}-{j}',s,iso(t+timedelta(seconds=offset)),'SIM-LIT-A',px-1,46000 if j<2 else 1000,px+1,1200))
                    if variant==0:
                        text='Operator to strategy support: The bid stack came off as soon as our sell completed again. Keep the execution timestamps for review.'
                    elif variant==1:
                        text='Approved risk ticket: this strategy withdraws bids when its inventory hedge sells complete. The same cancellation linkage operated throughout the preceding week. Review the full sequence before attributing intent.'
                    else:text='Strategy-support log partition covering the three order cycles is unavailable. The order feed is complete, but rationale and configuration records need restoration.'
                    eids.append(self.evidence('strategy_log',self.time(day,start+10),text,[a],status='unavailable' if variant==2 else 'available'))
                elif family=='pre_announcement':
                    oid,_=self.order(day,s,a,tr,'buy',list(range(start,start+6)),[3000]*6);orders.append(oid)
                    schedule=self.evidence('public_news',dt('2025-05-01T00:00:00Z'),'NVIDIA publicly scheduled 28 May 2025 results for approximately 13:20 Pacific. A scheduled earnings event is public information.',[a],meta={'origin':'historical_public_summary','source_url':'https://investor.nvidia.com/news/press-release-details/2025/NVIDIA-Sets-Conference-Call-for-First-Quarter-Financial-Results/default.aspx'})
                    eids.append(schedule)
                    eids.append(self.evidence('public_news',dt('2025-05-29T00:00:00Z'),'NVIDIA published first-quarter fiscal 2026 results on 28 May 2025. Publication date is verified; next-day availability is a conservative bound, not a precise release timestamp.',[a],meta={'origin':'historical_public_summary','source_url':'https://investor.nvidia.com/news/press-release-details/2025/NVIDIA-Announces-Financial-Results-for-First-Quarter-Fiscal-2026/default.aspx'}))
                    if variant==0:
                        eids.append(self.evidence('communication',self.time(day,start-8),'Trader to research colleague: Does the blue folder go public after the bell? Keep the figures out of the desk channel until then.',[a]))
                        eids.append(self.evidence('access',self.time(day,start-12),'Bank research colleague opened a restricted internal NVDA research draft. The draft is bank research, and the access extract does not establish possession of issuer confidential results. Trader has no direct entitlement.',[a]))
                        eids.append(self.evidence('communication',self.time(day,start-7),'Facilities: The blue folder for the office move also needs sign-off. Please collect it tomorrow.',[a]))
                    elif variant==1:
                        eids.append(self.mandate(oid,-172800))
                        eids.append(self.evidence('strategy_log',self.time(day,start-15),'Dated strategy authorization: the NVDA allocation was approved two days earlier using the public earnings calendar and portfolio risk limits. No nonpublic result figures are included.',[a]))
                    else:eids.append(self.evidence('archive_coverage',self.time(day,start-15),'Communications archive for this trader and trading window is unavailable. A targeted review cannot be completed.',[a],status='unavailable'))
                elif family=='front_running':
                    oid,_=self.order(day,s,a,tr,'buy',[start,start+1],[400,400]);orders.append(oid)
                    client=f'A-{17+episode:02}'
                    customer,_=self.order(day,s,client,'T-07','buy',list(range(start+5,start+13)),[2500]*8);orders.append(customer)
                    received=self.time(day,start-10)
                    self.db.execute('INSERT INTO customer_instructions VALUES (?,?,?,?,?,?)',('CI-'+customer,customer,iso(received),iso(received),'recorded_call','CALL-'+customer))
                    if variant==0:
                        text=f'Access record: {tr} opened the pending customer block instruction ten minutes before the principal order. No customer hedging consent is attached to that instruction.'
                    elif variant==1:text='Recorded customer instruction authorizes a disclosed principal hedge ahead of the block execution. Risk approval and the hedge-to-client allocation link are attached; compliance must verify the applicable exception.'
                    else:text='Access audit partition for pending customer instructions is unavailable. The receipt timestamp is known; who viewed it cannot be established.'
                    eids.append(self.evidence('customer_order_access',self.time(day,start+14),text,[a,client],status='unavailable' if variant==2 else 'available',meta={'instruction_received_at':iso(received)}))
                elif family in ('wash_self_trade','coordinated_trading'):
                    left,right=('A-01','A-09') if family=='wash_self_trade' else (f'A-{4+variant:02}',f'A-{12+variant:02}')
                    a=left
                    for c in range(3):
                        minute=start+c*3
                        buy,bf=self.order(day,s,left,'T-04','buy',[minute],[120]);sell,sf=self.order(day,s,right,'T-19','sell',[minute],[120])
                        orders.extend([buy,sell])
                        when=self.db.execute('SELECT executed_at FROM fills WHERE fill_id=?',(bf[0],)).fetchone()[0]
                        self.db.execute('INSERT INTO execution_matches VALUES (?,?,?,?,?)',('MATCH-'+bf[0],bf[0],sf[0],when,'CROSS-APPROVED' if variant==1 else None))
                    if variant==0:text='Operations: Three matched executions repeat across these accounts. Retain the operator instruction and account-control records. No approved crossing instruction is attached.'
                    elif variant==1:text=('Independent strategy logs document an accidental self-match; the prevention-control exception and remediation ticket are attached.' if family=='wash_self_trade' else 'Both clients signed the negotiated-cross instruction before execution. The matching engine records the approved cross reference on all three trades.')
                    else:text='The order records show repeated matched executions. The relevant strategy communications and account-control certification are unavailable.'
                    eids.append(self.evidence('crossing_records',self.time(day,start+8),text,[left,right],status='unavailable' if variant==2 else 'available'))
                elif family=='marking_close':
                    oid,_=self.order(day,s,a,tr,'buy',[385,386,387,388,389],[int(self.volume[(day,s,m)]*.20) for m in range(385,390)]);orders.append(oid)
                    if variant==0:text='Trader to desk: The closing print matters for the month-end valuation. Keep our buys concentrated into the final minutes. Preserve this message for supervisor review.'
                    elif variant==1:
                        eids.append(self.mandate(oid,-172800));text='Portfolio mandate: target the closing benchmark to align fund subscriptions. The execution schedule was approved two days earlier; a high final-minute participation rate is expected.'
                    else:text='Final-minute trade records are available, but the benchmark instruction and valuation-position extract are unavailable.'
                    eids.append(self.evidence('communication',self.time(day,370),text,[a],status='unavailable' if variant==2 else 'available'))
                elif family=='size_outlier':
                    oid,_=self.order(day,s,a,tr,'buy',list(range(start,start+10)),[3000]*10);orders.append(oid)
                    if variant==0:text='Operations query: no portfolio instruction or documented strategy change was found in the supplied mandate index for this order. Ask the desk to supply its authorization.'
                    elif variant==1:
                        eids.append(self.mandate(oid,-172800));text='The client allocation document specifies this security, direction, quantity and execution window. It was signed two days before the order.'
                    else:text='Two mandate versions disagree on quantity. The original signed attachment is unavailable; do not infer approval from the later metadata.'
                    eids.append(self.evidence('mandate_index',self.time(day,start-5),text,[a],status='unavailable' if variant==2 else 'available'))
                else:
                    client=f'A-{29+episode:02}';a=client
                    oid,_=self.order(day,s,client,'T-13','buy',[start,start+1,start+2],[300]*3);orders.append(oid)
                    eids.append(self.mandate(oid,900))
                    if variant==0:text='Order authorization review: execution preceded the signed instruction. No earlier approval is present in the supplied records. Request original client authorization.'
                    elif variant==1:text='Recorded call received before execution contains explicit verbal client authorization. Internal demo policy permits documented verbal orders pending a later signature; call ID and supervisor acknowledgment are attached.'
                    else:
                        self.db.execute('INSERT INTO restrictions VALUES (?,?,?,?,?,?)',('R-'+oid,s,client,iso(self.time(day,0)),iso(self.time(day,389,59)),'Internal restricted-security control'))
                        text='Restricted-security exception archive is unavailable for this account and execution window. The restriction was effective before execution; an exception cannot be verified.'
                    eids.append(self.evidence('authorization_record',self.time(day,start-8),text,[client],status='unavailable' if variant==2 else 'available'))
                self.truth.append({'family':family,'variant':expected,'order_ids':orders,'account_id':a,'evidence_ids':eids,
                    'grading_note':'Expected investigative route, not a legal finding. Escalation requires calibrated language and human review.'})
                self.catalog.append({'family':family,'day':day,'symbol':s,'orders':orders,'account_id':a})
        self.db.commit()

    def background(self,target_orders,target_fills):
        remaining=target_orders-self.order_seq
        zero=remaining//20
        active=remaining-zero
        needed=target_fills-self.fill_seq
        base,extra=divmod(needed,active)
        if not 2<=base<=6:raise ValueError('Unexpected population fill distribution')
        # Reserve opening inventory for small scenario sells rather than using future buys.
        self.inventory=defaultdict(lambda:20000)
        self.background_mode=True
        for n in range(remaining):
            day=self.days[min(len(self.days)-1,n*len(self.days)//remaining)]
            desk=self.rng.randrange(4);tr=f'T-{desk*6+self.rng.randrange(6)+1:02}'
            pool=[range(1,9),range(17,29),range(29,41),range(9,17)][desk]
            account=f'A-{self.rng.choice(pool):02}'
            s=self.rng.choice(self.symbols)
            iszero=n%20==0 and zero>0
            if iszero:zero-=1
            count=0 if iszero else base+(extra>0)
            if count and extra>0:extra-=1
            side=self.rng.choice(['buy','sell'])
            if self.inventory[(account,s)]<5000+count*1000:side='buy'
            strategy=self.rng.choices(['manual','VWAP','TWAP','participation'],[.3,.35,.2,.15])[0]
            minute=self.rng.choices([self.rng.randrange(5,45),self.rng.randrange(45,300),self.rng.randrange(330,351)],[.25,.5,.25])[0]
            if strategy=='TWAP':
                step=self.rng.randint(2,8);offsets=[i*step for i in range(count)]
            elif strategy=='participation':
                step=self.rng.randint(1,5);offsets=[i*step for i in range(count)]
            else:offsets=sorted(self.rng.sample(range(40),count))
            minutes=[minute+offset for offset in offsets]
            # Do not fabricate an execution when a simulated minute has no capacity.
            attempts=0
            while any(int(self.volume[(day,s,m)]*.35)-self.used[(day,s,m)]<=0 for m in minutes):
                minute=self.rng.randrange(5,351);minutes=[minute+offset for offset in offsets];attempts+=1
                if attempts>100:raise ValueError('Unable to place background order within volume budget')
            typical=max(1,round(self.rng.lognormvariate([4.8,5.8,5.4,4.6][desk],.55)))
            volumes=[self.volume[(day,s,m)] for m in minutes]
            if strategy=='VWAP' and count:
                mean=statistics.mean(volumes);quantities=[max(1,round(typical*v/mean)) for v in volumes]
            elif strategy=='TWAP':quantities=[typical]*count
            elif strategy=='participation':
                rate=self.rng.uniform(.001,.008);quantities=[max(1,round(v*rate)) for v in volumes]
            else:quantities=[max(1,round(typical*self.rng.uniform(.4,1.6))) for _ in minutes]
            planned=sum(min(q,max(0,int(self.volume[(day,s,m)]*.35)-self.used[(day,s,m)])) for m,q in zip(minutes,quantities))
            if side=='sell' and planned>max(0,self.inventory[(account,s)]-5000):side='buy'
            partial=bool(count and self.rng.random()<.1)
            otype='limit' if partial or iszero or self.rng.random()<.65 else 'market'
            oid,_=self.order(day,s,account,tr,side,minutes,quantities,partial=partial,cancel=iszero,
                             amend=bool(count>1 and otype=='limit' and self.rng.random()<.12),strategy=strategy,otype=otype,
                             second=self.rng.randint(10,48))
            o=self.db.execute('SELECT * FROM orders WHERE order_id=?',(oid,)).fetchone()
            if desk in (1,2) and count:
                if not partial and self.rng.random()<.12:self.mandate(oid)
                else:
                    received=dt(o['submitted_at'])-timedelta(minutes=self.rng.randint(2,30))
                    self.db.execute('INSERT INTO customer_instructions VALUES (?,?,?,?,?,?)',('CI-'+oid,oid,iso(received),None,'authenticated_order_api','OMS-'+oid))
                    self.db.execute('UPDATE orders SET claimed_instruction_at=? WHERE order_id=?',(iso(received),oid))
            if n and n%10000==0:
                self.db.commit();print(f'Background orders created: {n:,}',flush=True)
        self.background_mode=False
        for n in range(4800):
            day=self.rng.choice(self.days);s=self.rng.choice(self.symbols);a=f'A-{self.rng.randrange(1,41):02}'
            text=self.rng.choice([
                'Confirm the {symbol} allocation for {account} after execution.',
                'Please keep {symbol} within the approved participation cap today.',
                'The blue folder is the office seating plan. Facilities needs the signed copy.',
                'Run the scheduled portfolio weights for {symbol}; use the documented window.',
                'The closing bell reminder is for the operations staffing handover.',
                'Please reconcile the {account} statement against the executed fills.',
                'The signed file for {account} is in the document archive.',
                'Quotes in {symbol} moved with the market; check the risk cap before repricing.',
                'Keep the internal draft off the public channel until review is complete.',
                'Cash allocation updated for {account}; do not change the approved order quantity.',
                'Confirm who is covering the {symbol} desk during the training session.',
                'The risk dashboard for {account} is ready for the afternoon check.',
            ]).format(symbol=s,account=a)
            self.evidence('communication',self.time(day,self.rng.randrange(5,380)),text,[a])
        self.db.commit()

    def alerts(self):
        """Rules inspect source records only; no truth keys or outcome labels are read."""
        db=self.db;seq=0;group_ids={}
        def emit(family,orders,features):
            nonlocal seq
            orders=sorted(set(orders))
            if not orders:return
            key=(family,tuple(orders))
            if key in group_ids:return
            seq+=1;aid=f'TS-{2000+seq}'
            o=db.execute('SELECT * FROM orders WHERE order_id=?',(orders[0],)).fetchone()
            day=o['submitted_at'][:10]
            end=dt(db.execute('SELECT close_at FROM sessions WHERE session_date=?',(day,)).fetchone()[0])
            detected=end+timedelta(minutes=1)
            cutoff=detected+timedelta(minutes=5)
            if family=='pre_announcement':
                detected=dt(features['public_event_at'])+timedelta(minutes=15)
                cutoff=max(detected+timedelta(minutes=5),dt(day+'T00:00:00Z')+timedelta(days=1,hours=12,minutes=10))
            db.execute('INSERT INTO alerts VALUES (?,?,?,?,?,?)',(aid,'SURV-'+aid,family,iso(detected),iso(cutoff),o['account_id']))
            db.executemany('INSERT INTO alert_orders VALUES (?,?)',[(aid,oid) for oid in orders])
            db.execute('INSERT INTO alert_features VALUES (?,?,?)',(aid,json.dumps(features,sort_keys=True),'synthetic-rules-v2'))
            group_ids[key]=aid
        metrics=[dict(r) for r in db.execute('''SELECT o.*,t.desk_id,sum(f.quantity) filled_quantity,min(f.executed_at) first_fill,max(f.executed_at) last_fill
                    FROM orders o JOIN traders t USING(trader_id) JOIN fills f USING(order_id) GROUP BY o.order_id ORDER BY first_fill,o.order_id''')]
        history=defaultdict(list)
        daily_volume={(r['security_id'],r['session_date']):r['volume_shares'] for r in db.execute('SELECT * FROM market_daily')}
        public_events=[dict(r) for r in db.execute('SELECT * FROM public_events')]
        for o in metrics:
            cohort=(o['desk_id'],o['security_id'],o['execution_strategy'])
            prior=history[cohort]
            # Final daily volume is known only after the session; baseline uses earlier dates.
            completed=sorted((p for p in prior if p[1][:10]<o['first_fill'][:10]),key=lambda p:p[1])[-80:]
            baseline=statistics.median(p[0] for p in completed) if completed else 0
            fractions=sorted(p[2] for p in completed)
            median_fraction=statistics.median(fractions) if fractions else 0
            upper_fraction=fractions[max(0,math.ceil(.95*len(fractions))-1)] if fractions else 0
            fraction=o['filled_quantity']/daily_volume[(o['security_id'],o['first_fill'][:10])]
            if (len(completed)>=15 and o['filled_quantity']>=5000 and baseline and o['filled_quantity']/baseline>=6
                and median_fraction and fraction/median_fraction>=6 and fraction>2*upper_fraction):
                emit('size_outlier',[o['order_id']],{'prior_parent_orders':len(completed),'cohort_desk':o['desk_id'],
                    'execution_strategy':o['execution_strategy'],'prior_median_shares':baseline,'filled_shares':o['filled_quantity'],
                    'ratio':round(o['filled_quantity']/baseline,2),'daily_volume_fraction':fraction,
                    'historical_volume_fraction_ratio':round(fraction/median_fraction,2),'baseline_cutoff':'prior completed sessions'})
            for public in public_events:
                if (o['security_id']==public['security_id'] and dt(public['event_at'])-timedelta(days=1)<=dt(o['first_fill'])<dt(public['event_at'])
                    and public['known_from']<=o['first_fill'] and o['filled_quantity']>=5000):
                    emit('pre_announcement',[o['order_id']],{'public_event_id':public['event_id'],'public_event_at':public['event_at'],'filled_shares':o['filled_quantity'],'event_schedule_was_public':True})
            prior.append((o['filled_quantity'],o['last_fill'],fraction))
        for r in db.execute('''SELECT o.account_id,o.security_id,substr(v.submitted_at,1,10) day,count(*) layers,
                         group_concat(DISTINCT o.order_id) orders FROM venue_orders v JOIN orders o ON o.order_id=v.parent_order_id
                         WHERE (julianday(v.cancelled_at)-julianday(v.accepted_at))*86400<2 AND v.executed_quantity=0
                         AND EXISTS(SELECT 1 FROM fills f JOIN orders opposite USING(order_id) WHERE opposite.account_id=o.account_id
                          AND opposite.security_id=o.security_id AND opposite.side!=v.side AND f.executed_at BETWEEN v.accepted_at AND v.cancelled_at)
                         GROUP BY 1,2,3 HAVING count(*)>=6''').fetchall():
            related=[x[0] for x in db.execute('''SELECT DISTINCT o.order_id FROM orders o JOIN fills f USING(order_id)
                       WHERE o.account_id=? AND o.security_id=? AND substr(f.executed_at,1,10)=?
                       AND EXISTS(SELECT 1 FROM venue_orders v JOIN orders p ON p.order_id=v.parent_order_id
                       WHERE p.account_id=o.account_id AND p.security_id=o.security_id AND v.side!=o.side
                       AND f.executed_at BETWEEN v.accepted_at AND v.cancelled_at)''',(r['account_id'],r['security_id'],r['day']))]
            emit('spoofing_layering',r['orders'].split(',')+related,{'short_lived_layers':r['layers'],'opposite_side_fill_overlap':True,'book_data_origin':'simulated'})
        for customer in db.execute('''SELECT c.*,o.security_id,o.account_id,o.side,sum(f.quantity) quantity,min(f.executed_at) first_fill
                           FROM customer_instructions c JOIN orders o USING(order_id) JOIN fills f USING(order_id)
                           GROUP BY c.instruction_id HAVING sum(f.quantity)>=15000''').fetchall():
            candidates=db.execute('''SELECT p.order_id FROM orders p JOIN accounts a USING(account_id) JOIN fills f USING(order_id)
                         WHERE a.account_type='internal' AND p.security_id=? AND p.side=?
                         GROUP BY p.order_id HAVING sum(f.quantity)>=500 AND min(f.executed_at)>=? AND min(f.executed_at)<?''',
                         (customer['security_id'],customer['side'],customer['received_at'],customer['first_fill'])).fetchall()
            if candidates:emit('front_running',[customer['order_id']]+[x[0] for x in candidates],{'customer_instruction_received':customer['received_at'],'customer_first_fill':customer['first_fill'],'knowledge_not_established_by_timing':True})
        matches=defaultdict(list)
        for r in db.execute('''SELECT m.*,b.order_id buy_order,s.order_id sell_order,bo.account_id ba,so.account_id sa,bo.security_id,
                    ownb.beneficial_owner_id buyer_owner,owns.beneficial_owner_id seller_owner FROM execution_matches m
                    JOIN fills b ON b.fill_id=m.buy_fill_id JOIN fills s ON s.fill_id=m.sell_fill_id
                    JOIN orders bo ON bo.order_id=b.order_id JOIN orders so ON so.order_id=s.order_id
                    JOIN account_ownership ownb ON ownb.account_id=bo.account_id JOIN account_ownership owns ON owns.account_id=so.account_id'''):
            family='wash_self_trade' if r['buyer_owner']==r['seller_owner'] else 'coordinated_trading'
            matches[(family,r['ba'],r['sa'],r['security_id'],r['match_at'][:10])].append(dict(r))
        for key,rows in matches.items():
            if len(rows)>=3:emit(key[0],[o for r in rows for o in [r['buy_order'],r['sell_order']]],{'matched_executions':len(rows),'same_beneficial_owner':key[0]=='wash_self_trade'})
        for o in metrics:
            day=o['last_fill'][:10]
            close=dt(db.execute('SELECT close_at FROM sessions WHERE session_date=?',(day,)).fetchone()[0]);start=iso(close-timedelta(minutes=5))
            if o['first_fill']>=start:
                volume=db.execute('SELECT sum(market_volume_shares) FROM market_bars WHERE security_id=? AND minute_at>=? AND minute_at<?',(o['security_id'],start,iso(close))).fetchone()[0]
                if o['filled_quantity']/volume>=.10:emit('marking_close',[o['order_id']],{'last_five_minute_share':round(o['filled_quantity']/volume,4),'market_path_origin':'simulated'})
        for r in db.execute('''SELECT o.order_id,c.received_at,c.signed_at,min(f.executed_at) first_fill FROM customer_instructions c
                    JOIN orders o USING(order_id) JOIN fills f USING(order_id) GROUP BY o.order_id
                    HAVING c.signed_at IS NOT NULL AND c.signed_at>min(f.executed_at)''').fetchall():
            emit('authorization_restriction',[r['order_id']],{'first_fill':r['first_fill'],'signed_at':r['signed_at'],'claimed_receipt':r['received_at']})
        for r in db.execute('''SELECT DISTINCT o.order_id,r.restriction_id FROM restrictions r JOIN orders o USING(security_id,account_id)
                     JOIN fills f USING(order_id) WHERE f.executed_at BETWEEN r.valid_from AND r.valid_to''').fetchall():
            emit('authorization_restriction',[r['order_id']],{'active_restriction':r['restriction_id']})
        # Evaluation-only association happens AFTER detection; it cannot influence triggers.
        for episode in self.truth:
            ids=[]
            for row in db.execute('SELECT a.alert_id FROM alerts a JOIN alert_orders ao USING(alert_id) WHERE a.rule=? AND ao.order_id IN ('+','.join('?' for _ in episode['order_ids'])+')',(episode['family'],*episode['order_ids'])):
                ids.append(row[0])
            episode['detected_alert_ids']=sorted(set(ids))
        self.db.commit()
        from scripts.group_cases import persist_cases
        persist_cases(db)
        return dict(Counter(r[0] for r in db.execute('SELECT rule FROM alerts')))

    def validate(self,target_orders,target_fills):
        db=self.db
        checks={}
        checks['foreign_keys']=not db.execute('PRAGMA foreign_key_check').fetchall()
        checks['target_order_count']=db.execute('SELECT count(*) FROM orders').fetchone()[0]==target_orders
        checks['target_execution_count']=db.execute('SELECT count(*) FROM fills').fetchone()[0]==target_fills
        checks['all_eight_alert_families_detected']=set(r[0] for r in db.execute('SELECT DISTINCT rule FROM alerts'))==set(FAMILIES)
        checks['all_authored_episodes_detected']=len(self.truth)==96 and all(e['detected_alert_ids'] for e in self.truth)
        checks['all_alerts_grouped_once']=db.execute('SELECT count(*) FROM case_alerts').fetchone()[0]==db.execute('SELECT count(*) FROM alerts').fetchone()[0]
        checks['no_overfills']=db.execute('''SELECT count(*) FROM
            (SELECT o.order_id,o.original_quantity,sum(f.quantity) quantity FROM orders o JOIN fills f USING(order_id) GROUP BY o.order_id)
            WHERE quantity>original_quantity''').fetchone()[0]==0
        checks['terminal_states_reconcile']=db.execute('''SELECT count(*) FROM orders o
            JOIN order_events e ON e.event_id=o.order_id||'-Z'
            LEFT JOIN (SELECT order_id,sum(quantity) quantity FROM fills GROUP BY order_id) f USING(order_id)
            WHERE (e.event_type='filled' AND coalesce(f.quantity,0)!=e.total_quantity)
            OR (e.event_type='cancelled' AND coalesce(f.quantity,0)>=e.total_quantity)''').fetchone()[0]==0
        checks['fills_follow_acceptance_and_precede_terminal_state']=db.execute('''SELECT count(*) FROM fills f
            JOIN order_events a ON a.event_id=f.order_id||'-A' JOIN order_events z ON z.event_id=f.order_id||'-Z'
            WHERE f.executed_at<a.event_at OR f.executed_at>z.event_at''').fetchone()[0]==0
        checks['fills_in_open_sessions']=db.execute('''SELECT count(*) FROM fills f
            LEFT JOIN sessions s ON s.session_date=substr(f.executed_at,1,10)
            WHERE s.session_date IS NULL OR f.executed_at<s.open_at OR f.executed_at>=s.close_at''').fetchone()[0]==0
        checks['prices_respect_effective_limits']=db.execute('''SELECT count(*) FROM fills f JOIN orders o USING(order_id)
            WHERE (o.side='buy' AND f.price_cents>(SELECT e.limit_price_cents FROM order_events e WHERE e.order_id=f.order_id AND e.event_at<=f.executed_at ORDER BY e.event_at DESC LIMIT 1))
            OR (o.side='sell' AND f.price_cents<(SELECT e.limit_price_cents FROM order_events e WHERE e.order_id=f.order_id AND e.event_at<=f.executed_at ORDER BY e.event_at DESC LIMIT 1))''').fetchone()[0]==0
        checks['execution_prices_inside_sourced_daily_range']=db.execute('''SELECT count(*) FROM fills f JOIN orders o USING(order_id)
            LEFT JOIN market_daily d ON d.security_id=o.security_id AND d.session_date=substr(f.executed_at,1,10)
            WHERE d.security_id IS NULL OR f.price_cents<d.low_cents OR f.price_cents>d.high_cents''').fetchone()[0]==0
        checks['simulated_minute_bars_reconcile_daily_context']=db.execute('''SELECT count(*) FROM
            (SELECT security_id,substr(minute_at,1,10) session_date,sum(market_volume_shares) volume,min(low_cents) low,max(high_cents) high,count(*) minutes
            FROM market_bars GROUP BY 1,2) b JOIN market_daily d USING(security_id,session_date)
            WHERE b.volume!=d.volume_shares OR b.low!=d.low_cents OR b.high!=d.high_cents OR b.minutes!=390''').fetchone()[0]==0
        checks['broker_execution_volume_within_minute_budget']=db.execute('''SELECT count(*) FROM
            (SELECT o.security_id,substr(f.executed_at,1,16)||':00.000Z' minute_at,sum(f.quantity) qty
            FROM fills f JOIN orders o USING(order_id) GROUP BY 1,2) x JOIN market_bars b USING(security_id,minute_at)
            WHERE x.qty>cast(b.market_volume_shares*.35 AS INTEGER)''').fetchone()[0]==0
        checks['no_unfunded_short_sales']=db.execute('''SELECT count(*) FROM
            (SELECT p.quantity+sum(CASE WHEN o.side='buy' THEN f.quantity ELSE -f.quantity END)
             OVER(PARTITION BY o.account_id,o.security_id ORDER BY f.executed_at,f.fill_id ROWS UNBOUNDED PRECEDING) balance
             FROM fills f JOIN orders o USING(order_id) JOIN opening_positions p USING(account_id,security_id)) WHERE balance<0''').fetchone()[0]==0
        checks['matched_execution_legs_reconcile']=db.execute('''SELECT count(*) FROM execution_matches m
            JOIN fills b ON b.fill_id=m.buy_fill_id JOIN fills s ON s.fill_id=m.sell_fill_id
            JOIN orders bo ON bo.order_id=b.order_id JOIN orders so ON so.order_id=s.order_id
            WHERE b.quantity!=s.quantity OR b.price_cents!=s.price_cents OR b.executed_at!=s.executed_at
            OR bo.security_id!=so.security_id OR bo.side!='buy' OR so.side!='sell' ''').fetchone()[0]==0
        checks['private_scenario_truth_not_in_source_schema']=all('truth' not in r[0] and 'outcome' not in r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'"))
        return checks

    def export(self,checks):
        counts={t:self.db.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in TABLES}
        outcomes=Counter(e['variant'] for e in self.truth)
        manifest={'dataset_kind':'public_daily_context_with_simulated_broker_activity','seed':self.seed,
            'market_start':self.days[0],'market_end':self.days[-1],'trading_sessions':len(self.days),'counts':counts,
            'source_market_cache_sha256':hashlib.sha256((ROOT/'sample/market_history.json').read_bytes()).hexdigest(),
            'order_sides':dict(self.db.execute('SELECT side,count(*) FROM orders GROUP BY side').fetchall()),
            'order_types':dict(self.db.execute('SELECT order_type,count(*) FROM orders GROUP BY order_type').fetchall()),
            'execution_strategies':dict(self.db.execute('SELECT execution_strategy,count(*) FROM orders GROUP BY execution_strategy').fetchall()),
            'alerts_by_family':dict(self.db.execute('SELECT rule,count(*) FROM alerts GROUP BY rule').fetchall()),
            'authored_episodes':len(self.truth),'checks':checks,
            'limitations':['Market daily OHLC/volume is sourced; intraday paths, depth, individual orders, fills and private evidence are simulated.',
                'Intraday paths are conditioned on the complete historical daily bar and cannot be used to claim predictive performance.',
                'Market-order price_limit_cents is an internal protection collar, not an exchange limit order.',
                'Venue-level detail exists for curated spoofing episodes; this is not a full exchange matching engine.',
                'Ordinary communications use templated text; market impact, queue position and routing economics are not calibrated.',
                'The eight demo rules are illustrative alert candidates, not validated regulatory surveillance coverage.',
                'The 96 authored episodes are not a statistically representative benchmark; their expected review routes are not legal findings.']}
        export_dir=ROOT/'sample/population';export_dir.mkdir(exist_ok=True)
        for table in ['orders','fills','alerts','securities']:
            cursor=self.db.execute(f'SELECT * FROM {table} ORDER BY 1')
            with (export_dir/f'{table}.csv').open('w',newline='') as f:
                writer=csv.writer(f);writer.writerow([c[0] for c in cursor.description]);writer.writerows(cursor)
        (export_dir/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        (ROOT/'evals/population_truth.json').write_text(json.dumps({'seed':self.seed,'episodes':self.truth},indent=2)+'\n')
        from scripts.render_workspace import render
        render(self.db)
        return manifest


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--orders',type=int,default=40000)
    parser.add_argument('--fills',type=int,default=150000)
    parser.add_argument('--seed',type=int,default=1042)
    parser.add_argument('--replace',action='store_true')
    args=parser.parse_args()
    out=ROOT/'data/population.sqlite3';out.parent.mkdir(exist_ok=True)
    if out.exists() and not args.replace:raise SystemExit('Population exists; use --replace to regenerate this owned artifact.')
    temp=out.with_suffix('.building.sqlite3')
    if temp.exists():
        if args.replace:temp.unlink()
        else:raise SystemExit('Incomplete build exists; use --replace to restart.')
    pop=Population(temp,args.seed)
    try:
        pop.setup();print('Generating simulated intraday context from sourced daily data...',flush=True)
        pop.market();pop.scenarios();print('Generating ordinary broker activity...',flush=True)
        pop.background(args.orders,args.fills)
        print('Applying source-based alert rules...',flush=True);pop.alerts()
        print('Checking integrity and reconciliation...',flush=True);checks=pop.validate(args.orders,args.fills)
        if not all(checks.values()):
            print(json.dumps(checks,indent=2))
            missing=[(e['family'],e['variant']) for e in pop.truth if not e['detected_alert_ids']]
            raise ValueError(f'Dataset checks failed; undetected authored episodes: {missing}')
        pop.db.commit()
        from scripts.add_order_chats import add_threads
        add_threads(temp)
        from scripts.add_flagged_chats import add_flagged
        add_flagged(temp)
        manifest=pop.export(checks);pop.db.commit();pop.db.close();temp.replace(out)
        print(json.dumps(manifest,indent=2),flush=True)
    finally:
        try:pop.db.close()
        except sqlite3.Error:pass


if __name__=='__main__':main()
