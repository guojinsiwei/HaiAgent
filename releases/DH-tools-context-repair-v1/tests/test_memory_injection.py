import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'sources/bestfgs-project/src'), str(ROOT/'sources/bestfgs-project/tests')]
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_audit import read_trace
from bestfgs.memory_injection import reserved_view, validate_review, MEMORY_INSTRUCTION, MEMORY_EXAMPLES
from bestfgs.lean_conversation import Conversation
from bestfgs.retrac_adapter import OpenAICompatibleJSONClient, RetracModelConfig
from bestfgs.models import TaskSpec
from test_lean import FakeEnvironment, Scripted, run_action, SUBMIT
from test_conversation import Capture


def review(action, decision='recheck'):
    return dict(memory_review=dict(ids=['M1'], decision=decision,
        observed_result='The config parser failed on the recorded input.',
        applicability='Check whether source and input still match the failed state.',
        reason='Recheck the observed config failure using a different command.'),
        strategy_adjustment='Use a different check and compare its output with the prior parser failure.', **action)


class InjectionTests(unittest.TestCase):
    def exercise(self, actions, **cfg):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        actor = Capture(actions)
        runner = LeanTaskRunner(FakeEnvironment(), actor, Scripted([]),
            LeanConfig(**(dict(memory_reliability=True, auto_memory=True,
                max_advisor_calls=0, max_turns=30, max_tools=20) | cfg)),
            Path(temp.name)/'audit', monitor_client=Scripted([]))
        result = runner.run(TaskSpec('fixture', 'Fix config parser'))
        return result, runner, actor, read_trace(Path(temp.name)/'audit/events.jsonl')

    def test_tail_memory_and_system_rule_reach_actual_model_call(self):
        result, runner, actor, events = self.exercise(
            [run_action('fail'), run_action('fail'), review(run_action('write', 'new')), review(SUBMIT)])
        self.assertTrue(result['submitted'], result)
        call = actor.calls[2]
        self.assertIn(MEMORY_INSTRUCTION, call['system_prompt'])
        payload = json.loads(call['user_prompt'])
        self.assertEqual(list(payload)[-1], 'fixed_context')
        self.assertEqual(list(payload['fixed_context'])[-2:], ['memories', 'memory_action_contract'])
        self.assertEqual(payload['fixed_context']['memories'][0]['id'], 'M1')
        final = [e for e in events if e['event']=='final_prompt'][2]
        self.assertEqual(final['messages'][-1]['content'], call['user_prompt'])
        self.assertEqual(final['messages'][0]['content'], call['system_prompt'])
        self.assertTrue(any(e['event']=='memory_decision_review' for e in events))
        self.assertEqual(result['interaction_rounds'], 4)  # no extra reasoning-model call

    def test_missing_review_does_not_execute_command(self):
        result, runner, actor, events = self.exercise([run_action('fail'), run_action('fail'),
            run_action('write', 'NOT_ALLOWED'), review(run_action('write', 'allowed')), review(SUBMIT)])
        self.assertTrue(result['submitted'], result)
        self.assertEqual(result['tool_calls'], 3)
        self.assertNotIn('NOT_ALLOWED', [a['argv'][-1] for a in runner.environment.executed])
        self.assertTrue(any(e['event']=='protocol_error' and 'memory_review' in e['protocol_error'] for e in events))

    def test_stale_memory_retains_warning_not_a_hard_fact(self):
        record = dict(id='M1', kind='blocker', conclusion='old failure', condition='old source',
            targets=['source.py'], evidence_ids=['E1'],
            applicability='target_dependencies_changed_or_unknown_recheck_required')
        shown, omitted = reserved_view([record], 3000)
        self.assertEqual(shown[0]['applicability'], record['applicability'])
        self.assertEqual(omitted, [])

    def test_compaction_does_not_mutate_store_or_truncate_conditions(self):
        records = [dict(id='M'+str(i), conclusion='x'*500, condition='y'*400,
            next_step='z'*400, evidence_ids=['E1'], support=[{'quote':'q'*300}]*3) for i in range(4)]
        original = copy.deepcopy(records)
        shown, omitted = reserved_view(records, 3000)
        self.assertTrue(shown); self.assertTrue(omitted)
        self.assertEqual(records, original)
        self.assertEqual(shown[0]['condition'], records[0]['condition'])
        self.assertNotIn('support', shown[0])

    def test_retry_requires_new_evidence_and_ids_must_be_visible(self):
        for action in (review(run_action('read'), 'justified_retry'),
                       dict(SUBMIT, memory_review={'ids':['M99'], 'decision':'apply', 'reason':'use it'})):
            with self.assertRaises(ValueError): validate_review(action, {'M1'}, True)
        good = review(run_action('read'), 'justified_retry')
        good['memory_review']['new_evidence'] = 'Input encoding was changed; compare parser stderr.'
        self.assertIsNotNone(validate_review(good, {'M1'}, True))

    def test_claiming_different_route_cannot_repeat_exact_failed_executable(self):
        result, runner, actor, events = self.exercise([run_action('fail'), run_action('fail'),
            review(run_action('fail'), 'different_route'), review(run_action('write','new')), review(SUBMIT)])
        self.assertTrue(result['submitted'], result)
        self.assertEqual(result['tool_calls'], 3)
        self.assertTrue(any(e['event']=='protocol_error' and 'same executable' in e['protocol_error'] for e in events))

    def test_reasoned_retry_with_a_discriminating_observation_is_allowed(self):
        retry = review(run_action('fail'), 'justified_retry')
        retry['memory_review']['new_evidence'] = 'Check whether the external dependency recovered; compare stderr.'
        retry.update(uses_memory=['M1'], memory_reason=retry['memory_review']['new_evidence'])
        result, runner, actor, events = self.exercise(
            [run_action('fail'), run_action('fail'), retry, review(SUBMIT)])
        self.assertTrue(result['submitted'], result)
        self.assertEqual(result['tool_calls'], 3)

    def test_review_summary_is_not_counted_as_a_changed_executable_action(self):
        action = run_action('read')
        self.assertEqual(LeanTaskRunner._action_core(action), LeanTaskRunner._action_core(review(action)))

    def test_review_and_adjustment_are_serialized_before_action(self):
        response = review(run_action('write','new'))
        encoded = json.dumps(response)
        self.assertEqual(list(response)[:3], ['memory_review','strategy_adjustment','action'])
        self.assertLess(encoded.index('"observed_result"'), encoded.index('"strategy_adjustment"'))
        self.assertLess(encoded.index('"strategy_adjustment"'), encoded.index('"action"'))
        self.assertIsNotNone(validate_review(response, {'M1'}, True))

    def test_action_first_response_is_refused_before_execution(self):
        wrong = dict(run_action('write','NOT_ALLOWED'),
            memory_review=review(SUBMIT)['memory_review'], strategy_adjustment='Modify and check source.')
        result, runner, actor, events = self.exercise([run_action('fail'), run_action('fail'),
            wrong, review(run_action('write','allowed')), review(SUBMIT)])
        self.assertTrue(result['submitted'], result)
        self.assertNotIn('NOT_ALLOWED', [a['argv'][-1] for a in runner.environment.executed])
        self.assertTrue(any(e['event']=='protocol_error' and 'first three keys' in e['protocol_error'] for e in events))

    def test_short_factual_review_and_concrete_adjustment_are_required(self):
        for field in ('observed_result', 'applicability', 'strategy_adjustment'):
            with self.subTest(field=field):
                response = review(SUBMIT)
                if field == 'strategy_adjustment': response[field] = ''
                else: response['memory_review'][field] = ''
                with self.assertRaisesRegex(ValueError, field): validate_review(response, {'M1'}, True)

    def test_both_demonstrations_validate_and_preserve_flat_action_contract(self):
        from bestfgs.lean_protocol import parse_action
        for example in MEMORY_EXAMPLES:
            response = example['response']
            ids = set(response['memory_review']['ids'])
            self.assertIsNotNone(validate_review(response, ids, True))
            self.assertEqual(parse_action(response)['action'], 'run')
            self.assertNotIn('next_action', response)
            self.assertIn(json.dumps(example, ensure_ascii=False), MEMORY_INSTRUCTION)
        self.assertEqual(MEMORY_EXAMPLES[0]['response']['memory_review']['decision'], 'different_route')
        self.assertEqual(MEMORY_EXAMPLES[1]['response']['memory_review']['decision'], 'justified_retry')
        self.assertTrue(MEMORY_EXAMPLES[1]['response']['memory_review']['new_evidence'])

    def test_demonstrations_are_not_claimed_as_task_facts(self):
        self.assertIn('NOT facts about your task', MEMORY_INSTRUCTION)
        self.assertIn('Never copy their IDs', MEMORY_INSTRUCTION)

    def test_archived_assistant_messages_keep_review_first_without_mutating_archive(self):
        conversation = Conversation()
        conversation.append(review(run_action('read')), {'stdout':'historical output'})
        before = copy.deepcopy(conversation.turns)
        history, stats = conversation.build('system', {'task':'current task'}, 16000)
        response = json.loads(next(m['content'] for m in history if m['role']=='assistant'))
        self.assertEqual(list(response)[:3], ['memory_review','strategy_adjustment','action'])
        self.assertEqual(before, conversation.turns)

    def test_adjustment_logged_but_not_claimed_as_verified_benefit(self):
        result, runner, actor, events = self.exercise([run_action('fail'), run_action('fail'),
            review(run_action('write','new')), review(SUBMIT)])
        decision = next(e for e in events if e['event']=='memory_decision_review')
        self.assertEqual(decision['strategy_adjustment'], review(SUBMIT)['strategy_adjustment'])
        self.assertFalse(decision['verified'])
        self.assertFalse(decision['causal_benefit_proven'])
        response = next(e for e in events if e['event']=='model_response' and 'memory_review' in e['response'])
        self.assertEqual(response['response_key_order'][:3], ['memory_review','strategy_adjustment','action'])

    def test_intervention_memory_is_reserved_even_if_generic_query_does_not_recall_it(self):
        _, runner, _, _ = self.exercise([SUBMIT])
        memory = dict(id='M9', kind='blocker', conclusion='nebula celestial astronomy',
            condition='celestial configuration', targets=[], next_step='inspect constellation',
            operation='', evidence_ids=['E1'], applicability='historical_recheck_required')
        runner.pending_memory_intervention = dict(id='MI1', matched_memories=[memory], instruction='Reconsider M9')
        panel = runner._panel()['fixed_context']
        self.assertEqual(panel['memories'][0]['id'], 'M9')
        self.assertEqual(panel['memory_intervention']['matched_memory_ids'], ['M9'])
        self.assertEqual(runner.pending_memory_intervention['matched_memories'], [memory])

    def test_disabled_memory_does_not_require_review_or_add_memory_instruction(self):
        result, runner, actor, events = self.exercise([SUBMIT], memory_enabled=False, auto_memory=False)
        self.assertTrue(result['submitted'], result)
        self.assertNotIn(MEMORY_INSTRUCTION, actor.calls[0]['system_prompt'])

    def test_config_rejects_invalid_reserve(self):
        for reserve in (0, 2000, 25000):
            with self.assertRaises(ValueError): LeanConfig(memory_reserve_chars=reserve)

    def test_wire_audit_matches_actual_attempt_and_retry_preserves_memory_tail(self):
        sent, audited = [], []
        def fake(client, **kwargs):
            sent.append(json.loads(kwargs['encoded']))
            value = '{bad' if len(sent)==1 else json.dumps(SUBMIT)
            return json.dumps(dict(choices=[dict(message=dict(content=value), finish_reason='stop')],
                usage=dict(prompt_tokens=1, completion_tokens=1))).encode()
        client = OpenAICompatibleJSONClient(RetracModelConfig('fixture','https://example.invalid','offline',
            provider='deepseek', request_attempts=2, parse_attempts=1))
        client.request_audit = lambda body, attempt: audited.append((copy.deepcopy(body), attempt))
        prompt = json.dumps(dict(fixed_context=dict(memories=[dict(id='M1', conclusion='failure')],
            memory_action_contract=dict(label='CURRENT MEMORY REVIEW'))))
        with patch.object(OpenAICompatibleJSONClient, '_request_bytes', fake), patch('time.sleep'):
            client.complete_json(system_prompt=MEMORY_INSTRUCTION, user_prompt=prompt)
        self.assertEqual([body for body, _ in audited], sent)
        self.assertEqual([attempt for _, attempt in audited], [1,2])
        self.assertNotIn('Authorization', json.dumps(audited))
        self.assertIn('CURRENT MEMORY REVIEW', sent[1]['messages'][-1]['content'])

    def test_final_prompt_log_is_redacted_and_history_not_lost(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        actor = Capture([run_action('write','fixture-private-key'), SUBMIT])
        runner = LeanTaskRunner(FakeEnvironment(), actor, Scripted([]), LeanConfig(),
            Path(temp.name)/'audit', secrets=('fixture-private-key',))
        result = runner.run(TaskSpec('fixture','write output'))
        self.assertTrue(result['submitted'])
        events = read_trace(Path(temp.name)/'audit/events.jsonl')
        prompts = [e for e in events if e['event']=='final_prompt']
        self.assertNotIn('fixture-private-key', json.dumps(prompts))
        self.assertIn('[REDACTED]', json.dumps(prompts))
        self.assertTrue(any(m['role']=='assistant' for m in prompts[-1]['messages']))

    def test_runner_records_and_redacts_actual_wire_body(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        sent = []
        def fake(client, **kwargs):
            sent.append(json.loads(kwargs['encoded']))
            response = run_action('write','fixture-private-key') if len(sent)==1 else SUBMIT
            return json.dumps(dict(choices=[dict(message=dict(content=json.dumps(response)),finish_reason='stop')],
                usage=dict(prompt_tokens=1,completion_tokens=1))).encode()
        client = OpenAICompatibleJSONClient(RetracModelConfig('fixture','https://example.invalid','fixture-private-key',
            provider='deepseek',request_attempts=1,parse_attempts=1))
        runner = LeanTaskRunner(FakeEnvironment(), client, Scripted([]), LeanConfig(), Path(temp.name)/'audit')
        with patch.object(OpenAICompatibleJSONClient, '_request_bytes', fake):
            result = runner.run(TaskSpec('fixture','write output'))
        self.assertTrue(result['submitted'], result)
        events = read_trace(Path(temp.name)/'audit/events.jsonl')
        wire = [e['request_body'] for e in events if e['event']=='wire_prompt']
        self.assertEqual(wire, sent)
        self.assertEqual(len(wire), 2)
        self.assertNotIn('fixture-private-key', json.dumps(wire))
        self.assertIsNone(client.request_audit)  # temporary hook is restored


if __name__ == '__main__': unittest.main()
