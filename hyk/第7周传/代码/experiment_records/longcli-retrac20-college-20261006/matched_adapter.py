"""Budget/transport adapter; the handed-off RE-TRAC engine stays unchanged."""
import json
import os
from pathlib import Path
import re
import time
import urllib.request

from common import save
from context_limit import fit_request, input_bytes
from retrac.client import ModelConfig, ModelReply, OpenAIChatClient
from retrac.engine import RetracRunner
from retrac.audit import redact


class MatchedRunner(RetracRunner):
    @staticmethod
    def _size(messages):
        return input_bytes({'messages': messages})

    def _observation(self, text, max_chars=None):
        if not isinstance(text, str):
            raise TypeError('Terminal observations must be strings')
        limit = min(self.config.max_observation_chars, max_chars) if max_chars is not None else self.config.max_observation_chars
        raw = text.encode('utf-8')
        if len(json.dumps(text,ensure_ascii=False).encode('utf-8')) <= limit:
            return text
        marker = f'\n[observation truncated: {len(raw)} UTF-8 bytes; full output in audit]\n'
        room = max(0, limit - len(json.dumps(marker,ensure_ascii=False).encode('utf-8')))
        if not room:
            return '[truncated]'[:max(0,limit-2)]
        while room:
            candidate=raw[:room//2].decode('utf-8',errors='ignore')+marker+raw[-(room-room//2):].decode('utf-8',errors='ignore')
            if len(json.dumps(candidate,ensure_ascii=False).encode('utf-8'))<=limit:return candidate
            room=max(0,room-max(1,room//10))
        return marker


class MatchedClient:
    """Key is RAM-only on the host, never in the isolated terminal environment."""
    def __init__(self, key, directory, mock=False, pressure=False, fact=''):
        self.key = key
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.mock, self.pressure, self.fact = mock, pressure, fact
        self.calls = self.wire_attempts = 0
        self.current_purpose = None
        self.steps = {}
        # The stock client requires a credential environment name. Supply only
        # an inert placeholder, replacing it inside the trusted opener seam.
        os.environ['RETRAC_LOCAL_PLACEHOLDER'] = 'not-a-provider-credential'
        self.client = OpenAIChatClient(ModelConfig(model_name='deepseek-flash', base_url='https://api.deepseek.com',
            api_key_env='RETRAC_LOCAL_PLACEHOLDER', max_attempts=2, timeout_seconds=90,
            max_output_tokens=4096, temperature=0, extra_body={'thinking': {'type': 'disabled'}}), opener=self._open)

    def _open(self, request, timeout):
        self.wire_attempts += 1
        if self.wire_attempts > 1600:
            raise RuntimeError('LONGCLI_WIRE_BUDGET')
        body = json.loads(request.data)
        body, audit = fit_request(body)
        assert body['max_tokens'] == 4096 and body['temperature'] == 0 and body['thinking']['type'] == 'disabled'
        seq = self.wire_attempts
        save(self.directory / f'request-{seq:04d}.json', body)
        save(self.directory / f'context-{seq:04d}.json', {**audit, 'purpose': self.current_purpose})
        actual = urllib.request.Request('https://api.deepseek.com/chat/completions',
            data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'})
        opener = urllib.request.build_opener(_NoRedirect())
        started = time.time()
        try:
            with opener.open(actual, timeout=timeout) as response:
                raw = response.read()
                status = response.status
            data = json.loads(raw)
            save(self.directory / f'response-{seq:04d}.json', redact(data,secrets=(self.key,)))
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
        # Native offline fixtures call the real recursive engine and terminal.
        save(self.directory / f'mock-request-{self.calls:04d}.json', {'messages': messages, 'purpose': purpose})
        rendered = json.dumps(messages, ensure_ascii=False)
        if purpose == 'compress':
            assert any(m['role']=='user' and re.search(r'(?m)^'+re.escape(self.fact)+r'\r?$',m['content']) for m in messages), 'Compression has no observed evidence (proposed command is insufficient)'
            from retrac.engine import STATE_HEADINGS
            state = '\n'.join(f'{i}) {heading}\n' + (f'Observed file continuity-proof.txt contains {self.fact}; '
                'shell variable RETRAC_PERSIST survives; recheck before use.' if i in (1,3) else 'None.')
                for i, heading in enumerate(STATE_HEADINGS))
            return ModelReply(state, finish_reason='stop')
        match = re.search(r'RE-TRAC rollout (\d+)/', messages[1]['content'])
        index = int(match.group(1))
        step = self.steps.get(index, 0)
        self.steps[index] = step+1
        if index > 1:
            assert self.fact in rendered, 'Fresh rollout has no recursive memory'
        if step > 0 and not self.pressure:
            return ModelReply(json.dumps({'analysis':'Observed persistent evidence', 'commands': [],
                'task_complete': True, 'final_answer':'Offline terminal check'}), finish_reason='stop')
        if step > 0 and index == 8:
            return ModelReply(json.dumps({'analysis':'Final offline rollout', 'commands': [],
                'task_complete': True, 'final_answer':'Offline continuity verified'}), finish_reason='stop')
        if index == 1 and step == 0:
            command = f"printf '{self.fact}\\n' > continuity-proof.txt; export RETRAC_PERSIST=alive; "
            command += "python3 -c 'import os,resource,socket; from pathlib import Path; "
            command += "assert len(os.sched_getaffinity(0))==2; assert resource.getrlimit(resource.RLIMIT_AS)[0]==3*2**30; "
            command += "assert not Path(\"/mnt/lizh639\").exists(); assert not Path(\"/var/run/docker.sock\").exists(); "
            command += "assert not any(\"API_KEY\" in k or \"TOKEN\" in k for k in os.environ); "
            command += "assert not Path(\"/tests/run-tests.sh\").exists(); f=os.open(\"/dev/null\",os.O_RDWR); "
            command += "assert os.write(f,b\"ok\")==2; os.close(f); s=socket.socket(); s.settimeout(0.1); "
            command += "assert s.connect_ex((\"1.1.1.1\",443))!=0; print(\"ISOLATION_OK\")'; "
        else:
            command = 'test "$RETRAC_PERSIST" = alive && cat continuity-proof.txt; '
        if self.pressure:
            command += "awk 'BEGIN{for(i=0;i<900;i++)printf \"pressure row %d abcdefghijklmnopqrstuvwxyz0123456789\\n\",i}'; "
        command += 'cat continuity-proof.txt\n'
        return ModelReply(json.dumps({'analysis':'Use persistent shell and recursive state',
            'commands':[{'keystrokes':command,'duration':1}], 'task_complete':False,'final_answer':''}), finish_reason='stop')


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


class _Response:
    def __init__(self, raw): self.raw=raw
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def read(self): return self.raw
