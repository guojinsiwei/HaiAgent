"""Offline tests: HTTP calls are replaced by an in-memory transport."""

import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from recuris.audit import JsonlLogger, redact
from recuris.client import ModelClientError, ModelConfig, ModelDeadlineExceeded, OpenAIChatClient


_KEY = "provider-key-used-only-in-offline-tests"
_MESSAGES = [{"role": "user", "content": "检查终端"}]


def completion(content='{"done": true}', **updates):
    result = {
        "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 7},
    }
    result.update(updates)
    return json.dumps(result).encode("utf-8")


def http_error(code, body=None, headers=None):
    return HTTPError(
        "https://api.deepseek.com/chat/completions", code, "Provider failure", headers or {},
        io.BytesIO(json.dumps(body or {"error": {"message": "bad request"}}).encode()),
    )


class FakeTransport:
    def __init__(self, *results):
        self.results = list(results)
        self.requests = []

    def __call__(self, request, *, timeout):
        self.requests.append((request, timeout))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return io.BytesIO(result)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"DEEPSEEK_API_KEY": _KEY}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_deepseek_request_and_usage(self):
        transport = FakeTransport(completion())
        client = OpenAIChatClient(ModelConfig("explicit-model"), opener=transport)
        reply = client.complete(_MESSAGES, purpose="executor")
        request, timeout = transport.requests[0]
        self.assertEqual(request.full_url, "https://api.deepseek.com/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + _KEY)
        self.assertEqual(timeout, 120)
        self.assertEqual(json.loads(request.data), {
            "model": "explicit-model", "messages": _MESSAGES, "stream": False, "max_tokens": 4096,
        })
        self.assertEqual((reply.input_tokens, reply.output_tokens, reply.finish_reason), (12, 7, "stop"))
        self.assertEqual(reply.content, '{"done": true}')

    def test_configurable_provider_and_complete_endpoint(self):
        os.environ.update(DEEPSEEK_BASE_URL="https://ds.example/v1/", OPENAI_BASE_URL="https://oa.example/v1")
        self.assertEqual(OpenAIChatClient(ModelConfig("m")).endpoint, "https://ds.example/v1/chat/completions")
        self.assertEqual(
            OpenAIChatClient(ModelConfig("m", base_url="https://own.example/chat/completions/")).endpoint,
            "https://own.example/chat/completions",
        )
        os.environ.pop("DEEPSEEK_BASE_URL")
        self.assertEqual(OpenAIChatClient(ModelConfig("m")).endpoint, "https://oa.example/v1/chat/completions")

    def test_optional_parameters_and_compatible_token_override(self):
        transport = FakeTransport(completion())
        client = OpenAIChatClient(ModelConfig(
            "m", temperature=0.5, top_p=0.9, reasoning_effort="high",
            extra_body={"max_completion_tokens": 100, "thinking": {"type": "enabled"}},
        ), opener=transport)
        client.complete(_MESSAGES, purpose="reflector")
        payload = json.loads(transport.requests[0][0].data)
        self.assertEqual(payload["max_completion_tokens"], 100)
        self.assertNotIn("max_tokens", payload)
        self.assertEqual(payload["thinking"], {"type": "enabled"})
        self.assertEqual(payload["temperature"], 0.5)
        self.assertEqual(payload["reasoning_effort"], "high")

    def test_transient_rate_limit_retries_with_bounded_retry_after(self):
        transport = FakeTransport(http_error(429, headers={"Retry-After": "999"}), completion())
        delays = []
        client = OpenAIChatClient(ModelConfig("m"), opener=transport, sleep=delays.append)
        client.complete(_MESSAGES, purpose="supervisor")
        self.assertEqual(delays, [30])
        self.assertEqual(len(transport.requests), 2)
        self.assertEqual(transport.requests[0][0].data, transport.requests[1][0].data)

    def test_persistent_server_failure_is_bounded_and_redacted(self):
        errors = [http_error(503, {"error": {"message": "key " + _KEY}}) for _ in range(3)]
        transport = FakeTransport(*errors)
        delays = []
        client = OpenAIChatClient(ModelConfig("m"), opener=transport, sleep=delays.append)
        with self.assertRaises(ModelClientError) as raised:
            client.complete(_MESSAGES, purpose="executor " + _KEY)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertNotIn(_KEY, str(raised.exception))
        self.assertIn("3 attempt(s)", str(raised.exception))
        self.assertEqual(delays, [1, 2])

    def test_client_errors_do_not_retry(self):
        for code in (400, 401, 402, 403, 404, 422):
            with self.subTest(code=code):
                transport = FakeTransport(http_error(code))
                client = OpenAIChatClient(ModelConfig("m"), opener=transport, sleep=lambda _: self.fail("unexpected retry"))
                with self.assertRaises(ModelClientError) as raised:
                    client.complete(_MESSAGES, purpose="executor")
                self.assertEqual(raised.exception.status_code, code)
                self.assertEqual(len(transport.requests), 1)

    def test_transport_errors_retry(self):
        transport = FakeTransport(URLError("temporarily unavailable"), TimeoutError("timed out"), completion())
        delays = []
        client = OpenAIChatClient(ModelConfig("m"), opener=transport, sleep=delays.append)
        client.complete(_MESSAGES, purpose="executor")
        self.assertEqual(delays, [1, 2])

    def test_run_deadline_caps_transport_timeout(self):
        transport = FakeTransport(completion())
        client = OpenAIChatClient(ModelConfig("m"), opener=transport)
        with patch("recuris.client.time.monotonic", return_value=10):
            client.complete(_MESSAGES, purpose="executor", deadline_monotonic=12.5)
        self.assertEqual(transport.requests[0][1], 2.5)

    def test_late_reply_raises_deadline_with_reported_usage(self):
        clock = [0.0]

        def late_response(request, *, timeout):
            clock[0] = 3.0
            return io.BytesIO(completion())

        client = OpenAIChatClient(ModelConfig("m"), opener=late_response)
        with patch("recuris.client.time.monotonic", side_effect=lambda: clock[0]):
            with self.assertRaises(ModelDeadlineExceeded) as raised:
                client.complete(_MESSAGES, purpose="executor", deadline_monotonic=2)
        self.assertEqual((raised.exception.input_tokens, raised.exception.output_tokens), (12, 7))

    def test_retry_sleep_cannot_exceed_run_deadline(self):
        clock = [0.0]
        delays = []

        def advance(delay):
            delays.append(delay)
            clock[0] += delay

        transport = FakeTransport(http_error(429, headers={"Retry-After": "10"}))
        client = OpenAIChatClient(ModelConfig("m"), opener=transport, sleep=advance)
        with patch("recuris.client.time.monotonic", side_effect=lambda: clock[0]):
            with self.assertRaises(ModelDeadlineExceeded):
                client.complete(_MESSAGES, purpose="executor", deadline_monotonic=0.5)
        self.assertEqual(delays, [0.5])
        self.assertEqual(len(transport.requests), 1)

    def test_expired_deadline_prevents_network_request(self):
        transport = FakeTransport()
        client = OpenAIChatClient(ModelConfig("m"), opener=transport)
        with patch("recuris.client.time.monotonic", return_value=10):
            with self.assertRaises(ModelDeadlineExceeded):
                client.complete(_MESSAGES, purpose="executor", deadline_monotonic=9)
        self.assertEqual(transport.requests, [])

    def test_socket_timeout_at_run_deadline_is_not_retried(self):
        clock = [0.0]

        def timed_out(request, *, timeout):
            clock[0] += timeout
            raise TimeoutError("deadline")

        client = OpenAIChatClient(ModelConfig("m"), opener=timed_out)
        with patch("recuris.client.time.monotonic", side_effect=lambda: clock[0]):
            with self.assertRaises(ModelDeadlineExceeded):
                client.complete(_MESSAGES, purpose="executor", deadline_monotonic=2)

    def test_invalid_content_preserves_reported_usage_on_error(self):
        client = OpenAIChatClient(ModelConfig("m"), opener=FakeTransport(completion(None)))
        with self.assertRaises(ModelClientError) as raised:
            client.complete(_MESSAGES, purpose="executor")
        self.assertEqual((raised.exception.input_tokens, raised.exception.output_tokens), (12, 7))

    def test_malformed_reply_does_not_retry(self):
        for raw in (b"not JSON", b"[]", b"{}", completion(None), completion("")):
            with self.subTest(raw=raw):
                transport = FakeTransport(raw)
                client = OpenAIChatClient(ModelConfig("m"), opener=transport)
                with self.assertRaises(ModelClientError):
                    client.complete(_MESSAGES, purpose="executor")
                self.assertEqual(len(transport.requests), 1)

    def test_tool_only_response_fails_without_executing(self):
        raw = completion(choices=[{"message": {"content": None, "tool_calls": [{"function": {"name": "shell", "arguments": "echo bad"}}]}, "finish_reason": "tool_calls"}])
        client = OpenAIChatClient(ModelConfig("m"), opener=FakeTransport(raw))
        with self.assertRaisesRegex(ModelClientError, "tool_calls"):
            client.complete(_MESSAGES, purpose="executor")

    def test_missing_key_fails_before_transport(self):
        os.environ.clear()
        transport = FakeTransport()
        client = OpenAIChatClient(ModelConfig("m"), opener=transport)
        with self.assertRaisesRegex(ModelClientError, "DEEPSEEK_API_KEY"):
            client.complete(_MESSAGES, purpose="executor")
        self.assertEqual(transport.requests, [])

    def test_truncation_and_usage_are_preserved(self):
        raw = completion(choices=[{"message": {"content": '{"partial"'}, "finish_reason": "length"}])
        reply = OpenAIChatClient(ModelConfig("m"), opener=FakeTransport(raw)).complete(_MESSAGES, purpose="executor")
        self.assertEqual(reply.finish_reason, "length")
        self.assertEqual(reply.output_tokens, 7)

    def test_optional_or_invalid_usage_does_not_break_reply(self):
        for usage, expected in ((None, (0, 0)), ({"prompt_tokens": -1, "completion_tokens": True}, (0, 0)), ({"input_tokens": 9, "output_tokens": 3}, (9, 3))):
            with self.subTest(usage=usage):
                reply = OpenAIChatClient(ModelConfig("m"), opener=FakeTransport(completion(usage=usage))).complete(_MESSAGES, purpose="executor")
                self.assertEqual((reply.input_tokens, reply.output_tokens), expected)

    def test_invalid_configuration_is_rejected(self):
        for kwargs in ({"model_name": " "}, {"max_attempts": 0}, {"max_output_tokens": True}, {"timeout_seconds": float("nan")}, {"timeout_seconds": True}, {"temperature": True}, {"top_p": False}, {"temperature": 3}, {"extra_body": {"messages": []}}, {"extra_body": {"stream": True}}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ModelConfig(**({"model_name": "m"} | kwargs))
        for url in ("file:///tmp/model", "https://key@example.test/v1", "https://example.test?key=secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                OpenAIChatClient(ModelConfig("m", base_url=url))


class AuditTests(unittest.TestCase):
    def test_explicit_credential_values_are_redacted_even_with_custom_env_names(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = JsonlLogger(directory, secrets=("custom-credential-value",))
            logger.write("observation", output="printed custom-credential-value")
            saved = logger.save("result", "printed custom-credential-value")
            self.assertNotIn("custom-credential-value", (Path(directory) / "events.jsonl").read_text(encoding="utf-8"))
            self.assertNotIn("custom-credential-value", saved.read_text(encoding="utf-8"))

    def test_audit_redacts_nested_credentials_and_environment_values(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DEEPSEEK_API_KEY": _KEY}):
            logger = JsonlLogger(directory)
            logger.write("response", text=f"echo {_KEY}; Authorization: Bearer arbitrary-private-token", nested={"api_key": "tiny", "content": "sk-abcdefghijklmnop"})
            raw = (Path(directory) / "events.jsonl").read_text(encoding="utf-8")
            event = json.loads(raw)
            for secret in (_KEY, "arbitrary-private-token", "tiny", "sk-abcdefghijklmnop"):
                self.assertNotIn(secret, raw)
            self.assertEqual(event["event"], "response")
            self.assertIn("timestamp", event)
            self.assertEqual(event["nested"]["api_key"], "[REDACTED]")

    def test_snapshot_is_valid_json_and_cannot_escape_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = JsonlLogger(directory)
            path = logger.save("state", {"step": 3, "instructions": "重试", "password": "secret"})
            self.assertEqual(path, Path(directory) / "state.json")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["password"], "[REDACTED]")
            for name in ("../secret", "..\\secret", "C:\\secret", "", ".", ".."):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    logger.save(name, {})

    def test_redaction_keeps_usage_counts_and_masks_shell_assignments(self):
        value = redact({"input_tokens": 123, "output_tokens": 45, "text": "DEEPSEEK_API_KEY='very-private' foo", "notes": "short secret xyz"}, secrets=("xyz",))
        self.assertEqual((value["input_tokens"], value["output_tokens"]), (123, 45))
        self.assertNotIn("very-private", value["text"])
        self.assertNotIn("xyz", value["notes"])


if __name__ == "__main__":
    unittest.main()
