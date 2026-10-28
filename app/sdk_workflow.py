"""Investigation orchestration executed by OpenAI Agents SDK Agent + Runner."""
import asyncio
import json
import time
from agents import Agent, Runner, FunctionTool, ModelSettings, OpenAIResponsesModel, RunConfig, RunHooks
from openai import AsyncOpenAI
from pydantic import ValidationError
from openai.types.shared import Reasoning
from . import runtime as rt
from .config import settings,reasoning_options,output_budget
from .agent import BASE, EXTRA, INSTRUCTIONS, definitions, check_claim, validate_report, check_grounding_verdict
from .models import ToolArgs, InitialAssessment, Promotion, Report, GroundingVerdict
from .evidence_tools import EvidenceTools, DESCRIPTIONS
from .indexes import client
from .investigation_extensions import recordings
from .investigation_prompts import DRAFT_INSTRUCTIONS, REVIEW_INSTRUCTIONS


def create_sdk_model(async_client):
    return OpenAIResponsesModel(settings.openai_model, async_client)


class InvestigationState:
    def __init__(self, run):
        self.run = run
        self.rid = run['run_id']
        self.started = time.monotonic()
        self.deadline = self.started + settings.max_job_seconds
        self.client = client()
        self.tools = EvidenceTools(self.rid, run['case_id'], self.client)
        self.tools.deadline = self.deadline
        self.ctx = self.tools.ctx
        self.ctx['recording_count'] = len(recordings(self.ctx))
        self.mandatory = set(BASE) | {'reconstruct_timeline', 'retrieve_prior_cases'}
        from .image_evidence import eligible
        self.ctx['image_count']=len(eligible(self.ctx))
        if self.ctx['image_count']:self.mandatory.add('review_image_evidence')
        if self.ctx['recording_count']: self.mandatory.add('transcribe_calls')
        if rt.submitted_sources(self.rid): self.mandatory.add('read_submitted_evidence')
        for family in self.ctx['families']: self.mandatory |= EXTRA.get(family, set())
        if set(self.ctx['families']) & {'marking_close', 'spoofing_layering', 'front_running'}:
            self.mandatory.add('analyze_execution_patterns')
        self.done = set()
        self.failed_tools = set()
        self.depth = 'lightweight'
        self.initial = False
        self.initial_view = None
        self.finished = False
        self.calls = 0
        self.tokens = 0

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0: raise TimeoutError('Investigation time budget exhausted')
        return remaining

    def needs_deep(self):
        return (self.run.get('required_depth') == 'deep' or
                any(r['status'] != 'available' for r in rt.recalled(self.rid).values()) or
                bool(set(self.ctx['families']) - {'size_outlier'}) or
                self.initial_view in ('concerning', 'inconclusive'))

    def allowed(self):
        if BASE <= self.done and not self.initial: return {'record_initial_assessment'}
        if self.initial and self.needs_deep() and self.depth == 'lightweight': return {'promote_to_deep'}
        return {spec['name'] for spec in definitions(self.done, self.initial, self.depth, self.mandatory, self.needs_deep())}

    def control_state(self):
        state = {'required_checks_remaining': sorted(self.mandatory - self.done),
                 'initial_assessment_recorded': self.initial, 'depth': self.depth}
        if BASE <= self.done and not self.initial: state['next_control_step'] = 'record_initial_assessment with an exact citation_option'
        elif self.initial and self.needs_deep() and self.depth == 'lightweight': state['next_control_step'] = 'promote_to_deep, then complete remaining checks'
        elif self.initial and not (self.mandatory - self.done): state['next_control_step'] = 'finish_investigation'
        return state

    def invoke(self, name, arguments):
        self.remaining()
        self.calls += 1
        if self.calls > settings.max_tool_calls: raise RuntimeError('Tool-call budget exhausted')
        raw = json.loads(arguments)
        reason = str(raw.get('reason', ''))[:300]
        rt.audit(self.rid, 'tool_started', {'tool': name, 'reason': reason, 'query': str(raw.get('query', ''))[:500]})
        try:
            if name not in self.allowed(): raise ValueError('Tool is unavailable in this stage; follow control_state')
            if name == 'record_initial_assessment':
                assessment = InitialAssessment.model_validate(raw)
                errors = check_claim(assessment.summary, rt.recalled(self.rid))
                if BASE - self.done: errors.append('Complete essential checks before initial assessment')
                if errors: raise ValueError('; '.join(errors))
                self.initial = True
                self.initial_view = assessment.assessment
                if self.initial_view != 'plausibly_benign' and self.ctx['families'] == ['size_outlier']:
                    self.mandatory |= {'search_communications', 'restrictions_authority'}
                rt.audit(self.rid, 'initial_assessment', assessment.model_dump())
                output = {'recorded': True, 'provisional': True}
            elif name == 'promote_to_deep':
                promotion = Promotion.model_validate(raw)
                if not self.initial: raise ValueError('Initial assessment is required before promotion')
                if not set(promotion.evidence_ids) <= set(rt.recalled(self.rid)): raise ValueError('Promotion must cite retrieved evidence')
                self.depth = 'deep'
                rt.update(self.rid, depth=self.depth)
                rt.audit(self.rid, 'depth_changed', promotion.model_dump() | {'depth': self.depth})
                output = {'depth': self.depth}
            elif name == 'finish_investigation':
                ToolArgs.model_validate(raw)
                if self.mandatory - self.done or not self.initial: raise ValueError('Required investigation checks remain incomplete')
                if self.needs_deep() and self.depth != 'deep': raise ValueError('Deep investigation is required')
                if self.failed_tools & self.mandatory: raise RuntimeError('A mandatory evidence tool failed; human attention required')
                self.finished = True
                output = {'ready_to_draft': True}
            elif name in DESCRIPTIONS:
                args = ToolArgs.model_validate(raw)
                self.tools.client = self.client.with_options(timeout=min(90 if settings.openai_model == 'gpt-6.1-sol' else 40, self.remaining()), max_retries=0 if settings.openai_model == 'gpt-6.1-sol' else 1)
                output = self.tools.call(name, args.query)
                self.done.add(name)
            else: raise ValueError('Tool is not authorized')
            rt.audit(self.rid, 'tool_completed', {'tool': name, 'reason': reason,
                'evidence_ids': [r['evidence_id'] for r in output] if isinstance(output, list) else [],
                'result': output if isinstance(output, dict) else {'record_count': len(output)}})
        except (ValueError, ValidationError) as exc:
            output = {'status': 'validation_error', 'message': str(exc)[:600]}
            rt.audit(self.rid, 'tool_rejected', {'tool': name, 'message': output['message']})
        except Exception as exc:
            record = self.tools.doc('tool_failure', f'{name} failed with {type(exc).__name__}. No conclusion about underlying activity can be drawn from this failure.', status='unavailable')
            output = [record]
            self.done.add(name)
            self.failed_tools.add(name)
            rt.audit(self.rid, 'tool_failed', {'tool': name, 'error_class': type(exc).__name__, 'evidence_id': record['evidence_id']})
        return json.dumps({'result': output, 'control_state': self.control_state()}, ensure_ascii=False)


