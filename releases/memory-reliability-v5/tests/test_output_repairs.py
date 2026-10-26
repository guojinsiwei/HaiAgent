import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'sources'), str(ROOT/'sources/bestfgs-project/src'),
               str(ROOT/'sources/bestfgs-project/tests'), str(ROOT/'integration')]
from bestfgs.retrac_adapter import OpenAICompatibleJSONClient, RetracModelConfig, _SerializedHTTPError
from bestfgs.response_repair import repair_feedback, REPAIRABLE_OUTPUT
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.lean_protocol import LeanConfig
from bestfgs.models import ModelCallError, TaskSpec
from bestfgs.lean_conversation import Conversation, message_chars
from test_lean import FakeEnvironment, Scripted, SUBMIT, run_action
from audit import Audit, JSONClientAudit, model_error_fields
from outcomes import classify
from supervisor import disposition


def response(content, reason='stop'):
    return json.dumps(dict(choices=[dict(message=dict(content=content), finish_reason=reason)],
                           usage=dict(prompt_tokens=10, completion_tokens=10))).encode()


def client(**kw):
    return OpenAICompatibleJSONClient(RetracModelConfig('fixture', 'https://example.invalid',
        'fixture-secret', provider='deepseek', max_tokens=4096, request_attempts=2,
        retry_interval_seconds=0, **kw))


