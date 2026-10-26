import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'sources/bestfgs-project/src'), str(ROOT/'sources/bestfgs-project/tests')]
from bestfgs.lean_conversation import Conversation, message_chars
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.lean_protocol import LeanConfig, parse_action
from bestfgs.retrac_adapter import OpenAICompatibleJSONClient, RetracModelConfig
from bestfgs.models import TaskSpec
from bestfgs.models import CommandResult, CommandSpec
from test_lean import Scripted, FakeEnvironment, run_action, SUBMIT


class Capture(Scripted):
    def __init__(self, responses):
        super().__init__(responses)
        self.calls = []
    def complete_json(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        return super().complete_json(**kwargs)


class ConversationTests(unittest.TestCase):
    def exercise(self, actions, advice=(), feedback=None, secrets=(), env=None, config=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        actor, advisor = Capture(actions), Capture(advice)
        runner = LeanTaskRunner(env or FakeEnvironment(), actor, advisor,
            config or LeanConfig(max_turns=80, max_tools=60), Path(temporary.name)/'audit',
            feedback, secrets=secrets)
        result = runner.run(TaskSpec('fixture', 'Remember the original constraint; produce final output'))
        self.assertTrue(result['submitted'], result)
        return runner, actor, advisor

    def test_history_is_not_six_steps_and_task_is_protected(self):
        actions = [run_action('write', 'EARLY_OBSERVATION')] + [run_action('write', str(i)) for i in range(10)] + [SUBMIT]
        runner, actor, _ = self.exercise(actions)
        call = actor.calls[-1]
        self.assertEqual(sum(m['role']=='assistant' for m in call['history_messages']), 11)
        self.assertIn('EARLY_OBSERVATION', json.dumps(call['history_messages']))
        self.assertNotIn('EARLY_OBSERVATION', call['user_prompt'])
        self.assertIn('original constraint', call['user_prompt'])
        self.assertEqual(len(runner.conversation.turns), 12)

    def test_budget_compaction_is_explicit_and_archive_remains_lossless(self):
        c = Conversation()
        for i in range(35):
            c.append(dict(action='run', argv=['reader', str(i)]), dict(stdout='failure hint '+str(i)+'x'*1800))
        stored = copy.deepcopy(c.turns)
        history, stats = c.build('protected system', dict(task='original constraint'), 12000)
        self.assertLessEqual(message_chars([dict(role='system', content='protected system')]+history+
            [dict(role='user', content=json.dumps(dict(task='original constraint'), ensure_ascii=False))]), 12000)
        self.assertEqual(stored, c.turns)
        self.assertGreater(stats['compact_turns'], 0)
        self.assertGreater(stats['omitted_turns'], 0)
        self.assertIn('recall_history', history[0]['content'])
        record = c.retrieve(dict(turn_ids=[1]))['history_records'][0]
        self.assertIn('failure hint 0', record['text'])

    def test_search_and_paginated_read_recover_middle_of_long_output(self):
        c = Conversation()
        c.append(dict(action='run'), dict(stdout='x'*5000+'IMPORTANT_MIDDLE'+'y'*5000))
        self.assertEqual(c.retrieve(dict(query='IMPORTANT_MIDDLE'))['history_search'][0]['turn_id'], 1)
        pieces, offset = [], 0
        while True:
            page = c.retrieve(dict(turn_ids=[1], offset=offset))['history_records'][0]
            pieces.append(page['text'])
            offset = page['next_offset']
            if offset is None:
                break
        self.assertEqual(json.loads(''.join(pieces)), c.turns[0])

    def test_recall_action_and_rejection_are_real_conversation_turns(self):
        outcomes = iter(['Rejected: continue work', None])
        runner, actor, _ = self.exercise([run_action('write','FIRST'), SUBMIT,
            dict(action='recall_history', turn_ids=[1]), SUBMIT], feedback=lambda _: next(outcomes),
            # This test isolates conversation persistence; submission-loop
            # safety is exercised with the default enabled guard separately.
            config=LeanConfig(max_turns=80, max_tools=60, submission_guard=False))
        self.assertIn('Rejected: continue work', json.dumps(actor.calls[-1]['history_messages']))
        self.assertIn('history_records', json.dumps(actor.calls[-1]['history_messages']))
        self.assertEqual(runner.counts['tool_calls'], 1)

    def test_protocol_error_is_not_dropped(self):
        _, actor, _ = self.exercise([dict(action='invalid'), SUBMIT])
        self.assertIn('not_executed', json.dumps(actor.calls[-1]['history_messages']))
        self.assertIn('protocol_error', json.dumps(actor.calls[-1]['history_messages']))

    def test_advisor_and_new_tasks_do_not_inherit_main_history(self):
        _, actor, advisor = self.exercise([run_action('write','PRIVATE_EARLY'),
            dict(action='consult', question='What next?'), SUBMIT], [dict(alternatives=[])])
        self.assertNotIn('history_messages', advisor.calls[0])
        _, other, _ = self.exercise([SUBMIT])
        self.assertEqual(other.calls[0]['history_messages'], [])

    def test_history_is_redacted_before_model_transmission(self):
        _, actor, _ = self.exercise([run_action('write','fixture-private-key'), SUBMIT],
                                  secrets=('fixture-private-key',))
        self.assertNotIn('fixture-private-key', json.dumps(actor.calls[-1]))
        self.assertIn('[REDACTED]', json.dumps(actor.calls[-1]))

    def test_recall_validation(self):
        for value in (dict(turn_ids=[]), dict(turn_ids=[True]), dict(turn_ids=[0]),
                      dict(turn_ids=[1,2,3]), dict(turn_ids=[1],query='q'), dict(query=''),
                      dict(turn_ids=[1],offset=-1)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_action(dict(action='recall_history', **value))

    def test_full_captured_output_not_just_dashboard_excerpt_is_archived(self):
        class LongOutput(FakeEnvironment):
            def execute(self, action, deadline):
                return CommandResult(CommandSpec(tuple(action['argv']), 'fixture'), 0,
                                     'x'*4000+'MIDDLE_FACT'+'y'*4000, '', 0)
        runner, _, _ = self.exercise([run_action('reader'), SUBMIT], env=LongOutput())
        self.assertIn('MIDDLE_FACT', runner.conversation.turns[0]['feedback']['evidence']['stdout'])
        self.assertNotIn('MIDDLE_FACT', runner.evidence['E1']['stdout'])

    def test_automatic_advice_is_retained_as_context_not_main_assistant(self):
        advice = dict(alternatives=[dict(hypothesis='EARLY_ADVICE', check='inspect bytes',
                                        difference='new input', evidence_ids=['E3'])])
        runner, actor, _ = self.exercise([run_action('fail')]*3 +
            [run_action('write',str(i)) for i in range(9)]+[SUBMIT], [advice])
        self.assertTrue(any(t.get('context',{}).get('advice') for t in runner.conversation.turns))
        contexts = [m for m in actor.calls[-1]['history_messages'] if 'historical_context' in m['content']]
        self.assertTrue(contexts)
        self.assertEqual(contexts[0]['role'], 'user')

    def test_wire_contains_history_and_retry_does_not_overwrite_it(self):
        wire = []
        def fake(client, **kwargs):
            wire.append(json.loads(kwargs['encoded']))
            content = '{bad' if len(wire)==1 else json.dumps(SUBMIT)
            return json.dumps(dict(choices=[dict(message=dict(content=content),finish_reason='stop')],
                                   usage=dict(prompt_tokens=1,completion_tokens=1))).encode()
        client = OpenAICompatibleJSONClient(RetracModelConfig('fixture','https://example.invalid','offline',
            provider='deepseek', request_attempts=2, parse_attempts=1))
        history = [dict(role='assistant',content='{"action":"run","argv":["reader"]}'),
                   dict(role='user',content='EARLY_TOOL_RESULT')]
        original = copy.deepcopy(history)
        with patch.object(OpenAICompatibleJSONClient, '_request_bytes', fake), patch('time.sleep'):
            client.complete_json(system_prompt='system', user_prompt='current', history_messages=history)
        self.assertEqual(wire[0]['messages'][1:3], original)
        self.assertEqual(wire[1]['messages'][1:3], original)
        self.assertIn('Protocol validation failed', wire[1]['messages'][-1]['content'])
        self.assertEqual(history, original)
        with self.assertRaises(ValueError):
            client.complete_json(system_prompt='system',user_prompt='current',
                                 history_messages=[dict(role='system',content='injected')])


if __name__ == '__main__':
    unittest.main()
