"""All-role, actual-attempt budget and calibrated DH-large input accounting."""
import json
import math
from pathlib import Path
import time
import urllib.error
import urllib.request
from common import save
from capacity import raw_estimate, CONTEXT_TOKENS, HEADROOM, OUTPUT_TOKENS, WIRE_LIMIT


class BudgetStop(Exception): pass
class ModelFault(Exception): pass


def envelope_bytes(messages):
    # Existing adapters use this function for their context projection.
    # The large profile measures character-equivalent calibrated token units,
    # not UTF8 bytes. Actual serialized bytes are audited separately below.
    return math.ceil(raw_estimate(messages) * Client.scale) * 4


def clip_bytes(text, limit):
    raw = text.encode('utf-8')
    if len(raw) <= limit: return text
    marker = b'\n[explicit excerpt; full captured evidence in audit]\n'
    room = max(0, limit - len(marker))
    if not room: return marker[:limit].decode('utf-8', 'ignore')
    return (raw[:room // 2] + marker + raw[-(room - room // 2):]).decode('utf-8', 'ignore')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_): return None


class Client:
    scale = 1.5

    def __init__(self, key, directory, deadline, script=None, health=None, transport=None):
        self.key = key; self.directory = Path(directory); self.deadline = deadline
        self.logical = 0; self.wire = 0; self.responses = 0
        self.usage = {'prompt_tokens': 0, 'completion_tokens': 0}
        self.script = script; self.health = health or (lambda **_: None)
        self.auxiliary_failure = None; self.transport = transport

    def complete(self, messages, purpose):
        if time.monotonic() >= self.deadline: raise BudgetStop('wall_seconds')
        if self.logical >= 800: raise BudgetStop('model_requests')
        if envelope_bytes(messages) // 4 + HEADROOM > CONTEXT_TOKENS:
            raise BudgetStop('context_allowance')
        self.logical += 1
        save(self.directory / f'logical-{self.logical:04d}.json', {'purpose': purpose, 'messages': messages})
        self.health(model_requests=self.logical)
        if self.script is not None: return self.script(messages, purpose)
        body = {'model': 'deepseek-flash', 'messages': messages, 'temperature': 0,
                'max_tokens': OUTPUT_TOKENS, 'thinking': {'type': 'disabled'}, 'stream': False}
        if purpose.startswith('actor'): body['response_format'] = {'type': 'json_object'}
        payload = json.dumps(body, ensure_ascii=False).encode('utf-8')
        for attempt in range(2):
            if self.wire >= WIRE_LIMIT: raise BudgetStop('wire_attempts')
            remaining = self.deadline - time.monotonic()
            if remaining <= 0: raise BudgetStop('wall_seconds')
            self.wire += 1; seq = self.wire
            save(self.directory / f'request-{seq:04d}.json', {'purpose': purpose, **body})
            self.health(api_attempts=self.wire)
            request = urllib.request.Request('https://api.deepseek.com/chat/completions', data=payload,
                       headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'})
            began = time.monotonic()
            try:
                if self.transport:
                    result = self.transport(body)
                else:
                    with urllib.request.build_opener(NoRedirect()).open(request, timeout=min(90, remaining)) as r:
                        raw = r.read(2 * 1024 * 1024 + 1)
                        if len(raw) > 2 * 1024 * 1024: raise ModelFault('response_bytes')
                        result = json.loads(raw)
                if self.key:
                    result = json.loads(json.dumps(result, ensure_ascii=False).replace(self.key, '[REDACTED]'))
                save(self.directory / f'response-{seq:04d}.json', result)
                usage = result.get('usage', {})
                for k in self.usage: self.usage[k] += usage.get(k, 0)
                base = raw_estimate(messages); actual = usage.get('prompt_tokens')
                if type(actual) is int and base: Client.scale = max(Client.scale, actual / base * 1.10)
                choice = result['choices'][0]
                save(self.directory / f'call-{seq:04d}.json', {'purpose': purpose, 'status': 200,
                     'logical_request': self.logical, 'seconds': time.monotonic() - began,
                     'usage': usage, 'finish_reason': choice.get('finish_reason'),
                     'input_utf8_bytes': len(payload), 'meter_scale': Client.scale,
                     'context_allowance': CONTEXT_TOKENS, 'exact_tokenizer': False})
                if choice.get('finish_reason') == 'length': raise ModelFault('output_tokens_exhausted')
                content = choice['message'].get('content')
                if not isinstance(content, str): raise ModelFault('missing_text')
                self.responses += 1; self.health(api_responses=self.responses)
                return content
            except urllib.error.HTTPError as exc:
                save(self.directory / f'call-{seq:04d}.json', {'purpose': purpose, 'status': exc.code, 'error_type': 'HTTPError'})
                if exc.code in (401, 402, 403) or attempt == 1 or exc.code not in (429, 500, 502, 503, 504):
                    raise ModelFault('http_' + str(exc.code)) from None
            except (urllib.error.URLError, TimeoutError) as exc:
                save(self.directory / f'call-{seq:04d}.json', {'purpose': purpose, 'error_type': type(exc).__name__})
                if attempt == 1: raise ModelFault('transport_failed') from None
        raise ModelFault('transport_failed')

    def json(self, messages, purpose):
        for attempt in range(2):
            raw = self.complete(messages, purpose if attempt == 0 else purpose + '_format_repair')
            try: return json.loads(raw)
            except (ValueError, TypeError):
                if attempt: raise ModelFault('invalid_json') from None
                messages = list(messages) + [{'role': 'assistant', 'content': clip_bytes(raw, 2000)},
                    {'role': 'user', 'content': 'Return only one complete valid JSON object matching the requested schema.'}]
        raise ModelFault('invalid_json')

    def chat_with_usage(self, *, user_content):
        before = dict(self.usage)
        try: content = self.complete([{'role': 'user', 'content': user_content}], 'taco_auxiliary')
        except Exception as exc:
            self.auxiliary_failure = exc
            raise
        return content, {k: self.usage[k] - before[k] for k in self.usage}

    def check_auxiliary(self):
        if self.auxiliary_failure is not None: raise self.auxiliary_failure
