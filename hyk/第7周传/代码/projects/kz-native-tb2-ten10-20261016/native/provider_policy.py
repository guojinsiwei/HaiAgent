"""Provider availability, separate from model strategy and task failure."""
import datetime
import email.utils
import json
import os
from pathlib import Path
import time

class ProviderQuotaUnavailable(RuntimeError):
    pass

def classify(status, body):
    try:
        value = json.loads(body)
    except (ValueError, TypeError):
        value = {}
    error = value.get('error', value) if isinstance(value, dict) else {}
    if not isinstance(error, dict):
        error = {}
    code = str(error.get('code', error.get('type', ''))).upper()
    message = str(error.get('message', '')).lower()
    quota = code in {'QUOTA', 'INSUFFICIENT_QUOTA', 'QUOTA_EXCEEDED', 'INSUFFICIENT_BALANCE'} or 'no usable token plan quota' in message
    if quota:
        return 'quota'
    if status in (401, 402, 403):
        return 'credentials'
    if status in (408, 429) or status >= 500:
        return 'temporary'
    return 'other'

class ProviderGate:
    def __init__(self, directory, clock=time.time, sleeper=time.sleep):
        self.directory = Path(directory) if directory is not None else None
        self.clock, self.sleeper = clock, sleeper
        self.path = self.directory / 'provider-state.json' if self.directory else None
        self.memory = {}

    def read(self):
        if self.path is None:return self.memory
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return {}

    def record(self, event, **fields):
        if self.directory is None:return
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / 'provider-events.jsonl').open('a') as f:
            f.write(json.dumps(dict(event=event, time=self.clock(), **fields))+'\n')

    def save(self, state):
        if self.path is None:self.memory=state;return
        self.directory.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + f'.{os.getpid()}.tmp')
        tmp.write_text(json.dumps(state))
        tmp.replace(self.path)

    def before(self, seconds):
        state = self.read()
        if state.get('kind') in ('quota', 'credentials', 'budget'):
            raise ProviderQuotaUnavailable(state['kind'])
        delay = max(0, state.get('retry_at', 0) - self.clock())
        if delay >= seconds:
            self.sleeper(max(0, seconds))
            raise TimeoutError('Provider cooldown exceeds current request time allowance')
        if delay:
            self.sleeper(delay)
        return seconds-delay

    def response(self, status, body='', retry_after=None):
        kind = classify(status, body)
        previous = self.read()
        self.record('response', status=status, kind=kind)
        if kind in ('quota', 'credentials'):
            self.save(dict(kind=kind, status=status, updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
        elif kind == 'temporary':
            n = previous.get('consecutive', 0) + 1
            delay = min(60, 5 * 2**min(n-1, 4))
            try:
                explicit = float(retry_after)
            except (ValueError, TypeError):
                try:
                    explicit = email.utils.parsedate_to_datetime(retry_after).timestamp()-self.clock()
                except (ValueError, TypeError, AttributeError):
                    explicit = 0
            delay = max(delay, explicit)
            self.save(dict(kind='temporary', consecutive=n, retry_at=self.clock()+delay, status=status))
        elif 200 <= status < 300:
            self.save(dict(kind='available', consecutive=0))
        return kind
