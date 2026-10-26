import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'sources'), str(ROOT/'sources/bestfgs-project/src'),
               str(ROOT/'sources/bestfgs-project/tests'), str(ROOT/'integration')]
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_monitor import parse_review, MONITOR_SYSTEM
from bestfgs.lean_audit import read_trace
from bestfgs.models import TaskSpec, ModelCallError
from bestfgs.monitor_config import monitor_config
from bestfgs.retrac_adapter import RetracModelConfig, OpenAICompatibleJSONClient
from test_lean import FakeEnvironment, Scripted, SUBMIT, run_action
from outcomes import classify
from supervisor import disposition
from audit import Audit, JSONClientAudit


def review(verdict='progress', ids=None, memories=None):
    return dict(verdict=verdict, reason='The observations distinguish the input hypothesis.',
                evidence_ids=ids or ['E1', 'E2'], next_check='Inspect a different input header',
                memories=memories or [])


def memory(eid='E2', **changes):
    value = dict(kind='blocker', conclusion='This input produced the observed parser error.',
        condition='Same input and configuration; external state must be rechecked.',
        targets=[], operation='fail', next_step='Inspect input header', evidence_ids=[eid],
        support=[dict(evidence_id=eid, field='stderr', quote='same error')])
    value.update(changes)
    return value


