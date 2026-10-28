import json
from pathlib import Path
from app import runtime as rt
from app.config import settings
from app.evidence_tools import EvidenceTools,context
from app.chatgpt_cases import read_section


def test_every_case_order_has_scoped_thread_with_valid_times():
    with rt.source() as c:
        orders=c.execute('''SELECT DISTINCT o.order_id,o.account_id,o.submitted_at FROM orders o JOIN alert_orders ao USING(order_id)''').fetchall()
        assert len(orders)==370
        for order in orders:
            e=c.execute('SELECT * FROM evidence WHERE evidence_id=?',('CHAT-'+order['order_id'],)).fetchone()
            assert e and e['kind']=='communication' and e['ingested_at']<order['submitted_at']
            meta=json.loads(e['metadata_json'])
            assert meta['order_ids']==[order['order_id']] and len(meta['messages'])==3
            assert all(m['sender'] and m['text'] for m in meta['messages'])
            assert c.execute('SELECT account_id FROM evidence_scope WHERE evidence_id=?',(e['evidence_id'],)).fetchone()[0]==order['account_id']


def test_order_threads_do_not_leak_from_other_orders_on_same_account(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'runtime_path',str(tmp_path/'runtime.sqlite3'))
    rt.init()
    for cid in ('CASE-AF1D9C5F','CASE-52074E40','CASE-542714B9'):
        run,_=rt.ingest(cid)
        tool=EvidenceTools(run['run_id'],cid,None)
        records=tool.records(['communication'])
        threads=[r for r in records if r['evidence_id'].startswith('CHAT-')]
        assert {oid for r in threads for oid in json.loads(r['metadata_json'])['order_ids']}==set(context(cid)['order_ids'])
        page=read_section(cid,'communications',limit=100)
        assert all(not r['included_in_assessment'] for r in page['items'] if r.get('evidence_id','').startswith('CHAT-'))
        assert not rt.recalled(run['run_id'])  # Reading new sources does not rewrite the assessment.


def test_concerning_threads_are_scoped_and_do_not_rewrite_assessments(tmp_path,monkeypatch):
    from scripts.add_flagged_chats import SCENARIOS
    monkeypatch.setattr(settings,'runtime_path',str(tmp_path/'runtime.sqlite3'))
    rt.init()
    for cid in SCENARIOS:
        run,_=rt.ingest(cid)
        tool=EvidenceTools(run['run_id'],cid,None)
        flagged=[r for r in tool.records(['communication']) if r['evidence_id'].startswith('CHAT-FLAG-')]
        assert len(flagged)==1 and flagged[0]['evidence_id']=='CHAT-FLAG-'+cid
        meta=json.loads(flagged[0]['metadata_json'])
        assert len(meta['messages'])==3 and meta['origin']=='synthetic'
        assert set(meta['order_ids'])==set(context(cid)['order_ids'])
        assert rt.details(run['run_id'])['report'] is None
    benign,_=rt.ingest('CASE-52074E40')
    assert not any(r['evidence_id'].startswith('CHAT-FLAG-') for r in EvidenceTools(benign['run_id'],benign['case_id'],None).records(['communication']))
