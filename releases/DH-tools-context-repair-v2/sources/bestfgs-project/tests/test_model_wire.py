import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bestfgs.model_wire import collect_stream, coalesce_stream
from bestfgs.retrac_adapter import OpenAICompatibleJSONClient, RetracModelConfig, ModelCallError


def event(obj):
    return ('data: ' + json.dumps(obj, ensure_ascii=False) + '\n\n').encode()


def response(content='{"ok":true}', reason='stop', done=True):
    return (event({'choices': [{'index': 0, 'delta': {'content': content}}]})
            + event({'choices': [{'index': 0, 'delta': {}, 'finish_reason': reason}]})
            + event({'choices': [], 'usage': {'prompt_tokens': 10, 'completion_tokens': 7}})
            + (b'data: [DONE]\n\n' if done else b''))


def client(attempts=1, path=None):
    return OpenAICompatibleJSONClient(RetracModelConfig(
        api_key='private-configured-key', model_name='fake', base_url='http://fake',
        request_attempts=attempts, retry_interval_seconds=0, max_retry_interval_seconds=1,
        hard_timeout_process=False), diagnostics_path=path)


class WireTests(unittest.TestCase):
    def invoke(self, c, bodies):
        with patch.object(OpenAICompatibleJSONClient, '_request_bytes', side_effect=bodies):
            return c.complete_json(system_prompt='schema', user_prompt='task')

    def test_complete_stream_counts_usage(self):
        c = client()
        self.assertEqual(self.invoke(c, [coalesce_stream(response())]), {'ok': True})
        self.assertEqual(c.completion_tokens, 7)
        self.assertEqual(c.usage_summary()['usage_unreported_requests'], 0)

    def test_eof_rejects_even_valid_json_and_preserves_usage(self):
        c = client()
        with self.assertRaises(ModelCallError):
            self.invoke(c, [coalesce_stream(response(done=False))])
        self.assertEqual(c.last_failure_kind, 'transport')
        self.assertEqual(c.last_failure_detail, 'incomplete_stream')
        self.assertEqual(c.completion_tokens, 7)

    def test_finish_reason_required_for_sse(self):
        c = client()
        with self.assertRaises(ModelCallError):
            self.invoke(c, [coalesce_stream(response(reason=None))])
        self.assertEqual(c.last_failure_detail, 'missing_finish_reason')

    def test_length_is_not_accepted_even_if_json_valid(self):
        c = client()
        with self.assertRaises(ModelCallError):
            self.invoke(c, [coalesce_stream(response(reason='length'))])
        self.assertEqual(c.last_failure_detail, 'output_length')
        self.assertEqual(c.last_failure_kind, 'model_output')

    def test_nonstop_finish_is_not_accepted(self):
        for reason in ('content_filter', 'tool_calls', 'insufficient_system_resource'):
            c = client()
            with self.subTest(reason=reason), self.assertRaises(ModelCallError):
                self.invoke(c, [coalesce_stream(response(reason=reason))])
            self.assertEqual(c.last_failure_detail, 'nonstop_finish')

    def test_retry_feedback_and_all_usage_counted(self):
        c = client(2)
        bodies = [coalesce_stream(response('{} {}')), coalesce_stream(response())]
        with patch.object(OpenAICompatibleJSONClient, '_request_bytes', side_effect=bodies) as request:
            self.assertEqual(c.complete_json(system_prompt='schema', user_prompt='task'), {'ok': True})
        first, second = [json.loads(call.kwargs['encoded']) for call in request.call_args_list]
        self.assertEqual(first['messages'][1]['content'], 'task')
        self.assertIn('Protocol validation failed: json_syntax', second['messages'][1]['content'])
        self.assertEqual(first['temperature'], second['temperature'])
        self.assertEqual(c.api_request_count, 2)
        self.assertEqual(c.completion_tokens, 14)
        self.assertEqual(c.failure_counts, {'json_syntax': 1})

    def test_budget_exhaustion_never_salvages_first_object(self):
        c = client(2)
        with self.assertRaises(ModelCallError):
            self.invoke(c, [coalesce_stream(response('{} {}'))] * 2)
        self.assertEqual(c.api_request_count, 2)
        self.assertEqual(c.failure_counts, {'json_syntax': 2})

    def test_empty_and_root_type_classified(self):
        for content, detail in [('', 'empty_content'), ('[]', 'json_root_type')]:
            c = client()
            with self.subTest(content=content), self.assertRaises(ModelCallError):
                self.invoke(c, [coalesce_stream(response(content))])
            self.assertEqual(c.last_failure_detail, detail)

    def test_chunked_content_unicode_keepalive_and_usage(self):
        raw = (b': keepalive\n\n' + event({'choices': [{'delta': {'content': '{"text":'}}]})
               + event({'choices': [{'delta': {'content': '"中文"}'}, 'finish_reason': 'stop'}]})
               + b'data: [DONE]\n\n')
        c = client()
        self.assertEqual(self.invoke(c, [coalesce_stream(raw)]), {'text': '中文'})

    def test_multiline_sse_event(self):
        raw = b'data: {"choices":\ndata: [{"delta":{"content":"{}"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
        self.assertEqual(self.invoke(client(), [coalesce_stream(raw)]), {})

    def test_reader_and_coalescer_agree(self):
        class Sender:
            def __init__(self): self.count = 0
            def send(self, value): self.count += 1
        sender = Sender()
        raw = response()
        self.assertEqual(collect_stream(io.BytesIO(raw), sender), coalesce_stream(raw))
        self.assertGreater(sender.count, 0)

    def test_malformed_event_rejects(self):
        c = client()
        raw = response(done=False) + b'data: invalid\n\ndata: [DONE]\n\n'
        with self.assertRaises(ModelCallError):
            self.invoke(c, [coalesce_stream(raw)])
        self.assertEqual(c.last_failure_detail, 'incomplete_stream')
        self.assertEqual(c.completion_tokens, 7)

    def test_diagnostics_bounded_redacted_and_schema_recorded(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'model-failures.jsonl'
            c = client(path=path)
            secret = c.config.api_key
            content = secret + ' sk-abcdefghijklm Bearer other-secret ' + ('x' * 20000) + secret
            with self.assertRaises(ModelCallError):
                self.invoke(c, [coalesce_stream(response(content))])
            c.record_schema_failure(ValueError(secret))
            raw = path.read_text()
            self.assertNotIn(secret, raw)
            self.assertNotIn('sk-abcdefghijklm', raw)
            self.assertNotIn('other-secret', raw)
            rows = [json.loads(line) for line in raw.splitlines()]
            self.assertEqual(len(rows), 2)
            self.assertTrue(rows[0]['content_truncated'])
            self.assertLess(len(raw), 19000)
            self.assertEqual(rows[0]['finish_reason'], 'stop')

    def test_broken_diagnostic_path_does_not_change_failure(self):
        with tempfile.TemporaryDirectory() as root:
            c = client(path=Path(root))
            with self.assertRaises(ModelCallError):
                self.invoke(c, [coalesce_stream(response('{} {}'))])
            self.assertEqual(c.last_failure_kind, 'model_output')

    def test_malformed_envelope_does_not_escape_or_count_usage(self):
        for body in (b'[]', b'not-json', b'{"choices":[]}'):
            c = client()
            with self.subTest(body=body), self.assertRaises(ModelCallError):
                self.invoke(c, [body])
            self.assertEqual(c.last_failure_kind, 'transport')

    def test_transport_retry_does_not_inject_format_feedback(self):
        c = client(2)
        with patch.object(OpenAICompatibleJSONClient, '_request_bytes', side_effect=[TimeoutError(), coalesce_stream(response())]) as request:
            c.complete_json(system_prompt='schema', user_prompt='task')
        self.assertEqual(request.call_args_list[0].kwargs['encoded'], request.call_args_list[1].kwargs['encoded'])
        self.assertEqual(c.usage_summary()['usage_unreported_requests'], 1)


if __name__ == '__main__':
    unittest.main()
