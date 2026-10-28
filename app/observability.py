"""Workflow tracing and supplementary API spans around SDK-run investigations."""
import json
import logging
import re
from contextlib import contextmanager, ExitStack
from functools import wraps
from types import SimpleNamespace
from agents import (trace, agent_span, generation_span, function_span, custom_span,
                    get_current_trace, set_tracing_export_api_key)
from agents.tracing import get_trace_provider
from .config import settings

log = logging.getLogger(__name__)
EVENTS = {'image_review', 'initial_assessment', 'depth_changed', 'audio_transcription', 'grounding_review',
          'validation', 'manual_review_required', 'report_ready', 'quantitative_analysis'}


def encoded(value, limit=24000):
    """Bound telemetry and remove credential-shaped values and personal email addresses."""
    def clean(v):
        if hasattr(v, 'model_dump'): return clean(v.model_dump(mode='json'))
        if isinstance(v, dict):
            return {str(k): ('[redacted]' if re.search(r'password|secret|api_key|authorization|token$', str(k), re.I)
                             else clean(x)) for k, x in v.items()}
        if isinstance(v, (list, tuple)): return [clean(x) for x in v]
        if isinstance(v, str):
            v = re.sub(r'sk-[A-Za-z0-9_-]+', '[redacted key]', v)
            return re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[redacted email]', v)
        if v is None or isinstance(v, (int, float, bool)): return v
        return '[non-text value]'
    text = json.dumps(clean(value), ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + '… [trace excerpt truncated; full evidence remains in application]'


def active():
    return settings.openai_tracing_enabled and get_current_trace() is not None


@contextmanager
def span(factory, **kwargs):
    """Exporter/instrumentation failures must not interrupt the investigation."""
    current = None
    if active():
        try:
            current = factory(**kwargs)
            current.start(mark_as_current=True)
        except Exception:
            log.warning('Could not start OpenAI trace span; investigation continues')
            current = None
    try:
        yield current
    except Exception as exc:
        if current:
            current.set_error({'message': type(exc).__name__, 'data': {}})
        raise
    finally:
        if current:
            try: current.finish(reset_current=True)
            except Exception: log.warning('Could not finish OpenAI trace span')


def trace_event(kind, payload):
    if kind in EVENTS and active():
        with span(custom_span, name=kind.replace('_', ' ').title(), data={'event_excerpt': encoded(payload)}):
            pass


@contextmanager
def tool_call(name, arguments):
    with span(function_span, name=name, input=encoded(arguments)) as current:
        result = SimpleNamespace(output=None)
        yield result
        if current:
            current.span_data.output = encoded(result.output)
            if isinstance(result.output, dict) and result.output.get('status') == 'validation_error':
                current.set_error({'message': 'Tool arguments rejected by application controls', 'data': {}})


class TracedClient:
    """Preserves SDK request/return behavior, including bounded timeout clones."""
    def __init__(self, client, path=''):
        self._client = client
        self._path = path

    def with_options(self, **kwargs):
        return TracedClient(self._client.with_options(**kwargs))

    def __getattr__(self, name):
        value = getattr(self._client, name)
        path = (self._path + '.' + name).lstrip('.')
        if path in {'responses', 'embeddings', 'audio', 'audio.transcriptions'}:
            return TracedClient(value, path)
        if path not in {'responses.create', 'responses.parse', 'embeddings.create', 'audio.transcriptions.create'}:
            return value
        @wraps(value)
        def request(*args, **kwargs):
            if not active(): return value(*args, **kwargs)
            is_response = path.startswith('responses.')
            options = ({'model': kwargs.get('model'),
                        'input': [{'role': 'user', 'content': encoded({'instructions': kwargs.get('instructions'), 'input': kwargs.get('input')})}],
                        'model_config': {'api': path, 'store': kwargs.get('store', True), **({'reasoning': kwargs['reasoning']} if 'reasoning' in kwargs else {})}} if is_response else
                       {'name': 'OpenAI ' + path, 'data': {'model': kwargs.get('model'),
                        'input_count': len(kwargs.get('input', [])) if isinstance(kwargs.get('input'), list) else 1}})
            with ExitStack() as stack:
                hosted = [t.get('type') for t in kwargs.get('tools', []) if isinstance(t, dict)]
                capability = None
                if is_response and 'file_search' in hosted:
                    capability = stack.enter_context(span(custom_span, name='OpenAI File Search', data={'api':path,'model':kwargs.get('model')}))
                elif is_response and 'code_interpreter' in hosted:
                    capability = stack.enter_context(span(custom_span, name='OpenAI Code Interpreter', data={'api':path,'model':kwargs.get('model')}))
                elif is_response and 'web_search' in hosted:
                    capability = stack.enter_context(span(custom_span, name='OpenAI Web Search', data={'api':path,'model':kwargs.get('model')}))
                current = stack.enter_context(span(generation_span if is_response else custom_span, **options))
                response = value(*args, **kwargs)
                if capability:
                    capability.span_data.data['response_id'] = response.id
                if current:
                    try:
                        usage = getattr(response, 'usage', None)
                        if is_response:
                            current.span_data.output = [{'role': 'assistant', 'content': encoded([
                                ({'type': 'reasoning', 'summary': [part.model_dump() if hasattr(part, 'model_dump') else part for part in (getattr(item, 'summary', None) or [])]} if getattr(item, 'type', None) == 'reasoning' else item) for item in response.output if getattr(item, 'type', None) != 'reasoning' or getattr(item, 'summary', None)])}]
                            current.span_data.usage = {'input_tokens': getattr(usage, 'input_tokens', 0),
                                                      'output_tokens': getattr(usage, 'output_tokens', 0)}
                            current.span_data.model_config = options['model_config'] | {'response_id': response.id}
                        else:
                            current.span_data.data.update({'request_id': getattr(response, '_request_id', None),
                                'tokens': getattr(usage, 'total_tokens', None), 'duration_seconds': getattr(response, 'duration', None)})
                    except Exception:
                        log.warning('Could not attach OpenAI trace result; original API result preserved')
                return response
        return request


def traced_investigation(fn):
    @wraps(fn)
    def run(record):
        if not settings.openai_tracing_enabled or not settings.openai_api_key: return fn(record)
        from . import runtime as rt
        set_tracing_export_api_key(settings.openai_api_key)
        workflow = trace('Trade Surveillance Investigation', group_id=record['case_id'],
                         metadata={'case_id': record['case_id'], 'run_id': record['run_id'],
                                   'revision': str(record['revision']), 'activity_origin': 'fictional demonstration',
                                   'execution_engine': 'openai_agents_sdk'})
        with workflow:
            rt.audit(record['run_id'], 'platform_trace_started', {'trace_id': workflow.trace_id,
                'url': 'https://platform.openai.com/logs/trace?trace_id=' + workflow.trace_id + '&api=traces'})
            with custom_span(name='Investigation workflow controls', data={'execution_engine': 'openai_agents_sdk'}) as agent:
                result = fn(record)
                with span(custom_span, name='Human review handoff', data={'status': result['status'],
                          'report': encoded(result.get('report')), 'human_decision_recorded': False}):
                    pass
                if result['status'] == 'manual_review':
                    agent.set_error({'message': 'Investigation held for human attention', 'data': {}})
            rt.audit(record['run_id'], 'platform_trace_completed', {'trace_id': workflow.trace_id, 'status': result['status'],
                'export_status': 'queued for OpenAI exporter; dashboard visibility must be verified'})
        return rt.details(record['run_id'])
    return run


def flush():
    get_trace_provider().force_flush()
