"""Common, bounded, credential-redacted, hash-chained JSONL audit stream."""
import hashlib
import json
from pathlib import Path
import re
import time

def model_error_fields(error, client=None):
    """Keep safe provider/output categories, never raw exception content."""
    code = getattr(client, 'last_failure_detail', None)
    output_codes = {'output_length', 'json_syntax', 'json_root_type', 'empty_content',
                    'schema_validation', 'nonstop_finish'}
    transport_codes = {'provider_quota','provider_cooldown','transport', 'empty_http_body', 'invalid_response_envelope',
                       'incomplete_stream', 'missing_finish_reason'}
    if not isinstance(code, str) or not (re.fullmatch(r'http_\d{3}', code) or code in output_codes | transport_codes):
        message = str(error)
        code = message if re.fullmatch(r'provider_\d{3}', message) else None
    retryable = None
    if code and re.fullmatch(r'(http|provider)_\d{3}', code):
        status = int(code.rsplit('_', 1)[1])
        retryable = status in {408, 429} or status >= 500
    kind = ('model_output' if code in output_codes else 'transport'
            if code in transport_codes or code and re.fullmatch(r'(http|provider)_\d{3}', code) else None)
    return {'error_code': code, 'failure_kind': kind, 'retryable': retryable}

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))

class Audit:
    def __init__(self, path, secrets=()):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            raise FileExistsError('Audit log already exists; never append a new trial to an old one')
        self.path.touch(exist_ok=False)
        self.secrets = tuple(s for s in secrets if s)
        self.previous = '0' * 64
        self.sequence = 0

    def clean(self, value):
        if isinstance(value, dict):
            return {k: ('[REDACTED]' if any(t in k.lower() for t in ('api_key', 'authorization', 'password', 'secret'))
                        else self.clean(v)) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.clean(v) for v in value]
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, '[REDACTED]')
            return value
        return value

    def emit(self, event, **payload):
        self.sequence += 1
        row = {'seq': self.sequence, 'time': time.time(), 'event': event,
               'previous_sha256': self.previous, **self.clean(payload)}
        row['sha256'] = hashlib.sha256(canonical(row).encode()).hexdigest()
        with self.path.open('a', encoding='utf-8') as stream:
            stream.write(canonical(row) + '\n')
            stream.flush()
        self.previous = row['sha256']

def verify(path):
    previous = '0' * 64
    count = 0
    for count, line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
        row = json.loads(line)
        claimed = row.pop('sha256')
        if row['seq'] != count or row['previous_sha256'] != previous:
            raise ValueError('Audit ordering/hash chain broken')
        if hashlib.sha256(canonical(row).encode()).hexdigest() != claimed:
            raise ValueError('Audit content changed')
        previous = claimed
    return {'events': count, 'tail_sha256': previous}

class JSONClientAudit:
    def __init__(self, inner, audit, role, deadline=None):
        self.inner, self.audit, self.role = inner, audit, role
        self.deadline = deadline

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def complete_json(self, *args, **kwargs):
        if self.deadline is not None:
            from dataclasses import replace
            from bestfgs.models import ModelCallError
            remaining = int(self.deadline - time.monotonic())
            if remaining < 2:
                self.audit.emit('model_budget_stop', role=self.role)
                raise ModelCallError('Cumulative trial wall budget exhausted; preserve candidate')
            self.inner.config = replace(self.inner.config,
                timeout_seconds=min(self.inner.config.timeout_seconds, 90, remaining),
                max_wall_time_seconds=min(self.inner.config.max_wall_time_seconds, 180, remaining))
        self.audit.emit('model_request', role=self.role, args=args, kwargs=kwargs)
        try:
            result = self.inner.complete_json(*args, **kwargs)
        except Exception as error:
            self.audit.emit('model_error', role=self.role, error_type=type(error).__name__,
                            **model_error_fields(error, self.inner))
            raise
        self.audit.emit('model_response', role=self.role, response=result,
                        cumulative_usage=self.inner.usage_summary())
        return result

class HAIClientAudit:
    def __init__(self, inner, audit):
        self.inner, self.audit = inner, audit

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def complete(self, messages, deadline, recorder):
        self.audit.emit('model_request', role='action', messages=messages)
        try:
            result = self.inner.complete(messages, deadline, recorder)
        except Exception as error:
            self.audit.emit('model_error', role='action', error_type=type(error).__name__,
                            **model_error_fields(error, self.inner))
            raise
        self.audit.emit('model_response', role='action', response=result)
        return result
