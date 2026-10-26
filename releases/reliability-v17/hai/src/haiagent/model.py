"""v14's process-isolated HTTP deadline idea, without search/model-policy dependencies."""
import json
import hashlib
import multiprocessing
import time
import urllib.error
import urllib.parse
import urllib.request
from .action_protocol import TOOL_NAME, action_tool


class ModelError(RuntimeError):
    pass


def _bounded_tool_call_audit(call):
    """Return shape-only diagnostics; never retain argument contents."""
    audit = {'call_type': type(call).__name__}
    if not isinstance(call, dict):
        return audit
    function = call.get('function')
    call_id = call.get('id')
    audit.update({
        'type_present': 'type' in call,
        'type_value': call.get('type') if isinstance(call.get('type'), str) else None,
        'id_type': type(call_id).__name__,
        'id_chars': len(call_id) if isinstance(call_id, str) else None,
        'function_type': type(function).__name__,
    })
    if isinstance(function, dict):
        arguments = function.get('arguments')
        audit.update({
            'name_present': 'name' in function,
            'name_value': function.get('name') if isinstance(function.get('name'), str) else None,
            'arguments_type': type(arguments).__name__,
        })
        if isinstance(arguments, str):
            audit['arguments_chars'] = len(arguments)
            audit['arguments_sha256'] = hashlib.sha256(arguments.encode()).hexdigest()
        elif isinstance(arguments, dict):
            encoded = json.dumps(arguments, ensure_ascii=False, sort_keys=True,
                                 separators=(',', ':')).encode()
            audit['arguments_chars'] = len(encoded)
            audit['arguments_sha256'] = hashlib.sha256(encoded).hexdigest()
    return audit


def _normalize_tool_call(call):
    """Normalize provider-only deviations without changing action semantics."""
    audit = _bounded_tool_call_audit(call)
    if not isinstance(call, dict):
        return None, 'tool_call_not_object', audit
    function = call.get('function')
    if not isinstance(function, dict):
        return None, 'tool_call_function_not_object', audit
    if function.get('name') != TOOL_NAME:
        return None, 'tool_call_wrong_name', audit

    call_type = call.get('type')
    normalized_fields = []
    if call_type not in (None, 'function'):
        return None, 'tool_call_wrong_type', audit
    if call_type is None:
        normalized_fields.append('missing_type')

    arguments = function.get('arguments')
    if isinstance(arguments, dict):
        arguments = json.dumps(arguments, ensure_ascii=False, sort_keys=True,
                               separators=(',', ':'))
        normalized_fields.append('object_arguments')
    elif not isinstance(arguments, str):
        return None, 'tool_call_arguments_not_json_text_or_object', audit
    if len(arguments) > 64000:
        return None, 'tool_call_arguments_too_large', audit

    call_id = call.get('id')
    if not isinstance(call_id, str) or not 1 <= len(call_id) <= 256:
        # The ID only correlates the assistant call with its subsequent tool
        # result. It has no action semantics, so a deterministic local ID is safe.
        call_id = 'compat-' + hashlib.sha256(arguments.encode()).hexdigest()[:24]
        normalized_fields.append('invalid_or_missing_id')

    normalized = {'id': call_id, 'type': 'function',
                  'function': {'name': TOOL_NAME, 'arguments': arguments}}
    audit['normalized_fields'] = normalized_fields
    return normalized, None, audit


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _http_worker(send, endpoint, payload, key, timeout):
    try:
        request = urllib.request.Request(endpoint, data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
        with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as response:
            body = response.read(2_000_001)
        send.send(("ok", body) if len(body) <= 2_000_000 else ("error", "response_too_large"))
    except urllib.error.HTTPError as exc:
        # Provider bodies can contain sensitive material. Never log them by default.
        send.send(("http", exc.code))
    except Exception as exc:
        send.send(("error", type(exc).__name__))
    finally:
        send.close()


def request_with_deadline(endpoint, payload, key, seconds):
    ctx = multiprocessing.get_context("spawn")
    receiver, sender = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_http_worker, args=(sender, endpoint, payload, key, seconds), daemon=True)
    until = time.monotonic() + seconds
    process.start()
    sender.close()
    try:
        if not receiver.poll(max(0, until - time.monotonic())):
            return ("error", "absolute_request_timeout")
        try:
            return receiver.recv()
        except EOFError:
            return ("error", "transport_worker_exited")
    finally:
        receiver.close()
        if process.is_alive():
            process.terminate()
        process.join(timeout=0.5)
        if process.is_alive():
            process.kill()
            process.join(timeout=0.5)


