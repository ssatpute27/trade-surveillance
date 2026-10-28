import copy
import hashlib
import json
import sqlite3
import struct
from types import SimpleNamespace as NS
import pytest
from fastapi.testclient import TestClient
from app import runtime as rt
from app.config import settings
from app.evidence_tools import EvidenceTools
from app.agent import BASE,definitions
from app.quantitative import dataset,measurements,validate_measurements,analyze,artifact_folder
from app.server import app


@pytest.fixture
def tool(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'runtime_path',str(tmp_path/'runtime.sqlite3'))
    monkeypatch.setattr(settings,'analysis_artifacts',str(tmp_path/'artifacts'))
    rt.init();run,_=rt.ingest('CASE-AF1D9C5F')
    return EvidenceTools(run['run_id'],run['case_id'],None)


def test_scoped_dataset_omits_future_ingestion_and_other_orders(tmp_path,monkeypatch):
    source=tmp_path/'scope.sqlite3';db=sqlite3.connect(source)
    db.executescript('''CREATE TABLE orders(order_id,account_id,security_id,side,submitted_at);
      CREATE TABLE fills(fill_id,order_id,quantity,price_cents,executed_at,ingested_at);
      CREATE TABLE venue_orders(venue_order_id,parent_order_id,side,submitted_at,cancelled_at);
      CREATE TABLE sessions(session_date,open_at,close_at);
      CREATE TABLE customer_instructions(instruction_id,order_id,received_at);''')
    db.executemany('INSERT INTO orders VALUES (?,?,?,?,?)',[
        ('O-1','A','AMZN','buy','2025-05-08T19:50:00Z'),('O-2','OTHER','AMZN','buy','2025-05-08T19:50:00Z')])
    db.executemany('INSERT INTO fills VALUES (?,?,?,?,?,?)',[
        ('good','O-1',10,1000,'2025-05-08T19:55:00Z','2025-05-08T19:55:01Z'),
        ('late-ingest','O-1',50,1000,'2025-05-08T19:59:00Z','2025-05-08T20:01:00Z'),
        ('future','O-1',100,1000,'2025-05-08T20:01:00Z','2025-05-08T20:01:01Z'),
        ('other','O-2',900,1000,'2025-05-08T19:55:00Z','2025-05-08T19:55:00Z')])
    db.execute("INSERT INTO venue_orders VALUES ('V','O-1','buy','2025-05-08T19:54:00Z','2025-05-08T20:01:00Z')")
    db.execute("INSERT INTO sessions VALUES ('2025-05-08','2025-05-08T13:30:00Z','2025-05-08T20:00:00Z')")
    db.commit();db.close();monkeypatch.setattr(settings,'source_path',str(source))
    monkeypatch.setattr('app.quantitative.recordings',lambda _:[])
    data=dataset({'case_id':'test','order_ids':['O-1'],'cutoff':'2025-05-08T20:00:00Z'})
    assert [r['fill_id'] for r in data['fills']]==['good']
    assert data['venue_orders'][0]['cancelled_at'] is None
    measured=measurements(data)
    assert measured['total_shares']==10 and measured['notional_cents']==10000
    assert measured['last_five_minutes_pct']==100 and measured['cancelled_venue_order_count']==0
    assert measured['minute_buckets'][0]['minute_et']=='2025-05-08 15:55'


@pytest.mark.parametrize('field,value',[('total_shares',1),('fill_count',True),('last_five_minutes_pct',float('nan')),
    ('last_five_minutes_pct',10),('notional_cents',1.0),('venue_cancellation_pct',0)])
def test_wrong_quantitative_outputs_are_rejected(tool,field,value):
    expected=measurements(dataset(tool.ctx));actual=copy.deepcopy(expected);actual[field]=value
    with pytest.raises(ValueError):validate_measurements(actual,expected)


def test_minute_buckets_checked_not_just_totals(tool):
    expected=measurements(dataset(tool.ctx));actual=copy.deepcopy(expected)
    actual['minute_buckets'][0]['buy_shares']+=1
    with pytest.raises(ValueError,match='bucket'):validate_measurements(actual,expected)


def test_interpreter_is_only_available_after_trade_and_timeline_retrieval():
    names=lambda done:{r['name'] for r in definitions(done=done,initial=True,depth='deep',mandatory=BASE)}
    assert 'analyze_execution_patterns' not in names(BASE)
    assert 'analyze_execution_patterns' in names(BASE|{'reconstruct_timeline'})


