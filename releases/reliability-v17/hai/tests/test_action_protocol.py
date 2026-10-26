"""Offline provider-envelope tests: no API credential, no network model calls."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import time
import unittest

from haiagent.action_protocol import action_tool, strict_object, response_diagnostic
from haiagent.cli import run_exit_code
from haiagent.executor import Result
from haiagent.model import APIClient
from haiagent.protocol import Config, Task
from haiagent.runtime import run, compact_pair
from haiagent.storage import Recorder, read_trace


def envelope(arguments=None, *, calls=None, text=None, finish='tool_calls'):
    if calls is None:
        calls = [{'id': 'real-provider-id', 'type': 'function',
                  'function': {'name': 'choose_action', 'arguments': arguments}}]
    return json.dumps({'model': 'deepseek-flash', 'choices': [{'finish_reason': finish,
        'message': {'role': 'assistant', 'content': text, 'tool_calls': calls}}],
        'usage': {'prompt_tokens': 12, 'completion_tokens': 7}}).encode()


class ActionProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ws = self.root / 'workspace'
        self.ws.mkdir()
        self.task = Task('T', 'inspect files', self.ws, delivery='terminal')
        self.out = self.root / 'run'

    def client(self, replies, config=None):
        replies = iter(replies)
        self.sent = []
        def transport(endpoint, payload, *args):
            self.sent.append(payload)
            return 'ok', next(replies)
        return APIClient('https://api.deepseek.com', 'deepseek-flash', 'test-key', config or Config(), transport)

    def recorder(self):
        rec = Recorder(self.out, secrets=('test-key',))
        rec.emit('header')
        return rec

    def test_single_native_call_with_prose_uses_only_arguments(self):
        client = self.client([envelope('{"action":"submit","summary":"done"}', text='Here is my plan.')])
        result = run(self.task, Config(), client, self.out)
        self.assertTrue(result['submitted'])
        payload = self.sent[0]
        self.assertNotIn('response_format', payload)
        self.assertEqual(payload['tool_choice']['function']['name'], 'choose_action')
        self.assertEqual(payload['thinking'], {'type': 'disabled'})

    def test_real_call_id_and_result_roundtrip_in_next_request(self):
        class Exec:
            def execute(self, *args):
                return Result(0, stdout='visible-feedback')
        client = self.client([envelope('{"action":"run","argv":["pwd"]}'),
                              envelope('{"action":"submit","summary":"done"}')])
        result = run(self.task, Config(), client, self.out, executor=Exec())
        self.assertTrue(result['submitted'])
        assistant, tool = self.sent[1]['messages'][-2:]
        self.assertEqual(assistant['tool_calls'][0]['id'], 'real-provider-id')
        self.assertEqual(tool['role'], 'tool')
        self.assertEqual(tool['tool_call_id'], 'real-provider-id')
        self.assertIn('visible-feedback', tool['content'])
        self.assertEqual(result['interaction_rounds'], 2)

    def test_multi_call_never_executes_first_and_trips_breaker(self):
        call = {'id': 'one', 'type': 'function', 'function': {'name': 'choose_action',
                'arguments': '{"action":"run","argv":["echo","unsafe-to-guess"]}'}}
        class Never:
            def execute(self, *args):
                raise AssertionError('Ambiguous output executed')
        client = self.client([envelope(calls=[call, call])] * 3)
        result = run(self.task, Config(), client, self.out, executor=Never())
        self.assertEqual(result['stop_reason'], 'protocol_error')
        self.assertEqual(run_exit_code(result), 6)
        self.assertEqual(result['interaction_rounds'], 3)
        self.assertEqual(result['tool_calls'], 0)
        self.assertEqual(len(self.sent), 3)

    def test_concatenated_json_never_partially_executes(self):
        text = '{"action":"submit","summary":"one"}{"action":"submit","summary":"two"}'
        client = self.client([envelope(text)] * 3)
        result = run(self.task, Config(), client, self.out)
        self.assertFalse(result['submitted'])
        errors = [r for r in read_trace(self.out / 'events.jsonl') if r['event'] == 'format_error']
        self.assertEqual(errors[0]['diagnostic']['classification'], 'multiple_json_values')
        self.assertEqual(result['stop_reason'], 'protocol_error')

    def test_legacy_json_gets_same_breaker_and_redacted_diagnostic(self):
        class Bad:
            def complete(self, *args):
                return {'content': '{"action":"submit","summary":"test-key"}extra test-key', 'complete': True}
        result = run(self.task, Config(response_protocol='json'), Bad(), self.out, secrets=('test-key',))
        text = (self.out / 'events.jsonl').read_text()
        self.assertNotIn('test-key', text)
        errors = [r for r in read_trace(self.out / 'events.jsonl') if r['event'] == 'format_error']
        self.assertEqual(errors[0]['diagnostic']['classification'], 'text_after_json')
        self.assertIn('[REDACTED]', errors[0]['diagnostic']['head'])
        self.assertEqual(result['interaction_rounds'], 3)

    def test_intermittent_errors_hit_total_limit(self):
        cfg = Config(max_format_errors=3, max_consecutive_format_errors=2)
        class Intermittent:
            def __init__(self):
                self.n = 0
            def complete(self, *args):
                self.n += 1
                return {'complete': True, 'content': 'bad' if self.n % 2 else '{"action":"run","argv":["pwd"]}'}
        class Exec:
            def execute(self, *args):
                return Result(0, stdout='ok')
        result = run(self.task, cfg, Intermittent(), self.out, executor=Exec())
        self.assertEqual(result['interaction_rounds'], 5)
        self.assertEqual(result['tool_calls'], 2)
        self.assertEqual(result['stop_reason'], 'protocol_error')

    def test_duplicate_fields_arrays_and_nonfinite_rejected(self):
        for text in ('{"action":"run","action":"submit"}', '[{"action":"submit"}]', '{"timeout_seconds":NaN}'):
            with self.assertRaises(ValueError):
                strict_object(text)

    def test_wrong_tool_missing_tool_or_truncation_not_complete(self):
        wrong = {'id': 'x', 'type': 'function', 'function': {'name': 'other', 'arguments': '{}'}}
        client = self.client([envelope(calls=[wrong]), envelope(calls=[], text='{"action":"submit"}'),
                              envelope('{"action":"submit","summary":"done"}', finish='length')])
        rec = self.recorder()
        for _ in range(3):
            self.assertFalse(client.complete([], time.monotonic() + 3, rec)['complete'])

    def test_provider_only_tool_call_deviations_are_normalized(self):
        calls = [{'function': {'name': 'choose_action',
                               'arguments': {'action': 'submit', 'summary': 'done'}}}]
        client = self.client([envelope(calls=calls)])
        rec = self.recorder()
        response = client.complete([], time.monotonic() + 3, rec)
        self.assertTrue(response['complete'])
        self.assertEqual(response['tool_call']['type'], 'function')
        self.assertTrue(response['tool_call']['id'].startswith('compat-'))
        self.assertEqual(strict_object(response['content'])['action'], 'submit')
        events = read_trace(self.out / 'events.jsonl')
        normalized = [event for event in events if event['event'] == 'tool_call_normalized']
        self.assertEqual(normalized[0]['normalized_fields'],
                         ['missing_type', 'object_arguments', 'invalid_or_missing_id'])

    def test_invalid_tool_shape_has_specific_content_free_diagnostic(self):
        secret = 'do-not-log-this-argument'
        wrong = {'id': '', 'type': 'other',
                 'function': {'name': 'choose_action', 'arguments': secret}}
        client = self.client([envelope(calls=[wrong])])
        rec = self.recorder()
        response = client.complete([], time.monotonic() + 3, rec)
        self.assertFalse(response['complete'])
        diagnostic = response_diagnostic(response)
        self.assertEqual(diagnostic['classification'], 'tool_call_wrong_type')
        self.assertEqual(diagnostic['tool_call_audit']['arguments_chars'], len(secret))
        self.assertNotIn(secret, json.dumps(diagnostic))

    def test_wrong_tool_name_remains_rejected(self):
        wrong = {'id': 'x', 'type': 'function',
                 'function': {'name': 'other', 'arguments': {'action': 'submit'}}}
        client = self.client([envelope(calls=[wrong])])
        response = client.complete([], time.monotonic() + 3, self.recorder())
        self.assertFalse(response['complete'])
        self.assertEqual(response['protocol_classification'], 'tool_call_wrong_name')

    def test_raw_schema_has_no_memory(self):
        self.assertNotIn('memory', action_tool('raw')['function']['parameters']['properties'])
        self.assertIn('memory', action_tool('hai')['function']['parameters']['properties'])

    def test_oversized_native_history_becomes_explicit_summary_not_fake_call(self):
        args = json.dumps({'action': 'run', 'argv': ['python'], 'stdin': 'x' * 12000})
        call = {'id': 'real', 'type': 'function', 'function': {'name': 'choose_action', 'arguments': args}}
        pair = {'call_id': 1, 'messages': [{'role': 'assistant', 'content': None, 'tool_calls': [call]},
                                         {'role': 'tool', 'tool_call_id': 'real', 'content': '{"id":"E1","output":"ok"}'}]}
        compact = compact_pair(pair, 1000)
        self.assertNotIn('tool_calls', compact['messages'][0])
        self.assertEqual(compact['messages'][1]['role'], 'user')
        self.assertTrue(json.loads(compact['messages'][0]['content'])['history_is_summary'])
        self.assertEqual(call['function']['arguments'], args)

    def test_diagnostic_size_bounded(self):
        diagnostic = response_diagnostic({'content': 'x' * 64000})
        self.assertLess(len(json.dumps(diagnostic)), 3000)


if __name__ == '__main__':
    unittest.main()
