"""Matched transport only; source Actor/Evaluator/Reflection algorithms remain sealed."""
import json
import os
from pathlib import Path
import re
import time
import urllib.request
from common import save
from context_limit import fit_request, input_bytes
from reflexion.client import ModelConfig, ModelReply, OpenAIChatClient
from reflexion.engine import ReflexionRunner
from reflexion.audit import redact


def byte_clip(text, limit):
    if not isinstance(text, str):
        raise TypeError('Observation must be text')
    size = lambda value: len(json.dumps(value, ensure_ascii=False).encode('utf-8'))
    if size(text) <= limit:
        return text
    raw = text.encode('utf-8')
    marker = f'\n[TRUNCATED: {len(raw)} UTF-8 bytes; middle omitted; full evidence in audit]\n'
    if size(marker) > limit:
        return '[TRUNCATED]'[:max(0, limit - 2)]
    low, high = 0, min(len(raw), limit)
    best = marker
    while low <= high:
        count = (low + high) // 2
        head = count // 2
        tail = count - head
        value = raw[:head].decode('utf-8', errors='ignore') + marker
        if tail:
            value += raw[-tail:].decode('utf-8', errors='ignore')
        if size(value) <= limit:
            best, low = value, count + 1
        else:
            high = count - 1
    return best


class MatchedRunner(ReflexionRunner):
    @staticmethod
    def _size(messages):
        return input_bytes({'messages': messages})

    def _action(self, messages, record):
        hint = ('\nTransport: 4096 output tokens. Keep analysis brief; return a complete small '
                'JSON object with only declared fields. Write large files in manageable chunks. '
                'Command duration must be in [0, 300].')
        if hint not in messages[0]['content']:
            messages[0] = {**messages[0], 'content': messages[0]['content'] + hint}
        return super()._action(messages, record)

    def _review_messages(self, system, instruction, memory, trajectory, record, purpose):
        if purpose == 'reflect':
            system += ('\nKeep only decisive observed progress, failure and next steps. '
                       'Target <=2000 characters; hard original limit is 4000. '
                       'Do not copy full code or terminal logs.')
        messages = super()._review_messages(system, instruction, memory, trajectory, record, purpose)
        boundary = '\n\nCURRENT TRIAL TRAJECTORY:\n'
        prefix, evidence = messages[1]['content'].split(boundary, 1)
        prefix += boundary
        original = evidence
        limit = self.config.max_context_chars - 2000
        room = len(json.dumps(evidence, ensure_ascii=False).encode('utf-8'))
        while self._size(messages) > limit:
            room -= max(1, self._size(messages) - limit)
            if room < 100:
                from reflexion.engine import _Stopped
                raise _Stopped('max_context_chars_reached')
            evidence = byte_clip(original, room)
            messages[1]['content'] = prefix + evidence
        return messages

    def run(self, instruction, terminal):
        # One independent OS process per task; this scoped helper changes units,
        # not selection/evaluation/retry. Raw observations are logged before clip.
        import reflexion.engine as engine
        previous = engine.clip_text
        engine.clip_text = byte_clip
        try:
            return super().run(instruction, terminal)
        finally:
            engine.clip_text = previous


