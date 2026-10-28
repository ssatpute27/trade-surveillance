import json
from uuid import uuid4
import pytest
from agents import Agent, FunctionTool, Runner
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText
from app import runtime as rt, sdk_workflow as sdk
from app.agent import run_investigation, BASE
from app.config import settings


CLAIM = {'text':'The retrieved order is documented.', 'citations':[{'evidence_id':'E-read_trades','quote':'Order documented.'}]}
REPORT = {'assessment':'plausibly_benign','recommendation':'standard_review','summary':CLAIM,
          'observations':[CLAIM],'alternative_explanations':[CLAIM],'gaps':[],'reviewer_questions':['Confirm the source instruction?']}


class ScriptedModel(Model):
    def __init__(self, bypass=False): self.names=[]; self.bypass=bypass
    async def get_response(self, system_instructions, input, model_settings, tools, output_schema, handoffs, tracing, **kwargs):
        if output_schema:
            data=REPORT if output_schema.name()=='Report' else {'supported':True,'issues':[],'flagged_claims':[]}
            output=[ResponseOutputMessage(id='msg_'+uuid4().hex,role='assistant',status='completed',
                content=[ResponseOutputText(type='output_text',text=json.dumps(data),annotations=[])],type='message')]
        else:
            available={t.name for t in tools}
            if self.bypass: name='finish_investigation'
            else:
                order=['record_initial_assessment','promote_to_deep','finish_investigation',
                       'read_trades','historical_baseline','order_authority','market_context','search_market_news','policy_search',
                       'reconstruct_timeline','retrieve_prior_cases']
                name=next(n for n in order if n in available and n not in self.names)
            self.names.append(name)
            args={'reason':'Verify source records.','query':''}
            if name=='record_initial_assessment':args={'reason':'Order documented.','assessment':'plausibly_benign','summary':CLAIM}
            if name=='promote_to_deep':args={'reason':'Inspect missing evidence.','evidence_ids':['E-read_trades']}
            output=[ResponseFunctionToolCall(type='function_call',id='fc_'+uuid4().hex,
                call_id='call_'+uuid4().hex,name=name,arguments=json.dumps(args))]
        return ModelResponse(output=output,usage=Usage(requests=1,input_tokens=10,output_tokens=5,total_tokens=15),response_id='resp_'+uuid4().hex)
    async def stream_response(self,*args,**kwargs):
        raise NotImplementedError
        yield


@pytest.fixture
def workflow(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'runtime_path',str(tmp_path/'runtime.sqlite3'));rt.init()
    run,_=rt.ingest('CASE-52074E40');rt.claim()
    monkeypatch.setattr(sdk,'recordings',lambda ctx:[])
    monkeypatch.setattr('app.image_evidence.eligible',lambda ctx:[])
    class ScopedTools:
        def __init__(self,rid,cid,client):
            self.rid=rid;self.ctx={'case_id':cid,'accounts':['A-02'],'families':['size_outlier']};self.tokens=0
        def call(self,name,query):
            row={'evidence_id':'E-'+name,'source_type':name,'text':'Order documented.','status':'available'}
            rt.remember(self.rid,row);return [row]
    monkeypatch.setattr(sdk,'EvidenceTools',ScopedTools)
    model=ScriptedModel();monkeypatch.setattr(sdk,'create_sdk_model',lambda api:model)
    return run,model


def test_real_sdk_runner_executes_tools_and_two_structured_agents(workflow,monkeypatch):
    run,model=workflow
    original=Runner.run;calls=[]
    async def observed(agent,*args,**kwargs):
        assert isinstance(agent,Agent)
        calls.append(agent.name)
        return await original(agent,*args,**kwargs)
    monkeypatch.setattr(Runner,'run',observed)
    result=run_investigation(run)
    assert result['status']=='ready_for_review',result['error']
    assert calls==['Trade Surveillance Investigator','Surveillance Report Writer','Evidence Support Reviewer']
    assert BASE <= set(model.names)
    assert model.names.index('record_initial_assessment')>max(model.names.index(n) for n in BASE)
    assert model.names[-1]=='finish_investigation'
    assert result['report']['recommendation']=='standard_review'
    assert result['reviews']==[] and result['notification']['status']=='pending'
    assert all(e['payload']['execution_engine']=='openai_agents_sdk' for e in result['events'] if e['kind']=='model_response')


def test_sdk_cannot_finish_before_required_checks(workflow,monkeypatch):
    run,_=workflow;model=ScriptedModel(bypass=True)
    monkeypatch.setattr(sdk,'create_sdk_model',lambda api:model)
    result=run_investigation(run)
    assert result['status']=='manual_review'
    assert result['report'] is None and result['notification'] is None


def test_direct_tool_callback_enforces_state_and_budget(workflow,monkeypatch):
    run,_=workflow;state=sdk.InvestigationState(run)
    output=json.loads(state.invoke('finish_investigation',json.dumps({'reason':'Skip checks','query':''})))
    assert output['result']['status']=='validation_error' and not state.finished
    monkeypatch.setattr(settings,'max_tool_calls',1)
    with pytest.raises(RuntimeError,match='budget'):state.invoke('read_trades',json.dumps({'reason':'Read','query':''}))


def test_sdk_tools_have_no_analyst_decision_capabilities():
    tools=sdk.sdk_tools()
    assert all(isinstance(t,FunctionTool) for t in tools)
    assert not {'escalate','mark_reviewed','submit_analyst_decision','send_email'} & {t.name for t in tools}


def test_invalid_citations_exhaust_one_repair_then_hold_for_human(workflow,monkeypatch):
    import sys
    run,_=workflow
    invalid=json.loads(json.dumps(REPORT))
    invalid['summary']['citations'][0]['quote']='A fabricated source quotation.'
    monkeypatch.setattr(sys.modules[__name__],'REPORT',invalid)
    result=run_investigation(run)
    assert result['status']=='manual_review' and result['report'] is None
    assert result['notification'] is None and result['reviews']==[]
    validations=[e for e in result['events'] if e['kind']=='validation']
    assert len(validations)==2 and all(not e['payload']['passed'] for e in validations)
    assert result['evidence']


def test_expired_deadline_stops_before_model_call(workflow,monkeypatch):
    run,model=workflow
    monkeypatch.setattr(settings,'max_job_seconds',-1)
    result=run_investigation(run)
    assert result['status']=='manual_review' and not model.names
    assert result['report'] is None and result['notification'] is None