class OutputRepairs(unittest.TestCase):
    def test_truncation_retry_changes_feedback_preserves_history_and_budgets(self):
        wire = []
        history = [dict(role='assistant', content='{"action":"run","argv":["read"]}'),
                   dict(role='user', content='EARLY_EVIDENCE')]
        original = copy.deepcopy(history)
        def request(instance, **kw):
            wire.append(json.loads(kw['encoded']))
            if len(wire) == 1:
                return response(json.dumps(run_action('write', 'MUST_NOT_EXECUTE')), 'length')
            self.assertIn('one small executable edit', wire[-1]['messages'][-1]['content'])
            return response(json.dumps(run_action('write', 'small chunk')))
        model = client()
        with patch.object(OpenAICompatibleJSONClient, '_request_bytes', request):
            value = model.complete_json(system_prompt='JSON schema', user_prompt='protected task', history_messages=history)
        self.assertEqual(value['argv'][-1], 'small chunk')
        self.assertEqual(model.api_request_count, 2)
        for body in wire:
            self.assertEqual(body['max_tokens'], 4096)
            self.assertEqual(body['messages'][1:-1], original)
            self.assertTrue(body['messages'][-1]['content'].startswith('protected task'))
        self.assertEqual(history, original)
        self.assertEqual(model.failure_counts, {'output_length': 1})

    def test_truncated_or_invalid_action_never_executes_and_next_round_gets_cause(self):
        for detail in ('output_length', 'json_syntax'):
            with self.subTest(detail=detail), tempfile.TemporaryDirectory() as tmp:
                wire, env = [], FakeEnvironment()
                def request(instance, **kw):
                    wire.append(json.loads(kw['encoded']))
                    if len(wire) <= 2:
                        return (response(json.dumps(run_action('write', 'FORBIDDEN')), 'length')
                                if detail == 'output_length' else response('{"action":"run",BAD'))
                    if len(wire) == 3:
                        prompt = json.loads(wire[-1]['messages'][-1]['content'])
                        self.assertIn(detail, json.dumps(prompt))
                        self.assertIn('split', json.dumps(prompt).lower()) if detail == 'json_syntax' else self.assertIn('file chunk', json.dumps(prompt))
                        self.assertEqual(prompt['response_limits']['max_output_tokens'], 4096)
                        return response(json.dumps(run_action('write', 'RECOVERED')))
                    return response(json.dumps(SUBMIT))
                model = client()
                with patch.object(OpenAICompatibleJSONClient, '_request_bytes', request):
                    result = LeanTaskRunner(env, model, Scripted([]), LeanConfig(max_turns=8, max_tools=5),
                        Path(tmp)/'audit').run(TaskSpec('fixture', 'Write a small file'))
                self.assertTrue(result['submitted'], result)
                self.assertEqual(env.value, 'RECOVERED')
                self.assertEqual(len(env.executed), 1)
                self.assertEqual(model.api_request_count, 4)

    def test_repeated_truncation_remains_bounded_with_original_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, model = FakeEnvironment(), client()
            with patch.object(OpenAICompatibleJSONClient, '_request_bytes',
                              return_value=response(json.dumps(run_action('write', 'FORBIDDEN')), 'length')):
                result = LeanTaskRunner(env, model, Scripted([]), LeanConfig(max_turns=8, max_tools=5),
                    Path(tmp)/'audit').run(TaskSpec('fixture', 'Write'))
            self.assertEqual(result['stop_reason'], 'model_or_protocol_error_limit')
            self.assertEqual(model.api_request_count, 6)
            self.assertEqual(env.executed, [])
            self.assertEqual(result['artifact']['value'], 'seed')

    def test_retry_feedback_fits_reserved_message_budget(self):
        history = Conversation()
        for i in range(25):
            history.append(run_action('read'), dict(stdout=str(i)+'x'*3000))
        payload = dict(task='required original task', data='x'*6000)
        messages, stats = history.build('system', payload, 48000-1024)
        for detail in REPAIRABLE_OUTPUT:
            all_messages = [dict(role='system', content='system'), *messages,
                dict(role='user', content=json.dumps(payload, ensure_ascii=False)+'\n\n'+repair_feedback(detail, 4096))]
            self.assertLessEqual(message_chars(all_messages), 48000)

    def test_format_retry_replaces_feedback_instead_of_accumulating(self):
        model, wire = client(), []
        def request(instance, **kw):
            wire.append(json.loads(kw['encoded']))
            return response('bad JSON')
        with patch.object(OpenAICompatibleJSONClient, '_request_bytes', request), self.assertRaises(ModelCallError):
            model.complete_json(system_prompt='JSON', user_prompt='original task')
        self.assertEqual(len(wire), 2)
        self.assertEqual(wire[-1]['messages'][-1]['content'].count('Protocol validation failed'), 1)

    def test_provider_credential_failure_is_terminal_and_audited(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = client()
            wrapped = JSONClientAudit(model, Audit(Path(tmp)/'outer.jsonl', ['fixture-secret']), 'action')
            with patch.object(OpenAICompatibleJSONClient, '_request_bytes',
                side_effect=_SerializedHTTPError(401, 'unauthorized', None)), self.assertRaises(ModelCallError):
                wrapped.complete_json(system_prompt='JSON', user_prompt='task')
            self.assertEqual(model.api_request_count, 1)
            error = json.loads((Path(tmp)/'outer.jsonl').read_text().splitlines()[-1])
            self.assertEqual(error['error_code'], 'http_401')
            self.assertFalse(error['retryable'])
            self.assertTrue(disposition({}, [error])['blocks_dispatch'])

    def test_outer_audit_preserves_safe_cause_and_diagnostics_redact(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = client()
            model.diagnostics_path = Path(tmp)/'wire.jsonl'
            wrapped = JSONClientAudit(model, Audit(Path(tmp)/'outer.jsonl', ['fixture-secret']), 'action')
            with patch.object(OpenAICompatibleJSONClient, '_request_bytes',
                return_value=response('fixture-secret truncated', 'length')), self.assertRaises(ModelCallError):
                wrapped.complete_json(system_prompt='JSON', user_prompt='task')
            error = json.loads((Path(tmp)/'outer.jsonl').read_text().splitlines()[-1])
            self.assertEqual(error['error_code'], 'output_length')
            self.assertEqual(error['failure_kind'], 'model_output')
            text = (Path(tmp)/'wire.jsonl').read_text()
            self.assertNotIn('fixture-secret', text)
            self.assertEqual(len(text.splitlines()), 2)
            model.last_failure_detail = 'arbitrary-secret-text'
            self.assertIsNone(model_error_fields(ModelCallError('anything'), model)['error_code'])


class RecoveryClassification(unittest.TestCase):
    def classify_events(self, events, stop='request_or_tool_budget'):
        result = dict(method='bestfgs', process_exit_code=0, verifier_result={'rewards': {'reward': 0}}, exception_info=None)
        return classify(result, [*events, dict(event='method_end', result=dict(stop_reason=stop))])

    def test_same_role_recovery_is_warning_not_trial_failure(self):
        events = [dict(event='model_error', role='action', error_code='json_syntax'),
                  dict(event='model_response', role='action')]
        result = self.classify_events(events)
        self.assertEqual(result['method_issues'], [])
        self.assertEqual(result['recovered_model_errors'], 1)
        self.assertEqual(result['warnings'], ['recovered_model_errors'])
        self.assertFalse(disposition(dict(classification=result), events)['trial_failure'])

    def test_wrong_role_cannot_recover_actor(self):
        result = self.classify_events([dict(event='model_error', role='action', error_code='output_length'),
                                       dict(event='model_response', role='advisor')])
        self.assertEqual(result['method_issues'], ['model_error'])

    def test_terminal_output_limit_remains_failure(self):
        result = self.classify_events([dict(event='model_error', role='action', error_code='output_length')]*3,
                                     'model_or_protocol_error_limit')
        self.assertEqual(result['unrecovered_model_errors'], 3)
        self.assertEqual(result['method_issues'], ['model_error'])

    def test_recovery_does_not_erase_fatal_status_or_later_terminal_failure(self):
        events = [dict(event='model_error', role='action', error_code='http_401'),
                  dict(event='model_response', role='action')]
        self.assertEqual(self.classify_events(events)['method_issues'], ['model_error'])
        events[0]['error_code'] = 'json_syntax'
        self.assertEqual(self.classify_events(events, 'model_or_protocol_error_limit')['method_issues'], ['model_error'])

    def test_output_truncation_at_deadline_is_not_blanket_excused(self):
        self.assertEqual(self.classify_events([dict(event='model_error', role='action', error_code='output_length')],
                                             'wall_budget')['method_issues'], ['model_error'])

    def test_delivery_failure_is_infrastructure_error(self):
        self.assertFalse(self.classify_events([], 'delivery_error')['infrastructure_ok'])


if __name__ == '__main__':
    unittest.main()