def sdk_tools():
    tools = []
    for spec in definitions():
        name = spec['name']
        async def invoke(ctx, arguments, name=name):
            return await asyncio.to_thread(ctx.context.invoke, name, arguments)
        def enabled(ctx, agent, name=name):
            return name in ctx.context.allowed()
        tools.append(FunctionTool(name=name, description=spec['description'], params_json_schema=spec['parameters'],
                                  on_invoke_tool=invoke, is_enabled=enabled, strict_json_schema=True))
    return tools


class InvestigationHooks(RunHooks):
    def __init__(self, state, stage): self.state = state; self.stage = stage
    async def on_llm_start(self, context, agent, system_prompt, input_items): self.state.remaining()
    async def on_llm_end(self, context, agent, response):
        self.state.tokens += response.usage.total_tokens
        rt.audit(self.state.rid, 'model_response', {'response_id': response.response_id, 'stage': self.stage,
            'model': settings.openai_model, 'tokens': response.usage.total_tokens, 'execution_engine': 'openai_agents_sdk', 'agent': agent.name})


async def run_sdk(state, agent, input, stage, max_turns):
    remaining = state.remaining()
    return await asyncio.wait_for(Runner.run(agent, input, context=state, max_turns=max_turns,
        hooks=InvestigationHooks(state, stage), run_config=RunConfig(
            workflow_name='Trade Surveillance Investigation', group_id=state.run['case_id'],
            tracing_disabled=not settings.openai_tracing_enabled, trace_include_sensitive_data=True)), timeout=remaining)