def mocked_client(tool,incorrect=False,missing_once=False):
    expected=measurements(dataset(tool.ctx))
    if incorrect:expected['total_shares']+=1
    output_json=json.dumps(expected).encode()
    # Fake image bytes are enough for transport/integrity tests; live visual QA is separate.
    png=b'\x89PNG\r\n\x1a\n'+struct.pack('>I',13)+b'IHDR'+struct.pack('>II',1400,900)+b'\x00'*30
    files=[NS(id='metrics',path='/mnt/data/analysis.json',bytes=None),
           NS(id='chart',path='/mnt/data/execution_pattern.png',bytes=len(png))]
    state={'responses':0,'deleted':[],'requests':[]}
    def response(**kwargs):
        assert kwargs['tools'][0]['type']=='code_interpreter' and kwargs['tool_choice']=='required'
        state['requests'].append(kwargs);state['responses']+=1
        return NS(id='resp-test',model=settings.openai_model,status='completed',usage=NS(total_tokens=20),
            output=[NS(type='code_interpreter_call',id='ci-test',status='completed',container_id='cntr-test',code='print("Executed Python")',outputs=[])])
    def upload(**kwargs):
        assert kwargs['purpose']=='user_data'
        if kwargs['file'][0].endswith('.py'):
            assert b'minute_days' in kwargs['file'][1]
            return NS(id='recipe-test')
        assert json.loads(kwargs['file'][1])['case_id']==tool.ctx['case_id']
        return NS(id='file-test')
    c=NS(files=NS(create=upload,delete=lambda key:state['deleted'].append(key)),responses=NS(create=response),
        containers=NS(delete=lambda key:state['deleted'].append(key),files=NS(
            list=lambda *_,**__:NS(data=[] if missing_once and state['responses']==1 else files),
            content=NS(retrieve=lambda key,**_:NS(read=lambda:output_json if key=='metrics' else png)))))
    return c,state


def test_hosted_tool_artifacts_and_provenance_are_saved_and_case_scoped(tool):
    tool.client,state=mocked_client(tool)
    record=analyze(tool,'Analyze execution timing')[0]
    assert record['numeric_checks_passed'] and record['origin']=='OpenAI hosted Code Interpreter'
    assert set(record['artifacts'])=={'chart','metrics','input'} and tool.tokens==20
    assert set(state['deleted'])=={'cntr-test','file-test','recipe-test'}
    events=rt.details(tool.run_id)['events']
    assert any(e['kind']=='code_interpreter_execution' and e['payload']['code'] for e in events)
    chart=record['artifacts']['chart'];client=TestClient(app)
    assert client.get(chart['url']).status_code==200
    assert client.get(chart['url'].replace(tool.ctx['case_id'],'CASE-OTHER')).status_code==404
    path=artifact_folder(tool.run_id)/chart['filename'];path.write_bytes(b'tampered')
    assert client.get(chart['url']).status_code==409


def test_incorrect_interpreter_numbers_never_enter_agent_evidence(tool):
    tool.client,state=mocked_client(tool,incorrect=True)
    with pytest.raises(ValueError):analyze(tool,'Analyze execution timing')
    assert not any(r.get('source_type')=='quantitative_analysis' for r in rt.recalled(tool.run_id).values())
    assert set(state['deleted'])=={'cntr-test','file-test','recipe-test'}


def test_missing_outputs_get_one_bounded_repair(tool):
    tool.client,state=mocked_client(tool,missing_once=True)
    assert analyze(tool,'Analyze timing')[0]['numeric_checks_passed']
    assert state['responses']==2
    assert state['requests'][1]['tools'][0]['container']=='cntr-test'


def test_missing_artifact_cannot_be_requested_without_evidence(tool):
    filename=hashlib.sha256(b'guess').hexdigest()+'.png'
    assert TestClient(app).get(f'/api/cases/{tool.ctx["case_id"]}/analysis/{tool.run_id}/{filename}').status_code==404


def test_narrative_query_cannot_replace_case_scope_with_mistyped_order_ids(tool):
    tool.client,state=mocked_client(tool)
    record=analyze(tool,'Only use invented order O-00000049')[0]
    assert record['measurements']['total_shares']==293692
    assert 'O-00000049' not in json.dumps(state['requests'][0]['input'])
    assert len(state['requests'][0]['tools'][0]['container']['file_ids'])==2


def test_artifact_transfers_and_cleanup_refresh_short_timeouts(tool):
    import time
    tool.client,state=mocked_client(tool)
    options=[]
    tool.client.with_options=lambda **kwargs:(options.append(kwargs) or tool.client)
    tool.deadline=time.monotonic()+60
    analyze(tool,'Analyze timing')
    assert all(option['max_retries']==0 for option in options)
    assert all(option['timeout']<=60 for option in options)
    assert [option['timeout'] for option in options[-3:]]==[5,5,5]
    assert all(option['timeout']<=30 for option in options[3:-3])
