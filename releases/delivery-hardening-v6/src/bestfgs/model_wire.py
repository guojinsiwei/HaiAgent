"""Shared wire integrity checks. Never execute or salvage a partial JSON object."""
from __future__ import annotations

import io
import json
from typing import Any


def collect_stream(response: Any, send: Any = None) -> bytes:
    parts: list[str] = []
    fallback: list[bytes] = []
    pending: list[bytes] = []
    metadata: dict[str, Any] = {}
    usage = None
    finish_reason = None
    saw_sse = False
    done = False
    error = None

    def dispatch() -> None:
        nonlocal usage, finish_reason, done
        if not pending:
            return
        data = b'\n'.join(pending)
        pending.clear()
        if data.strip() == b'[DONE]':
            done = True
            return
        event = json.loads(data.decode('utf-8'))
        if not isinstance(event, dict) or 'error' in event:
            raise ValueError('invalid SSE event or provider error event')
        for key in ('model', 'system_fingerprint'):
            if isinstance(event.get(key), str):
                metadata[key] = event[key]
        if isinstance(event.get('usage'), dict):
            usage = event['usage']
        choices = event.get('choices', [])
        if not isinstance(choices, list) or len(choices) > 1:
            raise ValueError('expected a single streamed choice')
        if choices:
            choice = choices[0]
            if not isinstance(choice, dict) or choice.get('index', 0) != 0:
                raise ValueError('invalid stream choice index')
            reason = choice.get('finish_reason')
            if reason is not None:
                if finish_reason is not None and reason != finish_reason:
                    raise ValueError('conflicting stream finish reasons')
                finish_reason = reason
            delta = choice.get('delta', {})
            if not isinstance(delta, dict):
                raise ValueError('invalid stream delta')
            content = delta.get('content')
            if isinstance(content, str):
                parts.append(content)

    try:
        while not done:
            line = response.readline()
            if not line:
                dispatch()
                break
            if send is not None:
                send.send(('activity',))
            stripped = line.rstrip(b'\r\n')
            if not stripped:
                dispatch()
            elif stripped.startswith(b'data:'):
                saw_sse = True
                pending.append(stripped[5:].lstrip(b' '))
            elif stripped.startswith((b':', b'event:', b'id:', b'retry:')):
                saw_sse = True
            else:
                fallback.append(line)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        # Preserve received usage and content even on an incomplete stream.
        error = type(exc).__name__
    if not saw_sse and error is None:
        return b''.join(fallback)
    return json.dumps({
        'choices': [{'message': {'content': ''.join(parts)}, 'finish_reason': finish_reason}],
        'usage': usage, **metadata,
        '_stream_integrity': {'done': done, 'error': error,
                              'unexpected_lines': bool(fallback)},
    }, ensure_ascii=False).encode('utf-8')


def coalesce_stream(raw: bytes) -> bytes:
    if not raw.strip() or raw.lstrip().startswith(b'{'):
        return raw
    return collect_stream(io.BytesIO(raw))
