from types import SimpleNamespace
import pytest
from app import runtime as rt
from app.config import settings
from app.evidence_tools import EvidenceTools
from app.market_news import public_url, eligible_findings, NewsItem, NewsFindings


def response(cited=True, completed=True, searched=True):
    output = ([{'type': 'web_search_call', 'status': 'completed' if completed else 'failed',
                'action': {'sources': [{'url': 'https://example.com/release'}]}}] if searched else [])
    output.append({'type': 'message', 'content': [{'type': 'output_text', 'text': 'Source reports an earnings release on the case date; exact publication time unknown.',
        'annotations': [{'type': 'url_citation', 'url': 'https://example.com/release', 'title': 'Issuer release'}] if cited else []}]})
    return SimpleNamespace(id='resp_news', usage=SimpleNamespace(total_tokens=20), model_dump=lambda **kwargs: {'output': output})


@pytest.fixture
def news(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'runtime_path', str(tmp_path/'news.sqlite3'))
    rt.init()
    run, _ = rt.ingest('CASE-AF1D9C5F')
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return response()
    def parse(**kwargs):
        item = NewsItem(title='Issuer release', publication_date='2025-05-07', publication_time='unknown',
                       summary='Source reports an earnings release.', source_url='https://example.com/release')
        return SimpleNamespace(output_parsed=NewsFindings(findings=[item]), usage=SimpleNamespace(total_tokens=5))
    tool = EvidenceTools(run['run_id'], run['case_id'], SimpleNamespace(responses=SimpleNamespace(create=create, parse=parse)))
    return tool, calls


def test_news_is_fresh_scoped_cited_and_saved(news):
    tools, calls = news
    record, = tools.call('search_market_news', 'private account names must not be sent to public search')
    request, = calls
    assert request['tools'][0] == {'type': 'web_search', 'external_web_access': True, 'search_context_size': 'medium'}
    assert request['tool_choice'] == {'type': 'web_search'}
    assert request['include'] == ['web_search_call.action.sources']
    assert tools.ctx['cutoff'] in request['input'] and 'AMZN' in request['input']
    assert 'private account names' not in request['input']
    assert all(account not in request['input'] for account in tools.ctx['accounts'])
    assert record['sources'][0]['title'] == 'Issuer release'
    assert record['publication_timing_verified'] is False
    assert record['retrospective'] is True
    assert 'not independently verified' in record['text']
    assert 'not verbatim article text' in record['text']
    assert rt.recalled(tools.run_id)[record['evidence_id']]['response_id'] == 'resp_news'
    assert tools.tokens == 25


def test_uncited_output_does_not_become_news_evidence(news):
    tools, _ = news
    tools.client.responses.create = lambda **kwargs: response(cited=False)
    record, = tools.call('search_market_news', '')
    assert record['search_status'] == 'no_citable_findings'
    assert record['sources'] == []
    assert 'Source reports an earnings release' not in record['text']
    assert 'no citable news findings' in record['text']


@pytest.mark.parametrize('kwargs', [{'searched': False}, {'completed': False}])
def test_search_must_actually_complete(news, kwargs):
    tools, _ = news
    tools.client.responses.create = lambda **kw: response(**kwargs)
    with pytest.raises(RuntimeError, match='did not complete'):
        tools.call('search_market_news', '')
    assert not rt.recalled(tools.run_id)


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'file:///secret', 'https://user:pass@example.com', 'http://example.com'])
def test_unsafe_news_links_rejected(url):
    assert public_url(url) is None


@pytest.mark.parametrize('day,time,url', [
    ('2025-05-09','unknown','https://example.com/release'),
    ('2025-05-01','unknown','https://example.com/release'),
    ('2025-05-08','2025-05-08T21:00:00Z','https://example.com/release'),
    ('2025-05-08','2025-05-08T15:00:00','https://example.com/release'),
    ('unknown','unknown','https://example.com/release'),
    ('2025-05-08','unknown','https://invented.example/release'),
])
def test_code_rejects_wrong_dates_future_times_and_invented_sources(day,time,url):
    item=NewsItem(title='News',publication_date=day,publication_time=time,summary='Reported fact',source_url=url)
    assert eligible_findings([item], {'https://example.com/release'}, '2025-05-03','2025-05-08T20:06:00Z') == []


def test_same_day_unknown_time_retains_uncertainty():
    item=NewsItem(title='News',publication_date='2025-05-08',publication_time='unknown',summary='Reported fact',source_url='https://example.com/release')
    findings=eligible_findings([item], {item.source_url}, '2025-05-03','2025-05-08T20:06:00Z')
    assert findings[0]['publication_time']=='unknown'
