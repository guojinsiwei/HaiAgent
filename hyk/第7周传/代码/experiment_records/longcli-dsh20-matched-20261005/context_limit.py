"""External UTF-8 input allowance, including native tool declarations.

Keep the system prompt, initial task and newest complete tool exchange. Drop
older complete exchanges first; bound tool feedback rather than breaking calls.
No generated summaries, replanning or semantic output repair are introduced.
"""
import copy
import json

LIMIT = 48000


def input_bytes(body):
    return len(json.dumps({k: body[k] for k in ('messages', 'tools') if k in body},
                          ensure_ascii=False).encode('utf-8'))


def bound_text(text, allowance):
    raw = text.encode('utf-8')
    if len(raw) <= allowance:
        return text
    marker = b'\n[experiment output truncated]\n'
    remaining = max(0, allowance - len(marker))
    head = remaining // 2
    tail = remaining - head
    return raw[:head].decode('utf-8', 'ignore') + marker.decode() + (raw[-tail:].decode('utf-8', 'ignore') if tail else '')


def fit_request(original):
    body = copy.deepcopy(original)
    original_size = input_bytes(body)
    messages = body['messages']
    first_user = next((i for i, m in enumerate(messages) if m['role'] == 'user'), None)
    if first_user is None:
        # Auxiliary calls without a task are never silently truncated.
        if input_bytes(body) > LIMIT:
            raise ValueError('LONGCLI_INPUT_BUDGET: auxiliary request exceeds allowance')
        return body, {'before_bytes': original_size, 'after_bytes': original_size, 'dropped_messages': 0}
    pinned = messages[:first_user + 1]
    groups = []
    for message in messages[first_user + 1:]:
        if message['role'] in ('assistant', 'user') or not groups:
            groups.append([])
        groups[-1].append(message)
    # All individual tool feedback uses the historical 24k-byte allowance.
    for group in groups:
        for message in group:
            if message['role'] == 'tool' and isinstance(message.get('content'), str):
                message['content'] = bound_text(message['content'], 24000)
    dropped = 0
    while len(groups) > 1:
        body['messages'] = pinned + [m for group in groups for m in group]
        if input_bytes(body) <= LIMIT:
            break
        dropped += len(groups.pop(0))
    body['messages'] = pinned + [m for group in groups for m in group]
    # Preserve the newest executed action and its call IDs. Only its potentially
    # large textual observations can shrink further when the schema takes space.
    for allowance in (12000, 6000, 3000, 1000, 200):
        if input_bytes(body) <= LIMIT:
            break
        for message in body['messages'][len(pinned):]:
            if message['role'] == 'tool' and isinstance(message.get('content'), str):
                message['content'] = bound_text(message['content'], allowance)
    if input_bytes(body) > LIMIT:
        raise ValueError('LONGCLI_INPUT_BUDGET: mandatory task/schema/latest action exceeds allowance')
    return body, {'before_bytes': original_size, 'after_bytes': input_bytes(body), 'dropped_messages': dropped,
                  'input_unit': 'UTF-8 bytes, messages plus native tool declarations'}
