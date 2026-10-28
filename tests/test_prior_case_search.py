import json
from types import SimpleNamespace

import pytest

from app import runtime as rt
from app.config import settings
from app.investigation_extensions import prior_cases
from app.prior_case_search import rank_prior_cases


@pytest.fixture
def search_tool(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'runtime_path', str(tmp_path/'runtime.sqlite3'))
    monkeypatch.setattr(settings, 'investigation_archive', str(tmp_path))
    rt.init()
    calls=[]
    def embed(**kwargs):
        calls.append(kwargs)
        data=[]
        for i, text in enumerate(kwargs['input']):
            # An unrelated record repeats exact query words; the paraphrase is closer.
            vector=([0.,1.] if 'unrelated' in text else [1.,0.])+[0.]*510
            data.append(SimpleNamespace(index=i, embedding=vector))
        return SimpleNamespace(data=list(reversed(data)), usage=SimpleNamespace(total_tokens=5))
    tool=SimpleNamespace(ctx={'case_id':'CURRENT','start':'2025-05-02T09:00:00Z',
        'cutoff':'2025-05-02T12:00:00Z','families':['size_outlier'],'accounts':['A']},
        run_id='search-test',tokens=0,
        client=SimpleNamespace(embeddings=SimpleNamespace(create=embed)))
    return tool,calls,tmp_path


def record(case_id,text,**extra):
    return {'case_id':case_id,'text':text,'origin':'authored_synthetic_reference_case',
        'closed_at':'2025-04-01T00:00:00Z','available_at':'2025-04-01T00:00:00Z',
        'status':'available','families':['size_outlier'],**extra}


def test_semantics_beat_keyword_overlap_and_cache_refreshes(search_tool,monkeypatch):
    tool,calls,_=search_tool
    cases=[record('LEXICAL','unrelated portfolio rebalance'),
           record('SEMANTIC','Adjusting holdings to target weights')]
    ranked=rank_prior_cases(tool,cases,'portfolio rebalance')
    assert ranked[0][2]['case_id']=='SEMANTIC' and ranked[0][1]==0
    assert len(calls)==2 and tool.tokens==10
    rank_prior_cases(tool,cases,'portfolio rebalance')
    assert len(calls)==3 and calls[-1]['input']==['portfolio rebalance']
    cases[1]['text']='New approved weight adjustment'
    rank_prior_cases(tool,cases,'portfolio rebalance')
    assert calls[-2]['input']==['New approved weight adjustment']
    monkeypatch.setattr(settings,'embedding_model','different-model')
    rank_prior_cases(tool,cases,'portfolio rebalance')
    assert len(calls[-2]['input'])==2 and calls[-2]['model']=='different-model'
    with rt.db() as c:
        events=[json.loads(r[0]) for r in c.execute("SELECT payload FROM audit WHERE kind='prior_case_search'")]
    assert events[1]['cache_hit_count']==2 and events[2]['embedded_count']==1


def test_empty_archive_never_calls_api(search_tool):
    tool,calls,_=search_tool
    tool.doc=lambda *args,**kwargs: args[1]
    assert 'No eligible' in prior_cases(tool,'similar case')[0]
    assert calls==[]


def test_live_history_requires_human_review_time_and_scope(search_tool,monkeypatch):
    tool,calls,_=search_tool
    with rt.db() as c:
        for i,case in enumerate(['GOOD','PRIVATE','FUTURE','RECOMMENDED','CURRENT']):
            c.execute('INSERT INTO runs(run_id,case_id,revision,status,created_at,updated_at) VALUES(?,?,1,?,?,?)',
                (case,case,'ready_for_review','2025-04-01','2025-04-01'))
            if case!='RECOMMENDED':
                at='2025-05-03T00:00:00Z' if case=='FUTURE' else '2025-04-01T00:00:00Z'
                c.execute('INSERT INTO reviews VALUES(?,?,?,?,?,?)',(str(i),case,at,'analyst','mark_reviewed',case))
    monkeypatch.setattr('app.evidence_tools.context',lambda case: {
        'accounts':['B'] if case=='PRIVATE' else ['A'],'families':['size_outlier']})
    tool.doc=lambda kind,text,**kwargs: {'text':text,**kwargs.get('extra',{})}
    found=prior_cases(tool,'approved rebalance')
    assert [r['prior_case_id'] for r in found]==['GOOD']
    assert len(calls[0]['input'])==1 and 'GOOD' in calls[0]['input'][0]


def test_limits_output_and_uses_context_for_empty_query(search_tool):
    tool,calls,_=search_tool
    ranked=rank_prior_cases(tool,[record(str(i),'comparable') for i in range(5)],' ')
    assert len(ranked)==3
    assert 'size_outlier' in calls[-1]['input'][0]


def test_bad_embeddings_fail_explicitly(search_tool):
    tool,_,_=search_tool
    tool.client.embeddings.create=lambda **kwargs: SimpleNamespace(
        usage=None,data=[SimpleNamespace(index=0,embedding=[float('nan')]*512)])
    with pytest.raises(RuntimeError,match='Invalid prior-case embedding'):
        rank_prior_cases(tool,[record('BAD','text')],'query')