async def execute(state):
    async with AsyncOpenAI(api_key=settings.openai_api_key, timeout=90 if settings.openai_model == 'gpt-6.1-sol' else 40, max_retries=0 if settings.openai_model == 'gpt-6.1-sol' else 1) as api:
        model = create_sdk_model(api)
        investigator = Agent(name='Trade Surveillance Investigator', model=model, instructions=INSTRUCTIONS,
            tools=sdk_tools(), model_settings=ModelSettings(max_tokens=output_budget(2200), reasoning=Reasoning(**reasoning_options()['reasoning']) if reasoning_options() else None, parallel_tool_calls=False, tool_choice='required', store=True),
            reset_tool_choice=False, tool_use_behavior={'stop_at_tool_names': ['finish_investigation']})
        result = await run_sdk(state, investigator, json.dumps({'case': state.ctx, 'mandatory_tools': sorted(state.mandatory),
            'reviewer_request': state.run.get('review_request'), 'tool_budget': settings.max_tool_calls}), 'tool_selection', settings.max_tool_calls + 1)
        if not state.finished or state.mandatory - state.done or state.failed_tools & state.mandatory:
            raise RuntimeError('Investigation ended without completing mandatory checks')
        rt.audit(state.rid, 'draft_started', {'depth': state.depth})
        history = result.to_input_list()
        records = rt.recalled(state.rid)
        writer = Agent(name='Surveillance Report Writer', model=model, instructions=INSTRUCTIONS + DRAFT_INSTRUCTIONS,
                       output_type=Report, model_settings=ModelSettings(max_tokens=output_budget(5000), reasoning=Reasoning(**reasoning_options()['reasoning']) if reasoning_options() else None, store=True))
        reviewer = Agent(name='Evidence Support Reviewer', model=model, instructions=REVIEW_INSTRUCTIONS,
                         output_type=GroundingVerdict, model_settings=ModelSettings(max_tokens=output_budget(1500), reasoning=Reasoning(**reasoning_options()['reasoning']) if reasoning_options() else None, store=True))
        feedback = ''; rejected = None
        for attempt in range(2):
            draft_input = history + ([{'role':'assistant','content':json.dumps(rejected)}] if rejected else []) + [
                {'role':'user','content':('Revise only the flagged unsupported claims. ' if rejected else 'Produce the final cited draft now. ') + feedback}]
            draft = await run_sdk(state, writer, draft_input, 'draft', 1)
            report = draft.final_output_as(Report, raise_if_incorrect_type=True)
            rt.audit(state.rid, 'draft_candidate', {'attempt': attempt + 1, 'report': report.model_dump(), 'provisional': True})
            errors = validate_report(report, records)
            if report.assessment == 'concerning' and state.depth != 'deep': errors.append('Concerning assessment requires deep investigation')
            if 'pre_announcement' in state.ctx['families'] and report.assessment == 'concerning' and 'access_relationships' not in state.done:
                errors.append('Confidential-information escalation requires access verification')
            review = await run_sdk(state, reviewer, json.dumps({'case': state.ctx, 'report': report.model_dump(), 'evidence': list(records.values())}), 'support_review', 1)
            verdict = review.final_output_as(GroundingVerdict, raise_if_incorrect_type=True)
            rt.audit(state.rid, 'grounding_review', verdict.model_dump() | {'attempt': attempt + 1, 'method': 'independent SDK agent review; not proof of correctness'})
            check_grounding_verdict(report, verdict)
            if not verdict.supported: errors += verdict.issues
            rt.audit(state.rid, 'validation', {'attempt': attempt + 1, 'passed': not errors, 'issues': errors})
            if not errors:
                rt.finish(state.rid, report.model_dump(), state.tokens + state.tools.tokens, round(time.monotonic() - state.started, 2))
                return
            rejected = report.model_dump()
            feedback = 'Preserve supported claims; remove or qualify rejected claims. Flagged claims: ' + json.dumps(verdict.flagged_claims) + \
                ' Validation issues: ' + json.dumps(errors) + ' Unavailable source IDs: ' + json.dumps([eid for eid,r in records.items() if r['status'] != 'available']) + \
                ' Exact quotation choices: ' + json.dumps({eid: r.get('citation_options', [r['text']])[:8] for eid,r in records.items()})
        raise RuntimeError('Draft failed citation or support checks after one repair')


def investigate(run):
    state = InvestigationState(run)
    rt.audit(state.rid, 'investigation_started', {'model': settings.openai_model, 'depth': state.depth,
        'mandatory_checks': sorted(state.mandatory), 'controls_version': '2026-10-sdk-v1', 'execution_engine': 'openai_agents_sdk',
        'policy_vector_store': rt.meta_get('policy_index', {}).get('vector_store_id')})
    try: asyncio.run(execute(state))
    except Exception as exc:
        message = str(exc)[:700] if isinstance(exc, (ValueError, RuntimeError, TimeoutError)) else type(exc).__name__ + '; investigation needs human attention'
        rt.update(state.rid, status='manual_review', error=message, tokens=state.tokens + state.tools.tokens, elapsed=round(time.monotonic() - state.started, 2))
        rt.audit(state.rid, 'manual_review_required', {'reason': message, 'evidence_preserved': True})
    return rt.details(state.rid)