class APIClient:
    def __init__(self, base_url, model, api_key, config, transport=request_with_deadline):
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("API base URL must be HTTPS without embedded credentials/query")
        if not model.strip() or not api_key.strip() or any(ch.isspace() for ch in api_key):
            raise ValueError("Model and valid API key required")
        if model.startswith("REPLACE_"):
            raise ValueError("Replace the example model ID before starting")
        self.endpoint = base_url.rstrip("/") + "/chat/completions"
        self.model, self.key, self.config, self.transport = model, api_key, config, transport

    def complete(self, messages, deadline, recorder):
        payload = {"model": self.model, "messages": messages, "stream": False,
                   "temperature": self.config.temperature,
                   "max_tokens": self.config.max_tokens}
        if self.config.response_protocol == 'tool_call':
            payload['tools'] = [action_tool(self.config.method)]
            payload['tool_choice'] = {'type': 'function', 'function': {'name': TOOL_NAME}}
            # Named tool choice is not supported with DeepSeek thinking enabled.
            # Explicit provider setting, same in HAI and Raw; never silently switch endpoints.
            if urllib.parse.urlsplit(self.endpoint).hostname == 'api.deepseek.com':
                payload['thinking'] = {'type': 'disabled'}
        else:
            payload['response_format'] = {'type': 'json_object'}
        for attempt in range(self.config.api_attempts):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ModelError("task_deadline")
            recorder.emit("api_start", attempt=attempt + 1, model=self.model)
            start = time.monotonic()
            kind, body = self.transport(self.endpoint, payload, self.key, min(remaining, self.config.request_seconds))
            if kind == "ok":
                try:
                    parsed = json.loads(body)
                    choices = parsed["choices"]
                    if not isinstance(choices, list) or len(choices) != 1:
                        raise ValueError("expected one choice")
                    choice = choices[0]
                    message = choice['message']
                    content = message.get('content') or ''
                    usage = parsed.get("usage")
                    if not isinstance(content, str) or len(content) > 64000:
                        raise ValueError("invalid content")
                    recorder.emit("api_end", status="response", duration_seconds=time.monotonic() - start,
                                  usage=usage if isinstance(usage, dict) else None,
                                  returned_model=parsed.get("model"), finish_reason=choice.get("finish_reason"))
                    if self.config.response_protocol == 'tool_call':
                        calls = message.get('tool_calls')
                        if not isinstance(calls, list) or len(calls) != 1:
                            audit = {'tool_calls_type': type(calls).__name__,
                                     'tool_call_count': len(calls) if isinstance(calls, list) else None}
                            return {'content': content, 'complete': False,
                                    'protocol_error': 'Expected exactly one choose_action tool call',
                                    'protocol_classification': 'tool_call_count',
                                    'tool_call_audit': audit}
                        call, error, audit = _normalize_tool_call(calls[0])
                        if error:
                            return {'content': content, 'complete': False,
                                    'protocol_error': 'Invalid choose_action tool call: ' + error,
                                    'protocol_classification': error,
                                    'tool_call_audit': audit}
                        arguments = call['function']['arguments']
                        if audit.get('normalized_fields'):
                            recorder.emit('tool_call_normalized', normalized_fields=audit['normalized_fields'],
                                          diagnostic=audit)
                        return {'content': arguments, 'complete': choice.get('finish_reason') in ('tool_calls', 'stop'),
                                'tool_call': call, 'tool_call_audit': audit}
                    # Incomplete or ambiguous decisions never execute, in either transport.
                    return {"content": content, "complete": choice.get("finish_reason") == "stop"}
                except (ValueError, TypeError, KeyError, IndexError):
                    recorder.emit("api_end", status="invalid_envelope", duration_seconds=time.monotonic() - start, usage=None)
                    raise ModelError("invalid_provider_response")
            recorder.emit("api_end", status=str(body), duration_seconds=time.monotonic() - start, usage=None)
            retryable = kind == "error" or kind == "http" and (body in {408, 429} or 500 <= body < 600)
            if not retryable or attempt + 1 == self.config.api_attempts:
                raise ModelError(f"provider_{body}")
            delay = min(2 ** attempt, max(0, deadline - time.monotonic()))
            time.sleep(delay)
        raise ModelError("transport_exhausted")