class SemanticTests(unittest.TestCase):
    def exercise(self, actions, reviews, *, config=None, advisor=(), env=None, monitor=None):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        actor, adviser = Scripted(actions), Scripted(advisor)
        observer = monitor or Scripted(reviews)
        environment = env or FakeEnvironment()
        cfg = config or LeanConfig(semantic_monitor=True, auto_memory=True,
            monitor_cooldown_tools=2, monitor_interval_tools=3, max_monitor_calls=3)
        runner = LeanTaskRunner(environment, actor, adviser, cfg, Path(tmp.name)/'audit', monitor_client=observer)
        result = runner.run(TaskSpec('test', 'Produce the required artifact'))
        events = read_trace(Path(tmp.name)/'audit/events.jsonl')
        self.assertIsNone(result['error_type'], result)
        return result, runner, events, actor, observer, adviser

    def test_different_commands_semantic_stall_triggers_advisor_not_execution(self):
        result, runner, events, actor, monitor, advisor = self.exercise(
            [run_action('fail','A'), run_action('fail','B'), run_action('write','new'), SUBMIT],
            [review('stalled')], advisor=[dict(alternatives=[])])
        self.assertTrue(result['submitted'])
        self.assertEqual(result['monitor_rounds'], 1)
        self.assertEqual(result['advisor_rounds'], 1)
        self.assertEqual(result['interaction_rounds'], 6)
        self.assertEqual(result['tool_calls'], 3)
        self.assertEqual(runner.counts['semantic_stalls'], 1)
        self.assertTrue(any(e['event']=='advisor_trigger' and e['trigger']=='semantic_stall' for e in events))
        self.assertEqual(actor.prompts[2]['fixed_context']['semantic_review']['verdict'], 'stalled')
        self.assertNotIn('conversation', monitor.prompts[0])
        self.assertEqual(runner.environment.value, 'new')

    def test_read_only_new_information_does_not_force_advice(self):
        result, _, _, _, _, advisor = self.exercise([run_action('read','A'),run_action('read','B'),SUBMIT],
                                                    [review('progress')])
        self.assertTrue(result['submitted']); self.assertEqual(advisor.prompts, [])

    def test_necessary_retry_can_defer_heuristic_advice(self):
        cfg = LeanConfig(semantic_monitor=True, monitor_cooldown_tools=3, monitor_interval_tools=4)
        result, _, events, _, _, adviser = self.exercise([run_action('fail')]*3+[SUBMIT],
            [review('necessary_retry', ['E2','E3'])], config=cfg)
        self.assertTrue(result['submitted']); self.assertEqual(adviser.prompts, [])
        self.assertTrue(any(e['event']=='heuristic_advice_deferred' for e in events))

    def test_periodic_review_even_when_workspace_changes(self):
        result, _, events, _, mon, _ = self.exercise([run_action('write',str(i)) for i in range(3)]+[SUBMIT],
                                                   [review(ids=['E2','E3'])])
        self.assertTrue(result['submitted']); self.assertEqual(len(mon.prompts),1)
        self.assertEqual(mon.prompts[0]['trigger'], 'periodic_review')

    def test_candidate_memory_admitted_quoted_and_visible_to_actor(self):
        result, runner, events, actor, _, _ = self.exercise(
            [run_action('fail','A'),run_action('fail','B'),SUBMIT], [review(memories=[memory()])])
        self.assertEqual(runner.counts['auto_memories_admitted'],1)
        item = actor.prompts[2]['fixed_context']['memories'][0]
        self.assertEqual(item['origin'],'semantic_monitor')
        self.assertEqual(item['support'][0]['quote'],'same error')
        self.assertIn('not_verified',item['status'])
        self.assertTrue(result['submitted'])
        self.assertTrue(any(e['event']=='auto_memory_candidate' for e in events))

    def test_unquoted_invented_and_historical_memories_rejected(self):
        bad = [memory(eid='E99'), memory(support=[dict(evidence_id='E2',field='stderr',quote='invented')]),
               memory(support=[]), memory(targets=['../outside']), memory(targets='bad')]
        for item in bad:
            with self.subTest(item=item):
                result, runner, _, _, _, _ = self.exercise(
                    [run_action('fail','A'),run_action('fail','B'),SUBMIT],[review(memories=[item])])
                self.assertTrue(result['submitted']); self.assertEqual(len(runner.memory.items),0)
                self.assertEqual(runner.counts['auto_memories_rejected'],1)
        cfg = LeanConfig(auto_memory=True, monitor_cooldown_tools=2,monitor_interval_tools=2)
        _, runner, _, _, _, _ = self.exercise([run_action('fail'),run_action('write','changed'),SUBMIT],
            [review(memories=[memory('E1')])],config=cfg)
        self.assertEqual(len(runner.memory.items),0)

    def test_duplicate_lesson_with_new_evidence_is_not_reinserted(self):
        actions=[run_action('fail','A'),run_action('fail','B'),run_action('fail','C',uses_memory=['M1']),
                 run_action('fail','D',uses_memory=['M1']),SUBMIT]
        result, runner, events, _, _, _ = self.exercise(actions,
            [review(memories=[memory()]),review(ids=['E3','E4'],memories=[memory('E4')])])
        self.assertTrue(result['submitted']); self.assertEqual(runner.counts['auto_memories_admitted'],1)
        self.assertTrue(any(e['event']=='auto_memory_duplicate' for e in events))

    def test_monitor_and_memory_ablation_independent(self):
        for loop, mem in [(True,False),(False,True),(False,False)]:
            cfg=LeanConfig(semantic_monitor=loop,auto_memory=mem,monitor_cooldown_tools=2,monitor_interval_tools=3)
            result, runner, _, actor, mon, _ = self.exercise([run_action('fail','A'),run_action('fail','B'),SUBMIT],
                [review('stalled',memories=[memory()])],config=cfg,advisor=[dict(alternatives=[])])
            self.assertTrue(result['submitted'])
            self.assertEqual(runner.counts['auto_memories_admitted'],int(mem))
            self.assertEqual(runner.counts['advisor_calls'],int(loop))
            self.assertEqual(len(mon.prompts),int(loop or mem))
            self.assertEqual('semantic_review' in actor.prompts[-1]['fixed_context'],loop)

    def test_automatic_memory_reconsiders_repeat_then_tracks_real_outcome(self):
        result, runner, events, actor, _, _ = self.exercise(
            [run_action('fail','A'),run_action('fail','B'),run_action('fail','C'),
             run_action('write','different approach'),SUBMIT], [review(memories=[memory()])])
        self.assertTrue(result['submitted']); self.assertEqual(result['tool_calls'],3)
        self.assertEqual(runner.counts['memory_interventions'],1)
        self.assertEqual(runner.counts['memory_followup_workspace_changed'],1)
        self.assertFalse(any(a['argv']==['fail','C'] for a in runner.environment.executed))
        self.assertTrue(any(e['event']=='memory_followup_outcome' for e in events))
        self.assertEqual(actor.prompts[-1]['fixed_context']['semantic_review']['applicability'],
                         'historical_workspace_changed_recheck_required')

    def test_dependency_change_marks_auto_memory_historical(self):
        item=memory(targets=['data.csv'])
        result, runner, _, actor, _, _ = self.exercise(
            [run_action('fail','A'),run_action('fail','B'),run_action('artifact','data.csv','new',uses_memory=['M1']),SUBMIT],
            [review(memories=[item])])
        self.assertTrue(result['submitted'])
        self.assertEqual(actor.prompts[-1]['fixed_context']['memories'][0]['applicability'],
                         'target_dependencies_changed_or_unknown_recheck_required')

    def test_public_check_event_triggers_before_periodic_deadline(self):
        result,_,_,_,mon,_=self.exercise([run_action('write','A'),run_action('pytest'),SUBMIT],
                                       [review()])
        self.assertTrue(result['submitted'])
        self.assertEqual(mon.prompts[0]['trigger'],'public_check_completed_not_task_success')

    def test_malformed_nested_candidate_is_rejected_without_crashing_actor(self):
        for item in [memory(kind={}),memory(operation=[]),memory(next_step=[]),
                     memory(support=[dict(evidence_id='E2',field={},quote='same error')])]:
            result,runner,_,_,_,_=self.exercise([run_action('fail','A'),run_action('fail','B'),SUBMIT],
                                               [review(memories=[item])])
            self.assertTrue(result['submitted']); self.assertEqual(runner.counts['auto_memories_rejected'],1)

    def test_monitor_error_is_nonfatal_no_actor_error_streak(self):
        for error in [ModelCallError('provider unavailable'),ValueError('bad JSON')]:
            result,runner,_,_,_,_=self.exercise([run_action('read')]*2+[SUBMIT],[error])
            self.assertTrue(result['submitted']); self.assertEqual(runner.counts['monitor_deferred'],1)
            self.assertEqual(runner.counts['protocol_errors'],0)

    def test_monitor_auth_disables_monitor_not_actor(self):
        mon=Scripted([ModelCallError('Unauthorized')]); mon.last_failure_detail='http_401'
        result,runner,events,_,_,_=self.exercise([run_action('read')]*6+[SUBMIT],[],monitor=mon)
        self.assertTrue(result['submitted']); self.assertEqual(result['monitor_rounds'],1)
        classified=classify(dict(method='bestfgs',process_exit_code=0,verifier_result={}),events)
        self.assertEqual(classified['method_issues'],[])
        self.assertEqual(classified['optional_monitor_errors'],1)
        self.assertFalse(disposition(dict(classification=classified),events)['blocks_dispatch'])
        self.assertEqual(disposition(dict(classification=classified),events)['optional_monitor_errors'],1)

    def test_monitor_budget_reserves_last_actor_call(self):
        cfg=LeanConfig(semantic_monitor=True,max_turns=3,monitor_cooldown_tools=2,monitor_interval_tools=2)
        result,runner,_,_,mon,_=self.exercise([run_action('read')]*2+[SUBMIT],[],config=cfg)
        self.assertTrue(result['submitted']); self.assertEqual(result['interaction_rounds'],3)
        self.assertEqual(mon.prompts,[])

    def test_monitor_cap_and_cooldown(self):
        cfg=LeanConfig(semantic_monitor=True,max_monitor_calls=2,monitor_cooldown_tools=2,monitor_interval_tools=3)
        result,_,_,_,mon,_=self.exercise([run_action('read')]*10+[SUBMIT],
            [review(),review(ids=['E3','E4'])],config=cfg)
        self.assertTrue(result['submitted']); self.assertEqual(len(mon.prompts),2)
        self.assertEqual(result['interaction_rounds'],13)

    def test_oversized_task_skips_optional_review_no_api(self):
        cfg=LeanConfig(semantic_monitor=True,monitor_cooldown_tools=2,monitor_interval_tools=3,monitor_context_chars=8000)
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        mon=Scripted([])
        runner=LeanTaskRunner(FakeEnvironment(),Scripted([run_action('read')]*2+[SUBMIT]),Scripted([]),
            cfg,Path(tmp.name)/'audit',monitor_client=mon)
        result=runner.run(TaskSpec('large','x'*7000))
        self.assertTrue(result['submitted']); self.assertEqual(mon.prompts,[])
        self.assertEqual(runner.counts['monitor_deferred'],1)

    def test_strict_schema_rejects_single_step_stall_and_bad_ids(self):
        for response in [review('stalled',['E1']),review('stalled',['E1','E1']),review(ids=['E99']),
                         dict(review(),verdict='stop'),dict(review(),verdict={}),dict(review(),memories=[{}, {}, {}]),
                         dict(review(),next_check=[]), dict(review(),reason='')]:
            with self.assertRaises(ValueError): parse_review(response,{'E1':{},'E2':{}})

    def test_explicit_independent_client_and_flag_validation(self):
        with self.assertRaises(ValueError): LeanConfig(semantic_monitor=1)
        with self.assertRaises(ValueError): LeanConfig(monitor_window=49)
        with self.assertRaises(ValueError):
            LeanTaskRunner(FakeEnvironment(),Scripted([]),Scripted([]),LeanConfig(auto_memory=True),Path('unused'))
        actor=Scripted([])
        with self.assertRaises(ValueError):
            LeanTaskRunner(FakeEnvironment(),actor,Scripted([]),LeanConfig(),Path('unused'),monitor_client=actor)

    def test_model_default_and_independent_small_model_selection(self):
        base=RetracModelConfig('solver','https://example.invalid','fixture',provider='deepseek')
        same=monitor_config(base)
        self.assertEqual(same.model_name,'solver'); self.assertEqual(same.request_attempts,1)
        self.assertEqual(same.max_tokens,1536); self.assertEqual(same.max_wall_time_seconds,45)
        self.assertEqual(monitor_config(base,model_name='small').model_name,'small')
        with self.assertRaises(ValueError): monitor_config(base,provider='openai')
        with patch.dict(os.environ,{'MONITOR_KEY':'separate-fixture'}):
            alt=monitor_config(base,model_name='small',provider='openai',base_url='https://small.invalid',api_key_env='MONITOR_KEY')
            self.assertEqual(alt.api_key,'separate-fixture'); self.assertEqual(alt.provider,'openai')
            keyonly=monitor_config(base,api_key_env='MONITOR_KEY')
            self.assertEqual(keyonly.base_url,base.base_url)

    def test_real_wire_has_short_context_no_actor_dialogue_and_one_attempt(self):
        wires=[]
        base=RetracModelConfig('solver','https://example.invalid','fixture',provider='deepseek')
        client=OpenAICompatibleJSONClient(monitor_config(base))
        def request(instance,**kwargs):
            body=json.loads(kwargs['encoded']); wires.append(body)
            return json.dumps(dict(choices=[dict(message=dict(content=json.dumps(review())),finish_reason='stop')])).encode()
        with patch.object(OpenAICompatibleJSONClient,'_request_bytes',request):
            result,_,_,_,_,_=self.exercise([run_action('read')]*2+[SUBMIT],[],monitor=client)
        self.assertTrue(result['submitted']); self.assertEqual(len(wires),1)
        self.assertEqual(len(wires[0]['messages']),2)
        self.assertLess(len(json.dumps(wires[0]['messages'],ensure_ascii=False)),20000)
        self.assertEqual(wires[0]['max_tokens'],1536)

    def test_outer_audit_preserves_monitor_timeout_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            import time
            base=RetracModelConfig('solver','https://example.invalid','fixture',provider='deepseek')
            client=OpenAICompatibleJSONClient(monitor_config(base))
            wrapped=JSONClientAudit(client,Audit(Path(tmp)/'audit.jsonl',['fixture']),'monitor',time.monotonic()+500)
            with patch.object(OpenAICompatibleJSONClient,'complete_json',return_value=review()):
                wrapped.complete_json(system_prompt='test',user_prompt='test')
            self.assertEqual(client.config.max_wall_time_seconds,45)
            self.assertEqual(client.config.timeout_seconds,30)

    def test_harbor_separate_monitor_key_creates_one_redacted_audit(self):
        import ast
        tree=ast.parse((ROOT/'integration/transport.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='trial_audit')
        namespace=dict(Audit=Audit,os=os)
        exec(compile(ast.Module(body=[node],type_ignores=[]),'transport.py','exec'),namespace)
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'MONITOR_TEST_KEY':'monitor-secret'}):
            path=Path(tmp)/'audit.jsonl'
            audit=namespace['trial_audit'](path,'actor-secret','MONITOR_TEST_KEY')
            audit.emit('fixture',text='actor-secret monitor-secret')
            self.assertNotIn('actor-secret',path.read_text())
            self.assertNotIn('monitor-secret',path.read_text())


if __name__=='__main__': unittest.main()
