from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import json
import pytest
from agents import trace, set_trace_processors
from agents.tracing import TracingProcessor
from agents.tracing.processors import default_processor
from app import observability as obs
from app.config import settings


class Capture(TracingProcessor):
    def __init__(self): self.spans = []; self.traces = []
    def on_trace_start(self, trace): pass
    def on_trace_end(self, trace): self.traces.append(trace.export())
    def on_span_start(self, span): pass
    def on_span_end(self, span): self.spans.append(span.export())
    def shutdown(self): pass
    def force_flush(self): pass


@pytest.fixture
def capture(monkeypatch):
    capture = Capture()
    set_trace_processors([capture])
    monkeypatch.setattr(settings, 'openai_tracing_enabled', True)
    yield capture
    set_trace_processors([default_processor()])


def test_actual_client_call_nested_under_tool_and_return_preserved(capture):
    response = SimpleNamespace(id='resp_test', output=[SimpleNamespace(type='reasoning'), {'type':'message','text':'Observed evidence'}],
                               usage=SimpleNamespace(input_tokens=10, output_tokens=4))
    calls = []
    def create(**kwargs): calls.append(kwargs); return response
    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    client.with_options = lambda **kwargs: client
    wrapped = obs.TracedClient(client)
    with trace('test'):
        with obs.tool_call('policy_search', {'query':'approval'}) as tool:
            assert wrapped.with_options(timeout=2).responses.create(model='gpt-4.1',input='Evidence',store=False) is response
            tool.output = {'evidence_id':'E-1'}
    model = next(s for s in capture.spans if s['span_data']['type']=='generation')
    tool = next(s for s in capture.spans if s['span_data']['type']=='function')
    assert model['parent_id']==tool['id']
    assert model['span_data']['usage']=={'input_tokens':10,'output_tokens':4}
    assert model['span_data']['model_config']['response_id']=='resp_test'
    assert 'reasoning' not in json.dumps(model['span_data']['output'])
    assert calls==[{'model':'gpt-4.1','input':'Evidence','store':False}]


def test_api_error_is_preserved_and_recorded(capture):
    def fail(**kwargs): raise TimeoutError('sensitive upstream detail')
    client = obs.TracedClient(SimpleNamespace(responses=SimpleNamespace(create=fail)))
    with trace('test'):
        with pytest.raises(TimeoutError, match='sensitive upstream detail'):
            client.responses.create(model='gpt-4.1')
    assert capture.spans[0]['error']['message']=='TimeoutError'
    assert 'sensitive upstream detail' not in json.dumps(capture.spans)


def test_telemetry_excludes_secrets_emails_and_binary():
    value=obs.encoded({'api_key':'secret','smtp_password':'secret','note':'Email person@example.com and key sk-abc123','audio':b'raw'})
    assert 'secret' not in value and 'person@example.com' not in value and 'sk-abc123' not in value
    assert 'raw' not in value
    assert '[trace excerpt truncated' in obs.encoded('x'*25000)


def test_parallel_runs_keep_separate_trace_parents(capture):
    def job(name):
        with trace(name):
            with obs.tool_call(name, {}) as tool: tool.output={'status':'available'}
    with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(job,['case-a','case-b']))
    assert len({s['trace_id'] for s in capture.spans})==2


def test_disabled_tracing_makes_no_spans_and_calls_once(capture, monkeypatch):
    monkeypatch.setattr(settings,'openai_tracing_enabled',False)
    calls=[]
    client=obs.TracedClient(SimpleNamespace(embeddings=SimpleNamespace(create=lambda **kwargs:calls.append(kwargs))))
    client.embeddings.create(model='test',input=['one'])
    assert len(calls)==1 and not capture.spans


def test_hosted_file_search_has_an_explicit_span(capture):
    response=SimpleNamespace(id='resp_file_search',output=[],usage=SimpleNamespace(input_tokens=2,output_tokens=1))
    client=obs.TracedClient(SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs:response)))
    with trace('test'):
        assert client.responses.create(model='gpt-4.1',tools=[{'type':'file_search'}]) is response
    hosted=next(s for s in capture.spans if s['span_data'].get('name')=='OpenAI File Search')
    model=next(s for s in capture.spans if s['span_data']['type']=='generation')
    assert model['parent_id']==hosted['id']
    assert hosted['span_data']['data']['response_id']=='resp_file_search'


def test_hosted_web_search_has_an_explicit_span(capture):
    response=SimpleNamespace(id='resp_news',output=[],usage=SimpleNamespace(input_tokens=2,output_tokens=1))
    client=obs.TracedClient(SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs:response)))
    with trace('test'):
        assert client.responses.create(model='gpt-4.1',tools=[{'type':'web_search'}]) is response
    hosted=next(s for s in capture.spans if s['span_data'].get('name')=='OpenAI Web Search')
    model=next(s for s in capture.spans if s['span_data']['type']=='generation')
    assert model['parent_id']==hosted['id']
    assert hosted['span_data']['data']['response_id']=='resp_news'


def test_trace_keeps_public_reasoning_summary_without_private_fields(capture):
    response=SimpleNamespace(id='resp_reasoning',output=[SimpleNamespace(type='reasoning',summary=[{'type':'summary_text','text':'Compare the two source records.'}],content='PRIVATE_INTERNAL_CONTENT')],usage=None)
    wrapped=obs.TracedClient(SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs:response)))
    with trace('summary test'):
        wrapped.responses.create(model='gpt-6.1-sol',reasoning={'effort':'low','summary':'auto'})
    output=json.dumps(next(s for s in capture.spans if s['span_data']['type']=='generation')['span_data']['output'])
    assert 'Compare the two source records.' in output
    assert 'PRIVATE_INTERNAL_CONTENT' not in output
