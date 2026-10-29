from types import SimpleNamespace
import pytest
from app import image_evidence as im, runtime as rt
from app.config import settings


def test_quote_validation_rejects_changed_order_quantity():
    reading=im.ImageReading(readable_quotes=['buy 300,000 NVDA shares'],observations=[],uncertainties=[])
    with pytest.raises(ValueError):im.validate_quotes(reading,'Document: buy 30,000 NVDA shares for A-02.')
    reading.readable_quotes=['buy 30,000 NVDA shares']
    im.validate_quotes(reading,'Document: buy 30,000\nNVDA shares for A-02.')


def test_resolve_enforces_case_and_file_integrity(tmp_path,monkeypatch):
    from pathlib import Path
    original=im.folder()
    monkeypatch.setattr(im,'folder',lambda:tmp_path)
    record={'image_id':'IMG-TEST','filename':'test.png','sha256':'wrong'}
    monkeypatch.setattr(im,'context',lambda cid:{'case_id':cid})
    monkeypatch.setattr(im,'eligible',lambda ctx:[record] if ctx['case_id']=='allowed' else [])
    (tmp_path/'test.png').write_bytes(b'\x89PNG\r\n\x1a\ncorrupted')
    with pytest.raises(ValueError,match='authorized'):im.resolve('other','IMG-TEST')
    with pytest.raises(ValueError,match='integrity'):im.resolve('allowed','IMG-TEST')
    with pytest.raises(ValueError):im.resolve('allowed','../IMG-TEST')


def test_pixels_are_sent_and_verified_reading_is_cached(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'runtime_path',str(tmp_path/'runtime.sqlite3'));rt.init()
    calls=[]
    def parse(**kw):
        calls.append(kw)
        return SimpleNamespace(output_parsed=im.ImageReading(readable_quotes=['A factual source sentence.'],observations=[],uncertainties=[]),id='resp_test',usage=SimpleNamespace(total_tokens=10))
    record={'sha256':'abc','source_evidence_id':'SOURCE'}
    path=tmp_path/'test.png';path.write_bytes(b'\x89PNG\r\n\x1a\nimage')
    monkeypatch.setattr(im,'resolve',lambda *a:({},record,path))
    class Sources:
        def __init__(self,*a):pass
        def records(self,*a):return [{'evidence_id':'SOURCE','content':'A factual source sentence.'}]
    monkeypatch.setattr(im,'EvidenceTools',Sources)
    api=SimpleNamespace(responses=SimpleNamespace(parse=parse))
    assert not im.read_image('case','IMG-TEST',api)['cache_hit']
    assert im.read_image('case','IMG-TEST',api)['cache_hit']
    assert len(calls)==1
    assert calls[0]['store'] is False
    content=calls[0]['input'][0]['content']
    assert content[1]['type']=='input_image'
    assert content[1]['image_url'].startswith('data:image/png;base64,')
    assert 'A factual source sentence.' not in content[0]['text']


def test_eligibility_requires_available_paired_source():
    for cid,expected in [('CASE-0088C625','IMG-0088C625'),('CASE-52074E40','IMG-52074E40')]:
        ctx=im.context(cid)
        assert expected in {r['image_id'] for r in im.eligible(ctx)}
        assert im.eligible(ctx|{'cutoff':'1900-01-01T00:00:00Z'})==[]


def test_retired_image_remains_resolvable_but_is_not_a_current_preview(monkeypatch):
    old={'image_id':'IMG-OLD','active':False}
    new={'image_id':'IMG-NEW','title':'Apple desk conversation','sha256':'new-hash',
         'source_evidence_id':'CHAT-DESK','origin':'synthetic_source_rendering',
         'limitation':'Fictional rendering.','rendered_at':'2026-10-28'}
    monkeypatch.setattr(im,'eligible',lambda _: [old,new])
    monkeypatch.setattr(rt,'meta_get',lambda _: None)
    previews=im.previews({'case_id':'CASE-0088C625'})
    assert [r['image_id'] for r in previews]==['IMG-NEW']
    assert not previews[0]['included_in_assessment']


def test_agent_retrieves_image_and_paired_source_without_rewriting_case(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'runtime_path',str(tmp_path/'runtime.sqlite3'));rt.init()
    from app.evidence_tools import EvidenceTools
    from app.sdk_workflow import InvestigationState
    run,_=rt.ingest('CASE-52074E40')
    record=im.eligible(im.context(run['case_id']))[0]
    rt.meta_set(im.cache_key(record),{'model':settings.openai_model,'reviewed_at':rt.now(),'response_id':'cached',
        'readable_quotes':['buy 30,000 NVDA shares for A-02'],'observations':[], 'uncertainties':[],
        'tokens':12,'limitation':'Synthetic image.'})
    state=InvestigationState(run)
    assert 'review_image_evidence' in state.mandatory
    records=EvidenceTools(run['run_id'],run['case_id'],None).call('review_image_evidence','Review attached image')
    assert any(r['source_type']=='image_reading' for r in records)
    assert any(r['evidence_id']==record['source_evidence_id'] for r in records)
    assert im.previews(im.context(run['case_id']),run['run_id'])[0]['included_in_assessment']
    assert rt.details(run['run_id'])['report'] is None