class MatchedClient:
    def __init__(self, key, directory, mock=False, pressure=False, fact=''):
        self.key = key
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.mock, self.pressure, self.fact = mock, pressure, fact
        self.calls = self.wire_attempts = 0
        self.current_purpose = None
        self.steps = {}
        os.environ['REFLEXION_LOCAL_PLACEHOLDER'] = 'not-a-provider-credential'
        self.client = OpenAIChatClient(ModelConfig(model_name='deepseek-flash', base_url='https://api.deepseek.com',
            api_key_env='REFLEXION_LOCAL_PLACEHOLDER', max_attempts=2, timeout_seconds=90,
            max_output_tokens=4096, temperature=0, extra_body={'thinking': {'type': 'disabled'}}), opener=self._open)

    def _open(self, request, timeout):
        self.wire_attempts += 1
        if self.wire_attempts > 1600:
            raise RuntimeError('LONGCLI_WIRE_BUDGET')
        body, audit = fit_request(json.loads(request.data))
        assert body['max_tokens'] == 4096 and body['temperature'] == 0 and body['thinking']['type'] == 'disabled'
        seq = self.wire_attempts
        save(self.directory / f'request-{seq:04d}.json', body)
        save(self.directory / f'context-{seq:04d}.json', {**audit, 'purpose': self.current_purpose})
        actual = urllib.request.Request('https://api.deepseek.com/chat/completions',
            data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'})
        started = time.time()
        try:
            with urllib.request.build_opener(_NoRedirect()).open(actual, timeout=timeout) as response:
                raw, status = response.read(), response.status
            data = json.loads(raw)
            save(self.directory / f'response-{seq:04d}.json', redact(data, secrets=(self.key,)))
            save(self.directory / f'call-{seq:04d}.json', {'status': status, 'purpose': self.current_purpose,
                'logical_request': self.calls, 'seconds': time.time()-started, 'usage': data.get('usage', {}),
                'finish_reasons': [c.get('finish_reason') for c in data.get('choices', [])], 'max_tokens': 4096})
            return _Response(raw)
        except Exception as exc:
            save(self.directory / f'call-{seq:04d}.json', {'purpose': self.current_purpose,
                'logical_request': self.calls, 'error_type': type(exc).__name__, 'status': getattr(exc, 'code', None)})
            raise

    def complete(self, messages, *, purpose, deadline_monotonic=None):
        if self.calls >= 800:
            raise RuntimeError('LONGCLI_MODEL_BUDGET')
        self.calls += 1
        self.current_purpose = purpose
        fit_request({'messages': messages})
        if not self.mock:
            return self.client.complete(messages, purpose=purpose, deadline_monotonic=deadline_monotonic)
        save(self.directory / f'mock-request-{self.calls:04d}.json', {'messages': messages, 'purpose': purpose})
        rendered = json.dumps(messages, ensure_ascii=False)
        if purpose in ('reflect', 'evaluate'):
            # Evidence must occur in observation content, not just planned commands.
            assert re.search(r'Observation for executed command.*?' + re.escape(self.fact), rendered, re.S)
            index = int(re.search(r'"trial": (\d+)', messages[1]['content'])[1])
            if purpose == 'reflect':
                return ModelReply(f'I observed {self.fact} in continuity-proof.txt. REFLEXION_PERSIST remains alive. '
                                  'Completion was premature; reread the file and verify before claiming success.', finish_reason='stop')
            return ModelReply(json.dumps({'passed': index == 3, 'feedback': 'Fixture requires three trials.',
                                         'evidence': [f'Observed continuity-proof.txt: {self.fact}']}), finish_reason='stop')
        assert purpose == 'act', 'Unknown role in keyless acceptance'
        index = int(re.search(r'TRIAL (\d+)', messages[1]['content'])[1])
        step = self.steps.get(index, 0)
        self.steps[index] = step + 1
        if index > 1:
            assert self.fact in messages[1]['content'], 'Fresh Actor has no reflection memory'
        if step > 0 and (not self.pressure or index == 3):
            return ModelReply(json.dumps({'analysis': 'Observed evidence', 'commands': [],
                'task_complete': True, 'final_answer': 'Offline terminal check'}), finish_reason='stop')
        if index == 1 and step == 0:
            command = f"printf '{self.fact}\\n' > continuity-proof.txt; export REFLEXION_PERSIST=alive; "
            command += "python3 -c 'import os,resource,socket; from pathlib import Path; "
            command += "assert len(os.sched_getaffinity(0))==2; assert resource.getrlimit(resource.RLIMIT_AS)[0]==3*2**30; "
            command += "assert not Path(\"/var/run/docker.sock\").exists(); assert not Path(\"/mnt/lizh639\").exists(); "
            command += "assert not any(\"API_KEY\" in k or \"TOKEN\" in k for k in os.environ); "
            command += "assert not Path(\"/tests/run-tests.sh\").exists(); f=os.open(\"/dev/null\",os.O_RDWR); "
            command += "assert os.write(f,b\"ok\")==2; os.close(f); s=socket.socket(); s.settimeout(0.1); "
            command += "assert s.connect_ex((\"1.1.1.1\",443))!=0; print(\"ISOLATION_OK\")'; "
        else:
            command = 'test "$REFLEXION_PERSIST" = alive && cat continuity-proof.txt; '
        if self.pressure and index < 3 and step > 0:
            command += "python3 -c 'print((\"中文\\\"\\\\ pressure row\\n\")*5000)'; "
        command += 'cat continuity-proof.txt\n'
        return ModelReply(json.dumps({'analysis': 'Use persistent shell and episodic reflection',
            'commands': [{'keystrokes': command, 'duration': 1}], 'task_complete': False, 'final_answer': ''}), finish_reason='stop')


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


class _Response:
    def __init__(self, raw): self.raw = raw
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def read(self): return self.raw
